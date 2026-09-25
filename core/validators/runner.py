# SPDX-License-Identifier: GPL-3.0-or-later
"""Run every check on a generated KitScene and write JSON reports.

Output:
  <out>/reports/<piece_variant>.json   one report per piece variant
  <out>/reports/kit.json               kit-level checks (legal, clip)
  <out>/reports/summary.json           counts per check id, failures
"""

import os

import bpy

from . import core_checks, fixes, legal_checks, stl_checks
from .report import FAIL, PASS, SKIP, piece_report, write_json


def validate(scene, out_dir, fix=False, extra_meta=None):
    contract = scene.contract
    ctx = core_checks.Context(scene)
    meta_base = {
        "kit": contract["kit"]["id"],
        "kit_version": contract["kit"]["version"],
        "profile": contract["profile"]["name"],
        "seed": scene.seed,
        "blender": bpy.app.version_string,
        **(extra_meta or {}),
    }
    reports_dir = os.path.join(out_dir, "reports")
    all_fixes = {}
    if fix:
        for ps in scene.sets:
            all_fixes[ps.lod0.name] = fixes.apply(contract, ps, core_checks.expected_names(ctx, ps))
    core_checks.build_seam_refs(ctx)

    clip = scene.clips[0] if scene.clips else None
    summary = {"pieces": {}, "checks": {}, "failed_pieces": [], **meta_base}
    for ps in scene.sets:
        checks = []
        for fn in core_checks.ALL:
            checks.extend(fn(ctx, ps))
        if ps.printable is not None:
            checks.extend(stl_checks.run(ps.printable, contract, clip))
        rep = piece_report({**meta_base, "piece": ps.piece, "variant": ps.variant, "object": ps.lod0.name},
                           checks, all_fixes.get(ps.lod0.name, []))
        write_json(os.path.join(reports_dir, f"{ps.piece}_{ps.variant}.json"), rep)
        summary["pieces"][ps.lod0.name] = rep["passed"]
        if not rep["passed"]:
            summary["failed_pieces"].append(ps.lod0.name)
        for c in checks:
            counts = summary["checks"].setdefault(c.id, {PASS: 0, FAIL: 0, SKIP: 0})
            counts[c.status] += 1

    kit_checks = legal_checks.run(contract)
    if clip is not None:
        kit_checks.extend(stl_checks.run_clip(clip, contract))
    kit_rep = piece_report({**meta_base, "piece": "_kit", "variant": "", "object": ""}, kit_checks, [])
    write_json(os.path.join(reports_dir, "kit.json"), kit_rep)
    for c in kit_checks:
        counts = summary["checks"].setdefault(c.id, {PASS: 0, FAIL: 0, SKIP: 0})
        counts[c.status] += 1
    if not kit_rep["passed"]:
        summary["failed_pieces"].append("_kit")
    summary["passed"] = not summary["failed_pieces"]
    summary["notes"] = list(scene.notes)
    summary["fixes_applied"] = sum(len(v) for v in all_fixes.values())
    write_json(os.path.join(reports_dir, "summary.json"), summary)

    for cid, counts in sorted(summary["checks"].items()):
        print(f"CHECK {cid:22s} pass={counts[PASS]:3d} fail={counts[FAIL]:3d} skip={counts[SKIP]:3d}")
    for name in summary["failed_pieces"]:
        print(f"FAILED {name}")
    return summary
