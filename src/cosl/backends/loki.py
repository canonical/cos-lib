# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Loki rule backend.

This module provides :class:`LokiRuleBackend`, the Loki-specific
implementation of :class:`~cosl.rules.RuleBackend`.  It is used by
:class:`~cosl.rules.AbstractRules` to load, validate, and manage
alert and recording rules written in LogQL.
"""

from ..types import QueryType
from .grouped_rules import _GroupedRuleBackend  # type: ignore


class LokiRuleBackend(_GroupedRuleBackend):
    """Backend for Loki alerting / recording rules (LogQL).

    Inherits all behaviour from :class:`~cosl.backends.grouped_rules._GroupedRuleBackend`
    and sets :attr:`query_type` to ``"logql"``.

    Responsibilities:

    * Parse rule files/dicts in the official Loki rule format or the
      single-rule-per-file shorthand.
    * Inject Juju topology labels into rule labels and LogQL expressions
      via ``cos-tool``.
    * Validate the resulting rules through ``cos-tool`` LogQL validation.
    * Serialise the rules into the ``{"groups": [...]}`` format expected by
      Loki.

    Usage::

        from cosl.backends.loki import LokiRuleBackend
        from cosl.rules import AbstractRules

        rules = AbstractRules(backend=LokiRuleBackend(topology=my_topology))
        rules.add_path("./loki_alert_rules")
    """

    query_type: QueryType = "logql"
