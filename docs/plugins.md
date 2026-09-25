# Generator plug-ins

Paid kits live in a separate private repository. They plug into this core
without any change here.

## Layout

A generator is a directory:

```
my-kit/
  generator.toml   manifest
  kit.toml         kit contract (see contract.md)
  generator.py     the module
  LICENSE-...      the file named by legal.license_file or legal.eula_file
```

`generator.toml`:

```toml
id = "my-kit"            # must equal kit.generator in kit.toml
version = "1.0.0"
api_version = 1          # must equal core.API_VERSION
module = "generator.py"
kit = "kit.toml"
license = "commercial-eula"   # or CC0-1.0
```

## Discovery

`core/generators/registry.py` scans, in order:

1. `kits/` in this repository
2. every entry of `GARU_GENERATOR_PATH` (separated by `;` on Windows, `:` elsewhere)
3. every `--generator-path` given to `core/cli.py` or `-GeneratorPath` given to the scripts

A path is either a generator directory or a directory of generator
directories. The same id in two places is an error, and so is an
`api_version` mismatch. Modules are loaded by file path under a private
namespace; the core never imports a generator by name.

```powershell
$env:GARU_GENERATOR_PATH = "D:\private-kits\generators"
pwsh scripts/build-kit.ps1 -Kit my-kit -Profiles working -Seed 1
```

## Module API (api_version 1)

```python
def build(contract, seed, piece_ids) -> list[bpy.types.Object]: ...
def build_colliders(contract, obj) -> list[bpy.types.Object]: ...   # optional
```

- `contract` is the kit contract resolved for one profile, frozen.
  `contract["profile"]["kind"]` is `mesh` or `print`.
- Build one LOD0 mesh object per (piece, variant) in cell space, origin per
  `pivot_rule`, transforms applied, tagged with `api.tag(obj, piece, variant,
  api.ROLE_MESH)` and named with `api.piece_name(...)`.
- Use palette materials only: `api.material(contract, slot)`.
- All randomness must come from `api.rng_for(seed, ...)`. Never use global
  `random`, time or uuids. Draw random numbers in a deterministic order (for
  example one draw per stone, or after sorting vertices by position), because
  bmesh operator output order is not stable across runs.

The core then owns everything else, identically for every generator:
triangulation and canonical element order, LODs, colliders (unless
`build_colliders` is provided), the lightmap UV channel, scaling to profile
units, print bases and sockets, validation, export, previews and packaging.

`tests/fixtures/external_gen/demo-external` is a complete out-of-tree
example; `tests/test_registry.py` and `tests/test_external_pipeline.py`
prove it registers and runs through the full pipeline with no core edits.
