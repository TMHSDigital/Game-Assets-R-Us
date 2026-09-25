# SPDX-License-Identifier: GPL-3.0-or-later
"""Packaging: marketplace checks and reproducible zips."""

import hashlib
import json
import os
import shutil
import tempfile
import unittest

import bpy

from core.contract import load_contract, resolve
from core.generators import get
from core.packagers import PackagingError, marketplace, package
from core.packagers.zip_det import write_zip


def _png(path, w, h):
    img = bpy.data.images.new(os.path.basename(path), w, h)
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    return path


class MarketplaceChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="garu_pkg_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fab_gallery_minimum(self):
        small = _png(os.path.join(self.tmp, "small.png"), 1600, 1100)
        big = _png(os.path.join(self.tmp, "big.png"), 1920, 1080)
        self.assertEqual(marketplace.png_size(big), (1920, 1080))
        self.assertEqual(marketplace.check({"kit/previews/big.png": big}), [])
        problems = marketplace.check({"kit/previews/small.png": small})
        self.assertTrue(any("1920 x 1080" in p for p in problems), problems)
        # Textures are not gallery images.
        self.assertEqual(marketplace.check({"kit/models/textures/T_SDW_stone_normal.png": small}), [])

    def test_path_length(self):
        long_name = "kit/" + "a" * 140 + ".glb"
        self.assertTrue(marketplace.check({long_name: b"x"}))
        self.assertEqual(marketplace.check({"kit/models/SM_SDW_wall_straight_clean.glb": b"x"}), [])

    def test_zip_is_reproducible(self):
        src = os.path.join(self.tmp, "a.txt")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write("same\n")
        entries = {"k/b.bin": b"\x00\x01", "k/a.txt": src}
        a = write_zip(os.path.join(self.tmp, "one", "k.zip"), entries)
        os.utime(src, (0, 0))
        b = write_zip(os.path.join(self.tmp, "two", "k.zip"), dict(reversed(list(entries.items()))))
        digest = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
        self.assertEqual(digest(a), digest(b))


class PackagePrerequisites(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="garu_pkg_")
        self.info = get("stone-dungeon-wall-sampler")
        self.contract = resolve(load_contract(self.info.contract_path), "gltf_web")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel, data):
        path = os.path.join(self.tmp, "out", rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def _package(self):
        return package(self.contract, self.info, os.path.join(self.tmp, "out"), os.path.join(self.tmp, "dist"))

    def test_missing_inputs_raise_packaging_error(self):
        with self.assertRaisesRegex(PackagingError, "export manifest missing"):
            self._package()
        self._write("export_manifest.json", {"roundtrip_passed": True, "files": [], "seed": 1, "blender": "x"})
        with self.assertRaisesRegex(PackagingError, "validation summary missing"):
            self._package()

    def test_failed_validation_or_roundtrip_not_packaged(self):
        self._write("export_manifest.json", {"roundtrip_passed": True, "files": [], "seed": 1, "blender": "x"})
        self._write("reports/summary.json", {"passed": False, "checks": {}, "pieces": {}})
        with self.assertRaisesRegex(PackagingError, "validation did not pass"):
            self._package()
        self._write("reports/summary.json", {"passed": True, "checks": {}, "pieces": {}})
        self._write("export_manifest.json", {"roundtrip_passed": False, "files": [], "seed": 1, "blender": "x"})
        with self.assertRaisesRegex(PackagingError, "round-trip did not pass"):
            self._package()

    def test_stage_prerequisites(self):
        from core.cli import plan_stages
        self.assertEqual(plan_stages(["package"]), (["generate", "validate", "export", "package"],
                                                    ["validate", "export"]))
        self.assertEqual(plan_stages(["generate", "export"]), (["generate", "validate", "export"], ["validate"]))
        self.assertEqual(plan_stages(["render"]), (["generate", "render"], []))


if __name__ == "__main__":
    unittest.main()
