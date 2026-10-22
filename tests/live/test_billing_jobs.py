"""SOP-161: billing with real jobs on the GPU nodes. Exact charges, running jobs charged every hour and
finally once, and running out of credit mid-job (the 10-minute grace, slurm-design.md section 9).

Uses test customer c0002 (user zz03). The grace test takes c0002's credit away for its duration with an
adjustment, and gives it back at the end. It waits for the grace to run out (about 11 minutes); set
CLUSTER_TESTS_QUICK=1 to stop after the checks that need no waiting.
"""

import datetime
import json
import os
import re
import shlex
import time
import unittest
import uuid
from decimal import Decimal

import yaml

from helpers import REPO, head, run, wait_until

HEAD = head()
USER, CODE = "zz03", "c0002"
QUICK = bool(os.environ.get("CLUSTER_TESTS_QUICK"))
with open(os.path.join(REPO, "config", "rates.yml")) as f:
    RATES = yaml.safe_load(f)
with open(os.path.join(REPO, "config", "customers.yml")) as f:
    CUSTOMER = yaml.safe_load(f)["customers"][CODE]


def billing(*args):
    return run(HEAD, "sudo /usr/local/sbin/cluster-billing " + " ".join(shlex.quote(a) for a in args), timeout=300)


def available():
    return json.loads(billing("balance", CODE, "--json").stdout)["available"]


def credits(micro):
    """Micro-credits as the exact text the billing commands take ("-49.999988")."""
    return str(Decimal(micro) / Decimal(1_000_000))


def as_user(command, timeout=300):
    return run(HEAD, f"sudo -u {USER} bash -lc {shlex.quote('cd ~ && ' + command)}", timeout=timeout)


def submit(options, script):
    r = as_user(f"sbatch --parsable --job-name=cluster-test {options} --wrap {shlex.quote(script)}")
    if r.returncode != 0:
        raise AssertionError(f"sbatch failed: {r.stdout}{r.stderr}")
    return r.stdout.strip().split(";")[0]


def state(job):
    return run(HEAD, f"squeue -h -j {job} -o %T").stdout.strip()


def wait_running(job):
    if not wait_until(lambda: state(job) == "RUNNING", seconds=120):
        raise AssertionError(f"job {job} didn't start: {state(job)} "
                             f"{run(HEAD, f'squeue -h -j {job} -o %r').stdout.strip()}")


def finished_record(job):
    """(state, elapsed seconds, billing units) once Slurm's database has the finished job."""
    def read():
        lines = run(HEAD, f"sudo sacct -n -X -P -D -j {job} -o State,ElapsedRaw,AllocTRES,End").stdout.split()
        if not lines:
            return None
        st, elapsed, tres, end = lines[-1].split("|")
        if end in ("", "Unknown", "None"):
            return None
        units = int(float(dict(t.split("=", 1) for t in tres.split(",") if "=" in t)["billing"]))
        return st.split()[0], int(elapsed), units
    return wait_until(read, seconds=180, every=5)


def usage_row(job):
    rows = json.loads(as_user("/usr/local/bin/myusage --json").stdout)
    return next((r for r in rows if str(r["job_id"]) == str(job)), None)


def expected_cost(units, seconds):
    """Worked out from rates.yml here, independently of the billing code: micro-credits per unit-hour is
    the GPU-hour price over the units per GPU; a job pays per second, rounded down."""
    today = datetime.date.today().isoformat()
    prices = [p for p in RATES["prices"] if str(p["from"]) <= today][-1]
    unit_hour = int(Decimal(str(prices["gpu_hour"][RATES["partitions"]["gpu"]])) * 1_000_000) // RATES["units_per_gpu"]
    return units * seconds * unit_hour // 3600


def setUpModule():
    if CUSTOMER.get("rates") or CUSTOMER.get("discount_percent"):
        raise AssertionError(f"{CODE} must use the default prices for these tests")
    if available() <= 0:
        raise AssertionError(f"{CODE} has no credit: ./cluster credits grant {CODE} 50 "
                             f"--ref TEST-CREDIT-<date>-{CODE} (SOP-211)")


class RealJobCharges(unittest.TestCase):
    def test_a_finished_job_is_charged_exactly_what_it_cost(self):
        job = submit("--time=5 --gpus=1", "sleep 20")
        wait_until(lambda: state(job) == "", seconds=240)
        st, elapsed, units = finished_record(job)
        self.assertEqual(billing("hourly").returncode, 0)
        row = usage_row(job)
        self.assertIsNotNone(row, "the customer's own usage view doesn't show the job")
        self.assertEqual((row["units"], row["charged_seconds"]), (units, elapsed))
        self.assertEqual(row["charged"], expected_cost(units, elapsed))
        self.assertTrue(row["final"])

    def test_a_running_job_is_charged_every_hour_and_finally_once(self):
        job = submit("--time=5 --gpus=1", "sleep 75")
        try:
            wait_running(job)
            time.sleep(30)
            self.assertEqual(billing("hourly").returncode, 0)
            part = usage_row(job)
            self.assertGreater(part["charged"], 0, "a running job is charged for its time so far")
            self.assertFalse(part["final"])
            wait_until(lambda: state(job) == "", seconds=240)
            st, elapsed, units = finished_record(job)
            self.assertEqual(billing("hourly").returncode, 0)
            done = usage_row(job)
            self.assertEqual(done["charged"], expected_cost(units, elapsed), "the total, not the total plus the part")
            self.assertTrue(done["final"])
            self.assertEqual(billing("hourly").returncode, 0)
            self.assertEqual(usage_row(job)["charged"], done["charged"], "a finished job is never charged again")
        finally:
            run(HEAD, f"sudo scancel {job}")

    def test_the_monthly_cross_check_agrees_with_slurm(self):
        r = billing("check", datetime.date.today().strftime("%Y-%m"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class OutOfCredit(unittest.TestCase):
    """At zero credit: new jobs wait, and a running job gets 10 more minutes, with the warning it asked for,
    then stops at its new time limit. Slurm doesn't kill it earlier (the 'safe' rule). The grace is charged."""

    def test_a_running_job_gets_ten_more_minutes_and_its_warning(self):
        ref = f"test-grace-{uuid.uuid4().hex[:8]}"
        marker = f".cluster-test-{uuid.uuid4().hex[:8]}"
        # Bash runs a trap only between commands, so sleep in short steps.
        job = submit("--time=30 --gpus=1 --signal=B:USR1@600",
                     f"trap 'echo warned > ~/{marker}' USR1; for i in $(seq 1800); do sleep 1; done")
        taken = 0
        waiting = None
        try:
            wait_running(job)
            taken = available()
            self.assertGreater(taken, 0)
            r = billing("adjust", CODE, credits(-taken), "--ref", ref, "--note", "live test: out of credit (SOP-161)")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertLessEqual(available(), 0)

            self.assertEqual(billing("hourly").returncode, 0)
            out = run(HEAD, f"scontrol show job {job}").stdout
            hours, minutes = re.search(r"TimeLimit=(\d+):(\d+):\d+", out).groups()
            limit = int(hours) * 60 + int(minutes)
            self.assertLessEqual(limit, 12, f"time limit not shortened to now + 10 minutes: {out}")
            self.assertGreaterEqual(limit, 10)

            warned = wait_until(lambda: as_user(f"cat ~/{marker} 2>/dev/null").stdout.strip() == "warned",
                                seconds=150, every=5)
            self.assertTrue(warned, "the job's USR1 warning didn't arrive")

            # Right after submitting, Slurm's reason is "None" until the scheduler has looked at the job.
            waiting = submit("--time=5 --gpus=1", "true")
            blocked = wait_until(lambda: "QOSGrpBillingMinutes" in run(HEAD, f"squeue -h -j {waiting} -o %r").stdout,
                                 seconds=90)
            self.assertTrue(blocked, "a new job must wait for credit: "
                                     + run(HEAD, f"squeue -h -j {waiting} -o '%T %r'").stdout)

            time.sleep(60)
            self.assertEqual(state(job), "RUNNING", "Slurm must not kill the job over the limit")
            if QUICK:
                return

            ended = wait_until(lambda: state(job) == "", seconds=(limit + 3) * 60, every=15)
            self.assertTrue(ended, "the job outlived its shortened time limit")
            st, elapsed, units = finished_record(job)
            self.assertEqual(st, "TIMEOUT")
            self.assertLessEqual(elapsed, limit * 60 + 120)        # stopped at the limit, plus KillWait
            self.assertEqual(billing("hourly").returncode, 0)
            self.assertLess(available(), 0, "the grace minutes are charged, so the balance goes below zero")
        finally:
            run(HEAD, f"sudo scancel {job}")
            if waiting:
                run(HEAD, f"sudo scancel {waiting}")
            as_user(f"rm -f ~/{marker}")
            if taken:
                billing("adjust", CODE, credits(taken), "--ref", ref + "-back", "--note", "live test: credit back")
            billing("sync")


if __name__ == "__main__":
    unittest.main()
