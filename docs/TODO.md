# Open TODOs

## Roblox (profile: roblox, stub)
Verified on 2026-09-25 against create.roblox.com and recorded in
`profiles/roblox/profile.toml` with source URLs:
- 20,000 triangles per mesh (general specifications)
- textures up to 4096 x 4096 (texture specifications)
- one material per mesh (texture specifications): the sampler's two slots
  (stone, mortar) must be merged by a Roblox exporter
- 1 stud = 28 cm (units), so one 2.0 m cell is 7.142857 studs

The exporter exists (experimental, `core/roblox.py`): one watertight FBX per
piece variant, one material with a per-piece baked texture set, textures
embedded, verified limits enforced.

Still open:
- import check in Roblox Studio (Scale Unit = Stud); not installed here
- maximum mesh size in studs is not stated on the pages checked; it stays
  unverified and unapplied
- the Roblox docs ask for quads where possible; the pipeline exports
  triangles (allowed, but worth revisiting for Roblox)

## FiveM via Sollumz (profile: fivem_sollumz, experimental)
Headless feasibility is established. On 2026-09-25, with Blender 4.5.14 and
Sollumz at the pinned commit, `profiles/fivem_sollumz/probe.py` built the
sampler wall, converted it to a drawable, exported it under
`blender --background` and re-imported it at 2.0 x 0.5 x 4.0 m. The manual
workflow `.github/workflows/fivem-sollumz.yml` repeats this on Linux.

The exporter now exists (`core/fivem.py`, experimental): drawables with
High/Medium/Low LODs and LOD distances, normal.sps materials naming the
baked textures, embedded BVH collision, CodeWalker XML for gen8 and gen9,
Sollumz re-import verification, a streamed-memory estimate, and
byte-identical rebuilds (`tests/test_fivem.py`, verified 2026-09-25 on
Blender 4.5.14).

Local setup (what the workflow does):
1. `git archive` the pinned Sollumz commit (a plain checkout keeps a
   `$Format` version placeholder that Blender rejects) into
   `<user>/extensions/user_default/sollumz_dev`.
2. `pip install --target <site> --require-hashes` the szio version and hash
   pinned in the profile.
3. Run Blender 4.5 with `BLENDER_USER_RESOURCES=<user>` and
   `GARU_SZIO_SITE=<site>`.

Still open:
- in-game testing in FiveM, and building the .ytd from the shipped PNGs
- binary `.ydr` needs PyMateria, which is proprietary (CFX license) and must
  not be used or shipped here; conversion is left to the user's CodeWalker
- archetype (`.ytyp`) output and `target_builds`
- the memory estimate covers geometry only, not textures
- Sollumz is GPL-3.0-or-later and is never vendored here

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
Done: palette materials are baked to seamless tiling textures (base color,
roughness, tangent-space normal, 1024 px) by `core/bake.py` and shipped with
every game profile; `tests/test_bake.py` checks seamlessness, non-flatness
and reproducibility. Normal maps are OpenGL convention (+Y); Unreal users
flip the green channel on import (or enable "Flip Green Channel").
Open: stone color variation is per tile, not per stone (no per-stone tint).

## Cross-version determinism
Exports are byte-identical within one Blender version. Across versions the
glTF exporter embeds its version string and decimation can differ; that is
expected and not tested.
