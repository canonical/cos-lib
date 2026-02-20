# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Utility functions and classes."""

import base64
import lzma
from typing import Union


class LZMABase64:
    """A helper class for LZMA-compressed-base64-encoded strings.

    This is useful for transferring over juju relation data, which can only have keys of type string.
    """

    @classmethod
    def compress(cls, raw_json: Union[str, bytes]) -> str:
        """LZMA-compress and base64-encode into a string."""
        if not isinstance(raw_json, bytes):
            raw_json = raw_json.encode("utf-8")
        return base64.b64encode(lzma.compress(raw_json)).decode("utf-8")

    @classmethod
    def decompress(cls, compressed: str) -> str:
        """Decompress from base64-encoded-lzma-compressed string."""
        return lzma.decompress(base64.b64decode(compressed.encode("utf-8"))).decode()
