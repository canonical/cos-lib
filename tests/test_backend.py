# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for _GroupedRuleBackend (from_dict, from_file, as_dict, file_suffixes).

These tests exercise the shared backend base class via PrometheusRuleBackend,
since _GroupedRuleBackend is private and requires a concrete query_type.
"""

import re
import unittest

from helpers import (
    BAD_YAML_RULE_PATH,
    OFFICIAL_RULE,
    PROMETHEUS_RULES_DIR,
    SINGLE_ALERT_RULE,
    load_rule,
    make_topology,
)

from cosl.backends.prometheus import PrometheusRuleBackend

# ===================================================================
# GroupedRules – from_dict
# ===================================================================


class TestGroupedRulesFromDict(unittest.TestCase):
    """Tests for _GroupedRuleBackend.from_dict (via PrometheusRuleBackend)."""

    def test_official_format_parsed(self):
        """Official groups format is parsed correctly."""
        backend = PrometheusRuleBackend()
        groups = backend.from_dict(OFFICIAL_RULE)
        self.assertEqual(len(groups), 1)
        self.assertIn("TestGroup", groups[0]["name"])

    def test_single_rule_format_parsed(self):
        """Single-rule format is wrapped into a group."""
        backend = PrometheusRuleBackend()
        groups = backend.from_dict(SINGLE_ALERT_RULE, group_name="my_group")
        self.assertEqual(len(groups), 1)
        self.assertIn("my_group", groups[0]["name"])
        self.assertEqual(len(groups[0]["rules"]), 1)
        self.assertEqual(groups[0]["rules"][0]["alert"], "CPUOverUse")

    def test_single_rule_gets_hash_name_when_no_group_name(self):
        """When no group_name is provided, a hash-based name is generated."""
        backend = PrometheusRuleBackend()
        groups = backend.from_dict(SINGLE_ALERT_RULE)
        # Group name should end with _rules
        self.assertTrue(groups[0]["name"].endswith("_rules"))

    def test_group_name_prefix_applied(self):
        """group_name_prefix is prepended to the group name."""
        backend = PrometheusRuleBackend()
        groups = backend.from_dict(
            SINGLE_ALERT_RULE,
            group_name="mygroup",
            group_name_prefix="prefix",
        )
        self.assertTrue(groups[0]["name"].startswith("prefix_"))

    def test_official_format_group_name_prefix(self):
        """For official format, the existing group name is prefixed."""
        backend = PrometheusRuleBackend()
        groups = backend.from_dict(OFFICIAL_RULE, group_name_prefix="topo")
        self.assertTrue(groups[0]["name"].startswith("topo_"))
        self.assertIn("TestGroup", groups[0]["name"])

    def test_empty_dict_raises_value_error(self):
        """An empty dict raises ValueError."""
        backend = PrometheusRuleBackend()
        with self.assertRaises(ValueError) as ctx:
            backend.from_dict({})
        self.assertEqual(str(ctx.exception), "Empty")

    def test_topology_labels_injected(self):
        """Topology labels are injected into rule labels."""
        topo = make_topology()
        backend = PrometheusRuleBackend(topology=topo)
        groups = backend.from_dict(SINGLE_ALERT_RULE, group_name="test")
        rule = groups[0]["rules"][0]
        self.assertIn("juju_model", rule["labels"])
        self.assertIn("juju_application", rule["labels"])
        self.assertIn("juju_model_uuid", rule["labels"])
        self.assertEqual(rule["labels"]["juju_model"], "mymodel")
        self.assertEqual(rule["labels"]["juju_application"], "myapp")

    def test_topology_labels_not_overwritten(self):
        """Pre-existing topology labels in a rule are not overwritten."""
        topo = make_topology()
        backend = PrometheusRuleBackend(topology=topo)
        rule_with_labels = {
            "alert": "Test",
            "expr": "up < 1",
            "labels": {"severity": "critical", "juju_model": "existing_model"},
        }
        groups = backend.from_dict(rule_with_labels, group_name="test")
        self.assertEqual(groups[0]["rules"][0]["labels"]["juju_model"], "existing_model")

    def test_no_topology_no_labels_injected(self):
        """Without topology, no juju labels are added."""
        backend = PrometheusRuleBackend()
        groups = backend.from_dict(SINGLE_ALERT_RULE, group_name="test")
        rule = groups[0]["rules"][0]
        self.assertNotIn("juju_model", rule["labels"])

    def test_group_name_sanitized(self):
        """Special characters in group names are sanitized to underscores."""
        backend = PrometheusRuleBackend()
        groups = backend.from_dict(SINGLE_ALERT_RULE, group_name="Foo$Bar/Baz")
        name = groups[0]["name"]
        # Only [a-zA-Z0-9_:] should remain
        self.assertIsNotNone(re.match(r"^[a-zA-Z0-9_:]+$", name))

    def test_juju_topology_placeholder_replaced_promql(self):
        """The %%juju_topology%% placeholder is replaced in PromQL expressions."""
        topo = make_topology()
        backend = PrometheusRuleBackend(topology=topo)
        rule = load_rule(PROMETHEUS_RULES_DIR / "with_template_string.rule")
        groups = backend.from_dict(rule, group_name="test")
        expr = groups[0]["rules"][0]["expr"]
        self.assertNotIn("%%juju_topology%%", expr)


# ===================================================================
# GroupedRules – from_file
# ===================================================================


class TestGroupedRulesFromFile(unittest.TestCase):
    """Tests for from_file using existing fixture files using Prometheus backend."""

    def test_from_file_single_rule(self):
        """A single-rule fixture file is parsed into one group."""
        backend = PrometheusRuleBackend()
        path = PROMETHEUS_RULES_DIR / "cpu_overuse.rule"
        groups = backend.from_file(path, root_path=path.parent)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["rules"][0]["alert"], "CPUOverUse")

    def test_from_file_group_name_from_stem(self):
        """Group name should be derived from the file stem."""
        backend = PrometheusRuleBackend()
        path = PROMETHEUS_RULES_DIR / "cpu_overuse.rule"
        groups = backend.from_file(path, root_path=path.parent)
        self.assertIn("cpu_overuse", groups[0]["name"])

    def test_from_file_invalid_yaml_returns_empty(self):
        """Invalid YAML files return an empty list instead of raising."""
        backend = PrometheusRuleBackend()
        groups = backend.from_file(BAD_YAML_RULE_PATH, root_path=BAD_YAML_RULE_PATH.parent)
        self.assertEqual(groups, [])


# ===================================================================
# GroupedRules – as_dict, validate, file_suffixes
# ===================================================================


class TestGroupedRulesOther(unittest.TestCase):
    """Tests for as_dict, validate, and file_suffixes using Prometheus backend."""

    def test_prometheus_as_dict(self):
        """as_dict wraps items under a 'groups' key."""
        backend = PrometheusRuleBackend()
        items = backend.from_dict(OFFICIAL_RULE)
        result = backend.as_dict(items)
        self.assertIn("groups", result)
        self.assertEqual(len(result["groups"]), 1)

    def test_prometheus_as_dict_empty(self):
        """as_dict returns an empty dict when given no items."""
        backend = PrometheusRuleBackend()
        result = backend.as_dict([])
        self.assertEqual(result, {})

    def test_file_suffixes(self):
        """file_suffixes returns the expected rule file extensions."""
        backend = PrometheusRuleBackend()
        self.assertEqual(backend.file_suffixes, [".rule", ".rules", ".yml", ".yaml"])


if __name__ == "__main__":
    unittest.main()
