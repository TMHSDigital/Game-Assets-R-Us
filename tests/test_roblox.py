# SPDX-License-Identifier: GPL-3.0-or-later
"""Roblox profile: every FBX meets the verified Roblox limits and the
single-material, single-UV, embedded-texture layout, at stud scale.
Slow (builds the profile in a separate Blender process). A failed piece
bake leaves no bake nodes or bake settings behind."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace

import bpy

from core import pipeline, roblox
from core.contract import load_contract, resolve
from core.generators import get

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = "stone-dungeon-wall-sampler"
SLOW = os.environ.get("GARU_SKIP_SLOW") == "1"


@unittest.skipIf(SLOW, "slow test skipped (--skip-slow)")
class RobloxExport(unittest.TestCase):
    def test_exports_meet_roblox_rules(self):
        contract = resolve(load_contract(get(KIT).contract_path), "roblox")
        limits = {k: v["value"] for k, v in contract["profile"]["limits"].items() if v["verified"]}
        cell = contract["profile"]["cell_size"]
        tmp = tempfile.mkdtemp(prefix="garu_rbx_")
        try:
            proc = subprocess.run([bpy.app.binary_path, "--background", "--factory-startup", "--python",
                                   os.path.join(ROOT, "core", "cli.py"), "--", "run", "--kit", KIT,
                                   "--profile", "roblox", "--stages", "generate,export", "--build-dir", tmp],
                                  capture_output=True, text=True, timeout=3600)
            self.assertEqual(proc.returncode, 0, proc.stdout[-3000:])
            exports = os.path.join(tmp, KIT, "roblox", "exports")
            with open(os.path.join(tmp, KIT, "roblox", "export_manifest.json"), encoding="utf-8") as fh:
                fbx = [f["name"] for f in json.load(fh)["files"] if f["name"].endswith(".fbx")]
            self.assertEqual(len(fbx), 15)
            problems = []
            for name in fbx:
                bpy.ops.wm.read_factory_settings(use_empty=True)
                bpy.context.scene.unit_settings.system = "NONE"
                bpy.ops.import_scene.fbx(filepath=os.path.join(exports, name))
                bpy.context.view_layer.update()
                meshes = [o for o in bpy.data.objects if o.type == "MESH"]
                if len(meshes) != 1:
                    problems.append(f"{name}: {len(meshes)} meshes")
                    continue
                me = meshes[0].data
                me.calc_loop_triangles()
                if len(me.loop_triangles) > limits["max_triangles_per_mesh"]:
                    problems.append(f"{name}: {len(me.loop_triangles)} triangles")
                if len(me.materials) > limits["max_materials_per_mesh"]:
                    problems.append(f"{name}: {len(me.materials)} materials")
                if len(me.uv_layers) != 1:
                    problems.append(f"{name}: UV layers {[u.name for u in me.uv_layers]}")
                images = [i for i in bpy.data.images if i.size[0]]
                if not images or not all(i.packed_file for i in images):
                    problems.append(f"{name}: textures not embedded")
                if any(max(i.size) > limits["max_texture_size_px"] for i in images):
                    problems.append(f"{name}: texture over the size limit")
                # Every piece height is 2 cells or less; in studs that is 2 * cell_size.
                if max(meshes[0].dimensions) > 2 * cell + 1e-3:
                    problems.append(f"{name}: dims {list(meshes[0].dimensions)} not in studs")
            self.assertEqual(problems, [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class FailedBake(unittest.TestCase):
    def test_failed_bake_leaves_materials_and_settings_clean(self):
        pipeline.reset_scene()
        scene = bpy.context.scene
        settings = scene.render.bake
        settings.margin, settings.use_pass_direct, settings.normal_space = 7, True, "OBJECT"
        engine = scene.render.engine
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.active_object
        # No UV layer at all: Cycles refuses to bake.
        while obj.data.uv_layers:
            obj.data.uv_layers.remove(obj.data.uv_layers[0])
        mat = bpy.data.materials.new("M_Shared")
        mat.use_nodes = True
        obj.data.materials.append(mat)
        contract = {"profile": {"piece_texture_size": 8, "limits": {}},
                    "uv": {"lightmap_channel": "Lightmap", "tiling_channel": "UVMap"},
                    "textures": {"maps": ["base_color"]}}
        kit_scene = SimpleNamespace(contract=contract, sets=[SimpleNamespace(lod0=obj)])
        tmp = tempfile.mkdtemp(prefix="garu_rbx_fail_")
        try:
            with self.assertRaises(RuntimeError):
                roblox.prepare(kit_scene, tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual([n.type for n in mat.node_tree.nodes if n.type == "TEX_IMAGE"], [])
        self.assertEqual((settings.margin, settings.use_pass_direct, settings.normal_space), (7, True, "OBJECT"))
        self.assertEqual(scene.render.engine, engine)


if __name__ == "__main__":
    unittest.main()
