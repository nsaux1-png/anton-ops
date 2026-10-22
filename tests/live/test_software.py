"""SOP-144: the shared software in /cluster/software, used the way a customer would: modules, PyTorch on the
GPUs (one and two at a time), their own packages on top of ours, conda, the container image, and that
customers can't change any of it.

Run as test user zz01 (customer c0001, which may hold 2 GPUs).
"""

import os
import shlex
import time
import unittest
import uuid

import yaml

from helpers import REPO, head, run

HEAD = head()
USER = "zz01"
with open(os.path.join(REPO, "config", "versions.yml")) as f:
    SOFTWARE = yaml.safe_load(f)["software"]
TORCH = next(p for p in SOFTWARE["pytorch"] if p.get("default"))
MINIFORGE = SOFTWARE["miniforge"]
CONTAINER = SOFTWARE["containers"][0]
SIF = f"/cluster/software/containers/{CONTAINER['name']}.sif"
TORCH_VERSION = next(p.split("==")[1] for p in TORCH["packages"] if p.startswith("torch=="))


def as_user(command, timeout=600):
    return run(HEAD, f"sudo -u {USER} bash -lc {shlex.quote('cd ~ && ' + command)}", timeout=timeout)


def in_job(command, gpus=1, timeout=900):
    return as_user(f"srun --immediate=120 --job-name=cluster-test --time=10 --gpus={gpus} "
                   f"bash -lc {shlex.quote(command)}", timeout=timeout)


def setUpModule():
    r = run(HEAD, "sudo /usr/local/sbin/cluster-software check", timeout=120)
    if r.returncode != 0:
        raise AssertionError(f"shared software isn't all built: ./cluster software build (SOP-144)\n{r.stdout}")


class Modules(unittest.TestCase):
    def test_module_avail_lists_the_shared_software(self):
        out = as_user("module -t avail 2>&1").stdout
        self.assertIn(f"pytorch/{TORCH['version']}", out)
        self.assertIn(f"miniforge/{MINIFORGE['version']}", out)

    def test_module_load_pytorch_picks_the_default(self):
        r = as_user("module load pytorch && command -v python")
        self.assertEqual(r.stdout.strip(), f"/cluster/software/pytorch/{TORCH['version']}/bin/python", r.stderr)


class PyTorchOnTheGpus(unittest.TestCase):
    CHECK = ("import torch, time\n"
             "x = torch.randn(4096, 4096, device='cuda')\n"
             "y = (x @ x).sum().item()\n"
             "z = (x.cpu().double() @ x.cpu().double()).sum().item()\n"
             "print(torch.__version__, torch.version.cuda, torch.cuda.device_count(),\n"
             "      '%d.%d' % torch.cuda.get_device_capability(), abs(y - z) / abs(z) < 1e-3)\n")

    def test_one_gpu(self):
        r = in_job(f"module load pytorch && python -c {shlex.quote(self.CHECK)}")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        version, cuda, count, capability, agrees = r.stdout.split()[-5:]
        self.assertEqual(version, TORCH_VERSION)
        self.assertEqual(count, "1", "a 1-GPU job sees exactly one GPU")
        self.assertEqual(capability, "12.0", "Blackwell: the build must support sm_120")
        self.assertEqual(agrees, "True", "the GPU's result matches the CPU's")

    def test_two_gpus_talk_over_nccl(self):
        script = ("import os, torch, torch.distributed as dist\n"
                  "dist.init_process_group('nccl')\n"
                  "rank = dist.get_rank(); torch.cuda.set_device(rank)\n"
                  "t = torch.tensor([rank + 1.0], device='cuda')\n"
                  "dist.all_reduce(t)\n"
                  "print('sum', rank, t.item())\n"
                  "dist.destroy_process_group()\n")
        name = f"cluster-test-nccl-{uuid.uuid4().hex[:8]}.py"
        as_user(f"cat > ~/{name} <<'EOF'\n{script}EOF")
        try:
            r = in_job(f"module load pytorch && torchrun --standalone --nproc_per_node=2 ~/{name}", gpus=2)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            sums = sorted(line.split()[1:] for line in r.stdout.splitlines() if line.startswith("sum "))
            self.assertEqual(sums, [["0", "3.0"], ["1", "3.0"]])
        finally:
            as_user(f"rm -f ~/{name}")

    def test_start_up_time_over_nfs(self):
        """import torch reads its libraries from the RAID over NFS. Logged, and it must stay reasonable."""
        r = in_job("module load pytorch && python -c "
                   "'import time; t = time.time(); import torch; print(round(time.time() - t, 1))'")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        seconds = float(r.stdout.split()[-1])
        print(f"\n    import torch in a job took {seconds} s", flush=True)
        self.assertLess(seconds, 120)


class YourOwnPackagesOnTop(unittest.TestCase):
    """The recipe in the guide: a venv on top of the shared PyTorch, with only the extras in your own folder."""

    @classmethod
    def setUpClass(cls):
        cls.venv = f"~/envs/cluster-test-{uuid.uuid4().hex[:8]}"
        r = as_user(f"module load pytorch && python -m venv --system-site-packages {cls.venv} && "
                    f"source {cls.venv}/bin/activate && pip install -q tqdm 'filelock==3.13.1'")
        if r.returncode != 0:
            raise AssertionError(f"making the venv failed: {r.stdout}{r.stderr}")

    @classmethod
    def tearDownClass(cls):
        as_user(f"rm -rf {cls.venv}")

    def test_the_job_sees_both_ours_and_theirs(self):
        r = in_job(f"source {self.venv}/bin/activate && python -c "
                   "\"import torch, tqdm; print(torch.__file__); print(tqdm.__file__); print(torch.cuda.is_available())\"")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        torch_file, tqdm_file, cuda = r.stdout.split()[-3:]
        self.assertTrue(torch_file.startswith("/cluster/software/pytorch/"), torch_file)
        self.assertIn("/envs/cluster-test-", tqdm_file)
        self.assertEqual(cuda, "True")

    def test_their_version_wins_over_ours(self):
        r = as_user(f"source {self.venv}/bin/activate && python -c \"import filelock; print(filelock.__version__, filelock.__file__)\"")
        version, where = r.stdout.split()
        self.assertEqual(version, "3.13.1")
        self.assertIn("/envs/cluster-test-", where)

    def test_only_the_extras_use_their_storage(self):
        size = int(as_user(f"du -sm {self.venv} | cut -f1").stdout.strip())
        self.assertLess(size, 200, f"the venv is {size} MB: it must not have copied PyTorch")


class Conda(unittest.TestCase):
    def test_shared_conda_makes_an_environment_in_their_folder(self):
        env = f"~/envs/cluster-test-conda-{uuid.uuid4().hex[:8]}"
        try:
            r = as_user(f"module load miniforge && conda create -q -y -p {env} python=3.12 && "
                        f"conda activate {env} && python -c 'import sys; print(sys.prefix)'")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("/envs/cluster-test-conda-", r.stdout.split()[-1])
            r = in_job(f"module load miniforge && conda activate {env} && python -c 'print(42)'")
            self.assertEqual(r.stdout.split()[-1], "42", r.stderr)
        finally:
            as_user(f"rm -rf {env}; module load miniforge && conda clean -q -y --all >/dev/null 2>&1; true")


class Container(unittest.TestCase):
    def test_the_pytorch_image_runs_with_its_gpu(self):
        r = in_job(f"apptainer exec --nv {SIF} python -c "
                   "\"import torch; print(torch.cuda.device_count(), torch.cuda.is_available())\"")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.split()[-2:], ["1", "True"])


class ReadOnly(unittest.TestCase):
    def test_customers_cant_change_the_shared_software(self):
        target = f"/cluster/software/pytorch/{TORCH['version']}"
        r = as_user(f"touch {target}/x 2>&1; touch /cluster/software/modulefiles/x 2>&1; touch {SIF} 2>&1; true")
        self.assertEqual(r.stdout.count("Permission denied"), 3, r.stdout)

    def test_pip_into_the_shared_environment_is_refused(self):
        r = as_user("module load pytorch && pip install --no-user -q tqdm 2>&1; echo rc=$?")
        self.assertNotIn("rc=0", r.stdout, "pip must not be able to write into the shared environment")


if __name__ == "__main__":
    unittest.main()
