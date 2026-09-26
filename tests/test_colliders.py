# SPDX-License-Identifier: GPL-3.0-or-later
"""Sampler kit colliders: no collision above the visible geometry, in
particular above the broken top of ruined pieces."""

import unittest

from mathutils import Vector

from core import pipeline
from core.contract import load_contract, resolve
from core.generators import get, load_module
from core.validators import metrics

KIT = "stone-dungeon-wall-sampler"
PIECES = ["wall_straight", "doorway", "corner_outer"]


def _top(obj, x, y, z_above):
    hit, loc, _n, _i = obj.ray_cast(Vector((x, y, z_above)), Vector((0.0, 0.0, -1.0)))
    return loc.z if hit else None


class RuinedColliders(unittest.TestCase):
    def test_collider_tops_stay_under_geometry(self):
        info = get(KIT)
        contract = resolve(load_contract(info.contract_path), "unity")
        module = load_module(info)
        cell = contract["profile"]["cell_size"]
        t = contract["grid"]["wall_thickness_cells"]
        # Clean boxes cover the chamfers too; allow that much and no more.
        slack = (contract["style"]["bevel_width_cells"] + 1e-3) * cell
        col = contract["collider"]
        for seed in (1, 7, 42, 1337):
            scene = pipeline.generate(contract, module, seed, PIECES)
            for ps in scene.sets:
                self.assertLessEqual(len(ps.colliders), col["max_parts"], ps.name)
                for part in ps.colliders:
                    self.assertLessEqual(len(part.data.polygons), col["max_faces_per_part"], part.name)
                    self.assertTrue(metrics.is_convex(part, 1e-4)[0], part.name)
                fx, fy = [c * cell for c in contract["pieces"][[p["id"] for p in contract["pieces"]]
                                                               .index(ps.piece)]["footprint_cells"]]
                # Sample the middle of the wall thickness, away from mortar
                # grooves on the faces.
                pts = [(fx * i / 40, t * cell / 2) for i in range(1, 40)]
                if ps.piece == "corner_outer":
                    pts += [(t * cell / 2, fy * i / 40) for i in range(1, 40)]
                z_above = 10.0 * cell
                for x, y in pts:
                    geo = _top(ps.lod0, x, y, z_above)
                    for part in ps.colliders:
                        z = _top(part, x, y, z_above)
                        if z is None:
                            continue
                        with self.subTest(seed=seed, piece=ps.name, part=part.name, x=round(x, 3)):
                            self.assertIsNotNone(geo)
                            self.assertLessEqual(z, geo + slack)


if __name__ == "__main__":
    unittest.main()
