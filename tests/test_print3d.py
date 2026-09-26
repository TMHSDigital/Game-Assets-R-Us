# SPDX-License-Identifier: GPL-3.0-or-later
"""Printable tiles and the dogbone clip (core/print3d.py), and the print
settings sheet built from them (core/print_sheet.py)."""

import json
import os
import shutil
import tempfile
import unittest

import bmesh

from core import pipeline, print3d
from core.contract import load_contract, resolve
from core.generators import get, load_module
from core.print_sheet import write_print_sheet
from core.validators import metrics

KIT = "stone-dungeon-wall-sampler"
PIECES = ["wall_straight", "floor_2x2"]
TOL = 1e-3  # mm


def _is_closed_manifold(obj):
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        return bool(bm.edges) and all(len(e.link_faces) == 2 for e in bm.edges)
    finally:
        bm.free()


def _flat_area(obj, z, sign):
    """Area of faces lying in the plane at height z whose normal points
    along sign * Z."""
    area = 0.0
    for poly in obj.data.polygons:
        if poly.normal.z * sign > 0.999 and all(abs(obj.data.vertices[v].co.z - z) < TOL for v in poly.vertices):
            area += poly.area
    return area


def _pocket_area(clip):
    """Area of one T pocket inside the base (the part at w >= 0)."""
    return clip["neck_width_mm"] * clip["neck_length_mm"] + clip["head_width_mm"] * clip["head_length_mm"]


class ClipGeometry(unittest.TestCase):
    """Pure geometry of the socket system, no Blender scene needed."""

    @classmethod
    def setUpClass(cls):
        cls.contract = resolve(load_contract(get(KIT).contract_path), "stl_print")
        cls.clip = cls.contract["print"]["clip_system"]

    def test_socket_frames(self):
        for tx, ty in ((1, 1), (2, 2), (3, 1)):
            cell = 25.4
            frames = print3d.socket_frames(tx, ty, cell)
            with self.subTest(base=(tx, ty)):
                self.assertEqual(len(frames), 2 * (tx + ty))
                self.assertEqual(len({(round(o.x, 3), round(o.y, 3)) for o, _, _ in frames}), len(frames))
                for origin, u, w in frames:
                    # mathutils vectors are single precision.
                    self.assertAlmostEqual(u.dot(w), 0.0, places=5)
                    self.assertAlmostEqual(u.length, 1.0, places=5)
                    self.assertAlmostEqual(w.length, 1.0, places=5)
                    # On the perimeter, at a cell edge midpoint ...
                    on_x = abs(origin.y) < 1e-4 or abs(origin.y - ty * cell) < 1e-4
                    on_y = abs(origin.x) < 1e-4 or abs(origin.x - tx * cell) < 1e-4
                    self.assertTrue(on_x != on_y, f"{origin} is not on exactly one base edge")
                    along = origin.x if on_x else origin.y
                    self.assertAlmostEqual((along / cell) % 1.0, 0.5, places=5)
                    # ... with w pointing into the base.
                    inside = origin + w * 1.0
                    self.assertTrue(0 < inside.x < tx * cell and 0 < inside.y < ty * cell)

    def test_clip_fits_the_double_pocket_with_tolerance(self):
        c, t = self.clip, self.clip["tolerance_mm"]
        pocket = print3d.pocket_outline(c)
        clip = print3d.clip_outline(c)
        # Pocket: opens 1 mm outside the edge, depth neck + head.
        self.assertAlmostEqual(min(w for _, w in pocket), -1.0)
        self.assertAlmostEqual(max(w for _, w in pocket), c["neck_length_mm"] + c["head_length_mm"])
        self.assertAlmostEqual(max(u for u, _ in pocket), c["head_width_mm"] / 2)
        # Two facing pockets form a slot 2 * (neck + head) long; the clip is
        # shorter by the tolerance at both ends, narrower by it on each side.
        xs, ys = [x for x, _ in clip], [y for _, y in clip]
        self.assertAlmostEqual(max(xs) - min(xs), 2 * (c["neck_length_mm"] + c["head_length_mm"] - t))
        self.assertAlmostEqual(max(ys) - min(ys), c["head_width_mm"] - 2 * t)
        half_widths = sorted({round(abs(y), 9) for _, y in clip})
        self.assertEqual(len(half_widths), 2)
        self.assertAlmostEqual(half_widths[0], c["neck_width_mm"] / 2 - t)
        self.assertAlmostEqual(half_widths[1], c["head_width_mm"] / 2 - t)
        # The heads start t beyond the neck/head step of the pocket.
        inner = min(abs(x) for x, y in clip if abs(y) > c["neck_width_mm"] / 2)
        self.assertAlmostEqual(inner, c["neck_length_mm"] + t)
        dims = print3d.expected_clip_dims(c)
        self.assertAlmostEqual(dims[0], max(xs) - min(xs))
        self.assertAlmostEqual(dims[1], max(ys) - min(ys))
        self.assertAlmostEqual(dims[2], c["height_mm"] - t)


class Printables(unittest.TestCase):
    """make_printables on a real stl_print scene (two pieces, all variants)."""

    @classmethod
    def setUpClass(cls):
        info = get(KIT)
        cls.contract = resolve(load_contract(info.contract_path), "stl_print")
        cls.scene = pipeline.generate(cls.contract, load_module(info), 1337, piece_ids=PIECES)
        cls.clip = cls.contract["print"]["clip_system"]
        cls.tmp = tempfile.mkdtemp(prefix="garu_print_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_every_piece_set_has_a_printable_and_one_clip(self):
        self.assertTrue(self.scene.sets)
        self.assertEqual(sorted({ps.piece for ps in self.scene.sets}), sorted(PIECES))
        for ps in self.scene.sets:
            self.assertIsNotNone(ps.printable, ps.name)
            self.assertEqual(ps.printable.name, f"{ps.name}_print")
        self.assertEqual(len(self.scene.clips), 1)
        self.assertTrue(any(n.startswith("boolean solver:") for n in self.scene.notes))

    def test_printable_is_a_closed_solid_on_the_plate(self):
        cell = self.contract["profile"]["cell_size"]
        pieces = {p["id"]: p for p in self.contract["pieces"]}
        for ps in self.scene.sets:
            obj = ps.printable
            tx, ty = pieces[ps.piece]["print_base_cells"]
            lo, hi = metrics.bbox_world(obj)
            with self.subTest(piece=ps.name):
                self.assertTrue(_is_closed_manifold(obj), "printable is not a closed 2-manifold")
                self.assertTrue(all(len(p.vertices) == 3 for p in obj.data.polygons), "not triangulated")
                self.assertAlmostEqual(lo.z, 0.0, delta=TOL)
                self.assertAlmostEqual(lo.x, 0.0, delta=TOL)
                self.assertAlmostEqual(lo.y, 0.0, delta=TOL)
                self.assertAlmostEqual(hi.x, tx * cell, delta=TOL)
                self.assertAlmostEqual(hi.y, ty * cell, delta=TOL)
                self.assertGreater(hi.z, self.contract["print"]["base_height_mm"])
                self.assertEqual(list(obj["garu_print_base"]), [tx, ty])

    def test_sockets_are_cut_into_the_underside(self):
        cell = self.contract["profile"]["cell_size"]
        pieces = {p["id"]: p for p in self.contract["pieces"]}
        per_pocket = _pocket_area(self.clip)
        for ps in self.scene.sets:
            obj = ps.printable
            tx, ty = pieces[ps.piece]["print_base_cells"]
            sockets = 2 * (tx + ty)
            with self.subTest(piece=ps.name):
                # Underside: the full base minus one T pocket per perimeter cell edge.
                self.assertAlmostEqual(_flat_area(obj, 0.0, -1), tx * ty * cell * cell - sockets * per_pocket,
                                       delta=0.01)
                # Pocket roofs: downward faces at the pocket height, one T each.
                self.assertAlmostEqual(_flat_area(obj, self.clip["height_mm"], -1), sockets * per_pocket,
                                       delta=0.01)

    def test_clip_object_matches_expected_dims(self):
        clip_obj = self.scene.clips[0]
        lo, hi = metrics.bbox_world(clip_obj)
        for got, want in zip(hi - lo, print3d.expected_clip_dims(self.clip)):
            self.assertAlmostEqual(got, want, delta=TOL)
        self.assertAlmostEqual(lo.z, 0.0, delta=TOL)
        self.assertTrue(_is_closed_manifold(clip_obj))
        self.assertEqual(clip_obj.name, f"SM_{self.contract['kit']['prefix']}_clip_dogbone")

    def test_print_sheet(self):
        out = os.path.join(self.tmp, "sheet")
        exp = os.path.join(out, "exports")
        os.makedirs(os.path.join(out, "reports"))
        os.makedirs(exp)
        first = self.scene.sets[0]
        # A measured report for the first piece; the rest have none.
        report = {"object": first.name, "checks": [
            {"id": "STL.WALL.MIN", "detail": {"min_mm": 1.234}},
            {"id": "STL.OVERHANG", "detail": {"bridged_mm2": 5.67, "unsupported_mm2": 0.0}}]}
        with open(os.path.join(out, "reports", f"{first.name}.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh)
        with open(os.path.join(out, "reports", "summary.json"), "w", encoding="utf-8") as fh:
            json.dump({"object": "ignored", "checks": []}, fh)

        path = write_print_sheet(self.scene, out, exp)
        self.assertEqual(path, os.path.join(exp, "print_settings.md"))
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        rows = {line.split(" | ")[0].lstrip("| "): line for line in text.splitlines() if ".stl |" in line}
        self.assertEqual(set(rows), {f"{ps.name}.stl" for ps in self.scene.sets} | {f"{self.scene.clips[0].name}.stl"})
        self.assertIn("| 1.23 | 5.7 |", rows[f"{first.name}.stl"])
        for ps in self.scene.sets[1:]:
            self.assertTrue(rows[f"{ps.name}.stl"].endswith("| n/a | n/a |"))
        dims = " x ".join(f"{d:.2f}" for d in print3d.expected_clip_dims(self.clip))
        self.assertIn(f"| Clip size (l x w x h) | {dims} mm |", text)
        pr = self.contract["print"]
        self.assertIn(f"| Pocket height / roof | {self.clip['height_mm']} / "
                      f"{pr['base_height_mm'] - self.clip['height_mm']} mm |", text)
        self.assertIn(f"seed {self.scene.seed}", text)
        self.assertIn(self.contract["legal"]["license"], text)
        self.assertTrue(text.isascii())


if __name__ == "__main__":
    unittest.main()
