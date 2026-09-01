# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""pytest-bdd step definitions for remove-patch interaction scenarios.

Feature file: tests/features/remove_patch.feature
"""


from pytest_bdd import scenarios, when

from cosl.rules_customization import AlertRulesCustomization

scenarios("features/remove_patch.feature")


# ---------------------------------------------------------------------------
# When — Apply semantics (remove + patch interaction)
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
    ctx["result"] = ctx["alerts"]


@when('I apply a customization that removes "GoneForever" and patches "Survivor" for to "2m"')
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
