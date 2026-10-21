"""SOP-106: every machine keeps its system log (the journal) on disk, so a failed boot can be read afterwards."""

import unittest
import uuid

from helpers import hosts, run, wait_until


class Journal(unittest.TestCase):
    def test_journal_is_kept_on_disk(self):
        for host in hosts():
            with self.subTest(host=host):
                conf = run(host, "systemd-analyze cat-config systemd/journald.conf").stdout
                self.assertIn("Storage=persistent", conf.split())
                files = run(host, "sudo find /var/log/journal -name 'system*.journal'").stdout.split()
                self.assertTrue(files, "no journal files under /var/log/journal")

    def test_new_messages_reach_the_files_on_disk(self):
        for host in hosts():
            with self.subTest(host=host):
                tag = f"cluster-test-{uuid.uuid4().hex}"
                run(host, f"logger -t cluster-test {tag}")
                # -D reads only the files in that folder, not journald's in-memory copy.
                found = wait_until(lambda: tag in run(
                    host, "sudo journalctl -D /var/log/journal -t cluster-test --since -10min -o cat").stdout)
                self.assertTrue(found, f"{tag} not found in /var/log/journal")

    def test_admins_read_the_journal_without_sudo(self):
        for host in hosts():
            with self.subTest(host=host):
                r = run(host, "journalctl -q -n 1 -D /var/log/journal")
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertTrue(r.stdout.strip(), "nothing readable")


if __name__ == "__main__":
    unittest.main()
