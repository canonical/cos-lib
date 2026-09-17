# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""pytest-bdd step definitions for remove-patch interaction scenarios.

Feature file: tests/features/remove_patch.feature
"""

import copy

import yaml
from helpers import _find_alert
from pytest_bdd import given, parsers, scenarios, then, when

from cosl.rules_customization import AlertRulesCustomization

scenarios("features/remove_patch.feature")


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given("the following alert rules", target_fixture="alerts")
def given_the_following_alert_rules(docstring):
    return yaml.safe_load(docstring)


@given("the following combined config", target_fixture="customization")
def given_the_following_combined_config(docstring):
    return AlertRulesCustomization.from_yaml(docstring)


@given("the following remove config", target_fixture="customization")
def given_the_following_remove_config(docstring):
    return AlertRulesCustomization.from_yaml(docstring)


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


@when("the customization is applied", target_fixture="apply_outcome")
def when_the_customization_is_applied(customization, alerts):
    original = copy.deepcopy(alerts)
    result = customization.apply(alerts)
    return {"result": result, "original": original, "input": alerts}


@when("the same customization is applied to two different inputs", target_fixture="both_results")
def when_same_customization_applied_twice(customization, alerts):
    other = {
        "other": {"groups": [{"name": "g", "rules": [{"alert": "HostDown", "expr": "up < 1"}]}]}
    }
    return {
        "result1": customization.apply(alerts),
        "result2": customization.apply(other),
    }


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------


@then("the original input is unchanged")
def then_original_input_unchanged(apply_outcome):
    assert (
        apply_outcome["input"] == apply_outcome["original"]
    ), "apply() mutated the input — original and current input differ"


@then(parsers.parse('alert "{name}" is absent from identifier "{identifier}"'))
def then_alert_absent_from_identifier(apply_outcome, name, identifier):
    result = apply_outcome["result"]
    if identifier not in result:
        return
    assert name not in str(
        result[identifier]
    ), f"alert {name!r} was found in identifier {identifier!r} but should be absent"


@then(parsers.parse('alert "{name}" has "{field}" equal to "{value}"'))
def then_alert_field(apply_outcome, name, field, value):
    result = apply_outcome["result"]
    found = _find_alert(result, name)
    assert found[field] == value, f"expected {field}={value!r}, got {found.get(field)!r}"


@then(parsers.parse('alert "{name}" is absent from both results'))
def then_alert_absent_from_both(both_results, name):
    assert name not in str(
        both_results["result1"]
    ), f"alert {name!r} found in result1 but should be absent"
    assert name not in str(
        both_results["result2"]
    ), f"alert {name!r} found in result2 but should be absent"
