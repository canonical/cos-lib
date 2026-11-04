# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for host architecture name normalization."""

from unittest.mock import patch

import pytest

from cosl.architecture import get_host_architecture


@pytest.mark.parametrize(
    "machine, expected",
    [
        ("x86_64", "amd64"),
        ("AMD64", "amd64"),
        ("x64", "amd64"),
        ("amd64", "amd64"),
        ("aarch64", "arm64"),
        ("ARM64", "arm64"),
        ("armv8b", "arm64"),
        ("armv7l", "armhf"),
        ("armv7hl", "armhf"),
        ("armv8l", "armhf"),
        ("i386", "i386"),
        ("i686", "i386"),
        ("ppc", "powerpc"),
        ("ppc64le", "ppc64el"),
        ("riscv64", "riscv64"),
        ("s390x", "s390x"),
        ("mips64", "mips64"),
        ("", ""),
    ],
)
def test_get_host_architecture(machine: str, expected: str) -> None:
    with patch("cosl.architecture.platform.machine", return_value=machine) as mocked_machine:
        assert get_host_architecture() == expected
        mocked_machine.assert_called_once_with()
