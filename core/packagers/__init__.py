# SPDX-License-Identifier: GPL-3.0-or-later
"""Packagers.

Game profiles: an itch.io / Fab style zip with models, previews, a README,
the license and the export manifest. stl_print: an STL zip with the print
settings sheet, previews and the license. Everything goes to
dist/<profile>/ (gitignored).

Packaging fails if a verified marketplace requirement is not met (see
marketplace.py for the checks and their sources).
"""

import json
import os

from ..contract.load import confined_path
from ..validators.legal_checks import scan_names
from . import marketplace
from .readme import kit_readme
from .zip_det import settings as zip_settings
from .zip_det import write_zip


class PackagingError(Exception):
    pass


def _license_text(contract):
    legal = contract["legal"]
    rel = legal.get("license_file") if legal["license"] == "CC0-1.0" else legal.get("eula_file")
    if not rel:
        raise PackagingError(f"no license file named for license {legal['license']}")
    path = confined_path(contract["_dir"], rel)
    if path is None:
        raise PackagingError(f"license file '{rel}' is outside the kit directory")
    if not os.path.isfile(path):
        raise PackagingError(f"license file missing: {path}")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _load_json(path, what):
    if not os.path.isfile(path):
        raise PackagingError(f"{what} missing: {path} (run the validate and export stages first)")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise PackagingError(f"{what} unreadable: {path}: {exc}") from exc


def package(contract, info, out_dir, dist_dir):
    profile = contract["profile"]
    kit = contract["kit"]
    exp_dir = os.path.join(out_dir, "exports")
    prev_dir = os.path.join(out_dir, "previews")
    root = f"{kit['id']}-{kit['version']}-{profile['name']}"
    manifest = _load_json(os.path.join(out_dir, "export_manifest.json"), "export manifest")
    summary = _load_json(os.path.join(out_dir, "reports", "summary.json"), "validation summary")
    if summary.get("passed") is not True:
        raise PackagingError(f"validation did not pass (see {os.path.join(out_dir, 'reports')})")
    if manifest.get("roundtrip_passed") is not True:
        raise PackagingError("export round-trip did not pass (see export_manifest.json)")
    demo = None
    if os.path.isfile(os.path.join(prev_dir, "demo_scene.json")):
        with open(os.path.join(prev_dir, "demo_scene.json"), encoding="utf-8") as fh:
            demo = json.load(fh)

    entries = {}
    folder = "stl" if profile["kind"] == "print" else "models"
    for dirpath, _dirs, filenames in os.walk(exp_dir):
        for name in filenames:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, exp_dir).replace(os.sep, "/")
            if rel == "print_settings.md":
                entries[f"{root}/print_settings.md"] = path
            else:
                entries[f"{root}/{folder}/{rel}"] = path
    if os.path.isdir(prev_dir):
        for name in sorted(os.listdir(prev_dir)):
            entries[f"{root}/previews/{name}"] = os.path.join(prev_dir, name)
    # The shipped manifest is the export manifest plus the zip settings the
    # archive bytes depend on (zlib build included).
    shipped = dict(manifest, package={"zip": zip_settings()})
    entries[f"{root}/manifest.json"] = (json.dumps(shipped, indent=2, sort_keys=True) + "\n").encode("utf-8")
    entries[f"{root}/validation_summary.json"] = os.path.join(out_dir, "reports", "summary.json")
    entries[f"{root}/LICENSE"] = _license_text(contract).encode("utf-8")
    entries[f"{root}/README.md"] = kit_readme(contract, info, manifest, summary, demo).encode("utf-8")

    problems = marketplace.check(entries)
    problems += [f"brand mark {h['mark']!r} in file name {h['text']}" for h in scan_names(entries)]
    if problems:
        raise PackagingError("marketplace requirements not met:\n  " + "\n  ".join(problems))

    suffix = "stl" if profile["kind"] == "print" else profile["name"]
    zip_path = os.path.join(dist_dir, profile["name"], f"{kit['id']}-{kit['version']}-{suffix}.zip")
    write_zip(zip_path, entries)
    return zip_path
