# SPDX-License-Identifier: GPL-3.0-or-later
"""Intentionally broken fixture meshes for the validator tests.

Fixtures are built at test time (no binary files in the repo). All sizes are
in profile units (meters for unity, millimeters for stl_print).
"""

import bmesh
import bpy

from core import materials
from core.contract import load_contract, resolve
from core.generators import api, get
from core.geometry import prims
from core.geometry import uv as uv_mod
from core.pipeline import KitScene, PieceSet, reset_scene


def contract(profile):
    return resolve(load_contract(get("stone-dungeon-wall-sampler").contract_path), profile)


def fresh(profile):
    reset_scene()
    c = contract(profile)
    materials.ensure_palette(c)
    return c


def box(name, lo, hi, cuts=0, open_top=False):
    bm = bmesh.new()
    prims.add_box(bm, lo, hi)
    prims.recalc_normals(bm)
    if cuts:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
    if open_top:
        bm.normal_update()
        top = [f for f in bm.faces if f.normal.z > 0.99]
        bmesh.ops.delete(bm, geom=top, context="FACES_ONLY")
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    obj = prims.to_object(bm, name)
    bm.free()
    return obj


def dress(c, obj):
    """Palette material and both UV channels, like the pipeline does."""
    obj.data.materials.append(api.material(c, "stone"))
    cell = c["profile"]["cell_size"]
    uv_mod.box_project(obj, c["uv"]["tiling_channel"], c["uv"]["tiling_scale_per_cell"], cell=cell)
    uv_mod.lightmap(obj, c["uv"]["lightmap_channel"], c["uv"]["tiling_channel"], 0.01)
    return obj


def wall(c, variant="clean", thickness_cells=0.25, cuts=0, name=None):
    cell = c["profile"]["cell_size"]
    obj = box(name or api.piece_name(c, "wall_straight", variant), (0, 0, 0),
              (cell, thickness_cells * cell, 2 * cell), cuts=cuts)
    return dress(c, obj)


def scene(c, sets, seed=1337):
    return KitScene(c, seed, sets)


def piece_set(obj, piece="wall_straight", variant="clean"):
    return PieceSet(piece, variant, obj)


def two_overlapping_boxes(name):
    bm = bmesh.new()
    prims.add_box(bm, (0, 0, 0), (1, 1, 1))
    prims.add_box(bm, (0.5, 0.5, 0.5), (1.5, 1.5, 1.5))
    prims.recalc_normals(bm)
    obj = prims.to_object(bm, name)
    bm.free()
    return obj


def mushroom(name):
    """A 40 x 40 mm cap on a 10 x 10 mm post: an unsupported overhang."""
    bm = bmesh.new()
    prims.add_loft(bm, [(0, 15, 15, 25, 25), (20, 15, 15, 25, 25), (20, 0, 0, 40, 40), (25, 0, 0, 40, 40)])
    prims.recalc_normals(bm)
    obj = prims.to_object(bm, name)
    bm.free()
    return obj


def clear_objects():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
