# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Test the round-trip encoding/decoding of the LZMABase64 class."""

import json

import pytest

from cosl import LZMABase64


def test_decompress_invalid_data():
    # Should raise an error for corrupted input
    with pytest.raises(Exception):
        LZMABase64.decompress("not-a-valid-base64")


@pytest.mark.parametrize("non_str", [123, 45.6, [1, 2, 3], {"a": 1}])
def test_compress_non_string(non_str):
    with pytest.raises(Exception):
        LZMABase64.compress(non_str)


def test_round_trip_dict():
    d = {
        "some": "dict",
        "with": "keys",
        "even": [{"nested": "types", "and_integers": [42, 42]}],
    }
    assert d == json.loads(LZMABase64.decompress(LZMABase64.compress(json.dumps(d))))


@pytest.mark.parametrize(
    "input",
    [
        "simple string",
        "string with emojis: 😀🚀🌟",
        "",  # empty string
        " " * 100,  # whitespace only
        "!@#$%^&*()_+-=[]{}|;':,./<>?",  # special characters
        "\n\t\r",  # only escape sequences
        "a" * 10000,  # very large string
        bytes([0, 255, 127, 10, 20, 30]).hex(),  # binary data encoded as string
    ],
)
def test_round_trip(input):
    assert input == LZMABase64.decompress(LZMABase64.compress(input))
