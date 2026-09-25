# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract loading, schema_lite keyword coverage and profile resolution."""

import copy
import os
import tempfile
import tomllib
import unittest

from core.contract import ContractError, load_contract, resolve, available_profiles
from core.contract import schema_lite
from core.contract.load import semantic_errors

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLER = os.path.join(ROOT, "kits", "stone-dungeon-wall-sampler", "kit.toml")


def _base_schema():
    return schema_lite.load_schema(os.path.join(ROOT, "core", "contract", "base.schema.json"))


def _sampler_data():
    with open(SAMPLER, "rb") as fh:
        return tomllib.load(fh)


class SchemaLiteTests(unittest.TestCase):
    def test_types_and_bounds(self):
        schema = {"type": "object", "required": ["a"], "additionalProperties": False,
                  "properties": {"a": {"type": "integer", "minimum": 1, "maximum": 3}}}
        self.assertEqual(schema_lite.validate({"a": 2}, schema), [])
        self.assertTrue(schema_lite.validate({"a": 0}, schema))
        self.assertTrue(schema_lite.validate({"a": 1.5}, schema))
        self.assertTrue(schema_lite.validate({"a": True}, schema))
        self.assertTrue(schema_lite.validate({}, schema))
        self.assertTrue(schema_lite.validate({"a": 1, "b": 2}, schema))

    def test_ref_anyof_if_then_else(self):
        schema = {
            "$defs": {"pos": {"type": "number", "exclusiveMinimum": 0}},
            "type": "object",
            "properties": {
                "n": {"$ref": "#/$defs/pos"},
                "u": {"anyOf": [{"const": "generator"}, {"type": "string", "pattern": "^https://"}]},
            },
            "if": {"properties": {"kind": {"const": "a"}}},
            "then": {"required": ["n"]},
            "else": {"required": ["u"]},
        }
        self.assertEqual(schema_lite.validate({"kind": "a", "n": 1}, schema), [])
        self.assertTrue(schema_lite.validate({"kind": "a"}, schema))
        self.assertEqual(schema_lite.validate({"kind": "b", "u": "https://x"}, schema), [])
        self.assertTrue(schema_lite.validate({"kind": "b", "u": "http://x"}, schema))
        self.assertTrue(schema_lite.validate({"kind": "a", "n": 0}, schema))

    def test_unsupported_keyword_rejected(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write('{"type": "string", "format": "email"}')
        try:
            with self.assertRaises(schema_lite.SchemaError):
                schema_lite.load_schema(fh.name)
        finally:
            os.unlink(fh.name)


class ContractTests(unittest.TestCase):
    def test_sampler_contract_is_valid(self):
        contract = load_contract(SAMPLER)
        self.assertEqual(contract["kit"]["id"], "stone-dungeon-wall-sampler")
        self.assertEqual(len(contract["pieces"]), 5)

    def _errors(self, mutate):
        data = _sampler_data()
        mutate(data)
        return schema_lite.validate(data, _base_schema()) or semantic_errors(data)

    def test_bad_license_rejected(self):
        errs = self._errors(lambda d: d["legal"].__setitem__("license", "MIT"))
        self.assertTrue(any("/legal/license" in p for p, _ in errs), errs)

    def test_lod_budgets_must_decrease(self):
        errs = self._errors(lambda d: d["pieces"][0].__setitem__("lod_tris", [100, 100, 50]))
        self.assertTrue(any("strictly decrease" in m for _, m in errs), errs)

    def test_print_block_required_for_stl(self):
        errs = self._errors(lambda d: d.pop("print"))
        self.assertTrue(any("[print] block is missing" in m for _, m in errs), errs)

    def test_ai_content_must_be_false(self):
        errs = self._errors(lambda d: d["legal"].__setitem__("ai_content", True))
        self.assertTrue(any("ai_content" in p for p, _ in errs), errs)

    def test_commercial_eula_needs_file(self):
        errs = self._errors(lambda d: d["legal"].__setitem__("license", "commercial-eula"))
        self.assertTrue(any("eula_file" in m for _, m in errs), errs)

    def test_clip_system_fields_enforced(self):
        errs = self._errors(lambda d: d["print"]["clip_system"].pop("tolerance_mm"))
        self.assertTrue(any("tolerance_mm" in m for _, m in errs), errs)

    def test_unknown_key_rejected(self):
        errs = self._errors(lambda d: d["grid"].__setitem__("cell_size", 2.0))
        self.assertTrue(any("unknown key 'cell_size'" in m for _, m in errs), errs)

    def test_load_raises(self):
        data = _sampler_data()
        text = open(SAMPLER, encoding="utf-8").read().replace('license = "CC0-1.0"', 'license = "GPL"')
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False, encoding="utf-8") as fh:
            fh.write(text)
        try:
            with self.assertRaises(ContractError):
                load_contract(fh.name)
        finally:
            os.unlink(fh.name)
        self.assertIn("legal", data)


class ResolveTests(unittest.TestCase):
    def test_all_profiles_resolve(self):
        contract = load_contract(SAMPLER)
        self.assertEqual(set(available_profiles()), set(contract["exports"]["profiles"]))
        for name in available_profiles():
            resolved = resolve(contract, name)
            self.assertEqual(resolved["profile"]["name"], name)

    def test_cell_size_defaults(self):
        contract = load_contract(SAMPLER)
        self.assertEqual(resolve(contract, "unity")["profile"]["cell_size"], 2.0)
        self.assertEqual(resolve(contract, "stl_print")["profile"]["cell_size"], 25.4)
        self.assertEqual(resolve(contract, "stl_print")["profile"]["units"], "mm")

    def test_override_is_validated(self):
        contract = copy.deepcopy(load_contract(SAMPLER))
        contract["profiles"] = {"godot": {"export": {"export_yup": False}}}
        with self.assertRaises(ContractError):
            resolve(contract, "godot")

    def test_resolved_is_frozen(self):
        resolved = resolve(load_contract(SAMPLER), "unity")
        with self.assertRaises(TypeError):
            resolved["grid"]["height_cells"] = 3

    def test_roblox_limits_unverified(self):
        limits = resolve(load_contract(SAMPLER), "roblox")["profile"]["limits"]
        for name, entry in limits.items():
            self.assertFalse(entry["verified"], name)
            self.assertNotIn("value", entry, name)


if __name__ == "__main__":
    unittest.main()
