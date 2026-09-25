# Export profiles

| Profile | Status | Format | Axis / scale | LODs | Colliders |
|---|---|---|---|---|---|
| unity | working | FBX | -Z forward, Y up, meters, scale applied | `_LOD0.._LOD2` in one file | `UCX_<name>_NN` in the same file |
| unreal | working | FBX | -Z forward, Y up, meters with declared units | `<name>_LOD1.fbx`, `_LOD2.fbx` | `UCX_<name>_NN` with LOD0 |
| godot | working | GLB | glTF Y up, meters | `<name>_LOD1.glb`, `_LOD2.glb` | `<name>_colNN-convcolonly` in the same file |
| gltf_web | working | GLB, no Draco | glTF Y up, meters | separate files | `<name>_colliders.glb` |
| stl_print | working | binary STL | millimeters, base down | none | none |
| roblox | experimental | FBX, textures embedded | studs (Unit System None, FBX Units Scale) | LOD0 only (Roblox builds LODs) | none (set CollisionFidelity) |
| fivem_sollumz | experimental, Blender 4.5 + Sollumz | CodeWalker XML (.ydr.xml, gen8 and gen9) | meters | High/Medium/Low LOD levels with LOD distances | embedded bound composite (BVH, STONE) |

Every export is verified by importing it back into Blender and comparing
object names, triangle counts and per-axis sizes (`export_manifest.json`).
This proves the axis and unit settings are self-consistent. The godot
profile is also verified inside Godot 4 (`tests/test_godot_import.py`);
Unity and Unreal import tests are still a TODO (docs/TODO.md).

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

`roblox` is EXPERIMENTAL: it exports, but has been verified only by
re-import in Blender, not in Roblox Studio. Roblox allows one material per
mesh and asks for watertight meshes, so `core/roblox.py` bakes each piece's
tiling materials into one texture set on its unique (lightmap) UV layout,
which becomes its only UV layer. Export settings follow the Roblox Blender
export page. A limit in `profiles/roblox/profile.toml` carries a value only
when it has been verified against the Roblox documentation (source URL
recorded); verified limits are enforced at export, unverified ones never.
`tests/test_roblox.py` checks every FBX against them.

`fivem_sollumz` is EXPERIMENTAL, Blender 4.5 only, and needs the pinned
Sollumz commit and szio wheel installed (never vendored); without them it
exits 3 with instructions. `core/fivem.py` turns each piece variant into a
Sollumz drawable named `<archetype_prefix><piece>_<variant>`: LOD0 to LOD2
as the High, Medium and Low levels with the profile's LOD distances,
`normal.sps` materials naming the baked textures (lowercase, as the game
expects; the PNGs ship in textures/ for building a .ytd in CodeWalker), and
the convex collider parts as one embedded bound composite (BVH, collision
material STONE). Sollumz writes CodeWalker XML in `gen8/` and `gen9/`;
every file is re-imported through Sollumz and compared (size, triangles,
LOD levels, collision). A streamed-memory estimate (geometry only) is
written to `streamed_memory.json` and warns above 16 MiB.
`tests/test_fivem.py` runs where Sollumz is configured, and the manual
workflow `.github/workflows/fivem-sollumz.yml` installs it and runs it.
