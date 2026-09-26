# SPDX-License-Identifier: GPL-3.0-or-later
"""Validators on intentionally broken fixtures: each must fail with its
expected check ID, and a matching control fixture must pass it."""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures"))

import bmesh  # noqa: E402
import bpy  # noqa: E402
import make_broken as fx  # noqa: E402

from core.generators import api  # noqa: E402
from core.geometry import prims  # noqa: E402
from core.geometry import lod as lod_mod  # noqa: E402
from core.geometry import uv as uv_mod  # noqa: E402
from core.validators import core_checks, fixes, legal_checks, stl_checks  # noqa: E402


def flip_bottom(obj):
    """Invert the winding of the faces on z = 0. With the pivot on that
    plane the signed volume does not change, so only the winding check can
    see it."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.reverse_faces(bm, faces=[f for f in bm.faces if all(abs(v.co.z) < 1e-6 for v in f.verts)])
    bm.to_mesh(obj.data)
    bm.free()
    return obj


def bowtie(name):
    """Two closed boxes touching at a single corner vertex."""
    bm = bmesh.new()
    prims.add_box(bm, (0, 0, 0), (10, 10, 10))
    prims.add_box(bm, (10, 10, 10), (20, 20, 20))
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    prims.recalc_normals(bm)
    obj = prims.to_object(bm, name)
    bm.free()
    return obj


def front_profile(name, outline, depth=20):
    """A solid from an XZ outline (mm) extruded 0..depth along Y."""
    bm = bmesh.new()
    prims.add_prism(bm, outline, 0, depth, axes=("x", "z", "y"))
    prims.recalc_normals(bm)
    obj = prims.to_object(bm, name)
    bm.free()
    return obj


# A 10 mm flat ceiling held by a post on each side, and the same ceiling as a
# ledge held on one side only. Both are well under max_bridge_mm = 14.
GATE = [(0, 0), (5, 0), (5, 10), (15, 10), (15, 0), (20, 0), (20, 15), (0, 15)]
LEDGE = [(0, 0), (5, 0), (5, 10), (15, 10), (15, 15), (0, 15)]


def status(checks, check_id):
    found = [c.status for c in checks if c.id == check_id]
    assert found, f"check {check_id} not reported; got {[c.id for c in checks]}"
    return "fail" if "fail" in found else found[0]


class CoreCheckFixtures(unittest.TestCase):
    def setUp(self):
        self.c = fx.fresh("unity")

    def ctx(self, *sets):
        ctx = core_checks.Context(fx.scene(self.c, list(sets)))
        core_checks.build_seam_refs(ctx)
        return ctx

    def test_off_grid_fails_grid_snap(self):
        good = fx.wall(self.c)
        ctx = self.ctx(fx.piece_set(good))
        self.assertEqual(status(core_checks.check_grid(ctx, ctx.scene.sets[0]), "CORE.GRID.SNAP"), "pass")
        good.location.x += 0.013
        bpy.context.view_layer.update()
        self.assertEqual(status(core_checks.check_grid(ctx, ctx.scene.sets[0]), "CORE.GRID.SNAP"), "fail")

    def test_wrong_dimensions_fail_grid_dims(self):
        ctx = self.ctx(fx.piece_set(fx.wall(self.c, thickness_cells=0.3)))
        self.assertEqual(status(core_checks.check_grid(ctx, ctx.scene.sets[0]), "CORE.GRID.DIMS"), "fail")

    def test_seam_mismatch_fails_seam(self):
        ref = fx.piece_set(fx.wall(self.c))
        door = fx.piece_set(fx.wall(self.c, thickness_cells=0.3, name=api.piece_name(self.c, "doorway", "clean")),
                            piece="doorway")
        ctx = self.ctx(ref, door)
        self.assertEqual(status(core_checks.check_grid(ctx, ref), "CORE.GRID.SEAM"), "pass")
        self.assertEqual(status(core_checks.check_grid(ctx, door), "CORE.GRID.SEAM"), "fail")

    def test_non_manifold_fails_manifold(self):
        good = fx.piece_set(fx.wall(self.c))
        bad = fx.piece_set(fx.dress(self.c, fx.box("SM_SDW_wall_straight_cracked", (0, 0, 0), (2, 0.5, 4),
                                                    open_top=True)), variant="cracked")
        ctx = self.ctx(good, bad)
        self.assertEqual(status(core_checks.check_mesh(ctx, good), "CORE.MESH.MANIFOLD"), "pass")
        self.assertEqual(status(core_checks.check_mesh(ctx, bad), "CORE.MESH.MANIFOLD"), "fail")

    def test_flipped_face_fails_manifold(self):
        ps = fx.piece_set(flip_bottom(fx.wall(self.c)))
        ctx = self.ctx(ps)
        checks = core_checks.check_mesh(ctx, ps)
        self.assertGreater(checks[0].detail["signed_volume"], 0)
        self.assertGreater(checks[0].detail["flipped_edges"], 0)
        self.assertEqual(status(checks, "CORE.MESH.MANIFOLD"), "fail")

    def test_self_intersection_fails_selfx(self):
        bad = fx.piece_set(fx.two_overlapping_boxes("SM_SDW_wall_straight_clean"))
        ctx = self.ctx(bad)
        self.assertEqual(status(core_checks.check_mesh(ctx, bad), "CORE.MESH.SELFX"), "fail")

    def test_missing_lod_fails_chain(self):
        obj = fx.wall(self.c, cuts=4)
        ps = fx.piece_set(obj)
        ctx = self.ctx(ps)
        self.assertEqual(status(core_checks.check_lods(ctx, ps), "CORE.LOD.CHAIN"), "fail")
        tris = lod_mod.triangle_count(obj)
        ps.lods = [lod_mod.make_lod(obj, tris // 2, api.lod_name(self.c, obj.name, 1)),
                   lod_mod.make_lod(obj, tris // 5, api.lod_name(self.c, obj.name, 2))]
        self.assertEqual(status(core_checks.check_lods(ctx, ps), "CORE.LOD.CHAIN"), "pass")

    def test_over_budget_fails_budget(self):
        obj = fx.wall(self.c, cuts=12)
        tris = lod_mod.triangle_count(obj)
        self.assertGreater(tris, 900)
        ps = fx.piece_set(obj)
        ps.lods = [lod_mod.make_lod(obj, 400, api.lod_name(self.c, obj.name, 1)),
                   lod_mod.make_lod(obj, 150, api.lod_name(self.c, obj.name, 2))]
        ctx = self.ctx(ps)
        checks = core_checks.check_lods(ctx, ps)
        self.assertEqual(status(checks, "CORE.LOD.BUDGET"), "fail")
        self.assertEqual(status(checks, "CORE.LOD.CHAIN"), "pass")

    def test_bad_name_fails_naming(self):
        ps = fx.piece_set(fx.wall(self.c, name="Wall.001"))
        ctx = self.ctx(ps)
        self.assertEqual(status(core_checks.check_naming(ctx, ps), "CORE.NAMING"), "fail")

    def test_fix_applies_logged_transform_origin_and_rename(self):
        obj = fx.wall(self.c, name="wall_badly_named")
        obj.rotation_euler.z = math.pi / 2
        obj.scale = (1.0, 1.0, 2.0)
        ps = fx.piece_set(obj)
        ctx = self.ctx(ps)
        self.assertEqual(status(core_checks.check_transforms(ctx, ps), "CORE.XFORM"), "fail")
        records = fixes.apply(self.c, ps, core_checks.expected_names(ctx, ps))
        ids = sorted({r["id"] for r in records})
        self.assertEqual(ids, ["FIX.ORIGIN", "FIX.RENAME", "FIX.XFORM"])
        for r in records:
            self.assertIn("before", r)
            self.assertIn("after", r)
        self.assertEqual(status(core_checks.check_transforms(ctx, ps), "CORE.XFORM"), "pass")
        self.assertEqual(status(core_checks.check_naming(ctx, ps), "CORE.NAMING"), "pass")
        self.assertEqual(status(core_checks.check_pivot(ctx, ps), "CORE.PIVOT"), "pass")

    def test_uv_overlap_detected(self):
        a = ((0, 0), (1, 0), (0, 1))
        self.assertAlmostEqual(uv_mod.intersection_area(a, a), 0.5)
        self.assertEqual(uv_mod.intersection_area(a, ((1, 0), (1, 1), (0, 1))), 0.0)
        self.assertEqual(uv_mod.overlap_pairs([a, ((0.1, 0.1), (0.6, 0.1), (0.1, 0.6))]), 1)
        self.assertEqual(uv_mod.overlap_pairs([a, ((1, 0), (1, 1), (0, 1))]), 0)


class StlCheckFixtures(unittest.TestCase):
    def setUp(self):
        self.c = fx.fresh("stl_print")

    def test_non_manifold_fails_watertight(self):
        bad = fx.box("open", (0, 0, 0), (20, 20, 20), open_top=True)
        checks = stl_checks.check_watertight(bad)
        self.assertEqual(status(checks, "STL.WATERTIGHT"), "fail")
        self.assertEqual(status(checks, "STL.NONMANIFOLD"), "fail")
        good = fx.box("closed", (0, 0, 0), (20, 20, 20))
        self.assertEqual(status(stl_checks.check_watertight(good), "STL.WATERTIGHT"), "pass")
        self.assertEqual(status(stl_checks.check_watertight(good), "STL.NONMANIFOLD"), "pass")

    def test_flipped_face_fails_watertight(self):
        flipped = flip_bottom(fx.box("flipped", (0, 0, 0), (20, 20, 20)))
        self.assertEqual(status(stl_checks.check_watertight(flipped), "STL.WATERTIGHT"), "fail")

    def test_bowtie_vertex_fails_nonmanifold(self):
        checks = stl_checks.check_watertight(bowtie("bowtie"))
        self.assertEqual(status(checks, "STL.WATERTIGHT"), "pass")
        self.assertEqual(status(checks, "STL.NONMANIFOLD"), "fail")

    def test_thin_wall_fails_min_wall(self):
        thin = fx.box("thin", (0, 0, 0), (20, 20, 0.5))
        self.assertEqual(status(stl_checks.check_min_wall(thin, 1.2), "STL.WALL.MIN"), "fail")
        thick = fx.box("thick", (30, 0, 0), (50, 20, 5))
        self.assertEqual(status(stl_checks.check_min_wall(thick, 1.2), "STL.WALL.MIN"), "pass")

    def test_overhang_fails(self):
        self.assertEqual(status(stl_checks.check_overhang(fx.mushroom("mushroom"), self.c["print"]),
                                "STL.OVERHANG"), "fail")
        self.assertEqual(status(stl_checks.check_overhang(fx.box("block", (0, 0, 0), (20, 20, 20)),
                                                          self.c["print"]), "STL.OVERHANG"), "pass")

    def test_bridge_needs_support_on_two_sides(self):
        pr = self.c["print"]
        self.assertLessEqual(10, pr["max_bridge_mm"])
        gate = stl_checks.check_overhang(front_profile("gate", GATE), pr)[0]
        self.assertEqual(gate.status, "pass")
        self.assertEqual(gate.detail["bridge_spans_mm"], [10.0])
        ledge = stl_checks.check_overhang(front_profile("ledge", LEDGE), pr)[0]
        self.assertEqual(ledge.status, "fail")
        self.assertEqual(ledge.detail["bridged_mm2"], 0.0)
        self.assertAlmostEqual(ledge.detail["unsupported_mm2"], 200.0, places=3)
        self.assertEqual(stl_checks.check_overhang(front_profile("ledge2", LEDGE), {**pr, "presupport_required": True})
                         [0].status, "pass")

    def test_bbox_too_big_fails(self):
        big = fx.box("big", (0, 0, 0), (300, 20, 20))
        self.assertEqual(status(stl_checks.check_bbox(big, self.c["print"]), "STL.BBOX"), "fail")

    def test_missing_sockets_fail(self):
        base = fx.box("SM_SDW_wall_straight_clean_print", (0, 0, 0), (25.4, 25.4, 5.0))
        base["garu_print_base"] = [1, 1]
        self.assertEqual(status(stl_checks.check_sockets(base, self.c), "STL.SOCKET"), "fail")


class LegalCheckFixtures(unittest.TestCase):
    def setUp(self):
        self.c = fx.fresh("unity")

    def test_brand_named_object_fails(self):
        fx.wall(self.c)
        self.assertEqual(legal_checks.check_brand(self.c).status, "pass")
        fx.box("SM_SDW_ferrari_wall", (0, 0, 0), (1, 1, 1))
        result = legal_checks.check_brand(self.c)
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.id, "LEGAL.BRAND")

    def test_brand_tokenizer(self):
        scanner = legal_checks.BrandScanner()
        self.assertEqual(scanner.hits("McDonaldsSign"), ["mcdonalds"])
        self.assertEqual(scanner.hits("burger_king_crate"), ["burger king"])
        self.assertEqual(scanner.hits("BurgerKing"), ["burger king"])
        self.assertEqual(scanner.hits("fordable_bridge"), [])
        self.assertEqual(scanner.hits("for d, _, fs in os.walk(out)"), [])
        self.assertEqual(scanner.hits("CocaColaCrate"), ["coca cola", "cocacola"])
        self.assertEqual(scanner.hits("SM_SDW_wall_straight_clean"), [])

    def test_brand_in_material_fails(self):
        import bpy
        bpy.data.materials.new("GucciGold")
        self.assertEqual(legal_checks.check_brand(self.c).status, "fail")

    def test_external_image_fails_provenance(self):
        import bpy
        self.assertEqual(legal_checks.check_provenance(self.c).status, "pass")
        img = bpy.data.images.new("photo", 4, 4)
        img.filepath = "//textures/photo.png"
        self.assertEqual(legal_checks.check_provenance(self.c).status, "fail")


if __name__ == "__main__":
    unittest.main()
