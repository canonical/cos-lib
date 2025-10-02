# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
"""Types used by cos-lib."""

from typing import Any, Dict, List, Literal, Optional, TypedDict, Union

from ops.framework import StoredDict, StoredList
from typing_extensions import Required

QueryType = Literal["logql", "promql"]
RuleType = Literal["alert", "record"]


class _RecordingRuleFormat(TypedDict):
    record: Required[str]
    expr: Required[str]
    labels: Dict[str, str]


class _AlertingRuleFormat(TypedDict):
    alert: Required[str]
    expr: Required[str]
    duration: Optional[str]
    keep_firing_for: Optional[str]
    labels: Dict[str, str]
    annotations: Optional[Dict[str, str]]


SingleRuleFormat = Union[_AlertingRuleFormat, _RecordingRuleFormat]


class OfficialRuleFileItem(TypedDict):
    """Typing for a single node of the official rule file format."""

    name: str
    rules: List[SingleRuleFormat]


class OfficialRuleFileFormat(TypedDict):
    """Typing for the official rule file format.

    References:
    - https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
    - https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/
    """

    groups: List[OfficialRuleFileItem]


def type_convert_stored(
    obj: Union[StoredList, StoredDict, Any],
) -> Union[List[Any], Dict[Any, Any], Any]:
    """Helper for converting Stored[Dict|List|Set] to the objects they pretend to be.

    Ref: https://github.com/canonical/operator/pull/572
    """
    if isinstance(obj, StoredList):
        return list(map(type_convert_stored, obj))
    if isinstance(obj, StoredDict):
        rdict: Dict[Any, Any] = {}
        for k in obj.keys():
            rdict[k] = type_convert_stored(obj[k])
        return rdict
    return obj
