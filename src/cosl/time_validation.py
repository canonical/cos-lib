# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
"""Helper function(s) for determining for determining the validity of time options."""

import re


def is_valid_timespec(timeval: str) -> bool:
    """Returns a boolean based on whether the passed parameter is a valid timespec.

    Upstream ref: https://github.com/prometheus/prometheus/blob/c40e269c3e514953299e9ba1f6265e067ab43e64/cmd/prometheus/main.go#L302

    Args:
        timeval: a string representing a time specification, e.g., "1d", "1w".

    Returns:
        True if time specification is valid and False otherwise.
        The regex in this function returns True when the parameter is 0 or when it uses one of the following units:
        - y for years
        - m for months
        - w for weeks
        - d for days
        - h for hours
        - m for minutes
        - s for seconds
        - ms for milliseconds.
        Otherwise, it returns False.
    """
    timespec_re = re.compile(
        r"^((([0-9]+)y)?(([0-9]+)w)?(([0-9]+)d)?(([0-9]+)h)?(([0-9]+)m)?(([0-9]+)s)?(([0-9]+)ms)?|0)$"
    )
    matched = timespec_re.search(timeval)
    return bool(matched)
