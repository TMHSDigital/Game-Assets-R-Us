# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless Sollumz feasibility probe (EXPERIMENTAL, Blender 4.5).

Not part of the pipeline. Sollumz is never vendored: install the pinned
commit yourself (see docs/TODO.md or .github/workflows/fivem-sollumz.yml),
point BLENDER_USER_RESOURCES at that isolated folder, and run:

    blender --background --factory-startup --python profiles/fivem_sollumz/probe.py -- OUT_DIR [SZIO_SITE]

It builds the sampler wall, converts it to a Sollumz drawable, exports it
headless, re-imports the export with Sollumz and writes OUT_DIR/probe.json.
Exit 0 only if the export exists and re-imports at the original size.
"""

import json
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
ADDON = "bl_ext.user_default.sollumz_dev"


def main():
    import addon_utils
    import bpy

    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = os.path.abspath(argv[0] if argv else "sollumz_probe_out")
    if len(argv) > 1:
        sys.path.insert(0, argv[1])  # isolated site dir holding the pinned szio
    os.makedirs(out, exist_ok=True)
    result = {"blender": bpy.app.version_string, "steps": {}, "passed": False}

    def step(name, value):
        result["steps"][name] = value
        print(f"PROBE {name}: {value}")

    from core import pipeline
    from core.contract import load_contract, resolve
    from core.generators import get, load_module

    info = get("stone-dungeon-wall-sampler")
    contract = resolve(load_contract(info.contract_path), "gltf_web")
    scene = pipeline.generate(contract, load_module(info), 1337, ["wall_straight"])
    wall = [ps for ps in scene.sets if ps.variant == "clean"][0].lod0
    # From the vertices: obj.dimensions is stale until the depsgraph updates.
    cos = [v.co for v in wall.data.vertices]
    want_dims = [round(max(c[k] for c in cos) - min(c[k] for c in cos), 4) for k in range(3)]
    step("source", {"object": wall.name, "dims_m": want_dims})

    mod = addon_utils.enable(ADDON, default_set=True, handle_error=lambda e: traceback.print_exception(e))
    step("enabled", bool(mod))
    step("operators_registered", hasattr(bpy.types, "SOLLUMZ_OT_export_assets"))
    if not (mod and hasattr(bpy.types, "SOLLUMZ_OT_export_assets")):
        return result, out

    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    wall.select_set(True)
    bpy.context.view_layer.objects.active = wall
    step("convert_to_drawable", sorted(bpy.ops.sollumz.converttodrawable()))
    models = [o for o in bpy.data.objects if getattr(o, "sollum_type", "") == "sollumz_drawable_model"]
    drawables = [o for o in bpy.data.objects if getattr(o, "sollum_type", "") == "sollumz_drawable"]

    # Sollumz's material converter cannot read our procedural bump materials
    # (it expects an image Normal Map node), so plain Principled materials
    # stand in; a real exporter would assign Sollumz shaders directly.
    for model in models:
        for i, slot in enumerate(model.material_slots):
            plain = bpy.data.materials.new(f"probe_plain_{i}")
            plain.use_nodes = True
            slot.material = plain
    for obj in bpy.context.view_layer.objects:
        obj.select_set(obj in models)
    bpy.context.view_layer.objects.active = models[0]
    step("convert_materials", sorted(bpy.ops.sollumz.convertallmaterialstoselected()))

    for obj in bpy.context.view_layer.objects:
        obj.select_set(obj in drawables)
    step("export", sorted(bpy.ops.sollumz.export_assets(directory=out)))
    files = sorted(os.path.relpath(os.path.join(d, f), out).replace(os.sep, "/")
                   for d, _, fs in os.walk(out) for f in fs if f != "probe.json")
    step("files", files)
    target = next((f for f in files if f.endswith((".ydr", ".ydr.xml"))), None)
    if target is None:
        return result, out

    bpy.ops.wm.read_factory_settings(use_empty=True)
    mod = addon_utils.enable(ADDON, default_set=True)
    folder, name = os.path.split(os.path.join(out, target))
    step("reimport", sorted(bpy.ops.sollumz.import_assets(directory=folder, files=[{"name": name}])))
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    got = [round(d, 4) for d in meshes[0].dimensions] if meshes else None
    step("reimported_dims_m", got)
    result["passed"] = got is not None and all(abs(a - b) < 1e-3 for a, b in zip(got, want_dims))
    return result, out


if __name__ == "__main__":
    try:
        res, out_dir = main()
    except Exception:
        traceback.print_exc()
        res, out_dir = {"passed": False, "error": traceback.format_exc()}, os.getcwd()
    with open(os.path.join(out_dir, "probe.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2, sort_keys=True)
    print(f"PROBE passed: {res['passed']}")
    sys.stdout.flush()
    sys.exit(0 if res["passed"] else 1)
