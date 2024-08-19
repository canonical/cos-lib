from unittest.mock import patch

import pytest
from catan import App, Catan
from ops import ActiveStatus, BlockedStatus, WaitingStatus

from tests.charms.coordinator.src.charm import CoordinatorCharm
from tests.charms.worker.src.charm import WorkerCharm


@pytest.fixture(autouse=True)
def patch_running_version():
    with patch("cosl.coordinated_workers.worker.Worker.running_version", new=lambda _: "42.42"):
        yield


@pytest.fixture
def worker():
    return App.from_type(WorkerCharm)


@pytest.fixture
def coordinator():
    return App.from_type(CoordinatorCharm)


def test_deploy_worker(worker):
    # GIVEN an initially empty model
    c = Catan()

    # WHEN we deploy a worker
    c.deploy(worker, [0])
    c.settle()

    # THEN the worker gets to blocked state because we're missing a coordinator relation
    worker_state = c.get_unit_state(worker, 0)
    assert worker_state.unit_status == BlockedStatus("Missing relation to a coordinator charm")


def test_deploy_coordinator(coordinator):
    # GIVEN an initially empty model
    c = Catan()

    # WHEN we deploy a coordinator
    c.deploy(coordinator, [0])
    c.settle()

    # THEN the coordinator gets to blocked state because we're missing a relation to a worker
    worker_state = c.get_unit_state(coordinator, 0)
    assert worker_state.unit_status == BlockedStatus("[consistency] Missing any worker relation.")


def test_minimal_deployment_no_s3(worker, coordinator):
    # GIVEN an initially empty model
    c = Catan()

    # WHEN we deploy a worker and a coordinator, but no s3
    c.deploy(worker, [0], emit_pebble_ready=True)

    c.deploy(coordinator, [0])
    # and we relate them
    c.integrate(worker, "cluster", coordinator, "cluster")
    c.settle()

    # THEN the deployment goes to active
    worker_state = c.get_unit_state(worker, 0)
    assert worker_state.unit_status == WaitingStatus("Waiting for coordinator to publish a config")
    coordinator_state = c.get_unit_state(coordinator, 0)
    assert coordinator_state.unit_status == BlockedStatus("[consistency] Missing S3 integration.")


def test_minimal_deployment_s3(worker, coordinator):
    # GIVEN an initially empty model
    c = Catan()

    # WHEN we deploy a worker and a coordinator, and mock s3
    c.deploy(worker, [0], emit_pebble_ready=True)

    c.deploy(coordinator, [0], emit_pebble_ready=True)
    # and we relate them
    c.integrate(worker, "cluster", coordinator, "cluster")
    with patch(
        "cosl.coordinated_workers.coordinator.Coordinator._s3_config",
        new={
            "bucket": "bucket",
            "endpoint": "endpoint",
            "access-key": "access-key",
            "secret-key": "secret-key",
        },
    ):
        c.settle()

    # THEN the deployment goes to active
    worker_state = c.get_unit_state(worker, 0)
    assert worker_state.unit_status == ActiveStatus("(all roles) ready.")
    coordinator_state = c.get_unit_state(coordinator, 0)
    assert coordinator_state.unit_status == ActiveStatus("[coordinator] Degraded.")


def test_recommended_deployment_s3(worker, coordinator):
    # GIVEN an initially empty model
    c = Catan()

    # WHEN we deploy a worker and a coordinator, and mock s3
    c.deploy(worker, [0, 1, 2, 3], emit_pebble_ready=True)

    c.deploy(coordinator, [0], emit_pebble_ready=True)
    # and we relate them
    c.integrate(worker, "cluster", coordinator, "cluster")
    with patch(
        "cosl.coordinated_workers.coordinator.Coordinator._s3_config",
        new={
            "bucket": "bucket",
            "endpoint": "endpoint",
            "access-key": "access-key",
            "secret-key": "secret-key",
        },
    ):
        c.settle()

    # THEN the deployment goes to active
    worker_state = c.get_unit_state(worker, 0)
    assert worker_state.unit_status == ActiveStatus("(all roles) ready.")
    coordinator_state = c.get_unit_state(coordinator, 0)
    assert coordinator_state.unit_status == ActiveStatus("")


def test_cluster_inconsistent(worker, coordinator):
    # GIVEN an initially empty model
    c = Catan()

    # WHEN we deploy a worker and a coordinator
    c.deploy(worker, [0], emit_pebble_ready=True)
    c.configure(worker, **{"role-all": False, "role-querier": True})

    c.deploy(coordinator, [0])
    # and we relate them
    c.integrate(worker, "cluster", coordinator, "cluster")
    c.settle()

    # THEN the deployment goes to active
    worker_state = c.get_unit_state(worker, 0)
    assert worker_state.unit_status == WaitingStatus("Waiting for coordinator to publish a config")
    coordinator_state = c.get_unit_state(coordinator, 0)
    assert coordinator_state.unit_status == BlockedStatus("[consistency] Cluster inconsistent.")
