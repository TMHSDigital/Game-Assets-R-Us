# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry for profiles with kind = "stub": validate the profile and exit 3
with a clear message. Nothing is exported. (No profile is a stub today;
roblox and fivem_sollumz are experimental exporters.)"""

EXIT_STUB = 3


def run(contract):
    profile = contract["profile"]
    print(f"STUB profile '{profile['name']}' ({profile['status']}): schema fields are valid; "
          "no exporter is implemented.")
    return EXIT_STUB
