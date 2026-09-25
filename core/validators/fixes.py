# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic fixes applied only with --fix.

Exactly three fixes exist, and each one is recorded in the piece report with
its before and after values; nothing is ever changed silently:
  FIX.XFORM   apply rotation and scale into the mesh data
  FIX.ORIGIN  move the origin to the contract pivot rule, keeping the mesh
              where it is in the world
  FIX.RENAME  rename objects to the contract naming patterns
Checks always re-run after fixes, so a fix can never hide a failure.
"""

from mathutils import Matrix, Vector

from . import metrics


def _apply_rot_scale(obj):
    before = {"rotation": list(obj.rotation_euler), "scale": list(obj.scale)}
    # matrix_basis, not matrix_world: matrix_world is stale until the
    # depsgraph updates, which would silently drop the rotation.
    loc, rot, scale = obj.matrix_basis.decompose()
    basis = rot.to_matrix().to_4x4() @ Matrix.Diagonal(scale.to_4d())
    obj.data.transform(basis)
    obj.data.update()
    obj.matrix_basis = Matrix.Translation(loc)
    return {"id": "FIX.XFORM", "object": obj.name, "before": before,
            "after": {"rotation": list(obj.rotation_euler), "scale": list(obj.scale)}}


def _set_origin(obj, rule):
    lo, hi = metrics.bbox_local(obj)
    target = Vector((lo.x, lo.y, lo.z)) if rule == "base_min_corner" else Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    if target.length <= 1e-12:
        return None
    before = list(obj.location)
    obj.data.transform(Matrix.Translation(-target))
    obj.data.update()
    obj.location = obj.location + obj.matrix_basis.to_3x3() @ target
    return {"id": "FIX.ORIGIN", "object": obj.name, "before": {"location": before, "local_offset": list(target)},
            "after": {"location": list(obj.location)}}


def apply(contract, ps, expected):
    """expected: {slot: name} from core_checks.expected_names."""
    records = []
    for obj in ps.mesh_objects() + ps.colliders:
        rot_scale = any(abs(a) > 1e-9 for a in obj.rotation_euler) or any(abs(s - 1) > 1e-9 for s in obj.scale)
        if rot_scale:
            records.append(_apply_rot_scale(obj))
    for obj in ps.mesh_objects():
        rec = _set_origin(obj, contract["style"]["pivot_rule"])
        if rec:
            records.append(rec)
    slots = [("lod0", ps.lod0)] + [(f"lod{i + 1}", o) for i, o in enumerate(ps.lods)] \
        + [(f"collider{i}", o) for i, o in enumerate(ps.colliders)]
    for slot, obj in slots:
        want = expected.get(slot)
        if want and obj.name != want:
            before = obj.name
            obj.name = want
            obj.data.name = want
            records.append({"id": "FIX.RENAME", "object": want, "before": {"name": before},
                            "after": {"name": obj.name}})
    for rec in records:
        print(f"FIX {rec['id']} {rec['object']}: {rec['before']} -> {rec['after']}")
    return records
