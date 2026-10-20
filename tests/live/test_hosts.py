"""SOP-102: every machine resolves every cluster machine to its cluster address."""

import unittest

from helpers import hosts, run, var


class HostsFile(unittest.TestCase):
    def test_every_machine_resolves_every_cluster_machine(self):
        for host in hosts():
            for other in hosts():
                with self.subTest(on=host, name=other):
                    # IPv4 only: a machine also resolves its own name to its IPv6 addresses (nss myhostname).
                    r = run(host, f"getent ahostsv4 {other}")
                    self.assertEqual(r.returncode, 0, r.stderr)
                    self.assertEqual(r.stdout.split()[0], var(other, "cluster_ip"))

    def test_hosts_file_is_managed_by_ansible(self):
        for host in hosts():
            with self.subTest(host=host):
                self.assertIn("Managed by Ansible", run(host, "head -1 /etc/hosts").stdout)


if __name__ == "__main__":
    unittest.main()
