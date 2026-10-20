"""SOP-181 and SOP-301: backups exist, are private, leave out job scripts, and restore cleanly."""

import unittest

from helpers import head, run

HEAD = head()


class Backups(unittest.TestCase):
    def test_timers_are_enabled(self):
        for timer in ("cluster-backup-nightly.timer", "cluster-backup-binlogs.timer"):
            with self.subTest(timer=timer):
                self.assertEqual(run(HEAD, f"systemctl is-enabled {timer}").stdout.strip(), "enabled")
                self.assertEqual(run(HEAD, f"systemctl is-active {timer}").stdout.strip(), "active")

    def test_a_fresh_backup_restores_cleanly(self):
        r = run(HEAD, "sudo /usr/local/sbin/cluster-backup run", timeout=1800)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run(HEAD, "sudo /usr/local/sbin/cluster-backup verify", timeout=1800)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("restores cleanly", r.stdout)

    def test_backups_are_root_only(self):
        self.assertEqual(run(HEAD, "sudo stat -c '%U:%G %a' /raiddrive/backups").stdout.strip(), "root:root 700")
        self.assertNotEqual(run(HEAD, "ls /raiddrive/backups").returncode, 0)

    def test_binary_logs_are_copied_off_the_database_disk(self):
        r = run(HEAD, "sudo /usr/local/sbin/cluster-backup binlogs")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(run(HEAD, "sudo ls /raiddrive/backups/binlog").stdout.split())


if __name__ == "__main__":
    unittest.main()
