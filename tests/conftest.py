# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Shared pytest fixtures, step definitions, and helpers for alert rule customization tests."""

import copy
from pathlib import Path

import pytest
import yaml
from pytest_bdd import given, parsers, then

from cosl.rules_customization import AlertRulesCustomization

_HERE = Path(__file__).parent
_SAMPLE_ALERTS_PATH = _HERE / "sample_alerts.yaml"


@pytest.fixture
def sample_alerts():
    """Relation alerts dict loaded from sample_alerts.yaml."""
    with open(_SAMPLE_ALERTS_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture
def ctx():
    """Mutable context dict shared across steps within a scenario."""
    return {}


# ---------------------------------------------------------------------------
# Given steps (shared across feature files)
# ---------------------------------------------------------------------------


@given(parsers.parse('the sample alerts from "{filename}"'))
def given_sample_alerts_from_file(ctx, filename):
    path = _HERE / filename
    with open(path) as f:
        ctx["alerts"] = yaml.safe_load(f)
    ctx["original"] = copy.deepcopy(ctx["alerts"])


@given('a rule named "GoneForever" and a rule named "Survivor"')
def given_gone_forever_and_survivor(ctx):
    ctx["alerts"] = {
        "app": {
            "groups": [
                {
                    "name": "g",
                    "rules": [
                        {"alert": "GoneForever", "expr": "x", "for": "10m"},
                        {"alert": "Survivor", "expr": "y", "for": "10m"},
                    ],
                }
            ]
        }
    }
    ctx["original"] = copy.deepcopy(ctx["alerts"])


# ---------------------------------------------------------------------------
# Then — Presence / absence of alerts
# ---------------------------------------------------------------------------


@then(parsers.parse('alert "{alert_name}" is absent from the result'))
def then_alert_absent(ctx, alert_name):
    assert alert_name not in str(ctx["result"])


@then(parsers.parse('alert "{alert_name}" is present in the result'))
def then_alert_present(ctx, alert_name):
    assert alert_name in str(ctx["result"])


@then(parsers.parse('the recording rule "{record_name}" is present in the result'))
def then_recording_rule_present(ctx, record_name):
    assert record_name in str(ctx["result"])


# ---------------------------------------------------------------------------
# Then — Presence / absence of groups and identifiers
# ---------------------------------------------------------------------------


@then(parsers.parse('group "{group_name}" is absent from identifier "{identifier}"'))
def then_group_absent(ctx, group_name, identifier):
    result = ctx["result"]
    if identifier not in result:
        return
    group_names = [g["name"] for g in result[identifier].get("groups", [])]
    assert group_name not in group_names


@then(parsers.parse('group "{group_name}" is present in identifier "{identifier}"'))
def then_group_present(ctx, group_name, identifier):
    result = ctx["result"]
    assert identifier in result
    group_names = [g["name"] for g in result[identifier].get("groups", [])]
    assert group_name in group_names


@then(parsers.parse('identifier "{identifier}" is absent from the result'))
def then_identifier_absent(ctx, identifier):
    assert identifier not in ctx["result"]


@then(parsers.parse('identifier "{identifier}" is present in the result'))
def then_identifier_present(ctx, identifier):
    assert identifier in ctx["result"]


# ---------------------------------------------------------------------------
# Then — Rule field assertions
# ---------------------------------------------------------------------------


@then(parsers.parse('alert "{alert_name}" has for equal to "{value}"'))
def then_alert_for(ctx, alert_name, value):
    result = ctx["result"]
    found = _find_alert_anywhere(result, alert_name)
    assert found["for"] == value, f"expected for={value!r}, got {found.get('for')!r}"


@then(parsers.parse("alert \"{alert_name}\" has expr equal to '{value}'"))
def then_alert_expr_single_quoted(ctx, alert_name, value):
    result = ctx["result"]
    found = _find_alert_anywhere(result, alert_name)
    assert found["expr"] == value, f"expected expr={value!r}, got {found.get('expr')!r}"


@then(parsers.parse('alert "{alert_name}" has expr equal to "{value}"'))
def then_alert_expr(ctx, alert_name, value):
    result = ctx["result"]
    found = _find_alert_anywhere(result, alert_name)
    assert found["expr"] == value, f"expected expr={value!r}, got {found.get('expr')!r}"


@then(parsers.parse('alert "{alert_name}" has label "{label_key}" equal to "{label_value}"'))
def then_alert_label(ctx, alert_name, label_key, label_value):
    result = ctx["result"]
    found = _find_alert_anywhere(result, alert_name)
    labels = found.get("labels", {})
    assert (
        labels.get(label_key) == label_value
    ), f"expected label {label_key}={label_value!r}, got {labels.get(label_key)!r}"


@then(parsers.parse('alert "{alert_name}" has annotation "{ann_key}" equal to "{ann_value}"'))
def then_alert_annotation(ctx, alert_name, ann_key, ann_value):
    result = ctx["result"]
    found = _find_alert_anywhere(result, alert_name)
    annotations = found.get("annotations", {})
    assert (
        annotations.get(ann_key) == ann_value
    ), f"expected annotation {ann_key}={ann_value!r}, got {annotations.get(ann_key)!r}"


@then(parsers.parse('alert "{alert_name}" has no labels'))
def then_alert_no_labels(ctx, alert_name):
    result = ctx["result"]
    found = _find_alert_anywhere(result, alert_name)
    assert not found.get("labels"), f"expected no labels, got {found.get('labels')!r}"


@then(parsers.parse('the recording rule "{record_name}" has expr equal to "{value}"'))
def then_recording_rule_expr(ctx, record_name, value):
    result = ctx["result"]
    found = _find_record_anywhere(result, record_name)
    assert found["expr"] == value, f"expected expr={value!r}, got {found.get('expr')!r}"


@then(
    parsers.parse(
        'the recording rule "{record_name}" has label "{label_key}" equal to "{label_value}"'
    )
)
def then_recording_rule_label(ctx, record_name, label_key, label_value):
    result = ctx["result"]
    found = _find_record_anywhere(result, record_name)
    labels = found.get("labels", {})
    assert labels.get(label_key) == label_value


# ---------------------------------------------------------------------------
# Then — Apply semantics (shared across remove-patch file)
# ---------------------------------------------------------------------------


@then("the original input is unchanged")
def then_original_unchanged(ctx):
    assert ctx["alerts"] == ctx["original"]


@then(parsers.parse('alert "{alert_name}" is absent from identifier "{identifier}"'))
def then_alert_absent_from_identifier(ctx, alert_name, identifier):
    result = ctx["result"]
    if identifier not in result:
        return
    assert alert_name not in str(result[identifier])


@then(parsers.parse('alert "{alert_name}" in app has for equal to "{value}"'))
def then_alert_in_app_for(ctx, alert_name, value):
    rules = ctx["result"]["app"]["groups"][0]["rules"]
    found = next(r for r in rules if r.get("alert") == alert_name)
    assert found["for"] == value


@then(parsers.parse('alert "{alert_name}" is absent from both results'))
def then_alert_absent_both(ctx, alert_name):
    assert alert_name not in str(ctx["result1"])
    assert alert_name not in str(ctx["result2"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_alert_anywhere(result, alert_name):
    """Search all identifiers/groups for an alerting rule by name."""
    for rule_file in result.values():
        for group in rule_file.get("groups", []):
            for rule in group.get("rules", []):
                if rule.get("alert") == alert_name:
                    return rule
    raise AssertionError(f"Alert {alert_name!r} not found in result")


def _find_record_anywhere(result, record_name):
    """Search all identifiers/groups for a recording rule by name."""
    for rule_file in result.values():
        for group in rule_file.get("groups", []):
            for rule in group.get("rules", []):
                if rule.get("record") == record_name:
                    return rule
    raise AssertionError(f"Recording rule {record_name!r} not found in result")


def find_rule(alerts, identifier, group_name, rule_name, *, by_record=False):
    """Return a single rule from an alerts dict, raising if not found."""
    key = "record" if by_record else "alert"
    groups = alerts[identifier]["groups"]
    group = next(g for g in groups if g["name"] == group_name)
    return next(rule for rule in group["rules"] if rule.get(key) == rule_name)


def _load_sample_alerts():
    """Load the canonical sample alerts from sample_alerts.yaml."""
    with open(_SAMPLE_ALERTS_PATH) as f:
        return yaml.safe_load(f)


def _apply(config):
    return AlertRulesCustomization.from_yaml(config).apply(_load_sample_alerts())
