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
    'I apply a customization that removes "GoneForever" and patches "Survivor" for to "2m"'
)
def when_order_of_operations(ctx):
    config = """
remove:
  - where:
      alert: GoneForever
patch:
  - where:
      alert: Survivor
    set:
      for: 2m
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


# ---------------------------------------------------------------------------
# Behavioural assertions as plain pytest tests
# ---------------------------------------------------------------------------
#
# The feature-file scenarios above cover the happy paths. The tests below cover
# the detailed edge cases that are awkward to express in Gherkin, in the same
# style as the surrounding pytest suite.


def _sample_alerts():
    """Relation alerts dict in the same shape as MetricsConsumer.alerts."""
    return {
        "app-1": {
            "groups": [
                {
                    "name": "group_a",
                    "rules": [
                        {
                            "alert": "HighLatency",
                            "expr": "latency > 100",
                            "for": "10m",
                            "labels": {"severity": "critical", "juju_application": "app-1"},
                            "annotations": {"summary": "latency is high"},
                        },
                        {
                            "alert": "LowThroughput",
                            "expr": "throughput < 10",
                            "for": "5m",
                            "labels": {"severity": "warning"},
                        },
                        {
                            "record": "job:latency:mean5m",
                            "expr": "avg(latency)",
                            "labels": {"severity": "warning"},
                        },
                    ],
                },
                {
                    "name": "group_b",
                    "rules": [
                        {"alert": "HostDown", "expr": "up < 1"},
                    ],
                },
            ]
        },
        "app-2": {
            "groups": [
                {
                    "name": "group_c",
                    "rules": [
                        {"alert": "OtherAlert", "expr": "x > 0"},
                    ],
                }
            ]
        },
    }


def _find_rule(alerts, identifier, group_name, rule_name, *, by_record=False):
    """Fetch a single rule from an alerts dict for assertions."""
    key = "record" if by_record else "alert"
    groups = alerts[identifier]["groups"]
    group = next(g for g in groups if g["name"] == group_name)
    return next(rule for rule in group["rules"] if rule.get(key) == rule_name)


def _apply(config):
    return AlertRulesCustomization.from_yaml(config).apply(_sample_alerts())


class TestRemove:
    def test_remove_by_alert_name(self):
        config = """
            remove:
              - where:
                  alert: LowThroughput
            """
        result = _apply(config)

        group_names = [g["name"] for g in result["app-1"]["groups"]]
        assert group_names == ["group_a", "group_b"]
        rule_names = [r.get("alert") for r in result["app-1"]["groups"][0]["rules"]]
        assert rule_names == ["HighLatency", None]  # record remains

    def test_remove_by_group_only_drops_entire_group_including_recording_rules(self):
        config = """
            remove:
              - where:
                  group: group_a
            """
        result = _apply(config)

        group_names = [g["name"] for g in result["app-1"]["groups"]]
        assert group_names == ["group_b"]

    def test_remove_group_with_other_selector_keeps_recording_rules(self):
        config = """
            remove:
              - where:
                  group: group_a
                  alert: LowThroughput
            """
        result = _apply(config)

        group = next(g for g in result["app-1"]["groups"] if g["name"] == "group_a")
        rule_names = [r.get("alert") or r.get("record") for r in group["rules"]]
        # Only the matching alerting rule is removed; the rest survives.
        assert rule_names == ["HighLatency", "job:latency:mean5m"]

    def test_remove_by_alert_and_labels_combined(self):
        config_matching = """
            remove:
              - where:
                  alert: HighLatency
                  labels:
                    severity: critical
            """
        result = _apply(config_matching)
        assert "HighLatency" not in str(result)

        # Same alert but non-matching label value: nothing removed.
        config_not_matching = """
            remove:
              - where:
                  alert: HighLatency
                  labels:
                    severity: warning
            """
        result = _apply(config_not_matching)
        assert "HighLatency" in str(result)

    def test_remove_by_group_and_labels_combined(self):
        config = """
            remove:
              - where:
                  group: group_a
                  labels:
                    severity: warning
            """
        result = _apply(config)

        group = next(g for g in result["app-1"]["groups"] if g["name"] == "group_a")
        rule_names = [r.get("alert") or r.get("record") for r in group["rules"]]
        # Both the alerting rule and the recording rule carry severity=warning,
        # but only the alerting rule may be removed (group selector is combined).
        assert rule_names == ["HighLatency", "job:latency:mean5m"]

    def test_remove_by_annotations(self):
        config = """
            remove:
              - where:
                  annotations:
                    summary: latency is high
            """
        result = _apply(config)

        assert "HighLatency" not in str(result)
        assert "LowThroughput" in str(result)

    def test_remove_multiple_entries_are_ored(self):
        config = """
            remove:
              - where:
                  alert: HighLatency
              - where:
                  alert: OtherAlert
            """
        result = _apply(config)

        assert "HighLatency" not in str(result)
        assert "OtherAlert" not in str(result)
        assert "LowThroughput" in str(result)
        assert "HostDown" in str(result)

    def test_remove_prunes_empty_groups_and_drops_empty_identifiers(self):
        config_pruning_group = """
            remove:
              - where:
                  alert: HostDown
            """
        result = _apply(config_pruning_group)
        # group_b became empty and was pruned; app-1 keeps group_a only.
        assert [g["name"] for g in result["app-1"]["groups"]] == ["group_a"]
        assert "app-2" in result

        config_dropping_identifier = """
            remove:
              - where:
                  alert: OtherAlert
            """
        result = _apply(config_dropping_identifier)
        # app-2's only group became empty, so app-2 was dropped entirely.
        assert "app-2" not in result
        assert "app-1" in result

    def test_remove_preserves_recording_rules_when_group_not_sole_selector(self):
        config = """
            remove:
              - where:
                  labels:
                    severity: warning
            """
        result = _apply(config)

        record = _find_rule(result, "app-1", "group_a", "job:latency:mean5m", by_record=True)
        assert record["expr"] == "avg(latency)"


class TestPatch:
    def test_patch_updates_for(self):
        config = """
            patch:
              - where:
                  alert: HighLatency
                set:
                  for: 30m
            """
        result = _apply(config)

        assert _find_rule(result, "app-1", "group_a", "HighLatency")["for"] == "30m"
        # Untouched rule keeps its original value.
        assert _find_rule(result, "app-1", "group_a", "LowThroughput")["for"] == "5m"

    def test_patch_replaces_alert_name(self):
        config = """
            patch:
              - where:
                  alert: HighLatency
                set:
                  alert: RenamedLatency
            """
        result = _apply(config)

        renamed = _find_rule(result, "app-1", "group_a", "RenamedLatency")
        assert renamed["expr"] == "latency > 100"

    def test_patch_replaces_expr(self):
        config = """
            patch:
              - where:
                  alert: HostDown
                set:
                  expr: up == 0
            """
        result = _apply(config)

        assert _find_rule(result, "app-1", "group_b", "HostDown")["expr"] == "up == 0"

    def test_patch_merges_labels(self):
        config = """
            patch:
              - where:
                  alert: HighLatency
                set:
                  labels:
                    severity: page
                    extra: added
            """
        result = _apply(config)

        labels = _find_rule(result, "app-1", "group_a", "HighLatency")["labels"]
        # existing key overwritten, new key added, other keys untouched
        assert labels["severity"] == "page"
        assert labels["extra"] == "added"
        assert labels["juju_application"] == "app-1"

    def test_patch_merges_annotations(self):
        config = """
            patch:
              - where:
                  alert: HighLatency
                set:
                  annotations:
                    summary: new summary
                    description: new description
            """
        result = _apply(config)

        annotations = _find_rule(result, "app-1", "group_a", "HighLatency")["annotations"]
        assert annotations["summary"] == "new summary"
        assert annotations["description"] == "new description"

    def test_patch_skips_recording_rules(self):
        config = """
            patch:
              - where:
                  group: group_a
                set:
                  expr: hacked
            """
        result = _apply(config)

        record = _find_rule(result, "app-1", "group_a", "job:latency:mean5m", by_record=True)
        assert record["expr"] == "avg(latency)"
        # Alerting rules in the same group were patched.
        assert _find_rule(result, "app-1", "group_a", "HighLatency")["expr"] == "hacked"

    def test_patch_matches_on_labels(self):
        config = """
            patch:
              - where:
                  labels:
                    severity: warning
                set:
                  labels:
                    severity: critical
            """
        result = _apply(config)

        assert (
            _find_rule(result, "app-1", "group_a", "LowThroughput")["labels"]["severity"]
            == "critical"
        )
        # The recording rule also has severity=warning but must not be patched.
        record = _find_rule(result, "app-1", "group_a", "job:latency:mean5m", by_record=True)
        assert record["labels"]["severity"] == "warning"
        # The alert in the other app is unaffected.
        assert _find_rule(result, "app-2", "group_c", "OtherAlert")["expr"] == "x > 0"


class TestApplySemantics:
    def test_input_is_not_mutated(self):
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
        sample = _sample_alerts()
        snapshot = copy.deepcopy(sample)
        AlertRulesCustomization.from_yaml(config).apply(sample)
        assert sample == snapshot

    def test_order_of_operations_is_remove_then_patch(self):
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
            """
        relation_alerts = {
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
        result = AlertRulesCustomization.from_yaml(config).apply(relation_alerts)

        rules = result["app"]["groups"][0]["rules"]
        # Removed despite a patch entry targeting it; patch applied to the survivor.
        assert [r["alert"] for r in rules] == ["Survivor"]
        assert rules[0]["for"] == "2m"

    def test_apply_is_reusable_across_inputs(self):
        config = """
            remove:
              - where:
                  alert: HostDown
            """
        customization = AlertRulesCustomization.from_yaml(config)

        result_1 = customization.apply(_sample_alerts())
        assert "HostDown" not in str(result_1["app-1"])
        assert "app-2" in result_1

        other_relation_alerts = {
            "other": {
                "groups": [{"name": "g", "rules": [{"alert": "HostDown", "expr": "up < 1"}]}]
            }
        }
        result_2 = customization.apply(other_relation_alerts)
        assert result_2 == {}

        # And the first input's result is unchanged by the second call.
        assert "app-1" in result_1
