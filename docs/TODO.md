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

## FiveM via Sollumz (profile: fivem_sollumz, experimental)
Headless feasibility is established. On 2026-09-25, with Blender 4.5.14 and
Sollumz at the pinned commit, `profiles/fivem_sollumz/probe.py` built the
sampler wall, converted it to a drawable, exported it under
`blender --background` and re-imported it at 2.0 x 0.5 x 4.0 m. The manual
workflow `.github/workflows/fivem-sollumz.yml` repeats this on Linux.

What the probe showed a real exporter must handle:
- Install Sollumz from `git archive` of the pinned commit (a plain checkout
  keeps a `$Format` placeholder that Blender rejects as a version), plus the
  hash-pinned `szio` wheel Sollumz requires (pinned in the profile).
- Assign Sollumz shader materials directly: its material converter crashes
  on our procedural bump node tree.
- Name UV maps `UVMap 0`, `UVMap 1` and add a `Color 1` color attribute, as
  Sollumz shaders expect.
- Output is CodeWalker XML (`.ydr.xml`, in `gen8/` and `gen9/`). Binary
  `.ydr` needs PyMateria, which is proprietary (CFX license) and must not be
  used or shipped here; converting XML to binary is left to the user's
  CodeWalker.
- Still open: embedded collision, LOD distances, archetype (`.ytyp`)
  output, the 16 MiB streamed memory estimate, and `target_builds`.
- Sollumz is GPL-3.0-or-later and is never vendored here.

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
