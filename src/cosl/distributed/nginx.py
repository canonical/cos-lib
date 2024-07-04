# Copyright 2023 Canonical
# See LICENSE file for licensing details.

"""Nginx workload."""

import logging
from typing import Callable

from ops import CharmBase, pebble

logger = logging.getLogger(__name__)


NGINX_DIR = "/etc/nginx"
NGINX_CONFIG = f"{NGINX_DIR}/nginx.conf"
NGINX_PORT = "8080"
KEY_PATH = f"{NGINX_DIR}/certs/server.key"
CERT_PATH = f"{NGINX_DIR}/certs/server.cert"
CA_CERT_PATH = f"{NGINX_DIR}/certs/ca.cert" # TODO: this should probably be in /etc/certs , right ???


class Nginx:
    """Helper class to manage the nginx workload."""
    config_path = NGINX_CONFIG
    _name = "nginx"

    def __init__(self, charm: CharmBase, config_getter: Callable[[], str]):
        self._charm = charm
        self._config_getter = config_getter
        self._container = self._charm.unit.get_container("nginx")

    @property
    def are_certificates_on_disk(self) -> bool:
        return (
            self._container.can_connect()
            and self._container.exists(CERT_PATH)
            and self._container.exists(KEY_PATH)
            and self._container.exists(CA_CERT_PATH)
        )

    def configure_tls(self, private_key:str, server_cert:str, ca_cert:str) -> None:
        if self._container.can_connect():
            self._container.push(KEY_PATH, private_key)
            self._container.push(CERT_PATH, server_cert)
            self._container.push(CA_CERT_PATH, ca_cert)
            self._container.exec(["update-ca-certificates", "--fresh"])

    def delete_certificates(self) -> None:
        if self._container.can_connect():
            self._container.remove_path(CERT_PATH, recursive=True)
            self._container.remove_path(KEY_PATH, recursive=True)
            self._container.remove_path(CA_CERT_PATH, recursive=True)
            self._container.exec(["update-ca-certificates" "--fresh"])

    def _has_config_changed(self, new_config: str) -> bool:
        """Return True if the passed config differs from the one on disk."""
        if not self._container.can_connect():
            logger.debug("Could not connect to Nginx container")
            return False

        try:
            current_config = self._container.pull(self.config_path).read()
        except (pebble.ProtocolError, pebble.PathError) as e:
            logger.warning(
                "Could not check the current nginx configuration due to "
                "a failure in retrieving the file: %s",
                e,
            )
            return False

        return current_config != new_config

    def restart(self) -> None:
        """Restart the pebble service or start if not already running."""
        # TODO: change this to reload the config without restarting
        self._container.exec(["nginx", "-s", "reload"])
        # if not self._container.exists(self.config_path):
        #     logger.error("cannot restart nginx: config file doesn't exist (yet).")

        # try:
        #     if self._container.get_service(self._name).is_running():
        #         self._container.restart(self._name)
        #     else:
        #         self._container.start(self._name)
        # except pebble.ChangeError as e:
        #     logger.error(f"failed to (re)start nginx job: {e}", exc_info=True)
        #     return

    def configure_pebble_layer(self) -> None:
        """Configure pebble layer."""
        if self._container.can_connect():
            new_config: str = self._config_getter()
            should_restart: bool = self._has_config_changed(new_config)
            self._container.push(
                self.config_path, new_config, make_dirs=True  # type: ignore
            )
            self._container.add_layer("nginx", self.layer, combine=True)
            self._container.autostart()

            if should_restart:
                logger.info("new nginx config: restarting the service")
                self.restart()

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
                        "command": "nginx -g 'daemon off;'",
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
