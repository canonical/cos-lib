import enum
import socket

from cosl.coordinator.coordinator_charm_base import Coordinator
from ops import CharmBase


class MyClusterRolesConfig:
    class Role(str, enum.Enum):
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

    recommended_deployment = {
        Role.baz: 2,
        Role.bar: 1
    }


def generate_nginx_config(coordinator: Coordinator) -> str:
    # use peers to determine the routes
    ...


def generate_worker_config(coordinator: Coordinator) -> str:
    # use peers to determine scaling factor and gossip rings
    ...
    



class LokiCoordinator(CharmBase):
    def __init__(self, *args, **kwargs): # type:ignore
        super().__init__(*args, **kwargs) # type:ignore
        self.ingress = ...  # could be IPA or route

        self.coordinator = Coordinator(
            self,
            roles_config=MyClusterRolesConfig,
            # nginx config
            nginx_config=generate_nginx_config,
            # worker node config
            workers_config=generate_worker_config,

            s3_bucket_name="BuckyMcBucket",
            grafana_datasource_type="mydstype",
            external_url=self.external_url,
        )

        if not self.coordinator.is_coherent:
            return

        # todo: event handlers go here

    @property
    def external_url(self) -> str:
        return self.ingress.url or socket.getfqdn()
