# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import unittest

from cosl import GrafanaDashboard, LZMABase64, generate_dashboard_uid


class TestRoundTripEncDec(unittest.TestCase):
    """Tests the round-trip encoding/decoding of the GrafanaDashboard class."""

    def test_round_trip(self):
        d = {
            "some": "dict",
            "with": "keys",
            "even": [{"nested": "types", "and_integers": [42, 42]}],
        }
        self.assertDictEqual(d, GrafanaDashboard._serialize(json.dumps(d))._deserialize())


class TestLZMABase64(unittest.TestCase):
    """Tests the round-trip encoding/decoding of the GrafanaDashboard class."""

    def test_round_trip(self):
        s = "starting point"
        self.assertEqual(s, LZMABase64.decompress(LZMABase64.compress(s)))


class TestGenerateUID(unittest.TestCase):
    """Spec for the UID generation logic."""

    def test_uid_length_is_40(self):
        self.assertEqual(40, len(generate_dashboard_uid("whatever")))

    def test_collisions(self):
        """A very naive and primitive collision check that is meant to catch trivial errors."""
        self.assertNotEqual(
            generate_dashboard_uid("some-charm", "dashboard1.json"),
            generate_dashboard_uid("some-charm", "dashboard2.json"),
        )

        self.assertNotEqual(
            generate_dashboard_uid("some-charm"),
            generate_dashboard_uid("some-charm", "dashboard.json"),
        )
