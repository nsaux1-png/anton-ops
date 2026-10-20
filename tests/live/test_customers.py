"""SOP-141 and SOP-142: customers' accounts, folders, storage limits and logins.

Uses the fixed test accounts in config/customers.yml:
  c0001: zz01 (manager), zz02, zz04 (always suspended)      c0002: zz03
"""

import os
import shlex
import subprocess
import tempfile
import unittest
import uuid

import yaml

from helpers import REPO, head, hosts, run

HEAD = head()
with open(os.path.join(REPO, "config", "customers.yml")) as f:
    CONFIG = yaml.safe_load(f)
with open(os.path.join(REPO, "config", "uids.yml")) as f:
    UIDS = yaml.safe_load(f)
A, A2, SUSPENDED, B = "zz01", "zz02", "zz04", "zz03"
CUST_A, CUST_B = "c0001", "c0002"
GIB_MIB = 1024


def limit_gib(code):
    return CONFIG["customers"][code].get("storage_gb", CONFIG["defaults"]["storage_gb"])


def as_user(user, command, host=None):
    """Run a command as a user on a machine (no login), through sudo."""
    return run(host or HEAD, f"sudo -u {user} bash -c {shlex.quote(command)}")


def ssh_login(user, command, key_user=None, key_file=None, host="localhost"):
    """Log in over SSH as user with their test key (or another key) and run a command."""
    with tempfile.TemporaryDirectory() as d:
        key = key_file
        if key is None:
            key = os.path.join(d, "key")
            with open(key, "w") as f:
                f.write(run(HEAD, f"sudo cat /etc/cluster/test-keys/{key_user or user}").stdout)
            os.chmod(key, 0o600)
        return subprocess.run(
            ["ssh", "-i", key, "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=no",
             "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=10",
             f"{user}@{host}", command], capture_output=True, text=True, timeout=120)


def group_used_kib(gid):
    out = run(HEAD, "sudo xfs_quota -x -c 'report -g -b -N -n' /raiddrive").stdout
    for line in out.splitlines():
        parts = line.split()
        if parts and parts[0] == f"#{gid}":
            return int(parts[1])
    return 0


class Accounts(unittest.TestCase):
    def test_every_machine_has_the_customers_and_users_with_fixed_ids(self):
        for host in hosts():
            for code in (CUST_A, CUST_B):
                with self.subTest(host=host, group=code):
                    self.assertEqual(run(host, f"getent group {code}").stdout.split(":")[2], str(UIDS["groups"][code]))
            for user in (A, A2, SUSPENDED, B):
                with self.subTest(host=host, user=user):
                    name, _, uid, gid, gecos, home, shell = run(host, f"getent passwd {user}").stdout.strip().split(":")
                    self.assertEqual(int(uid), UIDS["users"][user])
                    code = CUST_B if user == B else CUST_A
                    self.assertEqual(int(gid), UIDS["groups"][code])
                    self.assertEqual(gecos, "", "real names must never be in /etc/passwd")
                    self.assertEqual(home, f"/cluster/home/{user}")
                    self.assertEqual(shell, "/sbin/nologin" if user == SUSPENDED else "/bin/bash")
                    self.assertEqual(run(host, f"id -Gn {user}").stdout.split(), [code], "only the customer's group")

    def test_no_passwords(self):
        for host in hosts():
            for user in (A, A2, SUSPENDED, B):
                with self.subTest(host=host, user=user):
                    self.assertEqual(run(host, f"sudo getent shadow {user}").stdout.split(":")[1], "!!")

    def test_suspended_user_is_expired(self):
        for host in hosts():
            with self.subTest(host=host):
                self.assertEqual(run(host, f"sudo getent shadow {SUSPENDED}").stdout.strip().split(":")[7], "1")


class Folders(unittest.TestCase):
    def test_home_and_project_folders(self):
        for user in (A, A2, SUSPENDED, B):
            with self.subTest(user=user):
                code = CUST_B if user == B else CUST_A
                self.assertEqual(run(HEAD, f"stat -c '%U:%G %a' /cluster/home/{user}").stdout.strip(), f"{user}:{code} 700")
        for code in (CUST_A, CUST_B):
            with self.subTest(project=code):
                self.assertEqual(run(HEAD, f"stat -c '%U:%G %a' /cluster/projects/{code}").stdout.strip(), f"root:{code} 2770")

    def test_customers_cannot_see_each_others_files(self):
        for command in (f"ls /cluster/home/{A}", f"ls /cluster/projects/{CUST_A}", "ls /cluster/home", "ls /cluster/projects"):
            with self.subTest(command=command):
                self.assertNotEqual(as_user(B, command).returncode, 0)

    def test_users_cannot_see_each_others_homes_even_in_the_same_customer(self):
        self.assertNotEqual(as_user(A2, f"ls /cluster/home/{A}").returncode, 0)

    def test_project_folder_is_shared_within_the_customer(self):
        name = f"/cluster/projects/{CUST_A}/share-test-{uuid.uuid4().hex}"
        try:
            self.assertEqual(as_user(A, f"echo hi > {name}").returncode, 0)
            self.assertEqual(run(HEAD, f"sudo stat -c %G {name}").stdout.strip(), CUST_A)
            self.assertEqual(as_user(A2, f"cat {name}").stdout.strip(), "hi")
            self.assertNotEqual(as_user(B, f"cat {name}").returncode, 0)
        finally:
            run(HEAD, f"sudo rm -f {name}")


class StorageLimits(unittest.TestCase):
    def test_group_and_project_limits_match_the_config(self):
        for kind in ("g", "p"):
            out = run(HEAD, f"sudo xfs_quota -x -c 'report -{kind} -b -N -n' /raiddrive").stdout
            limits = {p[0]: int(p[3]) for p in (line.split() for line in out.splitlines()) if p and p[0].startswith("#")}
            for code in (CUST_A, CUST_B):
                with self.subTest(kind=kind, customer=code):
                    self.assertEqual(limits.get(f"#{UIDS['groups'][code]}"), limit_gib(code) * 1024 * 1024)

    def test_folders_carry_the_customers_project_id(self):
        for path, code in ((f"/raiddrive/cluster/home/{A}", CUST_A), (f"/raiddrive/cluster/home/{B}", CUST_B),
                           (f"/raiddrive/cluster/projects/{CUST_A}", CUST_A)):
            with self.subTest(path=path):
                self.assertEqual(run(HEAD, f"sudo xfs_io -c lsproj {path}").stdout.strip(),
                                 f"projid = {UIDS['groups'][code]}")

    def test_df_inside_a_customers_folder_shows_their_limit(self):
        size = as_user(A2, f"df -BM --output=size /cluster/home/{A2} | tail -1").stdout.strip()
        self.assertEqual(size, f"{limit_gib(CUST_A) * GIB_MIB}M")

    def test_writing_past_the_limit_fails(self):
        path = f"/cluster/home/{A2}/fill-{uuid.uuid4().hex}"
        try:
            r = as_user(A2, f"dd if=/dev/zero of={path} bs=1M count={limit_gib(CUST_A) * GIB_MIB + 64} status=none")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("Disk quota exceeded", r.stderr)
        finally:
            run(HEAD, f"sudo rm -f {path}")

    def test_changing_a_files_project_does_not_escape_the_limit(self):
        """The review's finding: a file's owner can change its project ID. The group quota still counts it."""
        path = f"/cluster/home/{A2}/escape-{uuid.uuid4().hex}"
        gid = UIDS["groups"][CUST_A]
        try:
            as_user(A2, f"dd if=/dev/zero of={path} bs=1M count=64 status=none && sync")
            before = group_used_kib(gid)
            as_user(A2, f"chattr -p 0 {path}")       # may or may not be allowed; either way...
            run(HEAD, "sync")
            self.assertEqual(group_used_kib(gid), before, "the file must still count against the customer")
            self.assertGreaterEqual(before, 64 * 1024)
        finally:
            run(HEAD, f"sudo rm -f {path}")

    def test_files_cannot_be_moved_to_another_customers_group(self):
        path = f"/cluster/home/{A2}/chgrp-{uuid.uuid4().hex}"
        try:
            as_user(A2, f"touch {path}")
            r = as_user(A2, f"chgrp {CUST_B} {path}")
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(run(HEAD, f"sudo stat -c %G {path}").stdout.strip(), CUST_A)
        finally:
            run(HEAD, f"sudo rm -f {path}")


class Logins(unittest.TestCase):
    def test_customer_logs_in_with_their_key(self):
        r = ssh_login(A, "id -un")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), A)

    def test_customer_cannot_add_their_own_keys(self):
        with tempfile.TemporaryDirectory() as d:
            key = os.path.join(d, "own")
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key], check=True)
            with open(key + ".pub") as f:
                pub = f.read().strip()
            as_user(A, f"mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo {shlex.quote(pub)} >> ~/.ssh/authorized_keys "
                       f"&& chmod 600 ~/.ssh/authorized_keys")
            try:
                r = ssh_login(A, "true", key_file=key)
                self.assertNotEqual(r.returncode, 0, "a key the customer added must not work")
            finally:
                run(HEAD, f"sudo rm -rf /cluster/home/{A}/.ssh")

    def test_suspended_user_cannot_log_in(self):
        r = ssh_login(SUSPENDED, "true")
        self.assertNotEqual(r.returncode, 0)

    def test_sshd_rules_for_customers(self):
        def setting(user, addr, key):
            out = run(HEAD, f"sudo sshd -T -C user={user},host=test,addr={addr}").stdout
            return dict(line.split(" ", 1) for line in out.splitlines() if " " in line)[key]
        self.assertEqual(setting(A, "127.0.0.1", "passwordauthentication"), "no")
        self.assertEqual(setting(A, "127.0.0.1", "authorizedkeysfile"), "/etc/ssh/authorized_keys/%u")
        self.assertEqual(setting(A, "127.0.0.1", "pubkeyauthentication"), "yes")
        self.assertEqual(setting(A, "203.0.113.5", "pubkeyauthentication"), "no", "test users only log in locally")

    def test_customers_have_no_sudo_except_their_billing_views(self):
        out = run(HEAD, f"sudo -l -U {A}").stdout
        allowed = [line.strip() for line in out.splitlines() if "NOPASSWD" in line or "(ALL)" in line]
        self.assertEqual(allowed, ["(root) NOPASSWD: /usr/local/sbin/cluster-billing customer-view *"])

    def test_customers_see_only_their_own_processes(self):
        r = ssh_login(A, "ps -eo user= | sort -u; test -e /proc/1 && echo SEES_PID1; true")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), [A])

    def test_user_services_dont_reveal_other_processes(self):
        """systemd-run --user starts processes outside the login; they must not see others' processes either."""
        r = ssh_login(A, "systemd-run --user --wait --pipe --quiet ps -eo user= 2>/dev/null | sort -u")
        seen = set(r.stdout.split())
        self.assertTrue(seen <= {A}, f"saw processes of {seen - {A}}")


if __name__ == "__main__":
    unittest.main()
