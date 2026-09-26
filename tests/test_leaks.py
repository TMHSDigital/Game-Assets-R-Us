# SPDX-License-Identifier: GPL-3.0-or-later
"""No datablocks left behind by LOD retries or verification imports."""

import os
import shutil
import tempfile
import unittest
from unittest import mock

import bpy

from core import pipeline
from core.exporters import roundtrip, writers
from core.geometry import lod as lod_mod
from test_writers import EXPORT, _textured_cube

KINDS = ("objects", "meshes", "materials", "images", "collections", "node_groups")


def _counts():
    return {k: len(getattr(bpy.data, k)) for k in KINDS}


class LodRetries(unittest.TestCase):
    def test_retried_lod_mesh_keeps_its_name(self):
        pipeline.reset_scene()
        bpy.ops.mesh.primitive_uv_sphere_add()
        src = bpy.context.active_object
        real = lod_mod.triangle_count
        calls = []

        def over_budget_twice(obj):
            # Report the first two decimated copies as over budget.
            if obj is not src:
                calls.append(obj.name)
                if len(calls) <= 2:
                    return 10 ** 9
            return real(obj)

        with mock.patch.object(lod_mod, "triangle_count", over_budget_twice):
            lod = lod_mod.make_lod(src, 200, "SM_Test_LOD1")
        self.assertEqual(len(calls), 3)
        self.assertEqual(lod.name, "SM_Test_LOD1")
        self.assertEqual(lod.data.name, "SM_Test_LOD1")
        self.assertEqual(sorted(m.name for m in bpy.data.meshes if m.name.startswith("SM_Test_LOD1")),
                         ["SM_Test_LOD1"])


class RoundtripImport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="garu_leaks_")
        pipeline.reset_scene()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_import_leaves_nothing_behind(self):
        os.makedirs(os.path.join(self.tmp, "textures"))
        obj = _textured_cube(os.path.join(self.tmp, "textures", "T_Test.png"))
        path = os.path.join(self.tmp, "SM_Test.fbx")
        writers.export_fbx(path, [obj], {"profile": {"export": EXPORT}})
        # Drop the source image so the import has to load its own copy.
        bpy.data.images.remove(bpy.data.images["T_Test"])
        before = _counts()
        for _ in range(2):
            got = roundtrip._import(path)
            self.assertIn("Cube", got)
        self.assertEqual(_counts(), before)
        self.assertEqual(len(bpy.data.scenes), 1)


if __name__ == "__main__":
    unittest.main()
