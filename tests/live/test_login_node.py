"""SOP-145: the login node for customers. What they can reach (the internet, SSH into their own jobs, Slurm)
and can't (the office network, the BMCs, the rest of the cluster network, this machine's admin services),
including through SSH tunnels, and the limits on what one customer user can use there."""

import os
import shlex
import subprocess
import tempfile
import unittest

import yaml

from helpers import REPO, can_connect, head, hosts, run, ssh_login, var, wait_until

HEAD = head()
LOGIN = hosts("login_nodes")[0]
NODE = hosts("gpu_nodes")[0]
NODE_IP = var(NODE, "cluster_ip")
OFFICE_GATEWAY = run(HEAD, "ip route show default | awk '{print $3; exit}'").stdout.strip()
USER = "zz01"
with open(os.path.join(REPO, "ansible", "roles", "login_node", "defaults", "main.yml")) as f:
    LIMITS = yaml.safe_load(f)


def rejected():
    """Packets the login node's customer rules have refused so far (all their counters together)."""
    out = run(LOGIN, "sudo nft list table inet cluster_login_egress").stdout
    return sum(int(n) for n in __import__("re").findall(r"counter packets (\d+)", out))


def refused_by_the_rules(address, port):
    """True if a customer's connection to address:port fails *and* the rules counted it. A port nobody
    listens on fails anyway, so failing alone proves nothing."""
    before = rejected()
    failed = not can_connect(LOGIN, address, port, customer=True, seconds=3)
    return failed and rejected() > before


def ssh_with_key(user, args, timeout=60):
    """ssh as a test user with their test key, with any extra ssh arguments (tunnels, jumps)."""
    with tempfile.TemporaryDirectory() as d:
        key = os.path.join(d, "key")
        with open(key, "w") as f:
            f.write(run(HEAD, f"sudo cat /etc/cluster/test-keys/{user}").stdout)
        os.chmod(key, 0o600)
        common = ["-i", key, "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=no",
                  "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=10"]
        args = [a.replace("{common}", " ".join(shlex.quote(c) for c in common)) for a in args]
        return subprocess.run(["ssh"] + common + args, capture_output=True, text=True, timeout=timeout)


class CustomersReach(unittest.TestCase):
    def test_the_internet(self):
        self.assertTrue(can_connect(LOGIN, "1.1.1.1", 443, customer=True), "installs need the internet")

    def test_ssh_and_slurmd_on_the_compute_nodes(self):
        self.assertTrue(can_connect(LOGIN, NODE_IP, 22, customer=True))
        self.assertTrue(can_connect(LOGIN, NODE_IP, 6818, customer=True))

    def test_slurm_on_this_machine(self):
        r = run(LOGIN, f"sudo -u {USER} bash -lc 'sinfo -h -o %P && sacct -n -X -S now-1hour >/dev/null && echo ok'")
        self.assertEqual(r.stdout.strip().splitlines()[-1], "ok", r.stderr)

    def test_srun_output_comes_back(self):
        """srun's output arrives on a connection the node makes back to the login node."""
        r = run(LOGIN, f"sudo -u {USER} bash -lc 'srun --immediate=120 --time=2 --gpus=1 hostname'", timeout=300)
        self.assertEqual(r.stdout.strip(), NODE, r.stderr)


class CustomersDontReach(unittest.TestCase):
    def test_the_office_network(self):
        for port in (80, 443, 53):
            with self.subTest(port=port):
                self.assertTrue(refused_by_the_rules(OFFICE_GATEWAY, port))

    def test_other_private_ranges_and_link_local(self):
        for address in ("10.0.0.1", "192.168.0.1", "169.254.169.254", "172.16.99.200"):
            with self.subTest(address=address):
                self.assertTrue(refused_by_the_rules(address, 80))

    def test_the_rest_of_the_cluster_network(self):
        self.assertTrue(refused_by_the_rules(NODE_IP, 111))        # rpcbind
        self.assertTrue(refused_by_the_rules(NODE_IP, 9090))       # Cockpit

    def test_this_machines_admin_services(self):
        for port in LIMITS["login_blocked_local_ports"]:
            for address in ("127.0.0.1", var(HEAD, "cluster_ip")):
                with self.subTest(address=address, port=port):
                    self.assertTrue(refused_by_the_rules(address, port))

    def test_admins_are_not_limited(self):
        self.assertTrue(can_connect(LOGIN, "127.0.0.1", 3306))
        self.assertTrue(can_connect(LOGIN, NODE_IP, 111) or can_connect(LOGIN, NODE_IP, 22))


class Tunnels(unittest.TestCase):
    """SSH forwarding runs as the customer, so the same rules apply to it."""

    def test_a_tunnel_to_the_office_network_is_refused(self):
        r = ssh_with_key(USER, ["-W", f"{OFFICE_GATEWAY}:80", f"{USER}@localhost"], timeout=30)
        self.assertNotEqual(r.returncode, 0)

    def test_a_tunnel_to_an_admin_service_is_refused(self):
        r = ssh_with_key(USER, ["-W", "127.0.0.1:3306", f"{USER}@localhost"], timeout=30)
        self.assertNotEqual(r.returncode, 0)

    def test_jupyter_style_jump_into_your_own_job(self):
        """The guide's recipe: ssh -J through the login node into your job's node (then -L for Jupyter)."""
        job = run(HEAD, f"sudo -u {USER} bash -lc \"cd ~ && sbatch --parsable --job-name=cluster-test --time=5 "
                        f"--gpus=1 --wrap 'sleep 120'\"").stdout.strip().split(";")[0]
        try:
            self.assertTrue(wait_until(lambda: run(HEAD, f"squeue -h -j {job} -o %T").stdout.strip() == "RUNNING", 120))
            r = ssh_with_key(USER, ["-o", "ProxyCommand=ssh {common} -W %h:%p " + f"{USER}@localhost",
                                    f"{USER}@{NODE}", "cat /proc/self/cgroup"], timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("step_extern", r.stdout, "the hop lands inside the job")
        finally:
            run(HEAD, f"sudo scancel {job}")


class Limits(unittest.TestCase):
    def test_a_customers_session_is_limited(self):
        r = ssh_login(USER, "systemctl show user-$(id -u).slice -p MemoryMax -p MemorySwapMax "
                            "-p CPUQuotaPerSecUSec -p TasksMax")
        props = dict(line.split("=", 1) for line in r.stdout.split())
        self.assertEqual(int(props["MemoryMax"]), int(LIMITS["login_memory"].rstrip("G")) * 1024**3)
        self.assertEqual(props["MemorySwapMax"], "0")
        self.assertEqual(props["CPUQuotaPerSecUSec"], f"{LIMITS['login_cpu_percent'] // 100}s")
        self.assertEqual(props["TasksMax"], str(LIMITS["login_tasks"]))

    def test_a_program_bigger_than_the_limit_is_stopped(self):
        too_big = int(LIMITS["login_memory"].rstrip("G")) + 1
        # bytes * n really writes every page (a bytearray could stay as untouched zero pages).
        r = ssh_login(USER, f"python3 -c 'b = b\"x\" * ({too_big} * 1024**3); print(\"not stopped\")'; echo rc=$?")
        self.assertNotIn("not stopped", r.stdout)
        self.assertIn("rc=137", r.stdout, "killed by the memory limit")


if __name__ == "__main__":
    unittest.main()
