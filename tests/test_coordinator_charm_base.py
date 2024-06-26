import enum
import socket

from cosl.coordinator.coordinator_charm_base import Coordinator
from cosl.coordinator.roles import ConsistencyChecker
from ops import CharmBase


class ConsistencyC(ConsistencyChecker):
    #ABC.abstractmethod
    class Role(str, enum.Enum):
        write = "write"
        read = "read"
        foo = "foo"
        bar = "bar"
        baz = "baz"

    # ABC.abstractmethod
    meta_roles = {
        Role.write: [Role.foo, Role.bar],
        Role.read: [Role.baz],
    }
    # ABC.abstractmethod
    minimal_deployment = (Role.foo, Role.bar)

    # ABC.abstractmethod
    recommended_deployment = {
        Role.baz: 2,
        Role.bar: 1
    }

    # can override this to tell the coordinator how to compute what it means to be consistent
    def is_consistent(self) -> bool:
        pass

    # can override this to tell the coordinator how to compute what it means to be recommended
    def is_recommended(self) -> bool:
        pass


class NginxConfigGenerator(NginxConfigGeneratorBase):
    def generate(self, peers: List[str]):
        # use peers to determine the routes
        ...

class WorkerConfigGenerator(WorkerConfigGeneratorBase):
    def generate(self, peers: List[str]):
        # use peers to determine scaling factor and gossip rings
        ...


class LokiCoordinator(CharmBase):
    def __init__(self, *args, **kwargs):
        self.ingress = ...  # could be IPA or route

        self.coordinator = Coordinator(
            self,
            consistency_checker=ConsistencyC(),
            # nginx config
            nginx_config=NginxConfigGenerator(),
            # worker node config
            worker_config=WorkerConfigGenerator(),

            s3_bucket_name="BuckyMcBucket",
            grafana_datasource_type="mydstype",
            external_url=self.external_url
        )

        if not self.coordinator.is_coherent:
            return

        # todo: event handlers go here

    @property
    def external_url(self) -> str:
        return self.ingress.url or socket.getfqdn()
