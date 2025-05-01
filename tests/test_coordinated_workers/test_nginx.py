import logging
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import List, Tuple
from unittest.mock import patch

import ops
import pytest
from ops import testing

from src.cosl.coordinated_workers.nginx import (
    CA_CERT_PATH,
    CERT_PATH,
    KEY_PATH,
    NGINX_CONFIG,
    Nginx,
    NginxConfig,
    NginxLocationConfig,
    NginxLocationModifier,
)

sample_dns_ip = "198.18.0.0"

logger = logging.getLogger(__name__)


@pytest.fixture
def certificate_mounts():
    temp_files = {}
    for path in {KEY_PATH, CERT_PATH, CA_CERT_PATH}:
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_files[path] = temp_file

    mounts = {}
    for cert_path, temp_file in temp_files.items():
        mounts[cert_path] = testing.Mount(location=cert_path, source=temp_file.name)

    # TODO: Do we need to clean up the temp files since delete=False was set?
    return mounts


@pytest.fixture
def nginx_context():
    return testing.Context(
        ops.CharmBase, meta={"name": "foo", "containers": {"nginx": {"type": "oci-image"}}}
    )


def test_certs_on_disk(certificate_mounts: dict, nginx_context: testing.Context):
    # GIVEN any charm with a container
    ctx = nginx_context

    # WHEN we process any event
    with ctx(
        ctx.on.update_status(),
        state=testing.State(
            containers={testing.Container("nginx", can_connect=True, mounts=certificate_mounts)}
        ),
    ) as mgr:
        charm = mgr.charm
        nginx = Nginx(charm, lambda: "foo_string", None)

        # THEN the certs exist on disk
        assert nginx.are_certificates_on_disk


def test_certs_deleted(certificate_mounts: dict, nginx_context: testing.Context):
    # Test deleting the certificates.

    # GIVEN any charm with a container
    ctx = nginx_context

    # WHEN we process any event
    with ctx(
        ctx.on.update_status(),
        state=testing.State(
            containers={testing.Container("nginx", can_connect=True, mounts=certificate_mounts)}
        ),
    ) as mgr:
        charm = mgr.charm
        nginx = Nginx(charm, lambda: "foo_string", None)

        # AND when we call delete_certificates
        nginx.delete_certificates()

        # THEN the certs get deleted from disk
        assert not nginx.are_certificates_on_disk


def test_reload_calls_nginx_binary_successfully(nginx_context: testing.Context):
    # Test that the reload method calls the nginx binary without error.

    # GIVEN any charm with a container
    ctx = nginx_context

    # WHEN we process any event
    with ctx(
        ctx.on.update_status(),
        state=testing.State(
            containers={
                testing.Container(
                    "nginx",
                    can_connect=True,
                    execs={testing.Exec(("nginx", "-s", "reload"), return_code=0)},
                )
            },
        ),
    ) as mgr:
        charm = mgr.charm
        nginx = Nginx(charm, lambda: "foo_string", None)

        # AND when we call reload
        # THEN the nginx binary is used rather than container restart
        assert nginx.reload() is None


def test_has_config_changed(nginx_context: testing.Context):
    # Test changing the nginx config and catching the change.

    # GIVEN any charm with a container and a nginx config file
    test_config = tempfile.NamedTemporaryFile(delete=False, mode="w+")
    ctx = nginx_context
    # AND when we write to the config file
    with open(test_config.name, "w") as f:
        f.write("foo")

    # WHEN we process any event
    with ctx(
        ctx.on.update_status(),
        state=testing.State(
            containers={
                testing.Container(
                    "nginx",
                    can_connect=True,
                    mounts={
                        "config": testing.Mount(location=NGINX_CONFIG, source=test_config.name)
                    },
                )
            },
        ),
    ) as mgr:
        charm = mgr.charm
        nginx = Nginx(charm, lambda: "foo_string", None)

        # AND a unique config is added
        new_config = "bar"

        # THEN the _has_config_changed method correctly determines that foo != bar
        assert nginx._has_config_changed(new_config)


@contextmanager
def mock_resolv_conf(contents: str):
    with tempfile.NamedTemporaryFile() as tf:
        Path(tf.name).write_text(contents)
        with patch("src.cosl.coordinated_workers.nginx.RESOLV_CONF_PATH", tf.name):
            yield


@pytest.mark.parametrize(
    "mock_contents, expected_dns_ip",
    (
        (f"foo bar\nnameserver {sample_dns_ip}", sample_dns_ip),
        (f"nameserver {sample_dns_ip}\n foo bar baz", sample_dns_ip),
        (
            f"foo bar\nfoo bar\nnameserver {sample_dns_ip}\nnameserver 198.18.0.1",
            sample_dns_ip,
        ),
    ),
)
def test_dns_ip_addr_getter(mock_contents, expected_dns_ip):
    with mock_resolv_conf(mock_contents):
        assert NginxConfig._get_dns_ip_address() == expected_dns_ip


def test_dns_ip_addr_fail():
    with pytest.raises(RuntimeError):
        with mock_resolv_conf("foo bar"):
            NginxConfig._get_dns_ip_address()


@pytest.mark.parametrize("tls", (False, True))
def test_generate_nginx_config(tls):
    roles_to_upstreams = {
        "read": {
            "read": 3200,
        },
        "write": {
            "write": 3201,
        },
        "ingester": {
            "invalid-upstream": 9096,
        },
        "distributor": {
            "otlp-http": 9095,
        },
    }

    server_ports_to_locations = {
        3200: [
            NginxLocationConfig(upstream="read"),
            NginxLocationConfig(
                upstream="write", path="/write", modifier=NginxLocationModifier.REGEX
            ),
        ],
        3201: [
            NginxLocationConfig(
                upstream="write", path="/write", modifier=NginxLocationModifier.EXACT, is_grpc=True
            ),
        ],
        9095: [NginxLocationConfig(upstream="otlp-http")],
        9096: [NginxLocationConfig(upstream="invalid-upstream")],
    }

    addrs_by_role = {
        "read": {"1.2.3.4"},
        "write": {"5.6.7.8"},
        "distributor": {"9.10.11.12", "13.14.15.16"},
    }

    nginx = NginxConfig(
        "localhost",
        roles_to_upstreams=roles_to_upstreams,
        server_ports_to_locations=server_ports_to_locations,
    )
    generated_config = nginx.get_config(addrs_by_role, tls)

    _assert_upstreams(
        generated_config,
        valid_upstreams=["read", "write", "otlp-http"],
        invalid_upstreams=["invalid-upstream"],
    )
    _assert_listeners(
        generated_config,
        tls,
        valid_listeners=(("3200", "http"), ("3201", "grpc"), ("9095", "http")),
        invalid_listeners=(("9096", "http"),),
    )
    _assert_locations(
        generated_config,
        tls,
        valid_upstreams=(
            ("read", "http"),
            ("write", "http"),
            ("write", "grpc"),
            ("otlp-http", "http"),
        ),
        invalid_upstreams=(("invalid-upstream", "http"),),
    )


def _assert_upstreams(config: str, valid_upstreams: List[str], invalid_upstreams: List[str]):
    for upstream in valid_upstreams:
        assert f"upstream {upstream}" in config
    for upstream in invalid_upstreams:
        assert f"upstream {upstream}" not in config


def _assert_listeners(
    config: str, tls: bool, valid_listeners: Tuple[str, str], invalid_listeners: Tuple[str, str]
):
    for port, protocol in valid_listeners:
        config_protocol = ""
        if tls:
            config_protocol += " ssl"
        if protocol == "grpc":
            config_protocol += " http2"
        assert f"listen {port}{config_protocol};" in config

    for port, protocol in invalid_listeners:
        assert f"listen {port}" not in config


def _assert_locations(
    config: str, tls: bool, valid_upstreams: Tuple[str, str], invalid_upstreams: Tuple[str, str]
):
    s = "s" if tls else ""
    for upstream, protocol in valid_upstreams:
        config_protocol = f"grpc{s}" if protocol == "grpc" else f"http{s}"
        assert f"set $backend {config_protocol}://{upstream}" in config
    for upstream, protocol in invalid_upstreams:
        config_protocol = f"grpc{s}" if protocol == "grpc" else f"http{s}"
        assert f"set $backend {config_protocol}://{upstream}" not in config
