"""SOP-130: shared storage. /raiddrive with quotas, /cluster on every machine, NFS to the cluster network only.

Per-customer limits are tested in test_customers.py, once customers exist.
"""

import os
import unittest
import uuid

from helpers import head, hosts, run, var

HEAD = head()


class StorageServer(unittest.TestCase):
    def test_user_group_and_project_quotas_are_enforced(self):
        state = run(HEAD, "sudo xfs_quota -x -c state /raiddrive").stdout
        for kind in ("User", "Group", "Project"):
            with self.subTest(kind=kind):
                section = state.split(f"{kind} quota state")[1].split("quota state")[0]
                self.assertIn("Accounting: ON", section)
                self.assertIn("Enforcement: ON", section)

    def test_quota_options_survive_a_reboot(self):
        line = [l for l in run(HEAD, "cat /etc/fstab").stdout.splitlines() if " /raiddrive " in l]
        self.assertEqual(len(line), 1, line)
        for option in ("uquota", "gquota", "pquota"):
            self.assertIn(option, line[0].split()[3].split(","))

    def test_customer_folders_exist_and_cannot_be_listed(self):
        expected = {"/raiddrive/cluster/home": "711", "/raiddrive/cluster/projects": "711",
                    "/raiddrive/cluster/software": "755"}
        for path, mode in expected.items():
            with self.subTest(path=path):
                self.assertEqual(run(HEAD, f"stat -c '%U:%G %a' {path}").stdout.strip(), f"root:root {mode}")

    def test_cluster_path_on_the_head_node_is_the_same_storage(self):
        self.assertEqual(run(HEAD, "findmnt -no SOURCE /cluster").stdout.strip(), "/dev/md0[/cluster]")

    def test_nfs_exports_only_to_the_cluster_network(self):
        exports = run(HEAD, "sudo exportfs -v").stdout.replace("\n\t\t", " ")
        lines = [l for l in exports.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1, exports)
        self.assertTrue(lines[0].startswith(f"/raiddrive/cluster {var(HEAD, 'cluster_network')}("), lines[0])
        for option in ("rw", "root_squash", "sec=sys", "sync"):
            self.assertIn(option, lines[0].split("(")[1].rstrip(")").split(","))

    def test_nfs_version_3_is_off(self):
        self.assertIn("-3", run(HEAD, "sudo cat /proc/fs/nfsd/versions").stdout.split())

    def test_nfs_only_open_to_the_cluster_network(self):
        self.assertIn("nfs", run(HEAD, "sudo firewall-cmd --zone=cluster --list-services").stdout.split())
        self.assertNotIn("nfs", run(HEAD, "sudo firewall-cmd --zone=public --list-services").stdout.split())

    def test_nfs_server_needs_raiddrive_mounted(self):
        r = run(HEAD, "systemctl show -p RequiresMountsFor nfs-server").stdout
        self.assertIn("/raiddrive", r)


class StorageOnComputeNodes(unittest.TestCase):
    def test_every_compute_node_sees_the_same_files(self):
        marker = f"/raiddrive/cluster/software/.storage-test-{uuid.uuid4().hex}"
        run(HEAD, f"sudo touch {marker}")
        try:
            for node in hosts("compute"):
                with self.subTest(node=node):
                    self.assertEqual(run(node, "findmnt -no FSTYPE /cluster").stdout.strip(), "nfs4")
                    path = marker.replace("/raiddrive/cluster", "/cluster")
                    self.assertEqual(run(node, f"test -e {path}").returncode, 0)
        finally:
            run(HEAD, f"sudo rm -f {marker}")

    def test_root_on_a_compute_node_is_not_root_on_the_storage(self):
        for node in hosts("compute"):
            with self.subTest(node=node):
                path = f"/cluster/software/.root-squash-test-{uuid.uuid4().hex}"
                r = run(node, f"sudo touch {path}")
                self.assertNotEqual(r.returncode, 0, "root on a compute node could write to /cluster")
                run(HEAD, f"sudo rm -f {path.replace('/cluster', '/raiddrive/cluster')}")


if __name__ == "__main__":
    unittest.main()
