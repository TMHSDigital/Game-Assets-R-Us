# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-kit print settings sheet (markdown), built from the contract and the
measured STL check results, so every number on the sheet was checked."""

import json
import os

from .print3d import expected_clip_dims
from .validators import metrics


def _measured(out_dir):
    rows = {}
    reports = os.path.join(out_dir, "reports")
    if not os.path.isdir(reports):
        return rows
    for name in sorted(os.listdir(reports)):
        if name in ("summary.json", "kit.json") or not name.endswith(".json"):
            continue
        with open(os.path.join(reports, name), encoding="utf-8") as fh:
            rep = json.load(fh)
        checks = {c["id"]: c for c in rep["checks"]}
        wall = checks.get("STL.WALL.MIN", {}).get("detail", {})
        over = checks.get("STL.OVERHANG", {}).get("detail", {})
        rows[rep["object"]] = {"min_wall_mm": wall.get("min_mm"), "bridged_mm2": over.get("bridged_mm2"),
                               "unsupported_mm2": over.get("unsupported_mm2")}
    return rows


def write_print_sheet(scene, out_dir, exp_dir):
    c = scene.contract
    pr = c["print"]
    clip = pr["clip_system"]
    measured = _measured(out_dir)
    lines = [
        f"# Print settings: {c['kit']['name']} {c['kit']['version']}",
        "",
        f"License: {c['legal']['license']}. Generated deterministically (seed {scene.seed}); no AI content.",
        "",
        "## Printer settings",
        "",
        "| Setting | Value |",
        "|---|---|",
        f"| Units | millimeters (1 grid cell = {c['profile']['cell_size']} mm) |",
        f"| Orientation | {pr['print_orientation']} (base flat on the plate, as exported) |",
        f"| Layer height | {pr.get('layer_height_mm', 0.2)} mm suggested |",
        f"| Supports | {'required' if pr['presupport_required'] else 'none needed'} |",
        f"| Minimum wall (checked) | {pr['min_wall_mm']} mm |",
        f"| Maximum overhang (checked) | {pr['max_overhang_deg']} deg; flat bridges up to {pr.get('max_bridge_mm', 0)} mm |",
        f"| Build volume (checked) | {' x '.join(str(v) for v in pr['max_bbox_mm'])} mm |",
        f"| Base height | {pr['base_height_mm']} mm |",
        "",
    ]
    if clip["type"] != "none":
        dims = expected_clip_dims(clip)
        lines += [
            "## Clip system: garu_dogbone_v1",
            "",
            "Each base has a T-shaped pocket under every perimeter cell edge. Two tiles side by side form a",
            "double-T slot; press one printed clip (`*_clip_dogbone.stl`) in from below.",
            "This is this project's own parametric design, not OpenLOCK or another standard.",
            "",
            "| Parameter | Value |",
            "|---|---|",
            f"| Fit tolerance per face | {clip['tolerance_mm']} mm |",
            f"| Pocket neck (w x l) | {clip['neck_width_mm']} x {clip['neck_length_mm']} mm |",
            f"| Pocket head (w x l) | {clip['head_width_mm']} x {clip['head_length_mm']} mm |",
            f"| Pocket height / roof | {clip['height_mm']} / {pr['base_height_mm'] - clip['height_mm']} mm |",
            f"| Clip size (l x w x h) | {' x '.join(f'{d:.2f}' for d in dims)} mm |",
            "",
            "Print a test pair first: if clips are too tight, scale the clip STL in X/Y by 98 to 99 percent.",
            "",
        ]
    lines += ["## Pieces", "", "| File | Size (mm) | Min wall (mm) | Bridged (mm2) |", "|---|---|---|---|"]
    for ps in scene.sets:
        lo, hi = metrics.bbox_world(ps.printable)
        size = " x ".join(f"{d:.1f}" for d in (hi - lo))
        m = measured.get(ps.name, {})
        wall = f"{m['min_wall_mm']:.2f}" if m.get("min_wall_mm") is not None else "n/a"
        bridged = f"{m['bridged_mm2']:.1f}" if m.get("bridged_mm2") is not None else "n/a"
        lines.append(f"| {ps.name}.stl | {size} | {wall} | {bridged} |")
    for clip_obj in scene.clips:
        lo, hi = metrics.bbox_world(clip_obj)
        lines.append(f"| {clip_obj.name}.stl | {' x '.join(f'{d:.1f}' for d in (hi - lo))} | n/a | n/a |")
    lines.append("")
    path = os.path.join(exp_dir, "print_settings.md")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    return path
