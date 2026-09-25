# SPDX-License-Identifier: GPL-3.0-or-later
"""FiveM (Sollumz) profile: builds on Blender 4.5 with the pinned Sollumz,
every drawable re-imports through Sollumz, and two builds are identical.

Runs only where Sollumz is installed (it is never vendored):
  GARU_BLENDER_45     Blender 4.5 executable
  GARU_SOLLUMZ_USER   BLENDER_USER_RESOURCES folder holding the Sollumz extension
  GARU_SZIO_SITE      directory holding the pinned szio package
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = "stone-dungeon-wall-sampler"
BLENDER_45 = os.environ.get("GARU_BLENDER_45", "")
USER = os.environ.get("GARU_SOLLUMZ_USER", "")
SZIO = os.environ.get("GARU_SZIO_SITE", "")
READY = all(os.path.exists(p) for p in (BLENDER_45, USER, SZIO)) if BLENDER_45 and USER and SZIO else False
SLOW = os.environ.get("GARU_SKIP_SLOW") == "1"


def build(out):
    env = dict(os.environ, BLENDER_USER_RESOURCES=USER, GARU_SZIO_SITE=SZIO)
    proc = subprocess.run([BLENDER_45, "--background", "--factory-startup", "--python",
                           os.path.join(ROOT, "core", "cli.py"), "--", "run", "--kit", KIT,
                           "--profile", "fivem_sollumz", "--stages", "generate,validate,export",
                           "--build-dir", out], capture_output=True, text=True, timeout=3600, env=env)
    if proc.returncode != 0:
        raise AssertionError(f"build failed ({proc.returncode}):\n{proc.stdout[-4000:]}")
    with open(os.path.join(out, KIT, "fivem_sollumz", "export_manifest.json"), encoding="utf-8") as fh:
        return json.load(fh)


@unittest.skipIf(not READY, "Sollumz not configured (GARU_BLENDER_45, GARU_SOLLUMZ_USER, GARU_SZIO_SITE)")
@unittest.skipIf(SLOW, "slow test skipped (--skip-slow)")
class FivemSollumz(unittest.TestCase):
    def test_export_verified_and_reproducible(self):
        tmp = tempfile.mkdtemp(prefix="garu_fivem_")
        try:
            a = build(os.path.join(tmp, "a"))
            b = build(os.path.join(tmp, "b"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        xml = [f for f in a["files"] if f["name"].endswith(".ydr.xml")]
        self.assertEqual(len(xml), 30)  # 15 drawables, gen8 and gen9
        self.assertTrue(a["roundtrip_passed"])
        self.assertFalse(a["streamed_memory_over_warning"])
        hb = {f["name"]: f["sha256"] for f in b["files"]}
        differing = [f["name"] for f in a["files"] if hb.get(f["name"]) != f["sha256"]]
        self.assertEqual(differing, [])
        print(f"FIVEM {len(xml)} drawables verified through Sollumz; {len(a['files'])} files identical across builds")


if __name__ == "__main__":
    unittest.main()
