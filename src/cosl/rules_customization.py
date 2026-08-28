# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Admin-facing alert rule customization.

## Overview

This module provides :class:`AlertRulesCustomization`, a pure transformation helper that
takes relation-derived alert rule files (the same dict that relation libraries such as
``MetricsConsumer.alerts`` produce) and an admin-provided YAML customization config, and
returns the modified rules in the same format.

The customization config supports two top-level keys:

- ``remove``: drop matching alerting rules (or entire groups, when ``group`` is the only
  selector).
- ``patch``: modify matching alerting rules by merging a ``set`` block into them.

Matching is performed via a ``where`` block, supporting exact equality on ``alert``,
``group``, ``labels`` and ``annotations``. All fields within one ``where`` are ANDed;
multiple entries in the ``remove``/``patch`` lists provide OR semantics.

Recording rules are never removed or patched unless an entire group is dropped via a
group-only ``where`` selector.

This class is a pure transformation helper. It does not call CosTool, Pebble,
Prometheus, Loki or Mimir APIs, does not write files and does not set statuses.
Validation of the resulting rules is the charm's responsibility after calling
:meth:`AlertRulesCustomization.apply`.
"""

import collections.abc
import copy
import logging
from typing import Any, Dict, List, Mapping, Optional, cast

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from .types import OfficialRuleFileFormat

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models for config validation
# ---------------------------------------------------------------------------


class _WhereBlock(BaseModel):
    alert: Optional[str] = None
    group: Optional[str] = None
    labels: Optional[Dict[str, str]] = None
    annotations: Optional[Dict[str, str]] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("labels", "annotations")
    @classmethod
    def _validate_mapping(cls, v: Any) -> Optional[Dict[str, str]]:  # type: ignore[return]
        if v is not None and not isinstance(v, collections.abc.Mapping):
            raise ValueError("must be a mapping of key-value pairs")
        return v  # type: ignore[return-value]

    @model_validator(mode="after")
    def _not_empty(self):
        if not any([self.alert, self.group, self.labels, self.annotations]):
            raise ValueError("'where' must not be empty")
        return self


class _SetBlock(BaseModel):
    alert: Optional[str] = None
    expr: Optional[str] = None
    for_: Optional[str] = Field(default=None, alias="for")
    labels: Optional[Dict[str, str]] = None
    annotations: Optional[Dict[str, str]] = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @field_validator("labels", "annotations")
    @classmethod
    def _validate_mapping(cls, v: Any) -> Optional[Dict[str, str]]:  # type: ignore[return]
        if v is not None and not isinstance(v, collections.abc.Mapping):
            raise ValueError("must be a mapping of key-value pairs")
        return v  # type: ignore[return-value]

    @model_validator(mode="after")
    def _not_empty(self):
        if not any(
            [
                self.alert,
                self.expr,
                self.for_,
                self.labels,
                self.annotations,
            ]
        ):
            raise ValueError("'set' must not be empty")
        return self


class _RemoveOperation(BaseModel):
    where: _WhereBlock

    model_config = ConfigDict(extra="forbid")


class _PatchOperation(BaseModel):
    where: _WhereBlock
    set: _SetBlock

    model_config = ConfigDict(extra="forbid")


class _RulesCustomizationConfig(BaseModel):
    remove: Optional[List[_RemoveOperation]] = None
    patch: Optional[List[_PatchOperation]] = None

    model_config = ConfigDict(extra="forbid")


class AlertRulesCustomizationError(Exception):
    """Raised when the alert rules customization configuration is invalid."""


def _format_pydantic_error(err: ValidationError) -> str:
    """Format a pydantic ValidationError into a single human-readable message."""
    messages: List[str] = []
    for error in err.errors():
        loc = ".".join(str(p) for p in error["loc"]) if error["loc"] else "root"
        msg: str = str(error["msg"]).rstrip(".")
        messages.append(f"{loc}: {msg}")
    return "; ".join(messages)


class AlertRulesCustomization:
    """Apply admin-defined remove/patch operations to relation-derived alert rules.

    Build an instance with :meth:`from_yaml`, then call :meth:`apply` on the alerts dict
    (e.g. ``self.metrics_consumer.alerts``). The instance is reusable: ``apply()`` can be
    called multiple times on different inputs.
    """

    def __init__(
        self,
        remove: Optional[List[Dict[str, Any]]] = None,
        patch: Optional[List[Dict[str, Any]]] = None,
    ):
        r"""Build a customization object from pre-validated operation blocks.

        Prefer :meth:`from_yaml` for parsing and validating user input.
        """
        self._remove: List[Dict[str, Any]] = remove or []
        self._patch: List[Dict[str, Any]] = patch or []

    @classmethod
    def from_yaml(cls, config_string: str) -> "AlertRulesCustomization":
        """Parse and validate the customization YAML.

        Args:
            config_string: raw YAML string, e.g. from a charm config option.

        Returns:
            An ``AlertRulesCustomization`` instance. If the config string is empty,
            whitespace-only or parses to ``None``, the returned instance is a no-op.

        Raises:
            AlertRulesCustomizationError: on invalid YAML, unknown top-level keys
                (only ``remove``, ``patch`` are allowed), invalid operation
                shape (missing ``where``, unknown selector keys, unknown set keys),
                empty ``where`` selectors.
        """
        if not config_string or not config_string.strip():
            return cls()

        try:
            parsed = yaml.safe_load(config_string)
        except yaml.YAMLError as e:
            raise AlertRulesCustomizationError(f"invalid YAML: {e}") from e

        if parsed is None:
            return cls()

        if not isinstance(parsed, collections.abc.Mapping):
            raise AlertRulesCustomizationError(
                f"configuration must be a mapping with keys 'remove', 'patch'; "
                f"got {type(parsed).__name__}"
            )

        try:
            config = _RulesCustomizationConfig.model_validate(parsed)
        except ValidationError as e:
            raise AlertRulesCustomizationError(_format_pydantic_error(e)) from e

        return cls(
            remove=(
                [op.model_dump(exclude_none=True, by_alias=True) for op in config.remove]
                if config.remove
                else None
            ),
            patch=(
                [op.model_dump(exclude_none=True, by_alias=True) for op in config.patch]
                if config.patch
                else None
            ),
        )

    def apply(
        self, relation_alerts: Mapping[str, OfficialRuleFileFormat]
    ) -> Dict[str, OfficialRuleFileFormat]:
        """Apply remove and patch operations to the input rules.

        Operations run in this order: remove, patch. The input is never mutated;
        the transformations operate on a deep copy.

        Args:
            relation_alerts: mapping of identifier to rule file, e.g.
                ``self.metrics_consumer.alerts``.

        Returns:
            The transformed rules, in the same format as the input. Identifiers whose
            ``groups`` list becomes empty after removal are dropped.
        """
        output: Dict[str, OfficialRuleFileFormat] = copy.deepcopy(dict(relation_alerts))

        self._apply_remove(output)
        self._apply_patch(output)

        return output

    def _matches(self, where: Mapping[str, Any], group_name: str, rule: Mapping[str, Any]) -> bool:
        """Does this rule (in this group) satisfy all fields of this where block?

        All fields present in the where block must match (AND semantics). Exact equality
        is used for ``alert`` and ``group``; ``labels``/``annotations`` require every
        key-value pair in the where block to exist in the rule's corresponding mapping.
        """
        if "group" in where and where["group"] != group_name:
            return False
        if "alert" in where and rule.get("alert") != where["alert"]:
            return False
        if "labels" in where:
            where_labels: Dict[Any, Any] = where["labels"]
            labels: Dict[Any, Any] = rule.get("labels") or {}
            if any(labels.get(key) != value for key, value in where_labels.items()):
                return False
        if "annotations" in where:
            where_annotations: Dict[Any, Any] = where["annotations"]
            annotations: Dict[Any, Any] = rule.get("annotations") or {}
            if any(annotations.get(key) != value for key, value in where_annotations.items()):
                return False
        return True

    @staticmethod
    def _is_group_only_selector(where: Mapping[str, Any]) -> bool:
        """Is ``group`` the only key of this where block?"""
        return set(where.keys()) == {"group"}

    def _apply_remove(self, output: Dict[str, OfficialRuleFileFormat]) -> None:
        """Drop matching alerting rules, prune empty groups and empty identifiers."""
        if not self._remove:
            return

        where_blocks: List[Mapping[str, Any]] = [entry["where"] for entry in self._remove]

        def matches_any_remove(group_name: str, rule: Mapping[str, Any]) -> bool:
            # OR semantics across remove entries.
            return any(self._matches(where, group_name, rule) for where in where_blocks)

        for identifier in list(output):
            rule_file = output[identifier]
            kept_groups: List[Any] = []
            for group in cast(List[Any], rule_file.get("groups", [])):
                group_name = str(group.get("name", ""))
                if any(
                    self._is_group_only_selector(where) and where["group"] == group_name
                    for where in where_blocks
                ):
                    # A group-only selector drops the entire group, recording rules included.
                    logger.debug("Removed entire group '%s' from '%s'", group_name, identifier)
                    continue

                kept_rules: List[Any] = []
                for rule in cast(List[Any], group.get("rules", [])):
                    if "alert" not in rule:
                        # Recording rules are never removed unless the whole group is dropped.
                        kept_rules.append(rule)
                        continue
                    if matches_any_remove(group_name, rule):
                        logger.debug(
                            "Removed rule '%s' from group '%s' ('%s')",
                            rule.get("alert"),
                            group_name,
                            identifier,
                        )
                        continue
                    kept_rules.append(rule)

                if kept_rules:
                    group["rules"] = kept_rules
                    kept_groups.append(group)
                else:
                    logger.debug("Pruned empty group '%s' from '%s'", group_name, identifier)

            if kept_groups:
                rule_file["groups"] = kept_groups
            else:
                logger.debug("Dropped identifier '%s': no groups left", identifier)
                del output[identifier]

    def _apply_patch(self, output: Dict[str, OfficialRuleFileFormat]) -> None:
        """Merge each patch's ``set`` block into every matching alerting rule."""
        if not self._patch:
            return

        for identifier, rule_file in output.items():
            for group in cast(List[Any], rule_file.get("groups", [])):
                group_name = str(group.get("name", ""))
                for rule in cast(List[Any], group.get("rules", [])):
                    if "alert" not in rule:
                        # Recording rules are never patched.
                        continue
                    for entry in self._patch:
                        if self._matches(entry["where"], group_name, rule):
                            self._patch_rule(
                                cast(Dict[str, Any], rule), entry["set"], identifier, group_name
                            )

    @staticmethod
    def _patch_rule(
        rule: Dict[str, Any],
        set_block: Mapping[str, Any],
        identifier: str,
        group_name: str,
    ) -> None:
        """Merge a single ``set`` block into a rule, logging what changed."""
        changes: List[str] = []
        if "alert" in set_block:
            changes.append(f"alert={set_block['alert']}")
            rule["alert"] = set_block["alert"]
        if "expr" in set_block:
            changes.append("expr")
            rule["expr"] = set_block["expr"]
        if "for" in set_block:
            changes.append(f"for={set_block['for']}")
            rule["for"] = set_block["for"]
        if "labels" in set_block:
            changes.append(f"labels={set_block['labels']}")
            labels: Dict[Any, Any] = rule.setdefault("labels", {})
            labels.update(set_block["labels"])
        if "annotations" in set_block:
            changes.append(f"annotations={set_block['annotations']}")
            annotations: Dict[Any, Any] = rule.setdefault("annotations", {})
            annotations.update(set_block["annotations"])
        logger.debug(
            "Patched rule '%s' in group '%s' ('%s'): %s",
            rule.get("alert"),
            group_name,
            identifier,
            ", ".join(changes),
        )
