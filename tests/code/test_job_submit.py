"""Tests for job_submit.lua (SOP-153): the GPU job-size rules, run in a Lua interpreter with a stand-in
for Slurm's "slurm" table. The template is filled in with the real settings from slurm_common/defaults.
"""

import json
import os
import subprocess
import tempfile
import unittest

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
with open(os.path.join(REPO, "ansible/roles/slurm_common/defaults/main.yml")) as f:
    SETTINGS = yaml.safe_load(f)
with open(os.path.join(REPO, "ansible/roles/slurm_controller/templates/job_submit.lua.j2")) as f:
    TEMPLATE = f.read()

NO_VAL = 4294967294
NO_VAL16 = 65534


def render():
    """The template with its settings filled in (the same values Ansible uses)."""
    out = TEMPLATE
    partitions = ", ".join(f'["{p}"] = true' for p in SETTINGS["slurm_gpu_partitions"])
    expression = "{{ slurm_gpu_partitions | map('regex_replace', '^(.*)$', '[\"\\\\1\"] = true') | join(', ') }}"
    assert expression in out, "the partitions expression in the template changed; update this test"
    out = out.replace(expression, partitions)
    for name in ("slurm_default_partition", "slurm_cpus_per_gpu", "slurm_mem_per_gpu_mb", "slurm_user_uid"):
        out = out.replace("{{ " + name + " }}", str(SETTINGS[name]))
    assert "{{" not in out, out
    return out


HARNESS = r"""
local messages = {}
slurm = { SUCCESS = 0, ERROR = -1, NO_VAL = %d, NO_VAL16 = %d, NO_VAL64 = -2,
          log_user = function(m) messages[#messages + 1] = m end, log_info = function(m) end }
dofile(arg[1])
local cases = load("return " .. io.read("a"))()
for i, c in ipairs(cases) do
  messages = {}
  local result
  if c.modify_uid then
    result = slurm_job_modify(c.job, {}, {}, c.modify_uid)
  else
    result = slurm_job_submit(c.job, {}, 10100)
  end
  print(string.format("%%d\t%%d\t%%s", i, result, messages[1] or ""))
end
""" % (NO_VAL, NO_VAL16)


def lua_table(value):
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k} = {lua_table(v)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "{" + ", ".join(lua_table(v) for v in value) + "}"
    if isinstance(value, str):
        return json.dumps(value)
    return str(value)


def submit(*jobs, modify_uid=None):
    """Run each job through job_submit.lua. Returns [(accepted, message)]."""
    cases = [{"job": j, **({"modify_uid": modify_uid} if modify_uid is not None else {})} for j in jobs]
    with tempfile.TemporaryDirectory() as d:
        script, harness = os.path.join(d, "job_submit.lua"), os.path.join(d, "harness.lua")
        with open(script, "w") as f:
            f.write(render())
        with open(harness, "w") as f:
            f.write(HARNESS)
        r = subprocess.run(["lua", harness, script], input=lua_table(cases), capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    out = []
    for line in r.stdout.splitlines():
        _, result, message = line.split("\t", 2)
        out.append((result == "0", message))
    return out


def one(job, **kw):
    return submit(job, **kw)[0]


class GpuJobRules(unittest.TestCase):
    def assertAccepted(self, job):
        accepted, message = one(job)
        self.assertTrue(accepted, message)

    def assertRejected(self, job, fragment):
        accepted, message = one(job)
        self.assertFalse(accepted, f"{job} should be rejected")
        self.assertIn(fragment, message)

    def test_plain_gpu_requests_are_accepted(self):
        self.assertAccepted({"partition": "gpu", "tres_per_job": "gres/gpu:1"})
        self.assertAccepted({"tres_per_job": "gres/gpu:4"})                          # default partition
        self.assertAccepted({"tres_per_node": "gres/gpu:2"})                         # --gres=gpu:2
        self.assertAccepted({"tres_per_job": "gres/gpu:rtx5070ti:3"})               # a GPU model
        self.assertAccepted({"tres_per_task": "gres/gpu:1", "num_tasks": 4})        # --gpus-per-task

    def test_cpu_only_jobs_are_rejected_on_gpu_nodes(self):
        self.assertRejected({"partition": "gpu"}, "ask for at least one GPU")
        self.assertRejected({}, "ask for at least one GPU")                          # default partition is gpu
        self.assertRejected({"tres_per_job": "gres/gpumem:1000"}, "ask for at least one GPU")
        self.assertRejected({"tres_per_job": "gres/gpu:0"}, "ask for at least one GPU")

    def test_other_partitions_are_left_alone(self):
        self.assertAccepted({"partition": "cpu"})

    def test_several_partitions_are_each_checked(self):
        self.assertRejected({"partition": "cpu,gpu"}, "ask for at least one GPU")

    def test_cpu_limit_per_gpu(self):
        per = SETTINGS["slurm_cpus_per_gpu"]
        self.assertAccepted({"tres_per_job": "gres/gpu:1", "cpus_per_task": per})
        self.assertRejected({"tres_per_job": "gres/gpu:1", "cpus_per_task": per + 1}, f"at most {per} CPUs")
        self.assertAccepted({"tres_per_job": "gres/gpu:2", "num_tasks": 2, "cpus_per_task": per})
        self.assertRejected({"tres_per_job": "gres/gpu:2", "num_tasks": 3, "cpus_per_task": per}, "at most")
        self.assertRejected({"tres_per_job": "gres/gpu:1", "min_cpus": per + 2}, "at most")
        self.assertRejected({"tres_per_job": "gres/gpu:1", "cpus_per_tres": f"gres/gpu:{per + 1}"}, "at most")
        self.assertAccepted({"tres_per_job": "gres/gpu:3", "cpus_per_tres": f"gres/gpu:{per}"})
        self.assertRejected({"tres_per_node": "gres/gpu:1", "min_nodes": 1, "ntasks_per_node": per + 1}, "at most")

    def test_memory_limit_per_gpu(self):
        mb = SETTINGS["slurm_mem_per_gpu_mb"]
        self.assertAccepted({"tres_per_job": "gres/gpu:1", "min_mem_per_node": mb})
        self.assertRejected({"tres_per_job": "gres/gpu:1", "min_mem_per_node": mb + 1}, "of memory")
        self.assertAccepted({"tres_per_job": "gres/gpu:3", "min_mem_per_node": 3 * mb})
        self.assertRejected({"tres_per_job": "gres/gpu:1", "mem_per_tres": f"gres/gpu:{mb * 2}"}, "of memory")
        self.assertAccepted({"tres_per_job": "gres/gpu:2", "mem_per_tres": f"gres/gpu:{mb}"})
        self.assertRejected({"tres_per_job": "gres/gpu:1", "cpus_per_task": 4, "min_mem_per_cpu": mb}, "of memory")
        self.assertAccepted({"tres_per_job": "gres/gpu:1", "cpus_per_task": 4, "min_mem_per_cpu": mb // 4})

    def test_whole_node_requests_are_rejected(self):
        self.assertRejected({"tres_per_job": "gres/gpu:1", "min_mem_per_node": 0}, "--mem=0")
        self.assertRejected({"tres_per_job": "gres/gpu:1", "shared": 0}, "--exclusive")
        self.assertRejected({"tres_per_job": "gres/gpu:1", "shared": 2}, "--exclusive")   # --exclusive=user

    def test_unset_values_from_slurm_are_ignored(self):
        self.assertAccepted({"tres_per_job": "gres/gpu:1", "min_cpus": NO_VAL, "cpus_per_task": NO_VAL16,
                             "num_tasks": NO_VAL, "shared": NO_VAL16, "min_mem_per_node": -2,
                             "min_mem_per_cpu": -2})

    def test_gpus_per_socket_is_refused_with_advice(self):
        self.assertRejected({"tres_per_socket": "gres/gpu:1"}, "not per socket")

    def test_messages_tell_the_customer_the_numbers(self):
        _, message = one({"tres_per_job": "gres/gpu:2", "cpus_per_task": 30})
        per = SETTINGS["slurm_cpus_per_gpu"]
        self.assertIn(f"2 GPU(s) come with at most {2 * per} CPUs ({per} cores); this job asks for 30.", message)


class ChangingWaitingJobs(unittest.TestCase):
    def test_customers_cannot_change_a_jobs_size(self):
        for field, value in [("tres_per_job", "gres/gpu:8"), ("min_mem_per_node", 999999), ("cpus_per_task", 50),
                             ("partition", "cpu"), ("shared", 0), ("min_nodes", 2)]:
            with self.subTest(field=field):
                accepted, message = one({field: value}, modify_uid=10100)
                self.assertFalse(accepted)
                self.assertIn("cancel it", message)

    def test_customers_can_change_other_things(self):
        accepted, _ = one({"name": "new-name", "time_limit": 30, "min_cpus": NO_VAL, "partition": ""},
                          modify_uid=10100)
        self.assertTrue(accepted)

    def test_root_and_slurm_can_change_anything(self):
        for uid in (0, SETTINGS["slurm_user_uid"]):
            with self.subTest(uid=uid):
                self.assertTrue(one({"tres_per_job": "gres/gpu:8"}, modify_uid=uid)[0])


if __name__ == "__main__":
    unittest.main()
