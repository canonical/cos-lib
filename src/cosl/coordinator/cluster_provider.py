#!/usr/bin/env python3
# Copyright 2024 Canonical
# See LICENSE file for licensing details.

"""Shared utilities for the coordinator -> worker "cluster" interface.

As this relation is cluster-internal and not intended for third-party charms to interact with
`-coordinator-k8s`, its only user will be the -worker-k8s charm. As such,
it does not live in a charm lib as most other relation endpoint wrappers do.
"""

import collections
import enum
import json
import logging
from enum import Enum, unique
from typing import Any, Dict, List, Optional, Set, FrozenSet, Iterable, Mapping

import ops
import pydantic

# The only reason we need the tracing lib is this enum. Not super nice.
from ops import EventSource, Object, ObjectEvents

from databag_model import DatabagModel

from charms.tempo_k8s.v2.tracing import ReceiverProtocol

log = logging.getLogger("_cluster")

DEFAULT_ENDPOINT_NAME = "-cluster"
BUILTIN_JUJU_KEYS = {"ingress-address", "private-address", "egress-subnets"}


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


class JujuTopology(pydantic.BaseModel):
    """JujuTopology."""

    model: str
    unit: str
    # ...


class ClusterRequirerAppData(DatabagModel):
    """ClusterRequirerAppData."""
    role: str


class ClusterRequirerUnitData(DatabagModel):
    """ClusterRequirerUnitData."""
    juju_topology: JujuTopology
    address: str


class ClusterProviderAppData(DatabagModel):
    """ClusterProviderAppData."""

    ### worker node configuration
    worker_config: Dict[str, Any]
    """The whole worker workload configuration, whatever it is."""

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


class ClusterProviderEvents(ObjectEvents):
    """Events emitted by the ClusterProvider "-cluster" endpoint wrapper."""

    changed = EventSource(ClusterChangedEvent)


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
        self.juju_topology = {"unit": self.model.unit.name, "model": self.model.name}

        # filter out common unhappy relation states
        self._relations: List[ops.Relation] = [
            rel for rel in self.model.relations[endpoint] if (rel.app and rel.data)
        ]

        # we coalesce all -cluster-relation-* events into a single cluster-changed API.
        # the coordinator uses a common exit hook reconciler, that's why.
        self.framework.observe(
            self._charm.on[endpoint].relation_joined, self._on_cluster_changed
        )
        self.framework.observe(
            self._charm.on[endpoint].relation_changed, self._on_cluster_changed
        )
        self.framework.observe(
            self._charm.on[endpoint].relation_departed, self._on_cluster_changed
        )
        self.framework.observe(
            self._charm.on[endpoint].relation_broken, self._on_cluster_changed
        )

    def _on_cluster_changed(self, _):
        self.on.changed.emit()

    def publish_privkey(self, label: str) -> str:
        """Grant the secret containing the privkey to all relations, and return the secret ID."""
        secret = self.model.get_secret(label=label)
        for relation in self._relations:
            secret.grant(relation)
        # can't return secret.id because secret was obtained by label, and so
        # we don't have an ID unless we fetch it
        return secret.get_info().id

    def publish_data(
        self,
        _config: Dict[str, Any],
        _receiver: Optional[Dict[ReceiverProtocol, Any]] = None,
        ca_cert: Optional[str] = None,
        server_cert: Optional[str] = None,
        privkey_secret_id: Optional[str] = None,
        loki_endpoints: Optional[Dict[str, str]] = None,
    ) -> None:
        """Publish the  config to all related  worker clusters."""
        for relation in self._relations:
            if relation:
                local_app_databag = ClusterProviderAppData(
                    _config=_config,
                    loki_endpoints=loki_endpoints,
                    _receiver=_receiver,
                    ca_cert=ca_cert,
                    server_cert=server_cert,
                    privkey_secret_id=privkey_secret_id,
                )
                local_app_databag.dump(relation.data[self.model.app])

    @property
    def has_workers(self) -> bool:
        """Return whether this  coordinator has any connected workers."""
        # we use the presence of relations instead of addresses, because we want this
        # check to fail early
        return bool(self._relations)

    def gather_addresses_by_role(self) -> Dict[str, Set[str]]:
        """Go through the worker's unit databags to collect all the addresses published by the units, by role."""
        data = collections.defaultdict(set)
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
                    data[worker_app_data.role].add(unit_address)
                except DataValidationError as e:
                    log.info(f"invalid databag contents: {e}")
                    continue

        return data

    def gather_addresses(self) -> Set[str]:
        """Go through the worker's unit databags to collect all the addresses published by the units."""
        data = set()
        addresses_by_role = self.gather_addresses_by_role()
        for role, address_set in addresses_by_role.items():
            data.update(address_set)

        return data

    def gather_roles(self) -> Dict[str, int]:
        """Go through the worker's app databags and sum the available application roles."""
        data:Counter[str] = collections.Counter()
        for relation in self._relations:
            if relation.app:
                remote_app_databag = relation.data[relation.app]
                try:
                    worker_role: str = ClusterRequirerAppData.load(
                        remote_app_databag
                    ).role
                except DataValidationError as e:
                    log.debug(f"invalid databag contents: {e}")
                    continue

                # the number of units with each role is the number of remote units
                role_n = len(relation.units)  # exclude this unit
                if worker_role in self._meta_roles:
                    for role in self._meta_roles[worker_role]:
                        data[role] += role_n
                    continue

                data[worker_role] += role_n

        dct = dict(data)
        # exclude all roles from the count, if any slipped through
        if Role.all in data:
            del data[Role.all]
        return dct
