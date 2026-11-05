# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for the actionable generic alert rule descriptions."""

from cosl.rules import GENERIC_ALERT_TROUBLESHOOTING_URL, generic_alert_groups


def test_generic_alerts_reference_troubleshooting_guide():
    """Every generic host-health alert should link to the runbook."""
    rule_names = set()

    for groups in (
        generic_alert_groups.application_rules,
        generic_alert_groups.aggregator_rules,
    ):
        for group in groups["groups"]:
            for rule in group["rules"]:
                rule_names.add(rule["alert"])
                description = rule["annotations"]["description"]
                assert description.endswith(
                    "For troubleshooting, see " + GENERIC_ALERT_TROUBLESHOOTING_URL
                )
                assert description.count(GENERIC_ALERT_TROUBLESHOOTING_URL) == 1

    assert rule_names == {
        "HostDown",
        "HostMetricsMissing",
        "AggregatorMetricsMissing",
    }
