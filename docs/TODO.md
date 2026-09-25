# Open TODOs

## Roblox (profile: roblox, stub)
Verified on 2026-09-25 against create.roblox.com and recorded in
`profiles/roblox/profile.toml` with source URLs:
- 20,000 triangles per mesh (general specifications)
- textures up to 4096 x 4096 (texture specifications)
- one material per mesh (texture specifications): the sampler's two slots
  (stone, mortar) must be merged by a Roblox exporter
- 1 stud = 28 cm (units), so one 2.0 m cell is 7.142857 studs

Still open:
- maximum mesh size in studs is not stated on the pages checked; it stays
  unverified and unapplied
- the Roblox docs ask for quads where possible; the pipeline exports
  triangles (allowed, but worth revisiting for Roblox)
- the exporter itself (FBX, Apply Scalings "FBX Unit Scale" per the Roblox
  export settings page), plus an import check in Studio

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
terrain clip standards is not implemented and no third-party clip geometry
is used.

License check, OpenLOCK (2026-09-25, Printable Scenery's own page,
https://www.printablescenery.com/2020/02/10/the-openlock-license/): free
for home use; selling designs that use it requires an OpenLOCK license,
which is free, never expires, is obtained by contacting Printable Scenery
(https://www.printablescenery.com/helpdesk/), and requires displaying the
"OpenLOCK compatible" logo and linking back to Printable Scenery. Adding
OpenLOCK compatibility to paid kits is therefore a business decision (apply
for the license, accept the logo and link terms) before any geometry work.
Other clip standards have not been checked.

## Engine import verification
Exports are verified by re-importing into Blender (names, triangle counts,
per-axis size). Godot is also verified inside the engine:
`tests/test_godot_import.py` imports all 45 godot-profile GLB files into a
headless Godot 4 project (Godot 4.5.2 on 2026-09-25) and checks Y-up sizes,
names and that every `-convcolonly` collider becomes a convex physics shape.
It runs when Godot is available (`scripts/test.ps1 -Godot <path>` or
GARU_GODOT) and is skipped in CI.

Still to do: import tests inside Unity and Unreal (neither is installed
here), in particular Unity UCX_ handling (needs an asset postprocessor) and
the Unreal unit conversion of meter-based FBX files.

## Marketplaces
Checked 2026-09-25 and enforced by `core/packagers/marketplace.py`
(packaging fails if they are not met):
- Fab (Asset File Format and Structure Requirements): gallery images at
  least 1920 x 1080, under 3 MB each, JPEG or PNG, under 25 MB in total;
  FBX and GLB are accepted exchange formats; listings must state which LODs
  are included (the generated README does); modular assets must have
  assembly-friendly pivots and snap on a grid (CORE.PIVOT, CORE.GRID.*, and
  the demo room check that). The 140-character path limit (stated for UEFN
  projects) is applied as a conservative limit.
- itch.io (Creator FAQ): files are delivered exactly as uploaded, no format
  restrictions; soft limit of 10 files per page (one zip per profile fits).

Still open: Fab's full technical requirements page on support.fab.com could
not be fetched (TLS certificate error) and should be read before a Fab
submission; the Fab 3D viewer preview (under 500 MB) and gallery video are
not produced; itch.io's per-file size limit is not stated in its FAQ.

## Materials
Engines receive constant base color and roughness per material slot;
procedural detail (noise bump) is Blender-only. Baking the procedural
materials to textures (texture_provenance = "generator") is a candidate for
v0.2.

## Cross-version determinism
Exports are byte-identical within one Blender version. Across versions the
glTF exporter embeds its version string and decimation can differ; that is
expected and not tested.
