# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Helpers for working with host CPU architecture names."""

import platform

# Convert ``platform.machine()`` identifiers to Debian/Snap architecture names.
# The 32-bit armv8l variant deliberately maps to armhf, as in craft-parts.
_ARCHITECTURE_ALIASES = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "x64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
    "armv8b": "arm64",
    "armv7l": "armhf",
    "armv7hl": "armhf",
    "armv8l": "armhf",
    "i386": "i386",
    "i686": "i386",
    "ppc": "powerpc",
    "ppc64le": "ppc64el",
}


def get_host_architecture() -> str:
    """Return the host architecture using Debian/Snap aliases where known.

    Unknown machine names are returned unchanged. ``platform.machine()`` is
    used instead of ``platform.processor()``, which can be empty on Linux.
    """
    machine = platform.machine()
    return _ARCHITECTURE_ALIASES.get(machine.lower(), machine)
