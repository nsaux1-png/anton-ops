"""SOP-191 and the other timers: the scheduled runs are set up, and each service starts a program that
systemd is allowed to execute. SELinux won't let systemd execute a file in a home folder, so the weekly
test run failed with "Permission denied" before it ever ran (found 2026-10-22)."""

import unittest

from helpers import head, run

HEAD = head()
TIMERS = ["cluster-tests-weekly", "cluster-billing-hourly", "cluster-backup-nightly", "cluster-backup-binlogs"]


class Scheduled(unittest.TestCase):
    def test_every_timer_is_enabled_and_has_a_next_run(self):
        for name in TIMERS:
            with self.subTest(timer=name):
                self.assertEqual(run(HEAD, f"systemctl is-enabled {name}.timer").stdout.strip(), "enabled")
                next_run = run(HEAD, f"systemctl show -p NextElapseUSecRealtime --value {name}.timer").stdout.strip()
                self.assertTrue(next_run and next_run != "n/a", f"{name} has no next run")

    def test_each_service_starts_a_program_systemd_may_execute(self):
        for name in TIMERS:
            with self.subTest(service=name):
                exec_start = run(HEAD, f"systemctl show -p ExecStart --value {name}.service").stdout
                program = exec_start.split("path=")[1].split(";")[0].strip() if "path=" in exec_start else ""
                self.assertTrue(program, exec_start)
                label = run(HEAD, f"stat -c %C {program}").stdout.strip()
                self.assertNotIn(":user_home_t:", label, f"{program} is in a home folder: systemd can't execute it")


if __name__ == "__main__":
    unittest.main()
