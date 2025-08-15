"""Regretful reconciler charm utils."""

import inspect
from typing import Any, Callable, Final, Iterable, Optional, Set, Type, TypeVar, Union, cast

import ops

_EventTyp = TypeVar("_EventTyp", bound=Type[ops.EventBase])
_EventBaseSubclassIterable = Iterable[_EventTyp]
_EventBaseSubclassSet = Set[_EventTyp]

# baseline obtained by:
# ALL_EVENTS = _get_inheritance_tree_leaves(ops.HookEvent)
# where:
# def _get_inheritance_tree_leaves(cl:Type):
#     return list(
#         itertools.chain(
#             *[
#                 ([subc] if (subc.__module__.startswith("ops.") and not subc.__subclasses__()) else
#                 _get_inheritance_tree_leaves(subc)) for subc in cl.__subclasses__()
#             ]
#         )
#     )
# at: 11/8/2025 (ops==2.17.1)
ALL_EVENTS: Final[Set[Type[ops.EventBase]]] = {
    ops.charm.PebbleCheckRecoveredEvent,
    ops.charm.PebbleCheckFailedEvent,
    ops.charm.ConfigChangedEvent,
    ops.charm.UpdateStatusEvent,
    ops.charm.PreSeriesUpgradeEvent,
    ops.charm.PostSeriesUpgradeEvent,
    ops.charm.LeaderElectedEvent,
    ops.charm.LeaderSettingsChangedEvent,
    # ops.charm.CollectMetricsEvent,           # deprecated
    ops.charm.RelationCreatedEvent,
    ops.charm.PebbleReadyEvent,
    ops.charm.RelationJoinedEvent,
    ops.charm.RelationChangedEvent,
    ops.charm.RelationDepartedEvent,
    ops.charm.RelationBrokenEvent,
    ops.charm.StorageAttachedEvent,
    ops.charm.StorageDetachingEvent,
    ops.charm.SecretChangedEvent,
    ops.charm.SecretRotateEvent,
    ops.charm.SecretRemoveEvent,
    ops.charm.SecretExpiredEvent,
    ops.charm.InstallEvent,
    ops.charm.StartEvent,
    ops.charm.RemoveEvent,
    ops.charm.StopEvent,
    ops.charm.UpgradeCharmEvent,
    ops.charm.PebbleCustomNoticeEvent,
}

ALL_EVENTS_K8S: Final[Set[Type[ops.EventBase]]] = ALL_EVENTS.difference(
    {
        ops.charm.UpgradeCharmEvent,  # this is your only chance to know you've been upgraded
        ops.charm.PebbleCustomNoticeEvent,  # sometimes you want to handle the various notices differently
    }
)

ALL_EVENTS_VM: Final[Set[Type[ops.EventBase]]] = ALL_EVENTS.difference(
    {
        ops.charm.UpgradeCharmEvent,  # this is your only chance to know you've been upgraded
        ops.charm.InstallEvent,  # (machine) charms may want to observe this
        ops.charm.StartEvent,  # same
        ops.charm.RemoveEvent,  # usually pointless to reconcile towards an up state if you're shutting down
        ops.charm.StopEvent,  # same
    }
)


def observe_all(
    charm: ops.CharmBase,
    include: Optional[Iterable[_EventTyp]],
    callback: Union[Callable[[Any], None], Callable[[], None]],
):
    """Observe all events that are subtypes of any ``include``d types, and map them to a single handler.

    You can override the list of events to map to the callback by passing an iterable of ops.EventBase (sub)types.

    Usage:
    >>> class MyCharm(ops.CharmBase):
    ...    def __init__(self, ...):
    ...        super().__init__(...)
    ...        observe_all(self, ALL_EVENTS, self.reconcile)
    ...
    ...     def reconcile(self):
    ...         pass

    Or:
    >>> class MyCharm(ops.CharmBase):
    ...    def __init__(self, ...):
    ...        super().__init__(...)
    ...        observe_all(self, self._on_any_event)
    ...
    ...    def _on_any_event(self, _):
    ...        self.reconcile()
    ...
    ...     def reconcile(self):
    ...         pass

    Or:
    >>> class MyCharm(ops.CharmBase):
    ...    def __init__(self, ...):
    ...        super().__init__(...)
    ...        observe_all(self, self._on_group1, {ops.StartEvent, ops.StopEvent})
    ...        observe_all(self, self._on_group2, {ops.RelationEvent, ops.SecretEvent, ops.framework.LifecycleEvent})
    ...        # ... add more groups as needed
    ...
    ...    def _on_group1(self):
    ...        pass
    ...
    ...     def _on_group2(self):
    ...        pass

    Or even! (but you're a bad person if you do this)
    >>> class MyCharm(ops.CharmBase):
    ...    def __init__(self, ...):
    ...        super().__init__(...)
    ...        observe_all(self, lambda: print("I am running a relation event"), {ops.RelationEvent})
    """
    # ops types it with Any!
    evthandler: Callable[[Any], None]
    if not inspect.signature(callback).parameters:
        # we're passing the reconciler method directly
        class _Observer(ops.Object):
            def __init__(self):
                super().__init__(charm, key="_observer_proxy_obj")
                # attach ref to something solid to prevent GC
                charm.framework._observer_proxy_obj = self  # type: ignore

            def evt_handler(self, _: ops.EventBase) -> None:
                callback()  # type: ignore

        evthandler = _Observer().evt_handler
    else:
        evthandler = cast(Callable[[Any], None], callback)

    included_events: Set[Type[ops.EventBase]] = set(include) if include else ALL_EVENTS
    for bound_evt in charm.on.events().values():
        if any(issubclass(bound_evt.event_type, include_type) for include_type in included_events):
            charm.framework.observe(bound_evt, evthandler)
