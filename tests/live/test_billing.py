"""SOP-161, SOP-162, SOP-211: billing on the real cluster, with the test customers.

Test customers (c0001, c0002) get test credit ("grant") here when they need it; they're never invoiced.
"""

import json
import re
import shlex
import unittest
import uuid

from helpers import head, run, ssh_login

HEAD = head()
A, A2, B = "zz01", "zz02", "zz03"           # zz01 manages c0001; zz02 is a plain user of c0001; zz03 is c0002


def billing(*args):
    return run(HEAD, "sudo /usr/local/sbin/cluster-billing " + " ".join(shlex.quote(a) for a in args))


def balance(code):
    return json.loads(billing("balance", code, "--json").stdout)


def as_user(user, command):
    return run(HEAD, f"sudo -u {user} bash -lc {shlex.quote('cd ~ && ' + command)}")


def unit_minutes_per_micro():
    """How many billing-unit-minutes one micro-credit buys on the gpu partition, from rates.yml today
    (worked out here, not by the billing code)."""
    import datetime
    import os
    import yaml
    from decimal import Decimal
    from helpers import REPO
    with open(os.path.join(REPO, "config", "rates.yml")) as f:
        rates = yaml.safe_load(f)
    prices = [p for p in rates["prices"] if str(p["from"]) <= datetime.date.today().isoformat()][-1]
    gpu_hour = int(Decimal(str(prices["gpu_hour"][rates["partitions"]["gpu"]])) * 1_000_000)
    return gpu_hour // rates["units_per_gpu"]          # micro-credits per unit-hour


def qos_limit(code):
    out = run(HEAD, f"sudo scontrol show assoc_mgr flags=qos qos=cust-{code}").stdout
    m = re.search(r"GrpTRESMins=\S*?billing=(N|\d+)\((\d+)\)", out)
    return (None if m.group(1) == "N" else int(m.group(1))), int(m.group(2))


class Installed(unittest.TestCase):
    def test_hourly_timer_is_enabled_and_the_last_run_worked(self):
        self.assertEqual(run(HEAD, "systemctl is-enabled cluster-billing-hourly.timer").stdout.strip(), "enabled")
        self.assertEqual(run(HEAD, "systemctl is-active cluster-billing-hourly.timer").stdout.strip(), "active")
        r = billing("hourly")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_admin_files_are_admin_only(self):
        self.assertEqual(run(HEAD, "sudo stat -c '%U:%G %a' /usr/local/sbin/cluster-billing").stdout.strip(), "root:root 700")
        self.assertEqual(run(HEAD, "sudo stat -c '%U:%G %a' /etc/cluster/config/customers.yml").stdout.strip(), "root:wheel 640")
        self.assertEqual(run(HEAD, "sudo stat -c '%U:%G %a' /etc/cluster/secrets/billingdb-password").stdout.strip(), "root:root 600")

    def test_customers_can_run_only_their_own_views_with_sudo(self):
        out = run(HEAD, f"sudo -l -U {A}").stdout
        allowed = [line.strip() for line in out.splitlines() if "NOPASSWD" in line]
        self.assertEqual(allowed, ["(root) NOPASSWD: /usr/local/sbin/cluster-billing customer-view *"])
        self.assertNotEqual(as_user(A, "sudo -n /usr/local/sbin/cluster-billing balance c0001").returncode, 0)


class CreditsAndLimits(unittest.TestCase):
    def test_a_grant_counts_once_and_raises_the_slurm_limit(self):
        ref = f"test-{uuid.uuid4().hex}"
        before = balance("c0002")["available"]
        self.assertEqual(billing("grant", "c0002", "1.50", "--ref", ref, "--note", "live test").returncode, 0)
        self.assertEqual(billing("grant", "c0002", "1.50", "--ref", ref, "--note", "live test").returncode, 0)
        after = balance("c0002")["available"]
        self.assertEqual(after - before, 1_500_000, "granted once, not twice")
        self.assertEqual(billing("hourly").returncode, 0)
        # The hourly run also charges jobs that ended since the last one (c0002 runs real test jobs), so the
        # limit is checked against the balance as it is now, not as it was before the run.
        now = balance("c0002")["available"]
        limit, used = qos_limit("c0002")
        self.assertEqual(limit, used + max(0, now) * 60 // unit_minutes_per_micro())
        billing("adjust", "c0002", "-1.50", "--ref", ref + "-undo", "--note", "live test: take the grant back")

    def test_sync_is_idempotent(self):
        self.assertEqual(billing("sync").returncode, 0)
        r = billing("sync")
        self.assertEqual((r.returncode, r.stdout), (0, ""), "a second sync must find nothing to change")

    def test_every_customer_runs_under_their_own_credit_limit(self):
        for code in ("c0001", "c0002"):
            with self.subTest(customer=code):
                row = run(HEAD, f"sudo sacctmgr -nP show assoc where account={code} format=user,qos,defaultqos").stdout
                account_row = [line for line in row.splitlines() if line.startswith("|")][0]
                self.assertEqual(account_row, f"|cust-{code}|cust-{code}")
                flags = run(HEAD, f"sudo sacctmgr -nP show qos cust-{code} format=flags").stdout.strip()
                self.assertIn("NoDecay", flags)

    def test_adjustment_needs_a_reason(self):
        self.assertEqual(billing("adjust", "c0001", "1", "--ref", "x").returncode, 2)

    def test_monthly_cross_check_runs_and_agrees(self):
        import datetime
        r = billing("check", datetime.date.today().strftime("%Y-%m"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("the ledger agrees with Slurm", r.stdout)

    def test_unknown_customer_is_refused(self):
        self.assertEqual(billing("grant", "c9999", "1", "--ref", "x").returncode, 2)


class WhatCustomersSee(unittest.TestCase):
    def test_credits_shows_their_own_customer(self):
        out = as_user(A2, "/usr/local/bin/credits --json")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout)["customer"], "c0001")
        out = as_user(B, "/usr/local/bin/credits --json")
        self.assertEqual(json.loads(out.stdout)["customer"], "c0002")

    def test_only_managers_get_the_statement(self):
        self.assertIn("Statement for c0001", as_user(A, "/usr/local/bin/credits").stdout)
        self.assertNotIn("Statement", as_user(A2, "/usr/local/bin/credits").stdout)

    def test_prices_and_history(self):
        out = json.loads(as_user(A2, "/usr/local/bin/prices --json").stdout)
        self.assertTrue(out)
        self.assertIn("rtx5070ti", out[-1]["prices"]["gpu_hour"])

    def test_storage(self):
        out = json.loads(as_user(B, "/usr/local/bin/mystorage --json").stdout)
        self.assertEqual(out["customer"], "c0002")
        self.assertEqual(out["limit_gib"], 1)

    def test_usage(self):
        r = as_user(A2, "/usr/local/bin/myusage --json")
        self.assertEqual(r.returncode, 0, r.stderr)
        for job in json.loads(r.stdout):
            self.assertEqual(job["username"], A2, "a plain user sees only their own jobs")

    def test_the_commands_are_there_after_a_normal_login(self):
        r = ssh_login(A2, "credits --json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["customer"], "c0001")

    def test_someone_who_is_not_a_customer_is_refused(self):
        r = run(HEAD, "/usr/local/bin/credits")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
