"""SOP-161: the ledger against the real database server, in the scratch database cluster_ledger_test.

The tests themselves are in tests/ledger; they need root (the database password is root-only), so they
run through sudo. The real ledger (cluster_ledger) is never touched.
"""

import os
import subprocess
import unittest

from helpers import REPO


class Ledger(unittest.TestCase):
    def test_ledger_scenarios_against_the_database(self):
        folder = os.path.join(REPO, "tests", "ledger")
        r = subprocess.run(["sudo", "/usr/bin/python3", "-I", "-B", "-m", "unittest", "discover", "-s", folder,
                            "-t", folder, "-v"], capture_output=True, text=True, cwd="/", timeout=600)
        self.assertEqual(r.returncode, 0, r.stderr[-6000:])
        self.assertIn("OK", r.stderr)


if __name__ == "__main__":
    unittest.main()
