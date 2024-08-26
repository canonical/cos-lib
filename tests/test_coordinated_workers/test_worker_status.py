from contextlib import contextmanager
from functools import partial
from unittest.mock import MagicMock, patch

import pytest
from ops import ActiveStatus, BlockedStatus, CharmBase, Framework, WaitingStatus
from ops.pebble import Layer
from scenario import Container, Context, Relation, State

from cosl.coordinated_workers.interface import ClusterProviderAppData
from cosl.coordinated_workers.worker import Worker, WorkerError


@pytest.fixture(params=[True, False])
def tls(request):
    return request.param


@contextmanager
def _urlopen_patch(url: str, resp: str, tls: bool):
    if url == f"{'https' if tls else 'http'}://localhost:3200/ready":
        mm = MagicMock()
        mm.read = MagicMock(return_value=resp.encode("utf-8"))
        yield mm
    else:
        raise RuntimeError("unknown path")


@pytest.fixture
def ctx(tls):
    class MyCharm(CharmBase):
        def __init__(self, framework: Framework):
            super().__init__(framework)
            with patch(
                "cosl.coordinated_workers.worker.KubernetesComputeResourcesPatch._namespace",
                "test-namespace",
            ):
                self.worker = Worker(
                    self,
                    "workload",
                    lambda _: Layer(
                        {
                            "summary": "summary",
                            "services": {"service": {"summary": "summary", "override": "replace"}},
                        }
                    ),
                    {"cluster": "cluster"},
                    readiness_check_endpoint=self._readiness_check_endpoint,
                    resources_requests={"cpu": "50m", "memory": "100Mi"},
                    container_name="charm",
                )

        def _readiness_check_endpoint(self, _):
            return f"{'https' if tls else 'http'}://localhost:3200/ready"

    return Context(
        MyCharm,
        meta={
            "name": "lilith",
            "requires": {"cluster": {"interface": "cluster"}},
            "containers": {"workload": {"type": "oci-image"}},
        },
        config={
            "options": {
                "role-all": {"type": "bool", "default": False},
                "role-read": {"type": "bool", "default": True},
                "role-write": {"type": "bool", "default": True},
            }
        },
    )


@pytest.fixture(params=[True, False])
def base_state(request):
    app_data = {}
    ClusterProviderAppData(worker_config="some: yaml").dump(app_data)
    return State(
        leader=request.param,
        containers=[Container("workload")],
        relations=[Relation("cluster", remote_app_data=app_data)],
    )


@contextmanager
def endpoint_starting(tls):
    with patch(
        "urllib.request.urlopen",
        new=partial(_urlopen_patch, tls=tls, resp="foo\nStarting: 10\n bar"),
    ):
        yield


@contextmanager
def endpoint_ready(tls):
    with patch("urllib.request.urlopen", new=partial(_urlopen_patch, tls=tls, resp="ready")):
        yield


@contextmanager
def config_on_disk():
    with patch(
        "cosl.coordinated_workers.worker.Worker._running_worker_config", new=lambda _: True
    ):
        yield


def test_status_check_no_pebble(ctx, base_state, caplog):
    # GIVEN the container cannot connect
    state = base_state.with_can_connect("workload", False)

    # WHEN we run any event
    state_out = ctx.run("update_status", state)

    # THEN the charm sets blocked
    assert state_out.unit_status == BlockedStatus("node down (see logs)")
    # AND THEN the charm logs that the container isn't ready.
    assert "Container cannot connect. Skipping status check." in caplog.messages


def test_status_check_no_config(ctx, base_state, caplog):
    # GIVEN there is no config file on disk
    state = base_state.with_can_connect("workload", True)

    # WHEN we run any event
    state_out = ctx.run("update_status", state)

    # THEN the charm sets blocked
    assert state_out.unit_status == BlockedStatus("node down (see logs)")
    # AND THEN the charm logs that the config isn't on disk
    assert "Config file not on disk. Skipping status check." in caplog.messages


# need to patch as Blocked state of get_status will override the Waiting state
@patch(
    "cosl.coordinated_workers.worker.KubernetesComputeResourcesPatch.get_status",
    MagicMock(return_value=WaitingStatus("waiting for limits")),
)
def test_status_check_starting(ctx, base_state, tls):
    # GIVEN getting the status returns "Starting: X"
    with endpoint_starting(tls):
        # AND GIVEN that the config is on disk
        with config_on_disk():
            # AND GIVEN that the container can connect
            state = base_state.with_can_connect("workload", True)
            # WHEN we run any event
            state_out = ctx.run("update_status", state)
    # THEN the charm sets waiting: Starting...
    assert state_out.unit_status == WaitingStatus("Starting...")


@patch(
    "cosl.coordinated_workers.worker.KubernetesComputeResourcesPatch.get_status",
    MagicMock(return_value=ActiveStatus("")),
)
def test_status_check_ready(ctx, base_state, tls):
    # GIVEN getting the status returns "ready"
    with endpoint_ready(tls):
        # AND GIVEN that the config is on disk
        with config_on_disk():
            # AND GIVEN that the container can connect
            state = base_state.with_can_connect("workload", True)
            # WHEN we run any event
            state_out = ctx.run("update_status", state)
    # THEN the charm sets waiting: Starting...
    assert state_out.unit_status == ActiveStatus("read,write ready.")


def test_status_no_endpoint(ctx, base_state, caplog):
    # GIVEN a charm doesn't pass an endpoint to Worker
    class MyCharm(CharmBase):
        def __init__(self, framework: Framework):
            super().__init__(framework)
            self.worker = Worker(
                self,
                "workload",
                lambda _: Layer(""),
                {"cluster": "cluster"},
            )

    ctx = Context(
        MyCharm,
        meta={
            "name": "damian",
            "requires": {"cluster": {"interface": "cluster"}},
            "containers": {"workload": {"type": "oci-image"}},
        },
        config={
            "options": {
                "role-all": {"type": "bool", "default": False},
                "role-read": {"type": "bool", "default": True},
                "role-write": {"type": "bool", "default": True},
            }
        },
    )
    # AND GIVEN that the container can connect
    state = base_state.with_can_connect("workload", True)
    # WHEN we run any event
    state_out = ctx.run("update_status", state)
    # THEN the charm sets Active: ready, even though we have no idea whether the endpoint is ready.
    assert state_out.unit_status == ActiveStatus("read,write ready.")
    # AND THEN the charm logs that we can't determine the readiness
    assert "Unable to determine worker readiness: no endpoint given." in caplog.messages


def test_access_status_no_endpoint_raises():
    # GIVEN the caller doesn't pass an endpoint to Worker
    caller = MagicMock()
    with patch("cosl.juju_topology.JujuTopology.from_charm"):
        worker = Worker(
            caller,
            "workload",
            lambda _: Layer(""),
            {"cluster": "cluster"},
        )

    # THEN calling .status raises
    with pytest.raises(WorkerError):
        worker.status  # noqa


@patch(
    "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher.apply",
    MagicMock(return_value=None),
)
def test_status_check_ready_with_patch(ctx, base_state):

    with endpoint_ready():
        with config_on_disk():
            with patch(
                "cosl.coordinated_workers.worker.KubernetesComputeResourcesPatch.get_status",
                MagicMock(return_value=WaitingStatus("waiting")),
            ):
                state = base_state.with_can_connect("workload", True)
                state_out = ctx.run("config_changed", state)
                assert state_out.unit_status == WaitingStatus("waiting")
                with patch(
                    "cosl.coordinated_workers.worker.KubernetesComputeResourcesPatch.get_status",
                    MagicMock(return_value=ActiveStatus("")),
                ):
                    state_out_out = ctx.run("update_status", state_out)
                    assert state_out_out.unit_status == ActiveStatus("read,write ready.")