"""SOP-143: what customers get on the login node and compute nodes. The packages that need root, Python 3.12
the same everywhere, the module command, containers without root, temporary files kept in their own space,
the welcome message and the guide. Run as the test users, the way a new customer would."""

import os
import shlex
import unittest
import uuid

import yaml

from helpers import REPO, head, hosts, run, ssh_login

HEAD = head()
LOGIN = hosts("login_nodes")
USER_MACHINES = sorted(set(LOGIN) | set(hosts("compute")))
USER = "zz01"
with open(os.path.join(REPO, "ansible", "roles", "user_environment", "defaults", "main.yml")) as f:
    ENV = yaml.safe_load(f)


def as_user(command, host=None, timeout=300):
    """A command in the test user's login shell (profile scripts included), from their home folder."""
    return run(host or HEAD, f"sudo -u {USER} bash -lc {shlex.quote('cd ~ && ' + command)}", timeout=timeout)


def in_job(command, timeout=300):
    return as_user(f"srun --immediate=120 --job-name=cluster-test --time=5 --gpus=1 bash -lc {shlex.quote(command)}",
                   timeout=timeout)


class Packages(unittest.TestCase):
    def test_every_package_everywhere_customers_work(self):
        for host in USER_MACHINES:
            with self.subTest(host=host):
                r = run(host, "rpm -q " + " ".join(ENV["user_packages"]))
                missing = [line for line in r.stdout.splitlines() if "not installed" in line]
                self.assertEqual(missing, [])

    def test_python_312_is_the_same_on_the_login_node_and_in_jobs(self):
        versions = {h: run(h, "python3.12 -c 'import sys; print(sys.version.split()[0])'").stdout.strip()
                    for h in USER_MACHINES}
        self.assertEqual(len(set(versions.values())), 1, versions)
        self.assertTrue(list(versions.values())[0].startswith("3.12."))


class Modules(unittest.TestCase):
    def test_module_command_and_the_shared_software_path(self):
        for host in LOGIN:
            with self.subTest(host=host):
                r = as_user("module avail 2>&1; echo MODULEPATH=$MODULEPATH", host)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn(f"{ENV['shared_software_dir']}/modulefiles", r.stdout)

    def test_module_command_inside_a_job(self):
        r = in_job("module --version 2>&1 && echo MODULEPATH=$MODULEPATH")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"{ENV['shared_software_dir']}/modulefiles", r.stdout)


class TemporaryFiles(unittest.TestCase):
    def test_on_the_login_node_they_go_to_the_customers_own_folder(self):
        r = as_user("echo $TMPDIR; stat -c %a $TMPDIR; python3 -c 'import tempfile; print(tempfile.gettempdir())'")
        tmpdir, mode, python_tmp = r.stdout.split()
        home = run(HEAD, f"getent passwd {USER} | cut -d: -f6").stdout.strip()
        self.assertEqual(tmpdir, f"{home}/.tmp")
        self.assertEqual(mode, "700")
        self.assertEqual(python_tmp, tmpdir)

    def test_admins_are_left_alone(self):
        self.assertEqual(run(HEAD, "bash -lc 'echo ${TMPDIR:-unset}'").stdout.strip(), "unset")

    def test_in_a_job_they_go_to_the_jobs_own_tmp(self):
        r = in_job("echo $TMPDIR")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "/tmp")


class Containers(unittest.TestCase):
    """Apptainer, without root: pull an image on the login node, run it there and in a job."""

    @classmethod
    def setUpClass(cls):
        cls.image = f"cluster-test-{uuid.uuid4().hex[:8]}.sif"
        r = as_user(f"apptainer pull --disable-cache {cls.image} docker://busybox:1.36", timeout=600)
        if r.returncode != 0:
            raise AssertionError(f"apptainer pull failed: {r.stdout}{r.stderr}")

    @classmethod
    def tearDownClass(cls):
        as_user(f"rm -f {cls.image}")

    def test_runs_on_the_login_node(self):
        r = as_user(f"apptainer exec {self.image} echo inside")
        self.assertEqual(r.stdout.strip().splitlines()[-1], "inside", r.stderr)

    def test_runs_in_a_job_and_sees_cluster(self):
        code = run(HEAD, f"id -gn {USER}").stdout.strip()
        r = in_job(f"apptainer exec {self.image} sh -c 'ls -d /cluster/projects/{code} /cluster/software && id -u'")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"/cluster/projects/{code}", r.stdout)
        self.assertEqual(r.stdout.strip().splitlines()[-1], run(HEAD, f"id -u {USER}").stdout.strip(),
                         "the container runs as the customer, not root")


class Building(unittest.TestCase):
    def test_built_on_the_login_node_runs_in_a_job(self):
        source = 'int main(){puts("built here, runs there");return 0;}'
        r = as_user(f"d=$(mktemp -d) && echo {shlex.quote('#include <stdio.h>')} > $d/a.c && "
                    f"echo {shlex.quote(source)} >> $d/a.c && gcc -O2 -o ~/cluster-test-a.out $d/a.c && rm -r $d")
        self.assertEqual(r.returncode, 0, r.stderr)
        try:
            r = in_job("~/cluster-test-a.out")
            self.assertEqual(r.stdout.strip(), "built here, runs there", r.stderr)
        finally:
            as_user("rm -f ~/cluster-test-a.out")


class FirstLogin(unittest.TestCase):
    def test_welcome_message_and_guide(self):
        for host in LOGIN:
            with self.subTest(host=host):
                welcome = run(host, "cat /etc/motd.d/cluster-welcome").stdout
                self.assertIn("/cluster/docs/guide.md", welcome)
        r = as_user("head -1 /cluster/docs/guide.md")
        self.assertIn("guide", r.stdout.lower())

    def test_a_real_login_works_and_sets_up_the_environment(self):
        r = ssh_login(USER, "bash -lc 'echo $TMPDIR; type module | head -1'")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("/.tmp", r.stdout)
        self.assertIn("module is a function", r.stdout)


if __name__ == "__main__":
    unittest.main()
