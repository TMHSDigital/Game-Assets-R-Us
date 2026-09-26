# SPDX-License-Identifier: GPL-3.0-or-later
"""core/cli.py exit codes: 3 for stub profiles, 4 for unavailable ones."""

import tempfile
import unittest
from unittest import mock

import core.contract
from core import cli, fivem
from core.contract.resolve import freeze, thaw

KIT = "stone-dungeon-wall-sampler"


def _run(profile):
    with tempfile.TemporaryDirectory() as tmp:
        args = cli._args(["run", "--kit", KIT, "--profile", profile, "--build-dir", tmp, "--dist-dir", tmp])
        return cli.cmd_run(args)


class ExitCodes(unittest.TestCase):
    def test_stub_is_detected_by_status(self):
        real = core.contract.resolve

        def as_stub(contract, name):
            data = thaw(real(contract, name))
            data["profile"]["status"] = "stub"
            return freeze(data)

        with mock.patch("core.contract.resolve", as_stub):
            self.assertEqual(_run("unity"), 3)

    def test_unavailable_exporter_exits_4(self):
        def missing(profile):
            raise fivem.SollumzUnavailable("not installed (test)")

        with mock.patch.object(fivem, "ensure_sollumz", missing):
            self.assertEqual(_run("fivem_sollumz"), cli.EXIT_UNAVAILABLE)
        self.assertEqual(cli.EXIT_UNAVAILABLE, 4)


if __name__ == "__main__":
    unittest.main()
