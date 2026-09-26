# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolve a kit contract for one export profile.

Resolution merges three layers, later wins:
  1. profiles/<name>/profile.toml   (profile defaults)
  2. kit.toml [profiles.<name>]     (per-kit overrides)
and validates the merged profile table against profiles/<name>/schema.json.
The result is the base contract with the merged table under the key
"profile", frozen so generators cannot mutate shared state.
"""

import copy
import os
import tomllib
from types import MappingProxyType

from . import schema_lite
from .load import NAME_TEMPLATES, ContractError, name_template_errors

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROFILES_DIR = os.path.join(REPO_ROOT, "profiles")


def available_profiles():
    return sorted(
        name for name in os.listdir(PROFILES_DIR)
        if os.path.isfile(os.path.join(PROFILES_DIR, name, "profile.toml"))
    )


def load_profile(name):
    path = os.path.join(PROFILES_DIR, name, "profile.toml")
    if not os.path.isfile(path):
        raise ContractError(path, [("/", f"unknown profile '{name}', available: {available_profiles()}")])
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def deep_merge(base, override):
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(freeze(v) for v in value)
    return value


def thaw(value):
    if isinstance(value, MappingProxyType) or isinstance(value, dict):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [thaw(v) for v in value]
    return value


def resolve(contract, profile_name):
    if profile_name not in contract["exports"]["profiles"]:
        raise ContractError(contract.get("_path", "?"), [
            ("/exports/profiles", f"profile '{profile_name}' is not listed for this kit"),
        ])
    merged = deep_merge(load_profile(profile_name), contract.get("profiles", {}).get(profile_name, {}))
    schema_path = os.path.join(PROFILES_DIR, profile_name, "schema.json")
    errors = schema_lite.validate(merged, schema_lite.load_schema(schema_path))
    if not errors and "collider_pattern" in merged:
        fields, int_fields = NAME_TEMPLATES["collider_pattern"]
        errors = [("/collider_pattern", m)
                  for m in name_template_errors(merged["collider_pattern"], fields, int_fields)]
    if errors:
        raise ContractError(f"{contract.get('_path', '?')} [profile {profile_name}]",
                            [(f"/profiles/{profile_name}{p}", m) for p, m in errors])
    resolved = {k: v for k, v in contract.items() if k != "profiles"}
    resolved["profile"] = merged
    return freeze(resolved)
