import dataclasses
from unittest.mock import MagicMock, PropertyMock, patch

import httpx
import ops
import pytest
import tenacity
from lightkube import ApiError
from ops import testing

from cosl.coordinated_workers.coordinator import ClusterRolesConfig, Coordinator, VersionRange
from cosl.interfaces.cluster import ClusterProviderAppData, ClusterRequirerAppData
from tests.test_coordinated_workers.test_worker_status import k8s_patch

my_roles = ClusterRolesConfig(
    roles={"role"},
    meta_roles={},
    minimal_deployment={"role": 1},
    recommended_deployment={"role": 2},
)


class MyConfigBuilder:
    @property
    def version_range(self):
        return VersionRange(
            lower=(2, 7, 1),
            lower_inclusive=True,
            upper=(2, 8, 0),
            upper_inclusive=False,
        )

    def build(self, coordinator: Coordinator) -> str:
        return "worker config v2.7,1"


class MyCoordCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)

        self.coordinator = Coordinator(
            charm=self,
            roles_config=my_roles,
            external_url="localhost:3200",
            worker_metrics_port="8080",
            endpoints={
                "cluster": "cluster",
                "s3": "s3",
                "certificates": "certificates",
                "grafana-dashboards": "grafana-dashboard",
                "logging": "logging",
                "metrics": "metrics-endpoint",
                "charm-tracing": "self-charm-tracing",
                "workload-tracing": "self-workload-tracing",
                "send-datasource": None,
                "receive-datasource": "my-ds-exchange-require",
            },
            nginx_config=lambda _: "nginx config",
            workers_config=lambda _: "worker config",
            resources_requests=lambda _: {"cpu": "50m", "memory": "100Mi"},
            container_name="charm",
        )


class MyCoordCharmWithBuilders(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)

        self.coordinator = Coordinator(
            charm=self,
            roles_config=my_roles,
            external_url="localhost:3200",
            worker_metrics_port="8080",
            endpoints={
                "cluster": "cluster",
                "s3": "s3",
                "certificates": "certificates",
                "grafana-dashboards": "grafana-dashboard",
                "logging": "logging",
                "metrics": "metrics-endpoint",
                "charm-tracing": "self-charm-tracing",
                "workload-tracing": "self-workload-tracing",
                "send-datasource": None,
                "receive-datasource": "my-ds-exchange-require",
            },
            nginx_config=lambda _: "nginx config",
            workers_config=lambda _: "worker config",
            resources_requests=lambda _: {"cpu": "50m", "memory": "100Mi"},
            container_name="charm",
            config_builders=[MyConfigBuilder()],
        )


@pytest.fixture
def coord_charm():
    with k8s_patch():
        yield MyCoordCharm


@pytest.fixture
def coord_with_builder_charm():
    with k8s_patch():
        yield MyCoordCharmWithBuilders


@pytest.fixture
def meta():
    return {
        "name": "lilith",
        "requires": {
            "s3": {"interface": "s3"},
            "logging": {"interface": "loki_push_api"},
            "certificates": {"interface": "tls-certificates"},
            "self-charm-tracing": {"interface": "tracing", "limit": 1},
            "self-workload-tracing": {"interface": "tracing", "limit": 1},
            "my-ds-exchange-require": {"interface": "grafana_datasource_exchange"},
        },
        "provides": {
            "cluster": {"interface": "cluster"},
            "grafana-dashboard": {"interface": "grafana_dashboard"},
            "metrics-endpoint": {"interface": "prometheus_scrape"},
            "my-ds-exchange-provide": {"interface": "grafana_datasource_exchange"},
        },
        "containers": {
            "nginx": {"type": "oci-image"},
            "nginx-prometheus-exporter": {"type": "oci-image"},
        },
    }


@pytest.fixture
def ctx_with_builder(coord_with_builder_charm, meta):
    return testing.Context(coord_with_builder_charm, meta=meta)


@pytest.fixture
def ctx(coord_charm, meta):
    return testing.Context(coord_charm, meta=meta)


@pytest.fixture()
def s3():
    return testing.Relation(
        "s3",
        remote_app_data={
            "access-key": "key",
            "bucket": "tempo",
            "endpoint": "http://1.2.3.4:9000",
            "secret-key": "soverysecret",
        },
        local_unit_data={"bucket": "tempo"},
    )


@pytest.fixture()
def worker():
    app_data = {}
    ClusterProviderAppData(worker_config="some: yaml").dump(app_data)
    remote_app_data = {}
    ClusterRequirerAppData(role="role").dump(remote_app_data)
    return testing.Relation("cluster", local_app_data=app_data, remote_app_data=remote_app_data)


@pytest.fixture()
def base_state(s3, worker):
    return testing.State(
        leader=True,
        containers={testing.Container("nginx"), testing.Container("nginx-prometheus-exporter")},
        relations={worker, s3},
    )


def set_containers(state, nginx_can_connect=False, exporter_can_connect=False):
    containers = {
        testing.Container("nginx", can_connect=nginx_can_connect),
        testing.Container("nginx-prometheus-exporter", can_connect=exporter_can_connect),
    }
    return dataclasses.replace(state, containers=containers)


@patch(
    "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher.apply",
    MagicMock(return_value=None),
)
def test_status_check_no_workers(ctx, base_state, s3, caplog):
    # GIVEN the container cannot connect
    state = set_containers(base_state, True, False)
    state = dataclasses.replace(state, relations={s3})

    # WHEN we run any event
    state_out = ctx.run(ctx.on.config_changed(), state)

    # THEN the charm sets blocked
    assert state_out.unit_status == ops.BlockedStatus("[consistency] Missing any worker relation.")


@patch(
    "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher.apply",
    MagicMock(return_value=None),
)
def test_status_check_no_s3(ctx, base_state, worker, caplog):
    # GIVEN the container cannot connect
    state = set_containers(base_state, True, False)
    state = dataclasses.replace(base_state, relations={worker})

    # WHEN we run any event
    state_out = ctx.run(ctx.on.config_changed(), state)

    # THEN the charm sets blocked
    assert state_out.unit_status == ops.BlockedStatus("[s3] Missing S3 integration.")


@patch(
    "charms.observability_libs.v0.kubernetes_compute_resources_patch.KubernetesComputeResourcesPatch.get_status",
    MagicMock(return_value=(ops.BlockedStatus(""))),
)
def test_status_check_k8s_patch_failed(ctx, base_state, caplog):
    # GIVEN the container can connect
    state = set_containers(base_state, True, True)

    # WHEN we run any event
    state_out = ctx.run(ctx.on.update_status(), state)

    assert state_out.unit_status == ops.BlockedStatus("")


@patch("charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher")
@patch(
    "cosl.coordinated_workers.coordinator.KubernetesComputeResourcesPatch.PATCH_RETRY_STOP",
    PropertyMock(return_value=tenacity.wait_fixed(1)),
)
def test_status_check_k8s_patch_success_after_retries(
    resource_patcher_mock, ctx, base_state, caplog
):
    # GIVEN the container can connect
    state = set_containers(base_state, True, True)

    # Retry on that error
    response = httpx.Response(
        status_code=404, content='{"status": {"code": 404, "message": "Not Found"},"code":"404"}'
    )
    # Success on 2nd try
    resource_patcher_mock.return_value.apply.side_effect = [ApiError(response=response), None]

    # on collect-unit-status, the request patches are not yet reflected
    with patch(
        "cosl.coordinated_workers.coordinator.KubernetesComputeResourcesPatch.get_status",
        MagicMock(return_value=ops.WaitingStatus("waiting")),
    ):
        state_intermediate = ctx.run(ctx.on.config_changed(), state)
    assert state_intermediate.unit_status == ops.WaitingStatus("waiting")

    with patch(
        "cosl.coordinated_workers.coordinator.KubernetesComputeResourcesPatch.get_status",
        MagicMock(return_value=ops.ActiveStatus("")),
    ):
        state_out = ctx.run(ctx.on.update_status(), state_intermediate)
    assert state_out.unit_status == ops.ActiveStatus("Degraded.")


def worker_with_version(version: str):
    app_data = {}
    ClusterProviderAppData(worker_config="some: yaml").dump(app_data)
    remote_app_data = {}
    ClusterRequirerAppData(role="role", workload_version=version).dump(remote_app_data)
    return testing.Relation("cluster", local_app_data=app_data, remote_app_data=remote_app_data)


@patch(
    "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher.apply",
    MagicMock(return_value=None),
)
def test_status_check_workers_same_versions(ctx, base_state, s3, caplog):
    state = set_containers(base_state, True, True)

    # GIVEN workers that have the same workload version
    state = dataclasses.replace(
        state, relations={s3, worker_with_version("1.0"), worker_with_version("1.0")}
    )

    # WHEN we run any event
    state_out = ctx.run(ctx.on.config_changed(), state)

    # THEN the charm sets active
    assert state_out.unit_status == ops.ActiveStatus()


@patch(
    "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher.apply",
    MagicMock(return_value=None),
)
def test_status_check_workers_different_versions(ctx, base_state, s3, caplog):
    state = set_containers(base_state, True, True)

    # GIVEN workers that have different workload version
    state = dataclasses.replace(
        state, relations={s3, worker_with_version("1.0"), worker_with_version("2.0")}
    )

    # WHEN we run any event
    state_out = ctx.run(ctx.on.config_changed(), state)

    # THEN the charm sets blocked
    assert state_out.unit_status == ops.BlockedStatus(
        "[consistency] Workers are running different versions: 1.0, 2.0"
    )


@patch(
    "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher.apply",
    MagicMock(return_value=None),
)
def test_status_check_with_unsupported_version(ctx_with_builder, base_state, s3):
    state = set_containers(base_state, True, True)

    # GIVEN a worker with an unsupported workload version
    state = dataclasses.replace(state, relations={s3, worker_with_version("2.6")})

    # WHEN we run any event
    state_out = ctx_with_builder.run(ctx_with_builder.on.config_changed(), state)

    # THEN the charm sets blocked
    assert state_out.unit_status == ops.BlockedStatus(
        "Workers are requesting a config for a version: 2.6 that is not supported."
    )
