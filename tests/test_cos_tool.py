# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import PosixPath

from cosl import CosTool
from cosl.cos_tool import _exec, clear_exec_cache, configure_cache


def spy_on_cos_tool():
    """Patch ``subprocess.run`` to still run the real binary while counting calls.

    Returns a patcher whose mock has ``side_effect=real_run``, so the real cos-tool
    binary is executed (real output) while ``call_count`` lets a test assert whether the
    cache avoided a subprocess. Use as a context manager: ``with spy_on_cos_tool() as spy``.
    """
    return unittest.mock.patch("cosl.cos_tool.subprocess.run", side_effect=subprocess.run)


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
        clear_exec_cache()
        self.addCleanup(clear_exec_cache)
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
        clear_exec_cache()
        # Revert to a process-local temporary cache after each test.
        self.addCleanup(configure_cache, None)

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

    def test_temporary_cache_when_unconfigured(self):
        """Without configure_cache, memoization still works within the process."""
        # GIVEN no cache directory configured (process-local temporary cache)
        clear_exec_cache()
        with unittest.mock.patch(
            "cosl.cos_tool.subprocess.run",
            return_value=unittest.mock.Mock(stdout=b"x"),
        ) as mock_run:
            # WHEN the same command is executed twice
            first = _exec(["cmd"], cache_key=("k",))
            second = _exec(["cmd"], cache_key=("k",))

            # THEN it is memoized in-process: same result, only one subprocess
            self.assertEqual(first, "x")
            self.assertEqual(second, "x")
            self.assertEqual(mock_run.call_count, 1)

    def test_reconfigure_to_none_starts_fresh(self):
        """Reverting to a temporary cache does not see the previous directory's data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # GIVEN a value cached in a persistent directory
            configure_cache(tmpdir)
            with unittest.mock.patch(
                "cosl.cos_tool.subprocess.run",
                return_value=unittest.mock.Mock(stdout=b"persisted"),
            ):
                _exec(["cmd"], cache_key=("k",))

            # WHEN the cache is reconfigured to a fresh temporary one
            configure_cache(None)
            with unittest.mock.patch(
                "cosl.cos_tool.subprocess.run",
                return_value=unittest.mock.Mock(stdout=b"fresh"),
            ) as mock_run:
                out = _exec(["cmd"], cache_key=("k",))

                # THEN the previous directory's data is not visible: the binary runs again
                self.assertEqual(out, "fresh")
                self.assertEqual(mock_run.call_count, 1)


class TestValidateCaching(unittest.TestCase):
    """Validation must be memoized by rule content, not by the tempfile path."""

    def setUp(self):
        clear_exec_cache()
        self.addCleanup(clear_exec_cache)
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
        clear_exec_cache()
        self.addCleanup(clear_exec_cache)
        self.addCleanup(configure_cache, None)
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
