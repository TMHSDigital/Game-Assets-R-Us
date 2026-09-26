# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry for profiles with status = "stub": validate the profile and exit 3
with a clear message. Nothing is exported. (No profile is a stub today;
roblox and fivem_sollumz are experimental exporters.) A profile whose
exporter is missing on this machine exits 4 instead (core/cli.py)."""

EXIT_STUB = 3


def run(contract):
    profile = contract["profile"]
    print(f"STUB profile '{profile['name']}' ({profile['status']}): schema fields are valid; "
          "no exporter is implemented.")
    return EXIT_STUB
