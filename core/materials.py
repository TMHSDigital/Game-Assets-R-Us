# SPDX-License-Identifier: GPL-3.0-or-later
"""Procedural palette materials.

No external textures, HDRIs or fonts. Base color and roughness are plain
constants on the Principled BSDF, because game exporters (glTF, FBX) carry
only constant factors from procedural node trees. The procedural noise
drives a Bump node, which shows in Blender renders and previews without
changing what engines receive.
"""

import bpy

from .generators import api


def ensure_palette(contract):
    mats = {}
    for entry in contract["materials"]["palette"]:
        name = api.material_name(contract, entry["slot"])
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        if bpy.app.version < (5, 0, 0):
            mat.use_nodes = True
        tree = mat.node_tree
        tree.nodes.clear()
        out = tree.nodes.new("ShaderNodeOutputMaterial")
        bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
        rgba = (*entry["base_color"], 1.0)
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = entry["roughness"]
        tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        noise = tree.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = entry.get("noise_scale", 8.0)
        bump = tree.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.25
        tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        mat.diffuse_color = rgba
        mat.roughness = entry["roughness"]
        mats[entry["slot"]] = mat
    return mats
