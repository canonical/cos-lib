# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import os
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import PosixPath

import cosl.cos_tool as cos_tool
from cosl import CosTool
from cosl.cos_tool import _exec, configure_cache


def spy_on_cos_tool():
    """Patch ``subprocess.run`` to still run the real binary while counting calls.

    Returns a patcher whose mock has ``side_effect=real_run``, so the real cos-tool
    binary is executed (real output) while ``call_count`` lets a test assert whether the
    cache avoided a subprocess. Use as a context manager: ``with spy_on_cos_tool() as spy``.
    """
    return unittest.mock.patch("cosl.cos_tool.subprocess.run", side_effect=subprocess.run)


def isolate_cache(test_case):
    """Point the cache at a fresh temp dir for the duration of ``test_case``.

    Keeps tests off the shared default location (``/tmp/cosl-cos-tool``) so they neither
    read stale entries nor pollute it, and restores the default when the test finishes.
    """
    tmp = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp.cleanup)
    test_case.addCleanup(configure_cache, None)
    configure_cache(tmp.name)
    return tmp.name


class TestTool(unittest.TestCase):
    """Test that the cos-tool base implementation works."""

    def assert_type_error_helper(self, func, *args, **kwargs):
        with self.assertRaises(TypeError) as cm:
            func(*args, **kwargs)
        self.assertIn("Either a default query", str(cm.exception))

    # pylint: disable=protected-access
    @unittest.mock.patch("platform.machine", lambda: "teakettle")
    def test_disable_on_invalid_arch(self):
        tool = CosTool(default_query_type="logql")
        self.assertIsNone(tool.path)
        self.assertTrue(tool._disabled)

    # pylint: disable=protected-access
    @unittest.mock.patch("platform.machine", lambda: "x86_64")
    def test_gives_path_on_valid_arch(self):
        """When given a valid arch, it should return the binary path."""
        tool = CosTool(default_query_type="promql")
        self.assertIsInstance(tool.path, PosixPath)

    @unittest.mock.patch("platform.machine", lambda: "x86_64")
    def test_setup_transformer(self):
        """When setup it should know the path to the binary."""
        tool = CosTool(default_query_type="promql")

        self.assertIsInstance(tool.path, PosixPath)

        p = str(tool.path)
        self.assertTrue(p.endswith("cos-tool-amd64"))

    @unittest.mock.patch("platform.machine", lambda: "x86_64")
    def test_typeerror_is_raised_if_no_query_is_used(self):
        """If no default query type or querytpye is set, it should raise."""
        tool = CosTool()

        self.assert_type_error_helper(tool.apply_label_matchers, rules={})
        self.assert_type_error_helper(tool.validate_alert_rules, rules={})
        self.assert_type_error_helper(tool.inject_label_matchers, expression="", topology={})

        p = str(tool.path)
        self.assertTrue(p.endswith("cos-tool-amd64"))


class TestExecCache(unittest.TestCase):
    """Test that cos-tool invocations are memoized to avoid redundant subprocess calls."""

    def setUp(self):
        isolate_cache(self)
        # These tests run the real binary (resolved as cos-tool-<arch> in CWD).
        if CosTool(default_query_type="promql").path is None:
            self.skipTest("real cos-tool binary not available")

    def test_identical_expressions_run_subprocess_once(self):
        """Identical expressions should spawn the subprocess only once."""
        # GIVEN a CosTool and an expression + topology
        tool = CosTool(default_query_type="promql")
        topology = {"juju_model": "my_model", "juju_application": "app"}

        # WHEN the same expression is transformed twice
        with spy_on_cos_tool() as spy:
            first = tool.inject_label_matchers("up", topology)
            second = tool.inject_label_matchers("up", topology)

        # THEN both calls return the same (real) result and cos-tool ran only once
        self.assertEqual(first, second)
        self.assertEqual(spy.call_count, 1)

    def test_different_expressions_run_subprocess_each(self):
        """Different expressions should each spawn a subprocess."""
        # GIVEN a CosTool
        tool = CosTool(default_query_type="promql")

        # WHEN two different expressions are transformed
        with spy_on_cos_tool() as spy:
            tool.inject_label_matchers("up", {"juju_model": "m"})
            tool.inject_label_matchers("down", {"juju_model": "m"})

        # THEN cos-tool runs once per distinct expression
        self.assertEqual(spy.call_count, 2)


class TestExecCachePersistence(unittest.TestCase):
    """Test on-disk persistence of the cos-tool cache across processes."""

    def setUp(self):
        # Isolate every test from the shared default cache: point at a fresh temp dir and
        # restore the default afterwards so tests neither read nor pollute /tmp/cosl-cos-tool.
        isolate_cache(self)

    def test_persisted_cache_reused_across_processes(self):
        """Results written under a directory are reused after reconfiguring to it.

        Reconfiguring to the same directory simulates a brand-new process (a fresh
        Juju event) pointed at the same persistent storage.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # GIVEN a persistent cache populated by running cos-tool once
            configure_cache(tmpdir)
            with unittest.mock.patch(
                "cosl.cos_tool.subprocess.run",
                return_value=unittest.mock.Mock(stdout=b"transformed"),
            ) as mock_run:
                out = _exec(["cos-tool", "transform", "up"], cache_key=("k", "1"))
                self.assertEqual(out, "transformed")
                self.assertEqual(mock_run.call_count, 1)

            # WHEN a brand-new process reopens the cache at the same directory
            configure_cache(tmpdir)
            with unittest.mock.patch("cosl.cos_tool.subprocess.run") as mock_run:
                out = _exec(["cos-tool", "transform", "up"], cache_key=("k", "1"))

                # THEN the value is served from disk without spawning the subprocess
                self.assertEqual(out, "transformed")
                self.assertEqual(mock_run.call_count, 0)

    def test_cache_memoizes_within_a_directory(self):
        """A configured cache memoizes: identical calls run the subprocess only once."""
        # GIVEN a cache pointed at a directory (the setUp temp dir)
        with unittest.mock.patch(
            "cosl.cos_tool.subprocess.run",
            return_value=unittest.mock.Mock(stdout=b"x"),
        ) as mock_run:
            # WHEN the same command is executed twice
            first = _exec(["cmd"], cache_key=("k",))
            second = _exec(["cmd"], cache_key=("k",))

            # THEN it is memoized: same result, only one subprocess
            self.assertEqual(first, "x")
            self.assertEqual(second, "x")
            self.assertEqual(mock_run.call_count, 1)

    def test_reconfigure_switches_directory(self):
        """Reconfiguring to a different directory does not see the previous one's data."""
        # GIVEN a value cached in the current (setUp) directory
        with unittest.mock.patch(
            "cosl.cos_tool.subprocess.run",
            return_value=unittest.mock.Mock(stdout=b"first-dir"),
        ):
            _exec(["cmd"], cache_key=("k",))

        # WHEN the cache is repointed at a different, empty directory
        with tempfile.TemporaryDirectory() as other_dir:
            configure_cache(other_dir)
            with unittest.mock.patch(
                "cosl.cos_tool.subprocess.run",
                return_value=unittest.mock.Mock(stdout=b"second-dir"),
            ) as mock_run:
                out = _exec(["cmd"], cache_key=("k",))

                # THEN the first directory's data is not visible: the binary runs again
                self.assertEqual(out, "second-dir")
                self.assertEqual(mock_run.call_count, 1)

    def test_default_cache_location(self):
        """Without configure_cache (or with None), the cache uses the shared default dir."""
        # WHEN the cache is reset to its default
        configure_cache(None)

        # THEN the target directory is the fixed, shared location under /tmp
        self.assertEqual(cos_tool._cache_dir, cos_tool._DEFAULT_CACHE_DIR)
        self.assertEqual(cos_tool._DEFAULT_CACHE_DIR, "/tmp/cosl-cos-tool")

    def test_import_has_no_filesystem_side_effects(self):
        """Opening the cache is lazy: configuring a dir must not create it eagerly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "not-created-yet")
            # WHEN a directory is configured but the cache is never used
            configure_cache(target)

            # THEN the directory is not created until first use
            self.assertFalse(os.path.exists(target))
            self.assertIsNone(cos_tool._exec_cache)

    def test_cache_uses_lru_eviction(self):
        """The cache evicts least-recently-*used* entries, not least-recently-stored."""
        # WHEN the cache is opened
        cache = cos_tool._get_cache()

        # THEN it is configured with the least-recently-used eviction policy
        self.assertEqual(cache.eviction_policy, "least-recently-used")

    def test_changed_binary_fingerprint_invalidates_cache(self):
        """A changed binary fingerprint must miss the cache instead of serving stale output."""
        cos_tool._binary_fingerprint.cache_clear()
        self.addCleanup(cos_tool._binary_fingerprint.cache_clear)

        # GIVEN a value cached under one binary fingerprint
        with unittest.mock.patch.object(cos_tool, "_fingerprint", return_value="fp-v1"):
            with unittest.mock.patch(
                "cosl.cos_tool.subprocess.run",
                return_value=unittest.mock.Mock(stdout=b"v1-output"),
            ):
                first = _exec(["cos-tool", "transform", "up"], cache_key=("k",))
                self.assertEqual(first, "v1-output")

        # WHEN the binary fingerprint changes (e.g. the binary was replaced)
        with unittest.mock.patch.object(cos_tool, "_fingerprint", return_value="fp-v2"):
            with unittest.mock.patch(
                "cosl.cos_tool.subprocess.run",
                return_value=unittest.mock.Mock(stdout=b"v2-output"),
            ) as mock_run:
                out = _exec(["cos-tool", "transform", "up"], cache_key=("k",))

                # THEN it is a cache miss: the binary runs again, no stale value served
                self.assertEqual(out, "v2-output")
                self.assertEqual(mock_run.call_count, 1)


class TestValidateCaching(unittest.TestCase):
    """Validation must be memoized by rule content, not by the tempfile path."""

    def setUp(self):
        isolate_cache(self)
        # Runs the real binary (resolved as cos-tool-<arch> in CWD).
        if CosTool(default_query_type="promql").path is None:
            self.skipTest("real cos-tool binary not available")

    def test_identical_rules_validated_once(self):
        """Validating identical rules twice should spawn the subprocess only once."""
        # GIVEN a CosTool and a set of rules
        tool = CosTool(default_query_type="promql")
        rules = {"groups": [{"name": "g", "rules": [{"alert": "A", "expr": "up"}]}]}

        # WHEN the same rules are validated twice
        with spy_on_cos_tool() as spy:
            first_ok, _ = tool.validate_alert_rules(rules)
            second_ok, _ = tool.validate_alert_rules(rules)

        # THEN both validate successfully and cos-tool ran only once.
        # (Previously this was 2 because the random tempfile path defeated memoization.)
        self.assertTrue(first_ok)
        self.assertTrue(second_ok)
        self.assertEqual(spy.call_count, 1)


class TestCacheFidelity(unittest.TestCase):
    """The cached value must be byte-identical to what the real cos-tool binary returns.

    These tests do NOT mock cos-tool: they run the real binary once (populating the cache),
    then read back from the cache, and assert the two results are identical. This guards
    the memoization layer we introduced between the caller and the binary.
    """

    def setUp(self):
        isolate_cache(self)
        # These tests require the real cos-tool binary (resolved as cos-tool-<arch> in CWD).
        if CosTool(default_query_type="promql").path is None:
            self.skipTest("real cos-tool binary not available")

    def _assert_cached_equals_binary(self, call):
        """Run ``call`` twice (miss then hit) and assert identical output from the cache.

        Encapsulates the WHEN/THEN of the fidelity tests: it also asserts the second call
        is served from the cache (no subprocess), so a deterministic binary can't make the
        test pass without the cache working.

        Args:
            call: a zero-arg callable that invokes cos-tool via the library.
        """
        with spy_on_cos_tool() as spy:
            # WHEN the call runs the first time (cache miss -> runs the real binary)
            from_binary = call()
            runs_after_first = spy.call_count
            self.assertGreaterEqual(runs_after_first, 1, "first call should run the binary")

            # WHEN the same call runs again (cache hit -> should not run the binary)
            from_cache = call()
            # THEN the second call is served from the cache (no extra subprocess)
            self.assertEqual(
                spy.call_count,
                runs_after_first,
                "second call must be served from the cache (no extra subprocess)",
            )

        # THEN the cached value is byte-identical to the binary's output
        self.assertEqual(from_binary, from_cache, "cached value differs from binary output")
        return from_binary

    def test_inject_label_matchers_cached_equals_binary(self):
        """Transformed expression from cache is identical to the binary's output."""
        # GIVEN a CosTool and an expression + topology
        tool = CosTool(default_query_type="promql")
        topology = {"juju_model": "m", "juju_model_uuid": "uuid", "juju_application": "app"}

        # WHEN it is transformed (miss) and then read back (hit)
        # THEN both are identical (asserted in the helper)
        result = self._assert_cached_equals_binary(
            lambda: tool.inject_label_matchers("up == 0", topology)
        )
        # THEN the binary actually injected the labels (not a passthrough)
        self.assertIn("juju_application", result)

    def test_cached_value_survives_fresh_cache_open(self):
        """A value written to disk is read back identically after reopening the cache.

        This mirrors a fresh Juju event: a new process opens the persisted cache and must
        get exactly what the binary produced in a previous process.
        """
        tool = CosTool(default_query_type="promql")
        topology = {"juju_model": "m", "juju_application": "app"}
        with tempfile.TemporaryDirectory() as tmpdir:
            # GIVEN an expression transformed by the real binary into a persistent cache
            configure_cache(tmpdir)
            with spy_on_cos_tool():
                from_binary = tool.inject_label_matchers("up == 0", topology)

            # WHEN a fresh process reopens the cache and requests the same expression
            configure_cache(tmpdir)
            with unittest.mock.patch("cosl.cos_tool.subprocess.run") as spy:
                from_reopened_cache = tool.inject_label_matchers("up == 0", topology)
                # THEN the value comes from the cache (no subprocess)
                self.assertEqual(spy.call_count, 0, "value should come from the reopened cache")

            # THEN the reopened-cache value is identical to the binary's original output
            self.assertEqual(from_binary, from_reopened_cache)
