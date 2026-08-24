# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import copy
import unittest

from cosl.rules_customization import (
    CUSTOM_ALERT_RULES_KEY,
    AlertRulesCustomization,
    AlertRulesCustomizationError,
)


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


class TestFromYamlValidation(unittest.TestCase):
    def test_invalid_yaml_raises(self):
        with self.assertRaises(AlertRulesCustomizationError):
            AlertRulesCustomization.from_yaml("remove: [unclosed")

    def test_non_mapping_top_level_raises(self):
        for config in ("- a\n- b", "42", '"just a string"'):
            with self.assertRaises(AlertRulesCustomizationError):
                AlertRulesCustomization.from_yaml(config)

    def test_unknown_top_level_key_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "top-level"):
            AlertRulesCustomization.from_yaml("""
                remove:
                  - where:
                      alert: Foo
                destroy:
                  - where:
                      alert: Foo
                """)

    def test_remove_missing_where_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "remove"):
            AlertRulesCustomization.from_yaml("remove:\n  - alert: Foo")

    def test_remove_empty_where_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "'where' must not be empty"):
            AlertRulesCustomization.from_yaml("""
                remove:
                  - where: {}
                """)

    def test_remove_unknown_where_key_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "'where' keys"):
            AlertRulesCustomization.from_yaml("""
                remove:
                  - where:
                      expr: up < 1
                """)

    def test_patch_missing_where_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "patch"):
            AlertRulesCustomization.from_yaml("""
                patch:
                  - set:
                      for: 5m
                """)

    def test_patch_missing_set_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "patch"):
            AlertRulesCustomization.from_yaml("""
                patch:
                  - where:
                      alert: Foo
                """)

    def test_patch_empty_where_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "'where' must not be empty"):
            AlertRulesCustomization.from_yaml("""
                patch:
                  - where: {}
                    set:
                      for: 5m
                """)

    def test_patch_unknown_where_key_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "'where' keys"):
            AlertRulesCustomization.from_yaml("""
                patch:
                  - where:
                      record: some:record
                    set:
                      expr: up
                """)

    def test_patch_unknown_set_key_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "'set' keys"):
            AlertRulesCustomization.from_yaml("""
                patch:
                  - where:
                      alert: Foo
                    set:
                      duration: 5m
                """)

    def test_add_without_groups_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "'add'"):
            AlertRulesCustomization.from_yaml("""
                add:
                  rules:
                    - alert: Foo
                      expr: up
                """)

    def test_add_groups_not_a_list_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "'add.groups' must be a list"):
            AlertRulesCustomization.from_yaml("""
                add:
                  groups:
                    name: my-group
                    rules: []
                """)

    def test_add_group_missing_name_or_rules_raises(self):
        for group in ("rules: []", "name: my-group"):
            with self.assertRaisesRegex(AlertRulesCustomizationError, "add.groups"):
                AlertRulesCustomization.from_yaml(f"add:\n  groups:\n    - {group}")

    def test_add_malformed_values_raise(self):
        cases = {
            "add not a mapping": "add: groups",
            "group not a mapping": "add:\n  groups:\n    - just-a-string",
            "name not a string": ("add:\n  groups:\n    - name: [1]\n      rules: []"),
            "rules not a list": ("add:\n  groups:\n    - name: my-group\n      rules: nope"),
        }
        for case, config in cases.items():
            with self.subTest(case):
                with self.assertRaises(AlertRulesCustomizationError):
                    AlertRulesCustomization.from_yaml(config)

    def test_operations_not_a_list_raises(self):
        for key in ("remove", "patch"):
            with self.assertRaisesRegex(AlertRulesCustomizationError, f"'{key}'"):
                AlertRulesCustomization.from_yaml(f"{key}: not-a-list")

    def test_malformed_operation_entries_raise(self):
        cases = {
            "where not a mapping": "remove:\n  - where: nope",
            "where.alert not a string": ("remove:\n  - where:\n      alert: [1, 2]"),
            "where.labels not a mapping": ("remove:\n  - where:\n      labels: severity"),
            "set not a mapping": "patch:\n  - where:\n      alert: Foo\n    set: nope",
            "set.expr not a string": (
                "patch:\n  - where:\n      alert: Foo\n    set:\n      expr: {a: b}"
            ),
            "set.labels not a mapping": (
                "patch:\n  - where:\n      alert: Foo\n    set:\n      labels: x"
            ),
            "remove entry not a mapping": "remove:\n  - just-a-string",
            "patch entry not a mapping": "patch:\n  - just-a-string",
        }
        for case, config in cases.items():
            with self.subTest(case):
                with self.assertRaises(AlertRulesCustomizationError):
                    AlertRulesCustomization.from_yaml(config)


class TestNoOpConfigs(unittest.TestCase):
    def _assert_noop(self, config_string):
        sample = _sample_alerts()
        result = AlertRulesCustomization.from_yaml(config_string).apply(sample)
        self.assertEqual(result, sample)

    def test_empty_config_is_noop(self):
        self._assert_noop("")

    def test_whitespace_config_is_noop(self):
        self._assert_noop("   \n\t  ")

    def test_none_parsing_config_is_noop(self):
        # yaml.safe_load of these strings returns None or empty structures.
        self._assert_noop("~")
        self._assert_noop("# just a comment")
        self._assert_noop("{}")

    def test_zero_match_remove_is_noop(self):
        self._assert_noop("""
            remove:
              - where:
                  alert: NoSuchAlert
              - where:
                  labels:
                    nope: nothing
            """)

    def test_zero_match_patch_is_noop(self):
        self._assert_noop("""
            patch:
              - where:
                  alert: NoSuchAlert
                set:
                  for: 1m
            """)


class TestRemove(unittest.TestCase):
    def test_remove_by_alert_name(self):
        result = AlertRulesCustomization.from_yaml("""
            remove:
              - where:
                  alert: LowThroughput
            """).apply(_sample_alerts())

        group_names = [g["name"] for g in result["app-1"]["groups"]]
        self.assertEqual(group_names, ["group_a", "group_b"])
        rule_names = [r.get("alert") for r in result["app-1"]["groups"][0]["rules"]]
        self.assertEqual(rule_names, ["HighLatency", None])  # record remains

    def test_remove_by_group_only_drops_entire_group_including_recording_rules(self):
        result = AlertRulesCustomization.from_yaml("""
            remove:
              - where:
                  group: group_a
            """).apply(_sample_alerts())

        group_names = [g["name"] for g in result["app-1"]["groups"]]
        self.assertEqual(group_names, ["group_b"])

    def test_remove_group_with_other_selector_keeps_recording_rules(self):
        result = AlertRulesCustomization.from_yaml("""
            remove:
              - where:
                  group: group_a
                  alert: LowThroughput
            """).apply(_sample_alerts())

        group = next(g for g in result["app-1"]["groups"] if g["name"] == "group_a")
        rule_names = [r.get("alert") or r.get("record") for r in group["rules"]]
        # Only the matching alerting rule is removed; the rest survives.
        self.assertEqual(rule_names, ["HighLatency", "job:latency:mean5m"])

    def test_remove_by_alert_and_labels_combined(self):
        result = AlertRulesCustomization.from_yaml("""
            remove:
              - where:
                  alert: HighLatency
                  labels:
                    severity: critical
            """).apply(_sample_alerts())
        self.assertNotIn("HighLatency", str(result))

        # Same alert but non-matching label value: nothing removed.
        result = AlertRulesCustomization.from_yaml("""
            remove:
              - where:
                  alert: HighLatency
                  labels:
                    severity: warning
            """).apply(_sample_alerts())
        self.assertIn("HighLatency", str(result))

    def test_remove_by_group_and_labels_combined(self):
        result = AlertRulesCustomization.from_yaml("""
            remove:
              - where:
                  group: group_a
                  labels:
                    severity: warning
            """).apply(_sample_alerts())

        group = next(g for g in result["app-1"]["groups"] if g["name"] == "group_a")
        rule_names = [r.get("alert") or r.get("record") for r in group["rules"]]
        # Both the alerting rule and the recording rule carry severity=warning,
        # but only the alerting rule may be removed (group selector is combined).
        self.assertEqual(rule_names, ["HighLatency", "job:latency:mean5m"])

    def test_remove_by_annotations(self):
        result = AlertRulesCustomization.from_yaml("""
            remove:
              - where:
                  annotations:
                    summary: latency is high
            """).apply(_sample_alerts())
        self.assertNotIn("HighLatency", str(result))
        self.assertIn("LowThroughput", str(result))

    def test_remove_multiple_entries_are_ored(self):
        result = AlertRulesCustomization.from_yaml("""
            remove:
              - where:
                  alert: HighLatency
              - where:
                  alert: OtherAlert
            """).apply(_sample_alerts())
        self.assertNotIn("HighLatency", str(result))
        self.assertNotIn("OtherAlert", str(result))
        self.assertIn("LowThroughput", str(result))
        self.assertIn("HostDown", str(result))

    def test_remove_prunes_empty_groups_and_drops_empty_identifiers(self):
        result = AlertRulesCustomization.from_yaml("""
            remove:
              - where:
                  alert: HostDown
            """).apply(_sample_alerts())
        # group_b became empty and was pruned; app-1 keeps group_a only.
        self.assertEqual([g["name"] for g in result["app-1"]["groups"]], ["group_a"])
        self.assertIn("app-2", result)

        result = AlertRulesCustomization.from_yaml("""
            remove:
              - where:
                  alert: OtherAlert
            """).apply(_sample_alerts())
        # app-2's only group became empty, so app-2 was dropped entirely.
        self.assertNotIn("app-2", result)
        self.assertIn("app-1", result)

    def test_remove_preserves_recording_rules_when_group_not_sole_selector(self):
        result = AlertRulesCustomization.from_yaml("""
            remove:
              - where:
                  labels:
                    severity: warning
            """).apply(_sample_alerts())
        record = _find_rule(result, "app-1", "group_a", "job:latency:mean5m", by_record=True)
        self.assertEqual(record["expr"], "avg(latency)")


class TestPatch(unittest.TestCase):
    def test_patch_updates_for(self):
        result = AlertRulesCustomization.from_yaml("""
            patch:
              - where:
                  alert: HighLatency
                set:
                  for: 30m
            """).apply(_sample_alerts())
        self.assertEqual(_find_rule(result, "app-1", "group_a", "HighLatency")["for"], "30m")
        # Untouched rule keeps its original value.
        self.assertEqual(_find_rule(result, "app-1", "group_a", "LowThroughput")["for"], "5m")

    def test_patch_replaces_alert_name(self):
        result = AlertRulesCustomization.from_yaml("""
            patch:
              - where:
                  alert: HighLatency
                set:
                  alert: RenamedLatency
            """).apply(_sample_alerts())
        renamed = _find_rule(result, "app-1", "group_a", "RenamedLatency")
        self.assertEqual(renamed["expr"], "latency > 100")

    def test_patch_replaces_expr(self):
        result = AlertRulesCustomization.from_yaml("""
            patch:
              - where:
                  alert: HostDown
                set:
                  expr: up == 0
            """).apply(_sample_alerts())
        self.assertEqual(_find_rule(result, "app-1", "group_b", "HostDown")["expr"], "up == 0")

    def test_patch_merges_labels(self):
        result = AlertRulesCustomization.from_yaml("""
            patch:
              - where:
                  alert: HighLatency
                set:
                  labels:
                    severity: page
                    extra: added
            """).apply(_sample_alerts())
        labels = _find_rule(result, "app-1", "group_a", "HighLatency")["labels"]
        # existing key overwritten, new key added, other keys untouched
        self.assertEqual(labels["severity"], "page")
        self.assertEqual(labels["extra"], "added")
        self.assertEqual(labels["juju_application"], "app-1")

    def test_patch_merges_annotations(self):
        result = AlertRulesCustomization.from_yaml("""
            patch:
              - where:
                  alert: HighLatency
                set:
                  annotations:
                    summary: new summary
                    description: new description
            """).apply(_sample_alerts())
        annotations = _find_rule(result, "app-1", "group_a", "HighLatency")["annotations"]
        self.assertEqual(annotations["summary"], "new summary")
        self.assertEqual(annotations["description"], "new description")

    def test_patch_skips_recording_rules(self):
        result = AlertRulesCustomization.from_yaml("""
            patch:
              - where:
                  group: group_a
                set:
                  expr: hacked
            """).apply(_sample_alerts())
        record = _find_rule(result, "app-1", "group_a", "job:latency:mean5m", by_record=True)
        self.assertEqual(record["expr"], "avg(latency)")
        # Alerting rules in the same group were patched.
        self.assertEqual(_find_rule(result, "app-1", "group_a", "HighLatency")["expr"], "hacked")

    def test_patch_matches_on_labels(self):
        result = AlertRulesCustomization.from_yaml("""
            patch:
              - where:
                  labels:
                    severity: warning
                set:
                  labels:
                    severity: critical
            """).apply(_sample_alerts())
        self.assertEqual(
            _find_rule(result, "app-1", "group_a", "LowThroughput")["labels"]["severity"],
            "critical",
        )
        # The recording rule also has severity=warning but must not be patched.
        record = _find_rule(result, "app-1", "group_a", "job:latency:mean5m", by_record=True)
        self.assertEqual(record["labels"]["severity"], "warning")
        # The alert in the other app is unaffected.
        self.assertEqual(_find_rule(result, "app-2", "group_c", "OtherAlert")["expr"], "x > 0")


class TestAdd(unittest.TestCase):
    _config = """
        add:
          groups:
            - name: my-custom-alerts
              rules:
                - alert: MyAlert
                  expr: up{juju_model="prod"} == 0
                  for: 5m
        """

    def test_add_inserts_groups_under_fixed_key(self):
        sample = _sample_alerts()
        result = AlertRulesCustomization.from_yaml(self._config).apply(sample)

        custom = result[CUSTOM_ALERT_RULES_KEY]
        self.assertEqual(custom["groups"][0]["name"], "my-custom-alerts")
        self.assertEqual(custom["groups"][0]["rules"][0]["alert"], "MyAlert")
        # Existing identifiers are left untouched.
        self.assertEqual(set(result), set(sample) | {CUSTOM_ALERT_RULES_KEY})

    def test_added_rules_receive_no_topology_injection(self):
        result = AlertRulesCustomization.from_yaml(self._config).apply(_sample_alerts())
        rule = result[CUSTOM_ALERT_RULES_KEY]["groups"][0]["rules"][0]
        self.assertEqual(rule["expr"], 'up{juju_model="prod"} == 0')
        self.assertNotIn("labels", rule)

    def test_added_rules_are_deep_copied(self):
        customization = AlertRulesCustomization.from_yaml(self._config)
        result = customization.apply({})
        result[CUSTOM_ALERT_RULES_KEY]["groups"][0]["rules"][0]["alert"] = "Mangled"
        # A subsequent apply() must not be affected by mutations of a previous output.
        fresh = customization.apply({})[CUSTOM_ALERT_RULES_KEY]["groups"][0]["rules"][0]
        self.assertEqual(fresh["alert"], "MyAlert")


class TestApplySemantics(unittest.TestCase):
    def test_input_is_not_mutated(self):
        sample = _sample_alerts()
        snapshot = copy.deepcopy(sample)
        AlertRulesCustomization.from_yaml("""
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
            add:
              groups:
                - name: added
                  rules:
                    - alert: Added
                      expr: up
            """).apply(sample)
        self.assertEqual(sample, snapshot)

    def test_order_of_operations_is_remove_then_patch_then_add(self):
        result = AlertRulesCustomization.from_yaml("""
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
            """).apply(
            {
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
        )
        rules = result["app"]["groups"][0]["rules"]
        # Removed despite a patch entry targeting it; patch applied to the survivor;
        # the added rule lands under the fixed key, untouched by remove/patch.
        self.assertEqual([r["alert"] for r in rules], ["Survivor"])
        self.assertEqual(rules[0]["for"], "2m")
        added = result[CUSTOM_ALERT_RULES_KEY]["groups"][0]["rules"][0]
        self.assertEqual(added["alert"], "GoneForever")
        self.assertNotIn("for", added)  # the patch entry did not leak into the added rule

    def test_apply_is_reusable_across_inputs(self):
        customization = AlertRulesCustomization.from_yaml("""
            remove:
              - where:
                  alert: HostDown
            """)
        result_1 = customization.apply(_sample_alerts())
        self.assertNotIn("HostDown", str(result_1["app-1"]))
        self.assertIn("app-2", result_1)

        result_2 = customization.apply(
            {
                "other": {
                    "groups": [{"name": "g", "rules": [{"alert": "HostDown", "expr": "up < 1"}]}]
                }
            }
        )
        self.assertEqual(result_2, {})

        # And the first input's result is unchanged by the second call.
        self.assertIn("app-1", result_1)


if __name__ == "__main__":
    unittest.main()
