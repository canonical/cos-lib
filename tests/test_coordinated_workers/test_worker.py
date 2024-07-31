from unittest.mock import patch

import ops
import pytest

from cosl.coordinated_workers.worker import Worker

from ops import Framework
from ops.pebble import Layer
from scenario import Container, Context, State


class MyCharm(ops.CharmBase):
    def __init__(self, framework: Framework):
        super().__init__(framework)
        self.worker = Worker(self, "foo", lambda _: Layer(""), {"cluster": "cluster"})


def test_no_roles_error():
    ctx = Context(
        MyCharm,
        meta={
            "name": "foo",
            "requires": {"cluster": {"interface": "cluster"}},
            "containers": {"foo": {"type": "oci-image"}},
        },
        config={},
    )

    with pytest.raises(RuntimeError):
        ctx.run("update-status", State(containers=[Container("foo")]))


@pytest.mark.parametrize(
    "roles_active, roles_inactive, expected",
    (
        ("abc", "de", "abc"),
        ("ac", "bde", "ac"),
        ("ac", "", "ac"),
        ("", "d", ""),
    ),
)
def test_roles(roles_active, roles_inactive, expected):
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
        assert set(mgr.charm.worker.roles) == set(expected)
