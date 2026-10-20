"""SOP-110: package repositories on every machine."""

import unittest

from helpers import hosts, run


class Repos(unittest.TestCase):
    def test_crb_is_enabled_everywhere(self):
        for host in hosts():
            with self.subTest(host=host):
                self.assertIn("crb", run(host, "dnf -q repolist --enabled | awk '{print $1}'").stdout.split())

    def test_epel_never_supplies_slurm(self):
        for host in hosts():
            with self.subTest(host=host):
                r = run(host, "dnf -q list --available --repo=epel 'slurm*' 2>&1")
                self.assertNotIn("slurm", r.stdout.replace("No matching Packages", "").lower(), r.stdout)
                self.assertIn("excludepkgs=slurm*", run(host, "cat /etc/yum.repos.d/epel.repo").stdout)


if __name__ == "__main__":
    unittest.main()
