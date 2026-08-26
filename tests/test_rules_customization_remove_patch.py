# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""pytest-bdd step definitions for remove-patch interaction scenarios.

Feature file: tests/features/remove_patch.feature
"""

import copy

from conftest import _sample_alerts
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


# ---------------------------------------------------------------------------
# Plain pytest tests — edge cases for remove + patch interaction
# ---------------------------------------------------------------------------


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

        assert "app-1" in result_1
