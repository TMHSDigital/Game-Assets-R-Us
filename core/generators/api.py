# SPDX-License-Identifier: GPL-3.0-or-later
"""The generator plug-in contract (API_VERSION 1).

A generator is a directory with a `generator.toml` manifest, a kit contract
(`kit.toml`) and a Python module exposing:

    build(contract, seed, piece_ids) -> list[bpy.types.Object]

    contract   frozen mapping: the kit contract resolved for one profile.
               contract["profile"]["kind"] is "mesh" or "print".
    seed       int. All randomness must come from rng_for(seed, ...).
    piece_ids  piece ids to build (subset of contract["pieces"]).

Each returned object is one LOD0 mesh for one (piece, variant), built in
cell space (1 Blender unit = 1 grid cell), with transforms applied, origin
per the contract pivot rule, and these custom properties set:

    garu_piece    piece id
    garu_variant  variant id
    garu_role     "mesh"

Palette materials already exist when build() runs; fetch them with
material(contract, slot) and never create materials of your own.

Optional module hooks (the core supplies defaults when absent):

    build_colliders(contract, obj) -> list[bpy.types.Object]
        Convex collider parts for one LOD0 object, garu_role = "collider".
        Default: one convex hull of the LOD0 mesh.

The core then adds UVs it owns (lightmap), LODs, colliders, profile scale,
print bases and sockets, so every generator gets identical pipeline rules.
"""

import hashlib
import random

ROLE_MESH = "mesh"
ROLE_LOD = "lod"
ROLE_COLLIDER = "collider"
ROLE_CLIP = "clip"

PROP_PIECE = "garu_piece"
PROP_VARIANT = "garu_variant"
PROP_ROLE = "garu_role"
PROP_LOD = "garu_lod"
PROP_INDEX = "garu_index"


def hash_stable(*parts):
    """Process-independent 64-bit hash (Python's hash() is salted per run)."""
    digest = hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "little")


def rng_for(seed, *parts):
    """The only sanctioned randomness source for generators."""
    return random.Random(hash_stable(seed, *parts))


def tag(obj, piece, variant, role, lod=0, index=0):
    obj[PROP_PIECE] = piece
    obj[PROP_VARIANT] = variant
    obj[PROP_ROLE] = role
    obj[PROP_LOD] = lod
    obj[PROP_INDEX] = index
    return obj


def piece_name(contract, piece, variant):
    return contract["style"]["naming_pattern"].format(
        prefix=contract["kit"]["prefix"], kit=contract["kit"]["id"],
        piece=piece, variant=variant)


def lod_name(contract, base, n):
    return contract["style"]["lod_pattern"].format(name=base, n=n)


def collider_name(contract, base, index):
    return contract["style"]["collider_pattern"].format(name=base, index=index)


def pieces_by_id(contract):
    return {p["id"]: p for p in contract["pieces"]}


def material_name(contract, slot):
    return f"M_{contract['kit']['prefix']}_{slot}"


def material(contract, slot):
    """Palette material for a slot. The core creates every palette material
    before build() is called; a missing slot is a generator bug."""
    import bpy
    mat = bpy.data.materials.get(material_name(contract, slot))
    if mat is None:
        raise KeyError(f"material slot '{slot}' is not in the kit palette")
    return mat
