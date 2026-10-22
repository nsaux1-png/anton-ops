"""Tests for clusterlib.health: the checks behind ./cluster health."""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))

from clusterlib import health as h   # noqa: E402

NOW = datetime.datetime(2026, 10, 20, 12, 0)


class Checks(unittest.TestCase):
    def test_raid(self):
        self.assertTrue(h.raid_ok("md0 : active raid1 sdb[1] sda[0]\n      3906885440 blocks [2/2] [UU]")[0])
        ok, detail = h.raid_ok("md0 : active raid1 sda[0]\n      3906885440 blocks [2/1] [U_]")
        self.assertFalse(ok)
        self.assertIn("degraded", detail)
        self.assertFalse(h.raid_ok("Personalities : \nunused devices: <none>")[0])

    def test_disk(self):
        self.assertTrue(h.disk_ok(" 12% /raiddrive")[0])
        self.assertFalse(h.disk_ok(" 91% /")[0])

    def test_backup_age(self):
        self.assertTrue(h.backup_age_ok("2026-10-20", NOW)[0])
        self.assertFalse(h.backup_age_ok("2026-10-18", NOW)[0])
        self.assertFalse(h.backup_age_ok(None, NOW)[0])

    def test_timers(self):
        recent = NOW - datetime.timedelta(minutes=30)
        self.assertTrue(h.timer_ok("cluster-billing-hourly", "success", recent, NOW)[0])
        self.assertFalse(h.timer_ok("cluster-billing-hourly", "exit-code", recent, NOW)[0])
        self.assertFalse(h.timer_ok("cluster-billing-hourly", "success", NOW - datetime.timedelta(hours=5), NOW)[0])
        self.assertTrue(h.timer_ok("cluster-tests-weekly", "success", None, NOW)[0])     # not due yet
        self.assertFalse(h.timer_ok("cluster-backup-nightly", "success", None, NOW)[0])

    def test_nodes(self):
        self.assertTrue(h.nodes_ok(["douglas1 idle", "douglas2 mixed"])[0])
        ok, detail = h.nodes_ok(["douglas1 down*", "douglas2 idle"])
        self.assertFalse(ok)
        self.assertIn("douglas1", detail)
        self.assertFalse(h.nodes_ok(["douglas1 drained"])[0])

    def test_gpus(self):
        listing = "\n".join(f"GPU {i}: NVIDIA GeForce RTX 5070 Ti (UUID: GPU-{i})" for i in range(10))
        self.assertEqual(h.gpus_ok(listing, 10), (True, "10 of 10 GPUs"))
        ok, detail = h.gpus_ok("\n".join(listing.splitlines()[:9]), 10)
        self.assertFalse(ok)
        self.assertEqual(detail, "9 of 10 GPUs")
        self.assertFalse(h.gpus_ok("NVIDIA-SMI has failed because it couldn't communicate with the driver", 10)[0])

    def test_gpu_and_pcie_errors(self):
        self.assertEqual(h.gpu_errors_ok("kernel: NVRM: loading NVIDIA UNIX Open Kernel Module\n"), (True, "none since boot"))
        for line in ("kernel: NVRM: Xid (PCI:0000:01:00): 79, pid=1234, GPU has fallen off the bus.",
                     "kernel: {1}[Hardware Error]: event severity: corrected",
                     "kernel: NVRM: GPU 0000:45:00.0: GPU has fallen off the bus."):
            with self.subTest(line=line):
                ok, detail = h.gpu_errors_ok("kernel: ordinary line\n" + line)
                self.assertFalse(ok)
                self.assertIn("1 line(s)", detail)

    def test_summary(self):
        lines, ok = h.summary([("anton", "slurmctld", True, "active"), ("douglas1", "reachable", False, "no route")])
        self.assertFalse(ok)
        self.assertTrue(lines[0].startswith("OK  "))
        self.assertTrue(lines[1].startswith("FAIL"))
        self.assertEqual(lines[-1], "1 problem(s).")
        self.assertEqual(h.summary([("a", "b", True, "")])[0][-1], "All healthy.")


if __name__ == "__main__":
    unittest.main()
