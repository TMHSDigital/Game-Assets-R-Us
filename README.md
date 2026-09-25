# Game-Assets-R-Us

Grid-exact, style-consistent modular asset kits, produced by deterministic
headless Blender (bpy) generators, verified against a machine-checkable kit
contract, and exported to game engines, the web, and 3D-printable STL terrain.

This repository is the public core of that pipeline:

| Part | Path | What it does |
|---|---|---|
| Kit contract | `core/contract/` | TOML contract plus JSON Schema (base schema and per-profile overlays) |
| Generator plug-in seam | `core/generators/` | Discovers generators from configured paths, including external repos |
| Validators | `core/validators/` | Core mesh, STL print and legal checks, one JSON report per piece |
| Export profiles | `profiles/` | unity, unreal, godot, gltf_web, stl_print; roblox and fivem_sollumz experimental |
| Packagers | `core/packagers/` | Deterministic zips for itch.io / Fab style game packs and STL packs |
| Scripts | `scripts/` | PowerShell entry points: build, validate, clean, test |
| CI | `.github/workflows/` | Headless Blender on ubuntu-latest, 5.2 LTS and 4.5 LTS |
| Sampler kit | `kits/stone-dungeon-wall-sampler/` | A small CC0 kit that proves the whole pipeline end to end |

## Quick start

Requires Blender 5.2 LTS or 4.5 LTS. Only Blender's bundled Python and its
standard library are used; there is nothing to pip install.

```powershell
$env:GARU_BLENDER = "C:\path\to\blender.exe"
pwsh scripts/build-kit.ps1 -Kit stone-dungeon-wall-sampler -Profiles unity,unreal,godot,gltf_web,stl_print -Seed 1337
pwsh scripts/test.ps1
```

Outputs land in `build/` (scenes, reports, previews) and `dist/<profile>/`
(packaged zips). Both are gitignored.

See `docs/contract.md`, `docs/plugins.md`, `docs/profiles.md` and
`docs/print.md` for details, and `docs/TODO.md` for open items.

## Licensing

This repository uses two licenses, split by what the file is:

- **Code** (everything under `core/`, `profiles/`, `scripts/`, `tests/`,
  `kits/*/generator.py`, CI workflows): **GPL-3.0-or-later**. See `LICENSE`.
  Every source file carries an `SPDX-License-Identifier` header.
- **Generated sampler assets** (the meshes, previews and packages produced by
  `kits/stone-dungeon-wall-sampler`): **CC0-1.0**. See
  `kits/stone-dungeon-wall-sampler/assets/LICENSE-CC0` and
  `LICENSES/CC0-1.0.txt`.

Assets produced by the sampler generator are dedicated to the public domain
under CC0-1.0. GPL-3.0-or-later covers the generator code, not its output.

Some helpers in `core/geometry/` and `core/validators/` are adapted from the
author's own Blender-Developer-Tools repository and are relicensed here under
GPL-3.0-or-later by the same copyright holder. Each such file says so in its
header.

## Paid kits

Full kits and their generators are sold separately and are **not included**
in this repository. They live in a separate private repository and plug into
this core through the generator registry (`docs/plugins.md`) without any
changes to this repository.
