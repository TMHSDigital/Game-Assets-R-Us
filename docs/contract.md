# Kit contract

Every kit has a `kit.toml` contract. It is validated in two layers:

1. `core/contract/base.schema.json` (JSON Schema draft 2020-12) validates
   everything except the `[profiles.*]` tables, followed by semantic checks
   JSON Schema cannot express (strictly decreasing LOD budgets, unique piece
   ids, a `[print]` block when `stl_print` is exported, a license file for
   CC0 kits and an EULA file for commercial kits, both inside the kit
   directory, `ai_content = false`, `min_px_per_cell <= max_px_per_cell`,
   `[profiles.<name>]` only for profiles in `exports.profiles`, safe name
   templates).
2. For each export profile, `profiles/<name>/profile.toml` (defaults) is
   merged with the kit's `[profiles.<name>]` overrides and validated against
   `profiles/<name>/schema.json`.

Validation uses `core/contract/schema_lite.py`, a standard-library subset of
JSON Schema (Blender does not bundle `jsonschema`). Unsupported keywords are
rejected when a schema loads, so a schema never silently checks less than it
says. The schema files are standard JSON Schema and work with any validator.

## Units

The grid is unit-agnostic. Everything in the contract is in abstract cells.
Each profile sets `cell_size` and `units`:

| Profile | cell_size | units |
|---|---|---|
| unity, unreal, godot, gltf_web | 2.0 | m |
| stl_print | 25.4 | mm |
| roblox (experimental) | 7.142857 | studs (2.0 m at 28 cm per stud) |

Generators build in cell space (1 Blender unit = 1 cell). The core scales
every mesh once into profile units, so one validation rule covers all units.

## Blocks

| Block | Fields |
|---|---|
| `[kit]` | `id`, `name`, `version`, `prefix`, `generator` (registry id), `default_seed`, `description` |
| `[grid]` | `height_cells`, `wall_thickness_cells`, `snap_tolerance_cells` |
| `[style]` | `bevel_width_cells`, `bevel_segments`, masonry sizes, `naming_pattern`, `lod_pattern`, `collider_pattern`, `pivot_rule` (`base_min_corner` or `base_center`), `variants` |
| `[materials]` | `max_slots_per_piece`, `palette` (procedural only: `slot`, `base_color`, `base_color_2`, `roughness`, `noise_scale`) |
| `[uv]` | `tiling_channel`, `lightmap_channel`, `tiling_scale_per_cell`, `lightmap_margin` |
| `[texel_density]` | `texture_size`, `min_px_per_cell`, `max_px_per_cell`, `coverage` |
| `[textures]` | `bake`, `size` (must equal `texel_density.texture_size`), `maps` (`base_color`, `roughness`, `normal`) |
| `[collider]` | `type` (`convex`, `box`, `none`), `max_faces_per_part`, `max_parts` |
| `[[pieces]]` | `id`, `footprint_cells`, `height_cells`, `lod_tris` (per LOD budget), `seams`, `seam_profile`, `print_base_cells` |
| `[exports]` | `profiles` |
| `[legal]` | `license` (`CC0-1.0` or `commercial-eula`), `license_file` or `eula_file`, `texture_provenance` (`generator` or an https URL), `brand_check` (must be true), `ai_content` (must be false) |
| `[print]` | `manifold`, `min_wall_mm`, `max_overhang_deg`, `max_overhang_area_mm2`, `max_bridge_mm`, `base_height_mm`, `max_bbox_mm`, `print_orientation`, `presupport_required`, `layer_height_mm`, `clip_system` |
| `[print.clip_system]` | `type` (`none` or `garu_dogbone_v1`); for the dogbone: `tolerance_mm`, neck and head sizes, `height_mm`, `roof_mm`, `positions` |
| `[profiles.<name>]` | per-kit overrides of the profile defaults |

See `kits/stone-dungeon-wall-sampler/kit.toml` for a complete example.

## Name templates

`naming_pattern`, `lod_pattern` and `collider_pattern` (and a profile's
`collider_pattern`) are Python `str.format` templates whose results become
object and file names. They may use only these placeholders, with no
attribute access or `!` conversions; literal text is limited to letters,
digits, `_` and `-`:

| Template | Placeholders |
|---|---|
| `naming_pattern` | `{prefix}`, `{kit}`, `{piece}` (required), `{variant}` |
| `lod_pattern` | `{name}`, `{n}` (LOD number) |
| `collider_pattern` | `{name}`, `{index}` (part number) |

Integer placeholders accept a width spec such as `{index:02d}`.

## Seams

`seams` lists the piece faces that meet neighbours (`x0`, `x1`, `y0`, `y1`).
All seams in one `seam_profile` group must have the same cross-section: the
validator compares every seam against the group's reference profile (first
piece in contract order, first variant, first seam). This is what makes a
cracked wall snap to a clean corner.

## Check IDs

| ID | Rule |
|---|---|
| CORE.GRID.SNAP | object origin on the grid |
| CORE.GRID.DIMS | footprint exact; height exact for the first variant, never above for others |
| CORE.GRID.SEAM | seam cross-sections match the group reference |
| CORE.PIVOT | origin per `pivot_rule` |
| CORE.XFORM | rotation and scale applied |
| CORE.NAMING | contract naming, LOD and collider patterns |
| CORE.MESH.MANIFOLD | closed, manifold, outward normals |
| CORE.MESH.LOOSE | no loose vertices or edges, no zero-area faces |
| CORE.MESH.SELFX | no self-intersecting faces |
| CORE.UV.PRESENT | both UV channels on every LOD |
| CORE.UV.OVERLAP | lightmap channel does not overlap (tiling channel overlaps by design) |
| CORE.UV.TEXEL | texel density within range over `coverage` of the area |
| CORE.LOD.CHAIN | all LODs present, triangle counts strictly decreasing |
| CORE.LOD.BUDGET | every LOD within its budget |
| CORE.COLLIDER | convex parts, part count and face caps |
| CORE.MATERIAL.SLOTS | slot count and palette materials only |
| STL.WATERTIGHT, STL.NONMANIFOLD, STL.SELFX | printable solid |
| STL.WALL.MIN | minimum wall thickness (BVH rays between opposed surfaces) |
| STL.OVERHANG | overhang histogram; steep faces only as short flat bridges |
| STL.BBOX | fits the build plate, rests on z = 0 |
| STL.SOCKET | pockets open, walled and roofed; clip is the pocket minus tolerance |
| LEGAL.BRAND, LEGAL.LICENSE, LEGAL.PROVENANCE, LEGAL.AI_CONTENT | legal checks |

`--fix` applies only `FIX.XFORM`, `FIX.ORIGIN` and `FIX.RENAME`. Each fix is
recorded in the piece report with before and after values, and every check
runs again afterwards.
