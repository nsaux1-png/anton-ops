"""End-to-end tests of ./cluster user and ./cluster customer, in a sandbox copy of the repo."""

import json
import unittest

import yaml

from sandbox import KEY, Sandbox


class UserCommands(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.root = self.box.root

    def git(self, *args):
        return self.box.git(*args)

    def cluster(self, *args):
        return self.box.cluster(*args)

    def customers(self):
        return yaml.safe_load(self.box.read("config/customers.yml"))["customers"]

    def uids(self):
        return yaml.safe_load(self.box.read("config/uids.yml"))

    def commits(self):
        return self.box.commits()

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

    def test_a_test_customer_and_its_test_user(self):
        r = self.cluster("customer", "add", "--test", "--name", "Test customer 2", "--storage-gb", "20", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("c0002", self.customers(), "the lowest free test code")
        self.assertIs(self.customers()["c0002"]["test"], True)
        r = self.cluster("user", "add", "c0002", "--name", "Test user 2", "--email", "t2@localhost", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout)
        users = self.customers()["c0002"]["users"]
        self.assertEqual(list(users), ["zz02"], "the lowest free test username")
        key = users["zz02"]["ssh_key_file"]
        self.assertTrue(key.startswith(self.box.test_keys), "the sandbox's own key folder, never /etc")
        self.assertTrue(open(key).read().startswith("ssh-ed25519 "), "the apply's preparation made the key")
        self.assertIn("zz02", self.uids()["users"])

    def test_a_test_user_gets_a_generated_key_not_a_given_one(self):
        r = self.cluster("user", "add", "c0001", "--name", "T", "--email", "t@localhost", "--key", KEY, "--yes")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("generated key", r.stdout)

    def test_real_customers_keep_random_codes_and_usernames(self):
        self.assertEqual(self.cluster("customer", "add", "--name", "Real Co", "--yes").returncode, 0)
        new = [c for c in self.customers() if c not in ("c0001", "c4821")]
        self.assertGreaterEqual(int(new[0][1:]), 100)
        self.assertNotIn("test", self.customers()[new[0]])

    def test_uncommitted_changes_block_config_changes(self):
        self.box.write("config/customers.yml", self.box.read("config/customers.yml") + "# hand edit\n")
        r = self.cluster("user", "suspend", "kx47", "--yes")
        self.assertEqual(r.returncode, 2)
        self.assertIn("uncommitted", r.stdout)

    def test_listings(self):
        r = self.cluster("user", "list", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = json.loads(r.stdout)
        self.assertEqual({row["user"] for row in rows}, {"zz01", "kx47"})
        self.assertEqual(self.cluster("customer", "list").returncode, 0)


if __name__ == "__main__":
    unittest.main()
