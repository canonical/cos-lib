# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""pytest-bdd step definitions for patch scenarios.

Feature file: tests/features/patch.feature
"""

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
