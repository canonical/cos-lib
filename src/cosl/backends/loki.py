# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Loki rule backend."""

from ..types import QueryType
from .grouped_rules import _GroupedRuleBackend  # type: ignore


class LokiRuleBackend(_GroupedRuleBackend):
    """Backend for Loki alerting / recording rules (LogQL)."""

    query_type: QueryType = "logql"
