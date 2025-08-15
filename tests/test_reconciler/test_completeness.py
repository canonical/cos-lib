import itertools
from typing import Type

import ops

from cosl.reconciler import ALL_EVENTS, ALL_EVENTS_K8S, ALL_EVENTS_VM


def _get_inheritance_tree_leaves(cl: Type):
    return list(
        itertools.chain(
            *[
                (
                    [subc]
                    if (
                        subc.__module__.startswith("ops.") and not subc.__subclasses__()
                    )
                    else _get_inheritance_tree_leaves(subc)
                )
                for subc in cl.__subclasses__()
            ]
        )
    )


EXCLUDED_EVENTS = {
    ops.CollectMetricsEvent,
}

EXCLUDED_EVENTS_K8S = EXCLUDED_EVENTS.union({
    ops.UpgradeCharmEvent,
    ops.PebbleCustomNoticeEvent,
})

EXCLUDED_EVENTS_VM = EXCLUDED_EVENTS.union({
    ops.UpgradeCharmEvent,
    ops.InstallEvent,
    ops.StartEvent,
    ops.RemoveEvent,
    ops.StopEvent,
})


def test_correctness():
    """Verify we are surfacing only valid events."""
    all_event_types = set(_get_inheritance_tree_leaves(ops.EventBase))
    assert set(ALL_EVENTS).issubset(all_event_types)


def test_completeness():
    """Verify we are surfacing all events we care about.
    If a new version of ops adds more event types, this will start failing.
    Then we'll have to make a
    choice about whether to put those events in the safe or unsafe bucket.
    """
    all_event_types = set(_get_inheritance_tree_leaves(ops.HookEvent))
    assert set(ALL_EVENTS).union(EXCLUDED_EVENTS) == all_event_types
    assert set(ALL_EVENTS_K8S).union(EXCLUDED_EVENTS_K8S) == all_event_types
    assert set(ALL_EVENTS_VM).union(EXCLUDED_EVENTS_VM) == all_event_types


def test_exclusiveness():
    """Verify the safe and unsafe buckets have no intersection."""
    assert set(ALL_EVENTS).intersection(EXCLUDED_EVENTS) == set()
    assert set(ALL_EVENTS_K8S).intersection(EXCLUDED_EVENTS_K8S) == set()
    assert set(ALL_EVENTS_VM).intersection(EXCLUDED_EVENTS_VM) == set()
