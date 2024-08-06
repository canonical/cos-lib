import ops
import pytest
from typing import List
from src.cosl.coordinated_workers.interface import ClusterRequirerAppData, ClusterRequirerUnitData
from src.cosl.coordinated_workers.worker import Worker
from ops import Framework
from ops.pebble import Layer
from scenario import Container, Context, State, ExecOutput, Relation
from scenario.runtime import UncaughtCharmError


class MyCharm(ops.CharmBase):
    def __init__(self, framework: Framework):
        super().__init__(framework)
        self.worker = Worker(self, "foo", lambda _: Layer(""), {"cluster": "cluster"})


def test_no_roles_error():
    # Test that a charm that defines NO 'role-x' config options, when run,
    # raises a WorkerError

    # WHEN you define a charm with no role-x config options
    ctx = Context(
        MyCharm,
        meta={
            "name": "foo",
            "requires": {"cluster": {"interface": "cluster"}},
            "containers": {"foo": {"type": "oci-image"}},
        },
        config={},
    )

    # IF the charm executes any event
    # THEN the charm raises an error
    with pytest.raises(UncaughtCharmError):
        ctx.run("update-status", State(containers=[Container("foo")]))


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
        MyCharm,
        meta={
            "name": "foo",
            "requires": {"cluster": {"interface": "cluster"}},
            "containers": {"foo": {"type": "oci-image"}},
        },
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
            containers=[Container("foo")],
            config={
                **{f"role-{r}": False for r in roles_inactive},
                **{f"role-{r}": True for r in roles_active},
            },
        ),
    ) as mgr:
        # THEN the Worker.roles method correctly returns the list of only those that are set to true
        assert set(mgr.charm.worker.roles) == set(expected)


class MyWorker(ops.CharmBase):
    META = {
        "name": "foo-app",
        "requires": {"my-cluster": {"interface": "cluster"}},
        "containers": {"foo": {"type": "oci-image"}},
    }
    CONFIG = {
        "options": {
            f"role-{r}": {"type": "boolean", "default": "false"}
            for r in ("read", "write", "backend")
        }
    }
    def __init__(self, framework: Framework):
        super().__init__(framework)
        self.worker = Worker(
            self, "foo", lambda _: Layer(""), 
            {"cluster": "my-cluster"}
        )


@pytest.mark.parametrize(
    "output, expected_version", (
        ("tempo, version 1.0.0 (branch: HEAD, revision 32137ee...)" , "1.0.0"),
        ("mimir, version 2.1.45 (branch: HEAD, revision 32137ee...)" , "2.1.45"),
        ("tempo, version WEIRD (branch: HEAD, revision 32137ee...)" , "WEIRD"),
        ("gibberish" , None),
    )
)
def test_running_version(output: str, expected_version: str):
    # Test the worker's running_version method

    # WHEN you define a standard worker charm
    ctx = Context(
        MyWorker,
        meta=MyWorker.META,
        config=MyWorker.CONFIG
    )

    # AND the charm runs with a few of those set to true, the rest to false
    with ctx.manager(
        "update-status",
        State(
            containers=[Container("foo", can_connect=True,
                                  exec_mock={('/bin/foo', '-version'): 
                                             ExecOutput(
                                                 return_code=0, 
                                                 stdout=output)
                                             }
            )]
            )
    ) as mgr:
        # THEN the Worker.running_version returns what we expect
        charm: MyCharm = mgr.charm
        assert charm.worker.running_version() == expected_version


@pytest.mark.parametrize("leader", (True, False))
def test_pebble_layer_on_cluster_created(leader: bool):
    # verify that on cluster-created, the Worker initializes a pebble layer

    # WHEN you define a charm with a standard worker charm
    ctx = Context(
        MyWorker,
        meta=MyWorker.META,
        config=MyWorker.CONFIG
    )

    # AND the charm runs a cluster-created event
    cluster = Relation("my-cluster")
    foo_container = Container("foo", can_connect=True)
    
    state_out =  ctx.run(
        cluster.created_event,  # emit my-cluster-relation-created event
        State(
            leader=leader,
            config={"role-read": True},
            relations=[cluster],
            containers=[foo_container]
            )
    )

    # THEN the container has the expected layer
    assert state_out.get_container("foo").layers['foo'] == Layer("")
    



@pytest.mark.parametrize("leader", (True, False))
@pytest.mark.parametrize("roles", (["read"], ["read", "write"]))
def test_cluster_relation_data_on_cluster_created(leader: bool, roles: List[str]):
    # verify that on cluster-created, the Worker leader publishes relation data

    # WHEN you define a charm with a standard worker charm
    ctx = Context(
        MyWorker,
        meta=MyWorker.META,
        config=MyWorker.CONFIG
    )

    # AND the charm runs a cluster-created event
    cluster = Relation("my-cluster")
    foo_container = Container("foo", can_connect=True)
    
    state_out =  ctx.run(
        cluster.created_event,  # emit my-cluster-relation-created event
        State(
            leader=leader,
            config={f"role-{r}": True for r in roles},
            relations=[cluster],
            containers=[foo_container]
            )
    )
    
    cluster_out = state_out.get_relations("my-cluster")[0]
    
    if leader:
        # THEN the charm has published the right data to app data
        assert ClusterRequirerAppData.load(cluster_out.local_app_data).role == ",".join(roles)
    else:
        # THEN the charm didn't publish anything to app data
        assert not cluster_out.local_app_data

    # AND, either way, we put something in unit data
    assert ClusterRequirerUnitData.load(cluster_out.local_unit_data).juju_topology.application == "foo-app"


    
    
