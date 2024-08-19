from enum import Enum

import ops
from ops import Framework

from cosl.coordinated_workers.coordinator import Coordinator


class Role(str, Enum):
    all = "all"
    read = "read"
    write = "write"

    querier = "querier"
    interrogator = "interrogator"
    ingester = "ingester"
    compactor = "compactor"
    metrics_generator = "metrics-generator"


class MyRolesConfig:
    """Define the configuration for this coordinator's roles."""

    roles = set(Role)
    meta_roles = {
        "all": {
            Role.querier,
            Role.interrogator,
            Role.ingester,
            Role.compactor,
            Role.metrics_generator,
        },
        "read": {Role.querier, Role.interrogator},
        "write": {Role.ingester, Role.compactor},
    }

    minimal_deployment = {
        Role.querier: 1,
        Role.ingester: 1,
        Role.compactor: 1,
    }
    recommended_deployment = {
        Role.querier: 3,
        Role.ingester: 3,
        Role.compactor: 1,
        Role.metrics_generator: 1,
    }


class CoordinatorCharm(ops.CharmBase):
    def __init__(self, framework: Framework):
        super().__init__(framework)
        self.coordinator = Coordinator(
            self,
            roles_config=MyRolesConfig,
            s3_bucket_name="bucky",
            external_url="http://example.com",
            worker_metrics_port=3200,
            endpoints={
                "certificates": "certificates",
                "cluster": "cluster",
                "grafana-dashboards": "grafana-dashboard",
                "logging": "logging",
                "metrics": "metrics",
                "tracing": "tracing",
                "s3": "s3",
            },
            nginx_config=lambda _: "<nginx config file>",
            workers_config=lambda _: "<worker config>",
            tracing_receivers=lambda: {"otlp_http": "http://example.com/otlp_http"},
        )


if __name__ == "__main__":
    ops.main.main(CoordinatorCharm)
