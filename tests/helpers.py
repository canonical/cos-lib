# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared test helpers and fixtures for AbstractRules tests."""

from pathlib import Path

import yaml

from cosl.juju_topology import JujuTopology

FIXTURE_DIR = Path(__file__).resolve().parent / "promql_rules"
PROMETHEUS_RULES_DIR = FIXTURE_DIR / "prometheus_alert_rules"
BAD_YAML_RULE_PATH = FIXTURE_DIR / "bad_alert_rules" / "bad_yaml.rule"


def make_topology(**overrides):
    defaults = {
        "model": "mymodel",
        "model_uuid": "12de4fae-06cc-4ceb-9089-567be09fec78",
        "application": "myapp",
        "unit": "myapp/0",
        "charm_name": "mycharm",
    }
    defaults.update(overrides)
    return JujuTopology(**defaults)


def load_rule(path: Path) -> dict:
    """Load a YAML rule file into a dict."""
    with path.open() as f:
        return yaml.safe_load(f)


# Single-rule format loaded from fixture
SINGLE_ALERT_RULE = load_rule(PROMETHEUS_RULES_DIR / "cpu_overuse.rule")

# Official groups format (no fixture file exists for this format)
OFFICIAL_RULE = {
    "groups": [
        {
            "name": "TestGroup",
            "rules": [
                {
                    "alert": "TestAlert",
                    "expr": "up < 1",
                    "labels": {"severity": "warning"},
                }
            ],
        }
    ]
}
