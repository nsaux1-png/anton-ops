"""SOP-105: every machine keeps time; compute nodes follow the head node."""

import re
import unittest

from helpers import head, hosts, run, var, wait_until

HEAD = head()


def tracking(host):
    out = run(host, "chronyc -n tracking").stdout
    pairs = (line.split(":", 1) for line in out.splitlines() if ":" in line)
    return {k.strip(): v.strip() for k, v in pairs}


def synced(host):
    t = tracking(host)
    return t if t.get("Leap status") == "Normal" else None


class Time(unittest.TestCase):
    def test_head_node_is_synced(self):
        t = wait_until(lambda: synced(HEAD))
        self.assertTrue(t, tracking(HEAD))
        self.assertLess(int(t["Stratum"]), 16)

    def test_compute_nodes_follow_the_head_node(self):
        for node in hosts("compute"):
            with self.subTest(node=node):
                t = wait_until(lambda: synced(node))
                self.assertTrue(t, tracking(node))
                self.assertIn(f"({var(HEAD, 'cluster_ip')})", t["Reference ID"])
                offset = float(re.match(r"([\d.]+) seconds", t["System time"]).group(1))
                self.assertLess(offset, 0.1)

    def test_head_serves_time_to_the_cluster_network_only(self):
        self.assertIn("ntp", run(HEAD, "sudo firewall-cmd --zone=cluster --list-services").stdout.split())
        self.assertNotIn("ntp", run(HEAD, "sudo firewall-cmd --zone=public --list-services").stdout.split())

    def test_chronyd_enabled_everywhere(self):
        for host in hosts():
            with self.subTest(host=host):
                self.assertEqual(run(host, "systemctl is-enabled chronyd").stdout.strip(), "enabled")


if __name__ == "__main__":
    unittest.main()
