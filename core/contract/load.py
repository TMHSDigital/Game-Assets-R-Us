# SPDX-License-Identifier: GPL-3.0-or-later
"""Load a kit contract (TOML), validate it against the base JSON Schema and
run the semantic checks that JSON Schema cannot express."""

import os
import tomllib

from . import schema_lite

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_SCHEMA = os.path.join(HERE, "base.schema.json")


class ContractError(Exception):
    def __init__(self, path, errors):
        self.path = path
        self.errors = list(errors)
        lines = "\n".join(f"  {p or '/'}: {m}" for p, m in self.errors)
        super().__init__(f"invalid contract {path}:\n{lines}")


def semantic_errors(data):
    """Checks beyond the schema. Returns (json_pointer, message) pairs."""
    errors = []
    pieces = data.get("pieces", [])
    ids = [p.get("id") for p in pieces]
    for pid in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(("/pieces", f"duplicate piece id '{pid}'"))
    for i, piece in enumerate(pieces):
        lods = piece.get("lod_tris", [])
        if any(b >= a for a, b in zip(lods, lods[1:])):
            errors.append((f"/pieces/{i}/lod_tris", f"LOD budgets must strictly decrease, got {lods}"))
    profiles = data.get("exports", {}).get("profiles", [])
    if "stl_print" in profiles and "print" not in data:
        errors.append(("/", "exports include stl_print but the [print] block is missing"))
    legal = data.get("legal", {})
    if legal.get("license") == "commercial-eula" and not legal.get("eula_file"):
        errors.append(("/legal", "license commercial-eula requires legal.eula_file"))
    if legal.get("ai_content") is True:
        errors.append(("/legal/ai_content", "generators are deterministic code; ai_content must be false"))
    return errors


def load_contract(path):
    """Parse and validate a kit.toml. Raises ContractError on any problem."""
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    schema = schema_lite.load_schema(BASE_SCHEMA)
    errors = schema_lite.validate(data, schema)
    if not errors:
        errors = semantic_errors(data)
    if errors:
        raise ContractError(path, errors)
    data["_path"] = os.path.abspath(path)
    data["_dir"] = os.path.dirname(os.path.abspath(path))
    return data
