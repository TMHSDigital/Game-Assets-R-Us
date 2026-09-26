# SPDX-License-Identifier: GPL-3.0-or-later
"""Generator discovery.

Search order (a generator id declared in two places is an error, never a
silent override):
  1. the built-in kits/ directory of this repo
  2. every entry of the GARU_GENERATOR_PATH environment variable
     (separated by os.pathsep: ';' on Windows, ':' elsewhere)
  3. every --generator-path given on the command line

Each search path is either a generator directory itself (it contains
generator.toml) or a directory whose immediate children are generator
directories. Modules are loaded by file path under a private namespace, so
this core never imports a generator by name and an external private repo
can register generators without changing anything here.
"""

import importlib.util
import os
import sys
import tomllib
from dataclasses import dataclass

from .. import API_VERSION
from ..contract import schema_lite
from ..contract.load import confined_path

ENV_VAR = "GARU_GENERATOR_PATH"
MANIFEST = "generator.toml"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILTIN_KITS = os.path.join(REPO_ROOT, "kits")
MANIFEST_SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.schema.json")


class RegistryError(Exception):
    pass


@dataclass(frozen=True)
class GeneratorInfo:
    id: str
    version: str
    api_version: int
    license: str
    directory: str
    module_path: str
    contract_path: str
    source: str  # "builtin", "env" or "cli"


def search_paths(extra_paths=()):
    paths = [(BUILTIN_KITS, "builtin")]
    for entry in os.environ.get(ENV_VAR, "").split(os.pathsep):
        if entry.strip():
            paths.append((entry.strip(), "env"))
    for entry in extra_paths:
        paths.append((entry, "cli"))
    return paths


def _candidate_dirs(root):
    if os.path.isfile(os.path.join(root, MANIFEST)):
        return [root]
    if not os.path.isdir(root):
        return []
    return [os.path.join(root, name) for name in sorted(os.listdir(root))
            if os.path.isfile(os.path.join(root, name, MANIFEST))]


def _read_manifest(directory, source):
    path = os.path.join(directory, MANIFEST)
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    errors = schema_lite.validate(data, schema_lite.load_schema(MANIFEST_SCHEMA))
    if errors:
        detail = "; ".join(f"{p or '/'}: {m}" for p, m in errors)
        raise RegistryError(f"invalid manifest {path}: {detail}")
    if data["api_version"] != API_VERSION:
        raise RegistryError(
            f"{path}: generator '{data['id']}' targets api_version {data['api_version']}, "
            f"this core provides api_version {API_VERSION}")
    module_path = confined_path(directory, data["module"])
    contract_path = confined_path(directory, data["kit"])
    for key, p in (("module", module_path), ("kit", contract_path)):
        if p is None:
            raise RegistryError(f"{path}: {key} '{data[key]}' resolves outside the generator directory")
        if not os.path.isfile(p):
            raise RegistryError(f"{path}: missing file {p}")
    return GeneratorInfo(
        id=data["id"], version=data["version"], api_version=data["api_version"],
        license=data["license"], directory=os.path.abspath(directory),
        module_path=os.path.abspath(module_path), contract_path=os.path.abspath(contract_path),
        source=source)


def discover(extra_paths=()):
    """Return {generator_id: GeneratorInfo}. Raises RegistryError on conflicts."""
    found = {}
    seen_dirs = set()
    for root, source in search_paths(extra_paths):
        for directory in _candidate_dirs(root):
            real = os.path.realpath(directory)
            if real in seen_dirs:
                continue
            seen_dirs.add(real)
            info = _read_manifest(directory, source)
            if info.id in found:
                raise RegistryError(
                    f"duplicate generator id '{info.id}': {found[info.id].directory} and {info.directory}")
            found[info.id] = info
    return found


def get(generator_id, extra_paths=()):
    found = discover(extra_paths)
    if generator_id not in found:
        raise RegistryError(f"no generator '{generator_id}'; found {sorted(found)} "
                            f"in {[p for p, _ in search_paths(extra_paths)]}")
    return found[generator_id]


def contract_mismatches(info, contract):
    """(json_pointer, message) pairs where the kit contract disagrees with
    its generator manifest: id, version and license must all match."""
    kit, legal = contract["kit"], contract["legal"]
    pairs = [("/kit/generator", kit["generator"], info.id, "id"),
             ("/kit/version", kit["version"], info.version, "version"),
             ("/legal/license", legal["license"], info.license, "license")]
    return [(pointer, f"is '{value}', but the generator manifest {what} is '{expected}'")
            for pointer, value, expected, what in pairs if value != expected]


def load_module(info):
    name = "garu_generators." + info.id.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, info.module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if not callable(getattr(module, "build", None)):
        raise RegistryError(f"{info.module_path}: generator module has no build(contract, seed, piece_ids)")
    return module
