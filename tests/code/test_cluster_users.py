"""End-to-end tests of ./cluster user and ./cluster customer, in a throwaway copy of the repo.

The copy has its own git history, a sample customers.yml and a stand-in ansible-playbook, so the
commands really edit, commit and "apply", without touching the real repo or machines.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOlIa7dt5DISYUNqy1KetIR7aipepSVvgF5WjS1QB/5c test@laptop"

FAKE_PLAYBOOK = """#!/bin/bash
echo "ansible-playbook $*" >> "$FAKE_CALLS"
if [[ " $* " == *" --check "* && -f "$FAKE_STATE" ]]; then c=0; else c=1; fi
[[ " $* " != *" --check "* ]] && touch "$FAKE_STATE"
echo "anton                      : ok=2    changed=$c    unreachable=0    failed=0    skipped=0"
"""


class UserCommands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = self.root = os.path.join(self.tmp.name, "repo")
        os.makedirs(os.path.join(root, "config"))
        os.makedirs(os.path.join(root, "ansible"))
        shutil.copy(os.path.join(REPO, "cluster"), root)
        shutil.copy(os.path.join(REPO, ".gitignore"), root)
        shutil.copytree(os.path.join(REPO, "clusterlib"), os.path.join(root, "clusterlib"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        test_key = os.path.join(self.tmp.name, "zz01.pub")
        with open(test_key, "w") as f:
            f.write(KEY + "\n")
        with open(os.path.join(root, "config", "customers.yml"), "w") as f:
            f.write(f"""defaults:
  storage_gb: 150
  max_gpus: 4

customers:
  c0001:
    name: Test customer
    test: true
    users:
      zz01:
        name: Test user
        email: t@localhost
        ssh_key_file: {test_key}
  c4821:
    name: Acme
    users:
      kx47:
        name: Alice
        email: alice@acme.example
        ssh_key: {KEY}
""")
        for name in ("site.yml", "upgrade.yml"):
            open(os.path.join(root, "ansible", name), "w").close()
        open(os.path.join(root, "config", "nodes.yml"), "w").close()
        bin_dir = os.path.join(self.tmp.name, "bin")
        os.mkdir(bin_dir)
        with open(os.path.join(bin_dir, "ansible-playbook"), "w") as f:
            f.write(FAKE_PLAYBOOK)
        os.chmod(os.path.join(bin_dir, "ansible-playbook"), 0o755)
        self.logs = os.path.join(self.tmp.name, "logs")
        os.mkdir(self.logs)
        self.env = dict(os.environ, CLUSTER_LOG_DIR=self.logs, CLUSTER_SKIP_CODE_TESTS="1", PYTHONDONTWRITEBYTECODE="1",
                        FAKE_CALLS=os.path.join(self.tmp.name, "calls"),
                        FAKE_STATE=os.path.join(self.tmp.name, "applied"),
                        PATH=bin_dir + os.pathsep + os.environ["PATH"],
                        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "start")

    def git(self, *args):
        return subprocess.run(["git", "-C", self.root, *args], env=getattr(self, "env", None),
                              capture_output=True, text=True, check=True).stdout

    def cluster(self, *args):
        return subprocess.run(["/usr/bin/python3", os.path.join(self.root, "cluster"), *args], env=self.env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True)

    def customers(self):
        with open(os.path.join(self.root, "config", "customers.yml")) as f:
            return yaml.safe_load(f)["customers"]

    def uids(self):
        with open(os.path.join(self.root, "config", "uids.yml")) as f:
            return yaml.safe_load(f)

    def commits(self):
        return self.git("log", "--format=%s").splitlines()

    def test_user_add_edits_commits_gives_ids_and_applies(self):
        r = self.cluster("user", "add", "c4821", "--name", "Bob Smith", "--email", "bob@acme.example",
                         "--key", KEY, "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        users = self.customers()["c4821"]["users"]
        new = [u for u in users if u != "kx47"]
        self.assertEqual(len(new), 1)
        name = new[0]
        self.assertRegex(name, r"^[abcdefghjkmnpqrstuvwxyz]{2}[0-9]{2}$")
        self.assertEqual(users[name]["email"], "bob@acme.example")
        self.assertEqual(users[name]["ssh_key"], KEY)
        self.assertIn(name, self.uids()["users"])
        self.assertEqual(self.uids()["groups"]["c4821"], 20001)
        self.assertEqual(self.commits()[:2][::-1], [f"Add user {name} to c4821", self.commits()[0]])
        self.assertTrue(self.commits()[0].startswith("Give out IDs:"))
        self.assertIn("Done and settled.", r.stdout)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_user_add_to_unknown_customer_changes_nothing(self):
        before = self.commits()
        r = self.cluster("user", "add", "c7777", "--name", "X", "--email", "x@y.example", "--key", KEY, "--yes")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(self.commits(), before)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_dry_run_changes_nothing(self):
        before = self.commits()
        r = self.cluster("user", "add", "c4821", "--name", "X", "--email", "x@y.example", "--key", KEY, "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("+      ", r.stdout)   # the diff is shown
        self.assertEqual(self.commits(), before)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_without_terminal_or_yes_it_asks_and_is_refused(self):
        before = self.commits()
        r = self.cluster("user", "suspend", "kx47")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(self.commits(), before)

    def test_bad_key_is_refused(self):
        r = self.cluster("user", "add", "c4821", "--name", "X", "--email", "x@y.example", "--key", "nonsense", "--yes")
        self.assertEqual(r.returncode, 2)
        self.assertIn("doesn't look like an SSH public key", r.stdout)

    def test_suspend_resume_remove(self):
        self.assertEqual(self.cluster("user", "suspend", "kx47", "--yes").returncode, 0)
        self.assertEqual(self.customers()["c4821"]["users"]["kx47"]["status"], "suspended")
        self.assertEqual(self.cluster("user", "resume", "kx47", "--yes").returncode, 0)
        self.assertEqual(self.customers()["c4821"]["users"]["kx47"]["status"], "active")
        self.assertEqual(self.cluster("user", "remove", "kx47", "--yes").returncode, 0)
        self.assertEqual(self.customers()["c4821"]["users"]["kx47"]["status"], "removed")
        self.assertIn("User kx47: removed", self.commits()[0])

    def test_user_set(self):
        self.assertEqual(self.cluster("user", "set", "kx47", "max_gpus", "7", "--yes").returncode, 0)
        self.assertEqual(self.customers()["c4821"]["users"]["kx47"]["max_gpus"], 7)
        self.assertEqual(self.cluster("user", "set", "kx47", "max_gpus", "lots", "--yes").returncode, 2)
        self.assertEqual(self.cluster("user", "set", "kx47", "status", "removed", "--yes").returncode, 2)
        self.assertEqual(self.cluster("user", "set", "nobody", "max_gpus", "1", "--yes").returncode, 2)

    def test_customer_add_and_set(self):
        r = self.cluster("customer", "add", "--name", "New Co", "--storage-gb", "500", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout)
        new = [c for c in self.customers() if c not in ("c0001", "c4821")]
        self.assertEqual(len(new), 1)
        self.assertGreaterEqual(int(new[0][1:]), 100)
        self.assertEqual(self.customers()[new[0]]["storage_gb"], 500)
        self.assertIn(new[0], self.uids()["groups"])
        self.assertEqual(self.cluster("customer", "set", new[0], "storage_gb", "900", "--yes").returncode, 0)
        self.assertEqual(self.customers()[new[0]]["storage_gb"], 900)
        r = self.cluster("user", "add", new[0], "--name", "First", "--email", "f@new.example", "--key", KEY, "--yes")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(len(self.customers()[new[0]]["users"]), 1)

    def test_uncommitted_changes_block_config_changes(self):
        with open(os.path.join(self.root, "config", "customers.yml"), "a") as f:
            f.write("# hand edit\n")
        r = self.cluster("user", "suspend", "kx47", "--yes")
        self.assertEqual(r.returncode, 2)
        self.assertIn("uncommitted", r.stdout)

    def test_listings(self):
        r = self.cluster("user", "list", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        import json
        rows = json.loads(r.stdout)
        self.assertEqual({row["user"] for row in rows}, {"zz01", "kx47"})
        self.assertEqual(self.cluster("customer", "list").returncode, 0)


if __name__ == "__main__":
    unittest.main()
