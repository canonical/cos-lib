# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import copy
import unittest

from cosl.rules_customization import (
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
        config = """
            remove:
              - where:
                  alert: Foo
            destroy:
              - where:
                  alert: Foo
            """
        with self.assertRaises(AlertRulesCustomizationError):
            AlertRulesCustomization.from_yaml(config)

    def test_remove_missing_where_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "remove"):
            AlertRulesCustomization.from_yaml("remove:\n  - alert: Foo")

    def test_remove_empty_where_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "'where' must not be empty"):
            AlertRulesCustomization.from_yaml("remove:\n  - where: {}")

    def test_remove_unknown_where_key_raises(self):
        with self.assertRaises(AlertRulesCustomizationError):
            AlertRulesCustomization.from_yaml("remove:\n  - where:\n      expr: up < 1")

    def test_patch_missing_where_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "patch"):
            AlertRulesCustomization.from_yaml("patch:\n  - set:\n      for: 5m")

    def test_patch_missing_set_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "patch"):
            AlertRulesCustomization.from_yaml("patch:\n  - where:\n      alert: Foo")

    def test_patch_empty_where_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "'where' must not be empty"):
            AlertRulesCustomization.from_yaml("patch:\n  - where: {}\n    set:\n      for: 5m")

    def test_patch_unknown_where_key_raises(self):
        with self.assertRaises(AlertRulesCustomizationError):
            AlertRulesCustomization.from_yaml(
                "patch:\n  - where:\n      record: some:record\n    set:\n      expr: up"
            )

    def test_patch_unknown_set_key_raises(self):
        with self.assertRaises(AlertRulesCustomizationError):
            AlertRulesCustomization.from_yaml(
                "patch:\n  - where:\n      alert: Foo\n    set:\n      duration: 5m"
            )

    def test_operations_not_a_list_raises(self):
        for key in ("remove", "patch"):
            with self.assertRaises(AlertRulesCustomizationError):
                AlertRulesCustomization.from_yaml(f"{key}: not-a-list")

    def test_malformed_operation_entries_raise(self):
        cases = {
            "where not a mapping": "remove:\n  - where: nope",
            "where.alert not a string": "remove:\n  - where:\n      alert: [1, 2]",
            "where.labels not a mapping": "remove:\n  - where:\n      labels: severity",
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
        config = """
            remove:
              - where:
                  alert: NoSuchAlert
              - where:
                  labels:
                    nope: nothing
            """
        self._assert_noop(config)

    def test_zero_match_patch_is_noop(self):
        config = """
            patch:
              - where:
                  alert: NoSuchAlert
                set:
                  for: 1m
            """
        self._assert_noop(config)


class TestRemove(unittest.TestCase):
    def _apply(self, config):
        return AlertRulesCustomization.from_yaml(config).apply(_sample_alerts())

    def test_remove_by_alert_name(self):
        config = """
            remove:
              - where:
                  alert: LowThroughput
            """
        result = self._apply(config)

        group_names = [g["name"] for g in result["app-1"]["groups"]]
        self.assertEqual(group_names, ["group_a", "group_b"])
        rule_names = [r.get("alert") for r in result["app-1"]["groups"][0]["rules"]]
        self.assertEqual(rule_names, ["HighLatency", None])  # record remains

    def test_remove_by_group_only_drops_entire_group_including_recording_rules(self):
        config = """
            remove:
              - where:
                  group: group_a
            """
        result = self._apply(config)

        group_names = [g["name"] for g in result["app-1"]["groups"]]
        self.assertEqual(group_names, ["group_b"])

    def test_remove_group_with_other_selector_keeps_recording_rules(self):
        config = """
            remove:
              - where:
                  group: group_a
                  alert: LowThroughput
            """
        result = self._apply(config)

        group = next(g for g in result["app-1"]["groups"] if g["name"] == "group_a")
        rule_names = [r.get("alert") or r.get("record") for r in group["rules"]]
        # Only the matching alerting rule is removed; the rest survives.
        self.assertEqual(rule_names, ["HighLatency", "job:latency:mean5m"])

    def test_remove_by_alert_and_labels_combined(self):
        config_matching = """
            remove:
              - where:
                  alert: HighLatency
                  labels:
                    severity: critical
            """
        result = self._apply(config_matching)
        self.assertNotIn("HighLatency", str(result))

        # Same alert but non-matching label value: nothing removed.
        config_not_matching = """
            remove:
              - where:
                  alert: HighLatency
                  labels:
                    severity: warning
            """
        result = self._apply(config_not_matching)
        self.assertIn("HighLatency", str(result))

    def test_remove_by_group_and_labels_combined(self):
        config = """
            remove:
              - where:
                  group: group_a
                  labels:
                    severity: warning
            """
        result = self._apply(config)

        group = next(g for g in result["app-1"]["groups"] if g["name"] == "group_a")
        rule_names = [r.get("alert") or r.get("record") for r in group["rules"]]
        # Both the alerting rule and the recording rule carry severity=warning,
        # but only the alerting rule may be removed (group selector is combined).
        self.assertEqual(rule_names, ["HighLatency", "job:latency:mean5m"])

    def test_remove_by_annotations(self):
        config = """
            remove:
              - where:
                  annotations:
                    summary: latency is high
            """
        result = self._apply(config)

        self.assertNotIn("HighLatency", str(result))
        self.assertIn("LowThroughput", str(result))

    def test_remove_multiple_entries_are_ored(self):
        config = """
            remove:
              - where:
                  alert: HighLatency
              - where:
                  alert: OtherAlert
            """
        result = self._apply(config)

        self.assertNotIn("HighLatency", str(result))
        self.assertNotIn("OtherAlert", str(result))
        self.assertIn("LowThroughput", str(result))
        self.assertIn("HostDown", str(result))

    def test_remove_prunes_empty_groups_and_drops_empty_identifiers(self):
        config_pruning_group = """
            remove:
              - where:
                  alert: HostDown
            """
        result = self._apply(config_pruning_group)
        # group_b became empty and was pruned; app-1 keeps group_a only.
        self.assertEqual([g["name"] for g in result["app-1"]["groups"]], ["group_a"])
        self.assertIn("app-2", result)

        config_dropping_identifier = """
            remove:
              - where:
                  alert: OtherAlert
            """
        result = self._apply(config_dropping_identifier)
        # app-2's only group became empty, so app-2 was dropped entirely.
        self.assertNotIn("app-2", result)
        self.assertIn("app-1", result)

    def test_remove_preserves_recording_rules_when_group_not_sole_selector(self):
        config = """
            remove:
              - where:
                  labels:
                    severity: warning
            """
        result = self._apply(config)

        record = _find_rule(result, "app-1", "group_a", "job:latency:mean5m", by_record=True)
        self.assertEqual(record["expr"], "avg(latency)")


class TestPatch(unittest.TestCase):
    def _apply(self, config):
        return AlertRulesCustomization.from_yaml(config).apply(_sample_alerts())

    def test_patch_updates_for(self):
        config = """
            patch:
              - where:
                  alert: HighLatency
                set:
                  for: 30m
            """
        result = self._apply(config)

        self.assertEqual(_find_rule(result, "app-1", "group_a", "HighLatency")["for"], "30m")
        # Untouched rule keeps its original value.
        self.assertEqual(_find_rule(result, "app-1", "group_a", "LowThroughput")["for"], "5m")

    def test_patch_replaces_alert_name(self):
        config = """
            patch:
              - where:
                  alert: HighLatency
                set:
                  alert: RenamedLatency
            """
        result = self._apply(config)

        renamed = _find_rule(result, "app-1", "group_a", "RenamedLatency")
        self.assertEqual(renamed["expr"], "latency > 100")

    def test_patch_replaces_expr(self):
        config = """
            patch:
              - where:
                  alert: HostDown
                set:
                  expr: up == 0
            """
        result = self._apply(config)

        self.assertEqual(_find_rule(result, "app-1", "group_b", "HostDown")["expr"], "up == 0")

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
        result = self._apply(config)

        labels = _find_rule(result, "app-1", "group_a", "HighLatency")["labels"]
        # existing key overwritten, new key added, other keys untouched
        self.assertEqual(labels["severity"], "page")
        self.assertEqual(labels["extra"], "added")
        self.assertEqual(labels["juju_application"], "app-1")

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
        result = self._apply(config)

        annotations = _find_rule(result, "app-1", "group_a", "HighLatency")["annotations"]
        self.assertEqual(annotations["summary"], "new summary")
        self.assertEqual(annotations["description"], "new description")

    def test_patch_skips_recording_rules(self):
        config = """
            patch:
              - where:
                  group: group_a
                set:
                  expr: hacked
            """
        result = self._apply(config)

        record = _find_rule(result, "app-1", "group_a", "job:latency:mean5m", by_record=True)
        self.assertEqual(record["expr"], "avg(latency)")
        # Alerting rules in the same group were patched.
        self.assertEqual(_find_rule(result, "app-1", "group_a", "HighLatency")["expr"], "hacked")

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
        result = self._apply(config)

        self.assertEqual(
            _find_rule(result, "app-1", "group_a", "LowThroughput")["labels"]["severity"],
            "critical",
        )
        # The recording rule also has severity=warning but must not be patched.
        record = _find_rule(result, "app-1", "group_a", "job:latency:mean5m", by_record=True)
        self.assertEqual(record["labels"]["severity"], "warning")
        # The alert in the other app is unaffected.
        self.assertEqual(_find_rule(result, "app-2", "group_c", "OtherAlert")["expr"], "x > 0")


class TestApplySemantics(unittest.TestCase):
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
        self.assertEqual(sample, snapshot)

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
        self.assertEqual([r["alert"] for r in rules], ["Survivor"])
        self.assertEqual(rules[0]["for"], "2m")

    def test_apply_is_reusable_across_inputs(self):
        config = """
            remove:
              - where:
                  alert: HostDown
            """
        customization = AlertRulesCustomization.from_yaml(config)

        result_1 = customization.apply(_sample_alerts())
        self.assertNotIn("HostDown", str(result_1["app-1"]))
        self.assertIn("app-2", result_1)

        other_relation_alerts = {
            "other": {
                "groups": [{"name": "g", "rules": [{"alert": "HostDown", "expr": "up < 1"}]}]
            }
        }
        result_2 = customization.apply(other_relation_alerts)
        self.assertEqual(result_2, {})

        # And the first input's result is unchanged by the second call.
        self.assertIn("app-1", result_1)


if __name__ == "__main__":
    unittest.main()
