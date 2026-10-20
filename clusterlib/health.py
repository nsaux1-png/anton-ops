"""./cluster health (SOP-171): one screen of everything that should be true, and an exit code.

Each check returns (ok, detail). The parsing is kept apart from running commands, so it has code
tests (tests/code/test_health.py). Alerts (email) come later, with plan D34.
"""

import datetime
import re

HEAD_SERVICES = ["sshd", "firewalld", "chronyd", "munge", "mariadb", "slurmdbd", "slurmctld", "nfs-server", "squid"]
NODE_SERVICES = ["sshd", "chronyd", "cluster-egress"]
GPU_NODE_SERVICES = ["nvidia-persistenced"]
TIMERS = {"cluster-billing-hourly": 2, "cluster-backup-binlogs": 2, "cluster-backup-nightly": 26,
          "cluster-tests-weekly": 24 * 8}       # how many hours since its last run before it's a problem
DISK_LIMIT_PERCENT = 85
BACKUP_MAX_HOURS = 26


def raid_ok(mdstat):
    """Every md array in /proc/mdstat has all its members ([UU], not [U_])."""
    states = re.findall(r"\[([U_]+)\]", mdstat)
    if not states:
        return False, "no RAID arrays found"
    bad = [s for s in states if "_" in s]
    return (not bad), ("all members in sync" if not bad else f"degraded: [{', '.join(bad)}]")


def disk_ok(df_line):
    """A `df --output=pcent,target` line: under DISK_LIMIT_PERCENT full."""
    pcent, target = df_line.split()[:2]
    used = int(pcent.rstrip("%"))
    return used < DISK_LIMIT_PERCENT, f"{target} {used}% full"


def backup_age_ok(newest_day, now):
    if not newest_day:
        return False, "no backups yet"
    made = datetime.datetime.combine(datetime.date.fromisoformat(newest_day), datetime.time(1, 30))
    hours = (now - made).total_seconds() / 3600
    return hours < BACKUP_MAX_HOURS, f"newest backup {newest_day} ({hours:.0f} h ago)"


def timer_ok(name, result, last_run, now):
    """A service run by a timer: its last run succeeded and wasn't too long ago."""
    if result != "success":
        return False, f"last run: {result or 'never'}"
    if last_run is None:
        return name == "cluster-tests-weekly", "hasn't run yet"
    hours = (now - last_run).total_seconds() / 3600
    return hours <= TIMERS[name], f"last run {hours:.1f} h ago, succeeded"


def nodes_ok(sinfo_lines):
    """`sinfo -h -N -o '%N %T'` lines: no node down, drained or failing."""
    bad = [line for line in sinfo_lines if re.search(r"down|drain|fail|unknown|not_responding", line.lower())]
    return (not bad), ("all nodes up" if not bad else "; ".join(bad))


def summary(results):
    """[(area, check, ok, detail)] as text lines, and whether everything is fine."""
    width = max([len(f"{a}: {c}") for a, c, _, _ in results] + [10])
    lines = [f"{'OK  ' if ok else 'FAIL'}  {(a + ': ' + c).ljust(width)}  {detail}" for a, c, ok, detail in results]
    problems = sum(1 for r in results if not r[2])
    lines.append("All healthy." if not problems else f"{problems} problem(s).")
    return lines, problems == 0
