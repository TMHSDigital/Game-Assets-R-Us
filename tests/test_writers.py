# SPDX-License-Identifier: GPL-3.0-or-later
"""File writers: FBX texture references are relative with forward slashes on
every platform."""

import os
import shutil
import tempfile
import unittest

import bpy

from core import pipeline
from core.exporters import writers

EXPORT = {
    "mesh_smooth_type": "FACE",
    "axis_forward": "-Z",
    "axis_up": "Y",
    "global_scale": 1.0,
    "apply_unit_scale": True,
    "apply_scale_options": "FBX_SCALE_NONE",
    "bake_space_transform": False,
}


def _textured_cube(tex_path):
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    image = bpy.data.images.new("T_Test", 4, 4)
    image.filepath_raw = tex_path
    image.file_format = "PNG"
    image.save()
    mat = bpy.data.materials.new("M_Test")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    mat.node_tree.links.new(tex.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])
    obj.data.materials.append(mat)
    return obj


class FbxTexturePaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="garu_writers_")
        pipeline.reset_scene()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_relative_forward_slash_paths(self):
        os.makedirs(os.path.join(self.tmp, "textures"))
        obj = _textured_cube(os.path.join(self.tmp, "textures", "T_Test.png"))
        path = os.path.join(self.tmp, "SM_Test.fbx")
        writers.export_fbx(path, [obj], {"profile": {"export": EXPORT}})
        with open(path, "rb") as fh:
            data = fh.read()
        self.assertTrue(b"textures/T_Test.png" in data, "relative forward-slash path missing")
        self.assertFalse(b"textures\\T_Test.png" in data, "backslash path written")
        # No absolute path to the build folder either.
        self.assertFalse(os.path.basename(self.tmp).encode("utf-8") in data, "absolute path written")


if __name__ == "__main__":
    unittest.main()
