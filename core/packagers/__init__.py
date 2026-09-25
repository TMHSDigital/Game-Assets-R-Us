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

from . import marketplace
from .readme import kit_readme
from .zip_det import write_zip


class PackagingError(Exception):
    pass


def _license_text(contract):
    legal = contract["legal"]
    rel = legal.get("license_file") if legal["license"] == "CC0-1.0" else legal.get("eula_file")
    with open(os.path.join(contract["_dir"], rel), encoding="utf-8") as fh:
        return fh.read()


def package(contract, info, out_dir, dist_dir):
    profile = contract["profile"]
    kit = contract["kit"]
    exp_dir = os.path.join(out_dir, "exports")
    prev_dir = os.path.join(out_dir, "previews")
    root = f"{kit['id']}-{kit['version']}-{profile['name']}"
    with open(os.path.join(out_dir, "export_manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    with open(os.path.join(out_dir, "reports", "summary.json"), encoding="utf-8") as fh:
        summary = json.load(fh)
    demo = None
    if os.path.isfile(os.path.join(prev_dir, "demo_scene.json")):
        with open(os.path.join(prev_dir, "demo_scene.json"), encoding="utf-8") as fh:
            demo = json.load(fh)

    entries = {}
    folder = "stl" if profile["kind"] == "print" else "models"
    for name in sorted(os.listdir(exp_dir)):
        if name == "print_settings.md":
            entries[f"{root}/print_settings.md"] = os.path.join(exp_dir, name)
        else:
            entries[f"{root}/{folder}/{name}"] = os.path.join(exp_dir, name)
    if os.path.isdir(prev_dir):
        for name in sorted(os.listdir(prev_dir)):
            entries[f"{root}/previews/{name}"] = os.path.join(prev_dir, name)
    entries[f"{root}/manifest.json"] = os.path.join(out_dir, "export_manifest.json")
    entries[f"{root}/validation_summary.json"] = os.path.join(out_dir, "reports", "summary.json")
    entries[f"{root}/LICENSE"] = _license_text(contract).encode("utf-8")
    entries[f"{root}/README.md"] = kit_readme(contract, info, manifest, summary, demo).encode("utf-8")

    problems = marketplace.check(entries)
    if problems:
        raise PackagingError("marketplace requirements not met:\n  " + "\n  ".join(problems))

    suffix = "stl" if profile["kind"] == "print" else profile["name"]
    zip_path = os.path.join(dist_dir, profile["name"], f"{kit['id']}-{kit['version']}-{suffix}.zip")
    write_zip(zip_path, entries)
    return zip_path
