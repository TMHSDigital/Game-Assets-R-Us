# SPDX-License-Identifier: GPL-3.0-or-later
"""Reproducible zip files: sorted entries, fixed timestamps, fixed
permissions and host system, so identical inputs give identical bytes.

DEFLATE output also depends on the zlib build Python links against (some
builds use zlib-ng), so the byte-identical guarantee holds for one zlib
runtime; settings() is recorded in the packaged manifest."""

import os
import zipfile
import zlib

FIXED_TIME = (1980, 1, 1, 0, 0, 0)
COMPRESS_LEVEL = 9


def settings():
    """What the zip bytes depend on besides the entries themselves."""
    return {"compression": "deflate", "level": COMPRESS_LEVEL, "zlib": zlib.ZLIB_RUNTIME_VERSION}


def write_zip(path, entries):
    """entries: {archive name: source path or bytes}."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w") as zf:
        for name in sorted(entries):
            src = entries[name]
            if isinstance(src, (bytes, bytearray)):
                data = bytes(src)
            else:
                with open(src, "rb") as fh:
                    data = fh.read()
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3  # unix, regardless of the build host
            info.external_attr = 0o644 << 16
            zf.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=COMPRESS_LEVEL)
    os.replace(tmp, path)
    return path
