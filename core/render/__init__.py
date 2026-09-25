# SPDX-License-Identifier: GPL-3.0-or-later
"""Preview renders (Workbench: deterministic, no GPU, no HDRI, no fonts).

contact_sheet.png   every piece variant, rows = pieces, columns = variants
demo_scene.png      an assembled 4 x 4 cell room placed by grid position and
                    90 degree rotations only; demo_scene.json records the
                    measured seam deviation between every pair of touching
                    pieces, which proves the kit snaps on the grid.
"""

import math
import os

import bpy
from mathutils import Matrix, Vector

from ..generators import api
from ..validators.report import write_json

VIEW_DIR = Vector((1.0, -1.35, 1.05)).normalized()


def _setup_render(scene, width, height):
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.color_type = "MATERIAL"
    shading.show_cavity = True
    shading.cavity_type = "BOTH"
    shading.show_shadows = True
    scene.display.render_aa = "8"
    if scene.world is None:
        scene.world = bpy.data.worlds.new("garu_world")
    scene.world.color = (0.16, 0.17, 0.19)


def _frame(scene, objects, margin=1.08):
    cam = scene.camera
    if cam is None:
        cam = bpy.data.objects.new("garu_camera", bpy.data.cameras.new("garu_camera"))
        scene.collection.objects.link(cam)
        scene.camera = cam
    cam.data.type = "ORTHO"
    pts = [o.matrix_world @ v.co for o in objects for v in o.data.vertices]
    center = sum(pts, Vector()) / len(pts)
    rot = (-VIEW_DIR).to_track_quat("-Z", "Y")
    right, up = rot @ Vector((1, 0, 0)), rot @ Vector((0, 1, 0))
    xs = [(p - center).dot(right) for p in pts]
    ys = [(p - center).dot(up) for p in pts]
    aspect = scene.render.resolution_x / scene.render.resolution_y
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    cam.data.ortho_scale = max(w, h * aspect) * margin
    mid = center + right * (max(xs) + min(xs)) / 2 + up * (max(ys) + min(ys)) / 2
    radius = max((p - center).length for p in pts)
    cam.location = mid + VIEW_DIR * (radius * 4 + 1)
    cam.rotation_euler = rot.to_euler()
    cam.data.clip_end = radius * 10 + 10


def _render(scene, path):
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def contact_sheet(scene, kit_scene, path):
    contract = kit_scene.contract
    cell = contract["profile"]["cell_size"]
    pieces = [p["id"] for p in contract["pieces"]]
    variants = list(contract["style"]["variants"])
    gap = 0.8 * cell
    widths = {p["id"]: p["footprint_cells"][0] * cell for p in contract["pieces"]}
    col_w = max(widths.values()) + gap
    shown = []
    for ps in kit_scene.sets:
        obj = ps.printable if ps.printable is not None else ps.lod0
        obj.location = (variants.index(ps.variant) * col_w, -pieces.index(ps.piece) * (2.2 * cell + gap), 0.0)
        shown.append(obj)
    for extra in kit_scene.clips:
        extra.location = (len(variants) * col_w, 0.0, 0.0)
        shown.append(extra)
    for obj in bpy.data.objects:
        obj.hide_render = obj.type == "MESH" and obj not in shown
    bpy.context.view_layer.update()  # matrix_world is stale until the depsgraph updates
    _setup_render(scene, 1600, 1400)
    _frame(scene, shown)
    return _render(scene, path)


# ----------------------------------------------------------- demo room ----

def room_layout(contract, rng):
    """(piece, variant, x_cells, y_cells, quarter_turns). Walls sit inside
    the room boundary; corners at the four room corners."""
    pick = lambda: rng.choice(list(contract["style"]["variants"]))
    layout = []
    for x, y in ((0, 0), (2, 0), (0, 2), (2, 2)):
        layout.append(("floor_2x2", pick(), x, y, 0))
    for (x, y), turns in (((0, 0), 0), ((4, 0), 1), ((4, 4), 2), ((0, 4), 3)):
        layout.append(("corner_outer", pick(), x, y, turns))
    layout += [
        ("wall_straight", pick(), 1, 0, 0), ("doorway", "clean", 2, 0, 0),
        ("wall_straight", pick(), 4, 1, 1), ("wall_straight", pick(), 4, 2, 1),
        ("wall_straight", pick(), 3, 4, 2), ("doorway", pick(), 2, 4, 2),
        ("wall_straight", pick(), 0, 3, 3), ("wall_straight", pick(), 0, 2, 3),
        ("pillar", pick(), 1.75, 1.75, 0),
    ]
    return layout


def _seam_planes(obj, piece, cell):
    """World-space seam planes of a placed piece: (group, axis, value, points)."""
    out = []
    mw = obj.matrix_world
    fx, fy = (v * cell for v in piece["footprint_cells"])
    for seam in piece.get("seams", []):
        axis = 0 if seam[0] == "x" else 1
        value = 0.0 if seam[1] == "0" else (fx if axis == 0 else fy)
        pts = [mw @ v.co for v in obj.data.vertices if abs(v.co[axis] - value) <= 1e-4 * cell]
        if not pts:
            continue
        # After a 90 degree turn a local x seam can lie on a world y plane.
        world_axis = 0 if all(abs(p.x - pts[0].x) < 1e-4 * cell for p in pts) else 1
        out.append((piece.get("seam_profile"), world_axis, round(pts[0][world_axis], 4), pts))
    return out


def demo_scene(scene, kit_scene, path, json_path):
    contract = kit_scene.contract
    cell = contract["profile"]["cell_size"]
    tol = contract["grid"]["snap_tolerance_cells"] * cell
    pieces = api.pieces_by_id(contract)
    by_key = {(ps.piece, ps.variant): ps.lod0 for ps in kit_scene.sets}
    rng = api.rng_for(kit_scene.seed, "demo_room")
    for obj in bpy.data.objects:
        obj.hide_render = True
    placed = []
    for i, (pid, variant, x, y, turns) in enumerate(room_layout(contract, rng)):
        src = by_key[(pid, variant)]
        inst = bpy.data.objects.new(f"demo_{i:02d}_{pid}_{variant}", src.data)
        scene.collection.objects.link(inst)
        inst.matrix_world = Matrix.Translation((x * cell, y * cell, 0.0)) @ Matrix.Rotation(turns * math.pi / 2, 4, "Z")
        placed.append((inst, pieces[pid]))
    bpy.context.view_layer.update()

    pairs = []
    planes = [(inst, _seam_planes(inst, piece, cell)) for inst, piece in placed]
    for i in range(len(planes)):
        for j in range(i + 1, len(planes)):
            for ga, ax, val, pa in planes[i][1]:
                for gb, bx, bval, pb in planes[j][1]:
                    if ga != gb or ax != bx or abs(val - bval) > tol:
                        continue
                    other = 1 - ax
                    a2 = [(p[other], p.z) for p in pa]
                    b2 = [(p[other], p.z) for p in pb]
                    lo = max(min(p[0] for p in a2), min(p[0] for p in b2)) - tol
                    hi = min(max(p[0] for p in a2), max(p[0] for p in b2)) + tol
                    if hi < lo:
                        continue
                    dev = max(max(min(math.dist(p, q) for q in b2) for p in a2),
                              max(min(math.dist(q, p) for p in a2) for q in b2))
                    pairs.append({"a": planes[i][0].name, "b": planes[j][0].name,
                                  "plane": f"{'xy'[ax]}={val}", "max_deviation": dev})
    worst = max((p["max_deviation"] for p in pairs), default=0.0)
    on_grid = all(abs(c / (cell * 0.25) - round(c / (cell * 0.25))) < 1e-6
                  for inst, _ in placed for c in inst.matrix_world.translation[:2])
    result = {"pieces_placed": len(placed), "seam_pairs": len(pairs), "max_seam_deviation": worst,
              "tolerance": tol, "placements_on_grid": on_grid,
              "passed": bool(pairs) and worst <= tol and on_grid, "pairs": pairs}
    write_json(json_path, result)
    print(f"DEMO pieces={len(placed)} seam_pairs={len(pairs)} max_deviation={worst:.3g} "
          f"tolerance={tol:.3g} passed={result['passed']}")
    _setup_render(scene, 1600, 1100)
    _frame(scene, [inst for inst, _ in placed])
    _render(scene, path)
    return result


def render_previews(kit_scene, out_dir):
    scene = bpy.context.scene
    prev = os.path.join(out_dir, "previews")
    os.makedirs(prev, exist_ok=True)
    contact_sheet(scene, kit_scene, os.path.join(prev, "contact_sheet.png"))
    return demo_scene(scene, kit_scene, os.path.join(prev, "demo_scene.png"), os.path.join(prev, "demo_scene.json"))
