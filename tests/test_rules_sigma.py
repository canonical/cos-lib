# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Sigma rules tests."""

from pathlib import Path

from pytest_bdd import given, parsers, scenarios, then, when

from cosl.juju_topology import JujuTopology
from cosl.rules import SigmaRules

VALID_SIGMA_RULES_DIR = Path(__file__).resolve().parent / "sigma_rules" / "valid_rules"
INVALID_SIGMA_RULES_DIR = Path(__file__).resolve().parent / "sigma_rules" / "invalid_rules"
MODEL_UUID = "53316f3c-b681-47b8-b272-9f8a2a858e0e"

# --- Scenarios (auto-collect all from feature file) ---

scenarios("features/sigma_rules.feature")


# --- Given steps --- #


@given(
    parsers.parse('a Juju topology for model "{model}" and application "{app}"'),
    target_fixture="sigma",
)
def given_topology(model, app):
    topo = JujuTopology(
        model=model,
        model_uuid=MODEL_UUID,
        unit=f"{app}/0",
        application=app,
    )
    return SigmaRules(topology=topo)


@given("no Juju topology", target_fixture="sigma")
def given_no_topology():
    return SigmaRules()


# --- When steps --- #


@when(parsers.parse('I add a single sigma rule titled "{title}"'))
def when_add_single_rule(sigma, title):
    sigma.add(
        {
            "title": title,
            "logsource": {"category": "test", "product": "linux"},
            "detection": {"selection": {"field": "value"}, "condition": "selection"},
            "level": "low",
        }
    )


@when(parsers.parse('I add a collection containing rules "{title_a}" and "{title_b}"'))
def when_add_collection(sigma, title_a, title_b):
    sigma.add(
        {
            "rules": [
                {
                    "title": title_a,
                    "logsource": {"category": "auth", "product": "linux"},
                    "detection": {"selection": {"user": "root"}, "condition": "selection"},
                    "level": "high",
                },
                {
                    "title": title_b,
                    "logsource": {"category": "network", "product": "linux"},
                    "detection": {"selection": {"port": 22}, "condition": "selection"},
                    "level": "medium",
                },
            ]
        }
    )


@when("I add an empty dict")
def when_add_empty(sigma):
    sigma.add({})


@when(parsers.parse('I add a sigma rule with labels "{label_a}" and "{label_b}"'))
def when_add_with_labels(sigma, label_a, label_b):
    labels = {}
    for pair in (label_a, label_b):
        k, v = pair.split("=", 1)
        labels[k] = v
    sigma.add(
        {
            "title": "Pre-labeled Rule",
            "logsource": {"category": "test", "product": "linux"},
            "detection": {"selection": {"x": 1}, "condition": "selection"},
            "labels": labels,
        }
    )


@when(parsers.parse('I load the valid sigma rule file "{filename}"'))
def when_load_file(sigma, filename):
    sigma.add_path(VALID_SIGMA_RULES_DIR / filename)


@when(parsers.parse('I load the invalid sigma rule file "{filename}"'))
def when_load_file(sigma, filename):
    sigma.add_path(INVALID_SIGMA_RULES_DIR / filename)


@when("I load the sigma rules directory")
def when_load_directory(sigma):
    sigma.add_path(VALID_SIGMA_RULES_DIR)


@when(
    "I add a sigma rule and keep a reference to the original dict",
    target_fixture="original_dict",
)
def when_add_and_keep_ref(sigma):
    original = {
        "title": "Original",
        "logsource": {"category": "test", "product": "linux"},
        "detection": {"selection": {"a": 1}, "condition": "selection"},
    }
    sigma.add(original)
    return original


# --- Then steps --- #


@then(parsers.parse("the rules collection contains {count:d} rule"))
@then(parsers.parse("the rules collection contains {count:d} rules"))
def then_rule_count(sigma, count):
    result = sigma.as_dict()
    assert len(result.get("rules", [])) == count


@then("the rules collection is empty")
def then_empty(sigma):
    assert sigma.as_dict() == {}


@then(parsers.parse('the rule titled "{title}" exists'))
def then_rule_titled(sigma, title):
    titles = {r["title"] for r in sigma.rules}
    assert title in titles


@then(parsers.parse('the rule has label "{label}" set to "{value}"'))
def then_label_equals(sigma, label, value):
    labels = sigma.rules[0].get("labels", {})
    assert labels.get(label) == value


@then(parsers.parse('the rule has a label named "{label}"'))
def then_label_exists(sigma, label):
    labels = sigma.rules[0].get("labels", {})
    assert label in labels


@then(parsers.parse('the rule has id "{rule_id}"'))
def then_rule_id(sigma, rule_id):
    assert sigma.rules[0]["id"] == rule_id


@then("the rule has no labels")
def then_no_labels(sigma):
    assert "labels" not in sigma.rules[0]


@then("the original dict is unchanged")
def then_original_unchanged(original_dict):
    assert "labels" not in original_dict, "add() must not mutate the caller's dict"
