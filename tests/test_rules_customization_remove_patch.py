# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""pytest-bdd step definitions for remove-patch interaction scenarios.

Feature file: tests/features/remove_patch.feature
"""

import copy

import yaml
from helpers import _find_alert
from pytest_bdd import given, parsers, scenarios, then, when

from cosl.rules_customization import (
    AlertRulesCustomization,
    AlertRulesCustomizationValidationError,
)

scenarios("features/remove_patch.feature")


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given(parsers.parse("the following alert rules:\n{docstring}"), target_fixture="alerts")
def given_the_following_alert_rules(docstring):
    return yaml.safe_load(docstring)


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


@when(
    parsers.parse("the following customization is applied:\n{docstring}"),
    target_fixture="apply_outcome",
)
def when_the_following_customization_is_applied(docstring, alerts):
    customization = AlertRulesCustomization.from_yaml(docstring, "promql")
    original = copy.deepcopy(alerts)
    result = customization.apply(alerts)
    return {
        "result": result,
        "original": original,
        "input": alerts,
        "customization": customization,
    }


@when("the same customization is applied to a second input", target_fixture="both_results")
def when_same_customization_applied_to_second_input(apply_outcome):
    second_input = {
        "other": {"groups": [{"name": "g", "rules": [{"alert": "HostDown", "expr": "up < 1"}]}]}
    }
    return {
        "result1": apply_outcome["result"],
        "result2": apply_outcome["customization"].apply(second_input),
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
    for group in result[identifier].get("groups", []):
        for rule in group.get("rules", []):
            assert (
                rule.get("alert") != name
            ), f"alert {name!r} was found in identifier {identifier!r} but should be absent"


@then(parsers.parse('alert "{name}" has "{field}" equal to "{value}"'))
def then_alert_field(apply_outcome, name, field, value):
    result = apply_outcome["result"]
    found = _find_alert(result, name)
    assert found[field] == value, f"expected {field}={value!r}, got {found.get(field)!r}"


@then(parsers.parse('alert "{name}" is absent from both results'))
def then_alert_absent_from_both(both_results, name):
    for label, result in [
        ("result1", both_results["result1"]),
        ("result2", both_results["result2"]),
    ]:
        for rule_file in result.values():
            for group in rule_file.get("groups", []):
                for rule in group.get("rules", []):
                    assert (
                        rule.get("alert") != name
                    ), f"alert {name!r} found in {label} but should be absent"


# ---------------------------------------------------------------------------
# Steps for validation scenarios
# ---------------------------------------------------------------------------


@when(
    parsers.parse("the following customization is applied and validation occurs:\n{docstring}"),
    target_fixture="validation_outcome",
)
def when_customization_with_validation(docstring, alerts):
    original = copy.deepcopy(alerts)
    try:
        AlertRulesCustomization.from_yaml(docstring, "promql").apply(alerts)
        return {"error": None, "original": original}
    except AlertRulesCustomizationValidationError as e:
        return {"error": e, "original": original}


@then("an AlertRulesCustomizationValidationError is raised")
def then_validation_error_raised(validation_outcome):
    assert (
        validation_outcome["error"] is not None
    ), "expected an AlertRulesCustomizationValidationError but no error was raised"
    assert isinstance(validation_outcome["error"], AlertRulesCustomizationValidationError)


@then("the original alerts are unchanged")
def then_original_alerts_unchanged(validation_outcome, alerts):
    assert (
        alerts == validation_outcome["original"]
    ), "apply() must not have mutated the original alerts"
