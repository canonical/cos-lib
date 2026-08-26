# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""pytest-bdd step definitions for remove scenarios.

Feature file: tests/features/remove.feature
"""

from pytest_bdd import scenarios, when

from cosl.rules_customization import AlertRulesCustomization

scenarios("features/remove.feature")


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
# Plain pytest tests — edge cases for remove
# ---------------------------------------------------------------------------


def find_rule(alerts, identifier, group_name, rule_name, *, by_record=False):
    """Fetch a single rule from an alerts dict for assertions."""
    key = "record" if by_record else "alert"
    groups = alerts[identifier]["groups"]
    group = next(g for g in groups if g["name"] == group_name)
    return next(rule for rule in group["rules"] if rule.get(key) == rule_name)


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
        assert rule_names == ["HighLatency", None]

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
        assert [g["name"] for g in result["app-1"]["groups"]] == ["group_a"]
        assert "app-2" in result

        config_dropping_identifier = """
            remove:
              - where:
                  alert: OtherAlert
            """
        result = _apply(config_dropping_identifier)
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

        record = find_rule(result, "app-1", "group_a", "job:latency:mean5m", by_record=True)
        assert record["expr"] == "avg(latency)"
