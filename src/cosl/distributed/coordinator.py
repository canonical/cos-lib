#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.


from functools import partial
import json
import logging
import socket
from typing import Any, Callable, Dict, List, Optional, Protocol, Set, Mapping, Iterable, Type, TypedDict

import ops

from cosl.juju_topology import JujuTopology
from cosl.coordinator.cluster_provider import ClusterProvider
from cosl.helpers import check_libs_installed
from cosl.coordinator.nginx import Nginx, NGINX_PROMETHEUS_EXPORTER_PORT

check_libs_installed(
        "charms.data_platform_libs.v0.s3",
        "charms.grafana_k8s.v0.grafana_source",
        "charms.observability_libs.v1.cert_handler",
        "charms.grafana_k8s.v0.grafana_dashboard",
        "charms.observability_libs.v1.cert_handler",
        "charms.prometheus_k8s.v0.prometheus_scrape",
        "charms.loki_k8s.v1.loki_push_api",
        "charms.tempo_k8s.v2.tracing",
    )


from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.observability_libs.v1.cert_handler import CertHandler
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.loki_k8s.v1.loki_push_api import LokiPushApiConsumer
from charms.tempo_k8s.v2.tracing import TracingEndpointRequirer
from charms.data_platform_libs.v0.s3 import S3Requirer
from charms.grafana_k8s.v0.grafana_source import GrafanaSourceProvider
from charms.observability_libs.v1.cert_handler import VAULT_SECRET_LABEL, CertHandler


logger = logging.getLogger(__name__)


NGINX_ORIGINAL_ALERT_RULES_PATH = "./src/prometheus_alert_rules/nginx"
WORKER_ORIGINAL_ALERT_RULES_PATH = "./src/prometheus_alert_rules/mimir_workers"
CONSOLIDATED_ALERT_RULES_PATH = "./src/prometheus_alert_rules/consolidated_rules"

class S3NotFoundError(Exception):
    """Raised when the s3 integration is not present or not ready."""


class ClusterRolesConfig(Protocol):
    Role: Iterable[str]
    meta_roles: Dict[str, Iterable[str]]
    minimal_deployment: Iterable[str]
    recommended_deployment: Dict[str, int]


_EndpointMapping=TypedDict(
    '_EndpointMapping',
    {'certificates':str,
    'tracing':str,
    'logging':str,
    'grafana-dashboards':str,
    'metrics':str,
    's3':str},
    total=True
)

_EndpointMappingOverrides=TypedDict(
    '_EndpointMappingOverrides',
    {'certificates':str,
    'tracing':str,
    'logging':str,
    'grafana-dashboards':str,
    'metrics':str,
    's3':str},
    total=False
)

class Coordinator(ops.Object):
    """Charming coordinator."""
    _endpoints:_EndpointMapping = {
                 "certificates": "certificates",
                 "tracing": "tracing",
                 "logging": "logging",
                 "grafana-dashboards": "grafana-dashboards",
                 "metrics": "metrics-endpoint",
                 "s3": "s3",
        }

    def __init__(self,
                 charm: ops.CharmBase,
                 roles_config: ClusterRolesConfig,

                 s3_bucket_name: str,
                 external_url: str, # the ingressed url if we have ingress, else fqdn
                 metrics_port: str,
                 
                 nginx_config: Callable[["Coordinator"], str],
                 workers_config: Callable[["Coordinator"], str],

                 endpoints: Optional[_EndpointMappingOverrides] = None,
                 is_coherent: Optional[Callable[[ClusterProvider, ClusterRolesConfig], bool]] = None,
                 is_recommended: Optional[Callable[[ClusterProvider, ClusterRolesConfig], bool]] = None,
                 ):  # type: ignore
        super().__init__(charm, key="coordinator")
        self._charm = charm
        self._topology = JujuTopology.from_charm(self._charm)
        self._external_url = external_url
        self._metrics_port = metrics_port
        
        self._nginx_container = nginx_container or self.charm.unit.get_container("nginx")

        _endpoints = self._endpoints
        _endpoints.update(endpoints or {})

        self.roles_config = roles_config

        # TODO: get and pass the cluster relation name
        self.cluster = ClusterProvider(
            self._charm, frozenset(roles_config.Role),
            roles_config.meta_roles
            )
        
        self._is_coherent = is_coherent
        self._is_recommended = is_recommended
        
        self.nginx = Nginx(self._charm, 
                           partial(nginx_config, self)  # type:ignore
                           )
        self._workers_config_getter = partial(workers_config, self)


        self.cert_handler = CertHandler(
            self._charm,
            certificates_relation_name=_endpoints['certificates'],
            # let's assume we don't need the peer relation as all coordinator charms will assume juju secrets
            key="coordinator-server-cert",
            sans=[socket.getfqdn()],
        )

        self.s3_requirer = S3Requirer(self._charm, _endpoints['s3'], s3_bucket_name)

        self._grafana_dashboards = GrafanaDashboardProvider(
            self._charm, relation_name=_endpoints["grafana-dashboards"]
        )

        self._logging = LokiPushApiConsumer(self._charm, relation_name=_endpoints["logging"])

        # Provide ability for this to be scraped by Prometheus using prometheus_scrape
        refresh_events = [self._charm.on.update_status]
        # TODO: add cluster joined/changed/departed/broken events to refresh_events
        if self.cert_handler:
            refresh_events.append(self.cert_handler.on.cert_changed)

        self._render_alert_rules()
        self._scraping = MetricsEndpointProvider(
            self,
            relation_name=_endpoints["metrics"],
            alert_rules_path=CONSOLIDATED_ALERT_RULES_PATH,
            jobs=self._scrape_jobs,
            external_url=self._external_url,
            refresh_event=refresh_events
        )

        self.tracing = TracingEndpointRequirer(
            self._charm,
            relation_name=_endpoints['tracing'],
            protocols=["otlp_http"]
        )
        
        # We always listen to collect-status
        self.framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)

        if not self.is_coherent:
            logger.error(
                f"Incoherent deployment. {charm.unit.name} will be shutting down. "
                "This likely means you need to add an s3 integration. "
                "This charm will be unresponsive and refuse to handle any event until "
                "the situation is resolved by the cloud admin, to avoid data loss."
            )
            return  # refuse to handle any other event as we can't possibly know what to do.

        # lifecycle
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        # nginx
        self.framework.observe(self.on.nginx_pebble_ready, self._on_nginx_pebble_ready)
        self.framework.observe(self.on.nginx_prometheus_exporter_pebble_ready, self._on_nginx_prometheus_exporter_pebble_ready)

        # s3
        self.framework.observe(
            self.s3_requirer.on.credentials_changed, self._on_s3_credentials_changed
        )
        self.framework.observe(self.s3_requirer.on.credentials_gone, self._on_s3_credentials_gone)

        # tracing
        self.framework.observe(self.on.peers_relation_created, self._on_peers_relation_created)
        self.framework.observe(self.on.peers_relation_changed, self._on_peers_relation_changed)

        # logging
        self.framework.observe(self._logging.on.loki_push_api_endpoint_joined, self._on_loki_relation_changed)
        self.framework.observe(self._logging.on.loki_push_api_endpoint_departed, self._on_loki_relation_changed)

        # tls
        self.framework.observe(self.cert_handler.on.cert_changed, self._on_cert_handler_changed)

        # cluster
        self.framework.observe(self.cluster.on.changed, self._on_cluster_changed)

    ######################
    # UTILITY PROPERTIES #
    ######################

    @property
    def is_coherent(self) -> bool:
        """Check whether this coordinator is coherent."""

        if manual_coherency_checker := self._is_coherent:
            return manual_coherency_checker(self.cluster, self.roles_config)
            
        rc = self.roles_config
        minimal_deployment = set(rc.minimal_deployment)
        cluster = self.cluster
        roles = cluster.gather_roles()

        # Whether the roles list makes up a coherent mimir deployment.
        is_coherent = set(roles.keys()).issuperset(minimal_deployment)
        
        return is_coherent
        
    @property
    def missing_roles(self) -> Set[str]:
        """What roles are missing from this cluster, if any."""
        roles = self.cluster.gather_roles()
        missing_roles: Set[str] = set(self.roles_config.minimal_deployment).difference(roles.keys())
        return missing_roles
        
    @property
    def is_recommended(self) -> Optional[bool]:
        """Check whether this coordinator is connected to the recommended number of workers.
        
        Will return None if no recommended criterion is defined.
        """
        if manual_recommended_checker := self._is_recommended:
            return manual_recommended_checker(self.cluster, self.roles_config)

        rc = self.roles_config
        if rc.recommended_deployment:
            cluster = self.cluster
            roles = cluster.gather_roles()
            for role, min_n in rc.recommended_deployment.items():
                if roles.get(role, 0) < min_n:
                    return False
            return True
        
        else:
            # we don't have a definition of recommended: return None
            return None


    @property
    def is_clustered(self) -> bool:
        """Check whether this coordinator has worker nodes connected to it."""
        return self.cluster.has_workers


    @property
    def hostname(self) -> str:
        """Unit's hostname."""
        return socket.getfqdn()

    @property
    def _internal_url(self) -> str:
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
    def _s3_config(self) -> dict[str, Any]:
        s3_config = self.s3_requirer.get_s3_connection_info()
        if (
            s3_config
            and "bucket" in s3_config
            and "endpoint" in s3_config
            and "access-key" in s3_config
            and "secret-key" in s3_config
        ):
            return s3_config
        raise S3NotFoundError("s3 integration inactive")

    @property
    def s3_ready(self) -> bool:
        """Check whether s3 is configured."""
        try:
            return bool(self._s3_config)
        except S3NotFoundError:
            return False

    @property
    def peer_addresses(self) -> List[str]:
        peers = self._peers
        relation = self.model.get_relation("peers")
        # get unit addresses for all the other units from a databag
        if peers and relation:
            addresses = [relation.data[unit].get("local-ip") for unit in peers]
            addresses = list(filter(None, addresses))
        else:
            addresses = []

        # add own address
        if self._local_ip:
            addresses.append(self._local_ip)

        return addresses

    @property
    def _local_ip(self) -> Optional[str]:
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
        scrape_jobs = []
        worker_topologies = self.cluster.gather_topology()
        
        for worker in worker_topologies:
            job = {
                "static_configs": [
                    {
                        "targets": [f"{worker['address']}:{self._metrics_port}"],
                    }
                ],
                # setting these as "labels" in the static config gets some of them
                # replaced by the coordinator topology
                # https://github.com/canonical/prometheus-k8s-operator/issues/571
                "relabel_configs": [
                    # TODO: also pass the charm name in the worker relation data
                    {"target_label": "juju_charm", "replacement": worker["charm"]},
                    {"target_label": "juju_unit", "replacement": worker["unit"]},
                    {"target_label": "juju_application", "replacement": worker["app"]},
                    {"target_label": "juju_model", "replacement": self.model.name},
                    {"target_label": "juju_model_uuid", "replacement": self.model.uuid},
                ],
            }
            scrape_jobs.append(job)
        return scrape_jobs

    @property
    def _nginx_scrape_jobs(self) -> List[Dict[str, Any]]:
        job: Dict[str, Any] = {
            "static_configs": [{"targets": [f"{self.hostname}:{NGINX_PROMETHEUS_EXPORTER_PORT}"]}]
        }
        return [job]

    @property
    def _scrape_jobs(self) -> List[Dict[str, Any]]:
        return self._workers_scrape_jobs + self._nginx_scrape_jobs

    ##################
    # EVENT HANDLERS #
    ##################
    def _on_cert_handler_changed(self, _: ops.RelationChangedEvent):
        if self.tls_available:
            logger.debug("enabling TLS")
            self.nginx.configure_tls(
                server_cert=self.cert_handler.server_cert,
                ca_cert=self.cert_handler.ca_cert,
                private_key=self.cert_handler.private_key
            )
        else:
            logger.debug("disabling TLS")
            self.nginx.delete_certificates()

        # notify the cluster
        self.update_cluster()

    def _on_cluster_changed(self, _: ops.RelationEvent):
        self.update_cluster()

    def _on_nginx_pebble_ready(self, _: ops.PebbleReadyEvent):
        self.update_cluster()

    def _on_nginx_prometheus_exporter_pebble_ready(self, _: ops.PebbleReadyEvent):
        self.update_cluster()

    def _on_loki_relation_changed(self, _: ops.EventBase):
        self.update_cluster()

    def _on_s3_credentials_changed(self, _: ops.RelationChangedEvent):
        self._on_s3_changed()

    def _on_s3_credentials_gone(self, _: ops.RelationChangedEvent):
        self._on_s3_changed()

    def _on_s3_changed(self):
        self.update_cluster()

    def _on_peers_relation_created(self, event: ops.RelationCreatedEvent):
        if self._local_ip:
            event.relation.data[self._charm.unit]["local-ip"] = self._local_ip

    def _on_peers_relation_changed(self, _: ops.RelationChangedEvent):
        self.update_cluster()

    def _on_config_changed(self, _: ops.ConfigChangedEvent):
        # check if certificate files haven't disappeared and recreate them if needed
        self.update_cluster()

    # keep this event handler at the bottom
    def _on_collect_unit_status(self, e: ops.CollectStatusEvent):
        # todo add [nginx.workload] statuses

        # TODO: should we set these statuses on the leader only, or on all units?
        if not self.is_coherent:
            e.add_status(ops.BlockedStatus("[consistency] Cluster inconsistent."))
        else:
            if self.is_clustered:
                # no issues: tempo is consistent
                if self.is_recommended is False:
                    # if is_recommended is None: it means we don't have a recommended deployment criterion.
                    e.add_status(ops.ActiveStatus("[coordinator] Degraded."))
                else:
                    e.add_status(ops.ActiveStatus())
            else:
                e.add_status(ops.ActiveStatus())

    ###################
    # UTILITY METHODS #
    ###################
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
        if not self.is_coherent:
            logger.error("skipped cluster update: incoherent deployment")
            return

        self.nginx.configure_pebble_layer()
        # we share the certs in plaintext as they're not sensitive information
        # On every function call, we always publish everything to the databag; however, if there
        # are no changes, Juju will notice there's no delta and do nothing
        self.cluster.publish_data(
            worker_config=self._workers_config_getter(),
            loki_endpoints=self.loki_endpoints_by_unit,
            # TODO tempo receiver for charm tracing
            **({
              "ca_cert" : self.cert_handler.ca_cert,
              "server_cert" : self.cert_handler.server_cert,
              "privkey_secret_id" : self.cluster.publish_privkey(VAULT_SECRET_LABEL),
            } if self.tls_available else {}),
        )

    def _render_workers_alert_rules(self):
        self._remove_rendered_alert_rules()

        apps = set()
        for worker in self.cluster.gather_topology():
            if worker["app"] in apps:
                continue

            apps.add(worker["app"])
            topology_dict = {
                "model": self.model.name,
                "model_uuid": self.model.uuid,
                "application": worker["app"],
                "unit": worker["unit"],
                "charm_name": worker["charm"],
            }
            topology = JujuTopology.from_dict(topology_dict)
            alert_rules = AlertRules(query_type="promql", topology=topology)
            alert_rules.add_path(WORKER_ORIGINAL_ALERT_RULES_PATH, recursive=True)
            alert_rules_contents = yaml.dump(alert_rules.as_dict())

            file_name = f"{CONSOLIDATED_ALERT_RULES_PATH}/rendered_{worker['app']}.rules"
            with open(file_name, "w") as writer:
                writer.write(alert_rules_contents)

    def _remove_rendered_alert_rules(self):
        files = glob.glob(f"{CONSOLIDATED_ALERT_RULES_PATH}/rendered_*")
        for f in files:
            os.remove(f)

    def _consolidate_nginx_alert_rules(self):
        os.makedirs(CONSOLIDATED_ALERT_RULES_PATH, exist_ok=True)
        for filename in glob.glob(os.path.join(NGINX_ORIGINAL_ALERT_RULES_PATH, "*.*")):
            shutil.copy(filename, f"{CONSOLIDATED_ALERT_RULES_PATH}/")

    def _render_alert_rules(self):
        self._render_workers_alert_rules()
        self._consolidate_nginx_alert_rules()
