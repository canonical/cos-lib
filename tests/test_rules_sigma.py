# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Sigma rules tests."""

from pathlib import Path

import pytest

from cosl.juju_topology import JujuTopology
from cosl.rules import SigmaRules

SIGMA_RULES_DIR = Path(__file__).resolve().parent / "sigma_rules"
SIGMA_SINGLE_DIR = SIGMA_RULES_DIR / "single"
SIGMA_COLLECTION_DIR = SIGMA_RULES_DIR / "collection"
SIGMA_INVALID_DIR = SIGMA_RULES_DIR / "invalid"
MODEL_UUID = "53316f3c-b681-47b8-b272-9f8a2a858e0e"


@pytest.fixture
def sigma():
    topology = JujuTopology(
        model="testmodel", model_uuid=MODEL_UUID, unit="myapp/0", application="myapp"
    )
    return SigmaRules(topology=topology)


def _rule(title, **extra):
    return {
        "title": title,
        "logsource": {"category": "test", "product": "linux"},
        "detection": {"selection": {"field": "value"}, "condition": "selection"},
        **extra,
    }


# --- Adding rules from dicts ---


def test_add_single_rule(sigma):
    sigma.add(_rule("Test Rule"))
    assert len(sigma.as_dict()["rules"]) == 1
    assert sigma.rules[0]["title"] == "Test Rule"


def test_add_collection(sigma):
    sigma.add({"rules": [_rule("Rule A"), _rule("Rule B")]})
    assert {r["title"] for r in sigma.rules} == {"Rule A", "Rule B"}


def test_add_empty_dict_does_nothing(sigma):
    sigma.add({})
    assert sigma.as_dict() == {}


# --- Topology injection ---


def test_topology_injected_as_tags(sigma):
    sigma.add(_rule("Labeled Rule"))
    tags = sigma.rules[0]["tags"]
    assert "juju_model.testmodel" in tags
    assert "juju_application.myapp" in tags
    assert any(tag.startswith("juju_model_uuid.") for tag in tags)


def test_topology_does_not_overwrite_existing_tags(sigma):
    sigma.add(_rule("Pre-tagged Rule", tags=["juju_application.custom-app"]))
    tags = sigma.rules[0]["tags"]
    assert "juju_application.custom-app" in tags
    assert "juju_application.myapp" not in tags
    assert "juju_model.testmodel" in tags


def test_no_topology_means_no_tags():
    sigma = SigmaRules()
    sigma.add(_rule("No Topo Rule"))
    assert "tags" not in sigma.rules[0]


# --- Loading from filesystem ---


def test_load_single_file(sigma):
    sigma.add_path(SIGMA_SINGLE_DIR / "ssh_failed_login.yaml")
    assert len(sigma.rules) == 1
    assert sigma.rules[0]["title"] == "Failed SSH Login Attempt"
    assert sigma.rules[0]["id"] == "5f3a4e20-1b2c-4d5e-9f8a-7b6c3d4e5f6a"


def test_load_directory_recursively(sigma):
    # 3 single-rule files + 1 collection file containing 2 rules
    # + 1 partially-valid collection file containing 1 rule = 6
    sigma.add_path(SIGMA_RULES_DIR, recursive=True)
    assert len(sigma.rules) == 6


def test_load_single_rule_directory(sigma):
    sigma.add_path(SIGMA_SINGLE_DIR)
    assert len(sigma.rules) == 3


def test_collection_file_expands(sigma):
    sigma.add_path(SIGMA_COLLECTION_DIR / "collection.yaml")
    assert {r["title"] for r in sigma.rules} == {
        "Disk Space Critical",
        "Memory Exhaustion Warning",
    }


def test_load_nonexistent_path(sigma):
    sigma.add_path(SIGMA_RULES_DIR / "nonexistent.yaml")
    assert sigma.as_dict() == {}


def test_topology_injected_on_file_load(sigma):
    sigma.add_path(SIGMA_SINGLE_DIR / "high_cpu_process.yaml")
    tags = sigma.rules[0]["tags"]
    assert "juju_model.testmodel" in tags
    assert "juju_application.myapp" in tags


def test_existing_file_tags_preserved(sigma):
    sigma.add_path(SIGMA_SINGLE_DIR / "unauthorized_api_access.yaml")
    tags = sigma.rules[0]["tags"]
    assert "team.security" in tags
    assert "juju_model.testmodel" in tags


# --- Isolation ---


def test_add_does_not_mutate_input(sigma):
    original = _rule("Original")
    sigma.add(original)
    assert "tags" not in original, "add() must not mutate the caller's dict"


# --- Topology tag de-duplication edges (gap #5) ---


def test_existing_juju_model_tag_not_overwritten(sigma):
    # An upstream charm (e.g. an aggregator forwarding rules) may already have set a
    # juju_model tag; it must win over the local topology.
    sigma.add(_rule("Upstream Model", tags=["juju_model.upstream-model"]))
    tags = sigma.rules[0]["tags"]
    assert "juju_model.upstream-model" in tags
    assert "juju_model.testmodel" not in tags
    # other namespaces are still injected
    assert "juju_application.myapp" in tags


def test_existing_juju_model_uuid_tag_not_overwritten(sigma):
    sigma.add(_rule("Upstream UUID", tags=["juju_model_uuid.deadbeef"]))
    tags = sigma.rules[0]["tags"]
    assert "juju_model_uuid.deadbeef" in tags
    assert not any(
        tag.startswith("juju_model_uuid.") and tag != "juju_model_uuid.deadbeef" for tag in tags
    )
    assert "juju_model.testmodel" in tags


def test_existing_tag_is_preserved_and_does_not_block_juju_tags(sigma):
    # existing tags must survive injection untouched and must not swallow
    # any juju_* namespace.
    # Note: pySigma rejects dotless tags with the message:
    # "Sigma tag must start with namespace separated with dot from remaining tag."
    sigma.add(_rule("Flat Tag", tags=["attack.privilege-escalation"]))
    tags = sigma.rules[0]["tags"]
    assert "attack.privilege-escalation" in tags
    assert "juju_model.testmodel" in tags
    assert "juju_application.myapp" in tags
    assert any(tag.startswith("juju_model_uuid.") for tag in tags)


# --- Accumulation and (intentional) lack of de-duplication (gap #6) ---


def test_rules_accumulate_across_add_calls(sigma):
    sigma.add(_rule("First"))
    sigma.add(_rule("Second"))
    assert [r["title"] for r in sigma.rules] == ["First", "Second"]


def test_add_path_then_add_dict_accumulate(sigma):
    sigma.add_path(SIGMA_SINGLE_DIR / "ssh_failed_login.yaml")
    sigma.add(_rule("Manual"))
    titles = {r["title"] for r in sigma.rules}
    assert titles == {"Failed SSH Login Attempt", "Manual"}


def test_identical_rules_are_not_deduplicated(sigma):
    # SigmaRules deliberately does not de-duplicate: topology may legitimately
    # differentiate otherwise-identical rules, and `id` is optional. Pin this so a
    # future "helpful" dedup change is a conscious decision.
    sigma.add(_rule("Dup", id="11111111-1111-4111-8111-111111111111"))
    sigma.add(_rule("Dup", id="11111111-1111-4111-8111-111111111111"))
    assert len(sigma.rules) == 2


def test_same_file_loaded_twice_yields_duplicates(sigma):
    sigma.add_path(SIGMA_SINGLE_DIR / "ssh_failed_login.yaml")
    sigma.add_path(SIGMA_SINGLE_DIR / "ssh_failed_login.yaml")
    assert len(sigma.rules) == 2


def test_rule_id_is_preserved_verbatim(sigma):
    rule_id = "5f3a4e20-1b2c-4d5e-9f8a-7b6c3d4e5f6a"
    sigma.add(_rule("Has ID", id=rule_id))
    assert sigma.rules[0]["id"] == rule_id


# --- as_dict() returns an isolated rules list (gap #4) ---


def test_as_dict_returns_copy_of_rules_list(sigma):
    sigma.add(_rule("Original"))
    snapshot = sigma.as_dict()
    snapshot["rules"].append(_rule("Injected"))
    # Mutating the returned mapping's list must not affect internal state.
    assert len(sigma.rules) == 1
    assert sigma.rules[0]["title"] == "Original"


# --- Filesystem edge cases (gaps #2, #3, #7) ---


def test_empty_file_adds_no_rules(sigma, tmp_path):
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    sigma.add_path(empty)
    assert sigma.as_dict() == {}


def test_null_only_file_adds_no_rules(sigma, tmp_path):
    null_only = tmp_path / "null_only.yaml"
    null_only.write_text("null\n")
    sigma.add_path(null_only)
    assert sigma.as_dict() == {}


def test_directory_ignores_unrecognized_suffixes(sigma, tmp_path, caplog):
    # A valid rule alongside files with non-rule suffixes: only the rule is loaded,
    # and the ignored files are logged.
    (tmp_path / "good.yaml").write_text(
        "title: Good Rule\n"
        "logsource:\n  category: test\n  product: linux\n"
        "detection:\n  selection:\n    field: value\n  condition: selection\n"
    )
    (tmp_path / "notes.txt").write_text("not a rule")
    (tmp_path / "data.json").write_text('{"not": "a rule"}')

    with caplog.at_level("INFO", logger="cosl.rules"):
        sigma.add_path(tmp_path)

    assert [r["title"] for r in sigma.rules] == ["Good Rule"]
    log_text = " ".join(rec.message for rec in caplog.records)
    assert "notes.txt" in log_text
    assert "data.json" in log_text


def test_directory_non_recursive_skips_subdirs(sigma, tmp_path):
    _write_sigma_rule(tmp_path / "top.yaml", "Top Rule")
    nested = tmp_path / "nested"
    nested.mkdir()
    _write_sigma_rule(nested / "deep.yaml", "Deep Rule")

    sigma.add_path(tmp_path)  # recursive defaults to False

    assert [r["title"] for r in sigma.rules] == ["Top Rule"]


def test_directory_recursive_includes_subdirs(sigma, tmp_path):
    _write_sigma_rule(tmp_path / "top.yaml", "Top Rule")
    nested = tmp_path / "nested"
    nested.mkdir()
    _write_sigma_rule(nested / "deep.yaml", "Deep Rule")

    sigma.add_path(tmp_path, recursive=True)

    assert {r["title"] for r in sigma.rules} == {"Top Rule", "Deep Rule"}


def _write_sigma_rule(path: Path, title: str) -> None:
    path.write_text(
        f"title: {title}\n"
        "logsource:\n  category: test\n  product: linux\n"
        "detection:\n  selection:\n    field: value\n  condition: selection\n"
    )


# --- Determinism: output must be stable across hooks to avoid spurious relation-changed ---


def test_tags_are_sorted_regardless_of_input_order(sigma):
    sigma.add(_rule("Unsorted", tags=["zeta.last", "alpha.first", "mike.middle"]))
    tags = sigma.rules[0]["tags"]
    assert tags == sorted(tags), "tags must be sorted for byte-stable serialization"


def test_same_input_produces_identical_output(sigma):
    # Two SigmaRules built from identical input must serialize identically; otherwise
    # the relation databag would change on every hook and fire relation-changed.
    other = SigmaRules(
        topology=JujuTopology(
            model="testmodel", model_uuid=MODEL_UUID, unit="myapp/0", application="myapp"
        )
    )
    rule = _rule("Stable", tags=["zeta.z", "alpha.a"])
    sigma.add(dict(rule))
    other.add(dict(rule))
    assert sigma.as_dict() == other.as_dict()


def test_no_id_is_never_generated(sigma):
    # A UUID must never be auto-assigned; doing so would change output every hook.
    sigma.add(_rule("No Id"))
    assert "id" not in sigma.rules[0]


def test_reinjecting_already_topologized_rules_is_idempotent(sigma):
    # Models the RuleStore.combine() forwarding path: an aggregator re-ingests rules
    # that already carry juju_* tags. Re-injection must not add, duplicate, or reorder
    # tags, so the forwarded output is byte-identical to the input.
    sigma.add(_rule("Forwarded"))
    first = sigma.as_dict()

    downstream = SigmaRules(
        topology=JujuTopology(
            model="testmodel", model_uuid=MODEL_UUID, unit="myapp/0", application="myapp"
        )
    )
    # Feed the already-injected output back in, as combine() does.
    downstream.add(first)
    assert downstream.as_dict() == first


def test_reinjection_does_not_duplicate_juju_tags(sigma):
    sigma.add(_rule("Once"))
    injected = sigma.as_dict()["rules"][0]["tags"]

    downstream = SigmaRules(
        topology=JujuTopology(
            model="testmodel", model_uuid=MODEL_UUID, unit="myapp/0", application="myapp"
        )
    )
    downstream.add({"rules": [dict(sigma.rules[0])]})
    reinjected = downstream.as_dict()["rules"][0]["tags"]
    assert reinjected == injected
    # no namespace appears twice
    namespaces = [t.split(".", 1)[0] for t in reinjected]
    assert len(namespaces) == len(set(namespaces))


# --- Rule validation ---


def test_loading_invalid_rule_creates_empty_list(sigma):
    sigma.add_path(SIGMA_INVALID_DIR / "high_cpu_process.yaml")
    assert len(sigma.rules) == 0  # must not raise exception


def test_loading_partially_valid_collection_yields_valid_rules(sigma):
    sigma.add_path(SIGMA_INVALID_DIR / "collection.yaml")
    assert len(sigma.rules) == 1
    assert sigma.rules[0].get("title") == "Disk Space Critical"
    pass
