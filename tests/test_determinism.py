# SPDX-License-Identifier: GPL-3.0-or-later
"""Determinism: two separate Blender processes building the same kit with
the same seed and contract must write byte-identical export files, for every
working profile. A different seed must change the weathered variants.

Slow (it launches extra Blender processes); skipped with --skip-slow.
GARU_DETERMINISM_PROFILES limits the profiles (comma separated).
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "core", "cli.py")
KIT = "stone-dungeon-wall-sampler"
WORKING = ["unity", "unreal", "godot", "gltf_web", "stl_print"]
SLOW = os.environ.get("GARU_SKIP_SLOW") == "1"


def build(profile, seed, build_dir):
    cmd = [bpy.app.binary_path, "--background", "--factory-startup", "--python", CLI, "--",
           "run", "--kit", KIT, "--profile", profile, "--seed", str(seed),
           "--stages", "generate,export", "--build-dir", build_dir]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if proc.returncode != 0:
        raise AssertionError(f"build failed ({proc.returncode}):\n{proc.stdout[-4000:]}\n{proc.stderr[-2000:]}")
    with open(os.path.join(build_dir, KIT, profile, "export_manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    return {f["name"]: f["sha256"] for f in manifest["files"]}


@unittest.skipIf(SLOW, "slow test skipped (--skip-slow)")
class Determinism(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="garu_det_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_same_seed_same_bytes(self):
        profiles = [p for p in os.environ.get("GARU_DETERMINISM_PROFILES", ",".join(WORKING)).split(",") if p]
        for profile in profiles:
            with self.subTest(profile=profile):
                a = build(profile, 1337, os.path.join(self.tmp, "a"))
                b = build(profile, 1337, os.path.join(self.tmp, "b"))
                self.assertTrue(a)
                differing = sorted(name for name in a if a[name] != b.get(name))
                self.assertEqual(set(a), set(b))
                self.assertEqual(differing, [], f"{profile}: files differ between identical builds")
                print(f"DETERMINISM {profile}: {len(a)} files identical across two builds")

    def test_different_seed_changes_weathered_pieces(self):
        a = build("gltf_web", 1337, os.path.join(self.tmp, "s1"))
        b = build("gltf_web", 7, os.path.join(self.tmp, "s2"))
        changed = sorted(n for n in a if a[n] != b[n])
        self.assertTrue(any("_ruined" in n for n in changed))
        self.assertFalse(any("_clean" in n for n in changed), "clean variants must not depend on the seed")
        print(f"DETERMINISM seed 1337 vs 7: {len(changed)} of {len(a)} gltf_web files differ (weathered only)")


if __name__ == "__main__":
    unittest.main()
