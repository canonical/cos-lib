# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import unittest

from cosl import DashboardPath40UID, GrafanaDashboard, LZMABase64


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

    def test_generate_no_arguments_raises_error(self):
        """Test that generate raises ValueError when no arguments are provided."""
        with self.assertRaises(ValueError) as context:
            DashboardPath40UID.generate()
        self.assertIn("At least one string argument is required", str(context.exception))

    def test_generate_basic_functionality(self):
        """Test basic UID generation with common scenarios."""
        # Test with single argument
        uid1 = DashboardPath40UID.generate("my-charm")
        self.assertEqual(40, len(uid1))
        self.assertTrue(DashboardPath40UID.is_valid(uid1))

        # Test with multiple arguments
        uid2 = DashboardPath40UID.generate("my-charm", "dashboard.json", "v2", "production")
        self.assertEqual(40, len(uid2))
        self.assertTrue(DashboardPath40UID.is_valid(uid2))

        # Test backward compatibility with original signature
        uid3 = DashboardPath40UID.generate("some-charm", "dashboard.json")
        self.assertEqual(40, len(uid3))
        self.assertTrue(DashboardPath40UID.is_valid(uid3))

    def test_generate_deterministic_behavior(self):
        """Test that the same arguments produce the same UID (deterministic)."""
        test_cases = [
            ("single_arg",),
            ("my-charm", "dashboard.json"),
            ("my-charm", "dashboard.json", "v2", "production"),
        ]

        for args in test_cases:
            uid1 = DashboardPath40UID.generate(*args)
            uid2 = DashboardPath40UID.generate(*args)
            self.assertEqual(uid1, uid2, f"UIDs should be identical for args: {args}")

    def test_generate_uniqueness_across_combinations(self):
        """Test that different argument combinations produce unique UIDs."""
        combinations = [
            ("some-charm", "dashboard1.json"),
            ("some-charm", "dashboard2.json"),
            ("diff-charm", "dashboard.json"),
            ("arg1",),
            ("arg1", "arg2"),
            ("arg1", "arg2", "arg3"),
            ("arg2", "arg1"),  # Different order
        ]

        uids = [DashboardPath40UID.generate(*args) for args in combinations]

        # All UIDs should be unique
        for i in range(len(uids)):
            for j in range(i + 1, len(uids)):
                self.assertNotEqual(
                    uids[i],
                    uids[j],
                    f"UIDs should be different: {combinations[i]} vs {combinations[j]}",
                )

    def test_is_valid_edge_cases(self):
        """Test validity check with edge cases."""
        # Invalid cases
        self.assertFalse(DashboardPath40UID.is_valid("1234"))
        self.assertFalse(DashboardPath40UID.is_valid("short non-hex string"))
        self.assertFalse(DashboardPath40UID.is_valid("non-hex string, crafted to be 40 chars!!"))
        self.assertFalse(DashboardPath40UID.is_valid(""))
        self.assertFalse(DashboardPath40UID.is_valid(None))  # type: ignore
        self.assertFalse(DashboardPath40UID.is_valid(False))  # type: ignore

        # Valid cases
        self.assertTrue(DashboardPath40UID.is_valid("0" * 40))
        self.assertTrue(
            DashboardPath40UID.is_valid("a1b2c3d4e5f6789012345678901234567890abcd")
        )  # 40 chars
        # Generated UIDs should always be valid (covered by other tests but explicitly stated here)
        sample_uid = DashboardPath40UID.generate("test", "sample")
        self.assertTrue(DashboardPath40UID.is_valid(sample_uid))
