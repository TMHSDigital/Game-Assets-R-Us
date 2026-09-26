# SPDX-License-Identifier: GPL-3.0-or-later
"""UV channels: the lightmap margin is honored at every allowed value."""

import math
import unittest

import bpy

from core.geometry import uv


def _seg_dist(p, a, b):
    (ax, ay), (bx, by), (px, py) = a, b, p
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return math.hypot(ax + t * dx - px, ay + t * dy - py)


def _cube():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    return bpy.context.active_object


class LightmapMargin(unittest.TestCase):
    def _layout(self, margin):
        obj = _cube()
        uv.box_project(obj, "UVMap", 0.5)
        uv.lightmap(obj, "Lightmap", "UVMap", margin)
        layer = obj.data.uv_layers["Lightmap"]
        # Smart project splits a cube into one island per face.
        polys = [[tuple(layer.data[li].uv) for li in p.loop_indices] for p in obj.data.polygons]
        gap = min(_seg_dist(p, b[k], b[k - 1])
                  for i, a in enumerate(polys) for j, b in enumerate(polys) if i != j
                  for p in a for k in range(len(b)))
        coords = [c for poly in polys for pt in poly for c in pt]
        border = min(min(coords), 1.0 - max(coords))
        overlaps = uv.overlap_pairs(uv.uv_triangles(obj.data, "Lightmap"))
        return gap, border, overlaps

    def test_margin_honored(self):
        # The margin is the clearance around each island: twice it between
        # islands, once to the edge of the UV square.
        for margin in (0.005, 0.01, 0.02, 0.05, 0.1):
            with self.subTest(margin=margin):
                gap, border, overlaps = self._layout(margin)
                self.assertEqual(overlaps, 0)
                self.assertGreaterEqual(gap, 2 * margin - 1e-4)
                self.assertGreaterEqual(border, margin - 1e-4)
                # And not much more: the margin is not silently clamped or inflated.
                self.assertLess(border, margin * 1.5)


if __name__ == "__main__":
    unittest.main()
