# SPDX-License-Identifier: GPL-3.0-or-later
"""An out-of-tree generator runs through the full core pipeline (generate,
validate, export with round-trip) with no changes to this repository."""

import os
import shutil
import tempfile
import unittest

from core.contract import load_contract, resolve
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


if __name__ == "__main__":
    unittest.main()
