# SPDX-License-Identifier: GPL-3.0-or-later
"""An out-of-tree generator runs through the full core pipeline (generate,
validate, export with round-trip) with no changes to this repository."""

import os
import shutil
import tempfile
import unittest

from core.contract import load_contract, resolve
from core.contract.resolve import freeze, thaw
from core.exporters import export_scene
from core.generators import get, load_module
from core import pipeline
from core.validators import runner

EXTERNAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "external_gen")


class ExternalGeneratorPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="garu_ext_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, profile):
        info = get("demo-external", extra_paths=[EXTERNAL])
        contract = resolve(load_contract(info.contract_path), profile)
        scene = pipeline.generate(contract, load_module(info), 7)
        out = os.path.join(self.tmp, profile)
        summary = runner.validate(scene, out)
        self.assertTrue(summary["passed"], summary["failed_pieces"])
        manifest = export_scene(scene, out)
        self.assertTrue(manifest["roundtrip_passed"])
        return manifest

    def test_gltf_web(self):
        manifest = self._run("gltf_web")
        names = [f["name"] for f in manifest["files"]]
        self.assertIn("SM_DEMO_plinth_clean.glb", names)

    def test_stl_print_without_clips(self):
        manifest = self._run("stl_print")
        self.assertEqual([f["name"] for f in manifest["files"]], ["SM_DEMO_plinth_clean.stl"])

    def test_lod_pattern_names_exports(self):
        from core.exporters import mesh_jobs
        info = get("demo-external", extra_paths=[EXTERNAL])
        data = thaw(resolve(load_contract(info.contract_path), "gltf_web"))
        data["style"]["lod_pattern"] = "{name}_lod{n:02d}"
        scene = pipeline.generate(freeze(data), load_module(info), 7)
        files = [f for f, _ in mesh_jobs(scene)]
        self.assertIn("SM_DEMO_plinth_clean_lod01.glb", files)
        self.assertNotIn("SM_DEMO_plinth_clean_LOD1.glb", files)

    def test_box_collider(self):
        info = get("demo-external", extra_paths=[EXTERNAL])
        data = thaw(resolve(load_contract(info.contract_path), "gltf_web"))
        data["collider"]["type"] = "box"
        scene = pipeline.generate(freeze(data), load_module(info), 7)
        ps = scene.sets[0]
        self.assertEqual(len(ps.colliders), 1)
        col = ps.colliders[0]
        self.assertEqual(len(col.data.vertices), 8)  # a triangulated box

        def bounds(obj):
            pts = [obj.matrix_world @ v.co for v in obj.data.vertices]
            return [round(f(p[i] for p in pts), 5) for f in (min, max) for i in range(3)]
        self.assertEqual(bounds(col), bounds(ps.lod0))


if __name__ == "__main__":
    unittest.main()
