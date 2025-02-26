#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tools for managing worker charm workload configurations."""

import logging
import math
from dataclasses import dataclass
from typing import (
    Callable,
    Dict,
    Iterable,
    Optional,
    Tuple,
)


@dataclass(frozen=True)
class VersionRange:
    """Representation of a range of versions."""

    lower: Tuple[int, int, int]
    lower_inclusive: bool
    upper: Tuple[int, int, int]
    upper_inclusive: bool


class UnversionedWorkersConfig:
    """Responsible for building a worker config.

    Legacy implementation, for single-version worker configurations.
    """

    def __init__(
            self,
            config_generator: Callable[[], str]):
        self._config_generator = config_generator

    def build_config(self) -> str:
        """Build a worker config."""
        return self._config_generator()


class VersionedWorkersConfig:
    """Responsible for building a worker config."""

    def __init__(
            self,
            config_generators: Dict[VersionRange, Callable[[], str]],
            worker_versions: Iterable[str]
    ):
        self._config_generators = config_generators
        self._worker_versions = worker_versions

    def build_config(self) -> str:
        """Build a worker config."""
        version = self.get_version()
        if not version:
            logging.error("something useful")
            # don't send a config if the worker requests a config for a version that is not supported
            return ""
        return self._get_config_generator_for_version(version)()

    def get_version(self) -> Optional[str]:
        """Determines the workload version that the config is intended for."""
        worker_versions = set(self._worker_versions)
        if not worker_versions:
            # if the worker is not yet updated to request a specific config version,
            # return the default supported version
            return self._default_version
        if len(worker_versions) > 1:
            raise RuntimeError("something useful")

        requested_version = worker_versions.pop()

        # return the requested version if it is supported
        if self._get_config_generator_for_version(requested_version):
            return requested_version

        # or None if the worker requested a version that is not supported
        return None

    @property
    def _default_version(self) -> Optional[str]:
        """Returns the lowest supported version."""
        min_version = (math.inf, math.inf, math.inf)
        for version_range, _ in self._config_generators.items():
            if version_range.lower < min_version:
                version_range_lower = version_range.lower
                if version_range.lower_inclusive:
                    min_version = version_range_lower
                else:
                    # if it's not inclusive, increment the patch version by 1
                    min_version = (
                        version_range_lower[0],
                        version_range_lower[1],
                        version_range_lower[2] + 1,
                    )
        if min_version == (math.inf, math.inf, math.inf):
            return None
        return ".".join(map(str, min_version))

    @staticmethod
    def _parse_version(version: str) -> Optional[Tuple[int, int, int]]:
        """Parses a version string into a tuple of (major, minor, patch)."""
        if not version:
            return None
        if version == "0":
            return (0, 0, 0)
        parts = list(map(int, version.split(".")))
        return tuple(parts + [0] * (3 - len(parts)))  # type: ignore

    def _get_config_generator_for_version(self, version: Optional[str]) -> Optional[Callable[[], str]]:
        """Finds the correct builder for this version."""
        parsed_version = self._parse_version(version)
        if not parsed_version:
            return None
        for version_range, builder in self._config_generators.items():
            lower = version_range.lower
            lower_inclusive = version_range.lower_inclusive
            upper = version_range.upper
            upper_inclusive = version_range.upper_inclusive
            if (lower < parsed_version or (lower_inclusive and lower == parsed_version)) and (
                    parsed_version < upper or (upper_inclusive and parsed_version == upper)
            ):
                return builder
        return None
