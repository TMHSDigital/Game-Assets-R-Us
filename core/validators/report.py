# SPDX-License-Identifier: GPL-3.0-or-later
"""Check results and JSON reports.

Every check has a stable ID (for example CORE.GRID.DIMS or STL.WALL.MIN)
so tests and CI can assert on the exact failure. Status is one of:
  pass   the rule holds
  fail   the rule is broken; the run exits non-zero
  skip   the rule does not apply to this profile kind (reason given)
"""

import json
import os
from dataclasses import asdict, dataclass, field

PASS, FAIL, SKIP = "pass", "fail", "skip"


@dataclass
class Check:
    id: str
    status: str
    message: str = ""
    detail: dict = field(default_factory=dict)


def ok(check_id, message="", **detail):
    return Check(check_id, PASS, message, detail)


def fail(check_id, message, **detail):
    return Check(check_id, FAIL, message, detail)


def skip(check_id, reason):
    return Check(check_id, SKIP, reason)


def verdict(check_id, passed, message, **detail):
    return Check(check_id, PASS if passed else FAIL, message, detail)


def _clean(value):
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if hasattr(value, "to_tuple"):
        return [round(c, 6) for c in value.to_tuple()]
    return value


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(_clean(data), fh, indent=2, sort_keys=True)
        fh.write("\n")


def piece_report(meta, checks, fixes):
    return {
        **meta,
        "passed": all(c.status != FAIL for c in checks),
        "checks": [asdict(c) for c in checks],
        "fixes": fixes,
    }
