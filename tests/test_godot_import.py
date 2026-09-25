# SPDX-License-Identifier: GPL-3.0-or-later
"""Engine import test: the godot profile's GLB files imported by a real,
headless Godot 4. Checks that every visual mesh arrives Y-up at the size
Blender exported, and that every `-convcolonly` collider becomes a convex
physics shape with no visible mesh.

Needs Godot 4 (GARU_GODOT, or `godot` on PATH); skipped otherwise, so CI
without Godot is unaffected.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(ROOT, "tests", "engine", "godot_check.gd")
KIT = "stone-dungeon-wall-sampler"
GODOT = os.environ.get("GARU_GODOT") or shutil.which("godot") or ""
SLOW = os.environ.get("GARU_SKIP_SLOW") == "1"
TOL = 1e-3


def _run(cmd, timeout=1800):
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise AssertionError(f"{cmd[0]} failed ({proc.returncode}):\n{proc.stdout[-3000:]}\n{proc.stderr[-2000:]}")
    return proc


@unittest.skipIf(not GODOT, "Godot not found (set GARU_GODOT)")
@unittest.skipIf(SLOW, "slow test skipped (--skip-slow)")
class GodotImport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="garu_godot_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_godot_imports_sampler(self):
        build = os.path.join(self.tmp, "build")
        _run([bpy.app.binary_path, "--background", "--factory-startup", "--python",
              os.path.join(ROOT, "core", "cli.py"), "--", "run", "--kit", KIT, "--profile", "godot",
              "--seed", "1337", "--stages", "generate,export", "--build-dir", build])
        exports = os.path.join(build, KIT, "godot", "exports")
        with open(os.path.join(build, KIT, "godot", "export_manifest.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)

        project = os.path.join(self.tmp, "project")
        os.makedirs(os.path.join(project, "models"))
        with open(os.path.join(project, "project.godot"), "w", encoding="utf-8") as fh:
            fh.write('config_version=5\n\n[application]\nconfig/name="garu_import_check"\n')
        shutil.copy(CHECK, project)
        models = [f for f in manifest["files"] if f["name"].endswith(".glb")]
        for f in models:
            shutil.copy(os.path.join(exports, f["name"]), os.path.join(project, "models"))
        _run([GODOT, "--headless", "--path", project, "--import"])
        out = os.path.join(self.tmp, "godot.json")
        _run([GODOT, "--headless", "--path", project, "--script", "res://godot_check.gd", "--", out])
        with open(out, encoding="utf-8") as fh:
            seen = json.load(fh)

        problems = []
        for f in models:
            got = seen.get(f["name"])
            if not got or not got["loaded"]:
                problems.append(f"{f['name']}: not loaded by Godot")
                continue
            meshes = {m["name"]: m["size"] for m in got["meshes"]}
            shapes = {s["name"]: s["type"] for s in got["shapes"]}
            for name, want in f["objects"].items():
                if name.endswith("-convcolonly"):
                    node = name[: -len("-convcolonly")]
                    if shapes.get(node) != "ConvexPolygonShape3D":
                        problems.append(f"{f['name']}: {node} shape {shapes.get(node)}")
                    if node in meshes:
                        problems.append(f"{f['name']}: collider {node} has a visible mesh")
                    continue
                if name not in meshes:
                    problems.append(f"{f['name']}: mesh {name} missing, got {sorted(meshes)}")
                    continue
                bx, by, bz = want["dims"]
                gx, gy, gz = meshes[name]
                # Blender Z-up (x, y, z) arrives in Godot Y-up as (x, z, y).
                if any(abs(a - b) > TOL for a, b in ((bx, gx), (bz, gy), (by, gz))):
                    problems.append(f"{f['name']}: {name} size {meshes[name]} != Y-up of {want['dims']}")
        print(f"GODOT {len(models)} files imported by {os.path.basename(GODOT)}; problems: {len(problems)}")
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
