# SPDX-License-Identifier: GPL-3.0-or-later
"""Bake procedural materials to PNG textures (texture_provenance "generator").

Palette bake: every palette slot is baked once onto a plane that spans one
texture tile (one UV unit of the tiling channel, in profile units), giving a
seamless tiling set: base color, roughness and a tangent-space normal map.
The palette materials are then rebuilt around those images, so every piece
and every export uses them.

Cycles runs on the CPU with one sample and a fixed seed; the bakes are
deterministic (identical bytes across runs and across Blender 4.5 and 5.2 in
testing).
"""

import array
import contextlib
import math
import os

import bmesh
import bpy

from . import materials
from .generators import api

MAPS = {
    # map: (bake type, colorspace). The normal map is not baked by Cycles:
    # a bake has no ray differentials, so the Bump node contributes almost
    # nothing. Instead the height field is baked (EMIT, 32-bit float) and the
    # normal map is computed from it with wrap-around finite differences.
    "base_color": ("DIFFUSE", "sRGB"),
    "roughness": ("ROUGHNESS", "Non-Color"),
    "normal": ("EMIT", "Non-Color"),
}
# Tangent-space slope per unit of height per UV unit (one texture tile), so
# the look does not change with [textures] size. 6/1024 keeps the 1024 px
# default exactly as it was when the slope was taken per pixel with 6.0.
NORMAL_STRENGTH = 6.0 / 1024


@contextlib.contextmanager
def cycles_bake(scene):
    saved = {"engine": scene.render.engine}
    scene.render.engine = "CYCLES"
    cyc = scene.cycles
    saved.update(device=cyc.device, samples=cyc.samples, seed=cyc.seed,
                 denoise=getattr(cyc, "use_denoising", False))
    cyc.device = "CPU"
    cyc.samples = 1
    cyc.seed = 0
    if hasattr(cyc, "use_denoising"):
        cyc.use_denoising = False
    bake = scene.render.bake
    bake.use_pass_direct = False
    bake.use_pass_indirect = False
    bake.use_pass_color = True
    bake.normal_space = "TANGENT"
    bake.margin = 0
    try:
        yield
    finally:
        scene.render.engine = saved["engine"]
        cyc.device, cyc.samples, cyc.seed = saved["device"], saved["samples"], saved["seed"]
        if hasattr(cyc, "use_denoising"):
            cyc.use_denoising = saved["denoise"]


def _tile_plane(contract):
    """A plane covering one tiling-texture repeat, UVs 0..1 in the tiling channel."""
    size = contract["profile"]["cell_size"] / contract["uv"]["tiling_scale_per_cell"]
    bm = bmesh.new()
    verts = [bm.verts.new(co) for co in ((0, 0, 0), (size, 0, 0), (size, size, 0), (0, size, 0))]
    face = bm.faces.new(verts)
    uv = bm.loops.layers.uv.new(contract["uv"]["tiling_channel"])
    for loop, (u, v) in zip(face.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop[uv].uv = (u, v)
    mesh = bpy.data.meshes.new("garu_bake_plane")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("garu_bake_plane", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _bake_into(obj, mat, map_name, image):
    bake_type = MAPS[map_name][0]
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    mat.node_tree.nodes.active = node
    for other in bpy.context.view_layer.objects:
        other.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        result = bpy.ops.object.bake(type=bake_type)
    finally:
        mat.node_tree.nodes.remove(node)
    if result != {"FINISHED"}:
        raise RuntimeError(f"bake {map_name} of {mat.name} returned {result}")


def _bake_height(obj, mat, size, name):
    """Bake the material's height field (input of its garu_height Bump node)
    into a 32-bit float image via a temporary emission surface."""
    tree = mat.node_tree
    bump = tree.nodes.get(materials.HEIGHT_NODE)
    out = next(n for n in tree.nodes if n.type == "OUTPUT_MATERIAL")
    surface_src = out.inputs["Surface"].links[0].from_socket
    height_src = bump.inputs["Height"].links[0].from_socket
    emit = tree.nodes.new("ShaderNodeEmission")
    tree.links.new(height_src, emit.inputs["Color"])
    tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    image = bpy.data.images.new(name, size, size, alpha=False, float_buffer=True)
    image.colorspace_settings.name = "Non-Color"
    try:
        _bake_into(obj, mat, "normal", image)
    finally:
        tree.links.new(surface_src, out.inputs["Surface"])
        tree.nodes.remove(emit)
    return image


def normal_from_height(height, target, strength=NORMAL_STRENGTH):
    """Tangent-space (OpenGL, +Y) normal map from a height image, with
    wrap-around differences so the result tiles like the height does."""
    s = height.size[0]
    px = array.array("f", [0.0]) * (s * s * 4)
    height.pixels.foreach_get(px)
    h = px[0::4]
    out = array.array("f", [0.0]) * (s * s * 4)
    # Differences are per pixel; s pixels span one UV unit.
    k = strength * s
    for y in range(s):
        row, up, down = y * s, ((y + 1) % s) * s, ((y - 1) % s) * s
        for x in range(s):
            dx = (h[row + (x + 1) % s] - h[row + (x - 1) % s]) * 0.5 * k
            dy = (h[up + x] - h[down + x]) * 0.5 * k
            inv = 1.0 / math.sqrt(dx * dx + dy * dy + 1.0)
            i = (row + x) * 4
            out[i] = -dx * inv * 0.5 + 0.5
            out[i + 1] = -dy * inv * 0.5 + 0.5
            out[i + 2] = inv * 0.5 + 0.5
            out[i + 3] = 1.0
    target.pixels.foreach_set(out)
    return target


def new_image(name, size, map_name):
    image = bpy.data.images.new(name, size, size, alpha=False)
    image.colorspace_settings.name = MAPS[map_name][1]
    image["garu_generated"] = True
    return image


def save_png(image, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    return path


def bake_palette(contract, textures_dir):
    """Bake every palette slot. Returns {slot: {map: bpy image}}."""
    tex = contract["textures"]
    scene = bpy.context.scene
    plane = _tile_plane(contract)
    baked = {}
    try:
        with cycles_bake(scene):
            for entry in contract["materials"]["palette"]:
                slot = entry["slot"]
                mat = api.material(contract, slot)
                plane.data.materials.clear()
                plane.data.materials.append(mat)
                baked[slot] = {}
                for map_name in tex["maps"]:
                    name = f"T_{contract['kit']['prefix']}_{slot}_{map_name}"
                    image = new_image(name, tex["size"], map_name)
                    if map_name == "normal":
                        height = _bake_height(plane, mat, tex["size"], f"{name}_height")
                        normal_from_height(height, image)
                        bpy.data.images.remove(height)
                    else:
                        _bake_into(plane, mat, map_name, image)
                    save_png(image, os.path.join(textures_dir, f"{name}.png"))
                    baked[slot][map_name] = image
    finally:
        mesh = plane.data
        bpy.data.objects.remove(plane)
        bpy.data.meshes.remove(mesh)
    return baked


def apply_baked(contract, baked):
    """Rebuild the palette materials around the baked images."""
    for slot, images in baked.items():
        materials.build_image_based(contract, api.material(contract, slot), images)


def bake_and_apply(contract, textures_dir):
    baked = bake_palette(contract, textures_dir)
    apply_baked(contract, baked)
    return sorted(os.path.join(textures_dir, f) for f in os.listdir(textures_dir))
