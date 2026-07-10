# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
import unittest.mock
from pathlib import PosixPath

from cosl import CosTool
from cosl.cos_tool import clear_exec_cache


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

    @unittest.mock.patch("cosl.cos_tool.subprocess.run")
    def test_identical_commands_run_subprocess_once(self, mock_run):
        """Identical cos-tool invocations should spawn the subprocess only once."""
        mock_run.return_value = unittest.mock.Mock(stdout=b"transformed")
        tool = CosTool(default_query_type="promql")

        first = tool._exec(
            [
                "cos-tool",
                "--format",
                "promql",
                "transform",
                "--label-matcher=juju_model='my_model'",
                "--label-matcher=juju_application='app'",
                "-label-matcher=juju_unit='app/0'",
            ]
        )
        second = tool._exec(
            [
                "cos-tool",
                "--format",
                "promql",
                "transform",
                "--label-matcher=juju_model='my_model'",
                "--label-matcher=juju_application='app'",
                "-label-matcher=juju_unit='app/0'",
            ]
        )

        self.assertEqual(first, "transformed")
        self.assertEqual(second, "transformed")
        # The subprocess should have run only once; the second call is served from cache.
        self.assertEqual(mock_run.call_count, 1)

    @unittest.mock.patch("cosl.cos_tool.subprocess.run")
    def test_different_commands_run_subprocess_each(self, mock_run):
        """Distinct cos-tool invocations should each spawn a subprocess."""
        mock_run.return_value = unittest.mock.Mock(stdout=b"out")
        tool = CosTool(default_query_type="promql")

        tool._exec(
            [
                "cos-tool",
                "--format",
                "promql",
                "transform",
                "--label-matcher=juju_model='my_model'",
                "--label-matcher=juju_application='app'",
                "-label-matcher=juju_unit='app/0'",
            ]
        )
        tool._exec(
            [
                "cos-tool",
                "--format",
                "promql",
                "transform",
                "--label-matcher=juju_model='my_model'",
                "--label-matcher=juju_application='app'",
                "-label-matcher=juju_unit='app/1'",
            ]
        )

        self.assertEqual(mock_run.call_count, 2)

    @unittest.mock.patch("cosl.cos_tool.subprocess.run")
    def test_cache_shared_across_instances(self, mock_run):
        """The cache is shared across CosTool instances (they are created per-ruleset)."""
        mock_run.return_value = unittest.mock.Mock(stdout=b"x")
        cmd = ["cos-tool", "--format", "promql", "transform", "--", "up"]

        CosTool(default_query_type="promql")._exec(cmd)
        CosTool(default_query_type="promql")._exec(cmd)

        self.assertEqual(mock_run.call_count, 1)
