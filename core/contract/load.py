# SPDX-License-Identifier: GPL-3.0-or-later
"""Load a kit contract (TOML), validate it against the base JSON Schema and
run the semantic checks that JSON Schema cannot express."""

import ntpath
import os
import re
import string
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
    absolute, uses '..' or resolves (through symlinks) outside `base`.
    Windows drive and root forms are refused on every OS, so a kit is judged
    the same wherever it is built."""
    if not isinstance(rel, str) or not rel or os.path.isabs(rel):
        return None
    if rel[0] in "/\\" or ntpath.isabs(rel) or ntpath.splitdrive(rel)[0]:
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

# Name templates become object and file names: {field: (placeholders, integer placeholders)}.
NAME_TEMPLATES = {
    "naming_pattern": ({"prefix", "kit", "piece", "variant"}, set()),
    "lod_pattern": ({"name", "n"}, {"n"}),
    "collider_pattern": ({"name", "index"}, {"index"}),
}
_SAFE_LITERAL = re.compile(r"^[A-Za-z0-9_-]*$")
_INT_SPEC = re.compile(r"^0?[0-9]{0,2}d?$")


def name_template_errors(template, fields, int_fields=()):
    """Problems with a str.format name template: only the given plain
    placeholders (a width spec such as :02d on integer ones), and literal
    text limited to letters, digits, '_' and '-'."""
    try:
        parts = list(string.Formatter().parse(template))
    except ValueError as exc:
        return [f"invalid template {template!r}: {exc}"]
    problems = []
    for literal, field, spec, conversion in parts:
        if not _SAFE_LITERAL.match(literal):
            problems.append(f"text {literal!r} may only use letters, digits, '_' and '-'")
        if field is None:
            continue
        if field not in fields:
            problems.append(f"unknown placeholder {{{field}}}; allowed: {', '.join(sorted(fields))}")
        elif conversion:
            problems.append(f"placeholder {{{field}}} may not use a !{conversion} conversion")
        elif spec and (field not in int_fields or not _INT_SPEC.match(spec)):
            problems.append(f"placeholder {{{field}}} has an unsupported format spec {spec!r}")
    return problems


def semantic_errors(data):
    """Checks beyond the schema. Returns (json_pointer, message) pairs."""
    errors = []
    style = data.get("style", {})
    for key, (fields, int_fields) in NAME_TEMPLATES.items():
        if key in style:
            errors += [(f"/style/{key}", m) for m in name_template_errors(style[key], fields, int_fields)]
    pieces = data.get("pieces", [])
    ids = [p.get("id") for p in pieces]
    for pid in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(("/pieces", f"duplicate piece id '{pid}'"))
    for i, piece in enumerate(pieces):
        lods = piece.get("lod_tris", [])
        if any(b >= a for a, b in zip(lods, lods[1:])):
            errors.append((f"/pieces/{i}/lod_tris", f"LOD budgets must strictly decrease, got {lods}"))
    profiles = data.get("exports", {}).get("profiles", [])
    for name in sorted(set(data.get("profiles", {})) - set(profiles)):
        errors.append((f"/profiles/{name}", f"overrides profile '{name}', which exports.profiles does not list"))
    td = data.get("texel_density", {})
    if td.get("min_px_per_cell", 0) > td.get("max_px_per_cell", float("inf")):
        errors.append(("/texel_density", "min_px_per_cell must not exceed max_px_per_cell"))
    if "stl_print" in profiles and "print" not in data:
        errors.append(("/", "exports include stl_print but the [print] block is missing"))
    tex = data.get("textures")
    if tex and tex.get("bake") and tex["size"] != data.get("texel_density", {}).get("texture_size"):
        errors.append(("/textures/size", "must equal texel_density.texture_size, which the "
                                         "texel density check assumes"))
    legal = data.get("legal", {})
    if legal.get("license") == "commercial-eula" and not legal.get("eula_file"):
        errors.append(("/legal", "license commercial-eula requires legal.eula_file"))
    if legal.get("license") == "CC0-1.0" and not legal.get("license_file"):
        errors.append(("/legal", "license CC0-1.0 requires legal.license_file"))
    if legal.get("ai_content") is True:
        errors.append(("/legal/ai_content", "generators are deterministic code; ai_content must be false"))
    return errors


def read_toml(path):
    """Parse a TOML file; syntax and read errors become a ContractError."""
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ContractError(path, [("/", f"TOML syntax error: {exc}")]) from exc
    except OSError as exc:
        raise ContractError(path, [("/", f"cannot read file: {exc}")]) from exc


def load_contract(path):
    """Parse and validate a kit.toml. Raises ContractError on any problem."""
    data = read_toml(path)
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
