# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Prometheus Scrape Library.

## Overview

This document explains how to integrate with the Opentelemetry-collector charm
for the purpose of providing OTLP telemetry to Opentelemetry-collector. This document is the
authoritative reference on the structure of relation data that is
shared between Opentelemetry-collector charms and any other charm that intends to
provide OTLP telemetry for Opentelemetry-collector.
"""

# TODO: Move to a lib
import logging
import socket
from enum import Enum

from juju_topology import JujuTopology
from ops import CharmBase
from ops.charm import RelationEvent
from ops.framework import EventBase, EventSource, Object, ObjectEvents

DEFAULT_CONSUMER_GRPC_RELATION_NAME = "send-grpc-otlp"
DEFAULT_CONSUMER_HTTP_RELATION_NAME = "send-http-otlp"
DEFAULT_PROVIDER_RELATION_NAME = "receive-otlp"
RELATION_INTERFACE_NAME = "otlp"
logger = logging.getLogger(__name__)


class OtlpEndpointsChangedEvent(EventBase):
    """Event emitted when OTLP endpoints change."""

    def __init__(self, handle, relation_id):
        super().__init__(handle)
        self.relation_id = relation_id


class OtlpConsumerEvents(ObjectEvents):
    """Event descriptor for events raised by `OTLPConsumer`."""

    endpoints_changed = EventSource(OtlpEndpointsChangedEvent)


class Protocols(Enum, str):
    """Supported OTLP protocols."""
    grpc = "grpc"
    http = "http"


class BaseOtlpConsumer(Object):
    # TODO: update
    """docstring."""

    on = OtlpConsumerEvents()  # pyright: ignore

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str,
    ):
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

        self.topology = JujuTopology.from_charm(charm)

        on_relation = self._charm.on[self._relation_name]

        # TODO: Use Pietro's new lib to listen to all events and execute the reconcile
        self.framework.observe(self._charm.on.update_status, self._reconcile)
        self.framework.observe(self._charm.on.upgrade_charm, self._reconcile)
        self.framework.observe(on_relation.relation_joined, self._reconcile)
        self.framework.observe(on_relation.relation_changed, self._reconcile)
        self.framework.observe(on_relation.relation_departed, self._reconcile)
        self.framework.observe(on_relation.relation_broken, self._reconcile)

    def _reconcile(self, event: RelationEvent) -> None:
        pass


class OtlpHttpConsumer(BaseOtlpConsumer):
    # TODO: update
    """docstring."""

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = DEFAULT_CONSUMER_HTTP_RELATION_NAME,
    ):
        super().__init__(charm, relation_name)


class OtlpGrpcConsumer(BaseOtlpConsumer):
    # TODO: update
    """docstring."""

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = DEFAULT_CONSUMER_GRPC_RELATION_NAME,
    ):
        super().__init__(charm, relation_name)


class OtlpProviderConsumersChangedEvent(EventBase):
    """Event emitted when Prometheus remote_write alerts change."""


class OtlpProviderEvents(ObjectEvents):
    """Event descriptor for events raised by `PrometheusRemoteWriteProvider`."""

    consumers_changed = EventSource(OtlpProviderConsumersChangedEvent)


# TODO: Consider renaming to SendOTLP
class OtlpProvider(Object):
    # TODO: update
    """docstring."""

    on = OtlpProviderEvents()  # pyright: ignore

    def __init__(
        self,
        charm: CharmBase,
        port: int,
        relation_name: str = DEFAULT_PROVIDER_RELATION_NAME,
        path: str = "",
    ):
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        self._port = port
        self._path = path

        on_relation = self._charm.on[self._relation_name]
        self.framework.observe(self._charm.on.update_status, self._reconcile)
        self.framework.observe(self._charm.on.upgrade_charm, self._reconcile)
        self.framework.observe(on_relation.relation_joined, self._reconcile)
        self.framework.observe(on_relation.relation_changed, self._reconcile)
        self.framework.observe(on_relation.relation_departed, self._reconcile)
        self.framework.observe(on_relation.relation_broken, self._reconcile)

    def _reconcile(self, event: RelationEvent) -> None:
        if not self._charm.unit.is_leader():
            return

        endpoint = (f"http://{socket.getfqdn()}:{self._port}/{self._path}",)

        for relation in self.model.relations[self._relation_name]:
            relation.data[self._charm.app] = endpoint
