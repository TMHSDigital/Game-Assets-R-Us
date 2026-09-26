# SPDX-License-Identifier: GPL-3.0-or-later
"""Canonical mesh order (core/geometry/canonical.py): the same geometry
built in a different element order, or with last-bit float noise, becomes
the same mesh, and face materials, smoothing and UVs follow their faces."""

import unittest

import bpy

from core import pipeline
from core.geometry import canonical

# Two unit quads side by side, plus a triangle on top of the first one.
VERTS = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0),
         (2.0, 0.0, 0.0), (2.0, 1.0, 0.0), (1.0, 2.0, 0.0)]
FACES = [(0, 1, 2, 3), (1, 4, 5, 2), (3, 2, 6)]
MATS = [0, 1, 1]
SMOOTH = [False, True, False]


def _mesh(name, order, face_order, rotate, noise=0.0):
    """Build VERTS/FACES with vertices listed in `order`, faces in
    `face_order`, each face loop rotated by `rotate`, positions offset by
    `noise`. UV = (x, y) of the vertex, material/smooth per face."""
    remap = {old: new for new, old in enumerate(order)}
    verts = [tuple(c + noise for c in VERTS[i]) for i in order]
    faces, mats, smooth = [], [], []
    for fi in face_order:
        f = [remap[v] for v in FACES[fi]]
        k = rotate % len(f)
        faces.append(f[k:] + f[:k])
        mats.append(MATS[fi])
        smooth.append(SMOOTH[fi])
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for slot in ("garu_test_a", "garu_test_b"):
        mesh.materials.append(bpy.data.materials.get(slot) or bpy.data.materials.new(slot))
    mesh.polygons.foreach_set("material_index", mats)
    mesh.polygons.foreach_set("use_smooth", smooth)
    uv = mesh.uv_layers.new(name="UVMap")
    for loop in mesh.loops:
        co = mesh.vertices[loop.vertex_index].co
        uv.data[loop.index].uv = (co.x, co.y)
    return mesh


def _snapshot(mesh):
    uv = mesh.uv_layers["UVMap"].data
    return {
        "verts": [tuple(round(c, 6) for c in v.co) for v in mesh.vertices],
        "faces": [tuple(p.vertices) for p in mesh.polygons],
        "mats": [p.material_index for p in mesh.polygons],
        "smooth": [p.use_smooth for p in mesh.polygons],
        "uvs": [tuple(round(c, 6) for c in uv[li].uv) for p in mesh.polygons for li in p.loop_indices],
        "materials": [m.name for m in mesh.materials],
    }


class Canonical(unittest.TestCase):
    def setUp(self):
        pipeline.reset_scene()

    def test_element_order_does_not_matter(self):
        a = canonical.canonicalize(_mesh("a", [0, 1, 2, 3, 4, 5, 6], [0, 1, 2], 0))
        b = canonical.canonicalize(_mesh("b", [6, 4, 2, 0, 5, 3, 1], [2, 0, 1], 1))
        c = canonical.canonicalize(_mesh("c", [3, 5, 1, 6, 0, 2, 4], [1, 2, 0], 3))
        self.assertEqual(_snapshot(a), _snapshot(b))
        self.assertEqual(_snapshot(a), _snapshot(c))

    def test_vertices_sorted_and_loops_start_at_lowest_index(self):
        snap = _snapshot(canonical.canonicalize(_mesh("m", [6, 5, 4, 3, 2, 1, 0], [2, 1, 0], 2)))
        self.assertEqual(snap["verts"], sorted(snap["verts"]))
        self.assertEqual(snap["faces"], sorted(snap["faces"]))
        for face in snap["faces"]:
            self.assertEqual(face[0], min(face))

    def test_float_noise_is_quantized(self):
        a = canonical.canonicalize(_mesh("a", [0, 1, 2, 3, 4, 5, 6], [0, 1, 2], 0))
        b = canonical.canonicalize(_mesh("b", [0, 1, 2, 3, 4, 5, 6], [0, 1, 2], 0, noise=-3e-8))
        self.assertEqual(_snapshot(a), _snapshot(b))

    def test_attributes_follow_their_faces(self):
        mesh = canonical.canonicalize(_mesh("m", [5, 3, 1, 6, 0, 2, 4], [1, 2, 0], 1))
        self.assertEqual([m.name for m in mesh.materials], ["garu_test_a", "garu_test_b"])
        uv = mesh.uv_layers["UVMap"].data
        for poly in mesh.polygons:
            pos = sorted(tuple(round(c, 6) for c in mesh.vertices[v].co) for v in poly.vertices)
            fi = next(i for i, f in enumerate(FACES) if sorted(VERTS[v] for v in f) == pos)
            with self.subTest(face=fi):
                self.assertEqual(poly.material_index, MATS[fi])
                self.assertEqual(poly.use_smooth, SMOOTH[fi])
                for li in poly.loop_indices:
                    co = mesh.vertices[mesh.loops[li].vertex_index].co
                    self.assertAlmostEqual(uv[li].uv[0], co.x, places=6)
                    self.assertAlmostEqual(uv[li].uv[1], co.y, places=6)

    def test_finalize_triangulates_identically(self):
        a = canonical.finalize(_mesh("a", [0, 1, 2, 3, 4, 5, 6], [0, 1, 2], 0))
        b = canonical.finalize(_mesh("b", [6, 4, 2, 0, 5, 3, 1], [2, 0, 1], 1))
        self.assertTrue(all(len(p.vertices) == 3 for p in a.polygons))
        self.assertEqual(len(a.polygons), 2 + 2 + 1)
        self.assertEqual(_snapshot(a), _snapshot(b))

    def test_canonicalize_objects_skips_non_meshes(self):
        mesh_obj = bpy.data.objects.new("m", _mesh("m", [6, 5, 4, 3, 2, 1, 0], [2, 1, 0], 0))
        empty = bpy.data.objects.new("e", None)
        canonical.canonicalize_objects([mesh_obj, empty])
        verts = _snapshot(mesh_obj.data)["verts"]
        self.assertEqual(verts, sorted(verts))


if __name__ == "__main__":
    unittest.main()
