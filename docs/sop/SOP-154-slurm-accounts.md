# SOP-154: Slurm accounts and limits from `customers.yml`
**Status:** proved on anton 2026-10-20 ([ops log](../ops-log/2026-10-20-phase6-slurm.md))

## Purpose
The `cluster-slurm-accounts` tool (role `slurm_accounts`; code `ansible/roles/slurm_accounts/files/`) makes Slurm's accounting match `config/customers.yml`:
- **each customer is a Slurm account** (`c4821`). Its `max_gpus` caps all its users together (`GrpTRES=gres/gpu`).
- **each user has one association**, in their customer's account:
  - GPUs held at once and per job: the user's `max_gpus`
  - up to `slurm_max_queued_jobs` (500) jobs queued
- **suspended and removed users** can't submit or run anything (`MaxSubmitJobs=0`, `MaxJobs=0`). Their login is blocked too (SOP-141).
- **admins** (`slurm_admins`, now `papaya`) are in the `admin` account with `AdminLevel=Administrator`.
- **nothing is ever deleted**, so old jobs keep their owner. Customers aren't Slurm "coordinators" (those could change limits and cancel jobs).

It prints one line per change and nothing when Slurm already matches, so `./cluster apply`'s preview shows exactly what would change in Slurm.

Credits and per-customer billing limits (a QOS per customer) come with billing (build plan phase 7).

## When
Automatically on every `./cluster apply`, and so after every `./cluster user …` or `./cluster customer …` change (SOP-210).

## Checks
- **Code tests:** `./cluster test --code -k slurm_accounts`, 8 tests: an empty Slurm, a settled Slurm, changed and removed limits, suspended users, nobody deleted.
- **Live tests:** `./cluster test --live -k "test_slurm.Accounts"` compares every customer and user against `customers.yml`. `-k Privacy` checks customers see only their own associations and jobs.
- **By hand:** `sudo sacctmgr show assoc format=account,user,grptres,maxtresperjob,maxsubmitjobs,maxjobs`.

## History
- 2026-10-20: first version; the test customers c0001 and c0002 and their users zz01 to zz04 were created.
