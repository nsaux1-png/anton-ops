# 2026-10-20: Build phase 7 (billing and credits) on anton

## Why
Build plan phase 7. douglas1 is down, so everything that doesn't need a running job was built and tested on anton.

## Done
By Claude Code (a session on anton as papaya), while the user was away.
1. **`clusterlib/billing.py`:** the money logic, with no database in it.
   - whole-number micro-credits
   - the price list with dates, customers' own prices and discount
   - job cost; charging in hourly pieces adds up exactly to the total
   - batches spent soonest-expiring first, expiry, available credit
   - storage peaks
   - the Slurm limit formula (usage + what credit buys; review W1)
   - the grace step

   27 code tests.
2. **`clusterlib/ledger.py`:** the database.
   - append-only entries with per-customer unique references
   - batches; allocations, with debt paid off by the next top-up
   - per-job charge tracking by `DBIndex`
   - storage readings and month peaks; price history
   - every write is one transaction under a per-customer lock

   15 database tests in the scratch database `cluster_ledger_test`, including two concurrent writers.
   - The first draft charged a job and updated its record in two transactions; reworked into one before anything ran.
   - One test found an empty result coming back as a tuple; fixed.
3. **`clusterlib/billing_cli.py` (`cluster-billing`):** `hourly`, `sync`, `topup`, `grant`, `adjust`, `refund`, `balance`, `statement`, `customer-view`. **`./cluster credits …`** runs it (logged). **`./cluster apply`** now also checks `rates.yml` and every customer's prices before anything runs.
4. **`config/rates.yml`:** ⚠️ **placeholder prices**: 0.50 per GPU-hour, 0.02 per core-hour, 0.05 per GiB-month. The user sets the real ones (D29).
5. **Role `billing`:**
   - `python3-PyMySQL`
   - the databases and their user
   - code in `/usr/local/lib/cluster`, applied config in `/etc/cluster/config` (root:wheel 0640)
   - the hourly timer
   - customer commands, and a single sudo rule for them
   - a `sync` on every apply

   (I installed `python3-PyMySQL` by hand once, during discovery, before the role existed.)
6. **Applied with `./cluster apply --limit anton`**, "Done and settled" every time.
   - The first `./cluster credits hourly` recorded prices and created the QOS `cust-c0001` and `cust-c0002`, at limit 0 until the customers have credit.
7. **Tests:**
   - `test_billing`: 15 live tests
   - `test_ledger`: 15 database scenarios
   - `test_customers`: now checks customers' only sudo is their billing views
   - a test that called the customer commands through `sudo -u` couldn't find them (sudo's short PATH); it now uses full paths, plus one real SSH login
8. **Proof run:**
   - Removed the timer, tool, code, applied config, customer commands, sudo rule, both databases and their user, and the QOS assignments and QOS.
   - Re-applied, then `./cluster credits hourly`; the billing tests passed again.
   - It also showed a gap: a new customer had no Slurm credit limit until the next hourly run. Fixed: every apply now runs `cluster-billing sync`.
9. **Full suite:** 99 code tests pass, and every live test that runs on anton passes. The failures are the douglas1 checks, plus building the GPU check program (also on douglas1).

## Not done yet (needs douglas1 running jobs)
- Charging real jobs end to end, the grace step on a real job, and running out of credit mid-job.
- The monthly cross-check of ledger against Slurm (`billing check`).
- Low-balance and expiry emails: alerts come in phase 8.

## Decisions taken as working assumptions (for the user to confirm)
- 1 credit = 1 US dollar (D40).
- Prices are placeholders (D29).
- Storage is billed per GiB (1024³ bytes).
