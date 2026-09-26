# SPDX-License-Identifier: GPL-3.0-or-later
"""Generator registry: an out-of-tree generator registers with no core edits."""

import os
import shutil
import tempfile
import unittest

from core.generators import ENV_VAR, RegistryError, discover, get, load_module

HERE = os.path.dirname(os.path.abspath(__file__))
EXTERNAL = os.path.join(HERE, "fixtures", "external_gen")


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.pop(ENV_VAR, None)

    def tearDown(self):
        os.environ.pop(ENV_VAR, None)
        if self._env is not None:
            os.environ[ENV_VAR] = self._env

    def test_builtin_sampler_found(self):
        found = discover()
        self.assertIn("stone-dungeon-wall-sampler", found)
        self.assertEqual(found["stone-dungeon-wall-sampler"].source, "builtin")
        self.assertNotIn("demo-external", found)

    def test_external_via_env_var(self):
        os.environ[ENV_VAR] = os.pathsep.join([EXTERNAL, os.path.join(HERE, "does-not-exist")])
        info = get("demo-external")
        self.assertEqual(info.source, "env")
        self.assertTrue(info.contract_path.endswith("kit.toml"))

    def test_external_via_cli_path(self):
        info = get("demo-external", extra_paths=[os.path.join(EXTERNAL, "demo-external")])
        self.assertEqual(info.source, "cli")

    def test_external_module_loads(self):
        module = load_module(get("demo-external", extra_paths=[EXTERNAL]))
        self.assertTrue(callable(module.build))

    def test_same_dir_twice_is_not_a_duplicate(self):
        os.environ[ENV_VAR] = EXTERNAL
        self.assertIn("demo-external", discover(extra_paths=[EXTERNAL]))

    def test_duplicate_id_rejected(self):
        tmp = tempfile.mkdtemp()
        try:
            shutil.copytree(os.path.join(EXTERNAL, "demo-external"), os.path.join(tmp, "copy"))
            with self.assertRaisesRegex(RegistryError, "duplicate generator id"):
                discover(extra_paths=[EXTERNAL, tmp])
        finally:
            shutil.rmtree(tmp)

    def test_api_version_mismatch_rejected(self):
        tmp = tempfile.mkdtemp()
        try:
            dst = os.path.join(tmp, "future")
            shutil.copytree(os.path.join(EXTERNAL, "demo-external"), dst)
            path = os.path.join(dst, "generator.toml")
            text = open(path, encoding="utf-8").read()
            text = text.replace('id = "demo-external"', 'id = "future-gen"').replace("api_version = 1", "api_version = 99")
            open(path, "w", encoding="utf-8").write(text)
            with self.assertRaisesRegex(RegistryError, "api_version 99"):
                discover(extra_paths=[tmp])
        finally:
            shutil.rmtree(tmp)

    def test_bad_manifest_rejected(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "bad"))
            open(os.path.join(tmp, "bad", "generator.toml"), "w").write('id = "Bad Id"\n')
            with self.assertRaisesRegex(RegistryError, "invalid manifest"):
                discover(extra_paths=[tmp])
        finally:
            shutil.rmtree(tmp)

    def test_module_path_confined(self):
        tmp = tempfile.mkdtemp()
        try:
            dst = os.path.join(tmp, "escape")
            shutil.copytree(os.path.join(EXTERNAL, "demo-external"), dst)
            path = os.path.join(dst, "generator.toml")
            base = open(path, encoding="utf-8").read()
            for bad in ("../generator.py", "sub/generator.py", os.path.join(dst, "generator.py")):
                open(path, "w", encoding="utf-8").write(
                    base.replace('module = "generator.py"', f"module = {bad!r}".replace("'", '"')
                                 .replace("\\", "/")))
                with self.assertRaisesRegex(RegistryError, "invalid manifest"):
                    discover(extra_paths=[tmp])
        finally:
            shutil.rmtree(tmp)

    def test_confined_path(self):
        from core.contract.load import confined_path
        base = tempfile.mkdtemp()
        try:
            self.assertEqual(confined_path(base, "assets/LICENSE"),
                             os.path.join(os.path.realpath(base), "assets", "LICENSE"))
            for bad in ("../x", "a/../../x", "a\\..\\x", os.path.abspath(os.sep), "C:x", "", None):
                self.assertIsNone(confined_path(base, bad), bad)
        finally:
            shutil.rmtree(base)

    def test_unknown_id(self):
        with self.assertRaisesRegex(RegistryError, "no generator 'nope'"):
            get("nope")


if __name__ == "__main__":
    unittest.main()
