# SPDX-License-Identifier: GPL-3.0-or-later
"""STL print checks, run on each printable tile (and the clip).

STL.WATERTIGHT    no boundary edges, consistent winding, positive signed volume
STL.NONMANIFOLD   non-manifold edge and vertex counts are zero
STL.SELFX         no self-intersecting faces
STL.WALL.MIN      minimum wall thickness by BVH ray sampling
STL.OVERHANG      overhang angle histogram against max_overhang_deg; flat
                  bridges must be held on two opposite sides
STL.BBOX          fits the build plate and sits on it (min z = 0)
STL.SOCKET        socket pockets are open, surrounded by material, and the
                  clip is exactly the pocket shrunk by the tolerance
"""

from mathutils import Vector

from ..print3d import expected_clip_dims, socket_frames
from . import metrics
from .report import skip, verdict

OVERHANG_TOL_DEG = 0.5   # exact 45 degree chamfers count as 45
BRIDGE_MIN_DEG = 80.0    # only near-horizontal ceilings can be bridges
PLATE_EPS = 1e-3


def check_watertight(obj):
    h = metrics.hygiene(obj)
    return [
        verdict("STL.WATERTIGHT", h["boundary_edges"] == 0 and h["flipped_edges"] == 0 and h["signed_volume"] > 0,
                "closed surface with consistent, outward normals", boundary_edges=h["boundary_edges"],
                flipped_edges=h["flipped_edges"], signed_volume_mm3=h["signed_volume"], shells=h["shells"]),
        verdict("STL.NONMANIFOLD", h["non_manifold_edges"] == 0 and h["non_manifold_verts"] == 0
                and h["loose_verts"] == 0,
                "non-manifold edge and vertex counts must be zero", non_manifold_edges=h["non_manifold_edges"],
                non_manifold_verts=h["non_manifold_verts"], loose_verts=h["loose_verts"]),
        verdict("STL.SELFX", h["self_intersections"] == 0,
                "no self-intersecting faces", self_intersections=h["self_intersections"]),
    ]


OPPOSED = -0.5  # a wall is two surfaces facing away from each other (within 60 deg)


def check_min_wall(obj, min_wall):
    """One inward ray per triangle centroid along -normal. A sample is a thin
    wall when the ray reaches an opposed surface (normals facing apart)
    closer than min_wall. Rays that exit through an adjacent face at a
    convex corner (hit normal roughly perpendicular) measure corner geometry,
    not wall thickness, and are reported separately as corner_exits."""
    solid = metrics.Solid(obj)
    try:
        samples = metrics.triangle_samples(obj)
        thick, misses, thin, corner = [], 0, [], 0
        for centroid, n, _area, _tri in samples:
            d, hit_n = solid.thickness(centroid, n)
            if d is None:
                misses += 1
                continue
            if n.dot(hit_n) > OPPOSED:
                corner += 1
                continue
            thick.append(d)
            if d < min_wall:
                thin.append([round(c, 3) for c in centroid] + [round(d, 4)])
    finally:
        solid.free()
    thick.sort()
    pct = (lambda q: thick[min(len(thick) - 1, int(q * len(thick)))]) if thick else (lambda q: None)
    return [verdict("STL.WALL.MIN", not thin and misses == 0 and bool(thick),
                    f"every sampled wall must be at least {min_wall} mm thick",
                    samples=len(samples), ray_misses=misses, corner_exits=corner,
                    min_mm=thick[0] if thick else None, p01_mm=pct(0.01), median_mm=pct(0.5),
                    thin_samples=len(thin), thin_examples=thin[:10])]


def _key(p):
    return tuple(round(x, 5) for x in p)


def _edges(pts):
    keys = [_key(p) for p in pts]
    return [tuple(sorted((keys[a], keys[b]))) for a, b in ((0, 1), (1, 2), (2, 0))]


def _regions(tris):
    """Group triangles that share an edge (by rounded vertex positions)."""
    parent = list(range(len(tris)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner = {}
    for i, (_c, _n, _a, pts) in enumerate(tris):
        for edge in _edges(pts):
            if edge in owner:
                parent[find(i)] = find(owner[edge])
            else:
                owner[edge] = i
    groups = {}
    for i in range(len(tris)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _supported_edges(region, edge_tris):
    """Boundary edges of a region (lists of (tri id, sample)) that sit on
    material below: the neighbouring face across the edge goes down from
    it, like a door jamb under a lintel. The free edge of a ledge borders a
    face that goes up instead."""
    ids = {i for i, _t in region}
    count = {}
    for _i, t in region:
        for edge in _edges(t[3]):
            count[edge] = count.get(edge, 0) + 1
    out = []
    for edge, n in count.items():
        if n != 1:
            continue
        z = min(edge[0][2], edge[1][2])
        for j, other in edge_tris.get(edge, ()):
            if j not in ids and any(_key(p) not in edge and p.z < z - PLATE_EPS for p in other[3]):
                out.append(edge)
                break
    return out


def _bridge_span(pts, supported):
    """Shortest distance a region spans between supports on two opposite
    sides (along x or y), or None if it is not held on two opposite sides."""
    def held_at(axis, v):
        return any(abs(a[axis] - v) <= PLATE_EPS and abs(b[axis] - v) <= PLATE_EPS for a, b in supported)

    spans = []
    for axis in (0, 1):
        lo, hi = min(p[axis] for p in pts), max(p[axis] for p in pts)
        if held_at(axis, lo) and held_at(axis, hi):
            spans.append(hi - lo)
    return min(spans) if spans else None


def check_overhang(obj, pr):
    """Downward faces steeper than max_overhang_deg are unsupported unless
    they form a flat bridge: a near-horizontal region held by material on two
    opposite sides no further apart than max_bridge_mm. A one-sided ledge
    (cantilever) is never a bridge. Unsupported area up to
    max_overhang_area_mm2 is tolerated. With presupport_required the check
    only reports, since the slicer adds supports anyway."""
    limit = pr["max_overhang_deg"]
    bridge = pr.get("max_bridge_mm", 0.0)
    area_cap = pr.get("max_overhang_area_mm2", 0.0)
    hist = {}
    steep = []
    edge_tris = {}
    for i, sample in enumerate(metrics.triangle_samples(obj)):
        centroid, n, area, pts = sample
        for edge in _edges(pts):
            edge_tris.setdefault(edge, []).append((i, sample))
        if n.z >= 0:
            continue
        if all(p.z < PLATE_EPS for p in pts):
            continue  # on the build plate
        ang = metrics.angle_below_horizontal(n)
        b = min(85, int(ang // 5) * 5)
        hist[f"{b:02d}-{b + 5:02d}"] = hist.get(f"{b:02d}-{b + 5:02d}", 0.0) + area
        if ang > limit + OVERHANG_TOL_DEG:
            steep.append((i, sample))
    bridged = unsupported = 0.0
    bridges = []
    for group in _regions([t for _i, t in steep]):
        region = [steep[k] for k in group]
        tris = [t for _i, t in region]
        area = sum(t[2] for t in tris)
        flat = all(metrics.angle_below_horizontal(t[1]) >= BRIDGE_MIN_DEG for t in tris)
        span = _bridge_span([p for t in tris for p in t[3]], _supported_edges(region, edge_tris)) if flat else None
        if span is not None and span <= bridge:
            bridged += area
            bridges.append(round(span, 3))
        else:
            unsupported += area
    presupport = pr.get("presupport_required", False)
    passed = unsupported <= area_cap + 1e-9 or presupport
    return [verdict("STL.OVERHANG", passed,
                    f"downward faces steeper than {limit} deg only as bridges <= {bridge} mm "
                    f"held on two opposite sides, or <= {area_cap} mm2 in total"
                    + (" (report only: presupport_required)" if presupport else ""),
                    histogram_mm2=dict(sorted(hist.items())), steep_area_mm2=bridged + unsupported,
                    bridged_mm2=bridged, bridge_spans_mm=sorted(bridges), unsupported_mm2=unsupported)]


def check_bbox(obj, pr):
    lo, hi = metrics.bbox_world(obj)
    dims = hi - lo
    plate = pr["max_bbox_mm"]
    fits = all(d <= m for d, m in zip(dims, plate))
    return [verdict("STL.BBOX", fits and abs(lo.z) <= PLATE_EPS,
                    f"fits the {plate} mm build volume and rests on z = 0",
                    dims_mm=list(dims), min_z=lo.z)]


def check_sockets(obj, contract, clip_obj=None):
    pr = contract["print"]
    clip = pr["clip_system"]
    if clip["type"] == "none":
        return [skip("STL.SOCKET", "clip_system is none")]
    tx, ty = obj.get("garu_print_base", [1, 1])
    cell = contract["profile"]["cell_size"]
    h = clip["height_mm"]
    base_h = pr["base_height_mm"]
    nl, hl = clip["neck_length_mm"], clip["head_length_mm"]
    hw, nw = clip["head_width_mm"] / 2, clip["neck_width_mm"] / 2
    roof = base_h - h
    problems = []
    solid = metrics.Solid(obj)
    try:
        frames = socket_frames(tx, ty, cell)
        for k, (origin, u, w) in enumerate(frames):
            def at(a, b, z):
                p = origin + u * a + w * b
                return Vector((p.x, p.y, z))
            probes_open = {"neck": at(0, nl / 2, h / 2), "head": at(0, nl + hl / 2, h / 2),
                           "head_corner": at(hw - 0.3, nl + hl - 0.3, h - 0.3)}
            probes_solid = {"head_side": at(hw + 0.5, nl + hl / 2, h / 2),
                            "head_back": at(0, nl + hl + 0.5, h / 2),
                            "neck_side": at(nw + 0.5, nl / 2, h / 2),
                            "roof": at(0, nl + hl / 2, h + roof / 2)}
            for name, p in probes_open.items():
                if solid.inside(p):
                    problems.append(f"socket {k}: {name} probe is filled")
            for name, p in probes_solid.items():
                if not solid.inside(p):
                    problems.append(f"socket {k}: {name} probe is empty")
    finally:
        solid.free()
    detail = {"sockets": len(frames), "roof_mm": roof, "tolerance_mm": clip["tolerance_mm"]}
    if roof < pr["min_wall_mm"]:
        problems.append(f"roof above pocket {roof} mm < min_wall_mm {pr['min_wall_mm']}")
    if clip_obj is not None:
        lo, hi = metrics.bbox_world(clip_obj)
        dims = list(hi - lo)
        want = expected_clip_dims(clip)
        detail["clip_dims_mm"], detail["clip_expected_mm"] = dims, list(want)
        if any(abs(a - b) > 1e-4 for a, b in zip(dims, want)):
            problems.append(f"clip dims {dims} != expected {want}")
    return [verdict("STL.SOCKET", not problems, "pockets open, walled and roofed; clip = pocket minus tolerance",
                    problems=problems[:20], **detail)]


def run(obj, contract, clip_obj=None):
    pr = contract["print"]
    return (check_watertight(obj) + check_min_wall(obj, pr["min_wall_mm"])
            + check_overhang(obj, pr) + check_bbox(obj, pr) + check_sockets(obj, contract, clip_obj))


def run_clip(obj, contract):
    pr = contract["print"]
    return check_watertight(obj) + check_min_wall(obj, pr["min_wall_mm"]) + check_bbox(obj, pr)

