# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""pytest-bdd step definitions for patch scenarios.

Feature file: tests/features/patch.feature
"""

import yaml
from helpers import _find_alert, _find_record
from pytest_bdd import given, parsers, scenarios, then, when

from cosl.rules_customization import AlertRulesCustomization

scenarios("features/patch.feature")


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given(parsers.parse("the following alert rules:\n{docstring}"), target_fixture="alerts")
def given_the_following_alert_rules(docstring):
    return yaml.safe_load(docstring)


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


@when(parsers.parse("the following customization is applied:\n{docstring}"), target_fixture="result")
def when_the_following_customization_is_applied(docstring, alerts):
    return AlertRulesCustomization.from_yaml(docstring).apply(alerts)


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------


@then(parsers.parse('alert "{name}" has "{field}" equal to "{value}"'))
def then_alert_field(result, name, field, value):
    found = _find_alert(result, name)
    assert found[field] == value, f"expected {field}={value!r}, got {found.get(field)!r}"


@then(parsers.parse('alert "{name}" has label "{key}" equal to "{value}"'))
def then_alert_label(result, name, key, value):
    found = _find_alert(result, name)
    labels = found.get("labels", {})
    assert labels.get(key) == value, f"expected label {key}={value!r}, got {labels.get(key)!r}"


@then(parsers.parse('alert "{name}" has annotation "{key}" equal to "{value}"'))
def then_alert_annotation(result, name, key, value):
    found = _find_alert(result, name)
    annotations = found.get("annotations", {})
    assert (
        annotations.get(key) == value
    ), f"expected annotation {key}={value!r}, got {annotations.get(key)!r}"


@then(parsers.parse('alert "{name}" is present'))
def then_alert_present(result, name):
    _find_alert(result, name)  # raises AssertionError if not found


@then(parsers.parse('alert "{name}" is absent'))
def then_alert_absent(result, name):
    for rule_file in result.values():
        for group in rule_file.get("groups", []):
            for rule in group.get("rules", []):
                assert rule.get("alert") != name, f"alert {name!r} was found but should be absent"


@then(parsers.parse('recording rule "{name}" has "{field}" equal to "{value}"'))
def then_recording_rule_field(result, name, field, value):
    found = _find_record(result, name)
    assert found[field] == value, f"expected {field}={value!r}, got {found.get(field)!r}"


@then(parsers.parse('recording rule "{name}" has label "{key}" equal to "{value}"'))
def then_recording_rule_label(result, name, key, value):
    found = _find_record(result, name)
    labels = found.get("labels", {})
    assert labels.get(key) == value, f"expected label {key}={value!r}, got {labels.get(key)!r}"


@then(parsers.parse('alert "{name}" is present in group "{group_name}" of "{identifier}"'))
def then_alert_present_in_group(result, name, group_name, identifier):
    assert identifier in result, f"identifier {identifier!r} not found in result"
    groups = result[identifier].get("groups", [])
    group = next((g for g in groups if g.get("name") == group_name), None)
    assert group is not None, f"group {group_name!r} not found in {identifier!r}"
    rules = group.get("rules", [])
    assert any(
        r.get("alert") == name for r in rules
    ), f"alert {name!r} not found in group {group_name!r} of {identifier!r}"
