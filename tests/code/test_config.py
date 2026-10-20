"""Tests for clusterlib.config: checking customers.yml, IDs, usernames, and the text edits."""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))

from clusterlib import config as cfg   # noqa: E402

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOlIa7dt5DISYUNqy1KetIR7aipepSVvgF5WjS1QB/5c alice@laptop"

SAMPLE = f"""# Customers (test sample)
defaults:
  storage_gb: 150   # per customer
  max_gpus: 4

customers:
  c0001:
    name: Test customer 1
    test: true
    storage_gb: 1
    users:
      zz01:
        name: Test user 1
        email: test@localhost
        ssh_key_file: /etc/cluster/test-keys/zz01.pub
        role: manager
  c4821:
    name: Acme Robotics
    billing_email: ap@acme.example
    users:   # people
      kx47:
        name: Alice Chen
        email: alice@acme.example
        ssh_key: {KEY}
        max_gpus: 6   # override
  c5000:
    name: Empty Co
    users: {{}}
"""


class Checking(unittest.TestCase):
    def config(self, text=SAMPLE):
        return cfg.parse(text)

    def test_the_sample_is_fine(self):
        self.assertEqual(cfg.problems(self.config()), [])

    def assertProblem(self, text, fragment):
        found = cfg.problems(cfg.parse(text))
        self.assertTrue(any(fragment in p for p in found), found)

    def test_customer_code_format(self):
        self.assertProblem(SAMPLE.replace("  c4821:", "  acme:"), "code must be 'c' and four digits")

    def test_test_customers_use_reserved_codes(self):
        self.assertProblem(SAMPLE.replace("  c4821:\n    name: Acme Robotics\n",
                                          "  c4821:\n    name: Acme Robotics\n    test: true\n"),
                           "test customers must be c0001-c0099")
        self.assertProblem(SAMPLE.replace("    test: true\n", ""), "c0001-c0099 are for test customers")

    def test_usernames(self):
        self.assertProblem(SAMPLE.replace("kx47", "kl47"), "two letters (not i, l or o)")
        self.assertProblem(SAMPLE.replace("kx47", "zz47"), "zz is for tests")
        self.assertProblem(SAMPLE.replace("zz01", "ab01"), "test customers' users are zz01-zz99")
        self.assertProblem(SAMPLE.replace("kx47", "kx477"), "two letters")

    def test_a_username_can_only_appear_once(self):
        twice = SAMPLE.replace("    users: {}\n", f"    users:\n      kx47:\n        name: X\n        email: x@y\n        ssh_key: {KEY}\n")
        self.assertProblem(twice, "also listed under")

    def test_required_user_fields(self):
        self.assertProblem(SAMPLE.replace("        email: alice@acme.example\n", ""), "needs an email")
        self.assertProblem(SAMPLE.replace(f"        ssh_key: {KEY}\n", ""), "needs an ssh_key")
        self.assertProblem(SAMPLE.replace(KEY, "not-a-key"), "doesn't look like an SSH public key")

    def test_only_test_users_may_use_key_files(self):
        self.assertProblem(SAMPLE.replace(f"ssh_key: {KEY}", "ssh_key_file: /tmp/k.pub"), "only for test users")

    def test_status_role_and_numbers(self):
        self.assertProblem(SAMPLE.replace("role: manager", "role: boss"), "role must be one of")
        self.assertProblem(SAMPLE.replace("max_gpus: 6", "max_gpus: -1"), "max_gpus must be a whole number")
        self.assertProblem(SAMPLE.replace("storage_gb: 1\n", "storage_gb: 0\n"), "storage_gb must be")
        self.assertProblem(SAMPLE.replace("storage_gb: 150", "storage_gb: lots"), "defaults: storage_gb")
        self.assertProblem(SAMPLE.replace("        max_gpus: 6", "        status: gone"), "status must be one of")

    def test_unknown_fields_are_caught(self):
        self.assertProblem(SAMPLE.replace("        max_gpus: 6", "        max_gpu: 6"), "unknown field 'max_gpu'")
        self.assertProblem(SAMPLE.replace("    billing_email:", "    billing_mail:"), "unknown field 'billing_mail'")

    def test_check_raises_with_every_problem(self):
        with self.assertRaises(cfg.ConfigError) as e:
            cfg.check(cfg.parse(SAMPLE.replace("kx47", "kl47").replace("role: manager", "role: boss")))
        self.assertIn("two letters", str(e.exception))
        self.assertIn("role must be", str(e.exception))


class Ids(unittest.TestCase):
    def test_allocation_starts_at_the_ranges_and_is_ordered(self):
        uids, added = cfg.allocate(cfg.parse(SAMPLE), {"users": {}, "groups": {}})
        self.assertEqual(uids["groups"], {"c0001": 20000, "c4821": 20001, "c5000": 20002})
        self.assertEqual(uids["users"], {"zz01": 10100, "kx47": 10101})
        self.assertEqual(len(added), 5)

    def test_existing_ids_never_change_and_removed_ones_are_never_reused(self):
        old = {"users": {"gone": 10100, "kx47": 10105}, "groups": {"c9999": 20007}}
        uids, added = cfg.allocate(cfg.parse(SAMPLE), old)
        self.assertEqual(uids["users"]["gone"], 10100)          # kept, though no longer configured
        self.assertEqual(uids["users"]["kx47"], 10105)          # unchanged
        self.assertEqual(uids["users"]["zz01"], 10106)          # after the highest ever given
        self.assertEqual(uids["groups"]["c0001"], 20008)
        self.assertNotIn("kx47=", " ".join(added))

    def test_allocation_is_stable(self):
        once, _ = cfg.allocate(cfg.parse(SAMPLE), {"users": {}, "groups": {}})
        twice, added = cfg.allocate(cfg.parse(SAMPLE), once)
        self.assertEqual(once, twice)
        self.assertEqual(added, [])

    def test_uids_file_round_trips(self):
        uids, _ = cfg.allocate(cfg.parse(SAMPLE), {"users": {}, "groups": {}})
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as f:
            f.write(cfg.format_uids(uids))
        try:
            self.assertEqual(cfg.load_uids(f.name), uids)
        finally:
            os.unlink(f.name)


class Accounts(unittest.TestCase):
    def test_defaults_are_applied_and_ids_attached(self):
        config = cfg.parse(SAMPLE)
        uids, _ = cfg.allocate(config, {"users": {}, "groups": {}})
        acc = cfg.accounts(config, uids)
        byname = {u["name"]: u for u in acc["users"]}
        self.assertEqual(byname["kx47"]["max_gpus"], 6)
        self.assertEqual(byname["zz01"]["max_gpus"], 4)
        self.assertEqual(byname["zz01"]["role"], "manager")
        self.assertEqual(byname["kx47"]["status"], "active")
        self.assertEqual(byname["kx47"]["gid"], uids["groups"]["c4821"])
        bycode = {c["code"]: c for c in acc["customers"]}
        self.assertEqual(bycode["c4821"]["storage_gb"], 150)
        self.assertEqual(bycode["c0001"]["storage_gb"], 1)
        self.assertTrue(bycode["c0001"]["test"])

    def test_quota_spec_lists_each_customers_folders(self):
        config = cfg.parse(SAMPLE)
        uids, _ = cfg.allocate(config, {"users": {}, "groups": {}})
        spec = cfg.quota_spec(cfg.accounts(config, uids))
        self.assertEqual(spec["mount"], "/raiddrive")
        by_gid = {c["gid"]: c for c in spec["customers"]}
        acme = by_gid[uids["groups"]["c4821"]]
        self.assertEqual(acme["limit_gb"], 150)
        self.assertEqual(acme["dirs"], ["/raiddrive/cluster/projects/c4821", "/raiddrive/cluster/home/kx47"])
        self.assertEqual(by_gid[uids["groups"]["c5000"]]["dirs"], ["/raiddrive/cluster/projects/c5000"])

    def test_missing_ids_are_an_error(self):
        with self.assertRaises(cfg.ConfigError):
            cfg.accounts(cfg.parse(SAMPLE), {"users": {}, "groups": {}})


class Names(unittest.TestCase):
    def test_usernames_follow_the_rules(self):
        rng = random.Random(1)
        names = {cfg.new_username(set(), rng) for _ in range(5000)}
        for name in names:
            self.assertRegex(name, cfg.REAL_USERNAME_RE)
            self.assertFalse(name.startswith("zz"))
        self.assertGreater(len(names), 4000)   # random, not a short cycle

    def test_usernames_avoid_taken_ones(self):
        rng = random.Random(2)
        taken = set()
        for _ in range(2000):
            taken.add(cfg.new_username(taken, rng))
        self.assertEqual(len(taken), 2000)

    def test_customer_codes(self):
        rng = random.Random(3)
        codes = {cfg.new_customer_code(set(), rng) for _ in range(2000)}
        for code in codes:
            self.assertRegex(code, cfg.CUSTOMER_RE)
            self.assertGreater(int(code[1:]), cfg.TEST_CUSTOMER_MAX)


class TextEdits(unittest.TestCase):
    def test_add_user_keeps_comments_and_other_users(self):
        out = cfg.add_user_text(SAMPLE, "c4821", "bt82", {"name": "Bob Smith", "email": "bob@acme.example", "ssh_key": KEY})
        self.assertIn("users:   # people", out)
        self.assertIn("        max_gpus: 6   # override", out)
        self.assertIn("# Customers (test sample)", out)
        users = cfg.parse(out)["customers"]["c4821"]["users"]
        self.assertEqual(set(users), {"kx47", "bt82"})
        self.assertEqual(users["bt82"]["name"], "Bob Smith")
        self.assertEqual(cfg.problems(cfg.parse(out)), [])

    def test_add_first_user_to_an_empty_customer(self):
        out = cfg.add_user_text(SAMPLE, "c5000", "qr12", {"name": "Q R", "email": "q@r.example", "ssh_key": KEY})
        self.assertEqual(set(cfg.parse(out)["customers"]["c5000"]["users"]), {"qr12"})
        self.assertEqual(cfg.problems(cfg.parse(out)), [])

    def test_awkward_values_are_quoted_safely(self):
        name = 'Zoë "Z" O\'Neil: #1'
        out = cfg.add_user_text(SAMPLE, "c4821", "bt82", {"name": name, "email": "z@x.example", "ssh_key": KEY})
        self.assertEqual(cfg.parse(out)["customers"]["c4821"]["users"]["bt82"]["name"], name)

    def test_add_user_to_unknown_customer(self):
        with self.assertRaises(cfg.ConfigError):
            cfg.add_user_text(SAMPLE, "c7777", "bt82", {"name": "B", "email": "b@x", "ssh_key": KEY})

    def test_unusual_layout_is_refused_not_mangled(self):
        flow = SAMPLE.replace("    users:   # people\n      kx47:", "    users: {kx47: {name: A, email: a@b, ssh_key: x}}\n      xx47:")
        with self.assertRaises(cfg.ConfigError):
            cfg.add_user_text(flow, "c4821", "bt82", {"name": "B", "email": "b@x", "ssh_key": KEY})

    def test_set_user_field_replaces_or_adds(self):
        out = cfg.set_user_field_text(SAMPLE, "kx47", "max_gpus", 2)
        self.assertEqual(cfg.parse(out)["customers"]["c4821"]["users"]["kx47"]["max_gpus"], 2)
        self.assertIn("        max_gpus: 2   # override", out)
        out = cfg.set_user_field_text(SAMPLE, "kx47", "status", "suspended")
        self.assertEqual(cfg.parse(out)["customers"]["c4821"]["users"]["kx47"]["status"], "suspended")
        self.assertEqual(cfg.parse(out)["customers"]["c0001"]["users"]["zz01"].get("status"), None)

    def test_set_unknown_user_or_field(self):
        with self.assertRaises(cfg.ConfigError):
            cfg.set_user_field_text(SAMPLE, "nope", "status", "removed")
        with self.assertRaises(cfg.ConfigError):
            cfg.set_user_field_text(SAMPLE, "kx47", "shoe_size", 9)

    def test_add_customer(self):
        out = cfg.add_customer_text(SAMPLE, "c6000", {"name": "New Co", "storage_gb": 500})
        c = cfg.parse(out)["customers"]["c6000"]
        self.assertEqual(c["storage_gb"], 500)
        self.assertEqual(c["users"], {})
        self.assertEqual(cfg.problems(cfg.parse(out)), [])
        out2 = cfg.add_user_text(out, "c6000", "ab12", {"name": "A B", "email": "a@b.example", "ssh_key": KEY})
        self.assertIn("ab12", cfg.parse(out2)["customers"]["c6000"]["users"])

    def test_set_customer_field(self):
        out = cfg.set_customer_field_text(SAMPLE, "c4821", "storage_gb", 1000)
        self.assertEqual(cfg.parse(out)["customers"]["c4821"]["storage_gb"], 1000)
        out = cfg.set_customer_field_text(out, "c4821", "storage_gb", 2000)
        self.assertEqual(cfg.parse(out)["customers"]["c4821"]["storage_gb"], 2000)
        self.assertEqual(out.count("storage_gb: 2000"), 1)

    def test_find_user(self):
        self.assertEqual(cfg.find_user(cfg.parse(SAMPLE), "kx47")[0], "c4821")
        with self.assertRaises(cfg.ConfigError):
            cfg.find_user(cfg.parse(SAMPLE), "nobody")


if __name__ == "__main__":
    unittest.main()
