"""A new customer's first day, as test user zz05 of test customer c0003. Both were added with the real
onboarding commands (SOP-210): ./cluster customer add --test, ./cluster user add. Everything here goes
through a real SSH login with their own key, the way a customer works: looking around, copying files in,
installing a package, a training-style job that saves a checkpoint, interactive sessions, job arrays, and
the common mistakes, each of which must fail with a message that says why.
"""

import os
import shlex
import subprocess
import tempfile
import unittest
import uuid

import yaml

from helpers import REPO, head, hosts, run, wait_until

HEAD = head()
NODE = hosts("gpu_nodes")[0]
USER, CODE = "zz05", "c0003"
with open(os.path.join(REPO, "config", "customers.yml")) as f:
    CUSTOMER = yaml.safe_load(f)["customers"].get(CODE)


class Login:
    """A real SSH session as the new user, with their own key, on the login node."""

    def __init__(self):
        self.dir = tempfile.TemporaryDirectory()
        self.key = os.path.join(self.dir.name, "key")
        with open(self.key, "w") as f:
            f.write(run(HEAD, f"sudo cat /etc/cluster/test-keys/{USER}").stdout)
        os.chmod(self.key, 0o600)
        self.opts = ["-i", self.key, "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=no",
                     "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=10"]

    def run(self, command, timeout=600):
        """A command in a login shell (as after an interactive login: profile scripts, module command)."""
        return subprocess.run(["ssh"] + self.opts + [f"{USER}@localhost", f"bash -lc {shlex.quote(command)}"],
                              capture_output=True, text=True, timeout=timeout)

    def scp_in(self, local, remote):
        return subprocess.run(["scp", "-q"] + self.opts + [local, f"{USER}@localhost:{remote}"],
                              capture_output=True, text=True, timeout=120)


def setUpModule():
    global ME
    if not CUSTOMER or USER not in (CUSTOMER.get("users") or {}):
        raise AssertionError(f"{USER} of {CODE} isn't in customers.yml: onboard them first (SOP-210)")
    ME = Login()
    r = ME.run("credits --json")
    try:
        available = yaml.safe_load(r.stdout)["available"]
    except Exception:
        available = None
    if r.returncode != 0 or not available or available <= 0:
        raise AssertionError(f"{CODE} needs test credit: ./cluster credits grant {CODE} 50 --ref TEST-CREDIT-<date>-{CODE}\n"
                             f"{r.stdout}{r.stderr}")


def tearDownModule():
    ME.run("rm -rf ~/cluster-test-*")
    ME.dir.cleanup()


class LookingAround(unittest.TestCase):
    def test_their_credit_prices_and_storage(self):
        credit = yaml.safe_load(ME.run("credits --json").stdout)
        self.assertEqual(credit["customer"], CODE)
        self.assertGreater(credit["available"], 0)
        prices = yaml.safe_load(ME.run("prices --json").stdout)
        self.assertTrue(prices[-1]["prices"]["gpu_hour"])
        storage = yaml.safe_load(ME.run("mystorage --json").stdout)
        self.assertEqual(storage["limit_gib"], CUSTOMER["storage_gb"])

    def test_the_gpus_and_the_software(self):
        r = ME.run("sinfo -h -o '%P %G'; module -t avail 2>&1")
        self.assertIn("gpu", r.stdout)
        self.assertIn("pytorch/", r.stdout)

    def test_their_folders(self):
        r = ME.run(f"echo $HOME; stat -c %a $HOME; touch /cluster/projects/{CODE}/cluster-test-p && echo project-ok")
        home, mode, project = r.stdout.split()
        self.assertEqual(home, f"/cluster/home/{USER}")
        self.assertEqual(mode, "700")
        self.assertEqual(project, "project-ok")


class GettingDataAndSoftwareIn(unittest.TestCase):
    def test_copying_a_file_in_with_scp(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("dataset row 1\n")
        try:
            r = ME.scp_in(f.name, "cluster-test-data.txt")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(ME.run("cat ~/cluster-test-data.txt").stdout, "dataset row 1\n")
        finally:
            os.unlink(f.name)

    def test_downloading_on_the_login_node(self):
        r = ME.run("curl -fsS -o ~/cluster-test-dl.txt https://pypi.org/simple/tqdm/ && wc -c < ~/cluster-test-dl.txt")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertGreater(int(r.stdout.split()[-1]), 100)

    def test_their_own_package_on_top_of_the_shared_pytorch(self):
        r = ME.run("module load pytorch && python -m venv --system-site-packages ~/cluster-test-venv && "
                   "source ~/cluster-test-venv/bin/activate && pip install -q tqdm && python -c 'import tqdm, torch; print(\"ok\")'")
        self.assertEqual(r.stdout.strip().splitlines()[-1], "ok", r.stderr)


class FirstJobs(unittest.TestCase):
    TRAIN = """#!/bin/bash
#SBATCH --job-name=cluster-test-train
#SBATCH --gpus=1
#SBATCH --time=00:05:00
#SBATCH --signal=B:USR1@60
#SBATCH --output=cluster-test-train-%j.out
module load pytorch
save() { echo "checkpoint saved" ; touch ~/cluster-test-checkpoint; }
trap save USR1
python - <<'PY'
import torch
x = torch.randn(2048, 2048, device="cuda")
print("trained on", torch.cuda.get_device_name(0), round((x @ x).norm().item()) > 0)
PY
"""

    def test_a_training_job_from_the_guide(self):
        name = f"cluster-test-train-{uuid.uuid4().hex[:6]}.sh"
        ME.run(f"cat > ~/{name} <<'EOF'\n{self.TRAIN}EOF")
        r = ME.run(f"sbatch --parsable --wait ~/{name}", timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        job = r.stdout.strip().split(";")[0]
        out = ME.run(f"cat ~/cluster-test-train-{job}.out").stdout
        self.assertIn("trained on NVIDIA GeForce RTX 5070 Ti True", out)
        st = ME.run(f"sacct -n -X -j {job} -o State").stdout.split()
        self.assertEqual(st, ["COMPLETED"])
        run(HEAD, "sudo /usr/local/sbin/cluster-billing hourly")
        usage = yaml.safe_load(ME.run("myusage --json").stdout)
        mine = [u for u in usage if str(u["job_id"]) == job]
        self.assertEqual(len(mine), 1, "their job shows in their usage")
        self.assertGreater(mine[0]["charged"], 0)

    def test_an_interactive_session(self):
        r = ME.run("script -qec \"srun --immediate=120 --pty --gpus=1 --time=2 bash -c 'nvidia-smi -L | wc -l'\" /dev/null")
        self.assertEqual(r.stdout.strip().splitlines()[-1].strip(), "1", r.stdout + r.stderr)

    def test_a_job_array(self):
        r = ME.run("sbatch --parsable --wait --array=1-3 --gpus=1 --time=2 --output=cluster-test-array-%a.out "
                   "--wrap 'echo task $SLURM_ARRAY_TASK_ID'", timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = ME.run("cat ~/cluster-test-array-*.out").stdout.split("\n")
        self.assertEqual(sorted(line for line in out if line), ["task 1", "task 2", "task 3"])

    def test_data_from_the_project_folder_inside_a_job(self):
        ME.run(f"echo shared-data > /cluster/projects/{CODE}/cluster-test-shared.txt")
        r = ME.run(f"srun --immediate=120 --gpus=1 --time=2 cat /cluster/projects/{CODE}/cluster-test-shared.txt")
        self.assertEqual(r.stdout.strip(), "shared-data", r.stderr)
        ME.run(f"rm -f /cluster/projects/{CODE}/cluster-test-shared.txt /cluster/projects/{CODE}/cluster-test-p")


class CommonMistakes(unittest.TestCase):
    """Each fails, and the message says why."""

    def submit(self, options, script="true"):
        return ME.run(f"sbatch --parsable {options} --wrap {shlex.quote(script)}")

    def assertRefused(self, r, fragment):
        if r.returncode == 0:
            run(HEAD, f"sudo scancel {r.stdout.strip().split(';')[0]}")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn(fragment.lower(), (r.stdout + r.stderr).lower())

    def test_forgetting_the_gpu(self):
        self.assertRefused(self.submit("--time=5"), "GPU nodes run GPU jobs only")

    def test_too_long(self):
        self.assertRefused(self.submit("--gpus=1 --time=8-00:00:00"), "time limit")

    def test_windows_line_endings(self):
        ME.run("printf '#!/bin/bash\\r\\n#SBATCH --gpus=1\\r\\nhostname\\r\\n' > ~/cluster-test-dos.sh")
        r = ME.run("sbatch ~/cluster-test-dos.sh")
        self.assertRefused(r, "DOS line breaks")

    def test_the_whole_node(self):
        self.assertRefused(self.submit("--gpus=1 --mem=0"), "--mem=0")

    def test_more_gpus_than_the_company_may_hold(self):
        too_many = CUSTOMER["max_gpus"] + 1
        r = self.submit(f"--gpus={too_many} --time=5")
        if r.returncode == 0:
            job = r.stdout.strip().split(";")[0]
            try:
                reason = wait_until(lambda: (lambda x: x if x and x != "None" else None)(
                    run(HEAD, f"squeue -h -j {job} -o %r").stdout.strip()), seconds=60)
                self.assertRegex(reason or "", r"(Assoc|QOS).*(GRES|TRES|Limit)", "it must wait, saying why")
                self.assertEqual(run(HEAD, f"squeue -h -j {job} -o %T").stdout.strip(), "PENDING")
            finally:
                run(HEAD, f"sudo scancel {job}")

    def test_pip_install_inside_a_job_fails_fast(self):
        r = ME.run("srun --immediate=120 --gpus=1 --time=3 bash -lc "
                   "'module load pytorch && timeout 90 pip install --no-cache-dir --retries 0 --timeout 5 "
                   "--target /tmp/x requests 2>&1 | tail -3; echo rc=${PIPESTATUS[0]}'", timeout=300)
        self.assertNotIn("rc=0", r.stdout, "jobs have no internet")
        self.assertNotIn("rc=124", r.stdout, "it must fail with an error, not hang")

    def test_running_out_of_memory(self):
        r = ME.run("sbatch --parsable --wait --gpus=1 --time=3 --wrap "
                   "\"python3 -c 'b = b\\\"x\\\" * (25 * 1024**3)'\"", timeout=600)
        job = r.stdout.strip().split(";")[0]
        state = wait_until(lambda: ME.run(f"sacct -n -X -j {job} -o State").stdout.strip() or None, seconds=60)
        self.assertEqual(state, "OUT_OF_MEMORY", "a job over its 20 GB per GPU is stopped, and says so")


if __name__ == "__main__":
    unittest.main()
