# SPDX-License-Identifier: GPL-3.0-or-later
"""Stone Dungeon Wall Sampler generator (public reference generator).

Pieces: wall_straight, corner_outer, doorway, floor_2x2, pillar.
Variants: clean, cracked, ruined.

Construction rules that keep every piece grid-exact and watertight:
- each piece is ONE extruded profile or loft, so it is closed and manifold
  by construction, with no booleans;
- one chamfer width (style.bevel_width_cells) on every hard edge except the
  floor-contact edges at z = 0;
- stone courses are cut on a GLOBAL grid (course height, block length,
  alternating half-block offset per course), so the pattern lines up across
  neighbouring pieces;
- mortar joints are an inset of every stone plus a groove pushed inward, so
  stone faces stay on the original bounding planes and the bounding box is
  exact;
- cracked and ruined edits never touch seam planes (piece ends), so every
  variant of a piece snaps to every other.

Generated meshes are CC0-1.0 (see assets/LICENSE-CC0). This code is
GPL-3.0-or-later.
"""

import math

import bmesh
import bpy
from mathutils import Vector

from core.generators import api
from core.geometry import prims

EPS = 1e-6
STONE, MORTAR = 0, 1
MIN_STONE_AREA = 0.15      # cells^2: smaller faces are left plain
SLIVER = 0.08              # cells: no joint cut this close to a face edge
RUIN_END_MARGIN = 0.2      # cells: ruin edits stay this far from seams


# --------------------------------------------------------------------------
# Profiles
# --------------------------------------------------------------------------

MAX_RUIN_SLOPE = 1.2  # rise per run: about 50 deg, so no peak is sharper than 80 deg


def _jagged_top(rng, x_hi, x_lo, z_top, z_min, z_max, steps=4):
    """Broken top edge from x_hi down to x_lo (profile traversed right to
    left). Every segment is at most MAX_RUIN_SLOPE steep, so the silhouette
    has no knife-edge spikes a printer could not reproduce."""
    dx = (x_hi - x_lo) / (steps + 1)
    pts = [(x_hi, z_top)]
    z = z_top
    for i in range(1, steps + 1):
        remaining = (steps + 1 - i) * dx
        lo = max(z_min, z - MAX_RUIN_SLOPE * dx, z_top - MAX_RUIN_SLOPE * remaining)
        hi = min(z_max, z + MAX_RUIN_SLOPE * dx)
        z = rng.uniform(lo, max(lo, hi))
        pts.append((x_hi - i * dx, z))
    return pts + [(x_lo, z_top)]


def wall_profile(length, height, rng, ruined):
    top = [(length, height), (0.0, height)]
    if ruined:
        m = RUIN_END_MARGIN
        top = [(length, height)] + _jagged_top(rng, length - m, m, height,
                                               height - 1.0, height - 0.35) + [(0.0, height)]
    return [(0.0, 0.0), (length, 0.0)] + top


def doorway_profile(length, height, rng, ruined, door=(0.25, 0.75, 1.25)):
    x0, x1, dh = door
    base = [(0.0, 0.0), (x0, 0.0), (x0, dh), (x1, dh), (x1, 0.0), (length, 0.0)]
    top = [(length, height), (0.0, height)]
    if ruined:
        m = RUIN_END_MARGIN
        top = [(length, height)] + _jagged_top(rng, length - m, m, height,
                                               dh + 0.3, height - 0.15) + [(0.0, height)]
    return base + top


# --------------------------------------------------------------------------
# bmesh helpers
# --------------------------------------------------------------------------

def _plane_faces(bm, normal, point):
    # Faces created by bevel, bisect and inset do not get fresh normals until
    # normal_update(); reading stale normals makes face selection depend on
    # memory contents and breaks determinism.
    bm.normal_update()
    out = []
    for f in bm.faces:
        if f.normal.dot(normal) < 0.999:
            continue
        if all(abs((v.co - point).dot(normal)) < 1e-5 for v in f.verts):
            out.append(f)
    return out


def _geom(faces):
    # dict.fromkeys, not set: set order follows memory addresses, which would
    # make bmesh operator output order (and so export bytes) vary per run.
    verts = dict.fromkeys(v for f in faces for v in f.verts)
    edges = dict.fromkeys(e for f in faces for e in f.edges)
    return list(verts) + list(edges) + list(faces)


def _cut(bm, faces, co, no):
    if faces:
        bmesh.ops.bisect_plane(bm, geom=_geom(faces), dist=1e-7,
                               plane_co=co, plane_no=no)


def _ruin_cut(bm, co, no):
    """Remove everything above a plane (on the +no side) and cap the hole."""
    res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                 dist=1e-7, plane_co=co, plane_no=no, clear_outer=True)
    cut_edges = [g for g in res["geom_cut"] if isinstance(g, bmesh.types.BMEdge)]
    bmesh.ops.holes_fill(bm, edges=cut_edges, sides=0)
    prims.recalc_normals(bm)


def _is_convex(face, eps=1e-9):
    n = face.normal
    loops = face.loops
    for i, loop in enumerate(loops):
        a = loops[i - 1].vert.co
        b = loop.vert.co
        c = loops[(i + 1) % len(loops)].vert.co
        if (b - a).cross(c - b).dot(n) < -eps:
            return False
    return True


def _inradius(face):
    """Distance from the face centroid to its nearest edge (a lower bound
    proxy for how far the face can be inset without inverting)."""
    c = face.calc_center_median()
    best = float("inf")
    for e in face.edges:
        a, b = e.verts[0].co, e.verts[1].co
        ab = b - a
        t = max(0.0, min(1.0, (c - a).dot(ab) / max(ab.length_squared, 1e-18)))
        best = min(best, (a + ab * t - c).length)
    return best


def _on_seam(face, piece):
    fx, fy = piece["footprint_cells"]
    planes = {"x0": (0, 0.0), "x1": (0, fx), "y0": (1, 0.0), "y1": (1, fy)}
    for seam in piece.get("seams", []):
        axis, value = planes[seam]
        if all(abs(v.co[axis] - value) < EPS for v in face.verts):
            return True
    return False


# --------------------------------------------------------------------------
# Masonry
# --------------------------------------------------------------------------

def stoneify(bm, piece, style, horizontal_top=None):
    """Cut large faces into staggered stones with recessed mortar joints.
    Returns the list of stone faces."""
    course = style["course_height_cells"]
    block = style["block_length_cells"]
    gap = style["mortar_gap_cells"]
    depth = style["mortar_depth_cells"]

    bm.normal_update()
    targets = []
    for f in bm.faces:
        n = f.normal
        if f.calc_area() < MIN_STONE_AREA or _on_seam(f, piece):
            continue
        if abs(n.z) < 1e-4:
            targets.append((Vector((round(n.x, 6), round(n.y, 6), 0.0)).normalized(), f.verts[0].co.copy()))
        elif horizontal_top is not None and n.z > 0.9999 and abs(f.verts[0].co.z - horizontal_top) < EPS:
            targets.append((Vector((0.0, 0.0, 1.0)), f.verts[0].co.copy()))

    # Deduplicate coplanar targets (a plane may hold several faces).
    planes = []
    for n, p in targets:
        if not any(n.dot(n2) > 0.9999 and abs((p - p2).dot(n)) < EPS for n2, p2 in planes):
            planes.append((n, p))

    stones = []
    for n, p in planes:
        if n.z > 0.5:
            u_axis, v_axis, v_step = Vector((1, 0, 0)), Vector((0, 1, 0)), block
        else:
            u_axis, v_axis, v_step = Vector((-n.y, n.x, 0.0)), Vector((0, 0, 1)), course

        def region():
            return _plane_faces(bm, n, p)

        vs = [v.co.dot(v_axis) for f in region() for v in f.verts]
        k = math.floor(min(vs) / v_step) + 1
        while k * v_step < max(vs) - SLIVER:
            if k * v_step > min(vs) + SLIVER:
                _cut(bm, region(), v_axis * (k * v_step), v_axis)
            k += 1

        for f in list(region()):
            if not f.is_valid:
                continue
            fv = [v.co.dot(v_axis) for v in f.verts]
            row = math.floor((sum(fv) / len(fv)) / v_step + EPS)
            offset = (block * 0.5) if row % 2 else 0.0
            band = [f]
            us = [v.co.dot(u_axis) for v in f.verts]
            j = math.floor((min(us) - offset) / block) + 1
            while offset + j * block < max(us) - SLIVER:
                u = offset + j * block
                if u > min(us) + SLIVER:
                    band = [b for b in band if b.is_valid]
                    live = [b for b in band if min(v.co.dot(u_axis) for v in b.verts) < u - EPS
                            and max(v.co.dot(u_axis) for v in b.verts) > u + EPS]
                    before = set(bm.faces)
                    _cut(bm, live, u_axis * u + v_axis * 0.0, u_axis)
                    band = [b for b in band if b.is_valid] + [x for x in bm.faces if x not in before]
                j += 1

        # Concave faces, thin slivers and faces with tiny corner edges (broken
        # stones along a ruined edge) stay plain: insetting a reflex corner,
        # insetting deeper than the inradius, or insetting across an edge
        # shorter than the joint folds the ring faces over each other.
        plane_stones = [f for f in region() if _is_convex(f) and _inradius(f) > 3.0 * gap * 0.5
                        and min(e.calc_length() for e in f.edges) > 1.5 * gap]
        if not plane_stones:
            continue
        rings = bmesh.ops.inset_individual(bm, faces=plane_stones, thickness=gap * 0.5, depth=0.0,
                                           use_even_offset=True, use_relative_offset=False)["faces"]
        # Only interior joint lines are grooved. Vertices on the face's outer
        # boundary are shared with chamfers (and with the z = 0 contact edge);
        # moving them can fold a chamfer that meets a ruin cut at an acute
        # angle, so the perimeter joint stays a flush mortar strip.
        stone_verts = {v for f in plane_stones for v in f.verts}
        allowed = set(plane_stones) | set(rings)
        joint_verts = {v for f in rings for v in f.verts
                       if v not in stone_verts and all(lf in allowed for lf in v.link_faces)}
        for v in joint_verts:
            v.co -= n * depth
        for f in rings:
            f.material_index = MORTAR
        ring_set = set(rings)
        for f in plane_stones:
            # Interior stones are ringed only by grooved joints; stones on the
            # perimeter border the flush strip next to a chamfer.
            ring_verts = [v for e in f.edges for lf in e.link_faces if lf in ring_set for v in lf.verts]
            interior = all(v in stone_verts or v in joint_verts for v in ring_verts)
            stones.append((f, n, interior))
    return stones


MIN_CRACK_INRADIUS = 0.06  # cells


def crack(bm, stone, normal, rng, depth):
    """Split one stone with a jagged crack pushed into the surface.

    The crack ends stay on the stone's edge: they sit on straight edges that
    neighbouring faces share as collinear vertices, and pushing them would
    fold those faces. Only the interior crack polyline is grooved."""
    r = _inradius(stone)
    if r < MIN_CRACK_INRADIUS:
        return
    c = stone.calc_center_median()
    angle = rng.uniform(0.0, math.pi)
    if normal.z > 0.5:
        t1, t2 = Vector((1, 0, 0)), Vector((0, 1, 0))
    else:
        t1, t2 = Vector((-normal.y, normal.x, 0.0)), Vector((0, 0, 1))
    direction = t1 * math.cos(angle) + t2 * math.sin(angle)
    cut_no = direction.cross(normal).normalized()
    res = bmesh.ops.bisect_plane(bm, geom=_geom([stone]), dist=1e-7, plane_co=c, plane_no=cut_no)
    edges = [g for g in res["geom_cut"] if isinstance(g, bmesh.types.BMEdge)]
    if not edges:
        return
    sub = bmesh.ops.subdivide_edges(bm, edges=edges, cuts=2)
    inner = [g for g in sub["geom_inner"] if isinstance(g, bmesh.types.BMVert) and g.is_valid]
    # Operator output order is not stable across runs; sort before drawing
    # random numbers so each vertex always gets the same draw.
    inner.sort(key=lambda v: tuple(round(c, 5) for c in v.co))
    jitter = 0.2 * r
    for v in inner:
        v.co += cut_no * rng.uniform(-jitter, jitter) - normal * depth * 1.2


def weather(bm, stones, rng, depth, n_cracks, n_recess, recess_depth):
    """Crack some stones and recess others. Only interior stones (ringed by
    grooved joints on every side) are recessed, and never two neighbours, so
    no thin lip or mortar fin is left (the print min-wall check would rightly
    reject it)."""

    def box(f):
        return ([min(v.co[k] for v in f.verts) for k in range(3)],
                [max(v.co[k] for v in f.verts) for k in range(3)])

    def near(a, b, gap=0.05):
        # Neighbouring stones: recessing both would leave a thin mortar fin.
        return all(a[0][k] - gap <= b[1][k] and b[0][k] - gap <= a[1][k] for k in range(3))

    stones = [s for s in stones if s[0].is_valid]
    stones.sort(key=lambda s: tuple(round(c, 5) for c in s[0].calc_center_median()))
    order = rng.sample(range(len(stones)), len(stones))
    cracks = order[:n_cracks]
    recess, boxes = [], []
    for i in order[n_cracks:]:
        if len(recess) == n_recess:
            break
        b = box(stones[i][0])
        if stones[i][2] and not any(near(b, o) for o in boxes):
            recess.append(i)
            boxes.append(b)
    for i in recess:
        f, n, _ = stones[i]
        # One draw per stone: face loop order is not stable across runs.
        d = recess_depth * rng.uniform(0.6, 1.0)
        for v in f.verts:
            v.co -= n * d
    for i in cracks:
        f, n, _ = stones[i]
        if f.is_valid:
            crack(bm, f, n, rng, depth)


# --------------------------------------------------------------------------
# Pieces
# --------------------------------------------------------------------------

def build_piece(bm, contract, piece, variant, rng):
    grid, style = contract["grid"], contract["style"]
    t = grid["wall_thickness_cells"]
    h = piece["height_cells"]
    fx, fy = piece["footprint_cells"]
    ruined = variant == "ruined"
    pid = piece["id"]
    top = None

    if pid == "wall_straight":
        prims.add_prism(bm, wall_profile(fx, h, rng, ruined), 0.0, t, axes=("x", "z", "y"))
    elif pid == "doorway":
        prims.add_prism(bm, doorway_profile(fx, h, rng, ruined), 0.0, t, axes=("x", "z", "y"))
    elif pid == "corner_outer":
        prims.add_prism(bm, [(0, 0), (fx, 0), (fx, t), (t, t), (t, fy), (0, fy)], 0.0, h)
    elif pid == "floor_2x2":
        prims.add_box(bm, (0, 0, 0), (fx, fy, h))
        top = h
    elif pid == "pillar":
        inset = 0.06
        # The capital flares out over 0.10 cells of rise for 0.06 of run:
        # faces at 31 deg and corner chamfers at about 40 deg, inside the
        # 45 deg print overhang limit.
        prims.add_loft(bm, [
            (0.0, 0, 0, fx, fy), (0.2, 0, 0, fx, fy),
            (0.3, inset, inset, fx - inset, fy - inset),
            (h - 0.3, inset, inset, fx - inset, fy - inset),
            (h - 0.2, 0, 0, fx, fy), (h, 0, 0, fx, fy),
        ])
    else:
        raise ValueError(f"unknown piece '{pid}'")
    prims.recalc_normals(bm)

    if ruined and pid == "corner_outer":
        # Cut planes z = h0 + (s + t) x + (s - t) y. Keeping s + |t| <= 0.6
        # keeps every cut at least 60 deg off the vertical faces it meets,
        # so no knife-edge wedge forms, while the ends at x = 1 and y = 1
        # stay full height for the seams.
        m = RUIN_END_MARGIN
        for _ in range(2):
            tilt = rng.uniform(-0.1, 0.1)
            slope = rng.uniform(0.45, 0.6) - abs(tilt)
            h0 = h - (slope - abs(tilt)) * (fx - m)
            no = Vector((-(slope + tilt), -(slope - tilt), 1.0)).normalized()
            _ruin_cut(bm, Vector((0.0, 0.0, h0)), no)
    elif ruined and pid == "pillar":
        # The break stays inside the shaft (below h - 0.35 even at the most
        # tilted corner), away from the capital flare, where chamfers from
        # three directions would otherwise pinch into a thin crease.
        tip = Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 1.0)).normalized()
        _ruin_cut(bm, Vector((fx / 2, fy / 2, h - rng.uniform(0.5, 0.7))), tip)

    prims.chamfer_edges(bm, style["bevel_width_cells"], style["bevel_segments"], exclude_z0=True)
    # clamp_overlap can collapse two chamfer segments onto one point where a
    # ruin cut crosses a corner; merge such coincident vertices.
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    for f in bm.faces:
        f.material_index = STONE
    stones = stoneify(bm, piece, style, horizontal_top=top)

    depth = style["mortar_depth_cells"]
    if variant == "cracked":
        weather(bm, stones, rng, depth, n_cracks=4, n_recess=2, recess_depth=depth * 0.8)
    elif variant == "ruined":
        recess = 0.04 if pid == "floor_2x2" else depth * 0.9
        weather(bm, stones, rng, depth, n_cracks=6, n_recess=4, recess_depth=recess)

    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges[:])
    prims.recalc_normals(bm)


def build(contract, seed, piece_ids):
    pieces = api.pieces_by_id(contract)
    mats = [api.material(contract, "stone"), api.material(contract, "mortar")]
    objects = []
    for pid in piece_ids:
        for variant in contract["style"]["variants"]:
            rng = api.rng_for(seed, pid, variant)
            bm = bmesh.new()
            try:
                build_piece(bm, contract, pieces[pid], variant, rng)
                obj = prims.to_object(bm, api.piece_name(contract, pid, variant))
            finally:
                bm.free()
            for mat in mats:
                obj.data.materials.append(mat)
            # No UVs here: the core box-projects the tiling channel after it
            # has put positions in canonical, quantized form, so bmesh
            # last-bit noise never reaches the UVs.
            api.tag(obj, pid, variant, api.ROLE_MESH)
            objects.append(obj)
    return objects


def build_colliders(contract, obj):
    """Convex parts that keep doorways walkable and corners hollow."""
    from core.geometry import collider
    piece = api.pieces_by_id(contract)[obj[api.PROP_PIECE]]
    t = contract["grid"]["wall_thickness_cells"]
    h = piece["height_cells"]
    fx, fy = piece["footprint_cells"]
    boxes = {
        "wall_straight": [((0, 0, 0), (fx, t, h))],
        "doorway": [((0, 0, 0), (0.25, t, h)), ((0.75, 0, 0), (fx, t, h)), ((0.25, 0, 1.25), (0.75, t, h))],
        "corner_outer": [((0, 0, 0), (fx, t, h)), ((0, t, 0), (t, fy, h))],
        "floor_2x2": [((0, 0, 0), (fx, fy, h))],
    }.get(piece["id"])
    base = obj.name
    if boxes is None:
        parts = [collider.hull_of_object(obj, api.collider_name(contract, base, 0))]
    else:
        parts = [collider.box(lo, hi, api.collider_name(contract, base, i),
                              obj.users_collection[0] if obj.users_collection else None)
                 for i, (lo, hi) in enumerate(boxes)]
    for i, part in enumerate(parts):
        api.tag(part, obj[api.PROP_PIECE], obj[api.PROP_VARIANT], api.ROLE_COLLIDER, index=i)
    return parts
