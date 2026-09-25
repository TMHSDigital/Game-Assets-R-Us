# SPDX-License-Identifier: GPL-3.0-or-later
"""Generation stage: run a generator and add everything the core owns.

For every (piece, variant) the result is a PieceSet holding the LOD0 mesh,
its LODs and colliders (mesh profiles) or its printable tile (print
profile). All geometry is built in cell space and then scaled once into
profile units (1 Blender unit = 1 profile unit: meters or millimeters).
"""

from dataclasses import dataclass, field

import bpy
from mathutils import Matrix

from . import materials
from .generators import api
from .geometry import canonical
from .geometry import collider as collider_mod
from .geometry import lod as lod_mod
from .geometry import uv as uv_mod


class GenerationError(Exception):
    pass


@dataclass
class PieceSet:
    piece: str
    variant: str
    lod0: object
    lods: list = field(default_factory=list)
    colliders: list = field(default_factory=list)
    printable: object = None

    @property
    def name(self):
        return self.lod0.name

    def mesh_objects(self):
        return [self.lod0] + self.lods


@dataclass
class KitScene:
    contract: object
    seed: int
    sets: list
    clips: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    textures: list = field(default_factory=list)  # baked PNG paths (core/bake.py)


def reset_scene(unit_system="METRIC"):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = unit_system
    scene.unit_settings.scale_length = 1.0


def _check_build_output(contract, objects, piece_ids):
    expected = {(p, v) for p in piece_ids for v in contract["style"]["variants"]}
    seen = {}
    for obj in objects:
        if obj.type != "MESH":
            raise GenerationError(f"generator returned non-mesh object {obj.name}")
        missing = [k for k in (api.PROP_PIECE, api.PROP_VARIANT, api.PROP_ROLE) if k not in obj]
        if missing:
            raise GenerationError(f"{obj.name}: missing tags {missing}")
        key = (obj[api.PROP_PIECE], obj[api.PROP_VARIANT])
        if key in seen:
            raise GenerationError(f"{obj.name}: duplicate output for {key}, also {seen[key]}")
        seen[key] = obj.name
    if set(seen) != expected:
        raise GenerationError(f"generator output mismatch: missing {sorted(expected - set(seen))}, "
                              f"unexpected {sorted(set(seen) - expected)}")


def _scale_to_profile(objects, cell):
    m = Matrix.Scale(cell, 4)
    for obj in objects:
        obj.data.transform(m)
        obj.data.update()
        obj.location = obj.location * cell


def _default_collider(obj, kind, name):
    """One collider part for a LOD0 object: its convex hull, or for
    collider.type = "box" its world-space bounding box."""
    if kind == "box":
        mw = obj.matrix_world
        pts = [mw @ v.co for v in obj.data.vertices]
        lo = tuple(min(p[i] for p in pts) for i in range(3))
        hi = tuple(max(p[i] for p in pts) for i in range(3))
        return collider_mod.box(lo, hi, name, obj.users_collection[0] if obj.users_collection else None)
    return collider_mod.hull_of_object(obj, name)


def generate(contract, module, seed, piece_ids=None):
    """Run the generator and complete every piece set. Returns a KitScene."""
    reset_scene(contract["profile"].get("export", {}).get("scene_unit_system", "METRIC"))
    materials.ensure_palette(contract)
    piece_ids = list(piece_ids or [p["id"] for p in contract["pieces"]])
    objects = list(module.build(contract, seed, piece_ids))
    _check_build_output(contract, objects, piece_ids)
    pieces = api.pieces_by_id(contract)
    profile = contract["profile"]
    uvc = contract["uv"]

    sets = []
    for obj in sorted(objects, key=lambda o: o.name):
        canonical.finalize(obj.data)
        ps = PieceSet(obj[api.PROP_PIECE], obj[api.PROP_VARIANT], obj)
        if profile["kind"] == "mesh":
            budgets = pieces[ps.piece]["lod_tris"] if profile["lod_mode"] != "omit" else []
            for n, budget in enumerate(budgets[1:], start=1):
                lod = lod_mod.make_lod(obj, budget, api.lod_name(contract, obj.name, n))
                api.tag(lod, ps.piece, ps.variant, api.ROLE_LOD, lod=n)
                ps.lods.append(lod)
            if contract["collider"]["type"] != "none" and profile["collider_mode"] != "omit":
                if hasattr(module, "build_colliders"):
                    ps.colliders = list(module.build_colliders(contract, obj))
                else:
                    part = _default_collider(obj, contract["collider"]["type"],
                                             api.collider_name(contract, obj.name, 0))
                    api.tag(part, ps.piece, ps.variant, api.ROLE_COLLIDER)
                    ps.colliders = [part]
            canonical.canonicalize_objects(ps.lods + ps.colliders)
            for mesh_obj in ps.mesh_objects():
                if mesh_obj.data.uv_layers.get(uvc["tiling_channel"]) is None:
                    uv_mod.box_project(mesh_obj, uvc["tiling_channel"], uvc["tiling_scale_per_cell"])
                uv_mod.lightmap(mesh_obj, uvc["lightmap_channel"], uvc["tiling_channel"],
                                uvc.get("lightmap_margin", 0.01))
        sets.append(ps)

    everything = [o for ps in sets for o in ps.mesh_objects() + ps.colliders]
    _scale_to_profile(everything, profile["cell_size"])
    scene = KitScene(contract, seed, sets)

    if profile["kind"] == "print":
        from .print3d import make_printables
        make_printables(scene)
    return scene
