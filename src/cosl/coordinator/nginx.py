# Copyright 2023 Canonical
# See LICENSE file for licensing details.

"""Nginx workload."""

from typing import Callable
from ops import CharmBase, pebble

import logging

logger = logging.getLogger(__name__)


NGINX_DIR = "/etc/nginx"
NGINX_CONFIG = f"{NGINX_DIR}/nginx.conf"
NGINX_PORT = "8080"
KEY_PATH = f"{NGINX_DIR}/certs/server.key"
CERT_PATH = f"{NGINX_DIR}/certs/server.cert"
CA_CERT_PATH = f"{NGINX_DIR}/certs/ca.cert"


class Nginx:
    """Helper class to manage the nginx workload."""
    config_path = NGINX_CONFIG

    def __init__(self, charm: CharmBase, config_getter: Callable[[None], str]):
        self._charm = charm
        self._config_getter = config_getter
        self._container = self._charm.unit.get_container("nginx")

    def configure_tls(self, private_key:str, server_cert:str, ca_cert:str) -> None:
        if self._container.can_connect():
            self._container.push(KEY_PATH, private_key)
            self._container.push(CERT_PATH, server_cert)
            self._container.push(CA_CERT_PATH, ca_cert)
            self._container.exec(["update-ca-certificates", "--fresh"])

    def configure_pebble_layer(self) -> None:
        """Configure pebble layer."""
        if self._container.can_connect():
            self._container.push(
                self.config_path, self._config_getter(), make_dirs=True  # type: ignore
            )
            self._container.add_layer("nginx", self.layer, combine=True)
            self._container.autostart()

    @property
    def layer(self) -> pebble.Layer:
        """Return the Pebble layer for Nginx."""
        return pebble.Layer(
            {
                "summary": "nginx layer",
                "description": "pebble config layer for Nginx",
                "services": {
                    "nginx": {
                        "override": "replace",
                        "summary": "nginx",
                        "command": "nginx",
                        "startup": "enabled",
                    }
                },
            }
        )




NGINX_PROMETHEUS_EXPORTER_PORT = "9113"


class NginxPrometheusExporter:
    """Helper class to manage the nginx prometheus exporter workload."""

    def __init__(self, charm: CharmBase) -> None:
        self._charm = charm
        self._container = self._charm.unit.get_container("nginx-prometheus-exporter")

    def configure_pebble_layer(self) -> None:
        """Configure pebble layer."""
        self._container.add_layer("nginx-prometheus-exporter", self.layer, combine=True)
        self._container.autostart()

    @property
    def layer(self) -> pebble.Layer:
        """Return the Pebble layer for Nginx Prometheus exporter."""
        scheme = "https" if self._charm._is_cert_available else "http"  # type: ignore
        return pebble.Layer(
            {
                "summary": "nginx prometheus exporter layer",
                "description": "pebble config layer for Nginx Prometheus exporter",
                "services": {
                    "nginx": {
                        "override": "replace",
                        "summary": "nginx prometheus exporter",
                        "command": f"nginx-prometheus-exporter --no-nginx.ssl-verify --web.listen-address=:{NGINX_PROMETHEUS_EXPORTER_PORT}  --nginx.scrape-uri={scheme}://127.0.0.1:{NGINX_PORT}/status",
                        "startup": "enabled",
                    }
                },
            }
        )
