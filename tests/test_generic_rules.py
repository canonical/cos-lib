# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for GenericRules (add, add_path, validate, backward compatibility)."""

import unittest

from deepdiff import DeepDiff
from helpers import OFFICIAL_RULE, PROMETHEUS_RULES_DIR, SINGLE_ALERT_RULE, make_topology

from cosl.prometheus import PrometheusRuleBackend
from cosl.rules import GenericRules

# ===================================================================
# GenericRules – add
# ===================================================================


class TestGenericRulesAdd(unittest.TestCase):
    """Tests for GenericRules.add method."""

    def test_add_single_rule(self):
        """Adding a single rule creates one group."""
        rules = GenericRules(backend=PrometheusRuleBackend())
        rules.add(SINGLE_ALERT_RULE, group_name="mygroup")
        result = rules.as_dict()
        self.assertIn("groups", result)
        self.assertEqual(len(result["groups"]), 1)

    def test_add_official_rule(self):
        """Adding an official-format rule creates one group."""
        rules = GenericRules(backend=PrometheusRuleBackend())
        rules.add(OFFICIAL_RULE)
        result = rules.as_dict()
        self.assertEqual(len(result["groups"]), 1)

    def test_add_multiple_rules_accumulate(self):
        """Multiple add calls accumulate groups."""
        rules = GenericRules(backend=PrometheusRuleBackend())
        rules.add(SINGLE_ALERT_RULE, group_name="group1")
        rules.add(SINGLE_ALERT_RULE, group_name="group2")
        result = rules.as_dict()
        self.assertEqual(len(result["groups"]), 2)

    def test_add_with_topology(self):
        """Rules added with topology get juju labels injected."""
        topo = make_topology()
        rules = GenericRules(backend=PrometheusRuleBackend(), topology=topo)
        rules.add(SINGLE_ALERT_RULE, group_name="test")
        result = rules.as_dict()
        rule = result["groups"][0]["rules"][0]
        self.assertEqual(rule["labels"]["juju_model"], "mymodel")

    def test_as_dict_empty_when_no_rules_added(self):
        """as_dict returns empty dict when no rules have been added."""
        rules = GenericRules(backend=PrometheusRuleBackend())
        self.assertEqual(rules.as_dict(), {})

    def test_topology_set_on_backend_via_generic_rules(self):
        """Passing topology to GenericRules sets it on the backend."""
        topo = make_topology()
        backend = PrometheusRuleBackend()
        self.assertIsNone(backend.topology)
        GenericRules(backend=backend, topology=topo)
        self.assertEqual(backend.topology, topo)


# ===================================================================
# GenericRules – add_path
# ===================================================================


class TestGenericRulesAddPath(unittest.TestCase):
    """Tests for GenericRules.add_path with file and directory loading."""

    def setUp(self):
        self.rules_dir = PROMETHEUS_RULES_DIR
        self.topology = make_topology()

    def test_add_path_single_file(self):
        """Loading a single file creates one group."""
        rules = GenericRules(backend=PrometheusRuleBackend(), topology=self.topology)
        rules.add_path(self.rules_dir / "cpu_overuse.rule")
        result = rules.as_dict()
        self.assertIn("groups", result)
        self.assertEqual(len(result["groups"]), 1)

    def test_add_path_directory_non_recursive(self):
        """Non-recursive directory scan finds only top-level files."""
        rules = GenericRules(backend=PrometheusRuleBackend(), topology=self.topology)
        rules.add_path(self.rules_dir)
        result = rules.as_dict()
        # Should find top-level .rule files but not nested/
        top_level_rules = [
            f for f in self.rules_dir.iterdir() if f.is_file() and f.suffix == ".rule"
        ]
        self.assertEqual(len(result["groups"]), len(top_level_rules))

    def test_add_path_directory_recursive(self):
        """Recursive directory scan finds nested files."""
        rules = GenericRules(backend=PrometheusRuleBackend(), topology=self.topology)
        rules.add_path(self.rules_dir, recursive=True)
        result = rules.as_dict()
        all_rules = list(self.rules_dir.rglob("*.rule"))
        self.assertEqual(len(result["groups"]), len(all_rules))

    def test_add_path_nonexistent_path_raises(self):
        """A nonexistent path raises InvalidRulePathError."""
        from cosl.rules import InvalidRulePathError

        rules = GenericRules(backend=PrometheusRuleBackend())
        with self.assertRaises(InvalidRulePathError):
            rules.add_path("/nonexistent/path")

    def test_add_path_topology_in_group_name(self):
        """Group names include topology identifier."""
        rules = GenericRules(backend=PrometheusRuleBackend(), topology=self.topology)
        rules.add_path(self.rules_dir / "cpu_overuse.rule")
        result = rules.as_dict()
        group_name = result["groups"][0]["name"]
        self.assertIn(self.topology.identifier, group_name)

    def test_add_path_nested_includes_relative_path(self):
        """Nested files include relative directory path in group name prefix."""
        rules = GenericRules(backend=PrometheusRuleBackend(), topology=self.topology)
        rules.add_path(self.rules_dir, recursive=True)
        result = rules.as_dict()
        nested_groups = [g for g in result["groups"] if "nested" in g["name"]]
        self.assertTrue(len(nested_groups) > 0)


# ===================================================================
# GenericRules – produces same output as legacy Rules
# ===================================================================


class TestGenericRulesBackwardCompat(unittest.TestCase):
    """Verify GenericRules with PrometheusRuleBackend matches legacy Rules output."""

    def setUp(self):
        self.topology = make_topology()

    def test_add_produces_same_as_legacy(self):
        """GenericRules.add with group_name produces same structure as legacy Rules._from_dict."""
        from cosl.rules import Rules

        legacy = Rules(query_type="promql")
        legacy_groups = legacy._from_dict(SINGLE_ALERT_RULE, group_name="test")

        generic = GenericRules(backend=PrometheusRuleBackend())
        generic.add(SINGLE_ALERT_RULE, group_name="test")
        generic_result = generic.as_dict()

        self.assertEqual({}, DeepDiff({"groups": legacy_groups}, generic_result))


if __name__ == "__main__":
    unittest.main()
