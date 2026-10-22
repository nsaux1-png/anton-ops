"""SOP-155: Slurm on the GPU nodes: slurmd, real GPU jobs, what a job can see and reach, and logins only
for users with a job on the node.

Jobs run as the fixed test users (config/customers.yml), submitted on the head node like a customer would.
"""

import os
import re
import shlex
import subprocess
import time
import unittest

import yaml

from helpers import REPO, head, hosts, run, ssh_login, var, wait_until

HEAD = head()
NODES = hosts("gpu_nodes")
with open(os.path.join(REPO, "ansible", "roles", "slurm_common", "defaults", "main.yml")) as f:
    SLURM = yaml.safe_load(f)
A, B = "zz01", "zz03"            # two test users of different customers; zz01 may hold 2 GPUs


def as_user(user, command, timeout=300):
    return run(HEAD, f"sudo -u {user} bash -lc {shlex.quote('cd ~ && ' + command)}", timeout=timeout)


def in_job(user, options, command, timeout=300):
    """srun a command as a user; gives up if the job can't start within 2 minutes."""
    return as_user(user, f"srun --immediate=120 --job-name=cluster-test --time=5 {options} "
                         f"bash -c {shlex.quote(command)}", timeout=timeout)


def setUpModule():
    """Jobs need credit: without it they wait forever (QOSGrpBillingMinutes). Fail at once instead."""
    for user in (A, B):
        code = run(HEAD, f"id -gn {user}").stdout.strip()
        limit = run(HEAD, f"sacctmgr -nP show qos cust-{code} format=grptresmins").stdout.strip()
        if not limit.startswith("billing=") or int(limit.split("=")[1]) <= 0:
            raise AssertionError(f"test customer {code} has no credit (QOS limit '{limit}'): "
                                 f"./cluster credits grant {code} 50 --ref TEST-CREDIT-<date>-{code} (SOP-211)")


def background_job(user, options, seconds=300):
    """sbatch a sleeping job; returns its id once it runs (or None)."""
    r = as_user(user, f"sbatch --parsable --job-name=cluster-test --time=10 {options} --wrap 'sleep {seconds}'")
    job = r.stdout.strip().split(";")[0] if r.returncode == 0 else None
    if job and wait_until(lambda: run(HEAD, f"squeue -h -j {job} -o %T").stdout.strip() == "RUNNING", seconds=120):
        return job
    if job:
        run(HEAD, f"sudo scancel {job}")
    raise AssertionError(f"background job didn't start: {r.stdout}{r.stderr}")


def sshd_denials(node, since):
    """SELinux denials for sshd on a node since a time (seconds since 1970), from the audit log."""
    out = run(node, f"sudo awk -v t={since} 'match($0, /audit\\(([0-9]+)\\./, m) && m[1] >= t "
                    f"&& /denied/ && /comm=\"sshd-session\"/' /var/log/audit/audit.log").stdout
    return out.splitlines()


def cancel(job):
    if job:
        run(HEAD, f"sudo scancel {job}")


class Slurmd(unittest.TestCase):
    def test_slurmd_runs_and_starts_at_boot(self):
        for node in NODES:
            with self.subTest(node=node):
                self.assertEqual(run(node, "systemctl is-active slurmd").stdout.strip(), "active")
                self.assertEqual(run(node, "systemctl is-enabled slurmd").stdout.strip(), "enabled")

    def test_node_is_up_with_all_its_gpus(self):
        usable = {"idle", "mixed", "allocated"}
        for node in NODES:
            with self.subTest(node=node):
                def state_and_gpus():
                    return run(HEAD, f"sinfo -h -N -n {node} -o '%T %G'").stdout.split()
                # "completing" passes in seconds after a job ends.
                wait_until(lambda: state_and_gpus()[0] in usable, seconds=120)
                state, gres = state_and_gpus()
                self.assertIn(state, usable)
                gres = re.sub(r"\(S:[^)]*\)", "", gres)      # sinfo adds the GPUs' CPU sockets
                self.assertEqual(gres, f"gpu:{var(node, 'slurm_gpu_type')}:{var(node, 'gpu_count')}")

    def test_a_full_share_of_anything_bills_the_same(self):
        """MAX_TRES bills the largest share: a GPU's full share of CPUs, of memory, or the GPU itself must each
        be the same number of units, never more (or a standard job would be overbilled)."""
        out = run(HEAD, "scontrol show partition gpu").stdout
        weights = dict(w.split("=") for w in re.search(r"TRESBillingWeights=(\S+)", out).group(1).split(","))
        units = SLURM["slurm_billing_units_per_gpu"]
        self.assertEqual(float(weights["CPU"]) * SLURM["slurm_cpus_per_gpu"], units)
        self.assertEqual(float(weights["GRES/gpu"]), units)
        memory_units = float(weights["Mem"].rstrip("G")) * SLURM["slurm_mem_per_gpu_mb"] / 1024
        self.assertLessEqual(memory_units, units, "a full share of memory must not bill above its GPU")
        self.assertGreater(memory_units, units - 0.01)

    def test_node_matches_config_nodes_yml(self):
        for node in NODES:
            with self.subTest(node=node):
                out = run(HEAD, f"scontrol show node {node}").stdout
                fields = dict(re.findall(r"(\w+)=(\S+)", out))
                self.assertEqual(fields["CPUTot"], str(var(node, "slurm_cpus")))
                self.assertEqual(fields["RealMemory"], str(var(node, "slurm_real_memory_mb")))
                self.assertEqual(fields["CoreSpecCount"], str(var(node, "slurm_core_spec_count")))
                reserved = var(node, "slurm_real_memory_mb") - var(node, "gpu_slots") * SLURM["slurm_mem_per_gpu_mb"]
                self.assertEqual(fields["MemSpecLimit"], str(reserved))

    def test_ports_open_to_the_cluster_network_only(self):
        for node in NODES:
            with self.subTest(node=node):
                ports = run(node, "sudo firewall-cmd --zone=cluster --list-ports").stdout.split()
                self.assertIn("6818/tcp", ports)
                self.assertIn(f"{SLURM['slurm_srun_ports']}/tcp", ports)
                self.assertIn("ssh", run(node, "sudo firewall-cmd --zone=cluster --list-services").stdout.split())
                self.assertIn(var(node, "cluster_network"),
                              run(node, "sudo firewall-cmd --zone=cluster --list-sources").stdout.split())
                public = run(node, "sudo firewall-cmd --zone=public --list-ports").stdout.split()
                self.assertNotIn("6818/tcp", public)

    def test_the_firewall_rules_survive_a_reload(self):
        """The rules are permanent, not only in the running firewall: compare the two."""
        for node in NODES:
            with self.subTest(node=node):
                for what in ("services", "ports", "sources"):
                    now = run(node, f"sudo firewall-cmd --zone=cluster --list-{what}").stdout.split()
                    saved = run(node, f"sudo firewall-cmd --permanent --zone=cluster --list-{what}").stdout.split()
                    self.assertEqual(sorted(now), sorted(saved), what)

    def test_no_plugin_errors_since_slurmd_started(self):
        for node in NODES:
            with self.subTest(node=node):
                log = run(node, "sudo tac /var/log/slurm/slurmd.log | sed '/slurmd started on/q' | tac").stdout
                # Lines from jobs ("[25.batch] error: *** JOB 25 ... CANCELLED ***") are about the job, not slurmd.
                errors = [l for l in log.splitlines() if "error:" in l and not re.search(r"\] \[\d+\.", l)]
                self.assertEqual(errors, [])


class GpuJobs(unittest.TestCase):
    def test_a_one_gpu_job_sees_exactly_one_gpu(self):
        r = in_job(A, "--gpus=1", "nvidia-smi -L")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len([l for l in r.stdout.splitlines() if l.startswith("GPU ")]), 1, r.stdout)

    def test_a_two_gpu_job_sees_exactly_two(self):
        r = in_job(A, "--gpus=2", "nvidia-smi -L")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len([l for l in r.stdout.splitlines() if l.startswith("GPU ")]), 2, r.stdout)

    def test_a_job_gets_its_share_of_cpus_and_memory(self):
        """Each GPU comes with its share of hardware threads and memory, held by the job's cgroup."""
        # The job's cgroup is the parent of its step's (Slurm 26.05 gives it an opaque name, not job_<id>).
        r = in_job(A, "--gpus=1",
                   "nproc; p=$(cut -d: -f3 /proc/self/cgroup); "
                   "while [ \"$p\" != / ] && [[ $(basename \"$p\") != step_* ]]; do p=$(dirname \"$p\"); done; "
                   "cat /sys/fs/cgroup$(dirname \"$p\")/memory.max")
        self.assertEqual(r.returncode, 0, r.stderr)
        cpus, memory = r.stdout.split()
        self.assertEqual(int(cpus), SLURM["slurm_cpus_per_gpu"])
        self.assertEqual(int(memory), SLURM["slurm_mem_per_gpu_mb"] * 1024 * 1024)

    def test_a_job_cannot_see_another_customers_processes(self):
        job = background_job(A, "--gpus=1")
        try:
            r = in_job(B, "--gpus=1", "ps -eo user= | sort -u")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn(A, r.stdout.split())
            self.assertIn(B, r.stdout.split())
        finally:
            cancel(job)

    def test_a_job_cannot_reach_the_internet_or_the_admin_proxy(self):
        proxy = f"{var(HEAD, 'cluster_ip')}/{var(HEAD, 'admin_proxy_port')}"
        r = in_job(A, "--gpus=1",
                   f"for t in 1.1.1.1/443 {proxy}; do timeout 5 bash -c \"echo > /dev/tcp/$t\" 2>/dev/null "
                   f"&& echo reached $t; done; echo done")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ["done"])

    def test_a_finished_job_is_recorded_with_its_gpus(self):
        r = as_user(A, "sbatch --parsable --wait --job-name=cluster-test --time=5 --gpus=1 --wrap true")
        self.assertEqual(r.returncode, 0, r.stderr)
        job = r.stdout.strip().split(";")[0]
        tres = wait_until(lambda: run(HEAD, f"sudo sacct -n -X -j {job} -o AllocTRES%200").stdout.strip())
        self.assertIn("gres/gpu=1", tres)
        self.assertIn(f"billing={SLURM['slurm_billing_units_per_gpu']}", tres)


class NodeLogins(unittest.TestCase):
    """pam_slurm_adopt: on a GPU node, customers log in only to a node where they have a job, and the
    login is put inside that job. Admins (group wheel) always get in."""

    def test_admin_logs_in_without_a_job(self):
        for node in NODES:
            with self.subTest(node=node):
                r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ControlPath=none", "-o", "ConnectTimeout=10",
                                    node, "true"], capture_output=True, text=True, timeout=60)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_customer_without_a_job_is_refused(self):
        for node in NODES:
            with self.subTest(node=node):
                r = ssh_login(B, "true", host=node)
                self.assertNotEqual(r.returncode, 0)

    def test_customer_with_a_job_gets_in_and_lands_in_the_job(self):
        job = background_job(A, "--gpus=1")
        try:
            node = run(HEAD, f"squeue -h -j {job} -o %N").stdout.strip()
            since = int(run(node, "date +%s").stdout)
            r = ssh_login(A, "cat /proc/self/cgroup", host=node)
            self.assertEqual(r.returncode, 0, r.stderr)
            # Adopted logins go into the job's "extern" step, under slurmstepd.
            self.assertRegex(r.stdout, r"/slurmstepd\.scope/[^/]+/step_extern/")
            self.assertEqual(sshd_denials(node, since), [])
        finally:
            cancel(job)

    def test_selinux_rules_for_it_are_loaded(self):
        for node in NODES:
            with self.subTest(node=node):
                if run(node, "getenforce").stdout.strip() == "Disabled":
                    continue
                self.assertIn("cluster_pam_slurm_adopt", run(node, "sudo semodule -l").stdout.split())


if __name__ == "__main__":
    unittest.main()
