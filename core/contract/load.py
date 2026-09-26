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


def confined_path(base, rel):
    """Absolute path of `rel` inside directory `base`, or None when `rel` is
    absolute, uses '..' or resolves (through symlinks) outside `base`."""
    if not isinstance(rel, str) or not rel or os.path.isabs(rel) or os.path.splitdrive(rel)[0]:
        return None
    if ".." in rel.replace("\\", "/").split("/"):
        return None
    root = os.path.realpath(base)
    path = os.path.realpath(os.path.join(root, rel))
    try:
        if os.path.commonpath([path, root]) != root:
            return None
    except ValueError:  # different drives
        return None
    return path


LEGAL_FILES = ("license_file", "eula_file")


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
    tex = data.get("textures")
    if tex and tex.get("bake") and tex["size"] != data.get("texel_density", {}).get("texture_size"):
        errors.append(("/textures/size", "must equal texel_density.texture_size, which the "
                                         "texel density check assumes"))
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
    kit_dir = os.path.dirname(os.path.abspath(path))
    if not errors:
        # License text is copied into the distributable zip: it must come
        # from the kit directory, never from elsewhere on the build machine.
        for key in LEGAL_FILES:
            rel = data["legal"].get(key)
            if rel is not None and confined_path(kit_dir, rel) is None:
                errors.append((f"/legal/{key}", f"'{rel}' must be a relative path inside the kit directory"))
    if errors:
        raise ContractError(path, errors)
    data["_path"] = os.path.abspath(path)
    data["_dir"] = kit_dir
    return data
