"""SOP-152, SOP-153, SOP-154: Slurm's controller, database, job-size rules, accounts and privacy.

Submission tests use the fixed test users (config/customers.yml). Rejections happen when a job is
submitted, so they don't need a compute node; accepted jobs are cancelled straight away.
"""

import os
import re
import shlex
import unittest

import yaml

from helpers import REPO, head, run

HEAD = head()
with open(os.path.join(REPO, "config", "customers.yml")) as f:
    CONFIG = yaml.safe_load(f)
with open(os.path.join(REPO, "ansible", "roles", "slurm_common", "defaults", "main.yml")) as f:
    SLURM = yaml.safe_load(f)
A, A2, SUSPENDED, B = "zz01", "zz02", "zz04", "zz03"


def as_user(user, command):
    """A command as a user on the login node, from their home folder."""
    return run(HEAD, f"sudo -u {user} bash -lc {shlex.quote('cd ~ && ' + command)}")


def submit(user, options):
    """sbatch as a user. Returns (job id or None, combined output)."""
    r = as_user(user, f"sbatch --parsable --job-name=cluster-test {options} --wrap 'sleep 30'")
    out = (r.stdout + r.stderr).strip()
    job = r.stdout.strip().split(";")[0] if r.returncode == 0 else None
    return job, out


def cancel(job):
    if job:
        run(HEAD, f"sudo scancel {job}")


class Daemons(unittest.TestCase):
    def test_controller_and_database_daemons_run(self):
        for service in ("munge", "mariadb", "slurmdbd", "slurmctld"):
            with self.subTest(service=service):
                self.assertEqual(run(HEAD, f"systemctl is-active {service}").stdout.strip(), "active")
                self.assertEqual(run(HEAD, f"systemctl is-enabled {service}").stdout.strip(), "enabled")

    def test_controller_answers(self):
        self.assertIn("is UP", run(HEAD, "scontrol ping").stdout)

    def test_munge_credentials_work(self):
        self.assertEqual(run(HEAD, "munge -n | unmunge").returncode, 0)

    def test_version_is_the_one_we_built(self):
        with open(os.path.join(REPO, "config", "versions.yml")) as f:
            version = yaml.safe_load(f)["slurm"]["version"]
        self.assertEqual(run(HEAD, "sinfo --version").stdout.strip(), f"slurm {version}")

    def test_partition_and_node_are_defined(self):
        out = run(HEAD, "sinfo -h -o '%P %N'").stdout
        self.assertIn("gpu*", out)


class Database(unittest.TestCase):
    def test_listens_locally_only(self):
        addrs = sorted(line.split()[3] for line in run(HEAD, "ss -Hltn sport = :3306").stdout.splitlines())
        self.assertEqual(addrs, ["127.0.0.1:3306"])

    def test_binary_logs_and_crash_safety(self):
        out = run(HEAD, "sudo mysql -N -B -e \"SHOW VARIABLES WHERE Variable_name IN "
                        "('log_bin','sync_binlog','innodb_flush_log_at_trx_commit')\"").stdout
        values = dict(line.split("\t") for line in out.splitlines())
        self.assertEqual(values, {"log_bin": "ON", "sync_binlog": "1", "innodb_flush_log_at_trx_commit": "1"})

    def test_no_anonymous_users_or_test_database(self):
        self.assertEqual(run(HEAD, "sudo mysql -N -B -e \"SELECT COUNT(*) FROM mysql.user WHERE user=''\"").stdout.strip(), "0")
        self.assertEqual(run(HEAD, "sudo mysql -N -B -e \"SHOW DATABASES LIKE 'test'\"").stdout.strip(), "")

    def test_secrets_are_root_only(self):
        self.assertEqual(run(HEAD, "sudo stat -c '%U:%G %a' /etc/cluster/secrets").stdout.strip(), "root:root 700")
        self.assertEqual(run(HEAD, "sudo stat -c '%U:%G %a' /etc/slurm/slurmdbd.conf").stdout.strip(), "slurm:slurm 600")
        self.assertNotEqual(as_user(A, "cat /etc/slurm/slurmdbd.conf").returncode, 0)


class Firewall(unittest.TestCase):
    def test_slurm_ports_open_to_the_cluster_network_only(self):
        cluster = run(HEAD, "sudo firewall-cmd --zone=cluster --list-ports").stdout.split()
        public = run(HEAD, "sudo firewall-cmd --zone=public --list-ports").stdout.split()
        for port in ("6817/tcp", f"{SLURM['slurm_srun_ports']}/tcp"):
            with self.subTest(port=port):
                self.assertIn(port, cluster)
                self.assertNotIn(port, public)


class Accounts(unittest.TestCase):
    def assocs(self):
        out = run(HEAD, "sudo sacctmgr -nP show assoc cluster=main format=account,user,grptres,maxtresperjob,maxsubmitjobs,maxjobs").stdout
        return {(p[0], p[1]): p[2:] for p in (line.split("|") for line in out.splitlines())}

    def test_every_customer_is_an_account_and_every_user_has_their_limits(self):
        assocs = self.assocs()
        defaults = CONFIG["defaults"]
        for code, c in CONFIG["customers"].items():
            with self.subTest(customer=code):
                self.assertIn((code, ""), assocs)
                if c.get("max_gpus") is not None:
                    self.assertEqual(assocs[(code, "")][0], f"gres/gpu={c['max_gpus']}")
            for name, u in (c.get("users") or {}).items():
                with self.subTest(user=name):
                    grp, per_job, max_submit, max_jobs = assocs[(code, name)]
                    gpus = u.get("max_gpus", defaults["max_gpus"])
                    self.assertEqual(grp, f"gres/gpu={gpus}")
                    self.assertEqual(per_job, f"gres/gpu={gpus}")
                    if u.get("status", "active") == "active":
                        self.assertEqual(max_submit, str(SLURM["slurm_max_queued_jobs"]))
                    else:
                        self.assertEqual((max_submit, max_jobs), ("0", "0"))

    def test_admins(self):
        out = run(HEAD, "sudo sacctmgr -nP show user papaya format=user,adminlevel").stdout.strip()
        self.assertEqual(out, "papaya|Administrator")


class Privacy(unittest.TestCase):
    def test_customers_see_only_their_own_accounts(self):
        out = as_user(B, "sacctmgr -nP show assoc format=account,user").stdout
        rows = {tuple(line.split("|")) for line in out.splitlines() if line.strip()}
        self.assertTrue(rows, "customer should see their own association")
        for account, user in rows:
            self.assertIn(user, ("", B))
            self.assertNotEqual(account, "c0001")

    def test_customers_see_only_their_own_jobs(self):
        job, out = submit(A, "--gpus=1")
        try:
            self.assertIsNotNone(job, out)
            self.assertIn(job, as_user(A, "squeue -h -o %i").stdout.split())
            self.assertNotIn(job, as_user(B, "squeue -h -o %i").stdout.split())
            self.assertNotIn(job, as_user(B, f"sacct -n -X -j {job} -o jobid").stdout)
            self.assertNotIn(job, as_user(A2, "squeue -h -o %i").stdout.split(), "same customer, other user")
        finally:
            cancel(job)


class JobRules(unittest.TestCase):
    """job_submit.lua and Slurm's own limits, on the real controller (SOP-153)."""

    def assertRejected(self, user, options, fragment):
        job, out = submit(user, options)
        cancel(job)
        self.assertIsNone(job, f"'{options}' should be rejected; got job {job}")
        self.assertIn(fragment, out)

    def test_a_normal_gpu_job_is_accepted(self):
        job, out = submit(A2, "--gpus=1")
        cancel(job)
        self.assertIsNotNone(job, out)

    def test_cpu_only_job_on_gpu_nodes(self):
        self.assertRejected(A2, "", "GPU nodes run GPU jobs only")

    def test_too_many_cpus_per_gpu(self):
        self.assertRejected(A2, f"--gpus=1 -c {SLURM['slurm_cpus_per_gpu'] + 1}", "come with at most")

    def test_too_much_memory_per_gpu(self):
        self.assertRejected(A2, f"--gpus=1 --mem={SLURM['slurm_mem_per_gpu_mb'] // 1024 + 1}G", "of memory")
        self.assertRejected(A2, f"--gpus=1 --mem-per-gpu={SLURM['slurm_mem_per_gpu_mb'] // 1024 + 1}G", "of memory")

    def test_whole_node_requests(self):
        self.assertRejected(A2, "--gpus=1 --mem=0", "--mem=0")
        self.assertRejected(A2, "--gpus=1 --exclusive", "--exclusive")

    def test_suspended_user_cannot_submit(self):
        job, out = submit(SUSPENDED, "--gpus=1")
        cancel(job)
        self.assertIsNone(job, out)

    def test_root_cannot_run_jobs(self):
        r = run(HEAD, "cd /tmp && sudo sbatch --parsable --gpus=1 --wrap true")
        if r.returncode == 0:
            cancel(r.stdout.strip())
        self.assertNotEqual(r.returncode, 0)

    def test_more_gpus_than_the_user_may_hold_never_starts(self):
        """zz02 may hold 1 GPU: a 2-GPU job is refused, or waits forever with the limit as its reason."""
        job, out = submit(A2, "--gpus=2")
        try:
            if job:
                reason = run(HEAD, f"squeue -h -j {job} -o %r").stdout.strip()
                self.assertRegex(reason, r"Assoc.*(GRES|TRES|Limit)", out)
        finally:
            cancel(job)

    def test_customers_cannot_resize_a_waiting_job(self):
        job, out = submit(A2, "--gpus=1 --hold")
        try:
            self.assertIsNotNone(job, out)
            r = as_user(A2, f"scontrol update job={job} NumCPUs=10")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("cancel it", r.stdout + r.stderr)
            r = as_user(A2, f"scontrol update job={job} TimeLimit=00:30:00")
            self.assertEqual(r.returncode, 0, r.stderr)
        finally:
            cancel(job)


if __name__ == "__main__":
    unittest.main()
