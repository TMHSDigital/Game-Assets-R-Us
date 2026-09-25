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
import hashlib

import bpy

from ..compat import operator_kwargs

# Fixed FBX header time. Blender's FBX exporter already writes fixed FileId
# and CreationTime values and reads the clock only in
# fbx_header_elements(..., time=None). See _reproducible_fbx for the uids.
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


def _stable_key_to_uuid(fbx_utils):
    """Same as io_scene_fbx.fbx_utils._key_to_uuid, except that the uid comes
    from SHA-256 of the key instead of Python's hash(), which is salted per
    process and would give every export run different FBX object ids."""

    def key_to_uuid(uuids, key):
        if isinstance(key, int) and 0 <= key < 2**63:
            uuid = key
        else:
            uuid = int.from_bytes(hashlib.sha256(repr(key).encode("utf-8")).digest()[:8], "little") >> 1
        if uuid > int(1e9):
            t_uuid = uuid % int(1e9)
            if t_uuid not in uuids:
                uuid = t_uuid
        if uuid in uuids:
            inc = 1 if uuid < 2**62 else -1
            while uuid in uuids:
                uuid += inc
        return fbx_utils.UUID(uuid)

    return key_to_uuid


@contextlib.contextmanager
def _reproducible_fbx():
    """Pin the two per-run inputs of Blender's FBX exporter: the header time
    and the uid hash. Uid tables are reset so each file is independent of
    what was exported before it in the same process."""
    import io_scene_fbx.export_fbx_bin as fbx_bin
    import io_scene_fbx.fbx_utils as fbx_utils
    original_header = fbx_bin.fbx_header_elements
    original_key = fbx_utils._key_to_uuid

    def pinned(root, scene_data, time=None):
        return original_header(root, scene_data, FBX_FIXED_TIME)

    fbx_utils._keys_to_uuids.clear()
    fbx_utils._uuids_to_keys.clear()
    fbx_bin.fbx_header_elements = pinned
    fbx_utils._key_to_uuid = _stable_key_to_uuid(fbx_utils)
    try:
        yield
    finally:
        fbx_bin.fbx_header_elements = original_header
        fbx_utils._key_to_uuid = original_key


def export_fbx(path, objects, contract):
    _select_only(objects)
    exp = contract["profile"]["export"]
    with _reproducible_fbx():
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
