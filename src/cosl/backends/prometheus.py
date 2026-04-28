# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Prometheus rule backend.

This module provides :class:`PrometheusRuleBackend`, the Prometheus-specific
implementation of :class:`~cosl.rules.RuleBackend`.  It is used by
:class:`~cosl.rules.AbstractRules` to load, validate, and manage
alert and recording rules written in PromQL.
"""

from ..types import QueryType
from .grouped_rules import _GroupedRuleBackend  # type: ignore


class PrometheusRuleBackend(_GroupedRuleBackend):
    """Backend for Prometheus alerting / recording rules (PromQL).

    Inherits all behaviour from :class:`~cosl.backends.grouped_rules._GroupedRuleBackend`
    and sets :attr:`query_type` to ``"promql"``.

    Responsibilities:

    * Parse rule files/dicts in the official Prometheus rule format or the
      single-rule-per-file shorthand.
    * Inject Juju topology labels into rule labels and PromQL expressions
      via ``cos-tool``.
    * Validate the resulting rules through ``cos-tool`` PromQL validation.
    * Serialise the rules into the ``{"groups": [...]}`` format expected by
      Prometheus.

    Usage::

        from cosl.backends.prometheus import PrometheusRuleBackend
        from cosl.rules import AbstractRules

        rules = AbstractRules(backend=PrometheusRuleBackend(topology=my_topology))
        rules.add_path("./prometheus_alert_rules")
    """

    query_type: QueryType = "promql"
