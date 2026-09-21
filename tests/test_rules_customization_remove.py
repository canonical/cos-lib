# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""pytest-bdd step definitions for remove scenarios.

Feature file: tests/features/remove.feature
"""

import yaml
from helpers import _find_alert, _find_record, _find_rule, _load_sample_alerts
from pytest_bdd import given, parsers, scenarios, then, when

from cosl.rules_customization import AlertRulesCustomization

scenarios("features/remove.feature")


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given(parsers.parse("the following alert rules:\n{docstring}"), target_fixture="alerts")
def given_the_following_alert_rules(docstring):
    return yaml.safe_load(docstring)


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


@when(
    parsers.parse("the following customization is applied:\n{docstring}"), target_fixture="result"
)
def when_the_following_customization_is_applied(docstring, alerts):
    return AlertRulesCustomization.from_yaml(docstring).apply(alerts)


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------


@then(parsers.parse('alert "{name}" is present'))
def then_alert_present(result, name):
    _find_alert(result, name)  # raises AssertionError if not found


@then(parsers.parse('alert "{name}" is absent'))
def then_alert_absent(result, name):
    for rule_file in result.values():
        for group in rule_file.get("groups", []):
            for rule in group.get("rules", []):
                assert rule.get("alert") != name, f"alert {name!r} was found but should be absent"


@then(parsers.parse('recording rule "{name}" is present'))
def then_recording_rule_present(result, name):
    _find_record(result, name)  # raises AssertionError if not found


@then(parsers.parse('group "{group_name}" is absent from identifier "{identifier}"'))
def then_group_absent(result, group_name, identifier):
    if identifier not in result:
        return
    group_names = [g["name"] for g in result[identifier].get("groups", [])]
    assert (
        group_name not in group_names
    ), f"group {group_name!r} was found in {identifier!r} but should be absent"


@then(parsers.parse('group "{group_name}" is present in identifier "{identifier}"'))
def then_group_present(result, group_name, identifier):
    assert identifier in result, f"identifier {identifier!r} not found in result"
    group_names = [g["name"] for g in result[identifier].get("groups", [])]
    assert group_name in group_names, f"group {group_name!r} not found in {identifier!r}"


@then(parsers.parse('identifier "{identifier}" is absent'))
def then_identifier_absent(result, identifier):
    assert identifier not in result, f"identifier {identifier!r} was found but should be absent"


@then(parsers.parse('identifier "{identifier}" is present'))
def then_identifier_present(result, identifier):
    assert identifier in result, f"identifier {identifier!r} not found in result"


# ---------------------------------------------------------------------------
# Plain pytest tests — edge cases for remove
# ---------------------------------------------------------------------------


class TestRemove:
    def test_remove_by_alert_and_labels_combined(self):
        alerts = _load_sample_alerts()

        config_matching = """
remove:
  - where:
      alert: HighLatency
      labels:
        severity: critical
"""
        result = AlertRulesCustomization.from_yaml(config_matching).apply(alerts)
        assert "HighLatency" not in str(result)

        config_not_matching = """
remove:
  - where:
      alert: HighLatency
      labels:
        severity: warning
"""
        result = AlertRulesCustomization.from_yaml(config_not_matching).apply(alerts)
        assert "HighLatency" in str(result)

    def test_remove_by_group_and_labels_combined(self):
        alerts = _load_sample_alerts()
        config = """
remove:
  - where:
      group: group_a
      labels:
        severity: warning
"""
        result = AlertRulesCustomization.from_yaml(config).apply(alerts)
        group = next(g for g in result["app-1"]["groups"] if g["name"] == "group_a")
        rule_names = [r.get("alert") or r.get("record") for r in group["rules"]]
        assert rule_names == ["HighLatency", "job:latency:mean5m"]

    def test_remove_preserves_recording_rules_when_group_not_sole_selector(self):
        alerts = _load_sample_alerts()
        config = """
remove:
  - where:
      labels:
        severity: warning
"""
        result = AlertRulesCustomization.from_yaml(config).apply(alerts)
        record = _find_rule(result, "app-1", "group_a", "job:latency:mean5m", by_record=True)
        assert record["expr"] == "avg(latency)"
