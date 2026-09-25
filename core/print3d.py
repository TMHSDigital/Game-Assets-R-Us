# SPDX-License-Identifier: GPL-3.0-or-later
"""Printable tiles: piece + base + parametric dogbone sockets, in mm.

The socket system (garu_dogbone_v1) is this project's own parametric design:
a T-shaped pocket is cut up from the underside of the base at every cell
edge midpoint on the base perimeter. Two neighbouring tiles form a closed
double-T slot that takes one printed dogbone clip. It is not a copy of
OpenLOCK or any other clip standard. Compatibility with existing standards
is a TODO pending a license check (docs/TODO.md).

Every tile is rotated into print orientation (base down, base bottom on
z = 0) and exported as one solid.
"""

import bmesh
import bpy
from mathutils import Matrix, Vector

from .generators import api
from .geometry import canonical, prims

EMBED_MM = 0.2  # the piece is sunk this far into the base so the union has overlap, not coplanar faces


def boolean_solver():
    items = {i.identifier for i in bpy.types.BooleanModifier.bl_rna.properties["solver"].enum_items}
    return "MANIFOLD" if "MANIFOLD" in items else "EXACT"


def _apply_boolean(target, operand, operation):
    mod = target.modifiers.new("garu_boolean", "BOOLEAN")
    mod.operation = operation
    mod.solver = boolean_solver()
    mod.object = operand
    depsgraph = bpy.context.evaluated_depsgraph_get()
    baked = bpy.data.meshes.new_from_object(target.evaluated_get(depsgraph))
    target.modifiers.remove(mod)
    old = target.data
    target.data = baked
    bpy.data.meshes.remove(old)


def _remove(obj):
    mesh = obj.data
    bpy.data.objects.remove(obj)
    if mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def socket_frames(tiles_x, tiles_y, cell):
    """(origin, along-edge unit u, inward unit w) at every perimeter cell
    edge midpoint, in base coordinates."""
    bx, by = tiles_x * cell, tiles_y * cell
    frames = []
    for i in range(tiles_x):
        x = (i + 0.5) * cell
        frames.append((Vector((x, 0.0)), Vector((1, 0)), Vector((0, 1))))
        frames.append((Vector((x, by)), Vector((-1, 0)), Vector((0, -1))))
    for j in range(tiles_y):
        y = (j + 0.5) * cell
        frames.append((Vector((0.0, y)), Vector((0, -1)), Vector((1, 0))))
        frames.append((Vector((bx, y)), Vector((0, 1)), Vector((-1, 0))))
    return frames


def pocket_outline(clip):
    """T-shaped pocket in the (u, w) edge frame; w = 0 is the base edge.
    Starts 1 mm outside the edge so the cut opens cleanly."""
    nw, nl = clip["neck_width_mm"] / 2, clip["neck_length_mm"]
    hw, hl = clip["head_width_mm"] / 2, clip["head_length_mm"]
    return [(-nw, -1.0), (nw, -1.0), (nw, nl), (hw, nl), (hw, nl + hl),
            (-hw, nl + hl), (-hw, nl), (-nw, nl)]


def clip_outline(clip):
    """Dogbone clip in its own frame: two heads joined by a neck, shrunk by
    the tolerance on every mating face."""
    t = clip["tolerance_mm"]
    nw = clip["neck_width_mm"] / 2 - t
    hw = clip["head_width_mm"] / 2 - t
    inner = clip["neck_length_mm"] + t
    outer = clip["neck_length_mm"] + clip["head_length_mm"] - t
    return [(-outer, -hw), (-inner, -hw), (-inner, -nw), (inner, -nw), (inner, -hw),
            (outer, -hw), (outer, hw), (inner, hw), (inner, nw), (-inner, nw),
            (-inner, hw), (-outer, hw)]


def expected_clip_dims(clip):
    t = clip["tolerance_mm"]
    return (2 * (clip["neck_length_mm"] + clip["head_length_mm"] - t),
            clip["head_width_mm"] - 2 * t,
            clip["height_mm"] - t)


def _socket_cutters(frames, clip, z0, z1):
    bm = bmesh.new()
    outline = pocket_outline(clip)
    for origin, u, w in frames:
        pts = [origin + u * a + w * b for a, b in outline]
        prims.add_prism(bm, [(p.x, p.y) for p in pts], z0, z1)
    prims.recalc_normals(bm)
    obj = prims.to_object(bm, "garu_socket_cutters")
    bm.free()
    return obj


def make_printable(contract, ps):
    pr = contract["print"]
    cell = contract["profile"]["cell_size"]
    piece = api.pieces_by_id(contract)[ps.piece]
    tx, ty = piece.get("print_base_cells", [1, 1])
    bx, by = tx * cell, ty * cell
    base_h = pr["base_height_mm"]
    clip = pr["clip_system"]

    bm = bmesh.new()
    prims.add_box(bm, (0.0, 0.0, 0.0), (bx, by, base_h))
    prims.recalc_normals(bm)
    tile = prims.to_object(bm, f"{ps.name}_print")
    bm.free()
    tile.data.materials.append(api.material(contract, contract["materials"]["palette"][0]["slot"]))

    fx, fy = (v * cell for v in piece["footprint_cells"])
    if piece.get("seams"):
        offset = Vector((0.0, 0.0))
    else:
        offset = Vector(((bx - fx) / 2, (by - fy) / 2))
    body = bpy.data.objects.new("garu_print_body", ps.lod0.data.copy())
    bpy.context.scene.collection.objects.link(body)
    body.matrix_world = Matrix.Translation((offset.x, offset.y, base_h - EMBED_MM))
    _apply_boolean(tile, body, "UNION")
    _remove(body)

    if clip["type"] == "garu_dogbone_v1":
        cutters = _socket_cutters(socket_frames(tx, ty, cell), clip, -1.0, clip["height_mm"])
        _apply_boolean(tile, cutters, "DIFFERENCE")
        _remove(cutters)

    canonical.triangulate(tile.data)
    canonical.canonicalize(tile.data)
    api.tag(tile, ps.piece, ps.variant, "print")
    tile["garu_print_base"] = [tx, ty]
    tile["garu_print_offset"] = [offset.x, offset.y]
    return tile


def make_clip(contract):
    clip = contract["print"]["clip_system"]
    bm = bmesh.new()
    prims.add_prism(bm, clip_outline(clip), 0.0, clip["height_mm"] - clip["tolerance_mm"])
    prims.recalc_normals(bm)
    obj = prims.to_object(bm, f"SM_{contract['kit']['prefix']}_clip_dogbone")
    bm.free()
    canonical.canonicalize(obj.data)
    obj.data.materials.append(api.material(contract, contract["materials"]["palette"][0]["slot"]))
    obj[api.PROP_ROLE] = api.ROLE_CLIP
    return obj


def make_printables(scene):
    contract = scene.contract
    for ps in scene.sets:
        ps.printable = make_printable(contract, ps)
    if contract["print"]["clip_system"]["type"] != "none":
        scene.clips.append(make_clip(contract))
    scene.notes.append(f"boolean solver: {boolean_solver()}")
