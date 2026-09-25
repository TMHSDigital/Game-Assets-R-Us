# SPDX-License-Identifier: GPL-3.0-or-later
"""UV channels.

Channel 0 (tiling): world-aligned box projection, so texel density is set
exactly by the contract (tiling_scale_per_cell) on every piece. Tiling UVs
overlap by design, as usual for modular kits with tiling materials.

Channel 1 (lightmap): unique, non-overlapping layout from smart_project plus
lightmap_pack. Its overlap is measured independently afterwards; the packer's
result is never trusted.

The lightmap authoring and the SAT overlap test are adapted from the author's
Blender-Developer-Tools (examples/lightmap-uv-channel), relicensed here under
GPL-3.0-or-later. Two hazards found there are handled here:
- lightmap_pack silently packs nothing when the active layer is empty, so
  smart_project runs first;
- holding a MeshUVLoopLayer across edit-mode UV operators can crash Blender
  4.5 headless, so layers are always re-fetched by name.
"""

import math

import bpy

SAT_EPS = 1e-7


def box_project(obj, channel, scale_per_cell, cell=1.0):
    """World-aligned box projection. `cell` is the size of one grid cell in
    the object's current units, so the mapping stays scale_per_cell UV units
    per cell regardless of the profile unit."""
    mesh = obj.data
    layer = mesh.uv_layers.get(channel) or mesh.uv_layers.new(name=channel)
    mw = obj.matrix_world
    k = scale_per_cell / cell
    for poly in mesh.polygons:
        n = poly.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in poly.loop_indices:
            co = mw @ mesh.vertices[mesh.loops[li].vertex_index].co
            if ax == 0:
                u, v = (co.y if n.x > 0 else -co.y), co.z
            elif ax == 1:
                u, v = (-co.x if n.y > 0 else co.x), co.z
            else:
                u, v = co.x, (co.y if n.z > 0 else -co.y)
            layer.data[li].uv = (u * k, v * k)
    return layer.name


def _set_active(mesh, active, render):
    for layer in mesh.uv_layers:
        layer.active = layer.name == active
        layer.active_render = layer.name == render


def lightmap(obj, channel, render_channel, margin=0.02):
    """Author a non-overlapping lightmap channel with Blender's own ops."""
    mesh = obj.data
    if mesh.uv_layers.get(channel) is None:
        mesh.uv_layers.new(name=channel)
    _set_active(mesh, channel, render_channel)
    view_layer = bpy.context.view_layer
    for other in view_layer.objects:
        other.select_set(False)
    view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=0.0,
                             area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    # Measured in Blender-Developer-Tools: nominal margin in UV units is
    # PREF_MARGIN_DIV * 0.01, and the operator caps PREF_MARGIN_DIV at 1.0.
    margin_div = min(1.0, max(0.001, margin / 0.01))
    bpy.ops.uv.lightmap_pack(PREF_CONTEXT="ALL_FACES", PREF_PACK_IN_ONE=True,
                             PREF_NEW_UVLAYER=False, PREF_MARGIN_DIV=margin_div)
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.select_set(False)
    _set_active(obj.data, channel, render_channel)


def uv_triangles(mesh, channel):
    """UV triangles from Blender's own triangulation (correct for concave
    n-gons, unlike a fan)."""
    layer = mesh.uv_layers[channel]
    mesh.calc_loop_triangles()
    return [tuple(tuple(layer.data[li].uv) for li in tri.loops) for tri in mesh.loop_triangles]


def _tri_overlap(t1, t2):
    """Strict 2D separating-axis test: True only for area-positive overlap,
    so shared edges and touching corners do not count."""
    for tri in (t1, t2):
        for i in range(3):
            x1, y1 = tri[i]
            x2, y2 = tri[(i + 1) % 3]
            nx, ny = -(y2 - y1), (x2 - x1)
            nlen = math.hypot(nx, ny)
            if nlen < 1e-12:
                continue
            nx, ny = nx / nlen, ny / nlen
            p1 = [nx * p[0] + ny * p[1] for p in t1]
            p2 = [nx * p[0] + ny * p[1] for p in t2]
            if min(max(p1), max(p2)) - max(min(p1), min(p2)) < SAT_EPS:
                return False
    return True


def _area2(t):
    (ax, ay), (bx, by), (cx, cy) = t
    return abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay))


def _ccw(t):
    (ax, ay), (bx, by), (cx, cy) = t
    return t if (bx - ax) * (cy - ay) - (cx - ax) * (by - ay) > 0 else (t[0], t[2], t[1])


def intersection_area(t1, t2):
    """Exact overlap area of two triangles (Sutherland-Hodgman clipping)."""
    poly = list(_ccw(t1))
    clip = _ccw(t2)
    for i in range(3):
        ax, ay = clip[i]
        bx, by = clip[(i + 1) % 3]
        inside = lambda p: (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax) >= 0.0
        out = []
        for j in range(len(poly)):
            p, q = poly[j], poly[(j + 1) % len(poly)]
            pin, qin = inside(p), inside(q)
            if pin:
                out.append(p)
            if pin != qin:
                dx, dy = q[0] - p[0], q[1] - p[1]
                den = (bx - ax) * dy - (by - ay) * dx
                if den != 0.0:
                    s = ((ax - p[0]) * (by - ay) - (ay - p[1]) * (bx - ax)) / -den
                    out.append((p[0] + s * dx, p[1] + s * dy))
        poly = out
        if len(poly) < 3:
            return 0.0
    return abs(sum(poly[k][0] * poly[k - 1][1] - poly[k - 1][0] * poly[k][1] for k in range(len(poly)))) / 2


MIN_OVERLAP_AREA = 1e-8  # UV units^2: about 1% of one texel at 1024 px


def overlap_pairs(tris, bins=64):
    """Count UV triangle pairs that overlap by more than MIN_OVERLAP_AREA.

    Broad phase: uniform grid. Narrow phase: separating-axis reject, then the
    exact clipped overlap area, so slivers that merely touch along a shared
    edge are not reported."""
    tris = [t for t in tris if _area2(t) > 1e-14]
    if not tris:
        return 0
    xs = [p[0] for t in tris for p in t]
    ys = [p[1] for t in tris for p in t]
    x0, y0 = min(xs), min(ys)
    span = max(max(xs) - x0, max(ys) - y0, 1e-9)
    cell = span / bins
    grid = {}
    for i, t in enumerate(tris):
        bx0 = int((min(p[0] for p in t) - x0) / cell)
        bx1 = int((max(p[0] for p in t) - x0) / cell)
        by0 = int((min(p[1] for p in t) - y0) / cell)
        by1 = int((max(p[1] for p in t) - y0) / cell)
        for bx in range(bx0, bx1 + 1):
            for by in range(by0, by1 + 1):
                grid.setdefault((bx, by), []).append(i)
    tested = set()
    hits = 0
    for members in grid.values():
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                pair = (members[a], members[b])
                if pair in tested:
                    continue
                tested.add(pair)
                t1, t2 = tris[pair[0]], tris[pair[1]]
                if _tri_overlap(t1, t2) and intersection_area(t1, t2) > MIN_OVERLAP_AREA:
                    hits += 1
    return hits
