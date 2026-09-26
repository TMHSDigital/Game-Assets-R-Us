# 3D print output (stl_print)

At 25.4 mm per cell, each piece is unioned onto a base
(`print_base_cells`, `base_height_mm`) and exported as one binary STL in
millimeters, base down on z = 0. Pieces with seams sit on the base edge like
their game counterparts; pieces without seams are centered.

## Clip system: garu_dogbone_v1

This is this project's own parametric socket. It is not a copy of OpenLOCK
or of any other clip standard.

- A T-shaped pocket (neck `neck_width_mm` x `neck_length_mm`, head
  `head_width_mm` x `head_length_mm`) is cut up from the underside of the
  base, `height_mm` tall, at the midpoint of every perimeter cell edge.
  `roof_mm` of material stays above it.
- Two tiles side by side form a double-T slot. The clip is that slot shrunk
  by `tolerance_mm` on every mating face, printed separately
  (`SM_<prefix>_clip_dogbone.stl`).
- `STL.SOCKET` probes every pocket: open inside, material around it and
  above it, and checks the clip is exactly the pocket minus the tolerance.

Compatibility with existing clip standards is a TODO pending a license
check (docs/TODO.md).

## Checks

| Check | How |
|---|---|
| STL.WATERTIGHT / STL.NONMANIFOLD | no boundary edges, every edge has two faces wound the same way (no flipped faces), no bowtie vertices, positive volume |
| STL.SELFX | BVH overlap between faces that share no vertex |
| STL.WALL.MIN | one ray per triangle along the inward normal; a sample is a wall when the ray reaches an opposed surface (normals facing apart within 60 deg); fails below `min_wall_mm` |
| STL.OVERHANG | area histogram of downward faces by angle; faces steeper than `max_overhang_deg` pass only as flat bridges no wider than `max_bridge_mm`, or within `max_overhang_area_mm2` in total |
| STL.BBOX | fits `max_bbox_mm`, rests on z = 0 |
| STL.SOCKET | see above |

Each STL pack includes `print_settings.md`, generated from the contract and
the measured check results.
