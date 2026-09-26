# SPDX-License-Identifier: GPL-3.0-or-later
"""Determinism: two separate Blender processes building the same kit with
the same seed and contract must write byte-identical export files, for every
working profile. A different seed must change the weathered variants. The
full pipeline (validate, bake, render, package) run twice must write
byte-identical dist/*.zip packages.

Slow (it launches extra Blender processes); skipped with --skip-slow.
GARU_DETERMINISM_PROFILES limits the export profiles and
GARU_PACKAGE_DETERMINISM_PROFILES the packaged ones (comma separated).
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "core", "cli.py")
KIT = "stone-dungeon-wall-sampler"
WORKING = ["unity", "unreal", "godot", "gltf_web", "stl_print", "roblox"]
# One game package (textures, previews, README) and the STL package; each
# full run renders previews, so the default stays at two profiles.
PACKAGE_PROFILES = ["gltf_web", "stl_print"]
STAGES = ["generate", "validate", "export", "render", "package"]
SLOW = os.environ.get("GARU_SKIP_SLOW") == "1"


def _run_cli(profile, seed, build_dir, stages, dist_dir=None):
    cmd = [bpy.app.binary_path, "--background", "--factory-startup", "--python-exit-code", "1", "--python", CLI, "--",
           "run", "--kit", KIT, "--profile", profile, "--seed", str(seed),
           "--stages", stages, "--build-dir", build_dir]
    if dist_dir:
        cmd += ["--dist-dir", dist_dir]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if proc.returncode != 0:
        raise AssertionError(f"build failed ({proc.returncode}):\n{proc.stdout[-4000:]}\n{proc.stderr[-2000:]}")


def build(profile, seed, build_dir):
    _run_cli(profile, seed, build_dir, "generate,export")
    with open(os.path.join(build_dir, KIT, profile, "export_manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    return {f["name"]: f["sha256"] for f in manifest["files"]}


def package(profile, seed, root):
    """Full pipeline (every stage, including render and package); returns
    {zip path relative to dist: (zip sha256, {entry name: entry sha256})}."""
    dist = os.path.join(root, "dist")
    _run_cli(profile, seed, os.path.join(root, "build"), ",".join(STAGES), dist)
    out = {}
    for dirpath, _, files in os.walk(dist):
        for name in files:
            if name.endswith(".zip"):
                path = os.path.join(dirpath, name)
                with open(path, "rb") as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()
                with zipfile.ZipFile(path) as zf:
                    entries = {n: hashlib.sha256(zf.read(n)).hexdigest() for n in zf.namelist()}
                out[os.path.relpath(path, dist).replace(os.sep, "/")] = (digest, entries)
    return out


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

    def test_full_pipeline_same_zip_bytes(self):
        # The shipped artifact: validate, bake, render and package included,
        # the dist/*.zip must be byte-identical across two separate runs.
        profiles = [p for p in os.environ.get("GARU_PACKAGE_DETERMINISM_PROFILES",
                                              ",".join(PACKAGE_PROFILES)).split(",") if p]
        for profile in profiles:
            with self.subTest(profile=profile):
                a = package(profile, 1337, os.path.join(self.tmp, profile, "a"))
                b = package(profile, 1337, os.path.join(self.tmp, profile, "b"))
                self.assertEqual(len(a), 1, f"{profile}: expected one zip, got {sorted(a)}")
                self.assertEqual(sorted(a), sorted(b))
                zip_name = next(iter(a))
                (digest_a, entries_a), (digest_b, entries_b) = a[zip_name], b[zip_name]
                self.assertEqual(sorted(entries_a), sorted(entries_b), f"{profile}: zip entry lists differ")
                differing = sorted(n for n in entries_a if entries_a[n] != entries_b[n])
                self.assertEqual(differing, [], f"{profile}: zip entries differ between identical builds")
                self.assertEqual(digest_a, digest_b, f"{profile}: zip bytes differ (entries identical)")
                print(f"DETERMINISM {profile}: {zip_name} identical across two full pipeline runs")


if __name__ == "__main__":
    unittest.main()
