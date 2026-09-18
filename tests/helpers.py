# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Shared test helpers for alert rule customization tests."""

from pathlib import Path

import yaml

_SAMPLE_ALERTS_PATH = Path(__file__).parent / "sample_alerts.yaml"


def _load_sample_alerts():
    """Load the canonical sample alerts from sample_alerts.yaml."""
    with open(_SAMPLE_ALERTS_PATH) as f:
        return yaml.safe_load(f)


def _find_alert(result, name):
    for rule_file in result.values():
        for group in rule_file.get("groups", []):
            for rule in group.get("rules", []):
                if rule.get("alert") == name:
                    return rule
    raise AssertionError(f"Alert {name!r} not found in result")


def _find_record(result, name):
    for rule_file in result.values():
        for group in rule_file.get("groups", []):
            for rule in group.get("rules", []):
                if rule.get("record") == name:
                    return rule
    raise AssertionError(f"Recording rule {name!r} not found in result")


def _find_rule(alerts, identifier, group_name, rule_name, *, by_record=False):
    """Return a single rule from an alerts dict by identifier, group, and name."""
    key = "record" if by_record else "alert"
    groups = alerts[identifier]["groups"]
    group = next(g for g in groups if g["name"] == group_name)
    return next(rule for rule in group["rules"] if rule.get(key) == rule_name)
