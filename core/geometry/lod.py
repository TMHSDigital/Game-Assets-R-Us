# SPDX-License-Identifier: GPL-3.0-or-later
"""Triangle counting and LOD chains.

evaluated_triangle_count and the collapse-decimate approach are adapted from
the author's Blender-Developer-Tools (snippets/lod_chain.py), relicensed here
under GPL-3.0-or-later. Unlike the snippet, LODs are baked into real mesh
data (no live modifier), and the ratio is tightened until the budget holds,
because collapse decimation can land a few triangles over its ratio.
"""

import bpy


def triangle_count(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    try:
        mesh.calc_loop_triangles()
        return len(mesh.loop_triangles)
    finally:
        eval_obj.to_mesh_clear()


def _decimated_copy(src, ratio, name):
    mesh = src.data.copy()
    obj = bpy.data.objects.new(name, mesh)
    for coll in src.users_collection:
        coll.objects.link(obj)
    obj.matrix_world = src.matrix_world.copy()
    mod = obj.modifiers.new("garu_decimate", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.use_collapse_triangulate = True
    mod.ratio = ratio
    depsgraph = bpy.context.evaluated_depsgraph_get()
    baked = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
    obj.modifiers.remove(mod)
    old = obj.data
    obj.data = baked
    bpy.data.meshes.remove(old)
    baked.name = name
    return obj


def make_lod(src, budget, name, attempts=10):
    """Decimate a copy of `src` until it has at most `budget` triangles."""
    current = triangle_count(src)
    ratio = min(1.0, budget / max(current, 1))
    for _ in range(attempts):
        lod = _decimated_copy(src, ratio, name)
        if triangle_count(lod) <= budget:
            return lod
        bpy.data.objects.remove(lod)
        ratio *= 0.9
    raise RuntimeError(f"could not decimate {src.name} to {budget} triangles")
