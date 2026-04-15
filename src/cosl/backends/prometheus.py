# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Prometheus rule backend and pre-built generic alert groups."""

from ..types import QueryType
from .grouped_rules import _GroupedRuleBackend  # type: ignore


class PrometheusRuleBackend(_GroupedRuleBackend):
    """Backend for Prometheus alerting / recording rules (PromQL)."""

    query_type: QueryType = "promql"
