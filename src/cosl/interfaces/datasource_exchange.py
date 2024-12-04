#!/usr/bin/env python3
# Copyright 2024 Canonical
# See LICENSE file for licensing details.

"""Shared utilities for the inter-coordinator "grafana_datasource_exchange" interface.

See https://github.com/canonical/charm-relation-interfaces/pull/207 for the interface specification.
# TODO update when pr merged
"""


# FIXME: the interfaces import (because it's a git dep perhaps?)
#  can't be type-checked, which breaks everything
# pyright: reportMissingImports=false
# pyright: reportUntypedBaseClass=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownParameterType=false


import json
import logging
from itertools import chain
from typing import (
    Iterable,
    List,
    Tuple, Optional,
)

import ops
from interfaces.grafana_datasource_exchange.v0.schema import (
    GrafanaDatasource,
    GrafanaSourceAppData,
)
from ops import CharmBase
from typing_extensions import TypedDict

import cosl.interfaces.utils
from cosl.interfaces.utils import DataValidationError

log = logging.getLogger("_cluster")

DEFAULT_PROVIDE_ENDPOINT_NAME = "provide-ds-exchange"
DEFAULT_REQUIRE_ENDPOINT_NAME = "require-ds-exchange"
DS_EXCHANGE_INTERFACE_NAME = "grafana_datasource_exchange"


class DSExchangeAppData(cosl.interfaces.utils.DatabagModelV2, GrafanaSourceAppData):
    """App databag schema for both sides of this interface."""


class DatasourceDict(TypedDict):
    """Raw datasource information."""

    type: str
    uid: str


class EndpointValidationError(ValueError):
    """Raised if an endpoint name is invalid."""


def _validate_endpoints(charm: CharmBase, provider_endpoint: str, requirer_endpoint: str):
    meta = charm.meta
    for endpoint, source in (
        (provider_endpoint, meta.provides),
        (requirer_endpoint, meta.requires),
    ):
        if endpoint not in source:
            raise EndpointValidationError(f"endpoint {endpoint!r} not declared in charm metadata")
        interface_name = source[endpoint].interface_name
        if interface_name != DS_EXCHANGE_INTERFACE_NAME:
            raise EndpointValidationError(
                f"endpoint {endpoint} has unexpected interface {interface_name!r} "
                f"(should be {DS_EXCHANGE_INTERFACE_NAME})."
            )


class DatasourceExchange:
    """``grafana_datasource_exchange`` interface endpoint wrapper (provider AND requirer)."""

    def __init__(
        self,
        charm: ops.CharmBase,
        *,
        provider_endpoint: Optional[str] = None,
        requirer_endpoint: Optional[str] = None,
    ):
        self._charm = charm
        provider_endpoint = provider_endpoint or DEFAULT_PROVIDE_ENDPOINT_NAME
        requirer_endpoint = requirer_endpoint or DEFAULT_REQUIRE_ENDPOINT_NAME

        _validate_endpoints(charm, provider_endpoint, requirer_endpoint)

        # gather all relations, provider or requirer
        all_relations = chain(
            charm.model.relations[provider_endpoint], charm.model.relations[requirer_endpoint]
        )

        # filter out some common unhappy relation states
        self._relations: List[ops.Relation] = [
            rel for rel in all_relations if (rel.app and rel.data)
        ]

    def submit(self, raw_datasources: Iterable[DatasourceDict]):
        """Submit these datasources to all remotes.

        This operation is leader-only.
        """
        # sort by UID to prevent endless relation-changed cascades if this keeps flapping
        encoded_datasources = json.dumps(sorted(raw_datasources, key=lambda raw_ds: raw_ds["uid"]))
        app_data = DSExchangeAppData(
            datasources=encoded_datasources  # type: ignore[reportCallIssue]
        )

        for relation in self._relations:
            app_data.dump(relation.data[self._charm.app])

    @property
    def received_datasources(self) -> Tuple[GrafanaDatasource, ...]:
        """Collect all datasources that the remotes have shared.

        This operation is leader-only.
        """
        datasources: List[GrafanaDatasource] = []

        for relation in self._relations:
            try:
                datasource = DSExchangeAppData.load(relation.data[relation.app])
            except DataValidationError:
                # load() already logs something in this case
                continue

            datasources.extend(datasource.datasources)
        return tuple(sorted(datasources, key=lambda ds: ds.uid))
