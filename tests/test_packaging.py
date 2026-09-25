# SPDX-License-Identifier: GPL-3.0-or-later
"""Packaging: marketplace checks and reproducible zips."""

import hashlib
import os
import shutil
import tempfile
import unittest

import bpy

from core.packagers import marketplace
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


if __name__ == "__main__":
    unittest.main()
