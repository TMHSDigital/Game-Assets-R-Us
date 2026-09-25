# SPDX-License-Identifier: GPL-3.0-or-later
"""Stub exporter entry for profiles with kind = "stub".

Running a stub profile validates its schema fields and exits with code 3
and a clear message. Nothing is exported, and no unverified platform limit
is ever applied.
"""

import importlib.util

EXIT_STUB = 3


def _sollumz_present(addon):
    try:
        return importlib.util.find_spec(addon) is not None
    except ModuleNotFoundError:
        return False


def run(contract):
    profile = contract["profile"]
    name = profile["name"]
    print(f"STUB profile '{name}' ({profile['status']}): schema fields are valid; no exporter is implemented.")
    if name == "fivem_sollumz":
        print(f"STUB   requires Blender {profile['blender_version']} and Sollumz "
              f"{profile['sollumz_repo']} at {profile['sollumz_commit']} (not vendored)")
        print(f"STUB   streamed memory warning threshold: {profile['streamed_memory_warn_mib']} MiB")
        print(f"STUB   Sollumz installed in this Blender: {_sollumz_present(profile['sollumz_addon'])}")
        print("STUB   headless export is feasible (profiles/fivem_sollumz/probe.py); the exporter is not "
              "implemented yet, see docs/TODO.md.")
    return EXIT_STUB
