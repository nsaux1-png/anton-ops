"""Tests for the ./cluster command itself (logging, apply's flow, exit codes), in a sandbox copy of the repo.

Run:  ./cluster test --code
"""

import os
import unittest

from sandbox import Sandbox


class ClusterCommandTest(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)

    def cluster(self, *args, **env):
        return self.box.cluster(*args, **env)

    def index_lines(self):
        with open(os.path.join(self.box.logs, "index.log")) as f:
            return f.read().splitlines()

    def only_log(self):
        logs = [n for n in os.listdir(self.box.logs) if n != "index.log"]
        self.assertEqual(len(logs), 1, logs)
        with open(os.path.join(self.box.logs, logs[0])) as f:
            return f.read()

    def test_run_is_logged_with_header_output_and_exit_code(self):
        r = self.cluster("ping")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        log = self.only_log()
        self.assertIn("== ./cluster ping", log)
        self.assertIn("operator=", log)
        self.assertIn("anton | SUCCESS", log)
        self.assertIn("== exit=0", log)
        [line] = self.index_lines()
        self.assertIn("\texit=0\t", line)
        self.assertIn("\tping\t", line)

    def test_log_is_not_readable_by_others(self):
        self.cluster("ping")
        name = [n for n in os.listdir(self.box.logs) if n != "index.log"][0]
        self.assertEqual(os.stat(os.path.join(self.box.logs, name)).st_mode & 0o007, 0)

    def test_failed_command_exits_1_and_index_says_so(self):
        r = self.cluster("ping", FAKE_EXIT="4")
        self.assertEqual(r.returncode, 1)
        self.assertIn("\texit=1\t", self.index_lines()[0])

    def test_apply_without_terminal_or_yes_is_refused_after_preview_only(self):
        r = self.cluster("apply")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("REFUSED", r.stdout)
        calls = self.box.calls_made()
        self.assertEqual(len(calls), 1)
        self.assertIn("--check", calls[0])
        self.assertFalse(os.path.exists(self.box.state))

    def test_apply_yes_previews_applies_then_checks_settled(self):
        r = self.cluster("apply", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout)
        calls = self.box.calls_made()
        self.assertEqual(len(calls), 3, calls)
        self.assertIn("--check", calls[0])
        self.assertNotIn("--check", calls[1])
        self.assertIn("--check", calls[2])
        self.assertIn("Done and settled.", r.stdout)

    def test_apply_with_nothing_to_change_stops_after_preview(self):
        open(self.box.state, "w").close()
        r = self.cluster("apply", "--yes")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Nothing to change.", r.stdout)
        self.assertEqual(len(self.box.calls_made()), 1)

    def test_dry_run_changes_nothing(self):
        r = self.cluster("apply", "--dry-run")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len(self.box.calls_made()), 1)
        self.assertFalse(os.path.exists(self.box.state))

    def test_apply_refuses_uncommitted_changes(self):
        self.box.write("config/nodes.yml", "# changed\n")
        r = self.cluster("apply", "--yes")
        self.assertEqual(r.returncode, 2)
        self.assertIn("uncommitted", r.stdout)
        self.assertEqual(self.box.calls_made(), [])

    def test_apply_gives_out_ids_and_commits_them_first(self):
        r = self.cluster("apply", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(self.box.commits()[0].startswith("Give out IDs: c0001=20000"), self.box.commits())
        self.assertIn("kx47: 10101", self.box.read("config/uids.yml"))
        self.assertEqual(self.box.git("status", "--porcelain"), "")

    def test_apply_refuses_a_broken_customers_file(self):
        self.box.write("config/customers.yml", self.box.read("config/customers.yml").replace("kx47", "kl47"))
        self.box.git("commit", "-qam", "break it")
        r = self.cluster("apply", "--yes")
        self.assertEqual(r.returncode, 2)
        self.assertIn("two letters (not i, l or o)", r.stdout)
        self.assertEqual(self.box.calls_made(), [])

    def test_runs_lists_the_index(self):
        self.cluster("ping")
        r = self.cluster("runs")
        self.assertEqual(r.returncode, 0)
        self.assertIn("ping", r.stdout)


if __name__ == "__main__":
    unittest.main()
