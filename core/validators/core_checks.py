# SPDX-License-Identifier: GPL-3.0-or-later
"""Core checks: grid, pivot, transforms, naming, manifold, UVs, texel
density, LODs, colliders and material slots.

All distances are in profile units (the scene is scaled before validation);
the grid tolerance is snap_tolerance_cells * cell_size.
"""

import math
import re

from ..generators import api
from ..geometry import lod as lod_mod
from ..geometry import uv as uv_mod
from . import metrics
from .report import fail, ok, skip, verdict

SAFE_NAME = re.compile(r"^[A-Za-z0-9_\-]+$")


class Context:
    def __init__(self, scene):
        self.scene = scene
        self.contract = scene.contract
        self.profile = scene.contract["profile"]
        self.cell = self.profile["cell_size"]
        self.tol = scene.contract["grid"]["snap_tolerance_cells"] * self.cell
        self.pieces = api.pieces_by_id(self.contract)
        self.seam_refs = {}

    @property
    def is_mesh(self):
        return self.profile["kind"] == "mesh"


# ---------------------------------------------------------------- grid ----

def seam_points(ctx, obj, piece, seam):
    axis = 0 if seam[0] == "x" else 1
    other = 1 - axis
    value = 0.0 if seam[1] == "0" else piece["footprint_cells"][axis] * ctx.cell
    pts = [(v.co[other], v.co.z) for v in obj.data.vertices if abs(v.co[axis] - value) <= ctx.tol]
    return sorted(set((round(a, 6), round(b, 6)) for a, b in pts))


def build_seam_refs(ctx):
    """Reference seam profile per group: the first piece (contract order)
    using the group, its first variant, its first seam."""
    by_key = {(ps.piece, ps.variant): ps for ps in ctx.scene.sets}
    first_variant = ctx.contract["style"]["variants"][0]
    for piece in ctx.contract["pieces"]:
        group = piece.get("seam_profile")
        if not group or group in ctx.seam_refs or not piece.get("seams"):
            continue
        ps = by_key.get((piece["id"], first_variant))
        if ps is not None:
            seam = piece["seams"][0]
            ctx.seam_refs[group] = (f"{ps.name}:{seam}", seam_points(ctx, ps.lod0, piece, seam))


def _hausdorff(a, b):
    def one(p, qs):
        return min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in qs)
    if not a or not b:
        return math.inf
    return max(max(one(p, b) for p in a), max(one(q, a) for q in b))


def check_grid(ctx, ps):
    piece = ctx.pieces[ps.piece]
    obj = ps.lod0
    out = []
    loc = obj.matrix_world.translation
    off = [abs(c / ctx.cell - round(c / ctx.cell)) * ctx.cell for c in loc]
    out.append(verdict("CORE.GRID.SNAP", max(off) <= ctx.tol,
                       f"object origin must sit on the {ctx.cell} {ctx.profile['units']} grid",
                       location=list(loc), max_offset=max(off), tolerance=ctx.tol))

    lo, hi = metrics.bbox_local(obj)
    dims = hi - lo
    fx, fy = (v * ctx.cell for v in piece["footprint_cells"])
    h = piece["height_cells"] * ctx.cell
    first_variant = ctx.contract["style"]["variants"][0]
    errs = {"x": dims.x - fx, "y": dims.y - fy}
    z_ok = dims.z <= h + ctx.tol
    if ps.variant == first_variant:
        errs["z"] = dims.z - h
        z_ok = abs(errs["z"]) <= ctx.tol
    xy_ok = all(abs(v) <= ctx.tol for k, v in errs.items() if k != "z")
    out.append(verdict("CORE.GRID.DIMS", xy_ok and z_ok,
                       "footprint must match exactly; height must match (first variant) or not exceed",
                       dims=list(dims), expected=[fx, fy, h], errors=errs, tolerance=ctx.tol))

    seams = piece.get("seams", [])
    group = piece.get("seam_profile")
    if not seams:
        out.append(skip("CORE.GRID.SEAM", "piece declares no seams"))
    elif group not in ctx.seam_refs:
        out.append(fail("CORE.GRID.SEAM", f"no reference profile for seam group '{group}'"))
    else:
        ref_name, ref = ctx.seam_refs[group]
        devs = {s: _hausdorff(seam_points(ctx, obj, piece, s), ref) for s in seams}
        worst = max(devs.values())
        out.append(verdict("CORE.GRID.SEAM", worst <= ctx.tol,
                           f"seam profiles must match reference {ref_name}",
                           deviations=devs, tolerance=ctx.tol, reference_points=len(ref)))
    return out


def check_pivot(ctx, ps):
    lo, hi = metrics.bbox_local(ps.lod0)
    rule = ctx.contract["style"]["pivot_rule"]
    if rule == "base_min_corner":
        err = max(abs(lo.x), abs(lo.y), abs(lo.z))
    else:
        err = max(abs((lo.x + hi.x) / 2), abs((lo.y + hi.y) / 2), abs(lo.z))
    return [verdict("CORE.PIVOT", err <= ctx.tol, f"origin must follow pivot rule '{rule}'",
                    bbox_min=list(lo), bbox_max=list(hi), error=err, tolerance=ctx.tol)]


def check_transforms(ctx, ps):
    out = []
    for obj in ps.mesh_objects() + ps.colliders:
        err = metrics.basis_error(obj)
        if err > metrics.XFORM_EPS:
            out.append(fail("CORE.XFORM", f"{obj.name}: rotation and scale (including deltas) must be applied",
                            basis_error=err, **metrics.xform_state(obj)))
    return out or [ok("CORE.XFORM", "rotation and scale applied on all objects")]


def expected_names(ctx, ps):
    base = api.piece_name(ctx.contract, ps.piece, ps.variant)
    names = {"lod0": base}
    lods = len(ctx.pieces[ps.piece]["lod_tris"]) if ctx.is_mesh and ctx.profile.get("lod_mode") != "omit" else 1
    for n in range(1, lods):
        names[f"lod{n}"] = api.lod_name(ctx.contract, base, n)
    for i in range(len(ps.colliders)):
        names[f"collider{i}"] = api.collider_name(ctx.contract, base, i)
    return names


def check_naming(ctx, ps):
    want = expected_names(ctx, ps)
    have = {"lod0": ps.lod0.name}
    have.update({f"lod{i + 1}": o.name for i, o in enumerate(ps.lods)})
    have.update({f"collider{i}": o.name for i, o in enumerate(ps.colliders)})
    bad = {k: {"expected": want.get(k), "actual": v} for k, v in have.items() if want.get(k) != v}
    unsafe = [v for v in have.values() if not SAFE_NAME.match(v)]
    return [verdict("CORE.NAMING", not bad and not unsafe,
                    "names must follow the contract naming, LOD and collider patterns",
                    mismatches=bad, unsafe=unsafe)]


# ---------------------------------------------------------------- mesh ----

def check_mesh(ctx, ps):
    h = metrics.hygiene(ps.lod0)
    manifold = (h["non_manifold_edges"] == 0 and h["boundary_edges"] == 0 and h["non_manifold_verts"] == 0
                and h["flipped_edges"] == 0 and h["signed_volume"] > 0)
    return [
        verdict("CORE.MESH.MANIFOLD", manifold,
                "LOD0 must be closed and manifold with consistent, outward normals", **h),
        verdict("CORE.MESH.LOOSE", h["loose_verts"] == 0 and h["loose_edges"] == 0 and h["zero_area_faces"] == 0,
                "no loose vertices, loose edges or zero-area faces",
                loose_verts=h["loose_verts"], loose_edges=h["loose_edges"], zero_area_faces=h["zero_area_faces"]),
        verdict("CORE.MESH.SELFX", h["self_intersections"] == 0,
                "no faces intersect other faces", self_intersections=h["self_intersections"]),
    ]


def check_uv(ctx, ps):
    if not ctx.is_mesh:
        return [skip("CORE.UV.PRESENT", "UV channels are not used by print profiles"),
                skip("CORE.UV.OVERLAP", "UV channels are not used by print profiles"),
                skip("CORE.UV.TEXEL", "texel density does not apply to print profiles")]
    uvc = ctx.contract["uv"]
    tiling, light = uvc["tiling_channel"], uvc["lightmap_channel"]
    out = []
    missing = {o.name: [c for c in (tiling, light) if o.data.uv_layers.get(c) is None]
               for o in ps.mesh_objects()}
    missing = {k: v for k, v in missing.items() if v}
    out.append(verdict("CORE.UV.PRESENT", not missing, f"UV channels '{tiling}' and '{light}' on every LOD",
                       missing=missing))
    if missing:
        out.append(skip("CORE.UV.OVERLAP", "UV channels missing"))
        out.append(skip("CORE.UV.TEXEL", "UV channels missing"))
        return out
    overlaps = {o.name: uv_mod.overlap_pairs(uv_mod.uv_triangles(o.data, light)) for o in ps.mesh_objects()}
    out.append(verdict("CORE.UV.OVERLAP", all(v == 0 for v in overlaps.values()),
                       f"lightmap channel '{light}' must not overlap (tiling channel overlaps by design)",
                       overlapping_pairs=overlaps))
    out.append(_texel(ctx, ps.lod0, tiling))
    return out


def _texel(ctx, obj, channel):
    td = ctx.contract["texel_density"]
    mesh = obj.data
    layer = mesh.uv_layers[channel]
    inside = total = 0.0
    lo_d, hi_d = math.inf, 0.0
    for poly in mesh.polygons:
        area_cells = poly.area / (ctx.cell ** 2)
        if area_cells < 1e-8:
            continue
        uvs = [layer.data[li].uv for li in poly.loop_indices]
        uv_area = abs(sum(uvs[i].x * uvs[i - 1].y - uvs[i - 1].x * uvs[i].y for i in range(len(uvs)))) / 2
        density = td["texture_size"] * math.sqrt(uv_area / area_cells)
        total += area_cells
        lo_d, hi_d = min(lo_d, density), max(hi_d, density)
        if td["min_px_per_cell"] <= density <= td["max_px_per_cell"]:
            inside += area_cells
    coverage = inside / total if total else 0.0
    return verdict("CORE.UV.TEXEL", coverage >= td["coverage"],
                   f"at least {td['coverage']:.0%} of surface area within "
                   f"{td['min_px_per_cell']}-{td['max_px_per_cell']} px per cell",
                   coverage=coverage, min_px_per_cell=lo_d, max_px_per_cell=hi_d)


# ----------------------------------------------------------------- LOD ----

def check_lods(ctx, ps):
    if not ctx.is_mesh:
        return [skip("CORE.LOD.CHAIN", "LODs are not used by print profiles"),
                skip("CORE.LOD.BUDGET", "LODs are not used by print profiles")]
    budgets = ctx.pieces[ps.piece]["lod_tris"]
    if ctx.profile.get("lod_mode") == "omit":
        tris = lod_mod.triangle_count(ps.lod0)
        return [skip("CORE.LOD.CHAIN", f"profile '{ctx.profile['name']}' omits LODs (engine builds its own)"),
                verdict("CORE.LOD.BUDGET", tris <= budgets[0], "LOD0 within its triangle budget",
                        tris=[tris], budgets=[budgets[0]])]
    chain = ps.mesh_objects()
    tris = [lod_mod.triangle_count(o) for o in chain]
    complete = len(chain) == len(budgets)
    decreasing = all(b < a for a, b in zip(tris, tris[1:]))
    over = {f"LOD{i}": {"tris": t, "budget": b} for i, (t, b) in enumerate(zip(tris, budgets)) if t > b}
    return [
        verdict("CORE.LOD.CHAIN", complete and decreasing,
                f"{len(budgets)} LODs present with strictly decreasing triangle counts",
                expected_lods=len(budgets), present_lods=len(chain), tris=tris),
        verdict("CORE.LOD.BUDGET", not over and complete, "every LOD within its triangle budget",
                tris=tris, budgets=list(budgets), over_budget=over),
    ]


# ------------------------------------------------------------ collider ----

def check_colliders(ctx, ps):
    col = ctx.contract["collider"]
    if not ctx.is_mesh:
        return [skip("CORE.COLLIDER", "colliders are not used by print profiles")]
    if col["type"] == "none":
        return [skip("CORE.COLLIDER", "contract collider type is none")]
    if ctx.profile.get("collider_mode") == "omit":
        return [skip("CORE.COLLIDER", f"profile '{ctx.profile['name']}' omits collision meshes")]
    if not ps.colliders:
        return [fail("CORE.COLLIDER", "no collider parts present")]
    parts = {}
    good = len(ps.colliders) <= col["max_parts"]
    for obj in ps.colliders:
        h = metrics.hygiene(obj)
        convex, worst = metrics.is_convex(obj, ctx.tol)
        faces = len(obj.data.polygons)
        # A closed solid needs at least a tetrahedron's 4 faces and a positive
        # volume; an empty or flat part would pass the other tests vacuously.
        closed = (faces >= 4 and h["signed_volume"] > 0 and h["boundary_edges"] == 0
                  and h["non_manifold_edges"] == 0 and h["flipped_edges"] == 0)
        part_ok = closed and convex and faces <= col["max_faces_per_part"]
        good = good and part_ok
        parts[obj.name] = {"faces": faces, "convex": convex, "convexity_error": worst,
                           "closed": closed, "volume": h["signed_volume"], "boundary_edges": h["boundary_edges"],
                           "non_manifold_edges": h["non_manifold_edges"], "flipped_edges": h["flipped_edges"]}
    return [verdict("CORE.COLLIDER", good,
                    f"1..{col['max_parts']} closed convex parts with volume, "
                    f"each 4..{col['max_faces_per_part']} faces",
                    parts=parts, count=len(ps.colliders))]


# ------------------------------------------------------------ material ----

def check_materials(ctx, ps):
    allowed = {api.material_name(ctx.contract, p["slot"]) for p in ctx.contract["materials"]["palette"]}
    limit = ctx.contract["materials"]["max_slots_per_piece"]
    problems = {}
    for obj in ps.mesh_objects():
        slots = [m.name if m else None for m in obj.data.materials]
        bad_idx = sorted({p.material_index for p in obj.data.polygons if p.material_index >= len(slots)})
        issues = []
        if len(slots) > limit:
            issues.append(f"{len(slots)} slots > {limit}")
        if any(s not in allowed for s in slots):
            issues.append(f"non-palette or empty slots {[s for s in slots if s not in allowed]}")
        if bad_idx:
            issues.append(f"faces use missing slot indices {bad_idx}")
        if issues:
            problems[obj.name] = issues
    return [verdict("CORE.MATERIAL.SLOTS", not problems,
                    f"at most {limit} slots, palette materials only", problems=problems)]


ALL = [check_grid, check_pivot, check_transforms, check_naming, check_mesh,
       check_uv, check_lods, check_colliders, check_materials]
