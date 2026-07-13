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
