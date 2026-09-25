# SPDX-License-Identifier: GPL-3.0-or-later
"""External generator fixture: one beveled plinth block per variant.

Uses only the public helpers a private generator would use.
"""

import bpy
import bmesh

from core.generators import api
from core.geometry import prims, uv


def build(contract, seed, piece_ids):
    objects = []
    pieces = api.pieces_by_id(contract)
    for piece_id in piece_ids:
        piece = pieces[piece_id]
        sx, sy = piece["footprint_cells"]
        sz = piece["height_cells"]
        for variant in contract["style"]["variants"]:
            rng = api.rng_for(seed, piece_id, variant)
            bm = bmesh.new()
            prims.add_box(bm, (0.0, 0.0, 0.0), (sx, sy, sz))
            prims.chamfer_edges(bm, contract["style"]["bevel_width_cells"], exclude_z0=True)
            name = api.piece_name(contract, piece_id, variant)
            mesh = bpy.data.meshes.new(name)
            bm.to_mesh(mesh)
            bm.free()
            obj = bpy.data.objects.new(name, mesh)
            bpy.context.scene.collection.objects.link(obj)
            obj.data.materials.append(api.material(contract, contract["materials"]["palette"][0]["slot"]))
            uv.box_project(obj, contract["uv"]["tiling_channel"], contract["uv"]["tiling_scale_per_cell"])
            obj["demo_rng_probe"] = rng.randint(0, 1000)
            api.tag(obj, piece_id, variant, api.ROLE_MESH)
            objects.append(obj)
    return objects
