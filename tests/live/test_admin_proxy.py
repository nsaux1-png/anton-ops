"""SOP-103: the admin web proxy on the head node, and the head node's cluster firewall zone."""

import unittest
import uuid

from helpers import can_connect, head, hosts, run, var

HEAD = head()
PORT = var(HEAD, "admin_proxy_port")


class AdminProxy(unittest.TestCase):
    def test_squid_is_running_and_enabled(self):
        self.assertEqual(run(HEAD, "systemctl is-active squid").stdout.strip(), "active")
        self.assertEqual(run(HEAD, "systemctl is-enabled squid").stdout.strip(), "enabled")

    def test_listens_on_the_cluster_address_only(self):
        r = run(HEAD, f"ss -Hltn sport = :{PORT}")
        listening = sorted(line.split()[3] for line in r.stdout.splitlines())
        self.assertEqual(listening, [f"{var(HEAD, 'cluster_ip')}:{PORT}"])

    def test_upstream_zone_does_not_open_it(self):
        services = run(HEAD, "sudo firewall-cmd --zone=public --list-services").stdout.split()
        self.assertNotIn("squid", services)

    def test_cluster_zone_covers_the_cluster_network(self):
        self.assertEqual(run(HEAD, "sudo firewall-cmd --zone=cluster --list-sources").stdout.split(),
                         [var(HEAD, "cluster_network")])
        services = run(HEAD, "sudo firewall-cmd --zone=cluster --list-services").stdout.split()
        self.assertIn("squid", services)
        self.assertIn("ssh", services)

    def test_admin_on_each_compute_node_gets_through_and_is_logged(self):
        for node in hosts("compute"):
            with self.subTest(node=node):
                tag = uuid.uuid4().hex
                # The tag goes in the path: squid leaves query strings out of its log.
                r = run(node, 'bash -lc "curl -sS -m 30 -o /dev/null -w %{http_code} '
                              f'http://dl.rockylinux.org/cluster-test-{tag}"')
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertRegex(r.stdout, r"^\d{3}$")
                logged = run(HEAD, f"sudo grep 'cluster-test-{tag}' /var/log/squid/access.log").stdout
                self.assertEqual(len(logged.splitlines()), 1, logged)
                self.assertIn(var(node, "cluster_ip"), logged)

    def test_admin_shells_on_compute_nodes_get_the_proxy(self):
        for node in hosts("compute"):
            with self.subTest(node=node):
                r = run(node, 'bash -lc "echo $https_proxy"')
                self.assertEqual(r.stdout.strip(), f"http://{var(node, 'admin_proxy_host')}:{PORT}")

    def test_dnf_on_compute_nodes_uses_the_proxy(self):
        for node in hosts("compute"):
            with self.subTest(node=node):
                r = run(node, "grep -x 'proxy=.*' /etc/dnf/dnf.conf")
                self.assertEqual(r.stdout.strip(), f"proxy=http://{var(node, 'admin_proxy_host')}:{PORT}")

    def test_admins_on_compute_nodes_can_reach_it(self):
        for node in hosts("compute"):
            with self.subTest(node=node):
                self.assertTrue(can_connect(node, var(HEAD, "cluster_ip"), PORT))


if __name__ == "__main__":
    unittest.main()
