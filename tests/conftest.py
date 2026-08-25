# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Shared pytest fixtures for cos-lib tests."""

import pytest


@pytest.fixture
def sample_alerts():
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


def find_rule(alerts, identifier, group_name, rule_name, *, by_record=False):
    """Return a single rule from an alerts dict, raising if not found."""
    key = "record" if by_record else "alert"
    groups = alerts[identifier]["groups"]
    group = next(g for g in groups if g["name"] == group_name)
    return next(rule for rule in group["rules"] if rule.get(key) == rule_name)
