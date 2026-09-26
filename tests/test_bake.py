# SPDX-License-Identifier: GPL-3.0-or-later
"""Texture baking: tiling maps are seamless, not flat, and reproducible."""

import array
import hashlib
import math
import os
import shutil
import statistics
import tempfile
import unittest

import bpy

from core import bake, materials, pipeline
from core.contract import load_contract, resolve
from core.contract.resolve import freeze, thaw
from core.generators import get

SIZE = 128


def _contract():
    c = thaw(resolve(load_contract(get("stone-dungeon-wall-sampler").contract_path), "gltf_web"))
    c["textures"]["size"] = SIZE
    return freeze(c)


def _pixels(image):
    px = array.array("f", [0.0]) * (image.size[0] * image.size[1] * 4)
    image.pixels.foreach_get(px)
    return px


class BakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="garu_bake_")
        self.contract = _contract()
        pipeline.reset_scene()
        materials.ensure_palette(self.contract)
        self.baked = bake.bake_palette(self.contract, self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_all_maps_written(self):
        names = sorted(os.listdir(self.tmp))
        self.assertEqual(len(names), 2 * 3, names)
        self.assertTrue(all(n.startswith("T_SDW_") and n.endswith(".png") for n in names))

    def test_seamless_and_not_flat(self):
        for slot, maps in self.baked.items():
            for name, image in maps.items():
                px = _pixels(image)
                s = image.size[0]
                red = px[0::4]
                wrap_x = max(abs(red[y * s] - red[y * s + s - 1]) for y in range(s))
                inner_x = max(abs(red[y * s + x] - red[y * s + x + 1]) for y in range(s) for x in range(s - 1))
                wrap_y = max(abs(red[x] - red[(s - 1) * s + x]) for x in range(s))
                inner_y = max(abs(red[y * s + x] - red[(y + 1) * s + x]) for y in range(s - 1) for x in range(s))
                with self.subTest(slot=slot, map=name):
                    # Across the tile edge the texture changes no more than between any two
                    # neighbouring texels inside it: no seam when tiled.
                    self.assertLessEqual(wrap_x, inner_x + 1e-6)
                    self.assertLessEqual(wrap_y, inner_y + 1e-6)
                    self.assertGreater(statistics.pstdev(red), 0.005, "map is flat")

    def test_reproducible(self):
        first = {n: hashlib.sha256(open(os.path.join(self.tmp, n), "rb").read()).hexdigest()
                 for n in os.listdir(self.tmp)}
        again = tempfile.mkdtemp(prefix="garu_bake2_")
        try:
            pipeline.reset_scene()
            materials.ensure_palette(self.contract)
            bake.bake_palette(self.contract, again)
            second = {n: hashlib.sha256(open(os.path.join(again, n), "rb").read()).hexdigest()
                      for n in os.listdir(again)}
        finally:
            shutil.rmtree(again, ignore_errors=True)
        self.assertEqual(first, second)


class NormalFromHeight(unittest.TestCase):
    def test_strength_independent_of_size(self):
        # Four sine periods across the tile: the slope per UV unit is fixed, so
        # the normal map must not change with the texture size.
        reds = {}
        for s in (64, 256):
            height = bpy.data.images.new(f"h{s}", s, s, float_buffer=True)
            px = array.array("f", [0.0]) * (s * s * 4)
            for y in range(s):
                for x in range(s):
                    px[(y * s + x) * 4] = 4.0 * math.sin(8 * math.pi * x / s)
            height.pixels.foreach_set(px)
            target = bpy.data.images.new(f"n{s}", s, s)
            bake.normal_from_height(height, target)
            out = _pixels(target)
            reds[s] = max(abs(v - 0.5) for v in out[0::4])
            bpy.data.images.remove(height)
            bpy.data.images.remove(target)
        self.assertGreater(reds[64], 0.05)
        self.assertAlmostEqual(reds[64], reds[256], delta=0.01)


if __name__ == "__main__":
    unittest.main()
