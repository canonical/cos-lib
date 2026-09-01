# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Schema validation tests for AlertRulesCustomization.from_yaml().

Covers invalid YAML, unknown top-level keys, malformed operation entries, and
no-op configs. Behavioural tests (remove/patch/add/apply semantics) live in
test_rules_customization.py backed by tests/features/alert_rule_customization.feature.
"""

import unittest

from cosl.rules_customization import (
    AlertRulesCustomization,
    AlertRulesCustomizationError,
)


def _sample_alerts():
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
                    ],
                },
            ]
        }
    }


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
        with self.assertRaisesRegex(
            AlertRulesCustomizationError, "Extra inputs are not permitted"
        ):
            AlertRulesCustomization.from_yaml(config)

    def test_remove_missing_where_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "remove"):
            AlertRulesCustomization.from_yaml("remove:\n  - alert: Foo")

    def test_remove_empty_where_raises(self):
        with self.assertRaisesRegex(
            AlertRulesCustomizationError, "'where' must have at least one of"
        ):
            AlertRulesCustomization.from_yaml("remove:\n  - where: {}")

    def test_remove_unknown_where_key_raises(self):
        with self.assertRaisesRegex(
            AlertRulesCustomizationError, "Extra inputs are not permitted"
        ):
            AlertRulesCustomization.from_yaml("remove:\n  - where:\n      expr: up < 1")

    def test_patch_missing_where_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "patch"):
            AlertRulesCustomization.from_yaml("patch:\n  - set:\n      for: 5m")

    def test_patch_missing_set_raises(self):
        with self.assertRaisesRegex(AlertRulesCustomizationError, "patch"):
            AlertRulesCustomization.from_yaml("patch:\n  - where:\n      alert: Foo")

    def test_patch_empty_where_raises(self):
        with self.assertRaisesRegex(
            AlertRulesCustomizationError, "'where' must have at least one of"
        ):
            AlertRulesCustomization.from_yaml("patch:\n  - where: {}\n    set:\n      for: 5m")

    def test_patch_unknown_where_key_raises(self):
        with self.assertRaisesRegex(
            AlertRulesCustomizationError, "Extra inputs are not permitted"
        ):
            AlertRulesCustomization.from_yaml(
                "patch:\n  - where:\n      record: some:record\n    set:\n      expr: up"
            )

    def test_patch_unknown_set_key_raises(self):
        with self.assertRaisesRegex(
            AlertRulesCustomizationError, "Extra inputs are not permitted"
        ):
            AlertRulesCustomization.from_yaml(
                "patch:\n  - where:\n      alert: Foo\n    set:\n      duration: 5m"
            )

    def test_operations_not_a_list_raises(self):
        for key in ("remove", "patch"):
            with self.assertRaisesRegex(
                AlertRulesCustomizationError, "Input should be a valid list"
            ):
                AlertRulesCustomization.from_yaml(f"{key}: not-a-list")

    def test_malformed_operation_entries_raise(self):
        invalid_cases = [
            # where must be a mapping, not a scalar
            ("remove:\n  - where: nope",),
            # where.alert must be a string, not a list
            ("remove:\n  - where:\n      alert: [1, 2]",),
            # where.labels must be a mapping, not a scalar
            ("remove:\n  - where:\n      labels: severity",),
            # set must be a mapping, not a scalar
            ("patch:\n  - where:\n      alert: Foo\n    set: nope",),
            # set.expr must be a string, not a mapping
            ("patch:\n  - where:\n      alert: Foo\n    set:\n      expr: {a: b}",),
            # set.labels must be a mapping, not a scalar
            ("patch:\n  - where:\n      alert: Foo\n    set:\n      labels: x",),
            # each remove entry must be a mapping (dict), not a string
            ("remove:\n  - just-a-string",),
            # each patch entry must be a mapping (dict), not a string
            ("patch:\n  - just-a-string",),
        ]
        for config in invalid_cases:
            with self.subTest(config):
                with self.assertRaises(AlertRulesCustomizationError):
                    AlertRulesCustomization.from_yaml(config[0])


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


if __name__ == "__main__":
    unittest.main()
