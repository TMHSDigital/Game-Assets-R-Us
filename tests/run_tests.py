# SPDX-License-Identifier: GPL-3.0-or-later
"""Test entry point. Runs inside Blender:

    blender --background --factory-startup --python tests/run_tests.py -- [--pattern test_*.py] [--skip-slow]

Exit code 0 when every test passes, 1 otherwise.
"""

import argparse
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="run_tests.py")
    parser.add_argument("--pattern", default="test_*.py")
    parser.add_argument("--skip-slow", action="store_true",
                        help="skip tests that launch extra Blender processes (determinism)")
    args = parser.parse_args(argv)
    if args.skip_slow:
        os.environ["GARU_SKIP_SLOW"] = "1"
    suite = unittest.defaultTestLoader.discover(HERE, pattern=args.pattern, top_level_dir=HERE)
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
    print(f"TESTS run={result.testsRun} failures={len(result.failures)} "
          f"errors={len(result.errors)} skipped={len(result.skipped)}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.stdout.flush()
    code = main()
    sys.stdout.flush()
    sys.exit(code)
