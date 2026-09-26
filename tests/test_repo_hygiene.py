# SPDX-License-Identifier: GPL-3.0-or-later
"""Repository rules: SPDX headers in every source file, ASCII-only text
(so no emojis and no em dashes) in docs, READMEs, comments and data, and
every working profile built in CI.
Checks git-tracked files; verbatim third-party license texts are exempt."""

import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPDX_EXT = {".py", ".ps1", ".toml", ".yml", ".yaml", ".gd"}
TEXT_EXT = SPDX_EXT | {".md", ".json", ".txt"}
VERBATIM = {"LICENSE", "LICENSES/CC0-1.0.txt", "LICENSES/GPL-3.0-or-later.txt",
            "kits/stone-dungeon-wall-sampler/assets/LICENSE-CC0"}


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [line for line in out.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        files = []
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in {".git", "build", "dist", "__pycache__"}]
            files += [os.path.relpath(os.path.join(dirpath, f), ROOT).replace(os.sep, "/") for f in filenames]
        return files


class RepoHygiene(unittest.TestCase):
    def test_spdx_headers(self):
        missing = []
        for rel in tracked_files():
            ext = os.path.splitext(rel)[1].lower()
            path = os.path.join(ROOT, rel)
            if ext in SPDX_EXT:
                with open(path, encoding="utf-8") as fh:
                    head = "".join(fh.readline() for _ in range(3))
                if "SPDX-License-Identifier:" not in head:
                    missing.append(rel)
            elif ext == ".json" and rel.endswith("schema.json"):
                with open(path, encoding="utf-8") as fh:
                    if "SPDX-License-Identifier" not in fh.read(400):
                        missing.append(rel)
        self.assertEqual(missing, [])

    def test_ascii_only_text(self):
        offenders = []
        for rel in tracked_files():
            if rel in VERBATIM or os.path.splitext(rel)[1].lower() not in TEXT_EXT:
                continue
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    bad = [ch for ch in line if ord(ch) > 127]
                    if bad:
                        offenders.append(f"{rel}:{lineno}: {''.join(bad)!r}")
        self.assertEqual(offenders, [], "non-ASCII (emoji, em dash, ...) found")

    def test_working_profiles_are_built_in_ci(self):
        # scripts/_common.ps1 expands "working" from a fixed list; it must
        # match the profiles whose profile.toml says status = "working", and
        # CI must build that set, so no working profile goes unbuilt.
        working = set()
        profiles_dir = os.path.join(ROOT, "profiles")
        for name in os.listdir(profiles_dir):
            toml = os.path.join(profiles_dir, name, "profile.toml")
            if os.path.isfile(toml):
                with open(toml, encoding="utf-8") as fh:
                    if re.search(r'^\s*status\s*=\s*"working"', fh.read(), re.M):
                        working.add(name)
        with open(os.path.join(ROOT, "scripts", "_common.ps1"), encoding="utf-8") as fh:
            listed = re.search(r"\$script:WorkingProfiles\s*=\s*@\(([^)]*)\)", fh.read())
        self.assertIsNotNone(listed)
        self.assertEqual(set(re.findall(r'"([^"]+)"', listed.group(1))), working)
        with open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8") as fh:
            build = re.search(r"build-kit\.ps1[^\n]*\n[^\n]*-Profiles\s+(\S+)", fh.read())
        self.assertIsNotNone(build, "ci.yml has no build-kit.ps1 -Profiles step")
        built = set(build.group(1).split(","))
        if "working" in built:
            built |= working
        self.assertEqual(working - built, set(), "working profiles not built in CI")


if __name__ == "__main__":
    unittest.main()
