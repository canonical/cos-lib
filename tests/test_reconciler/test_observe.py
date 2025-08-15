from unittest.mock import MagicMock, patch

import ops.framework
import pytest
from ops.testing import Context, Relation, State
from scenario.context import CharmEvents

from cosl.reconciler import ALL_EVENTS, observe_all


def get_observed_events(observe_mock):
    return {call.args[0].event_type for call in observe_mock.call_args_list}


@pytest.fixture
def observe_mock():
    with patch("ops.framework.Framework.observe", MagicMock()) as mm:
        yield mm


@pytest.fixture
def charm(observe_mock):
    ctx = Context(
        ops.CharmBase,
        meta={
            "name": "luca",
            "requires": {"bax": {"interface": "bar"}},
            "containers": {"foo": {}},
            "storage": {"foo": {"type": "bar"}},
        },
        actions={"foo": {}},
    )
    with ctx(ctx.on.update_status(), state=State()) as mgr:
        yield mgr.charm


@pytest.mark.parametrize("event_arg", (True, False))
def test_observe_all(charm, observe_mock, event_arg):
    # GIVEN a regular luca charm
    # WHEN we observe_all with no custom filters
    observe_all(
        charm, callback=(lambda _: None) if event_arg else (lambda: None), include=ALL_EVENTS
    )
    # THEN events from all categories are observed
    observed_events = get_observed_events(observe_mock)
    assert observed_events == ALL_EVENTS


@pytest.mark.parametrize("event_arg", (True, False))
def test_observe_emission(event_arg):
    # GIVEN a regular luca charm that only observes certain event types
    class LucaCharm(ops.CharmBase):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            observe_all(
                self,
                callback=self._event_observer if event_arg else self._reconcile,
                include={ops.RelationEvent, ops.SecretEvent, ops.StorageEvent},
            )

        def _event_observer(self, _):  # observe target
            self._reconcile()

        def _reconcile(self):  # observe target
            self.reconcile()

        def reconcile(self):  # mock target (for testing)
            pass

    # WHEN we observe_all
    ctx = Context(
        LucaCharm,
        meta={
            "name": "luca",
            "requires": {"bax": {"interface": "bar"}},
            "containers": {"foo": {}},
        },
        actions={"foo": {}},
    )
    with patch.object(LucaCharm, "reconcile", MagicMock()) as mm:
        # THEN the reconciler does NOT get called on excluded events
        ctx.run(ctx.on.upgrade_charm(), state=State())
        ctx.run(ctx.on.update_status(), state=State())
        ctx.run(ctx.on.install(), state=State())
        ctx.run(ctx.on.stop(), state=State())
        assert not mm.called

    with patch.object(LucaCharm, "reconcile", MagicMock()) as mm:
        relation = Relation("bax")
        ctx.run(ctx.on.relation_changed(relation), state=State(relations={relation}))
        # THEN the reconciler gets called on included events
        assert mm.called


@pytest.mark.parametrize(
    "event, name",
    (
        (CharmEvents.install(), "install"),
        (CharmEvents.upgrade_charm(), "upgradecharm"),
        (CharmEvents.update_status(), "updatestatus"),
    ),
)
def test_observe_groups(event, name):
    # GIVEN a regular luca charm that only observes certain event types
    class LucaCharm(ops.CharmBase):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            observe_all(
                self,
                callback=self._install,
                include=(ops.InstallEvent,),
            )
            observe_all(
                self,
                callback=self._upgradecharm,
                include=[ops.UpgradeCharmEvent],
            )
            observe_all(
                self,
                callback=self._updatestatus,
                include={ops.UpdateStatusEvent},
            )

        def _updatestatus(self):  # observe target
            self.updatestatus()

        def _upgradecharm(self):  # observe target
            self.upgradecharm()

        def _install(self):  # observe target
            self.install()

        def updatestatus(self):  # mock target (for testing)
            pass

        def upgradecharm(self):  # mock target (for testing)
            pass

        def install(self):  # mock target (for testing)
            pass

    # WHEN we observe_all
    ctx = Context(
        LucaCharm,
        meta={
            "name": "luca",
            "requires": {"bax": {"interface": "bar"}},
            "containers": {"foo": {}},
        },
        actions={"foo": {}},
    )
    mocks = [MagicMock(), MagicMock(), MagicMock()]
    with patch.object(LucaCharm, "updatestatus", mocks[0]):
        with patch.object(LucaCharm, "upgradecharm", mocks[1]):
            with patch.object(LucaCharm, "install", mocks[2]):
                # THEN the right reconciler gets called
                ctx.run(event, state=State())

                expected = {
                    "install": [False, False, True],
                    "upgradecharm": [False, True, False],
                    "updatestatus": [True, False, False],
                }[name]
                calls = [mock.called for mock in mocks]
                assert calls == expected
