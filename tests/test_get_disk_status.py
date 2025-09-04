# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.


from unittest.mock import patch

import ops
import pytest

from cosl.statuses import get_disk_usage_status


@pytest.mark.parametrize(
    "free_space,expected_status",
    [
        (1024**4, ops.ActiveStatus()),
        (1024**3, ops.ActiveStatus()),
        (1024**3 - 1, ops.BlockedStatus()),
        (0, ops.BlockedStatus()),
        (-1, ops.BlockedStatus()),
    ],
)
def test_get_disk_usage_status(free_space, expected_status):
    with patch("shutil.disk_usage") as mock_disk_usage:
        mock_disk_usage.return_value.free = free_space
        unit_status = get_disk_usage_status(location="/foo/bar")

        assert type(unit_status) is type(expected_status)
