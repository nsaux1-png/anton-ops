"""Tests for cluster-slurm-accounts (SOP-154): turning customers.yml into Slurm accounts and limits."""

import importlib.machinery
import importlib.util
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
PATH = os.path.join(REPO, "ansible/roles/slurm_accounts/files/cluster-slurm-accounts")
loader = importlib.machinery.SourceFileLoader("cluster_slurm_accounts", PATH)
spec = importlib.util.spec_from_loader(loader.name, loader)
sa = importlib.util.module_from_spec(spec)
loader.exec_module(sa)

WANT = {
    "cluster": "main", "admins": ["papaya"], "max_queued_jobs": 500,
    "customers": [{"code": "c0001", "max_gpus": 2}, {"code": "c4821", "max_gpus": None}],
    "users": [{"name": "zz01", "customer": "c0001", "status": "active", "max_gpus": 4},
              {"name": "zz04", "customer": "c0001", "status": "suspended", "max_gpus": 4},
              {"name": "kx47", "customer": "c4821", "status": "active", "max_gpus": 6}],
}


def fake_sacctmgr(outputs):
    def run(*args):
        return outputs.get(args[1], "")
    return run


SETTLED = {
    "cluster": "main\n",
    "account": "admin\nc0001\nc4821\nroot\n",
    "user": "papaya|Administrator\nroot|Administrator\nzz01|None\nzz04|None\nkx47|None\n",
    "assoc": "root|||||\nadmin|||||\nc0001||gres/gpu=2|||\nc4821|||||\nadmin|papaya||||\n"
             "c0001|zz01|gres/gpu=4|gres/gpu=4|500|\nc0001|zz04|gres/gpu=4|gres/gpu=4|0|0\n"
             "c4821|kx47|gres/gpu=6|gres/gpu=6|500|\n",
}


class Plan(unittest.TestCase):
    def steps(self, outputs):
        return sa.plan(WANT, sa.read_current("main", fake_sacctmgr(outputs)))

    def test_empty_slurm_gets_everything(self):
        steps = self.steps({})
        descriptions = [d for d, _ in steps]
        self.assertEqual(descriptions[0], "add cluster main")
        for expected in ("add account admin", "add account c0001", "add account c4821", "add admin papaya",
                         "user papaya: Slurm administrator", "add user zz01 to c0001", "add user kx47 to c4821"):
            self.assertIn(expected, descriptions)
        self.assertIn("account c0001: GPUs at once -> 2", descriptions)
        self.assertNotIn("account c4821: GPUs at once -> no limit", descriptions)   # no limit is the default

    def test_settled_slurm_needs_nothing(self):
        self.assertEqual(self.steps(SETTLED), [])

    def test_user_limits(self):
        args = dict(self.steps({}))
        zz01 = [a for d, a in self.steps({}) if d.startswith("user zz01")][0]
        self.assertIn("GrpTRES=gres/gpu=4", zz01)
        self.assertIn("MaxTRESPerJob=gres/gpu=4", zz01)
        self.assertIn("MaxSubmitJobs=500", zz01)
        self.assertIn("MaxJobs=-1", zz01)
        self.assertTrue(args)

    def test_suspended_users_can_run_nothing(self):
        zz04 = [a for d, a in self.steps({}) if d.startswith("user zz04")][0]
        self.assertIn("MaxSubmitJobs=0", zz04)
        self.assertIn("MaxJobs=0", zz04)

    def test_a_changed_limit_is_one_modify(self):
        outputs = dict(SETTLED, assoc=SETTLED["assoc"].replace("c4821|kx47|gres/gpu=6|gres/gpu=6|500|",
                                                               "c4821|kx47|gres/gpu=2|gres/gpu=2|500|"))
        steps = self.steps(outputs)
        self.assertEqual(len(steps), 1)
        description, args = steps[0]
        self.assertIn("gpus 2 -> 6", description)
        self.assertEqual(args[:6], ["modify", "user", "where", "name=kx47", "account=c4821", "cluster=main"])

    def test_customer_limit_removed(self):
        outputs = dict(SETTLED, assoc=SETTLED["assoc"].replace("c4821|||||", "c4821||gres/gpu=8|||"))
        [(description, args)] = self.steps(outputs)
        self.assertEqual(description, "account c4821: GPUs at once -> no limit")
        self.assertIn("GrpTRES=gres/gpu=-1", args)

    def test_users_who_left_are_never_deleted(self):
        outputs = dict(SETTLED, assoc=SETTLED["assoc"] + "c0001|gone|gres/gpu=4|gres/gpu=4|0|0\n")
        self.assertEqual(self.steps(outputs), [])

    def test_gpu_limit_parsing(self):
        self.assertEqual(sa.gpu_limit("cpu=4,gres/gpu=2"), 2)
        self.assertEqual(sa.gpu_limit(""), sa.UNLIMITED)
        self.assertEqual(sa.gpu_limit("gres/gpumem=100"), sa.UNLIMITED)


if __name__ == "__main__":
    unittest.main()
