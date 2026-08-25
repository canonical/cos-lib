# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""pytest-bdd step definitions for alert rule customization behavioural tests.

Feature file: tests/features/alert_rule_customization.feature
Schema/validation tests: tests/test_rules_customization_schema.py
"""

import copy

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from cosl.rules_customization import (
    CUSTOM_ALERT_RULES_KEY,
    AlertRulesCustomization,
)

scenarios("features/alert_rule_customization.feature")


# ---------------------------------------------------------------------------
# Shared context fixture — carries state between Given/When/Then steps
# ---------------------------------------------------------------------------


@pytest.fixture
def ctx():
    """Mutable context dict shared across steps within a scenario."""
    return {}


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given("a set of relation alerts from two apps")
def given_sample_alerts(ctx, sample_alerts):
    ctx["alerts"] = sample_alerts
    ctx["original"] = copy.deepcopy(sample_alerts)


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
# When — Remove
# ---------------------------------------------------------------------------


@when('I apply a customization that removes alert "LowThroughput"')
def when_remove_low_throughput(ctx):
    config = """
remove:
  - where:
      alert: LowThroughput
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


@when('I apply a customization that removes group "group_a"')
def when_remove_group_a(ctx):
    config = """
remove:
  - where:
      group: group_a
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


@when(
    'I apply a customization that removes alerts in group "group_a" with alert name "LowThroughput"'
)
def when_remove_group_a_low_throughput(ctx):
    config = """
remove:
  - where:
      group: group_a
      alert: LowThroughput
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


@when('I apply a customization that removes alerts with label "severity" equal to "warning"')
def when_remove_by_severity_warning(ctx):
    config = """
remove:
  - where:
      labels:
        severity: warning
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


@when(
    'I apply a customization that removes alerts with annotation "summary" equal to "latency is high"'
)
def when_remove_by_annotation(ctx):
    config = """
remove:
  - where:
      annotations:
        summary: latency is high
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


@when('I apply a customization that removes alerts with label "juju_application" equal to "app-1"')
def when_remove_by_juju_application(ctx):
    config = """
remove:
  - where:
      labels:
        juju_application: app-1
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


@when('I apply a customization that removes alert "HighLatency" and alert "OtherAlert"')
def when_remove_two_alerts(ctx):
    config = """
remove:
  - where:
      alert: HighLatency
  - where:
      alert: OtherAlert
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


@when('I apply a customization that removes alert "HostDown"')
def when_remove_host_down(ctx):
    config = """
remove:
  - where:
      alert: HostDown
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


@when('I apply a customization that removes alert "OtherAlert"')
def when_remove_other_alert(ctx):
    config = """
remove:
  - where:
      alert: OtherAlert
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


# ---------------------------------------------------------------------------
# When — Patch
# ---------------------------------------------------------------------------


@when('I apply a customization that patches alert "HighLatency" setting for to "30m"')
def when_patch_for(ctx):
    config = """
patch:
  - where:
      alert: HighLatency
    set:
      for: 30m
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


@when(
    'I apply a customization that patches alert "HighLatency" setting alert name to "RenamedLatency"'
)
def when_patch_alert_name(ctx):
    config = """
patch:
  - where:
      alert: HighLatency
    set:
      alert: RenamedLatency
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


@when('I apply a customization that patches alert "HostDown" setting expr to "up == 0"')
def when_patch_expr(ctx):
    config = """
patch:
  - where:
      alert: HostDown
    set:
      expr: up == 0
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


@when(
    'I apply a customization that patches alert "HighLatency" setting label "severity" to "page" and adding label "extra" as "added"'
)
def when_patch_labels(ctx):
    config = """
patch:
  - where:
      alert: HighLatency
    set:
      labels:
        severity: page
        extra: added
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


@when(
    'I apply a customization that patches alert "HighLatency" setting label "juju_application" to "other-app"'
)
def when_patch_juju_label(ctx):
    config = """
patch:
  - where:
      alert: HighLatency
    set:
      labels:
        juju_application: other-app
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


@when(
    'I apply a customization that patches alert "HighLatency" setting annotation "summary" to "new summary" and adding annotation "description" as "new description"'
)
def when_patch_annotations(ctx):
    config = """
patch:
  - where:
      alert: HighLatency
    set:
      annotations:
        summary: new summary
        description: new description
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


@when('I apply a customization that patches all rules in group "group_a" setting expr to "hacked"')
def when_patch_group_expr(ctx):
    config = """
patch:
  - where:
      group: group_a
    set:
      expr: hacked
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


@when(
    'I apply a customization that patches alerts with label "severity" equal to "warning" setting label "severity" to "critical"'
)
def when_patch_by_label(ctx):
    config = """
patch:
  - where:
      labels:
        severity: warning
    set:
      labels:
        severity: critical
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


# ---------------------------------------------------------------------------
# When — Add
# ---------------------------------------------------------------------------


@when('I apply a customization that adds a group named "my-custom-alerts" with alert "MyAlert"')
def when_add_group(ctx):
    config = """
add:
  groups:
    - name: my-custom-alerts
      rules:
        - alert: MyAlert
          expr: up{juju_model="prod"} == 0
          for: 5m
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


@when(
    'I apply a customization that adds a group named "my-custom-alerts" with alert "MyAlert" and expr \'up{juju_model="prod"} == 0\''
)
def when_add_group_check_expr(ctx):
    config = """
add:
  groups:
    - name: my-custom-alerts
      rules:
        - alert: MyAlert
          expr: 'up{juju_model="prod"} == 0'
"""
    ctx["customization"] = AlertRulesCustomization.from_yaml(config)
    ctx["result"] = ctx["customization"].apply(ctx["alerts"])


@when("I apply the same customization twice with an add block")
def when_apply_twice_add(ctx):
    config = """
add:
  groups:
    - name: my-custom-alerts
      rules:
        - alert: MyAlert
          expr: up == 0
"""
    ctx["customization"] = AlertRulesCustomization.from_yaml(config)
    ctx["result1"] = ctx["customization"].apply(ctx["alerts"])
    ctx["result2"] = ctx["customization"].apply(ctx["alerts"])


@when("I mutate the alert name in the first result")
def when_mutate_first_result(ctx):
    ctx["result1"][CUSTOM_ALERT_RULES_KEY]["groups"][0]["rules"][0]["alert"] = "Mangled"


# ---------------------------------------------------------------------------
# When — Apply semantics
# ---------------------------------------------------------------------------


@when('I apply a customization that removes alert "LowThroughput" and patches alert "HighLatency"')
def when_remove_and_patch(ctx):
    config = """
remove:
  - where:
      alert: LowThroughput
patch:
  - where:
      alert: HighLatency
    set:
      for: 1h
      labels:
        severity: page
"""
    AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])
    ctx["result"] = ctx["alerts"]  # we check that the original is unchanged


@when(
    'I apply a customization that removes "GoneForever", patches "Survivor" for to "2m", and adds a new "GoneForever"'
)
def when_order_of_operations(ctx):
    config = """
remove:
  - where:
      alert: GoneForever
patch:
  - where:
      alert: GoneForever
    set:
      for: 1m
  - where:
      alert: Survivor
    set:
      for: 2m
add:
  groups:
    - name: added
      rules:
        - alert: GoneForever
          expr: up
"""
    ctx["result"] = AlertRulesCustomization.from_yaml(config).apply(ctx["alerts"])


@when("I apply the same remove customization to two different inputs")
def when_reuse_customization(ctx):
    config = """
remove:
  - where:
      alert: HostDown
"""
    customization = AlertRulesCustomization.from_yaml(config)
    ctx["result1"] = customization.apply(ctx["alerts"])
    other = {
        "other": {"groups": [{"name": "g", "rules": [{"alert": "HostDown", "expr": "up < 1"}]}]}
    }
    ctx["result2"] = customization.apply(other)


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
        return  # identifier itself gone, group certainly absent
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
# Then — Apply semantics
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


@then('alert "Survivor" has for equal to "2m"')
def then_survivor_for(ctx):
    rules = ctx["result"]["app"]["groups"][0]["rules"]
    survivor = next(r for r in rules if r.get("alert") == "Survivor")
    assert survivor["for"] == "2m"


@then('the added alert "GoneForever" does not have a for field')
def then_added_gone_forever_no_for(ctx):
    added = ctx["result"][CUSTOM_ALERT_RULES_KEY]["groups"][0]["rules"][0]
    assert added["alert"] == "GoneForever"
    assert "for" not in added


@then('the second result still contains alert "MyAlert"')
def then_second_result_has_my_alert(ctx):
    rule = ctx["result2"][CUSTOM_ALERT_RULES_KEY]["groups"][0]["rules"][0]
    assert rule["alert"] == "MyAlert"


@then('alert "HostDown" is absent from both results')
def then_host_down_absent_both(ctx):
    assert "HostDown" not in str(ctx["result1"])
    assert "HostDown" not in str(ctx["result2"])


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
