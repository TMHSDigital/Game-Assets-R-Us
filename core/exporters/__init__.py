# SPDX-License-Identifier: GPL-3.0-or-later
"""Export a validated KitScene for its profile, then verify every file by
importing it back into Blender.

Output: <out>/exports/ plus <out>/exports/manifest.json listing every file
with its SHA-256, the exporter settings used (including any settings the
running Blender did not accept), and the round-trip result.
"""

import hashlib
import os

import bpy

from ..validators.report import write_json
from . import roundtrip
from .writers import export_fbx, export_glb, export_stl


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _profile_name(profile, base, role, index=0, lod=0):
    if role == "lod0":
        return base + profile["lod0_suffix"]
    if role == "lod":
        return f"{base}_LOD{lod}"
    return profile["collider_pattern"].format(name=base, index=index)


def mesh_jobs(scene):
    """(file name, [(object, exported name)]) for every file a mesh profile writes."""
    profile = scene.contract["profile"]
    ext = profile["format"]
    jobs = []
    for ps in scene.sets:
        base = ps.name
        main = [(ps.lod0, _profile_name(profile, base, "lod0"))]
        if profile["lod_mode"] == "embedded":
            main += [(o, _profile_name(profile, base, "lod", lod=i + 1)) for i, o in enumerate(ps.lods)]
        if profile["collider_mode"] == "embedded":
            main += [(o, _profile_name(profile, base, "collider", index=i)) for i, o in enumerate(ps.colliders)]
        jobs.append((f"{base}.{ext}", main))
        if profile["lod_mode"] == "separate_files":
            for i, o in enumerate(ps.lods):
                name = _profile_name(profile, base, "lod", lod=i + 1)
                jobs.append((f"{name}.{ext}", [(o, name)]))
        if profile["collider_mode"] == "separate_files" and ps.colliders:
            jobs.append((f"{base}_colliders.{ext}",
                         [(o, _profile_name(profile, base, "collider", index=i)) for i, o in enumerate(ps.colliders)]))
    return jobs


def print_jobs(scene):
    jobs = [(f"{ps.name}.stl", [(ps.printable, ps.name)]) for ps in scene.sets]
    jobs += [(f"{clip.name}.stl", [(clip, clip.name)]) for clip in scene.clips]
    return jobs


class _Renamed:
    """Temporarily give objects (and their meshes) their exported names."""

    def __init__(self, pairs):
        self.pairs = pairs
        self.saved = []

    def __enter__(self):
        for obj, name in self.pairs:
            self.saved.append((obj, obj.name, obj.data.name))
            obj.name = "__garu_tmp__" + name
        for obj, name in self.pairs:
            obj.name = name
            obj.data.name = name
        return self

    def __exit__(self, *exc):
        for obj, _name, _mesh in self.saved:
            obj.name = "__garu_restore__" + obj.name
        for obj, name, mesh in self.saved:
            obj.name = name
            obj.data.name = mesh


def export_scene(scene, out_dir):
    contract = scene.contract
    profile = contract["profile"]
    exp_dir = os.path.join(out_dir, "exports")
    os.makedirs(exp_dir, exist_ok=True)
    jobs = mesh_jobs(scene) if profile["kind"] == "mesh" else print_jobs(scene)
    writer = {"fbx": export_fbx, "glb": export_glb, "stl": export_stl}[profile["format"]]

    files, settings, expected = [], None, {}
    for filename, pairs in jobs:
        path = os.path.join(exp_dir, filename)
        with _Renamed(pairs):
            expected[filename] = roundtrip.expected(pairs)
            settings = writer(path, [o for o, _ in pairs], contract)
        files.append(filename)

    if profile["kind"] == "print":
        from ..print_sheet import write_print_sheet
        write_print_sheet(scene, out_dir, exp_dir)

    results = roundtrip.verify(exp_dir, expected, profile)
    manifest = {
        "kit": contract["kit"]["id"],
        "kit_version": contract["kit"]["version"],
        "profile": profile["name"],
        "seed": scene.seed,
        "blender": bpy.app.version_string,
        "exporter_settings": settings,
        "files": [{"name": f, "sha256": sha256(os.path.join(exp_dir, f)),
                   "bytes": os.path.getsize(os.path.join(exp_dir, f)),
                   "objects": expected[f], "roundtrip": results[f]} for f in files],
    }
    manifest["roundtrip_passed"] = all(r["passed"] for r in results.values())
    write_json(os.path.join(out_dir, "export_manifest.json"), manifest)
    failed = [f for f, r in results.items() if not r["passed"]]
    for f in failed:
        print(f"ROUNDTRIP FAIL {f}: {results[f]['problems']}")
    print(f"ROUNDTRIP {len(files) - len(failed)}/{len(files)} files re-imported and matched")
    return manifest
