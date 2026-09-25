# SPDX-License-Identifier: GPL-3.0-or-later
"""bmesh primitives that always produce closed, manifold solids.

Pieces are built from extruded profiles (prisms) and lofted rings rather than
from overlapping boxes, so no boolean is needed and every shell is watertight
by construction. Box and bevel helpers are adapted from the author's
Blender-Developer-Tools (showcase/fence-kit/fence_kit.py add_box), relicensed
here under GPL-3.0-or-later.
"""

import bmesh
import bpy
from mathutils import Vector

AXES = {"x": 0, "y": 1, "z": 2}


def _place(u, v, w, axes):
    co = [0.0, 0.0, 0.0]
    co[AXES[axes[0]]] = u
    co[AXES[axes[1]]] = v
    co[AXES[axes[2]]] = w
    return Vector(co)


def add_prism(bm, poly2d, w0, w1, axes=("x", "y", "z")):
    """Extrude a simple 2D polygon (list of (u, v)) from w0 to w1.

    axes names which world axis u, v and w map to, so ("x", "z", "y") builds
    a front profile in the XZ plane extruded along Y. Winding is fixed up by
    recalc_normals() once the whole solid is built.
    """
    bottom = [bm.verts.new(_place(u, v, w0, axes)) for u, v in poly2d]
    top = [bm.verts.new(_place(u, v, w1, axes)) for u, v in poly2d]
    n = len(poly2d)
    faces = [bm.faces.new(list(reversed(bottom))), bm.faces.new(top)]
    for i in range(n):
        j = (i + 1) % n
        faces.append(bm.faces.new((bottom[i], bottom[j], top[j], top[i])))
    return faces


def add_box(bm, lo, hi):
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    return add_prism(bm, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1)


def add_loft(bm, rings):
    """Closed loft through rectangular rings [(z, x0, y0, x1, y1), ...],
    bottom to top, capped at both ends. Used for pillars with plinth and
    capital without any boolean union."""
    loops = []
    for z, x0, y0, x1, y1 in rings:
        loops.append([bm.verts.new((x0, y0, z)), bm.verts.new((x1, y0, z)),
                      bm.verts.new((x1, y1, z)), bm.verts.new((x0, y1, z))])
    faces = [bm.faces.new(list(reversed(loops[0]))), bm.faces.new(loops[-1])]
    for lower, upper in zip(loops, loops[1:]):
        for i in range(4):
            j = (i + 1) % 4
            faces.append(bm.faces.new((lower[i], lower[j], upper[j], upper[i])))
    return faces


def recalc_normals(bm):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])


def chamfer_edges(bm, width, segments=1, exclude_z0=True, exclude=None):
    """Bevel every sharp edge with one consistent width and profile.

    Edges lying on z = 0 are skipped when exclude_z0 is set: they are contact
    edges that sit on the floor or on a print base. `exclude(edge)` can veto
    further edges.
    """
    if width <= 0:
        return
    bm.normal_update()
    edges = []
    for e in bm.edges:
        if len(e.link_faces) != 2:
            continue
        if e.calc_face_angle(0.0) < 0.35:  # about 20 degrees: not a hard edge
            continue
        if exclude_z0 and abs(e.verts[0].co.z) < 1e-9 and abs(e.verts[1].co.z) < 1e-9:
            continue
        if exclude and exclude(e):
            continue
        edges.append(e)
    if edges:
        bmesh.ops.bevel(bm, geom=edges, offset=width, offset_type="OFFSET",
                        segments=segments, profile=0.5, affect="EDGES",
                        clamp_overlap=True)


def to_object(bm, name, collection=None):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj
