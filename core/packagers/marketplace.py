# SPDX-License-Identifier: GPL-3.0-or-later
"""Marketplace checks run while packaging. Only requirements verified
against the marketplaces' own documentation are enforced (checked
2026-09-25):

Fab, "Asset File Format and Structure Requirements"
https://dev.epicgames.com/documentation/en-us/fab/asset-file-format-and-structure-requirements-in-fab
  - media gallery images: at least 1920 x 1080, under 3 MB each, JPEG or
    PNG, under 25 MB in total
  - asset file paths of 140 characters or less (stated for UEFN projects;
    applied here as a conservative limit)

itch.io, "Creator FAQ" https://itch.io/docs/creators/faq
  - files are delivered exactly as uploaded, no format restrictions
  - soft limit of 10 files per project page (one zip per profile fits)
"""

import os
import struct

MIN_W, MIN_H = 1920, 1080
MAX_IMAGE_BYTES = 3 * 1024 * 1024
MAX_GALLERY_BYTES = 25 * 1024 * 1024
MAX_PATH = 140


def png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def check(entries):
    """entries: {archive name: source path or bytes}. Returns problems."""
    problems = []
    gallery = 0
    for name, src in sorted(entries.items()):
        if len(name) > MAX_PATH:
            problems.append(f"path longer than {MAX_PATH} characters: {name}")
        if name.lower().endswith(".png") and not isinstance(src, (bytes, bytearray)):
            size = png_size(src)
            nbytes = os.path.getsize(src)
            gallery += nbytes
            if size is None or size[0] < MIN_W or size[1] < MIN_H:
                problems.append(f"preview {name} is {size}, Fab needs at least {MIN_W} x {MIN_H}")
            if nbytes >= MAX_IMAGE_BYTES:
                problems.append(f"preview {name} is {nbytes} bytes, Fab needs under 3 MB")
    if gallery >= MAX_GALLERY_BYTES:
        problems.append(f"previews total {gallery} bytes, Fab needs under 25 MB")
    return problems
