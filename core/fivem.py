# SPDX-License-Identifier: GPL-3.0-or-later
"""FiveM export through Sollumz (EXPERIMENTAL, Blender 4.5 only).

Sollumz is never vendored: it must be installed (pinned commit, see
profiles/fivem_sollumz/profile.toml) in the running Blender. This module
only calls its public operators and helpers:

- each piece variant becomes one Sollumz drawable named
  <archetype_prefix><piece>_<variant>, with LOD0/LOD1/LOD2 as the High,
  Medium and Low LOD levels of one drawable model and the profile's LOD
  distances;
- materials are Sollumz shaders (profile `shader`, normal.sps) whose
  DiffuseSampler and BumpSampler name the baked tiling textures; meshes get
  the "UVMap 0" and "Color 1" layers those shaders read;
- the convex collider parts become one embedded bound composite (BVH) with
  the profile's collision material;
- export is Sollumz's export_assets (CodeWalker XML in gen8/ and gen9/);
  every file is re-imported with Sollumz and compared to the source.
"""

import importlib
import os
import re
import sys

import bmesh
import bpy

from .exporters.roundtrip import discard_new_datablocks
from .validators.report import write_json

UV0, COLOR = "UVMap 0", "Color 1"
VERTEX_STRIDE = 52  # position 12, normal 12, color 4, uv 8, tangent 16 bytes


class SollumzUnavailable(Exception):
    pass


def ensure_sollumz(profile):
    """Enable the pinned Sollumz in this Blender or raise with instructions."""
    want = tuple(int(x) for x in profile["blender_version"].split("."))
    if bpy.app.version[:2] != want:
        raise SollumzUnavailable(f"needs Blender {profile['blender_version']}, running {bpy.app.version_string}")
    site = os.environ.get("GARU_SZIO_SITE")
    if site and site not in sys.path:
        sys.path.insert(0, site)
    import addon_utils
    errors = []
    mod = addon_utils.enable(profile["sollumz_addon"], default_set=True, handle_error=errors.append)
    if not mod or not hasattr(bpy.types, "SOLLUMZ_OT_export_assets"):
        raise SollumzUnavailable(
            f"Sollumz ({profile['sollumz_addon']}) is not installed or its szio dependency is missing "
            f"({errors[0] if errors else 'operators not registered'}). Install {profile['sollumz_repo']} at "
            f"{profile['sollumz_commit']} and szio {profile['szio_version']} as described in docs/TODO.md, "
            "then set BLENDER_USER_RESOURCES and GARU_SZIO_SITE.")
    root = profile["sollumz_addon"]
    return {name: importlib.import_module(f"{root}.{name}") for name in (
        "sollumz_properties", "ydr.shader_materials", "tools.drawablehelper",
        "tools.boundhelper", "ybn.collision_materials")}


def _layers(mesh, tiling):
    """Rename the tiling UV to UVMap 0, drop other UV layers, add Color 1."""
    for layer in list(mesh.uv_layers):
        if layer.name != tiling:
            mesh.uv_layers.remove(layer)
    mesh.uv_layers[tiling].name = UV0
    if COLOR not in mesh.color_attributes:
        attr = mesh.color_attributes.new(COLOR, "BYTE_COLOR", "CORNER")
        attr.data.foreach_set("color", [1.0] * (4 * len(attr.data)))


def _sollumz_materials(sz, contract, textures):
    """One Sollumz shader material per palette slot, naming baked textures."""
    from .generators import api
    shader = contract["profile"]["shader"]
    by_slot = {}
    for entry in contract["materials"]["palette"]:
        slot = entry["slot"]
        mat = sz["ydr.shader_materials"].create_shader(shader)
        mat.name = f"{api.material_name(contract, slot)}_sz"
        nodes = mat.node_tree.nodes
        images = textures.get(slot, {})
        if "DiffuseSampler" in nodes and "base_color" in images:
            nodes["DiffuseSampler"].image = images["base_color"]
        if "BumpSampler" in nodes and "normal" in images:
            nodes["BumpSampler"].image = images["normal"]
        by_slot[api.material_name(contract, slot)] = mat
    return by_slot


def _join_colliders(parts, name):
    bm = bmesh.new()
    for part in parts:
        other = part.data.copy()
        other.transform(part.matrix_world)
        bm.from_mesh(other)
        bpy.data.meshes.remove(other)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _estimate_bytes(meshes):
    total = 0
    for mesh in meshes:
        mesh.calc_loop_triangles()
        total += len(mesh.loops) * VERTEX_STRIDE + len(mesh.loop_triangles) * 3 * 2
    return total


def build_drawables(scene, sz, textures):
    """Turn every piece set into a Sollumz drawable. Returns [(ps, drawable)]."""
    contract = scene.contract
    profile = contract["profile"]
    props = sz["sollumz_properties"]
    lod_levels = [props.LODLevel.HIGH, props.LODLevel.MEDIUM, props.LODLevel.LOW]
    mats = _sollumz_materials(sz, contract, textures)
    col_index = next(i for i, m in enumerate(sz["ybn.collision_materials"].collisionmats)
                     if m.name == profile["collision_material"])
    tiling = contract["uv"]["tiling_channel"]
    out = []
    for ps in scene.sets:
        chain = ps.mesh_objects()
        for obj in chain:
            _layers(obj.data, tiling)
            for i, slot in enumerate(obj.data.materials):
                obj.data.materials[i] = mats[slot.name]
        name = profile["archetype_prefix"] + f"{ps.piece}_{ps.variant}"
        ps.lod0.name = name
        drawable = sz["tools.drawablehelper"].convert_obj_to_drawable(ps.lod0)
        model = ps.lod0
        for level, lod_obj in zip(lod_levels[1:], ps.lods):
            model.sz_lods.get_lod(level).mesh = lod_obj.data
            bpy.data.objects.remove(lod_obj)
        dp = drawable.drawable_properties
        for attr, dist in zip(("lod_dist_high", "lod_dist_med", "lod_dist_low", "lod_dist_vlow"),
                              profile["lod_distances"]):
            setattr(dp, attr, dist)
        if profile["embedded_collision"] and ps.colliders:
            hull = _join_colliders(ps.colliders, f"{name}_col")
            for part in ps.colliders:
                bpy.data.objects.remove(part)
            hull.data.materials.append(
                sz["ybn.collision_materials"].create_collision_material_from_index(col_index))
            composite = sz["tools.boundhelper"].convert_obj_to_composite(
                hull, props.SollumType.BOUND_GEOMETRYBVH)
            composite.parent = drawable
        out.append((ps, drawable))
    return out


def baked_images(contract):
    """{slot: {map: image}} for the baked tiling textures (core/bake.py names)."""
    prefix = contract["kit"]["prefix"]
    maps = contract["textures"]["maps"] if contract.get("textures") else []
    return {e["slot"]: {m: bpy.data.images[f"T_{prefix}_{e['slot']}_{m}"]
                        for m in maps if f"T_{prefix}_{e['slot']}_{m}" in bpy.data.images}
            for e in contract["materials"]["palette"]}


def export(scene, exp_dir):
    """Build drawables, export them with Sollumz, re-import and compare."""
    contract = scene.contract
    profile = contract["profile"]
    sz = ensure_sollumz(profile)
    textures = baked_images(contract)
    # Capture what each drawable must come back as, before Sollumz edits it.
    expected = {}
    for ps in scene.sets:
        name = profile["archetype_prefix"] + f"{ps.piece}_{ps.variant}"
        lo = [min(v.co[k] for v in ps.lod0.data.vertices) for k in range(3)]
        hi = [max(v.co[k] for v in ps.lod0.data.vertices) for k in range(3)]
        ps.lod0.data.calc_loop_triangles()
        expected[name] = {"dims": [b - a for a, b in zip(lo, hi)], "tris": len(ps.lod0.data.loop_triangles),
                          "lods": 1 + len(ps.lods), "mem_bytes": _estimate_bytes([o.data for o in ps.mesh_objects()]),
                          # Same condition build_drawables embeds a bound under.
                          "collision": bool(profile["embedded_collision"] and ps.colliders)}
    drawables = build_drawables(scene, sz, textures)
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for _ps, drawable in drawables:
        drawable.select_set(True)
    result = bpy.ops.sollumz.export_assets(directory=exp_dir)
    if result != {"FINISHED"}:
        raise RuntimeError(f"sollumz.export_assets returned {result}")
    files = sorted(os.path.relpath(os.path.join(d, f), exp_dir).replace(os.sep, "/")
                   for d, _dirs, fs in os.walk(exp_dir) for f in fs
                   if f.endswith(".ydr.xml"))
    return files, _verify(exp_dir, files, expected), expected


def _verify(exp_dir, files, expected):
    results = {}
    for rel in files:
        stem = re.sub(r"\.ydr\.xml$", "", os.path.basename(rel))
        want = expected.get(stem)
        before = set(bpy.data.objects)
        folder, name = os.path.split(os.path.join(exp_dir, rel))
        problems = []
        # Sollumz creates meshes, materials, images and collections as well
        # as objects; drop them all so imports do not pile up.
        with discard_new_datablocks():
            bpy.ops.sollumz.import_assets(directory=folder, files=[{"name": name}])
            new = [o for o in bpy.data.objects if o not in before]
            models = [o for o in new if o.type == "MESH" and getattr(o, "sollum_type", "") == "sollumz_drawable_model"]
            bounds = [o for o in new if getattr(o, "sollum_type", "") == "sollumz_bound_composite"]
            if want is None:
                problems.append(f"no source drawable for {stem}")
            elif len(models) != 1:
                problems.append(f"{len(models)} drawable models")
            else:
                model = models[0]
                me = model.data
                lo = [min(v.co[k] for v in me.vertices) for k in range(3)]
                hi = [max(v.co[k] for v in me.vertices) for k in range(3)]
                dims = [b - a for a, b in zip(lo, hi)]
                if any(abs(a - b) > 1e-3 for a, b in zip(dims, want["dims"])):
                    problems.append(f"dims {dims} != {want['dims']}")
                me.calc_loop_triangles()
                if len(me.loop_triangles) != want["tris"]:
                    problems.append(f"tris {len(me.loop_triangles)} != {want['tris']}")
                lods = sum(1 for level in ("very_high", "high", "medium", "low", "very_low")
                           if getattr(model.sz_lods, level).has_mesh)
                if lods != want["lods"]:
                    problems.append(f"{lods} LOD levels != {want['lods']}")
                if want["collision"] and not bounds:
                    problems.append("no embedded collision")
                elif bounds and not want["collision"]:
                    problems.append(f"{len(bounds)} unexpected embedded collision bounds")
        results[rel] = {"passed": not problems, "problems": problems, "objects": 1}
    return results


def memory_report(expected, profile, out_dir):
    warn = profile["streamed_memory_warn_mib"] * 1024 * 1024
    rows = {name: {"estimate_mib": e["mem_bytes"] / (1024 * 1024), "over_warning": e["mem_bytes"] > warn}
            for name, e in sorted(expected.items())}
    report = {"method": f"geometry only: loops x {VERTEX_STRIDE} bytes + 2 bytes per index, all LODs; "
                        "textures ship separately (ytd)", "warn_mib": profile["streamed_memory_warn_mib"],
              "drawables": rows, "any_over_warning": any(r["over_warning"] for r in rows.values())}
    write_json(os.path.join(out_dir, "streamed_memory.json"), report)
    for name, r in rows.items():
        if r["over_warning"]:
            print(f"WARNING {name}: streamed memory estimate {r['estimate_mib']:.2f} MiB over "
                  f"{profile['streamed_memory_warn_mib']} MiB")
    return report
