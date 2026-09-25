# SPDX-License-Identifier: GPL-3.0-or-later
"""Canonical element order for meshes.

Some bmesh operators (bisect, inset, convex hull, booleans) return elements
in an order that depends on memory layout, so two runs with identical vertex
positions can still write different bytes. The core therefore rebuilds every
mesh it owns in a canonical order before UV packing and export:

  vertices  quantized to 1e-6 units, then sorted by position
  faces     each loop rotated to start at its lowest vertex index, then
            faces sorted by their vertex index tuples
  edges     derived from the faces (deterministic)

Material indices and every UV layer (quantized like positions) are carried
over per loop. With this in
place, deterministic positions are enough for byte-identical exports.
"""


def canonicalize(mesh, digits=6):
    # Quantize first: bmesh operators can leave last-bit float noise that
    # depends on internal element order (0.5 vs 0.49999997).
    verts = [tuple(round(c, digits) for c in v.co) for v in mesh.vertices]
    order = sorted(range(len(verts)), key=lambda i: verts[i])
    new_index = {old: new for new, old in enumerate(order)}
    layers = [layer.name for layer in mesh.uv_layers]
    # UVs are quantized too: UVs projected from pre-quantization positions
    # carry the same last-bit noise.
    uv_data = {name: [tuple(round(c, digits) for c in d.uv) for d in mesh.uv_layers[name].data] for name in layers}

    polys = []
    for poly in mesh.polygons:
        loops = [(new_index[mesh.loops[li].vertex_index],
                  tuple(uv_data[name][li] for name in layers)) for li in poly.loop_indices]
        start = min(range(len(loops)), key=lambda k: loops[k][0])
        loops = loops[start:] + loops[:start]
        polys.append((tuple(v for v, _ in loops), poly.material_index, poly.use_smooth, loops))
    polys.sort(key=lambda p: p[0])

    materials = list(mesh.materials)
    mesh.clear_geometry()
    mesh.from_pydata([verts[i] for i in order], [], [p[0] for p in polys])
    mesh.update(calc_edges=True)
    mesh.materials.clear()
    for mat in materials:
        mesh.materials.append(mat)
    mesh.polygons.foreach_set("material_index", [p[1] for p in polys])
    mesh.polygons.foreach_set("use_smooth", [p[2] for p in polys])
    for li_layer, name in enumerate(layers):
        layer = mesh.uv_layers.get(name) or mesh.uv_layers.new(name=name)
        flat = [c for p in polys for _, uvs in p[3] for c in uvs[li_layer]]
        layer.data.foreach_set("uv", flat)
    mesh.update()
    return mesh


def triangulate(mesh):
    """Triangulate with Blender's BEAUTY method, so the triangles that are
    validated are exactly the triangles that are exported, and n-gons with
    collinear vertices never turn into zero-area ears downstream."""
    import bmesh
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="BEAUTY")
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()
    return mesh


def finalize(mesh):
    """Canonical order, then triangulate, then canonical order again.

    The first pass matters: BEAUTY triangulation breaks exact ties (a square
    face has two equally good diagonals) by loop order, so loop order has to
    be canonical before triangulating, or memory layout picks the diagonal."""
    canonicalize(mesh)
    triangulate(mesh)
    return canonicalize(mesh)


def canonicalize_objects(objects):
    for obj in objects:
        if obj.type == "MESH":
            canonicalize(obj.data)
