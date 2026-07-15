# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
import unittest.mock
from pathlib import PosixPath

from cosl import CosTool
from cosl.cos_tool import _exec, clear_exec_cache, configure_cache


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

    @unittest.mock.patch("cosl.cos_tool.CosTool._get_tool_path")
    @unittest.mock.patch("cosl.cos_tool.subprocess.run")
    def test_identical_expressions_run_subprocess_once(self, mock_run, mock_get_path):
        """Identical expressions should spawn the subprocess only once."""
        mock_get_path.return_value = PosixPath("/usr/bin/cos-tool-amd64")
        mock_run.return_value = unittest.mock.Mock(stdout=b"up{juju_model='my_model'}")
        tool = CosTool(default_query_type="promql")
        topology = {"juju_model": "my_model", "juju_application": "app"}

        first = tool.inject_label_matchers("up", topology)
        second = tool.inject_label_matchers("up", topology)

        self.assertEqual(first, "up{juju_model='my_model'}")
        self.assertEqual(second, "up{juju_model='my_model'}")
        self.assertEqual(mock_run.call_count, 1)

    @unittest.mock.patch("cosl.cos_tool.CosTool._get_tool_path")
    @unittest.mock.patch("cosl.cos_tool.subprocess.run")
    def test_different_expressions_run_subprocess_each(self, mock_run, mock_get_path):
        """Different expressions should each spawn a subprocess."""
        mock_get_path.return_value = PosixPath("/usr/bin/cos-tool-amd64")
        mock_run.return_value = unittest.mock.Mock(stdout=b"result")
        tool = CosTool(default_query_type="promql")

        tool.inject_label_matchers("up", {"juju_model": "m"})
        tool.inject_label_matchers("down", {"juju_model": "m"})

        self.assertEqual(mock_run.call_count, 2)

    @unittest.mock.patch("cosl.cos_tool.CosTool._get_tool_path")
    @unittest.mock.patch("cosl.cos_tool.subprocess.run")
    def test_cache_shared_across_instances(self, mock_run, mock_get_path):
        """The cache is shared across CosTool instances."""
        mock_get_path.return_value = PosixPath("/usr/bin/cos-tool-amd64")
        mock_run.return_value = unittest.mock.Mock(stdout=b"result")
        topology = {"juju_model": "my_model"}

        CosTool(default_query_type="promql").inject_label_matchers("up", topology)
        CosTool(default_query_type="promql").inject_label_matchers("up", topology)

        self.assertEqual(mock_run.call_count, 1)


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
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            configure_cache(tmpdir)
            with unittest.mock.patch(
                "cosl.cos_tool.subprocess.run",
                return_value=unittest.mock.Mock(stdout=b"transformed"),
            ) as mock_run:
                out = _exec(["cos-tool", "transform", "up"], cache_key=("k", "1"))
                self.assertEqual(out, "transformed")
                self.assertEqual(mock_run.call_count, 1)

            # Simulate a brand-new process: reopen the cache at the same directory.
            configure_cache(tmpdir)
            with unittest.mock.patch("cosl.cos_tool.subprocess.run") as mock_run:
                out = _exec(["cos-tool", "transform", "up"], cache_key=("k", "1"))
                self.assertEqual(out, "transformed")
                # No subprocess spawned: served from the on-disk cache.
                self.assertEqual(mock_run.call_count, 0)

    def test_temporary_cache_when_unconfigured(self):
        """Without configure_cache, memoization still works within the process."""
        clear_exec_cache()
        with unittest.mock.patch(
            "cosl.cos_tool.subprocess.run",
            return_value=unittest.mock.Mock(stdout=b"x"),
        ) as mock_run:
            first = _exec(["cmd"], cache_key=("k",))
            second = _exec(["cmd"], cache_key=("k",))
            self.assertEqual(first, "x")
            self.assertEqual(second, "x")
            # Memoized: only one subprocess even without a configured directory.
            self.assertEqual(mock_run.call_count, 1)

    def test_reconfigure_to_none_starts_fresh(self):
        """Reverting to a temporary cache does not see the previous directory's data."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            configure_cache(tmpdir)
            with unittest.mock.patch(
                "cosl.cos_tool.subprocess.run",
                return_value=unittest.mock.Mock(stdout=b"persisted"),
            ):
                _exec(["cmd"], cache_key=("k",))

            configure_cache(None)  # fresh temporary cache
            with unittest.mock.patch(
                "cosl.cos_tool.subprocess.run",
                return_value=unittest.mock.Mock(stdout=b"fresh"),
            ) as mock_run:
                out = _exec(["cmd"], cache_key=("k",))
                self.assertEqual(out, "fresh")
                self.assertEqual(mock_run.call_count, 1)


class TestValidateCaching(unittest.TestCase):
    """Validation must be memoized by rule content, not by the tempfile path."""

    def setUp(self):
        clear_exec_cache()
        self.addCleanup(clear_exec_cache)

    @unittest.mock.patch("cosl.cos_tool.CosTool._get_tool_path")
    @unittest.mock.patch("cosl.cos_tool.subprocess.run")
    def test_identical_rules_validated_once(self, mock_run, mock_get_path):
        """Validating identical rules twice should spawn the subprocess only once."""
        mock_get_path.return_value = PosixPath("/usr/bin/cos-tool-amd64")
        mock_run.return_value = unittest.mock.Mock(stdout=b"")
        tool = CosTool(default_query_type="promql")
        rules = {"groups": [{"name": "g", "rules": [{"alert": "A", "expr": "up"}]}]}

        first_ok, _ = tool.validate_alert_rules(rules)
        second_ok, _ = tool.validate_alert_rules(rules)

        self.assertTrue(first_ok)
        self.assertTrue(second_ok)
        # Previously this was 2 because the random tempfile path defeated memoization.
        self.assertEqual(mock_run.call_count, 1)
