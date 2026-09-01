# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""pytest-bdd step definitions for remove scenarios.

Feature file: tests/features/remove.feature
"""

from conftest import _load_sample_alerts
from conftest import find_rule as _find_rule
from pytest_bdd import scenarios, when

from cosl.rules_customization import AlertRulesCustomization

scenarios("features/remove.feature")


def _apply(config):
    return AlertRulesCustomization.from_yaml(config).apply(_load_sample_alerts())


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


class TestRemove:
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
