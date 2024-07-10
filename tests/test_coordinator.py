import enum
import socket

from cosl.distributed.coordinator import Coordinator
from ops import CharmBase


class MyClusterRolesConfig:
    class Role(str, enum.Enum):
        """Define the roles for the cluster."""

        write = "write"
        read = "read"
        foo = "foo"
        bar = "bar"
        baz = "baz"

    meta_roles = {
        Role.write: [Role.foo, Role.bar],
        Role.read: [Role.baz],
    }

    minimal_deployment = (Role.foo, Role.bar)

    recommended_deployment = {Role.baz: 2, Role.bar: 1}


def generate_nginx_config(coordinator: Coordinator) -> str:
    # use peers to determine the routes
    ...


def generate_worker_config(coordinator: Coordinator) -> str:
    # use peers to determine scaling factor and gossip rings
    ...


class LokiCoordinator(CharmBase):
    def __init__(self, *args, **kwargs):  # type:ignore
        super().__init__(*args, **kwargs)  # type:ignore
        self.ingress = ...  # could be IPA or route

        self.coordinator = Coordinator(
            self,
            roles_config=MyClusterRolesConfig,
            metrics_port="8080",
            # nginx config
            nginx_config=generate_nginx_config,
            # worker node config
            workers_config=generate_worker_config,
            s3_bucket_name="BuckyMcBucket",
            external_url=self.external_url,
        )

        if not self.coordinator.is_coherent:
            return

        # todo: event handlers go here

    @property
    def external_url(self) -> str:
        return self.ingress.url or socket.getfqdn()
