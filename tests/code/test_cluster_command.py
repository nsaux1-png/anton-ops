"""Tests for the ./cluster command itself, with stand-ins for ansible and ansible-playbook.

Run:  ./cluster test --code
"""

import os
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
CLUSTER = os.path.join(REPO, "cluster")

# Stand-in for ansible-playbook: a check run reports 1 change until a real run has happened.
FAKE_PLAYBOOK = """#!/bin/bash
echo "ansible-playbook $*" >> "$FAKE_CALLS"
if [[ " $* " == *" --check "* ]]; then
  if [[ -f "$FAKE_STATE" ]]; then c=0; else c=1; fi
else
  touch "$FAKE_STATE"; c=1
fi
echo "PLAY RECAP *********************************************************"
echo "anton                      : ok=2    changed=$c    unreachable=0    failed=0    skipped=0"
"""

FAKE_ANSIBLE = """#!/bin/bash
echo "ansible $*" >> "$FAKE_CALLS"
echo "anton | SUCCESS"
exit "${FAKE_EXIT:-0}"
"""


class ClusterCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        self.logs = os.path.join(d, "logs")
        bin_dir = os.path.join(d, "bin")
        os.mkdir(self.logs)
        os.mkdir(bin_dir)
        for name, body in [("ansible-playbook", FAKE_PLAYBOOK), ("ansible", FAKE_ANSIBLE)]:
            path = os.path.join(bin_dir, name)
            with open(path, "w") as f:
                f.write(body)
            os.chmod(path, 0o755)
        self.calls = os.path.join(d, "calls")
        self.state = os.path.join(d, "applied")
        self.env = dict(os.environ, CLUSTER_LOG_DIR=self.logs, CLUSTER_SKIP_CODE_TESTS="1", FAKE_CALLS=self.calls,
                        FAKE_STATE=self.state, PATH=bin_dir + os.pathsep + os.environ["PATH"])

    def cluster(self, *args, **env):
        return subprocess.run(["/usr/bin/python3", CLUSTER, *args], env=dict(self.env, **env),
                              stdin=subprocess.DEVNULL, capture_output=True, text=True)

    def calls_made(self):
        if not os.path.exists(self.calls):
            return []
        with open(self.calls) as f:
            return f.read().splitlines()

    def index_lines(self):
        with open(os.path.join(self.logs, "index.log")) as f:
            return f.read().splitlines()

    def only_log(self):
        logs = [n for n in os.listdir(self.logs) if n != "index.log"]
        self.assertEqual(len(logs), 1, logs)
        with open(os.path.join(self.logs, logs[0])) as f:
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
        name = [n for n in os.listdir(self.logs) if n != "index.log"][0]
        self.assertEqual(os.stat(os.path.join(self.logs, name)).st_mode & 0o007, 0)

    def test_failed_command_exits_1_and_index_says_so(self):
        r = self.cluster("ping", FAKE_EXIT="4")
        self.assertEqual(r.returncode, 1)
        self.assertIn("\texit=1\t", self.index_lines()[0])

    def test_apply_without_terminal_or_yes_is_refused_after_preview_only(self):
        r = self.cluster("apply", "--allow-dirty")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("REFUSED", r.stdout)
        calls = self.calls_made()
        self.assertEqual(len(calls), 1)
        self.assertIn("--check", calls[0])
        self.assertFalse(os.path.exists(self.state))

    def test_apply_yes_previews_applies_then_checks_settled(self):
        r = self.cluster("apply", "--yes", "--allow-dirty")
        self.assertEqual(r.returncode, 0, r.stdout)
        calls = self.calls_made()
        self.assertEqual(len(calls), 3, calls)
        self.assertIn("--check", calls[0])
        self.assertNotIn("--check", calls[1])
        self.assertIn("--check", calls[2])
        self.assertIn("Done and settled.", r.stdout)

    def test_apply_with_nothing_to_change_stops_after_preview(self):
        open(self.state, "w").close()
        r = self.cluster("apply", "--yes", "--allow-dirty")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Nothing to change.", r.stdout)
        self.assertEqual(len(self.calls_made()), 1)

    def test_dry_run_changes_nothing(self):
        r = self.cluster("apply", "--dry-run", "--allow-dirty")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len(self.calls_made()), 1)
        self.assertFalse(os.path.exists(self.state))

    def test_runs_lists_the_index(self):
        self.cluster("ping")
        r = self.cluster("runs")
        self.assertEqual(r.returncode, 0)
        self.assertIn("ping", r.stdout)


if __name__ == "__main__":
    unittest.main()
