# Open TODOs

## Roblox limits (profile: roblox, stub)
Every platform limit in `profiles/roblox/profile.toml` is unset and marked
`verified = false`. Before an exporter is written, check each against the
Roblox documentation and record value, source URL and `verified = true`:
- https://create.roblox.com/docs/art/modeling/specifications
- https://create.roblox.com/docs/art/modeling/export-requirements
- https://create.roblox.com/docs/art/modeling/meshes

Also confirm the stud-to-meter relationship; `cell_size = 8.0` studs is a
design choice, not a documented value.

## Sollumz headless feasibility (profile: fivem_sollumz, experimental)
- Run `.github/workflows/fivem-sollumz.yml` (manual) to find out whether
  Sollumz enables and exports under `blender --background` on 4.5.
- Sollumz commit pinned: see `profiles/fivem_sollumz/profile.toml`. Sollumz
  is GPL-3.0 and is never vendored here.
- Fill in `target_builds` once the target game builds are confirmed.
- Streamed memory estimate against the 16 MiB warning threshold is not
  implemented.

## Clip-standard compatibility (stl_print)
`garu_dogbone_v1` is this project's own design. Compatibility with existing
terrain clip standards (for example OpenLOCK) is not implemented and no
third-party clip geometry is used. Check each standard's license before any
compatibility work.

## Engine import verification
Exports are verified by re-importing into Blender (names, triangle counts,
per-axis size). Still to do: automated import tests inside Unity, Unreal and
Godot, in particular Unity UCX_ handling (needs an asset postprocessor) and
the Unreal unit conversion of meter-based FBX files.

## Marketplaces
Fab and itch.io listing and package requirements have not been verified;
the zips follow a neutral layout (models, previews, README, LICENSE,
manifest).

## Materials
Engines receive constant base color and roughness per material slot;
procedural detail (noise bump) is Blender-only. Baking the procedural
materials to textures (texture_provenance = "generator") is a candidate for
v0.2.

## Cross-version determinism
Exports are byte-identical within one Blender version. Across versions the
glTF exporter embeds its version string and decimation can differ; that is
expected and not tested.
