# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from pathlib import Path

from fs.tempfs import TempFS

from cosl.rules import AlertRules, InvalidRulePathError


class TestValidateRulesPath(unittest.TestCase):
    def setUp(self):
        self.sandbox = TempFS("charm_dir", auto_clean=True)
        self.addCleanup(self.sandbox.close)
        self.sandbox.makedirs("charm")
        self.charm_dir = Path(self.sandbox.getsyspath("charm"))

    def test_returns_absolute_for_existing_directory(self):
        self.sandbox.makedirs("charm/src/prometheus_alert_rules")
        res = AlertRules.resolve_dir_against_charm_path(
            "src/prometheus_alert_rules", charm_dir=self.charm_dir
        )
        self.assertEqual(res, str(self.charm_dir.joinpath("src/prometheus_alert_rules")))
        self.assertTrue(Path(res).is_dir())

    def test_returns_input_for_missing_directory(self):
        with self.assertRaises(InvalidRulePathError):
            AlertRules.resolve_dir_against_charm_path("does_not_exist", charm_dir=self.charm_dir)

    def test_returns_input_for_file_path(self):
        self.sandbox.writetext("charm/not_a_dir", "contents")
        with self.assertRaises(InvalidRulePathError):
            AlertRules.resolve_dir_against_charm_path("not_a_dir", charm_dir=self.charm_dir)
