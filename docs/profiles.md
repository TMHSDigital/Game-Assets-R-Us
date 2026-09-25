# Export profiles

| Profile | Status | Format | Axis / scale | LODs | Colliders |
|---|---|---|---|---|---|
| unity | working | FBX | -Z forward, Y up, meters, scale applied | `_LOD0.._LOD2` in one file | `UCX_<name>_NN` in the same file |
| unreal | working | FBX | -Z forward, Y up, meters with declared units | `<name>_LOD1.fbx`, `_LOD2.fbx` | `UCX_<name>_NN` with LOD0 |
| godot | working | GLB | glTF Y up, meters | `<name>_LOD1.glb`, `_LOD2.glb` | `<name>_colNN-convcolonly` in the same file |
| gltf_web | working | GLB, no Draco | glTF Y up, meters | separate files | `<name>_colliders.glb` |
| stl_print | working | binary STL | millimeters, base down | none | none |
| roblox | stub | (FBX) | studs | stub | stub |
| fivem_sollumz | experimental stub | (YDR) | meters | stub | stub |

Every export is verified by importing it back into Blender and comparing
object names, triangle counts and per-axis sizes (`export_manifest.json`).
This proves the axis and unit settings are self-consistent. Import tests in
each engine are still a TODO (docs/TODO.md).

Two presets from Blender-Developer-Tools were deliberately not ported: its
Godot preset writes Z-up glTF (the glTF spec is Y-up), and its Unreal preset
(global_scale 100 without unit scale) re-imported at 100x in the round-trip
check.

## Reproducible output

Building twice with the same seed and contract writes byte-identical files
for every working profile (`tests/test_determinism.py`). What makes that
hold:

- every mesh is triangulated and rebuilt in canonical element order, with
  positions quantized to 1e-6 units, before UV packing and export
  (`core/geometry/canonical.py`);
- the FBX exporter's header time and its object uid hash (Python `hash()`,
  salted per process) are pinned during export (`core/exporters/writers.py`);
- zips use sorted entries, fixed timestamps and fixed permissions.

Hashes are compared within one Blender version. Different Blender versions
may write different bytes (the glTF exporter embeds its version, and
decimation results can shift), which is why LOD checks use budgets, not
exact counts.

## Stubs

`roblox` has a schema and a stub exporter only. Running it validates the
profile and exits with code 3. A limit in `profiles/roblox/profile.toml`
carries a value only when it has been verified against the Roblox
documentation (source URL recorded); the schema rejects a value without
`verified = true`.

`fivem_sollumz` is EXPERIMENTAL: schema fields (archetype prefix, embedded
collision, LOD distances, 16 MiB streamed memory warning, target builds), a
stub exporter, Blender 4.5 only, and a pinned Sollumz commit and szio wheel.
Sollumz is never vendored; the manual workflow
`.github/workflows/fivem-sollumz.yml` installs it at run time and runs
`profiles/fivem_sollumz/probe.py`, which showed headless export works (see
docs/TODO.md for what a real exporter still needs).
