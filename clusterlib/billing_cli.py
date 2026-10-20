"""cluster-billing: the billing and credits tool on anton (SOP-161, SOP-162, SOP-211).

Installed by Ansible (role billing) as /usr/local/sbin/cluster-billing, with this package in
/usr/local/lib/cluster and the applied configuration in /etc/cluster/config. Runs as root:
  - by admins, through ./cluster credits ... (logged)
  - every hour, by cluster-billing.timer: cluster-billing hourly
  - by customers, through sudo and the commands credits, myusage, prices and mystorage:
    cluster-billing customer-view ... (it answers only about the person who ran it)
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys

import yaml

from clusterlib import billing, config as cfg
from clusterlib.ledger import Ledger, utcnow

CONFIG_DIR = os.environ.get("CLUSTER_CONFIG_DIR", "/etc/cluster/config")
SACCT_DAYS = 3                 # each run looks this far back, in case records reached the database late
QOS_PREFIX = "cust-"


def load_config():
    def read(name):
        with open(os.path.join(CONFIG_DIR, name)) as f:
            return yaml.safe_load(f)
    customers = cfg.check(read("customers.yml"))
    rates = read("rates.yml")
    problems = billing.check_rates(rates)
    if problems:
        raise billing.BillingError("rates.yml has problems:\n  - " + "\n  - ".join(problems))
    return customers, read("uids.yml"), rates


def operator():
    return os.environ.get("SUDO_USER") or ("timer" if not sys.stdin.isatty() else "root")


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


# --- hourly ---------------------------------------------------------------------------------------

def sync_prices(ledger, customers, rates, now, say):
    for code, c in customers["customers"].items():
        prices = billing.customer_prices(billing.default_prices_at(rates, now), c)
        if ledger.record_prices(code, prices, now):
            say(f"prices {code}: recorded {json.dumps(prices, sort_keys=True)}")


def storage_usage(uids):
    """{customer: bytes used}, from the group quotas (each customer's group carries its files)."""
    by_gid = {gid: code for code, gid in uids["groups"].items()}
    used = {code: 0 for code in uids["groups"]}
    out = run("xfs_quota", "-x", "-c", "report -g -b -N -n", "/raiddrive")
    for line in out.splitlines():
        parts = line.split()
        if parts and parts[0].startswith("#") and int(parts[0][1:]) in by_gid:
            used[by_gid[int(parts[0][1:])]] = int(parts[1]) * 1024
    return used


def charge_storage(ledger, customers, uids, now, say):
    for code, used in storage_usage(uids).items():
        if code not in customers["customers"]:
            continue
        prices = ledger.prices_at(code, now)
        cost = ledger.record_storage(code, used, prices["storage_gb_month"], operator(), now)
        if cost:
            say(f"storage {code}: new peak {used / billing.GIB:.2f} GiB, charged {billing.show(cost)}")


SACCT_FIELDS = "DBIndex,JobIDRaw,Account,User,Partition,State,Start,End,ElapsedRaw,TimelimitRaw,AllocTRES"


def slurm_jobs(now):
    """Job records that have started, from the last SACCT_DAYS days (sacct -D: requeues included)."""
    start = (now - datetime.timedelta(days=SACCT_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
    out = run("sacct", "-D", "-X", "-a", "-P", "-n", "--starttime", start, "-o", SACCT_FIELDS)
    jobs = []
    for line in out.splitlines():
        f = line.split("|")
        if len(f) < 11 or f[6] in ("", "Unknown", "None"):
            continue
        tres = dict(item.split("=", 1) for item in f[10].split(",") if "=" in item)
        jobs.append({"db_index": int(f[0]), "job_id": f[1], "account": f[2], "user": f[3], "partition": f[4],
                     "state": f[5].split()[0], "start": datetime.datetime.fromisoformat(f[6]),
                     "end": None if f[7] in ("", "Unknown", "None") else datetime.datetime.fromisoformat(f[7]),
                     "elapsed": int(f[8] or 0), "time_limit": int(f[9]) if f[9].isdigit() else 0,
                     "units": int(float(tres.get("billing", "0")))})
    return jobs


def local_to_utc(dt):
    return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None) if dt else None


def charge_jobs(ledger, customers, rates, now, say):
    jobs = slurm_jobs(now)
    for j in jobs:
        if j["account"] not in customers["customers"] or j["units"] <= 0:
            continue
        started = local_to_utc(j["start"])
        if ledger.job(j["db_index"]) is None:
            prices = ledger.prices_at(j["account"], started) or ledger.prices_at(j["account"], now)
            ledger.record_job(j["db_index"], j["job_id"], j["account"], j["user"], j["partition"], j["units"],
                              billing.unit_hour_price(prices, rates, j["partition"]), started)
        ended = local_to_utc(j["end"]) if j["state"] not in ("RUNNING", "SUSPENDED", "REQUEUED") else None
        cost = ledger.charge_job(j["db_index"], j["elapsed"], j["state"], ended, operator(), now)
        if cost:
            say(f"job {j['job_id']} ({j['user']}): charged {billing.show(cost)}")
        if j["state"] == "NODE_FAIL" and ended:
            refunded = ledger.refund_job(j["db_index"], "the node failed (our fault): refunded", operator(), now)
            if refunded:
                say(f"job {j['job_id']}: node failure, refunded {billing.show(refunded)}")
    return jobs


def expire_credit(ledger, customers, now, say):
    for code in customers["customers"]:
        for batch_id, amount in ledger.expire(code, operator(), now):
            say(f"credit {code}: {billing.show(amount)} from entry {batch_id} expired")


def qos_usage():
    """{qos name: (billing-minute limit or None, billing-minutes used)} from Slurm's association manager."""
    out = run("scontrol", "show", "assoc_mgr", "flags=qos")
    usage = {}
    for block in re.split(r"\n(?=QOS=)", out):
        name = re.match(r"QOS=([^(\s]+)", block)
        mins = re.search(r"GrpTRESMins=\S*?billing=(N|\d+)\((\d+)\)", block)
        if name and mins:
            usage[name.group(1)] = (None if mins.group(1) == "N" else int(mins.group(1)), int(mins.group(2)))
    return usage


def sync_slurm_limits(ledger, customers, rates, now, say):
    """Each customer's QOS limit = billing-minutes used so far + what their available credit buys."""
    usage = qos_usage()
    existing = set(usage)
    partitions = list((rates.get("partitions") or {}).keys())
    for code in customers["customers"]:
        qos = QOS_PREFIX + code
        if qos not in existing:
            run("sacctmgr", "-i", "add", "qos", qos, "Flags=NoDecay")
            say(f"slurm: added QOS {qos}")
            usage[qos] = (None, 0)
        rows = run("sacctmgr", "-nP", "show", "assoc", "where", f"account={code}",
                   "format=user,qos,defaultqos").strip().splitlines()
        account_row = next((r for r in rows if r.startswith("|")), "")
        if account_row != f"|{qos}|{qos}":
            run("sacctmgr", "-i", "modify", "account", "where", f"name={code}", "set", f"QOS={qos}",
                f"DefaultQOS={qos}")
            say(f"slurm: account {code} uses QOS {qos}")
        prices = ledger.prices_at(code, now)
        limit = billing.qos_limit(usage[qos][1], ledger.balance(code, now)["available"],
                                  billing.highest_unit_hour_price(prices, rates, partitions))
        if usage[qos][0] != limit:
            run("sacctmgr", "-i", "modify", "qos", qos, "set", f"GrpTRESMins=billing={limit}")
            say(f"slurm: {qos} limit {usage[qos][0]} -> {limit} billing-minutes")


def grace(ledger, customers, jobs, now, say):
    running = {j["db_index"]: j for j in jobs if j["state"] == "RUNNING"}
    for code in customers["customers"]:
        if ledger.balance(code, now)["available"] > 0:
            continue
        tracked = [r for r in ledger.running_jobs(code) if r["db_index"] in running]
        candidates = [billing.RunningJob(str(r["db_index"]), running[r["db_index"]]["elapsed"],
                                         running[r["db_index"]]["time_limit"], bool(r["graced"])) for r in tracked]
        for db_index, minutes in billing.grace_updates(0, candidates):
            job = running[int(db_index)]
            run("scontrol", "update", f"JobId={job['job_id']}", f"TimeLimit={minutes}")
            ledger.mark_graced(int(db_index))
            say(f"grace {code}: out of credit; job {job['job_id']} stops in {billing.GRACE_MINUTES} minutes "
                f"(time limit now {minutes} min)")


def cmd_hourly(args, ledger, customers, uids, rates):
    now = utcnow()
    say = print
    sync_prices(ledger, customers, rates, now, say)
    charge_storage(ledger, customers, uids, now, say)
    jobs = charge_jobs(ledger, customers, rates, now, say)
    expire_credit(ledger, customers, now, say)
    grace(ledger, customers, jobs, now, say)
    sync_slurm_limits(ledger, customers, rates, now, say)
    for code in customers["customers"]:
        b = ledger.balance(code, now)
        say(f"balance {code}: {billing.show(b['available'])} available")
    return 0


def cmd_sync(args, ledger, customers, uids, rates):
    """Prices and Slurm credit limits only. Run by every ./cluster apply, so a new customer never runs
    a job without a credit limit, even before the next hourly run."""
    now = utcnow()
    sync_prices(ledger, customers, rates, now, print)
    sync_slurm_limits(ledger, customers, rates, now, print)
    return 0


# --- admin commands -------------------------------------------------------------------------------

def need_customer(customers, code):
    if code not in customers["customers"]:
        raise billing.BillingError(f"no customer {code} in customers.yml")


def cmd_credit(kind):
    def cmd(args, ledger, customers, uids, rates):
        need_customer(customers, args.customer)
        amount = billing.to_micro(args.amount)
        if amount <= 0:
            raise billing.BillingError("the amount must be positive")
        entry = ledger.add_credit(args.customer, kind, amount, args.ref, args.note or "", operator())
        if entry is None:
            print(f"Already recorded: {args.customer} {args.ref}. Nothing changed.")
        else:
            print(f"{kind} of {billing.show(amount)} for {args.customer} recorded (entry {entry}, ref {args.ref}).")
        show_balance(ledger, args.customer)
        return 0
    return cmd


def cmd_adjust(args, ledger, customers, uids, rates):
    need_customer(customers, args.customer)
    amount = billing.to_micro(args.amount)
    if not args.note:
        raise billing.BillingError("an adjustment needs --note saying why")
    if amount > 0:
        entry = ledger.add_credit(args.customer, "adjustment", amount, args.ref, args.note, operator())
    elif amount < 0:
        entry = ledger.debit(args.customer, "adjustment", -amount, args.ref, args.note, operator())
    else:
        raise billing.BillingError("the amount can't be zero")
    print("Already recorded; nothing changed." if entry is None else f"Adjustment recorded (entry {entry}).")
    show_balance(ledger, args.customer)
    return 0


def cmd_refund(args, ledger, customers, uids, rates):
    amount = ledger.refund_job(args.db_index, args.reason, operator())
    print(f"Refunded {billing.show(amount)}." if amount else "Nothing to refund (never charged, or already refunded).")
    return 0


def show_balance(ledger, code, as_json=False):
    b = ledger.balance(code)
    if as_json:
        print(json.dumps({"customer": code, "balance": b["balance"], "available": b["available"], "debt": b["debt"],
                          "batches": [{"id": x.id, "amount": x.amount, "remaining": x.remaining,
                                       "expires_at": x.expires_at.isoformat()} for x in b["batches"]]}, indent=2))
        return
    print(f"{code}: {billing.show(b['available'])} credits available"
          + (f" (unpaid charges {billing.show(b['debt'])})" if b["debt"] else ""))
    for x in b["batches"]:
        if x.remaining > 0:
            print(f"  {billing.show(x.remaining):>12} of {billing.show(x.amount):>12}  expires {x.expires_at:%Y-%m-%d}")


def cmd_balance(args, ledger, customers, uids, rates):
    for code in ([args.customer] if args.customer else sorted(customers["customers"])):
        show_balance(ledger, code, args.json)
    return 0


def print_statement(ledger, code, month, as_json=False):
    s = ledger.statement(code, month)
    if as_json:
        print(json.dumps({"customer": code, "month": month, "opening": s.opening, "topups": s.topups,
                          "grants": s.grants, "refunds": s.refunds, "adjustments": s.adjustments,
                          "charges": s.charges, "storage": s.storage, "expiries": s.expiries,
                          "closing": s.closing,
                          "entries": [dict(e, created_at=e["created_at"].isoformat()) for e in s.lines]}, indent=2))
        return
    print(f"Statement for {code}, {month} (credits)")
    for label, value in (("Opening balance", s.opening), ("Top-ups", s.topups), ("Grants", s.grants),
                         ("Refunds", s.refunds), ("Adjustments", s.adjustments), ("Compute", -s.charges),
                         ("Storage", -s.storage), ("Expired", -s.expiries), ("Closing balance", s.closing)):
        print(f"  {label:<16}{billing.show(value):>14}")
    print()
    for e in s.lines:
        print(f"  {e['created_at']:%Y-%m-%d %H:%M}  {e['kind']:<10}{billing.show(e['amount']):>12}  {e['note'] or e['ref']}")


def cmd_statement(args, ledger, customers, uids, rates):
    need_customer(customers, args.customer)
    print_statement(ledger, args.customer, args.month, args.json)
    return 0


def cmd_setup(args, ledger, customers, uids, rates):
    print("created tables" if ledger.setup() else "", end="")
    return 0


# --- what customers see ---------------------------------------------------------------------------

def caller(customers):
    """(username, customer code, is manager) of the person who ran this through sudo."""
    user = os.environ.get("SUDO_USER")
    if not user:
        raise billing.BillingError("run this as yourself: credits, myusage, prices or mystorage")
    for code, c in customers["customers"].items():
        u = (c.get("users") or {}).get(user)
        if u:
            return user, code, u.get("role") == "manager"
    raise billing.BillingError("these commands are for customers' accounts")


def cmd_customer_view(args, ledger, customers, uids, rates):
    user, code, manager = caller(customers)
    month = args.month or utcnow().strftime("%Y-%m")
    if args.what == "credits":
        show_balance(ledger, code, args.json)
        if manager and not args.json:
            print()
            print_statement(ledger, code, month)
    elif args.what == "usage":
        rows = ledger.jobs_for(code, None if manager else user, month)
        if args.json:
            print(json.dumps([dict(r, started_at=r["started_at"].isoformat(),
                                   ended_at=r["ended_at"].isoformat() if r["ended_at"] else None) for r in rows],
                             indent=2))
        else:
            print(f"Jobs in {month}" + (f" for all of {code}" if manager else f" for {user}") + " (credits)")
            for r in rows:
                print(f"  {r['job_id']:>8} {r['username']:<6} {r['partition_name']:<6} {r['started_at']:%Y-%m-%d %H:%M} "
                      f"{r['charged_seconds'] // 60:>6} min  {r['units']:>3} units  {billing.show(r['charged']):>10}"
                      + ("  refunded" if r["refunded"] else ""))
            print(f"  Total {billing.show(sum(r['charged'] for r in rows if not r['refunded']))}")
    elif args.what == "prices":
        history = ledger.price_history(code)
        if args.json:
            print(json.dumps([{"from": t.isoformat(), "prices": p} for t, p in history], indent=2))
        else:
            for t, p in history:
                gpus = ", ".join(f"{m} {billing.show(v)}/GPU-hour" for m, v in sorted(p["gpu_hour"].items()))
                print(f"  from {t:%Y-%m-%d %H:%M} UTC: {gpus}; CPU {billing.show(p['cpu_core_hour'])}/core-hour; "
                      f"storage {billing.show(p['storage_gb_month'])}/GiB-month")
    elif args.what == "storage":
        s = ledger.storage_month(code, month)
        limit = customers["customers"][code].get("storage_gb", customers["defaults"]["storage_gb"])
        info = {"customer": code, "month": month, "limit_gib": limit,
                "latest_gib": None if s["latest_bytes"] is None else round(s["latest_bytes"] / billing.GIB, 3),
                "month_peak_gib": round(s["peak_bytes"] / billing.GIB, 3),
                "month_cost": billing.show(billing.storage_cost(s["peak_bytes"], s["gb_month_price"] or 0))}
        if args.json:
            print(json.dumps(info, indent=2))
        else:
            print(f"{code} storage, {month}: using {info['latest_gib']} GiB of {limit} GiB; "
                  f"this month's peak {info['month_peak_gib']} GiB = {info['month_cost']} credits")
    return 0


# --- main -----------------------------------------------------------------------------------------

def parser():
    p = argparse.ArgumentParser(prog="cluster-billing", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--database", default="cluster_ledger", help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("setup").set_defaults(func=cmd_setup)
    sub.add_parser("hourly").set_defaults(func=cmd_hourly)
    sub.add_parser("sync").set_defaults(func=cmd_sync)
    for kind in ("topup", "grant"):
        q = sub.add_parser(kind)
        q.add_argument("customer")
        q.add_argument("amount")
        q.add_argument("--ref", required=True, help="invoice or reference; the same one is never counted twice")
        q.add_argument("--note")
        q.set_defaults(func=cmd_credit(kind))
    q = sub.add_parser("adjust")
    q.add_argument("customer")
    q.add_argument("amount", help="positive adds credit, negative takes it")
    q.add_argument("--ref", required=True)
    q.add_argument("--note", required=True)
    q.set_defaults(func=cmd_adjust)
    q = sub.add_parser("refund")
    q.add_argument("db_index", type=int, help="the job record's DBIndex (sacct -D -o DBIndex)")
    q.add_argument("--reason", required=True)
    q.set_defaults(func=cmd_refund)
    q = sub.add_parser("balance")
    q.add_argument("customer", nargs="?")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_balance)
    q = sub.add_parser("statement")
    q.add_argument("customer")
    q.add_argument("month", help="YYYY-MM")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_statement)
    q = sub.add_parser("customer-view")
    q.add_argument("what", choices=["credits", "usage", "prices", "storage"])
    q.add_argument("--month")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_customer_view)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        customers, uids, rates = load_config()
        ledger = Ledger(database=args.database)
        try:
            return args.func(args, ledger, customers, uids, rates)
        finally:
            ledger.close()
    except (billing.BillingError, cfg.ConfigError) as e:
        print(f"cluster-billing: {e}", file=sys.stderr)
        return 2
