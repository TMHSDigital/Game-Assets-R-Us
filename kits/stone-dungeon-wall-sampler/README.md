# Stone Dungeon Wall Sampler

A small, free modular dungeon kit that proves the Game-Assets-R-Us pipeline
end to end.

## License

The generated assets (meshes, previews and packaged files) are dedicated to
the public domain under **CC0 1.0 Universal**: see `assets/LICENSE-CC0`.
The generator code in this folder (`generator.py`) is GPL-3.0-or-later like
the rest of this repository.

## Pieces

| Piece | Footprint (cells) | Height (cells) | Seams |
|---|---|---|---|
| wall_straight | 1 x 0.25 | 2 | x0, x1 |
| corner_outer | 1 x 1 (L-shaped) | 2 | x1, y1 |
| doorway | 1 x 0.25 | 2 | x0, x1 |
| floor_2x2 | 2 x 2 | 0.1 | x0, x1, y0, y1 |
| pillar | 0.5 x 0.5 | 2 | none |

Each piece comes in three variants: `clean`, `cracked` (cracked and sunken
stones) and `ruined` (broken silhouette, more damage). Cracks and ruin never
touch the seams, so any variant snaps to any other.

Game profiles get LOD0 to LOD2 and convex colliders (split so doorways stay
walkable and corners hollow). The print profile gets a base with the
parametric dogbone socket, at 25.4 mm per cell.

## Style

One bevel language: a single 45 degree chamfer of 0.02 cells on every hard
edge except floor-contact edges. Staggered ashlar courses on a global grid,
so the pattern continues across neighbouring pieces. Procedural materials
only; no external textures, HDRIs or fonts.

## Build

```powershell
pwsh scripts/build-kit.ps1 -Kit stone-dungeon-wall-sampler -Profiles unity,unreal,godot,gltf_web,stl_print -Seed 1337
```
