# SPDX-License-Identifier: GPL-3.0-or-later
"""Preview renders (core/render): the demo room layout, camera framing, and
a real Workbench render of the sampler's contact sheet and demo scene
(slow, about a minute; skipped with --skip-slow)."""

import json
import os
import shutil
import tempfile
import unittest

import bpy
from mathutils import Vector

from core import pipeline, render
from core.contract import load_contract, resolve
from core.generators import api, get, load_module
from core.packagers import marketplace

KIT = "stone-dungeon-wall-sampler"
SLOW = os.environ.get("GARU_SKIP_SLOW") == "1"


def _contract(profile="gltf_web"):
    return resolve(load_contract(get(KIT).contract_path), profile)


class RoomLayout(unittest.TestCase):
    def test_layout_is_seeded_and_on_the_quarter_grid(self):
        contract = _contract()
        a = render.room_layout(contract, api.rng_for(1337, "demo_room"))
        b = render.room_layout(contract, api.rng_for(1337, "demo_room"))
        self.assertEqual(a, b)
        variants = set(contract["style"]["variants"])
        pieces = {p["id"] for p in contract["pieces"]}
        self.assertEqual(len(a), 17)
        counts = {}
        for pid, variant, x, y, turns in a:
            counts[pid] = counts.get(pid, 0) + 1
            self.assertIn(pid, pieces)
            self.assertIn(variant, variants)
            self.assertIn(turns, (0, 1, 2, 3))
            for c in (x, y):
                self.assertAlmostEqual(c * 4, round(c * 4))
                self.assertTrue(0 <= c <= 4)
        self.assertEqual(counts, {"floor_2x2": 4, "corner_outer": 4, "wall_straight": 6, "doorway": 2, "pillar": 1})

    def test_other_seeds_can_change_variants_only(self):
        contract = _contract()
        layouts = [render.room_layout(contract, api.rng_for(seed, "demo_room")) for seed in range(1, 9)]
        placements = {tuple((p, x, y, t) for p, _, x, y, t in layout) for layout in layouts}
        self.assertEqual(len(placements), 1, "placements must not depend on the seed")
        self.assertGreater(len({tuple(v for _, v, _, _, _ in layout) for layout in layouts}), 1)


class Framing(unittest.TestCase):
    def setUp(self):
        pipeline.reset_scene()

    def test_camera_frames_every_vertex(self):
        scene = bpy.context.scene
        scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
        mesh = bpy.data.meshes.new("garu_frame_test")
        pts = [(0, 0, 0), (7, 0, 0), (7, 3, 0), (0, 3, 0), (0, 0, 5), (7, 3, 5)]
        mesh.from_pydata(pts, [], [])
        obj = bpy.data.objects.new("garu_frame_test", mesh)
        scene.collection.objects.link(obj)
        obj.location = (10, -4, 2)
        bpy.context.view_layer.update()
        render._frame(scene, [obj])
        bpy.context.view_layer.update()
        cam = scene.camera
        self.assertEqual(cam.data.type, "ORTHO")
        # Looking along -VIEW_DIR, and every vertex inside the ortho frustum.
        forward = cam.matrix_world.to_quaternion() @ Vector((0, 0, -1))
        self.assertAlmostEqual(forward.dot(-render.VIEW_DIR), 1.0, places=5)
        inv = cam.matrix_world.inverted()
        half_w = cam.data.ortho_scale / 2
        half_h = half_w * 1080 / 1920
        for v in obj.data.vertices:
            local = inv @ (obj.matrix_world @ v.co)
            self.assertLess(abs(local.x), half_w)
            self.assertLess(abs(local.y), half_h)
            self.assertLess(-local.z, cam.data.clip_end)
            self.assertGreater(-local.z, cam.data.clip_start)


@unittest.skipIf(SLOW, "slow test skipped (--skip-slow)")
class RenderPreviews(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        info = get(KIT)
        cls.contract = resolve(load_contract(info.contract_path), "gltf_web")
        cls.scene = pipeline.generate(cls.contract, load_module(info), 1337)
        cls.tmp = tempfile.mkdtemp(prefix="garu_render_")
        cls.result = render.render_previews(cls.scene, cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_images_written_at_gallery_size(self):
        prev = os.path.join(self.tmp, "previews")
        self.assertEqual(marketplace.png_size(os.path.join(prev, "contact_sheet.png")), (1920, 1440))
        self.assertEqual(marketplace.png_size(os.path.join(prev, "demo_scene.png")), (1920, 1080))
        for name in ("contact_sheet.png", "demo_scene.png"):
            # Fab caps gallery images at 3 MB.
            self.assertLess(os.path.getsize(os.path.join(prev, name)), 3 * 1024 * 1024, name)

    def test_demo_room_snaps(self):
        with open(os.path.join(self.tmp, "previews", "demo_scene.json"), encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual(saved["passed"], self.result["passed"])
        self.assertTrue(saved["passed"], saved)
        self.assertEqual(saved["pieces_placed"], 17)
        self.assertGreater(saved["seam_pairs"], 0)
        self.assertTrue(saved["placements_on_grid"])
        self.assertLessEqual(saved["max_seam_deviation"], saved["tolerance"])
        cell = self.contract["profile"]["cell_size"]
        self.assertAlmostEqual(saved["tolerance"], self.contract["grid"]["snap_tolerance_cells"] * cell)


if __name__ == "__main__":
    unittest.main()
