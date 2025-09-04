# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
"""Helper functions for calculating 'pull statuses'.

Ref: https://discourse.charmhub.io/t/its-probably-ok-for-a-unit-to-go-into-error-state/13022
"""

import logging
import shutil

import ops

logger = logging.getLogger(__name__)


def get_disk_usage_status(location: str, *, threshold: int = 1024**3) -> ops.StatusBase:
    """Returns a status that matches the disk usage.

    Returns:
     - ActiveStatus when the provided <location> has more <threshold> bytes;
     - BlockedStatus when <location> is below <threshold>;
     - MaintenanceStatus when the <location> is not found i.e. before storage is attached.
    """
    try:
        # NOTE: we measure the disk space from the charm container because it shares the same storage as the workload container
        free_disk_space = shutil.disk_usage(location).free
        if free_disk_space < threshold:
            logger.warning(f"Less than 1GiB of disk space remaining in {location}")
            return ops.BlockedStatus("<1 GiB remaining")

        else:
            return ops.ActiveStatus()
    # If this check is done before storage is attached, we don't want the charm to go error state
    except FileNotFoundError:
        logger.debug(
            f"Storage not available in {location}. Did we get a storage attached hook yet?"
        )
        return ops.MaintenanceStatus("Storage not available")
