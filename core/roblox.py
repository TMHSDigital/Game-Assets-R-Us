# SPDX-License-Identifier: GPL-3.0-or-later
"""Roblox preparation (profile material_mode = "single_baked").

Roblox allows one material per mesh and asks for watertight meshes, so each
piece keeps its single watertight mesh and gets one material: the piece's
tiling materials (stone, mortar, ...) are baked into one texture set on the
piece's unique lightmap UV layout, which then becomes its only UV layer.
Verified Roblox limits from the profile are enforced; unverified ones are
never applied.
"""

import os

import bpy

from . import bake, materials
from .geometry import lod as lod_mod


class RobloxLimitError(Exception):
    pass


def _limit(profile, key):
    entry = profile.get("limits", {}).get(key)
    return entry["value"] if entry and entry.get("verified") else None


def check_limits(contract, obj, texture_size):
    profile = contract["profile"]
    problems = []
    tris = lod_mod.triangle_count(obj)
    max_tris = _limit(profile, "max_triangles_per_mesh")
    if max_tris is not None and tris > max_tris:
        problems.append(f"{obj.name}: {tris} triangles > {max_tris:g}")
    max_mats = _limit(profile, "max_materials_per_mesh")
    if max_mats is not None and len(obj.data.materials) > max_mats:
        problems.append(f"{obj.name}: {len(obj.data.materials)} materials > {max_mats:g}")
    max_tex = _limit(profile, "max_texture_size_px")
    if max_tex is not None and texture_size > max_tex:
        problems.append(f"{obj.name}: texture {texture_size} px > {max_tex:g}")
    return problems


def prepare(scene, textures_dir):
    """Bake every piece to one material. Returns the written PNG paths."""
    contract = scene.contract
    profile = contract["profile"]
    size = profile["piece_texture_size"]
    light = contract["uv"]["lightmap_channel"]
    tiling = contract["uv"]["tiling_channel"]
    maps = contract["textures"]["maps"] if contract.get("textures") else ["base_color"]
    written, problems = [], []
    with bake.cycles_bake(bpy.context.scene):
        bpy.context.scene.render.bake.margin = 4
        for ps in scene.sets:
            obj = ps.lod0
            mesh = obj.data
            for layer in mesh.uv_layers:
                # Bake target and tangent space both come from the unique layout.
                layer.active = layer.name == light
                layer.active_render = layer.name == light
            images = {}
            for map_name in maps:
                name = f"T_{obj.name}_{map_name}"
                image = bake.new_image(name, size, map_name)
                if map_name == "normal":
                    # The tiling materials carry image normal maps now, which
                    # Cycles bakes directly (unlike a procedural Bump).
                    bake_type = "NORMAL"
                else:
                    bake_type = bake.MAPS[map_name][0]
                # The bake target nodes go into the shared palette materials;
                # remove them even when the bake raises, or later profiles in
                # the same run would render with them.
                added = []
                try:
                    for mat in mesh.materials:
                        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
                        added.append((mat.node_tree, node))
                        node.image = image
                        mat.node_tree.nodes.active = node
                    for other in bpy.context.view_layer.objects:
                        other.select_set(other == obj)
                    bpy.context.view_layer.objects.active = obj
                    result = bpy.ops.object.bake(type=bake_type)
                finally:
                    for tree, node in added:
                        tree.nodes.remove(node)
                if result != {"FINISHED"}:
                    raise RuntimeError(f"bake {map_name} of {obj.name} returned {result}")
                path = bake.save_png(image, os.path.join(textures_dir, f"{name}.png"))
                written.append(path)
                images[map_name] = image

            single = bpy.data.materials.new(f"M_{obj.name}")
            materials.build_image_based(contract, single, images, uv_channel=light)
            mesh.materials.clear()
            mesh.materials.append(single)
            for poly in mesh.polygons:
                poly.material_index = 0
            # The unique layout becomes the only UV layer, first and named
            # like the tiling channel, which importers treat as UV0.
            mesh.uv_layers.remove(mesh.uv_layers[tiling])
            mesh.uv_layers[light].name = tiling
            for node in single.node_tree.nodes:
                if node.type in {"UVMAP", "NORMAL_MAP"}:
                    node.uv_map = tiling
            problems += check_limits(contract, obj, size)
    if problems:
        raise RobloxLimitError("Roblox limits exceeded:\n  " + "\n  ".join(problems))
    return sorted(written)
