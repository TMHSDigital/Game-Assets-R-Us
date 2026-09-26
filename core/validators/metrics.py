# SPDX-License-Identifier: GPL-3.0-or-later
"""Mesh measurements shared by the validators.

hygiene() and signed_volume() are adapted from the author's
Blender-Developer-Tools (examples/mesh-hygiene-audit/mesh_hygiene_audit.py),
relicensed here under GPL-3.0-or-later.
"""

import math

import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

AREA_EPS = 1e-10


def bm_world(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    bm.normal_update()
    return bm


def hygiene(obj):
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        faces = len(bm.faces)
        out = {
            "verts": len(bm.verts),
            "edges": len(bm.edges),
            "faces": faces,
            "non_manifold_edges": sum(1 for e in bm.edges if len(e.link_faces) != 2),
            "boundary_edges": sum(1 for e in bm.edges if len(e.link_faces) == 1),
            # Two faces whose winding disagrees across their shared edge: one
            # of them is flipped. Signed volume alone misses this when the
            # flipped face lies on a plane through the origin.
            "flipped_edges": sum(1 for e in bm.edges if len(e.link_faces) == 2 and not e.is_contiguous),
            # Bowtie vertices (two fans meeting at a point) and any vertex on
            # a boundary or non-manifold edge.
            "non_manifold_verts": sum(1 for v in bm.verts if v.link_edges and not v.is_manifold),
            "loose_verts": sum(1 for v in bm.verts if not v.link_edges),
            "loose_edges": sum(1 for e in bm.edges if not e.link_faces),
            "zero_area_faces": sum(1 for f in bm.faces if f.calc_area() <= AREA_EPS),
            "signed_volume": bm.calc_volume(signed=True),
        }
        out["euler"] = out["verts"] - out["edges"] + faces
        out["shells"] = _shells(bm)
        out["self_intersections"] = self_intersections(bm)
    finally:
        bm.free()
    return out


def self_intersections(bm):
    """Pairs of faces that intersect without sharing a vertex."""
    bm.faces.ensure_lookup_table()
    bvh = BVHTree.FromBMesh(bm)
    count = 0
    for i, j in bvh.overlap(bvh):
        if i >= j:
            continue
        a = {v.index for v in bm.faces[i].verts}
        if not a.intersection(v.index for v in bm.faces[j].verts):
            count += 1
    return count


def _shells(bm):
    seen = set()
    shells = 0
    for v in bm.verts:
        if v.index in seen:
            continue
        shells += 1
        stack = [v]
        while stack:
            cur = stack.pop()
            if cur.index in seen:
                continue
            seen.add(cur.index)
            stack.extend(e.other_vert(cur) for e in cur.link_edges)
    return shells


XFORM_EPS = 1e-6


def basis_error(obj):
    """Largest deviation of the object's own rotation and scale from
    identity. matrix_basis combines every rotation mode (Euler, quaternion,
    axis-angle) with the delta transforms and needs no depsgraph update."""
    m = obj.matrix_basis.to_3x3()
    return max(abs(m[i][j] - (1.0 if i == j else 0.0)) for i in range(3) for j in range(3))


def xform_state(obj):
    """Rotation and scale as the user sees them, for reports."""
    rot = {"QUATERNION": obj.rotation_quaternion, "AXIS_ANGLE": obj.rotation_axis_angle}
    return {"rotation_mode": obj.rotation_mode,
            "rotation": list(rot.get(obj.rotation_mode, obj.rotation_euler)),
            "scale": list(obj.scale),
            "delta_rotation": list(obj.delta_rotation_quaternion if obj.rotation_mode in rot
                                   else obj.delta_rotation_euler),
            "delta_scale": list(obj.delta_scale)}


def bbox_local(obj):
    cos = [v.co for v in obj.data.vertices]
    lo = Vector((min(c.x for c in cos), min(c.y for c in cos), min(c.z for c in cos)))
    hi = Vector((max(c.x for c in cos), max(c.y for c in cos), max(c.z for c in cos)))
    return lo, hi


def bbox_world(obj):
    mw = obj.matrix_world
    cos = [mw @ v.co for v in obj.data.vertices]
    lo = Vector((min(c.x for c in cos), min(c.y for c in cos), min(c.z for c in cos)))
    hi = Vector((max(c.x for c in cos), max(c.y for c in cos), max(c.z for c in cos)))
    return lo, hi


def is_convex(obj, tol):
    """Max distance of any vertex in front of any face plane (0 for convex)."""
    mesh = obj.data
    worst = 0.0
    for poly in mesh.polygons:
        c, n = poly.center, poly.normal
        for v in mesh.vertices:
            worst = max(worst, (v.co - c).dot(n))
    return worst <= tol, worst


class Solid:
    """World-space BVH with inside tests and inward thickness rays."""

    # Three skewed, irrational-ish directions; the inside test takes a
    # majority vote so one ray grazing an edge or vertex cannot flip it.
    DIRS = [Vector(d).normalized() for d in ((0.5773, 0.5774, 0.5773),
                                             (-0.4142, 0.7071, 0.5720),
                                             (0.2679, -0.8391, 0.4735))]

    def __init__(self, obj):
        self.bm = bm_world(obj)
        self.bvh = BVHTree.FromBMesh(self.bm)

    def free(self):
        self.bm.free()

    def _parity(self, p, direction, max_hits=64):
        hits = 0
        origin = Vector(p)
        for _ in range(max_hits):
            loc, _n, _i, _d = self.bvh.ray_cast(origin, direction)
            if loc is None:
                break
            hits += 1
            origin = loc + direction * 1e-5
        return hits % 2 == 1

    def inside(self, p):
        return sum(self._parity(p, d) for d in self.DIRS) >= 2

    def thickness(self, p, n, eps=1e-4):
        """(distance, hit normal) from surface point p along -n to the far
        side, or (None, None) if the ray escapes."""
        loc, hit_n, _i, dist = self.bvh.ray_cast(p - n * eps, -n)
        return (None, None) if loc is None else (dist + eps, hit_n)


def triangle_samples(obj):
    """(centroid, normal, area) per loop triangle, world space."""
    mesh = obj.data
    mesh.calc_loop_triangles()
    mw = obj.matrix_world
    rot = mw.to_3x3()
    out = []
    for tri in mesh.loop_triangles:
        a, b, c = (mw @ mesh.vertices[i].co for i in tri.vertices)
        cross = (b - a).cross(c - a)
        area = cross.length * 0.5
        if area <= AREA_EPS:
            continue
        n = (rot @ tri.normal).normalized()
        out.append(((a + b + c) / 3.0, n, area, (a, b, c)))
    return out


def angle_below_horizontal(n):
    """0 for a vertical face, 90 for a flat ceiling; negative for up-facing."""
    return math.degrees(math.asin(max(-1.0, min(1.0, -n.z))))
