# SPDX-License-Identifier: GPL-3.0-or-later
"""Legal checks.

LEGAL.BRAND       brand blocklist scan over object, mesh, material, image,
                  node and collection names, custom properties, contract
                  metadata and export file names
LEGAL.LICENSE     the kit ships the license file its contract declares
LEGAL.PROVENANCE  texture_provenance = "generator" means no external
                  images, fonts or HDRIs exist in the scene
LEGAL.AI_CONTENT  generators are deterministic code: ai_content = false
"""

import os
import re
import unicodedata

import bpy

from .report import verdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOCKLIST = os.path.join(REPO_ROOT, "data", "brand_blocklist.txt")
ALLOWLIST = os.path.join(REPO_ROOT, "data", "brand_allowlist.txt")


def _read_list(path):
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip().lower()
            if line:
                out.append(line)
    return out


# Latin lookalikes from Cyrillic and Greek that NFKC leaves alone, so "Nike"
# spelled with a Cyrillic i still reads as "nike". Code points, not literal
# characters, because source files are ASCII only.
_CYRILLIC = {
    0x0430: "a", 0x0435: "e", 0x043E: "o", 0x0440: "p", 0x0441: "c", 0x0443: "y", 0x0445: "x",
    0x0456: "i", 0x0458: "j", 0x0455: "s", 0x0501: "d", 0x04CF: "l", 0x043A: "k", 0x043C: "m",
    0x043D: "h", 0x0442: "t", 0x0432: "b",
    0x0410: "A", 0x0412: "B", 0x0415: "E", 0x041A: "K", 0x041C: "M", 0x041D: "H", 0x041E: "O",
    0x0420: "P", 0x0421: "C", 0x0422: "T", 0x0425: "X", 0x0406: "I", 0x0408: "J", 0x0405: "S",
}
_GREEK = {
    0x03B1: "a", 0x03BF: "o", 0x03BD: "v", 0x03C1: "p", 0x03C4: "t", 0x03B9: "i", 0x03BA: "k",
    0x0391: "A", 0x0392: "B", 0x0395: "E", 0x0396: "Z", 0x0397: "H", 0x0399: "I", 0x039A: "K",
    0x039C: "M", 0x039D: "N", 0x039F: "O", 0x03A1: "P", 0x03A4: "T", 0x03A5: "Y", 0x03A7: "X",
}
CONFUSABLES = {**_CYRILLIC, **_GREEK}


def normalize(text):
    """Fold full-width forms (NFKC), Cyrillic and Greek lookalike letters and
    accents to plain letters, so full-width "nike", "Nike" with a Cyrillic i
    and "Citroen" with a diaeresis all read as their ASCII spelling."""
    text = unicodedata.normalize("NFKC", str(text)).translate(CONFUSABLES)
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _split_word(word):
    word = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", word)   # BMWLogo -> BMW Logo
    word = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", word)      # McDonalds -> Mc Donalds
    word = re.sub(r"([A-Za-z])([0-9])", r"\1 \2", word)      # Ford01 -> Ford 01
    word = re.sub(r"([0-9])([A-Za-z])", r"\1 \2", word)
    return word.lower().split()


def camel_parts(text):
    """Sub-tokens of each separate word: "McDonaldsSign lamp" gives
    [["mc", "donalds", "sign"], ["lamp"]]. Joining is only allowed inside one
    word, so "for d" in code never reads as "ford"."""
    return [_split_word(word) for word in re.split(r"[^A-Za-z0-9]+", normalize(text)) if word]


def tokens(text):
    return [t for parts in camel_parts(text) for t in parts]


def _find(seq, sub):
    n = len(sub)
    return [i for i in range(len(seq) - n + 1) if seq[i:i + n] == sub]


class BrandScanner:
    """Allowlist entries are phrases: a mark is not flagged where it only
    occurs inside an allowlisted phrase ("tesla coil"), so the same text
    can still be flagged for the mark elsewhere ("tesla_coil_tesla_logo")."""

    def __init__(self, blocklist=BLOCKLIST, allowlist=ALLOWLIST):
        self.marks = []
        for entry in _read_list(blocklist):
            parts = tokens(entry)
            if parts:
                self.marks.append((entry, parts, "".join(parts)))
        self.allowed = [p for p in (tokens(entry) for entry in _read_list(allowlist)) if p]
        self.longest = max((len(joined) for _e, _p, joined in self.marks), default=0)

    def hits(self, text):
        words = camel_parts(text)
        toks = [t for parts in words for t in parts]
        free = [True] * len(toks)
        for phrase in self.allowed:
            for i in _find(toks, phrase):
                free[i:i + len(phrase)] = [False] * len(phrase)

        def clear(i, j):
            return all(free[i:j])

        # Runs of two or more sub-tokens inside one word, joined: "Coca" +
        # "Cola" in "CocaColaCrate" reads as "cocacola". Runs longer than the
        # longest mark cannot match, which keeps long hashes cheap.
        joins = set()
        start = 0
        for parts in words:
            end = start + len(parts)
            for i in range(start, end):
                joined = toks[i]
                for j in range(i + 1, end):
                    joined += toks[j]
                    if len(joined) > self.longest or not (free[i] and free[j]):
                        break
                    joins.add(joined)
            start = end

        found = []
        for entry, parts, joined in self.marks:
            if joined in joins or any(t == joined and ok_ for t, ok_ in zip(toks, free)) \
                    or any(clear(i, i + len(parts)) for i in _find(toks, parts)):
                found.append(entry)
        return found

    def scan(self, surfaces):
        """surfaces: iterable of (where, text). Returns list of hit dicts."""
        out = []
        for where, text in surfaces:
            for mark in self.hits(text):
                out.append({"where": where, "text": str(text), "mark": mark})
        return out


def scene_surfaces():
    for obj in bpy.data.objects:
        yield f"object:{obj.name}", obj.name
        for key in obj.keys():
            yield f"object:{obj.name}:prop", key
            if isinstance(obj[key], str):
                yield f"object:{obj.name}:prop:{key}", obj[key]
    for mesh in bpy.data.meshes:
        yield f"mesh:{mesh.name}", mesh.name
    for mat in bpy.data.materials:
        yield f"material:{mat.name}", mat.name
        if mat.node_tree:
            for node in mat.node_tree.nodes:
                yield f"material:{mat.name}:node", node.name
                if node.label:
                    yield f"material:{mat.name}:node_label", node.label
    for img in bpy.data.images:
        yield f"image:{img.name}", img.name
        if img.filepath:
            yield f"image:{img.name}:path", img.filepath
    for tex in bpy.data.textures:
        yield f"texture:{tex.name}", tex.name
    for coll in bpy.data.collections:
        yield f"collection:{coll.name}", coll.name
    for scene in bpy.data.scenes:
        for key in scene.keys():
            yield f"scene:{scene.name}:prop", key


def contract_surfaces(contract):
    kit = contract["kit"]
    for key in ("id", "name", "prefix", "generator", "description"):
        if key in kit:
            yield f"contract:kit.{key}", kit[key]
    for piece in contract["pieces"]:
        yield "contract:pieces", piece["id"]
    for variant in contract["style"]["variants"]:
        yield "contract:variants", variant
    for entry in contract["materials"]["palette"]:
        yield "contract:palette", entry["slot"]


def check_brand(contract, extra_surfaces=()):
    scanner = BrandScanner()
    found = scanner.scan(list(scene_surfaces()) + list(contract_surfaces(contract)) + list(extra_surfaces))
    return verdict("LEGAL.BRAND", not found, "no blocklisted brand marks in names or metadata",
                   hits=found[:50], hit_count=len(found), marks=len(scanner.marks))


def check_license(contract):
    legal = contract["legal"]
    rel = legal.get("license_file") if legal["license"] == "CC0-1.0" else legal.get("eula_file")
    path = os.path.join(contract["_dir"], rel) if rel else None
    problems = []
    if not path or not os.path.isfile(path):
        problems.append(f"license file missing: {path}")
    elif legal["license"] == "CC0-1.0":
        with open(path, encoding="utf-8") as fh:
            if "CC0 1.0 Universal" not in fh.read():
                problems.append(f"{path} is not the CC0 1.0 Universal text")
    return verdict("LEGAL.LICENSE", not problems, f"license file for {legal['license']} ships with the kit",
                   path=path, problems=problems)


def check_provenance(contract):
    legal = contract["legal"]
    external = []
    if legal["texture_provenance"] == "generator":
        for img in bpy.data.images:
            if img.get("garu_generated"):
                continue  # baked from the kit's own procedural materials (core/bake.py)
            if img.source in {"FILE", "SEQUENCE", "MOVIE"} or img.filepath or img.packed_file:
                external.append(f"image:{img.name}")
        for font in bpy.data.fonts:
            if font.filepath and font.filepath != "<builtin>":
                external.append(f"font:{font.name}")
        for world in bpy.data.worlds:
            if world.node_tree and any(n.type == "TEX_ENVIRONMENT" for n in world.node_tree.nodes):
                external.append(f"world:{world.name}")
    return verdict("LEGAL.PROVENANCE", not external,
                   f"texture provenance '{legal['texture_provenance']}': no external images, fonts or HDRIs",
                   external=external)


def check_ai(contract):
    return verdict("LEGAL.AI_CONTENT", contract["legal"]["ai_content"] is False,
                   "generators are deterministic code; no AI-generated content")


def run(contract, extra_surfaces=()):
    return [check_brand(contract, extra_surfaces), check_license(contract),
            check_provenance(contract), check_ai(contract)]
