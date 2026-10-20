"""SOP-104: customer accounts on compute nodes reach only the cluster network."""

import ipaddress
import unittest

from helpers import as_customer, can_connect, first_host_address, head, hosts, run, var

HEAD = head()


def other_networks(node):
    """The node's IPv4 networks outside the cluster network, e.g. the BMC link."""
    cluster = ipaddress.ip_network(var(node, "cluster_network"))
    out = run(node, "ip -4 -o addr show scope global").stdout
    nets = {ipaddress.ip_interface(line.split()[3]).network for line in out.splitlines()}
    return [n for n in nets if not n.overlaps(cluster)]


class CustomerNetwork(unittest.TestCase):
    def test_rules_are_loaded_and_load_at_boot(self):
        for node in hosts("compute"):
            with self.subTest(node=node):
                self.assertEqual(run(node, "sudo nft list table inet cluster_egress").returncode, 0)
                self.assertEqual(run(node, "systemctl is-enabled cluster-egress").stdout.strip(), "enabled")

    def test_customer_cannot_use_the_admin_proxy(self):
        proxy = f"http://{var(HEAD, 'admin_proxy_host')}:{var(HEAD, 'admin_proxy_port')}"
        for node in hosts("compute"):
            with self.subTest(node=node):
                r = run(node, as_customer(f"curl -sS -m 10 -o /dev/null -x {proxy} https://rockylinux.org/"))
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("refused", r.stderr)

    def test_customer_cannot_reach_the_internet(self):
        for node in hosts("compute"):
            for address in ("1.1.1.1", "8.8.8.8"):
                with self.subTest(node=node, address=address):
                    self.assertFalse(can_connect(node, address, 443, customer=True))

    def test_customer_cannot_reach_the_office_network(self):
        targets = [(first_host_address(var(HEAD, "upstream_network")), 443),
                   (var(HEAD, "upstream_ip"), 22)]
        for node in hosts("compute"):
            for address, port in targets:
                with self.subTest(node=node, address=address, port=port):
                    self.assertFalse(can_connect(node, address, port, customer=True))

    def test_customer_cannot_reach_other_local_networks_like_the_bmc_link(self):
        for node in hosts("compute"):
            for net in other_networks(node):
                target = first_host_address(str(net))
                with self.subTest(node=node, network=str(net)):
                    r = run(node, as_customer(f"curl -sS -m 5 -o /dev/null http://{target}/"))
                    self.assertNotEqual(r.returncode, 0)
                    self.assertIn("No route to host", r.stderr)

    def test_customer_reaches_the_cluster_network(self):
        for node in hosts("compute"):
            with self.subTest(node=node):
                self.assertTrue(can_connect(node, var(HEAD, "cluster_ip"), 22, customer=True))

    def test_admins_are_not_limited(self):
        for node in hosts("compute"):
            with self.subTest(node=node):
                self.assertTrue(can_connect(node, var(HEAD, "cluster_ip"), var(HEAD, "admin_proxy_port")))


if __name__ == "__main__":
    unittest.main()
