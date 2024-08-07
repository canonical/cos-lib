from pathlib import Path
import ops
import pytest
from typing import List
from src.cosl.coordinated_workers.interface import ClusterProviderAppData, ClusterRequirerAppData, ClusterRequirerUnitData
from src.cosl.coordinated_workers.worker import Worker, CERT_FILE, CONFIG_FILE, KEY_FILE, CLIENT_CA_FILE, ROOT_CA_CERT_LOCAL, ROOT_CA_CERT_CONTAINER
from ops import Framework
from ops.pebble import Layer
from scenario import Container, Context, Secret, State, ExecOutput, Relation
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


    
@pytest.fixture
def privkey_secret():
    return Secret(
        id="secret:123312313",
        contents={0: {"private-key": "verysecret"}}
    )


@pytest.fixture
def foo_container():
    return Container(
        "foo", 
        can_connect=True,
        exec_mock={('/bin/foo', '-version'): 
                    ExecOutput(
                        return_code=0, 
                        stdout="n/a")
                    },
        layers={
            "foo": Layer( 
                {
                    'summary': "some",
                    'description': "layer",
                    'services': {"foo": {"command": "whoami"}},
                }
            )
        }
    )



def test_config_created_on_pebble_ready(foo_container: Container):
    ctx = Context(
        MyWorker,
        meta=MyWorker.META,
        config=MyWorker.CONFIG
    )
    cluster = Relation("my-cluster",
                       remote_app_data=ClusterProviderAppData(
                           worker_config="some: yaml"
                       ).dump())
    # WHEN we receive any of:
    # - pebble_ready
    # - worker_config_received
    # - cluster_created
    # - cluster_changed
    with ctx.manager(
        cluster.created_event,
        State(
            leader=True,
            config={f"role-{r}": True for r in {"read", "write"}},
            relations=[cluster],
            containers=[foo_container]
            )
    ) as mgr:
        charm: MyCharm = mgr.charm
        # we verify the cluster's get_tls_data sees it
        worker_config = charm.worker.cluster.get_worker_config()
        assert worker_config

    # THEN the charm pushes the workload config to the workload container
    fs = str(foo_container.get_filesystem(ctx))
    
    config_file_path_relative_to_fs = Path(fs + str(CONFIG_FILE))
    assert config_file_path_relative_to_fs.exists()
    assert config_file_path_relative_to_fs.read_text().strip() == "some: yaml"


@pytest.mark.parametrize("event_type", (
        "cluster-changed", "cluster-created", "pebble-ready", "upgrade-charm"
))
def test_update_tls_certificates_workload_container(privkey_secret: Secret, foo_container: Container, root_ca_cert:Path, event_type: str):
    # GIVEN the cluster has published TLS data
    ctx = Context(
        MyWorker,
        meta=MyWorker.META,
        config=MyWorker.CONFIG
    )

    cluster = Relation(
        "my-cluster",
        remote_app_data=ClusterProviderAppData(
            worker_config="some: yaml",
            ca_cert="cacert",
            server_cert="servercert",
            privkey_secret_id=privkey_secret.id,
        ).dump()
        )
    
    # WHEN we receive any of:
    # - pebble_ready
    # - _worker_config_received
    # - upgrade_charm
    # - cluster_created
    # - cluster_changed
    event = {
        "cluster-changed": cluster.changed_event,
        "cluster-created": cluster.created_event,
        "pebble-ready": foo_container.pebble_ready_event,
        "upgrade-charm": "upgrade-charm"
    }[event_type]
    with ctx.manager(
        event=event,
        state=State(
            leader=True,
            config={f"role-{r}": True for r in {"read", "write"}},
            relations=[cluster],
            containers=[foo_container],
            secrets=[privkey_secret]
            )
    ) as mgr:
        charm: MyCharm = mgr.charm
        # we verify the cluster's get_tls_data sees it
        tls_data = charm.worker.cluster.get_tls_data()
        assert tls_data

    # THEN the charm pushes TLS configs to the workload container 
    fs = str(foo_container.get_filesystem(ctx))

    for file, expected_content in zip(
        (CERT_FILE,
        KEY_FILE,
        CLIENT_CA_FILE,
        ROOT_CA_CERT_CONTAINER), (
            "servercert", "verysecret", "cacert", "cacert"
        ) ):
        path_relative_to_fs = Path(fs + str(file))
        assert path_relative_to_fs.exists(), file
        assert path_relative_to_fs.read_text() == expected_content


@pytest.mark.parametrize("event_type", (
        "cluster-changed", "cluster-created", "pebble-ready", "upgrade-charm"
))
def test_update_tls_certificates_local_fs(privkey_secret: Secret, foo_container: Container, root_ca_cert:Path, event_type: str):
    # GIVEN the cluster has published TLS data
    ctx = Context(
        MyWorker,
        meta=MyWorker.META,
        config=MyWorker.CONFIG
    )

    cluster = Relation(
        "my-cluster",
        remote_app_data=ClusterProviderAppData(
            worker_config="some: yaml",
            ca_cert="cacert",
            server_cert="servercert",
            privkey_secret_id=privkey_secret.id,
        ).dump()
    )

    # WHEN we receive any of:
    # - pebble_ready
    # - _worker_config_received
    # - upgrade_charm
    # - cluster_created
    # - cluster_changed
    event = {
        "cluster-changed": cluster.changed_event,
        "cluster-created": cluster.created_event,
        "pebble-ready": foo_container.pebble_ready_event,
        "upgrade-charm": "upgrade-charm"
    }[event_type]
    with ctx.manager(
            event=event,
            state=State(
                leader=True,
                config={f"role-{r}": True for r in {"read", "write"}},
                relations=[cluster],
                containers=[foo_container],
                secrets=[privkey_secret]
            )
    ) as mgr:
        charm: MyCharm = mgr.charm
        # we verify the cluster's get_tls_data sees it
        tls_data = charm.worker.cluster.get_tls_data()
        assert tls_data

    # THEN the charm pushes TLS configs to the local filesystem
    assert root_ca_cert.exists()
    assert root_ca_cert.read_text() == "cacert"