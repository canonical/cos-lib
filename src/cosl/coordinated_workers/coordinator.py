#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
"""Generic coordinator for a distributed charm deployment."""

import glob
import json
import logging
import os
import re
import shutil
import socket
from dataclasses import dataclass
from functools import partial
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Set,
    TypedDict,
)
from urllib.parse import urlparse

import ops
import pydantic
import yaml
from ops import StatusBase

import cosl
from cosl.coordinated_workers import worker
from cosl.coordinated_workers.nginx import (
    Nginx,
    NginxMappingOverrides,
    NginxPrometheusExporter,
)
from cosl.helpers import check_libs_installed
from cosl.interfaces.cluster import ClusterProvider, RemoteWriteEndpoint
from cosl.interfaces.datasource_exchange import DatasourceExchange

check_libs_installed(
    "charms.data_platform_libs.v0.s3",
    "charms.grafana_k8s.v0.grafana_source",
    "charms.grafana_k8s.v0.grafana_dashboard",
    "charms.observability_libs.v1.cert_handler",
    "charms.prometheus_k8s.v0.prometheus_scrape",
    "charms.loki_k8s.v1.loki_push_api",
    "charms.tempo_coordinator_k8s.v0.tracing",
    "charms.observability_libs.v0.kubernetes_compute_resources_patch",
    "charms.tls_certificates_interface.v3.tls_certificates",
    "charms.catalogue_k8s.v1.catalogue",
)

from charms.catalogue_k8s.v1.catalogue import CatalogueConsumer, CatalogueItem
from charms.data_platform_libs.v0.s3 import S3Requirer
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v1.loki_push_api import LogForwarder, LokiPushApiConsumer
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    KubernetesComputeResourcesPatch,
    adjust_resource_requirements,
)
from charms.observability_libs.v1.cert_handler import VAULT_SECRET_LABEL, CertHandler
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.tempo_coordinator_k8s.v0.tracing import ReceiverProtocol, TracingEndpointRequirer
from lightkube.models.core_v1 import ResourceRequirements

logger = logging.getLogger(__name__)

# The paths of the base rules to be rendered in CONSOLIDATED_ALERT_RULES_PATH
NGINX_ORIGINAL_ALERT_RULES_PATH = "./src/prometheus_alert_rules/nginx"
WORKER_ORIGINAL_ALERT_RULES_PATH = "./src/prometheus_alert_rules/workers"
# The path of the rules that will be sent to Prometheus
CONSOLIDATED_ALERT_RULES_PATH = "./src/prometheus_alert_rules/consolidated_rules"


class S3NotFoundError(Exception):
    """Raised when the s3 integration is not present or not ready."""


class ClusterRolesConfigError(Exception):
    """Raised when the ClusterRolesConfig instance is not properly configured."""


class S3ConnectionInfo(pydantic.BaseModel):
    """Model for the s3 relation databag, as returned by the s3 charm lib."""

    # they don't use it, we do

    model_config = {"populate_by_name": True}

    endpoint: str
    bucket: str
    access_key: str = pydantic.Field(alias="access-key")  # type: ignore
    secret_key: str = pydantic.Field(alias="secret-key")  # type: ignore

    region: Optional[str] = pydantic.Field(None)  # type: ignore
    tls_ca_chain: Optional[List[str]] = pydantic.Field(None, alias="tls-ca-chain")  # type: ignore

    @property
    def ca_cert(self) -> Optional[str]:
        """Unify the ca chain provided by the lib into a single cert."""
        return "\n\n".join(self.tls_ca_chain) if self.tls_ca_chain else None


@dataclass
class ClusterRolesConfig:
    """Worker roles and deployment requirements."""

    roles: Iterable[str]
    """The union of enabled roles for the application."""
    meta_roles: Mapping[str, Iterable[str]]
    """Meta roles are composed of non-meta roles (default: all)."""
    minimal_deployment: Iterable[str]
    """The minimal set of roles that need to be allocated for the deployment to be considered consistent."""
    recommended_deployment: Dict[str, int]
    """The set of roles that need to be allocated for the deployment to be considered robust according to the official recommendations/guidelines.."""

    def __post_init__(self):
        """Ensure the various role specifications are consistent with one another."""
        are_meta_keys_valid = set(self.meta_roles.keys()).issubset(self.roles)
        are_meta_values_valid = all(
            set(meta_value).issubset(self.roles) for meta_value in self.meta_roles.values()
        )
        is_minimal_valid = set(self.minimal_deployment).issubset(self.roles)
        is_recommended_valid = set(self.recommended_deployment).issubset(self.roles)
        if not all(
            [
                are_meta_keys_valid,
                are_meta_values_valid,
                is_minimal_valid,
                is_recommended_valid,
            ]
        ):
            raise ClusterRolesConfigError(
                "Invalid ClusterRolesConfig: The configuration is not coherent."
            )

    def is_coherent_with(self, cluster_roles: Iterable[str]) -> bool:
        """Returns True if the provided roles satisfy the minimal deployment spec; False otherwise."""
        return set(self.minimal_deployment).issubset(set(cluster_roles))


def _validate_container_name(
    container_name: Optional[str],
    resources_requests: Optional[Callable[["Coordinator"], Dict[str, str]]],
):
    """Raise `ValueError` if `resources_requests` is not None and `container_name` is None."""
    if resources_requests is not None and container_name is None:
        raise ValueError(
            "Cannot have a None value for container_name while resources_requests is provided."
        )


_EndpointMapping = TypedDict(
    "_EndpointMapping",
    {
        "certificates": str,
        "cluster": str,
        "grafana-dashboards": str,
        "logging": str,
        "metrics": str,
        "charm-tracing": str,
        "workload-tracing": str,
        "send-datasource": Optional[str],
        "receive-datasource": Optional[str],
        "s3": str,
        "catalogue": Optional[str],
    },
    total=True,
)
"""Mapping of the relation endpoint names that the charms uses, as defined in metadata.yaml."""

_ResourceLimitOptionsMapping = TypedDict(
    "_ResourceLimitOptionsMapping",
    {
        "cpu_limit": str,
        "memory_limit": str,
    },
)
"""Mapping of the resources limit option names that the charms use, as defined in config.yaml."""


class Coordinator(ops.Object):
    """Charming coordinator.

    This class takes care of the shared tasks of a coordinator, including handling workers,
    running Nginx, and implementing self-monitoring integrations.
    """

    def __init__(
        self,
        charm: ops.CharmBase,
        roles_config: ClusterRolesConfig,
        external_url: str,  # the ingressed url if we have ingress, else fqdn
        worker_metrics_port: int,
        endpoints: _EndpointMapping,
        nginx_config: Callable[["Coordinator"], str],
        workers_config: Callable[["Coordinator"], str],
        nginx_options: Optional[NginxMappingOverrides] = None,
        is_coherent: Optional[Callable[[ClusterProvider, ClusterRolesConfig], bool]] = None,
        is_recommended: Optional[Callable[[ClusterProvider, ClusterRolesConfig], bool]] = None,
        resources_limit_options: Optional[_ResourceLimitOptionsMapping] = None,
        resources_requests: Optional[Callable[["Coordinator"], Dict[str, str]]] = None,
        container_name: Optional[str] = None,
        remote_write_endpoints: Optional[Callable[[], List[RemoteWriteEndpoint]]] = None,
        workload_tracing_protocols: Optional[List[ReceiverProtocol]] = None,
        catalogue_item: Optional[CatalogueItem] = None,
    ):
        """Constructor for a Coordinator object.

        Args:
            charm: The coordinator charm object.
            roles_config: Definition of the roles and the deployment requirements.
            external_url: The external (e.g., ingressed) URL of the coordinator charm.
            worker_metrics_port: The port under which workers expose their metrics.
            nginx_config: A function generating the Nginx configuration file for the workload.
            workers_config: A function generating the configuration for the workers, to be
                published in relation data.
            endpoints: Endpoint names for coordinator relations, as defined in metadata.yaml.
            nginx_options: Non-default config options for Nginx.
            is_coherent: Custom coherency checker for a minimal deployment.
            is_recommended: Custom coherency checker for a recommended deployment.
            resources_limit_options: A dictionary containing resources limit option names. The dictionary should include
                "cpu_limit" and "memory_limit" keys with values as option names, as defined in the config.yaml.
                If no dictionary is provided, the default option names "cpu_limit" and "memory_limit" would be used.
            resources_requests: A function generating the resources "requests" portion to apply when patching a container using
                KubernetesComputeResourcesPatch. The "limits" portion of the patch gets populated by setting
                their respective config options in config.yaml.
            container_name: The container for which to apply the resources requests & limits.
                Required if `resources_requests` is provided.
            remote_write_endpoints: A function generating endpoints to which the workload
                and the worker charm can push metrics to.
            workload_tracing_protocols: A list of protocols that the worker intends to send
                workload traces with.
            catalogue_item: A catalogue application entry to be sent to catalogue.

        Raises:
        ValueError:
            If `resources_requests` is not None and `container_name` is None, a ValueError is raised.
        """
        super().__init__(charm, key="coordinator")
        self._charm = charm
        self.topology = cosl.JujuTopology.from_charm(self._charm)
        self._external_url = external_url
        self._worker_metrics_port = worker_metrics_port
        self._endpoints = endpoints

        _validate_container_name(container_name, resources_requests)
        self.roles_config = roles_config

        self.cluster = ClusterProvider(
            self._charm,
            frozenset(roles_config.roles),
            roles_config.meta_roles,
            endpoint=self._endpoints["cluster"],
        )

        self._is_coherent = is_coherent
        self._is_recommended = is_recommended
        self._resources_requests_getter = (
            partial(resources_requests, self) if resources_requests is not None else None
        )
        self._container_name = container_name
        self._resources_limit_options = resources_limit_options or {}
        self.remote_write_endpoints_getter = remote_write_endpoints
        self._catalogue_item = catalogue_item

        self.nginx = Nginx(
            self._charm,
            partial(nginx_config, self),
            options=nginx_options,
        )
        self._workers_config_getter = partial(workers_config, self)
        self.nginx_exporter = NginxPrometheusExporter(self._charm, options=nginx_options)

        self.cert_handler = CertHandler(
            self._charm,
            certificates_relation_name=self._endpoints["certificates"],
            # let's assume we don't need the peer relation as all coordinator charms will assume juju secrets
            key="coordinator-server-cert",
            # update certificate with new SANs whenever a worker is added/removed
            sans=[self.hostname, *self.cluster.gather_addresses()],
        )

        self.s3_requirer = S3Requirer(self._charm, self._endpoints["s3"])
        self.datasource_exchange = DatasourceExchange(
            self._charm,
            provider_endpoint=self._endpoints.get("send-datasource", None),
            requirer_endpoint=self._endpoints.get("receive-datasource", None),
        )

        self._grafana_dashboards = GrafanaDashboardProvider(
            self._charm, relation_name=self._endpoints["grafana-dashboards"]
        )

        self._logging = LokiPushApiConsumer(self._charm, relation_name=self._endpoints["logging"])
        self._log_forwarder = LogForwarder(self._charm, relation_name=self._endpoints["logging"])

        # Provide ability for this to be scraped by Prometheus using prometheus_scrape
        refresh_events = [self._charm.on.update_status, self.cluster.on.changed]
        if self.cert_handler:
            refresh_events.append(self.cert_handler.on.cert_changed)

        self._render_alert_rules()
        self._scraping = MetricsEndpointProvider(
            self._charm,
            relation_name=self._endpoints["metrics"],
            alert_rules_path=CONSOLIDATED_ALERT_RULES_PATH,
            jobs=self._scrape_jobs,
            external_url=self._external_url,
            refresh_event=refresh_events,
        )

        self.charm_tracing = TracingEndpointRequirer(
            self._charm,
            relation_name=self._endpoints["charm-tracing"],
            protocols=["otlp_http"],
        )
        self.workload_tracing = TracingEndpointRequirer(
            self._charm,
            relation_name=self._endpoints["workload-tracing"],
            protocols=workload_tracing_protocols,
        )

        # Resources patch
        self.resources_patch = (
            KubernetesComputeResourcesPatch(
                self._charm,
                self._container_name,  # type: ignore
                resource_reqs_func=self._adjust_resource_requirements,
            )
            if self._resources_requests_getter
            else None
        )

        self.catalogue = (
            CatalogueConsumer(self._charm, item=self._catalogue_item)
            if self._endpoints.get("catalogue", None)
            else None
        )

        # We always listen to collect-status
        self.framework.observe(self._charm.on.collect_unit_status, self._on_collect_unit_status)

        # If the cluster isn't ready, refuse to handle any other event as we can't possibly know what to do
        if not self.cluster.has_workers:
            logger.warning(
                f"Incoherent deployment. {charm.unit.name} is missing relation to workers. "
                "This charm will be unresponsive and refuse to handle any event until "
                "the situation is resolved by the cloud admin, to avoid data loss."
            )
            return
        if not self.is_coherent:
            logger.error(
                f"Incoherent deployment. {charm.unit.name} will be shutting down. "
                "This likely means you are lacking some required roles in your workers. "
                "This charm will be unresponsive and refuse to handle any event until "
                "the situation is resolved by the cloud admin, to avoid data loss."
            )
            return
        if self.cluster.has_workers and not self.s3_ready:
            logger.error(
                f"Incoherent deployment. {charm.unit.name} will be shutting down. "
                "This likely means you need to add an s3 integration. "
                "This charm will be unresponsive and refuse to handle any event until "
                "the situation is resolved by the cloud admin, to avoid data loss."
            )
            return

        self._reconcile()

    ######################
    # UTILITY PROPERTIES #
    ######################

    @property
    def _charm_tracing_receivers_urls(self) -> Dict[str, str]:
        """Returns the charm tracing enabled receivers with their corresponding endpoints."""
        endpoints = self.charm_tracing.get_all_endpoints()
        receivers = endpoints.receivers if endpoints else ()
        return {receiver.protocol.name: receiver.url for receiver in receivers}

    @property
    def _workload_tracing_receivers_urls(self) -> Dict[str, str]:
        """Returns the workload tracing enabled receivers with their corresponding endpoints."""
        endpoints = self.workload_tracing.get_all_endpoints()
        receivers = endpoints.receivers if endpoints else ()
        return {receiver.protocol.name: receiver.url for receiver in receivers}

    @property
    def is_coherent(self) -> bool:
        """Check whether this coordinator is coherent."""
        if manual_coherency_checker := self._is_coherent:
            return manual_coherency_checker(self.cluster, self.roles_config)

        return self.roles_config.is_coherent_with(self.cluster.gather_roles().keys())

    @property
    def missing_roles(self) -> Set[str]:
        """What roles are missing from this cluster, if any."""
        roles = self.cluster.gather_roles()
        missing_roles: Set[str] = set(self.roles_config.minimal_deployment).difference(
            roles.keys()
        )
        return missing_roles

    @property
    def is_recommended(self) -> Optional[bool]:
        """Check whether this coordinator is connected to the recommended number of workers.

        Will return None if no recommended criterion is defined.
        """
        if manual_recommended_checker := self._is_recommended:
            return manual_recommended_checker(self.cluster, self.roles_config)

        rc = self.roles_config
        if not rc.recommended_deployment:
            # we don't have a definition of recommended: return None
            return None

        cluster = self.cluster
        roles = cluster.gather_roles()
        for role, min_n in rc.recommended_deployment.items():
            if roles.get(role, 0) < min_n:
                return False
        return True

    @property
    def can_handle_events(self) -> bool:
        """Check whether the coordinator should handle events."""
        return self.cluster.has_workers and self.is_coherent and self.s3_ready

    @property
    def hostname(self) -> str:
        """Unit's hostname."""
        return socket.getfqdn()

    @property
    def _internal_url(self) -> str:
        """Unit's hostname including the scheme."""
        scheme = "https" if self.tls_available else "http"
        return f"{scheme}://{self.hostname}"

    @property
    def tls_available(self) -> bool:
        """Return True if tls is enabled and the necessary certs are found."""
        return (
            self.cert_handler.enabled
            and (self.cert_handler.server_cert is not None)
            and (self.cert_handler.private_key is not None)  # type: ignore
            and (self.cert_handler.ca_cert is not None)
        )

    @property
    def s3_connection_info(self) -> S3ConnectionInfo:
        """Cast and validate the untyped s3 databag to something we can handle."""
        try:
            # we have to type-ignore here because the s3 lib's type annotation is wrong
            return S3ConnectionInfo(**self.s3_requirer.get_s3_connection_info())  # type: ignore
        except pydantic.ValidationError:
            raise S3NotFoundError("s3 integration inactive or interface corrupt")

    @property
    def _s3_config(self) -> Dict[str, Any]:
        """The s3 configuration from relation data.

        The configuration is adapted to a drop-in format for the HA workers to use.

        Raises:
            S3NotFoundError: The s3 integration is inactive.
        """
        s3_data = self.s3_connection_info
        s3_config = {
            "endpoint": re.sub(rf"^{urlparse(s3_data.endpoint).scheme}://", "", s3_data.endpoint),
            "region": s3_data.region,
            "access_key_id": s3_data.access_key,
            "secret_access_key": s3_data.secret_key,
            "bucket_name": s3_data.bucket,
            "insecure": not s3_data.tls_ca_chain,
            # the tempo config wants a path to a file here. We pass the cert chain separately
            # over the cluster relation; the worker will be responsible for writing the file to disk
            "tls_ca_path": worker.S3_TLS_CA_CHAIN_FILE if s3_data.tls_ca_chain else None,
        }

        return s3_config

    @property
    def s3_ready(self) -> bool:
        """Check whether s3 is configured."""
        try:
            return bool(self._s3_config)
        except S3NotFoundError:
            return False

    @property
    def peer_addresses(self) -> List[str]:
        """If a peer relation is present, return the addresses of the peers."""
        peers = self._peers
        relation = self.model.get_relation("peers")
        # get unit addresses for all the other units from a databag
        addresses = []
        if peers and relation:
            addresses = [relation.data[unit].get("local-ip") for unit in peers]
            addresses = list(filter(None, addresses))

        # add own address
        if self._local_ip:
            addresses.append(self._local_ip)

        return addresses

    @property
    def _local_ip(self) -> Optional[str]:
        """Local IP of the peers binding."""
        try:
            binding = self.model.get_binding("peers")
            if not binding:
                logger.error(
                    "unable to get local IP at this time: "
                    "peers binding not active yet. It could be that the charm "
                    "is still being set up..."
                )
                return None
            return str(binding.network.bind_address)
        except (ops.ModelError, KeyError) as e:
            logger.debug("failed to obtain local ip from peers binding", exc_info=True)
            logger.error(
                f"unable to get local IP at this time: failed with {type(e)}; "
                f"see debug log for more info"
            )
            return None

    @property
    def _workers_scrape_jobs(self) -> List[Dict[str, Any]]:
        """The Prometheus scrape jobs for the workers connected to the coordinator."""
        scrape_jobs: List[Dict[str, Any]] = []

        for worker_topology in self.cluster.gather_topology():
            job = {
                "static_configs": [
                    {
                        "targets": [f"{worker_topology['address']}:{self._worker_metrics_port}"],
                    }
                ],
                # setting these as "labels" in the static config gets some of them
                # replaced by the coordinator topology
                # https://github.com/canonical/prometheus-k8s-operator/issues/571
                "relabel_configs": [
                    {"target_label": "juju_charm", "replacement": worker_topology["charm_name"]},
                    {"target_label": "juju_unit", "replacement": worker_topology["unit"]},
                    {
                        "target_label": "juju_application",
                        "replacement": worker_topology["application"],
                    },
                    {"target_label": "juju_model", "replacement": self.model.name},
                    {"target_label": "juju_model_uuid", "replacement": self.model.uuid},
                ],
            }
            if self.tls_available:
                job["scheme"] = "https"  # pyright: ignore
            scrape_jobs.append(job)
        return scrape_jobs

    @property
    def _nginx_scrape_jobs(self) -> List[Dict[str, Any]]:
        """The Prometheus scrape job for Nginx."""
        job: Dict[str, Any] = {
            "static_configs": [
                {"targets": [f"{self.hostname}:{self.nginx.options['nginx_exporter_port']}"]}
            ]
        }

        return [job]

    @property
    def _scrape_jobs(self) -> List[Dict[str, Any]]:
        """The scrape jobs to send to Prometheus."""
        return self._workers_scrape_jobs + self._nginx_scrape_jobs

    ##################
    # EVENT HANDLERS #
    ##################

    def _on_peers_relation_created(self, event: ops.RelationCreatedEvent):
        if self._local_ip:
            event.relation.data[self._charm.unit]["local-ip"] = self._local_ip

    # keep this event handler at the bottom
    def _on_collect_unit_status(self, e: ops.CollectStatusEvent):
        # todo add [nginx.workload] statuses
        statuses: List[StatusBase] = []

        if self.resources_patch and self.resources_patch.get_status().name != "active":
            statuses.append(self.resources_patch.get_status())

        if not self.cluster.has_workers:
            statuses.append(ops.BlockedStatus("[consistency] Missing any worker relation."))
        elif not self.is_coherent:
            statuses.append(ops.BlockedStatus("[consistency] Cluster inconsistent."))
        elif not self.is_recommended:
            # if is_recommended is None: it means we don't have a recommended deployment criterion.
            statuses.append(ops.ActiveStatus("Degraded."))

        if not self.s3_requirer.relations:
            statuses.append(ops.BlockedStatus("[s3] Missing S3 integration."))
        elif not self.s3_ready:
            statuses.append(ops.BlockedStatus("[s3] S3 not ready (probably misconfigured)."))

        if not statuses:
            statuses.append(ops.ActiveStatus())

        for status in statuses:
            e.add_status(status)

    ###################
    # UTILITY METHODS #
    ###################
    def _update_nginx_tls_certificates(self) -> None:
        """Update the TLS certificates for nginx on disk according to their availability."""
        if self.tls_available:
            self.nginx.configure_tls(
                server_cert=self.cert_handler.server_cert,  # type: ignore
                ca_cert=self.cert_handler.ca_cert,  # type: ignore
                private_key=self.cert_handler.private_key,  # type: ignore
            )
        else:
            self.nginx.delete_certificates()

    def _reconcile(self):
        """Run all logic that is independent of what event we're processing."""
        # There could be a race between the resource patch and pebble operations
        # i.e., charm code proceeds beyond a can_connect guard, and then lightkube patches the statefulset
        # and the workload is no longer available.
        # `resources_patch` might be `None` when no resources requests or limits are requested by the charm.
        if self.resources_patch and not self.resources_patch.is_ready():
            logger.debug("Resource patch not ready yet. Skipping cluster update step.")
            return

        self._update_nginx_tls_certificates()
        self.update_cluster()
        if self.catalogue:
            self.catalogue.update_item(item=self._catalogue_item)  # type: ignore

    @property
    def _peers(self) -> Optional[Set[ops.model.Unit]]:
        relation = self.model.get_relation("peers")
        if not relation:
            return None

        # self is not included in relation.units
        return relation.units

    @property
    def loki_endpoints_by_unit(self) -> Dict[str, str]:
        """Loki endpoints from relation data in the format needed for Pebble log forwarding.

        Returns:
            A dictionary of remote units and the respective Loki endpoint.
            {
                "loki/0": "http://loki:3100/loki/api/v1/push",
                "another-loki/0": "http://another-loki:3100/loki/api/v1/push",
            }
        """
        endpoints: Dict[str, str] = {}
        relations: List[ops.Relation] = self.model.relations.get(self._endpoints["logging"], [])

        for relation in relations:
            for unit in relation.units:
                if "endpoint" not in relation.data[unit]:
                    continue
                endpoint = relation.data[unit]["endpoint"]
                deserialized_endpoint = json.loads(endpoint)
                url = deserialized_endpoint["url"]
                endpoints[unit.name] = url

        return endpoints

    def update_cluster(self):
        """Build the workers config and distribute it to the relations."""
        self.nginx.configure_pebble_layer()
        self.nginx_exporter.configure_pebble_layer()
        if not self.is_coherent:
            logger.error("skipped cluster update: incoherent deployment")
            return

        if not self._charm.unit.is_leader():
            return

        # we share the certs in plaintext as they're not sensitive information
        # On every function call, we always publish everything to the databag; however, if there
        # are no changes, Juju will notice there's no delta and do nothing
        self.cluster.publish_data(
            worker_config=self._workers_config_getter(),
            loki_endpoints=self.loki_endpoints_by_unit,
            # all arguments below are optional:
            ca_cert=self.cert_handler.ca_cert,
            server_cert=self.cert_handler.server_cert,
            # FIXME tls_available check is due to fetching secret from vault. We should be generating a new secret.
            # see https://github.com/canonical/cos-lib/issues/49 for full context
            privkey_secret_id=(
                self.cluster.grant_privkey(VAULT_SECRET_LABEL) if self.tls_available else None
            ),
            charm_tracing_receivers=self._charm_tracing_receivers_urls,
            workload_tracing_receivers=self._workload_tracing_receivers_urls,
            remote_write_endpoints=(
                self.remote_write_endpoints_getter()
                if self.remote_write_endpoints_getter
                else None
            ),
            s3_tls_ca_chain=self.s3_connection_info.ca_cert,
        )

    def _render_workers_alert_rules(self):
        """Regenerate the worker alert rules from relation data."""
        self._remove_rendered_alert_rules()

        apps: Set[str] = set()
        for worker_topology in self.cluster.gather_topology():
            if worker_topology["application"] in apps:
                continue

            apps.add(worker_topology["application"])
            topology_dict = {
                "model": self.model.name,
                "model_uuid": self.model.uuid,
                "application": worker_topology["application"],
                "unit": worker_topology["unit"],
                "charm_name": worker_topology["charm_name"],
            }
            topology = cosl.JujuTopology.from_dict(topology_dict)
            alert_rules = cosl.AlertRules(query_type="promql", topology=topology)
            alert_rules.add_path(WORKER_ORIGINAL_ALERT_RULES_PATH, recursive=True)
            alert_rules_contents = yaml.dump(alert_rules.as_dict())

            file_name = (
                f"{CONSOLIDATED_ALERT_RULES_PATH}/rendered_{worker_topology['application']}.rules"
            )
            with open(file_name, "w") as writer:
                writer.write(alert_rules_contents)

    def _remove_rendered_alert_rules(self):
        files = glob.glob(f"{CONSOLIDATED_ALERT_RULES_PATH}/rendered_*")
        for f in files:
            os.remove(f)

    def _consolidate_nginx_alert_rules(self):
        """Copy Nginx alert rules to the consolidated alert folder."""
        for filename in glob.glob(os.path.join(NGINX_ORIGINAL_ALERT_RULES_PATH, "*.*")):
            shutil.copy(filename, f"{CONSOLIDATED_ALERT_RULES_PATH}/")

    def _render_alert_rules(self):
        """Render the alert rules for Nginx and the connected workers."""
        os.makedirs(CONSOLIDATED_ALERT_RULES_PATH, exist_ok=True)
        self._render_workers_alert_rules()
        self._consolidate_nginx_alert_rules()

    def _adjust_resource_requirements(self) -> ResourceRequirements:
        """A method that gets called by `KubernetesComputeResourcesPatch` to adjust the resources requests and limits to patch."""
        cpu_limit_key = self._resources_limit_options.get("cpu_limit", "cpu_limit")
        memory_limit_key = self._resources_limit_options.get("memory_limit", "memory_limit")

        limits = {
            "cpu": self._charm.model.config.get(cpu_limit_key),
            "memory": self._charm.model.config.get(memory_limit_key),
        }
        return adjust_resource_requirements(
            limits, self._resources_requests_getter(), adhere_to_requests=True  # type: ignore
        )
