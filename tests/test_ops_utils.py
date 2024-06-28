# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import unittest
from textwrap import dedent

from cosl.ops_utils import is_cmr
from ops.charm import CharmBase
from ops.testing import Harness


class TestCharm(CharmBase):
    meta = dedent(
        """
        name: test-charm
        requires:
          some-relation:
            interface: some_interface
        """
    )


class TestCMRCheck(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(TestCharm, meta=TestCharm.meta)
        self.harness.begin()

    def test_is_cmr(self):
        rel_id_local = self.harness.add_relation("some-relation", "local-app")
        self.harness.add_relation_unit(rel_id_local, "local-app/0")
        rel_id_abc = self.harness.add_relation("some-relation", "remote-abc")
        self.harness.add_relation_unit(rel_id_abc, "remote-abc/0")
        rel_id_xyz = self.harness.add_relation(
            "some-relation", "remote-c87d7acb413449cd8097b523af7ff830"
        )
        self.harness.add_relation_unit(rel_id_xyz, "remote-c87d7acb413449cd8097b523af7ff830/0")

        relation = self.harness.model.get_relation("some-relation", rel_id_local)
        self.assertFalse(is_cmr(relation))

        relation = self.harness.model.get_relation("some-relation", rel_id_abc)
        self.assertTrue(is_cmr(relation))

        relation = self.harness.model.get_relation("some-relation", rel_id_xyz)
        self.assertTrue(is_cmr(relation))
