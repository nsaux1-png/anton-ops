"""SOP-132: each job's private /tmp on the node's scratch disk, and its own /dev/shm. Run as two test users of
different customers, at the same time, the way two customers' jobs would share a node."""

import shlex
import unittest
import uuid

from helpers import head, hosts, run, ssh_login, var, wait_until

HEAD = head()
NODES = hosts("gpu_nodes")
A, B = "zz01", "zz03"            # customers c0001 and c0002


def as_user(user, command, timeout=600):
    return run(HEAD, f"sudo -u {user} bash -lc {shlex.quote('cd ~ && ' + command)}", timeout=timeout)


def in_job(user, command, timeout=600):
    return as_user(user, f"srun --immediate=120 --job-name=cluster-test --time=5 --gpus=1 bash -c {shlex.quote(command)}",
                   timeout=timeout)


def background_job(user, script):
    r = as_user(user, f"sbatch --parsable --job-name=cluster-test --time=10 --gpus=1 --wrap {shlex.quote(script)}")
    job = r.stdout.strip().split(";")[0]
    if not job or not wait_until(lambda: run(HEAD, f"squeue -h -j {job} -o %T").stdout.strip() == "RUNNING", 120):
        run(HEAD, f"sudo scancel {job}")
        raise AssertionError(f"background job didn't start: {r.stdout}{r.stderr}")
    return job


class ScratchDisk(unittest.TestCase):
    def test_scratch_is_the_nodes_own_disk_on_the_host_and_in_slurmd(self):
        """Checked in PID 1's and slurmd's mount namespaces: an SSH session has its own (ProtectProc), and on
        2026-10-21 /scratch was mounted only there."""
        for node in NODES:
            device = run(node, f"readlink -f {var(node, 'scratch_device')}").stdout.strip()
            for who, pid in (("host", "1"), ("slurmd", "$(pidof slurmd)")):   # pidof under sudo: our own session hides root's processes
                with self.subTest(node=node, namespace=who):
                    out = run(node, f"sudo sh -c 'nsenter -t {pid} -m findmnt -n -o SOURCE,FSTYPE /scratch'").stdout.split()
                    self.assertEqual(out, [device, "xfs"])
                self.assertIn("nofail", run(node, "findmnt -s -n -o OPTIONS /scratch").stdout,
                              "a dead scratch disk mustn't stop the node from booting")

    def test_slurm_reports_it_as_the_nodes_temporary_space(self):
        for node in NODES:
            with self.subTest(node=node):
                tmp_disk = run(HEAD, f"scontrol show node {node} | grep -o 'TmpDisk=[0-9]*'").stdout.strip()
                self.assertGreater(int(tmp_disk.split("=")[1]), 1_000_000, tmp_disk)     # MB: more than 1 TB


class PrivateTmp(unittest.TestCase):
    def test_a_jobs_tmp_is_its_own_on_the_scratch_disk(self):
        r = in_job(A, "stat -c '%U %a' /tmp; ls -A /tmp | wc -l; df --output=source /tmp | tail -1")
        self.assertEqual(r.returncode, 0, r.stderr)
        owner_mode, count, tmp_source = r.stdout.strip().splitlines()[-3:]
        self.assertEqual(owner_mode, f"{A} 700")
        self.assertEqual(count, "0", "a job's /tmp starts empty")
        # The scratch device itself: comparing with /scratch's own source would pass even with it unmounted.
        device = run(NODES[0], f"readlink -f {var(NODES[0], 'scratch_device')}").stdout.strip()
        self.assertEqual(tmp_source, device, "a job's /tmp is on the scratch disk")

    def test_two_customers_jobs_dont_see_each_others_tmp_or_shm(self):
        secret = f"cluster-test-{uuid.uuid4().hex[:8]}"
        job = background_job(A, f"echo hush > /tmp/{secret}; echo hush > /dev/shm/{secret}; sleep 300")
        try:
            r = in_job(B, f"ls -A /tmp /dev/shm; find /scratch -name '{secret}' 2>/dev/null; "
                          f"cat /scratch/slurm/*/*/{secret} 2>/dev/null; true")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn(secret, r.stdout, "another customer's job saw the file's name")
            self.assertNotIn("hush", r.stdout, "another customer's job read the file")
        finally:
            run(HEAD, f"sudo scancel {job}")

    def test_a_jobs_tmp_is_gone_when_it_ends(self):
        r = in_job(A, "echo here > /tmp/x; echo $SLURM_JOB_ID")
        job = r.stdout.strip().splitlines()[-1]
        for node in NODES:
            gone = wait_until(lambda: run(node, f"sudo find /scratch/slurm -maxdepth 1 -name '{job}*' | wc -l")
                              .stdout.strip() == "0", seconds=60)
            self.assertTrue(gone, f"job {job}'s folder is still on {node}")

    def test_big_writes_stay_off_the_system_disk(self):
        for node in NODES:
            before = int(run(node, "df --output=used / | tail -1").stdout)
            r = in_job(A, "dd if=/dev/zero of=/tmp/big bs=1M count=2048 status=none && "
                          "df --output=used / | tail -1")
            self.assertEqual(r.returncode, 0, r.stderr)
            during = int(r.stdout.split()[-1])
            self.assertLess(during - before, 500_000, "2 GB in a job's /tmp grew the system disk")   # KB


class AdoptedLogins(unittest.TestCase):
    def test_a_login_into_your_job_sees_its_tmp(self):
        marker = f"cluster-test-{uuid.uuid4().hex[:8]}"
        job = background_job(A, f"touch /tmp/{marker}; sleep 300")
        try:
            node = run(HEAD, f"squeue -h -j {job} -o %N").stdout.strip()
            r = ssh_login(A, f"ls /tmp", host=node)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(marker, r.stdout.split())
        finally:
            run(HEAD, f"sudo scancel {job}")


if __name__ == "__main__":
    unittest.main()
