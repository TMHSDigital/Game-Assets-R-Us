# SPDX-License-Identifier: GPL-3.0-or-later
"""Palette materials.

Procedural stage (no external textures, HDRIs or fonts): each palette slot
is a Principled BSDF whose color, roughness and bump come from 4D noise
sampled on a torus built from the tiling UV channel:

    (cos 2 pi u, sin 2 pi u, cos 2 pi v, sin 2 pi v)

so the pattern repeats exactly once per UV unit and a baked texture tiles
without seams.

Image stage (after baking, see core/bake.py): the same materials are
rebuilt around the baked PNG textures, which is what engines receive.
"""

import math

import bpy

from .generators import api

TAU = 2.0 * math.pi
HEIGHT_NODE = "garu_height"


def _node_tree(mat):
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    return tree


def _torus_noise(tree, uv_socket, scale, w_offset=0.0, detail=2.0):
    """4D noise that is periodic in u and v with period 1."""
    sep = tree.nodes.new("ShaderNodeSeparateXYZ")
    tree.links.new(uv_socket, sep.inputs[0])

    def angle(src, fn, offset=0.0):
        mul = tree.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = TAU
        tree.links.new(src, mul.inputs[0])
        trig = tree.nodes.new("ShaderNodeMath")
        trig.operation = fn
        tree.links.new(mul.outputs[0], trig.inputs[0])
        if not offset:
            return trig.outputs[0]
        add = tree.nodes.new("ShaderNodeMath")
        add.operation = "ADD"
        add.inputs[1].default_value = offset
        tree.links.new(trig.outputs[0], add.inputs[0])
        return add.outputs[0]

    comb = tree.nodes.new("ShaderNodeCombineXYZ")
    tree.links.new(angle(sep.outputs[0], "COSINE"), comb.inputs[0])
    tree.links.new(angle(sep.outputs[0], "SINE"), comb.inputs[1])
    tree.links.new(angle(sep.outputs[1], "COSINE"), comb.inputs[2])
    noise = tree.nodes.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "4D"
    noise.inputs["Scale"].default_value = scale
    # Few octaves: finer ones fall below one texel of a 1024 px tile and
    # alias into grain in the baked maps.
    noise.inputs["Detail"].default_value = detail
    tree.links.new(comb.outputs[0], noise.inputs["Vector"])
    tree.links.new(angle(sep.outputs[1], "SINE", w_offset), noise.inputs["W"])
    return noise.outputs["Fac"]


def build_procedural(contract, entry, mat):
    tree = _node_tree(mat)
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    uv = tree.nodes.new("ShaderNodeUVMap")
    uv.uv_map = contract["uv"]["tiling_channel"]
    scale = entry.get("noise_scale", 8.0)

    raw = _torus_noise(tree, uv.outputs["UV"], scale)
    # 4D noise clusters around 0.5; stretch it so the two palette colors mix.
    stretch = tree.nodes.new("ShaderNodeMapRange")
    stretch.clamp = True
    stretch.inputs["From Min"].default_value = 0.35
    stretch.inputs["From Max"].default_value = 0.65
    tree.links.new(raw, stretch.inputs["Value"])
    color_fac = stretch.outputs["Result"]
    mix = tree.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    # The Mix node has one A/B/Result socket per data type; pick the color
    # ones by identifier, not by (shared) name.
    ins = {s.identifier: s for s in mix.inputs}
    outs = {s.identifier: s for s in mix.outputs}
    ins["A_Color"].default_value = (*entry["base_color"], 1.0)
    ins["B_Color"].default_value = (*entry.get("base_color_2", entry["base_color"]), 1.0)
    tree.links.new(color_fac, ins["Factor_Float"])
    tree.links.new(outs["Result_Color"], bsdf.inputs["Base Color"])

    rough = tree.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = max(0.0, entry["roughness"] - 0.1)
    rough.inputs["To Max"].default_value = min(1.0, entry["roughness"] + 0.1)
    tree.links.new(color_fac, rough.inputs["Value"])
    tree.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])

    bump_fac = _torus_noise(tree, uv.outputs["UV"], scale * 2.0, w_offset=7.0, detail=1.0)
    bump = tree.nodes.new("ShaderNodeBump")
    bump.name = HEIGHT_NODE  # core/bake.py bakes this node's Height input
    bump.inputs["Strength"].default_value = 0.35
    tree.links.new(bump_fac, bump.inputs["Height"])
    tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    mat.diffuse_color = (*entry["base_color"], 1.0)
    mat.roughness = entry["roughness"]


def build_image_based(contract, mat, images, uv_channel=None):
    """Rebuild a material around baked images {map: bpy image}."""
    tree = _node_tree(mat)
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    uv = tree.nodes.new("ShaderNodeUVMap")
    uv.uv_map = uv_channel or contract["uv"]["tiling_channel"]

    def tex(image):
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        node.interpolation = "Linear"
        tree.links.new(uv.outputs["UV"], node.inputs["Vector"])
        return node

    if "base_color" in images:
        tree.links.new(tex(images["base_color"]).outputs["Color"], bsdf.inputs["Base Color"])
    if "roughness" in images:
        tree.links.new(tex(images["roughness"]).outputs["Color"], bsdf.inputs["Roughness"])
    if "normal" in images:
        nmap = tree.nodes.new("ShaderNodeNormalMap")
        nmap.space = "TANGENT"
        nmap.uv_map = uv.uv_map
        tree.links.new(tex(images["normal"]).outputs["Color"], nmap.inputs["Color"])
        tree.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])


def ensure_palette(contract):
    mats = {}
    for entry in contract["materials"]["palette"]:
        name = api.material_name(contract, entry["slot"])
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        build_procedural(contract, entry, mat)
        mats[entry["slot"]] = mat
    return mats
