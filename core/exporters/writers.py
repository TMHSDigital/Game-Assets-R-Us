# SPDX-License-Identifier: GPL-3.0-or-later
"""File writers for GLB, FBX and STL with fixed, reproducible settings.

Engine axis and scale presets come from the profile. Two presets from the
author's Blender-Developer-Tools were deliberately not ported: the Godot one
exports Z-up glTF (the glTF spec is Y-up and Godot imports it as such), and
the Unreal one (global_scale 100, apply_unit_scale off) re-imports at 100x
in the export round-trip check. See profiles/unreal/profile.toml.
"""

import contextlib
import datetime

import bpy

from ..compat import operator_kwargs

# Fixed FBX header time so files are byte-for-byte reproducible. Blender's
# FBX exporter already writes fixed FileId and CreationTime values and reads
# the clock only in fbx_header_elements(..., time=None).
FBX_FIXED_TIME = datetime.datetime(2000, 1, 1, 0, 0, 0)


def _select_only(objects):
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def _call(op, wanted):
    accepted, dropped = operator_kwargs(op, wanted)
    result = op(**accepted)
    if result != {"FINISHED"}:
        raise RuntimeError(f"{op.idname()} returned {result}")
    return {"accepted": {k: (sorted(v) if isinstance(v, set) else v) for k, v in accepted.items() if k != "filepath"},
            "dropped": dropped}


def export_glb(path, objects, contract):
    _select_only(objects)
    exp = contract["profile"]["export"]
    return _call(bpy.ops.export_scene.gltf, {
        "filepath": path,
        "export_format": "GLB",
        "use_selection": True,
        "export_yup": exp["export_yup"],
        "export_apply": True,
        "export_texcoords": True,
        "export_normals": True,
        "export_materials": "EXPORT",
        "export_animations": False,
        "export_skins": False,
        "export_morph": False,
        "export_cameras": False,
        "export_lights": False,
        "export_extras": False,
        "export_draco_mesh_compression_enable": False,
        "export_copyright": contract["legal"]["license"],
    })


@contextlib.contextmanager
def _fixed_fbx_time():
    import io_scene_fbx.export_fbx_bin as fbx_bin
    original = fbx_bin.fbx_header_elements

    def pinned(root, scene_data, time=None):
        return original(root, scene_data, FBX_FIXED_TIME)

    fbx_bin.fbx_header_elements = pinned
    try:
        yield
    finally:
        fbx_bin.fbx_header_elements = original


def export_fbx(path, objects, contract):
    _select_only(objects)
    exp = contract["profile"]["export"]
    with _fixed_fbx_time():
        return _call(bpy.ops.export_scene.fbx, {
            "filepath": path,
            "use_selection": True,
            "object_types": {"MESH"},
            "use_mesh_modifiers": True,
            "mesh_smooth_type": exp["mesh_smooth_type"],
            "axis_forward": exp["axis_forward"],
            "axis_up": exp["axis_up"],
            "global_scale": exp["global_scale"],
            "apply_unit_scale": exp["apply_unit_scale"],
            "apply_scale_options": exp["apply_scale_options"],
            "bake_space_transform": exp["bake_space_transform"],
            "use_custom_props": False,
            "add_leaf_bones": False,
            "bake_anim": False,
            "use_tspace": False,
            "embed_textures": False,
            "path_mode": "STRIP",
        })


def export_stl(path, objects, contract):
    _select_only(objects)
    return _call(bpy.ops.wm.stl_export, {
        "filepath": path,
        "export_selected_objects": True,
        "ascii_format": contract["profile"]["ascii"],
        "global_scale": 1.0,
        "use_scene_unit": False,
        "apply_modifiers": True,
        "forward_axis": "Y",
        "up_axis": "Z",
    })
