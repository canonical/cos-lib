# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""pytest-bdd step definitions for patch scenarios.

Feature file: tests/features/patch.feature
"""

from conftest import _apply
from conftest import find_rule as _find_rule
from pytest_bdd import scenarios, when

from cosl.rules_customization import AlertRulesCustomization

scenarios("features/patch.feature")


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
# Plain pytest tests — edge cases for patch
# ---------------------------------------------------------------------------


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
        record = _find_rule(result, "app-1", "group_a", "job:latency:mean5m", by_record=True)
        assert record["labels"]["severity"] == "warning"
        assert _find_rule(result, "app-2", "group_c", "OtherAlert")["expr"] == "x > 0"
