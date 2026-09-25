# SPDX-License-Identifier: GPL-3.0-or-later
"""Round-trip verification: import each exported file back into Blender and
compare object names, triangle counts and bounding-box sizes with what was
exported. This proves axis and unit settings are self-consistent (a file
that comes back rotated or 100x too large fails). It does not replace an
import test inside each engine; that remains a documented TODO.

Imports happen in a throwaway scene so the kit scene stays intact.
"""

import os
import re

import bpy

from ..validators import metrics

REL_TOL = 1e-3


def _dims(obj):
    # Per axis, not sorted: a file that comes back rotated must fail.
    lo, hi = metrics.bbox_world(obj)
    return list(hi - lo)


def _tris(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def expected(pairs):
    return {name: {"tris": _tris(obj), "dims": _dims(obj)} for obj, name in pairs}


def _importer(path):
    if path.endswith(".glb"):
        return bpy.ops.import_scene.gltf, {"filepath": path}
    if path.endswith(".fbx"):
        return bpy.ops.import_scene.fbx, {"filepath": path}
    return bpy.ops.wm.stl_import, {"filepath": path}


def _import(path):
    tmp = bpy.data.scenes.new("garu_roundtrip")
    before = set(bpy.data.objects)
    before_meshes = set(bpy.data.meshes)
    before_mats = set(bpy.data.materials)
    op, kwargs = _importer(path)
    try:
        with bpy.context.temp_override(scene=tmp, view_layer=tmp.view_layers[0]):
            op(**kwargs)
        bpy.context.view_layer.update()
        tmp.view_layers[0].update()
        new = [o for o in bpy.data.objects if o not in before]
        # The originals still exist, so imported names get a .001 suffix.
        return {re.sub(r"\.\d{3}$", "", obj.name): {"tris": _tris(obj), "dims": _dims(obj)}
                for obj in new if obj.type == "MESH"}
    finally:
        for obj in [o for o in bpy.data.objects if o not in before]:
            bpy.data.objects.remove(obj)
        for mesh in [m for m in bpy.data.meshes if m not in before_meshes]:
            bpy.data.meshes.remove(mesh)
        for mat in [m for m in bpy.data.materials if m not in before_mats]:
            bpy.data.materials.remove(mat)
        bpy.data.scenes.remove(tmp)


def _match(want, got):
    problems = []
    if want["tris"] != got["tris"]:
        problems.append(f"tris {got['tris']} != {want['tris']}")
    for a, b in zip(want["dims"], got["dims"]):
        if abs(a - b) > REL_TOL * max(abs(a), 1e-9):
            problems.append(f"dims {[round(x, 5) for x in got['dims']]} != {[round(x, 5) for x in want['dims']]}")
            break
    return problems


def verify(exp_dir, expected_by_file, profile):
    results = {}
    for filename, want in expected_by_file.items():
        got = _import(os.path.join(exp_dir, filename))
        problems = []
        if filename.endswith(".stl"):
            # STL has no object names: compare the single solid.
            (w,) = want.values()
            if len(got) != 1:
                problems.append(f"expected 1 solid, imported {len(got)}")
            else:
                problems += _match(w, next(iter(got.values())))
        else:
            missing = sorted(set(want) - set(got))
            extra = sorted(set(got) - set(want))
            if missing or extra:
                problems.append(f"names: missing {missing}, unexpected {extra}")
            for name in sorted(set(want) & set(got)):
                problems += [f"{name}: {p}" for p in _match(want[name], got[name])]
        results[filename] = {"passed": not problems, "problems": problems, "objects": len(got)}
    return results
