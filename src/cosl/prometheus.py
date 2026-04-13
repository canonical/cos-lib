# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Prometheus rule backend and pre-built generic alert groups."""

from .grouped_rules import _GroupedRuleBackend  # type: ignore
from .types import QueryType


class PrometheusRuleBackend(_GroupedRuleBackend):
    """Backend for Prometheus alerting / recording rules (PromQL)."""

    query_type: QueryType = "promql"
