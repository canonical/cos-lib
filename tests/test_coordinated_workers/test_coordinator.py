import logging
import ops
import pytest

from types import SimpleNamespace
from ops import Framework
from scenario import Container, Context, Relation, State
from scenario.runtime import UncaughtCharmError

from src.cosl.coordinated_workers.coordinator import (
    ClusterRolesConfig,
    Coordinator,
    S3NotFoundError,
)

logger = logging.getLogger(__name__)

# TODO Make a fixture that generates a valid Coordinator instantiation
# TODO Make a fixture that generates a valid S3 Relation
# TODO I can also patch _s3_config to return a random dict to test parts working


@pytest.fixture
def roles_config():
    # Used loki-coordinator-k8s-operator as reference
    return SimpleNamespace(
        roles={"all", "read", "write", "backend"},
        meta_roles={"all": {"all", "read", "write", "backend"}},
        minimal_deployment={
            "read",
            "write",
            "backend",
        },
        recommended_deployment={
            "read": 3,
            "write": 3,
            "backend": 3,
        },
    )


@pytest.fixture
def coordinator_state():
    requires_relations = {
        "my-certificates": {"interface": "certificates"},
        "my-cluster": {"interface": "cluster"},
        "my-logging": {"interface": "loki_push_api"},
        "my-tracing": {"interface": "tracing"},
        "my-s3": {"interface": "s3"},
    }

    provides_relations = {
        "my-dashboards": {"interface": "grafana_dashboard"},
        "my-metrics": {"interface": "prometheus_scrape"},
    }

    requires_relations = {
        endpoint: Relation(endpoint=endpoint, interface=interface["interface"])
        for endpoint, interface in requires_relations.items()
    }
    provides_relations = {
        endpoint: Relation(endpoint=endpoint, interface=interface["interface"])
        for endpoint, interface in provides_relations.items()
    }

    return State(
        containers=[Container("nginx"), Container("nginx-prometheus-exporter")],
        relations=list(requires_relations.values()),
    )


@pytest.fixture
def coordinator(charm: ops.CharmBase):
    return Coordinator(
        charm=charm,
        roles_config=roles_config(),
        s3_bucket_name="foo-s3",
        external_url="https://foo.example.com",
        worker_metrics_port=123,
        endpoints={
            "certificates": "my-certificates",
            "cluster": "my-cluster",
            "grafana-dashboards": "my-dashboards",
            "logging": "my-logging",
            "metrics": "my-metrics",
            "tracing": "my-tracing",
            "s3": "my-s3",
        },
        nginx_config=lambda coordinator: f"nginx configuration for {coordinator.name}",
        workers_config=lambda coordinator: f"workers configuration for {coordinator.name}",
        # nginx_options: Optional[NginxMappingOverrides] = None,
        # is_coherent: Optional[Callable[[ClusterProvider, ClusterRolesConfig], bool]] = None,
        # is_recommended: Optional[Callable[[ClusterProvider, ClusterRolesConfig], bool]] = None,
        # tracing_receivers: Optional[Callable[[], Optional[Dict[str, str]]]] = None,
    )


class MyCoordinator(ops.CharmBase):
    META = {
        "name": "foo-app",
        "requires": {
            "my-certificates": {"interface": "certificates"},
            "my-cluster": {"interface": "cluster"},
            "my-logging": {"interface": "loki_push_api"},
            "my-tracing": {"interface": "tracing"},
            "my-s3": {"interface": "s3"},
        },
        "containers": {
            "nginx": {"type": "oci-image"},
            "nginx-prometheus-exporter": {"type": "oci-image"},
        },
    }
    CONFIG = {"options": {f"role-{r}": {"type": "boolean", "default": "false"} for r in ("all")}}

    def __init__(self, framework: Framework):
        super().__init__(framework)
        # Note: Here it is a good idea not to use context mgr because it is "ops aware"
        self.coordinator = coordinator(self)


def test_s3_not_found_error(coordinator_state: State):
    # Test a charm without an s3 integration raises S3NotFoundError

    # GIVEN a cluster without an s3 integration
    ctx = Context(MyCoordinator, meta=MyCoordinator.META, config=MyCoordinator.CONFIG)

    # logger.warning(f"STATE: {state.relations}")
    # WHEN you
    with ctx.manager("start", coordinator_state) as mgr:
        logger.warning(
            f"S3 CONNECTION INFO: {mgr.charm.coordinator.s3_requirer.get_s3_connection_info()}"
        )
        # THEN the Coordinator has an inactive S3 integration
        with pytest.raises(S3NotFoundError):
            mgr.charm.coordinator._s3_config


@pytest.mark.parametrize(
    "roles_active, roles_inactive, expected",
    (
        (
            ["read", "write", "ingester", "all"],
            ["alertmanager"],
            ["read", "write", "ingester", "all"],
        ),
        (["read", "write"], ["alertmanager"], ["read", "write"]),
        (["read"], ["alertmanager", "write", "ingester", "all"], ["read"]),
        ([], ["read", "write", "ingester", "all", "alertmanager"], []),
    ),
)
def test_roles_from_config(roles_active, roles_inactive, expected):
    # Test that a charm that defines any 'role-x' config options, when run,
    # correctly determines which ones are enabled through the Worker

    # WHEN you define a charm with a few role-x config options
    ctx = Context(
        MyCoordinator,
        meta={"name": "foo-app"},
        config={
            "options": {
                f"role-{r}": {"type": "boolean", "default": "false"}
                for r in (roles_active + roles_inactive)
            }
        },
    )

    # AND the charm runs with a few of those set to true, the rest to false
    with ctx.manager(
        "update-status",
        State(
            containers=[Container("nginx")],
            config={
                **{f"role-{r}": False for r in roles_inactive},
                **{f"role-{r}": True for r in roles_active},
            },
        ),
    ) as mgr:
        with pytest.raises(S3NotFoundError):
            # THEN the Worker.roles method correctly returns the list of only those that are set to true
            assert set(mgr.charm.worker.roles) == set(expected)


@pytest.mark.parametrize("leader", (True, False))
def test_pebble_layer_on_cluster_created(leader: bool):
    # verify that on cluster-created, the Worker initializes a pebble layer

    # WHEN you define a charm with a standard coordinator charm
    ctx = Context(MyCoordinator, meta=MyCoordinator.META, config=MyCoordinator.CONFIG)

    # AND the charm runs a cluster-created event
    relations = {name: Relation(name) for name in MyCoordinator.META["requires"]}
    # logger.warning(f"CLUSTERS: {relations}")
    foo_container = Container("nginx", can_connect=True)
    # logger.warning(f"CONTAINER: {foo_container}")
    logger.warning(f'EVENTS: {relations["my-cluster"].__dict__}')

    state_out = ctx.run(
        relations["my-cluster"].created_event,  # emit my-cluster-relation-created event
        State(
            leader=leader,
            config={"role-read": True},
            relations=list(relations.values()),
            containers=[foo_container],
        ),
    )

    # THEN the container has the expected layer
    logger.warning(f"STATE OUT: {state_out.containers[0]}")
    # assert state_out.get_container("foo").layers["foo"] == Layer("")
