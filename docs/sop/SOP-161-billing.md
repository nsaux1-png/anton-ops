# SOP-161: Billing and credits: how it works
**Status:** proved on anton 2026-10-20 ([ops log](../ops-log/2026-10-20-phase7-billing.md)). Charging real jobs is checked end to end once douglas1 runs jobs.

## Purpose
Customers buy credits up front, and usage draws them down (`slurm-design.md` section 9).
- **Ledger:** database `cluster_ledger` on anton, with its own database user. The password is in `/etc/cluster/secrets/` and never in the repo.
  - Append-only: every top-up, grant, refund, adjustment, charge, storage charge and expiry is one entry.
  - Every entry has a reference that's unique per customer, so the same invoice or job minute is never counted twice.
  - Amounts are whole numbers of micro-credits. 1 credit = 1 US dollar (plan D40, working assumption).
- **Credit batches:** each top-up, grant or refund is a batch that expires 12 months later.
  - Spending uses the batch that expires soonest first.
  - Charges no batch can cover are debt, and the next top-up pays them first.
- **Prices:** `config/rates.yml` holds the default list, with dates. Customers can have their own prices (`rates:`) or a discount (`discount_percent:`) in `customers.yml`.
  - Each customer's prices are recorded with the time they took effect (`price_history`), which is also what customers see.
  - A job is charged at the prices in effect when it started; storage at the prices of the month's first reading.
  - ⚠️ The prices in `rates.yml` are **placeholders** until the user sets them (D29).
- **The hourly run** (`cluster-billing-hourly.timer`, i.e. `cluster-billing hourly`):
  1. **Prices:** record any change.
  2. **Storage:** read each customer's group-quota use and charge for any new peak this month.
  3. **Jobs:** read `sacct -D` for the last 3 days, keyed by Slurm's `DBIndex`. Charge each job up to its elapsed time (hourly while it runs; final when it ends). A node failure is refunded automatically.
  4. **Expiry:** write off what's left in expired batches.
  5. **Grace:** a customer at zero credit gets 10 more minutes on each running job, once. Then Slurm's normal end applies: their `--signal` warning, then `SIGTERM`, then `SIGKILL` 60 s later.
  6. **Slurm limits:** each customer has a QOS `cust-<code>` (`NoDecay`) with `GrpTRESMins=billing` = usage so far + what their available credit buys.
- **Every `./cluster apply`** also runs `cluster-billing sync` (prices and Slurm limits), so a new customer never runs without a credit limit.
- Each charge, refund and storage charge is one database transaction, holding a per-customer lock. A crash can't charge twice, and two runs at once can't overspend a batch (tested).

Role: `ansible/roles/billing`. Code: `clusterlib/billing.py` (the money logic), `clusterlib/ledger.py` (the database), `clusterlib/billing_cli.py` (the tool), installed in `/usr/local/lib/cluster`. The configuration it bills by is the last applied copy in `/etc/cluster/config`.

## When
- Installed and synced by every `./cluster apply`.
- The hourly run happens by itself.
- `./cluster credits hourly` runs it now.

## Checks
- **Code tests:** `./cluster test --code -k billing` covers money, prices, overrides, job costs, batches and expiry, storage, the Slurm limit formula and grace.
- **Database tests:** `./cluster test --live -k test_ledger`, 15 scenarios in the scratch database `cluster_ledger_test`. These include two concurrent writers, which never overspend a batch.
- **Live tests:** `./cluster test --live -k test_billing`:
  - the timer runs, and files are admin-only
  - customers' only sudo is their own views
  - a grant counts once and raises the Slurm limit by exactly what it buys
  - every customer runs under their own QOS
  - `sync` changes nothing the second time
  - customers see only their own data
- `journalctl -u cluster-billing-hourly` shows every hourly run's output.

## Undo
See the proof run in the ops log. ⚠️ Dropping `cluster_ledger` deletes the money records: **never on a cluster with customers.**

## History
- 2026-10-20: first version on anton. Proof run: databases, tool, timer, customer commands, sudo rule and the QOS limits removed, then rebuilt with one apply. The tests passed again.
