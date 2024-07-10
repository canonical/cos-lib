#!/usr/bin/env python3
# Copyright 2024 Canonical
# See LICENSE file for licensing details.

"""Shared utilities for the coordinator -> worker "cluster" interface.

As this relation is cluster-internal and not intended for third-party charms to interact with
`-coordinator-k8s`, its only user will be the -worker-k8s charm. As such,
it does not live in a charm lib as most other relation endpoint wrappers do.
"""

import collections
import json
import logging
from typing import (
    Any,
    Counter,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Set,
)
from urllib.parse import urlparse

import ops
import pydantic
import yaml
from cosl import JujuTopology
from ops import EventSource, Object, ObjectEvents, RelationCreatedEvent
from pydantic import ConfigDict

log = logging.getLogger("_cluster")

DEFAULT_ENDPOINT_NAME = "-cluster"
BUILTIN_JUJU_KEYS = {"ingress-address", "private-address", "egress-subnets"}

# =================
# | Databag Model |
# =================

# Note: MutableMapping is imported from the typing module and not collections.abc
# because subscripting collections.abc.MutableMapping was added in python 3.9, but
# most of our charms are based on 20.04, which has python 3.8.

_RawDatabag = MutableMapping[str, str]


class DataValidationError(Exception):
    """Raised when relation databag validation fails."""


class DatabagModel(pydantic.BaseModel):
    """Base databag model."""

    model_config = ConfigDict(
        # tolerate additional keys in databag
        extra="ignore",
        # Allow instantiating this class by field name (instead of forcing alias).
        populate_by_name=True,
        # Custom config key: whether to nest the whole datastructure (as json)
        # under a field or spread it out at the toplevel.
        _NEST_UNDER=None,
        # TODO: Check if this is necessary / good to have
        # Protected namespaces: will warn if keys starts with those
        protected_namespaces=(),
    )  # type: ignore
    """Pydantic config."""

    @classmethod
    def load(cls, databag: _RawDatabag):
        """Load this model from a Juju databag."""
        nest_under = cls.model_config.get("_NEST_UNDER")
        if nest_under:
            return cls.model_validate(json.loads(databag[nest_under]))  # type: ignore

        try:
            data = {
                k: json.loads(v)
                for k, v in databag.items()
                # Don't attempt to parse model-external values
                if k in {(f.alias or n) for n, f in cls.__fields__.items()}  # type: ignore
            }
        except json.JSONDecodeError as e:
            msg = f"invalid databag contents: expecting json. {databag}"
            log.error(msg)
            raise DataValidationError(msg) from e

        try:
            return cls.model_validate_json(json.dumps(data))  # type: ignore
        except pydantic.ValidationError as e:
            msg = f"failed to validate databag: {databag}"
            log.debug(msg, exc_info=True)
            raise DataValidationError(msg) from e

    def dump(self, databag: Optional[_RawDatabag] = None, clear: bool = True) -> None:
        """Write the contents of this model to Juju databag.

        :param databag: the databag to write the data to.
        :param clear: ensure the databag is cleared before writing it.
        """
        if clear and databag:
            databag.clear()

        if databag is None:
            databag = {}
        if nest_under := self.model_config.get("_NEST_UNDER"):
            databag[nest_under] = self.model_dump_json(  # type: ignore
                by_alias=True,
                # skip keys whose values are default
                exclude_defaults=True,
            )

        dct = self.model_dump(mode="json", by_alias=True, exclude_defaults=True)  # type: ignore
        databag.update({k: json.dumps(v) for k, v in dct.items()})


# =============
# | Interface |
# =============


class ConfigReceivedEvent(ops.EventBase):
    """Event emitted when the "-cluster" provider has shared a new  config."""

    config: Dict[str, Any]
    """The  config."""

    def __init__(self, handle: ops.framework.Handle, config: Dict[str, Any]):
        super().__init__(handle)
        self.config = config

    def snapshot(self) -> Dict[str, Any]:
        """Used by the framework to serialize the event to disk.

        Not meant to be called by charm code.
        """
        return {"config": json.dumps(self.config)}

    def restore(self, snapshot: Dict[str, Any]):
        """Used by the framework to deserialize the event from disk.

        Not meant to be called by charm code.
        """
        self.relation = json.loads(snapshot["config"])  # noqa


class ClusterError(Exception):
    """Base class for exceptions raised by this module."""


class DatabagAccessPermissionError(ClusterError):
    """Raised when a follower attempts to write leader settings."""


class _Topology(pydantic.BaseModel):
    """Juju topology information."""

    model: str
    model_uuid: str  # TODO: do we need this? we get it for free but causes pydantic warnings
    application: str
    unit: str
    charm_name: str


class ClusterRequirerAppData(DatabagModel):
    """App data that the worker sends to the coordinator."""

    role: str


class ClusterRequirerUnitData(DatabagModel):
    """Unit data the worker sends to the coordinator."""

    juju_topology: _Topology
    address: str


class ClusterProviderAppData(DatabagModel):
    """App data the the coordinator sends to the worker."""

    ### worker node configuration
    worker_config: str
    """The whole worker workload configuration, whatever it is. E.g. yaml-encoded things."""

    ### self-monitoring stuff
    loki_endpoints: Optional[Dict[str, str]] = None
    """Endpoints to which the workload (and the worker charm) can push logs to."""
    tracing_receivers: Optional[Dict[str, str]] = None
    """Endpoints to which the workload (and the worker charm) can push traces to."""

    ### TLS stuff
    ca_cert: Optional[str] = None
    server_cert: Optional[str] = None
    privkey_secret_id: Optional[str] = None
    """TLS Config"""


class ClusterChangedEvent(ops.EventBase):
    """Event emitted when any "-cluster" relation event fires."""


class ClusterRemovedEvent(ops.EventBase):
    """Event emitted when the relation with the "-cluster" provider has been severed.

    Or when the relation data has been wiped.
    """


class ClusterProviderEvents(ObjectEvents):
    """Events emitted by the ClusterProvider "-cluster" endpoint wrapper."""

    changed = EventSource(ClusterChangedEvent)


class ClusterRequirerEvents(ObjectEvents):
    """Events emitted by the ClusterRequirer "-cluster" endpoint wrapper."""

    config_received = EventSource(ConfigReceivedEvent)
    created = EventSource(RelationCreatedEvent)
    removed = EventSource(ClusterRemovedEvent)


class ClusterProvider(Object):
    """``-cluster`` provider endpoint wrapper."""

    on = ClusterProviderEvents()  # type: ignore

    def __init__(
        self,
        charm: ops.CharmBase,
        roles: FrozenSet[str],
        meta_roles: Optional[Mapping[str, Iterable[str]]] = None,
        key: Optional[str] = None,
        endpoint: str = DEFAULT_ENDPOINT_NAME,
    ):
        super().__init__(charm, key or endpoint)
        self._charm = charm
        self._roles = roles
        self._meta_roles = meta_roles or {}
        self.juju_topology = JujuTopology.from_charm(self._charm)

        # filter out common unhappy relation states
        self._relations: List[ops.Relation] = [
            rel for rel in self.model.relations[endpoint] if (rel.app and rel.data)
        ]

        # we coalesce all -cluster-relation-* events into a single cluster-changed API.
        # the coordinator uses a common exit hook reconciler, that's why.
        self.framework.observe(self._charm.on[endpoint].relation_created, self._on_cluster_changed)
        self.framework.observe(self._charm.on[endpoint].relation_joined, self._on_cluster_changed)
        self.framework.observe(self._charm.on[endpoint].relation_changed, self._on_cluster_changed)
        self.framework.observe(
            self._charm.on[endpoint].relation_departed, self._on_cluster_changed
        )
        self.framework.observe(self._charm.on[endpoint].relation_broken, self._on_cluster_changed)

    def _on_cluster_changed(self, _: ops.EventBase) -> None:
        self.on.changed.emit()

    def grant_privkey(self, label: str) -> str:
        """Grant the secret containing the privkey to all relations, and return the secret ID."""
        secret = self.model.get_secret(label=label)
        for relation in self._relations:
            secret.grant(relation)
        # can't return secret.id because secret was obtained by label, and so
        # we don't have an ID unless we fetch it
        return secret.get_info().id

    def publish_data(
        self,
        worker_config: str,
        ca_cert: Optional[str] = None,
        server_cert: Optional[str] = None,
        privkey_secret_id: Optional[str] = None,
        loki_endpoints: Optional[Dict[str, str]] = None,
    ) -> None:
        """Publish the config to all related worker clusters."""
        for relation in self._relations:
            if relation:
                local_app_databag = ClusterProviderAppData(
                    worker_config=worker_config,
                    loki_endpoints=loki_endpoints,
                    ca_cert=ca_cert,
                    server_cert=server_cert,
                    privkey_secret_id=privkey_secret_id,
                )
                local_app_databag.dump(relation.data[self.model.app])

    @property
    def has_workers(self) -> bool:
        """Return True if the coordinator is connected to any worker."""
        # we use the presence of relations instead of addresses, because we want this
        # check to fail early
        return bool(self._relations)

    def _expand_roles(self, role_string: str) -> Set[str]:
        """Expand the meta-roles from a comma-separated list of roles."""
        expanded_roles: Set[str] = set()
        for role in role_string.split(","):
            if role in self._meta_roles:
                expanded_roles.update(self._meta_roles[role])
            else:
                expanded_roles.update(role)
        return expanded_roles

    def gather_addresses_by_role(self) -> Dict[str, Set[str]]:
        """Go through the worker's unit databags to collect all the addresses published by the units, by role."""
        data: Dict[str, Set[str]] = collections.defaultdict(set)
        for relation in self._relations:

            if not relation.app:
                log.debug(f"skipped {relation} as .app is None")
                continue

            try:
                worker_app_data = ClusterRequirerAppData.load(relation.data[relation.app])
            except DataValidationError as e:
                log.info(f"invalid databag contents: {e}")
                continue

            for worker_unit in relation.units:
                try:
                    worker_data = ClusterRequirerUnitData.load(relation.data[worker_unit])
                    unit_address = worker_data.address
                    for role in self._expand_roles(worker_app_data.role):
                        data[role].add(unit_address)
                except DataValidationError as e:
                    log.info(f"invalid databag contents: {e}")
                    continue

        return data

    def gather_addresses(self) -> Set[str]:
        """Go through the worker's unit databags to collect all the addresses published by the units."""
        data: Set[str] = set()
        addresses_by_role = self.gather_addresses_by_role()
        for _, address_set in addresses_by_role.items():
            data.update(address_set)

        return data

    def gather_roles(self) -> Dict[str, int]:
        """Go through the worker's app databags and sum the available application roles."""
        data: Counter[str] = collections.Counter()
        for relation in self._relations:
            if relation.app:
                remote_app_databag = relation.data[relation.app]
                try:
                    worker_role: str = ClusterRequirerAppData.load(remote_app_databag).role
                except DataValidationError as e:
                    log.error(f"invalid databag contents: {e}")
                    continue

                # the number of units with each role is the number of remote units
                role_n = len(relation.units)  # exclude this unit
                for role in self._expand_roles(worker_role):
                    data[role] += role_n

        dct = dict(data)
        return dct

    def gather_topology(self) -> List[Dict[str, str]]:
        """Gather Juju topology by unit."""
        data: List[Dict[str, str]] = []
        for relation in self._relations:
            if not relation.app:
                continue

            for worker_unit in relation.units:
                try:
                    worker_data = ClusterRequirerUnitData.load(relation.data[worker_unit])
                    unit_address = worker_data.address
                except DataValidationError as e:
                    log.info(f"invalid databag contents: {e}")
                    continue
                worker_topology = {
                    "address": unit_address,
                    "model": worker_data.juju_topology.model,
                    "model_uuid": worker_data.juju_topology.model_uuid,
                    "application": worker_data.juju_topology.application,
                    "unit": worker_data.juju_topology.unit,
                    "charm_name": worker_data.juju_topology.charm_name,
                }
                data.append(worker_topology)

        return data

    def get_address_from_role(self, role: str) -> Optional[str]:
        """Get datasource address."""
        addresses_by_role = self.gather_addresses_by_role()
        if address_set := addresses_by_role.get(role, None):
            return address_set.pop()
        return None


class ClusterRequirer(Object):
    """``-cluster`` requirer endpoint wrapper."""

    on = ClusterRequirerEvents()  # type: ignore

    def __init__(
        self,
        charm: ops.CharmBase,
        key: Optional[str] = None,
        endpoint: str = DEFAULT_ENDPOINT_NAME,
    ):
        super().__init__(charm, key or endpoint)
        self._charm = charm
        self.juju_topology = JujuTopology.from_charm(self._charm)

        relation = self.model.get_relation(endpoint)
        self.relation: Optional[ops.Relation] = (
            relation if relation and relation.app and relation.data else None
        )

        self.framework.observe(
            self._charm.on[endpoint].relation_changed, self._on_cluster_relation_changed  # type: ignore
        )
        self.framework.observe(
            self._charm.on[endpoint].relation_created, self._on_cluster_relation_created  # type: ignore
        )
        self.framework.observe(
            self._charm.on[endpoint].relation_broken, self._on_cluster_relation_broken  # type: ignore
        )

    def _on_cluster_relation_broken(self, _event: ops.RelationBrokenEvent):
        self.on.removed.emit()

    def _on_cluster_relation_created(self, event: ops.RelationCreatedEvent):
        self.on.created.emit(relation=event.relation, app=event.app, unit=event.unit)

    def _on_cluster_relation_changed(self, _event: ops.RelationChangedEvent):
        # to prevent the event from firing if the relation is in an unhealthy state (breaking...)
        if self.relation:
            new_config = self.get_worker_config()
            if new_config:
                self.on.config_received.emit(new_config)

            # if we have published our data, but we receive an empty/invalid config,
            # then the remote end must have removed it.
            elif self.is_published():
                self.on.removed.emit()

    def is_published(self):
        """Verify that the local side has done all they need to do.

        - unit address is published
        - roles are published
        """
        relation = self.relation
        if not relation:
            return False

        unit_data = relation.data[self._charm.unit]
        app_data = relation.data[self._charm.app]

        try:
            ClusterRequirerUnitData.load(unit_data)
            ClusterRequirerAppData.load(app_data)
        except DataValidationError as e:
            log.info(f"invalid databag contents: {e}")
            return False
        return True

    def publish_unit_address(self, url: str):
        """Publish this unit's URL via the unit databag."""
        try:
            urlparse(url)
        except Exception as e:
            raise ValueError(f"{url} is an invalid url") from e

        databag_model = ClusterRequirerUnitData(
            juju_topology=dict(self.juju_topology.as_dict()),  # type: ignore
            address=url,
        )
        relation = self.relation
        if relation:
            unit_databag = relation.data[self.model.unit]  # type: ignore # all checks are done in __init__
            databag_model.dump(unit_databag)

    def publish_app_roles(self, roles: Iterable[str]):
        """Publish this application's roles via the application databag."""
        if not self._charm.unit.is_leader():
            raise DatabagAccessPermissionError("only the leader unit can publish roles.")

        relation = self.relation
        if relation:
            databag_model = ClusterRequirerAppData(role=",".join(roles))
            databag_model.dump(relation.data[self.model.app])

    def _get_data_from_coordinator(self) -> Optional[ClusterProviderAppData]:
        """Fetch the contents of the doordinator databag."""
        data: Optional[ClusterProviderAppData] = None
        relation = self.relation
        # TODO: does this need a leader guard ??? maybe?
        if relation:
            try:
                databag = relation.data[relation.app]  # type: ignore # all checks are done in __init__
                coordinator_databag = ClusterProviderAppData.load(databag)
                data = coordinator_databag
            except DataValidationError as e:
                log.info(f"invalid databag contents: {e}")

        return data

    def get_worker_config(self) -> Dict[str, Any]:
        """Fetch the worker config from the coordinator databag."""
        data = self._get_data_from_coordinator()
        if data:
            return yaml.safe_load(data.worker_config)
        return {}

    def get_loki_endpoints(self) -> Dict[str, str]:
        """Fetch the loki endpoints from the coordinator databag."""
        data = self._get_data_from_coordinator()
        if data:
            return data.loki_endpoints or {}
        return {}

    def get_cert_secret_ids(self) -> Optional[str]:
        """Fetch certificates secrets ids for the worker config."""
        if self.relation and self.relation.app:
            return self.relation.data[self.relation.app].get("secrets", None)
        return None