# SPDX-License-Identifier: GPL-3.0-or-later
"""Convex collider parts.

The convex hull approach is adapted from the author's Blender-Developer-Tools
(snippets/convex_hull_collider.py), relicensed here under GPL-3.0-or-later.
The hull is built from a vertex-only bmesh so no source faces survive into
the collider.
"""

import bmesh
import bpy
from mathutils import Vector


def convex_hull(points, name, collection=None):
    bm = bmesh.new()
    try:
        verts = [bm.verts.new(p) for p in points]
        result = bmesh.ops.convex_hull(bm, input=verts)
        drop = {g for g in list(result.get("geom_interior") or []) + list(result.get("geom_unused") or [])
                if isinstance(g, bmesh.types.BMVert)}
        if drop:
            bmesh.ops.delete(bm, geom=sorted(drop, key=lambda v: v.index), context="VERTS")
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-7)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        # recalc_face_normals can flip a sliver triangle on a plane holding
        # many coplanar points; on a convex hull every face faces away from
        # the centroid.
        center = sum((v.co for v in bm.verts), Vector()) / len(bm.verts)
        bm.normal_update()
        inward = [f for f in bm.faces if (f.calc_center_median() - center).dot(f.normal) < 0.0]
        if inward:
            bmesh.ops.reverse_faces(bm, faces=inward)
        mesh = bpy.data.meshes.new(name)
        bm.to_mesh(mesh)
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, mesh)
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def hull_of_object(src, name):
    mw = src.matrix_world
    return convex_hull([mw @ v.co for v in src.data.vertices], name,
                       src.users_collection[0] if src.users_collection else None)


def box(lo, hi, name, collection=None):
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    pts = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    return convex_hull(pts, name, collection)
