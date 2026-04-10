# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Prometheus rule backend and pre-built generic alert groups."""

import copy
from types import SimpleNamespace
from typing import ClassVar, Final

from .grouped_rules import _GroupedRuleBackend  # type: ignore
from .types import OfficialRuleFileFormat, QueryType

# ---------------------------------------------------------------------------
# Generic alert rules (pre-built)
# ---------------------------------------------------------------------------

HOST_METRICS_MISSING_RULE_NAME = "HostMetricsMissing"

_generic_alert_rules: Final = SimpleNamespace(
    host_down={
        "alert": "HostDown",
        "expr": "up < 1",
        "for": "5m",
        "labels": {"severity": "critical"},
        "annotations": {
            "summary": "Host '{{ $labels.instance }}' is down.",
            "description": (
                "Juju application '{{ $labels.juju_application }}' in model "
                "'{{ $labels.juju_model }}' is down. Prometheus has been unable "
                "to scrape it during at least the past five minutes."
            ),
        },
    },
    host_metrics_missing={
        "alert": HOST_METRICS_MISSING_RULE_NAME,
        "expr": "absent(up)",
        "for": "5m",
        "labels": {"severity": "warning"},
        "annotations": {
            "summary": (
                "Unit '{{ $labels.juju_unit }}' of application "
                "'{{ $labels.juju_application }}' is down or failing to remote write."
            ),
            "description": (
                "`Up` missing for unit '{{ $labels.juju_unit }}' of application "
                "{{ $labels.juju_application }} in model {{ $labels.juju_model }}. "
                "Please ensure the unit or the collector scraping it is up and is "
                "able to successfully reach the metrics backend."
            ),
        },
    },
    aggregator_metrics_missing={
        "alert": "AggregatorMetricsMissing",
        "expr": "absent(up)",
        "for": "5m",
        "labels": {"severity": "critical"},
        "annotations": {
            "summary": (
                "Metrics not received from application "
                "'{{ $labels.juju_application }}'. All units are down or failing "
                "to remote write."
            ),
            "description": (
                "`Up` missing for ALL units of application "
                "{{ $labels.juju_application }} in model {{ $labels.juju_model }}. "
                "This can also mean the units or the collector scraping them are "
                "unable to reach the remote write endpoint of the metrics backend. "
                "Please ensure the correct firewall rules are applied."
            ),
        },
    },
)


class _GenericAlertGroups:
    """Pre-built alert groups for common health-check rules."""

    _application_rules: ClassVar[OfficialRuleFileFormat] = {
        "groups": [
            {
                "name": "HostHealth",
                "rules": [
                    _generic_alert_rules.host_down,
                    _generic_alert_rules.host_metrics_missing,
                ],
            },
        ]
    }
    _aggregator_rules: ClassVar[OfficialRuleFileFormat] = {
        "groups": [
            {
                "name": "AggregatorHostHealth",
                "rules": [
                    _generic_alert_rules.host_metrics_missing,
                    _generic_alert_rules.aggregator_metrics_missing,
                ],
            },
        ]
    }

    @property
    def application_rules(self) -> OfficialRuleFileFormat:
        """Rules for application-level monitoring (scrape-based)."""
        return copy.deepcopy(self._application_rules)

    @property
    def aggregator_rules(self) -> OfficialRuleFileFormat:
        """Rules for remote-write aggregator monitoring (no ``up`` metric from scrape)."""
        return copy.deepcopy(self._aggregator_rules)


generic_alert_groups: Final = _GenericAlertGroups()


# ---------------------------------------------------------------------------
# Prometheus backend
# ---------------------------------------------------------------------------


class PrometheusRuleBackend(_GroupedRuleBackend):
    """Backend for Prometheus alerting / recording rules (PromQL)."""

    query_type: QueryType = "promql"
