# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Types used by cos-lib."""

from typing import Any, Dict, Final, List, Literal, Union

from ops.framework import StoredDict, StoredList
from typing_extensions import NotRequired, Required, TypedDict

QueryType = Literal["logql", "promql"]
RuleType = Literal["alert", "record"]
RULE_TYPES: Final = frozenset({"alert", "record"})


class RecordingRuleFormat(TypedDict):
    """A custom single rule format for recording rules.

    The official format is a YAML file conforming to the Prometheus/Cortex documentation
    (https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/).
    The custom single rule format is a subsection of the official YAML, having a single recording
    rule, effectively "one record per file".
    """
    record: Required[str]
    expr: Required[str]
    labels: NotRequired[Dict[str, str]]


class AlertingRuleFormat(TypedDict):
    """A custom single rule format for alerting rules.

    The official format is a YAML file conforming to the Prometheus/Cortex documentation
    (https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/).
    The custom single rule format is a subsection of the official YAML, having a single alert
    rule, effectively "one alert per file".
    """
    alert: Required[str]
    expr: Required[str]
    duration: NotRequired[str]
    keep_firing_for: NotRequired[str]
    labels: NotRequired[Dict[str, str]]
    annotations: NotRequired[Dict[str, str]]


SingleRuleFormat = Union[AlertingRuleFormat, RecordingRuleFormat]


class OfficialRuleFileItem(TypedDict):
    """Typing for a single node of the official rule file format."""

    name: str
    rules: List[SingleRuleFormat]


class OfficialRuleFileFormat(TypedDict, total=False):
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
