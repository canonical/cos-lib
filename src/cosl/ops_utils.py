# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Utilities extending the functionality of ops."""

import re

from ops import ModelError, Relation


def is_cmr(relation: Relation) -> bool:
    """Temporary workaround for checking if the given relation is a cross-model relation.

    Note that this property will return a false positive if a local related app happens to be
    named in the same pattern juju names CMRs, e.g. "remote-abc".

    References:
    - https://github.com/juju/juju/blob/a8bde4056e53e50a05932e2c5588599f34b02cb2/apiserver/facades/controller/crossmodelrelations/crossmodelrelations.go#L273
    - https://github.com/juju/juju/blob/a8bde4056e53e50a05932e2c5588599f34b02cb2/state/migration_import_tasks.go#L444
    """
    # Units names in cross model relations are constructed from the application's token, e.g:
    # "remote-c87d7acb413449cd8097b523af7ff830/0".
    if not relation.units:
        raise ModelError("No units in relation, so cannot determine if cross-model.")

    return any(re.match(r"remote\-[a-f0-9]+/", unit.name) for unit in relation.units)
