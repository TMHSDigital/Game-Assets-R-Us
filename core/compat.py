# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender 4.5 LTS / 5.x compatibility shims.

eevee_engine_id is adapted from the author's Blender-Developer-Tools
(snippets/version-branch-skeleton.py), relicensed here under
GPL-3.0-or-later.
"""

import bpy


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def operator_kwargs(op, wanted):
    """Split kwargs into (accepted, dropped) for an operator.

    Dropped keys are returned, never silently discarded, so callers can
    record them in the export report.
    """
    props = {p.identifier for p in op.get_rna_type().properties}
    accepted = {k: v for k, v in wanted.items() if k in props}
    dropped = sorted(k for k in wanted if k not in props)
    return accepted, dropped
