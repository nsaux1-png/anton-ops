# Slurm system design

**Status: DRAFT, 2026-10-19 (fourth round).** Built from the user's requirements given that day. This page is the overall shape; [`plan.md`](plan.md) has the details of each piece.

## Requirements (user, 2026-10-19)
1. Track usage per user.
2. One simple config file to change people's settings.
3. The admin side is completely closed to users.
4. Track both compute usage and disk space. Disk space has limits, and storage is billed on the month's peak usage.
5. Users shouldn't be able to see the total disk space.
6. Ready for more GPU nodes and CPU nodes of different kinds.
7. Limits on how much memory and CPU a job can take with its GPUs. Nobody can take 3 GPUs and all of the node's memory.
8. Prepaid credits that are drawn down as customers use the cluster.
9. A default price list for everyone, overridden for many customers.
10. Credits expire 12 months after purchase. No free trials.
11. Test accounts, and a test suite that runs regularly (weekly).
12. Simple, repeatable admin commands (credits, software, maintenance and so on) that are real code, not AI. They can be run by hand, from cron, or by an agent.

## 1. Tracking per user
- Slurm's accounting (`slurmdbd` + MariaDB on anton) records every job and keeps the records forever. Section 8 lists exactly what's recorded.
- Each user belongs to a customer account. Bills are per customer, broken down by user.

## 2. The config file
The admin edits one file, `config/customers.yml`:

```yaml
defaults:                      # apply unless a customer or user overrides them
  storage_gb: 100              # each user's home folder limit
  max_gpus: 4                  # GPUs one user can hold at once

customers:
  c4821:                       # neutral customer code (section 3)
    name: Acme Robotics        # admin-only; never copied onto the cluster
    billing_email: ap@acme.example
    project_storage_gb: 1000   # shared project folder for the whole customer
    max_gpus: 8                # across all of the customer's users
    rates:                     # only the prices that differ from the default (section 9)
      gpu_hour.rtx5070ti: 0.40
    users:
      kx47:
        name: Alice Chen       # admin-only
        email: alice@acme.example
        ssh_key: ssh-ed25519 AAAA... alice@laptop
        max_gpus: 6            # override for this user
      bt82:
        name: Bob Smith
        email: bob@acme.example
        ssh_key: ssh-ed25519 AAAA... bob@desktop
        status: suspended      # active (default) | suspended | removed
```

- `./cluster add-user <customer> "<name>" <email>` picks a free random username and adds the entry. Everything else is edited in the file directly.
- `./cluster apply` shows what will change (for example "kx47: max GPUs 4 → 6") and asks before doing anything. It then updates Linux accounts, SSH keys, Slurm limits and disk quotas on every machine, logs the run, and commits the file. The git history shows who changed what, and when.
- User IDs (UIDs) are assigned automatically when a user first appears and kept in a generated file (`config/uids.yml`) that nobody edits by hand. A UID or username is never reused.
- Default prices go in `config/rates.yml` and machines in `config/nodes.yml`.

## 3. Admin side closed off
- Customers have no sudo. They can only log into a compute node while one of their own jobs is running on it (`pam_slurm_adopt`).
- Customers only see their own data:
  - their own jobs and usage (Slurm `PrivateData=jobs,usage,users,accounts`)
  - their own files (home folders `0700`, the folder holding them `0711` so it can't be listed; a project folder is readable only by that customer)
  - their own processes (`/proc` mounted with `hidepid`)
- Admin material is readable by root only: this repo and the config files, the vault password, the ops logs, the database credentials (`slurmdbd.conf`, mode `0600`), the munge key and the saved job scripts. Only admin accounts are Slurm administrators.
- **Admin logins only through a VPN** (recommended, Q3).
  - anton's upstream network is shared with other machines (plan D11), so "from the local network only" isn't private enough.
  - Admin accounts can log in only through a WireGuard VPN on anton, in the office too, and from the cluster network. Root can't log in over SSH at all.
  - Customers log in from the internet with SSH keys only, so a stolen customer key gives no route to an admin account.
  - Before direct admin logins are switched off, the VPN login is tested and a way back in is checked (a screen and keyboard on anton, or its BMC).
- On the upstream network, anton offers only SSH (and later the VPN port). Slurm, munge, the database and NFS listen only on the cluster network.
- The commands customers get (`credits`, `myusage`, `mystorage`) only show the caller's own data.
- **Usernames: two letters + two digits** (e.g. `kx47`), random, unrelated to the person's name (decided, Q1).
  - Letters that look like digits (`i`, `l`, `o`) aren't used, and `zz` is reserved for test accounts (section 11). That still leaves about 52,000 names.
  - Customer groups and Slurm accounts get neutral codes too (e.g. `c4821`).
  - Real names, emails and company names stay in the admin config. They are never written into `/etc/passwd`, which every user can read.

## 4. Compute and storage: tracking, limits, billing
- **Compute** comes from Slurm accounting, priced per GPU-hour (by GPU model) and per CPU-hour (section 9, plan D29).
- **Storage limits:** XFS project quotas on `/raiddrive`, one for each user's home folder and one for each customer's project folder. The hard limit is the most a customer can use; writing past it fails. An email warning goes out at 90%.
- **Storage measurement:** every hour a collector records each user's and each customer's usage in the accounting database.
- **Storage billing:** the month's **peak**, meaning the highest hourly reading, times the price per GB. The quota is only a ceiling; customers pay for what they actually used at the peak. Section 9 explains how this draws credits during the month.
- Scratch space on compute nodes is wiped after each job and isn't billed separately.
- **Monthly statement** per customer: compute by user plus peak storage, built from the same database.

## 5. Hiding the total disk space
- With XFS project quotas, `df` and `quota` show a user **their own limit** as the size of the disk, not the 3.7 TB.
- Limitation: on the machine that physically holds the disks (anton today), a technical user can still read the raw disk sizes, for example with `lsblk`. Hiding them completely means customers log into a separate login node that only reaches storage over NFS (plan D6). The medium-size plan already needs that node within the year.
- During the build we log in as a test customer and record exactly what is visible.
- **Nodes and GPUs stay visible** (decided, Q2): customers can see with `sinfo` which nodes and GPUs exist and which are busy.

## 6. Mixed GPU and CPU nodes
- Each node is one entry in `config/nodes.yml`: name, type, CPU sockets and cores, memory, GPU model and count, local scratch, and its per-GPU job size (section 7). Slurm's node list is generated from it.
- Partitions by node type, starting with `gpu` and `cpu`. GPUs are registered with their model (`gpu:rtx5070ti`), so a job can ask for a model (`--gpus=rtx5070ti:2`), and each model can have its own price.
- Node features let jobs pick CPU type, memory size and so on (`--constraint`).
- On dual-socket CPU nodes, a job's cores are kept on one socket where possible (cgroups plus CPU affinity).
- A job can use several GPUs in one node; they talk over PCIe, since the 5070 Ti has no NVLink. Jobs spread across several nodes would need a much faster network than 10 Gb (for example 100 Gb InfiniBand). That isn't planned for now.

## 7. Job sizes and limits
douglas1 has 56 cores (112 threads), 251 GB RAM and 10 GPUs. Plan for an eventual 11.

Straight division:

| | Cores | RAM |
|---|---|---|
| Total | 56 | 251 GB |
| ÷ 10 | 5.6 | 25.1 GB |
| ÷ 11 | 5.1 | 22.8 GB |
| ÷ 12 | 4.7 | 20.9 GB |

In practice each GPU's share has to be whole cores, because two customers never share a physical core. The system also needs a little for itself (`CoreSpecCount`, `MemSpecLimit`):

| GPUs | Per GPU | Jobs use in total | Left for the system |
|---|---|---|---|
| 10 | 5 cores, 24 GB | 50 cores, 240 GB | 6 cores, 11 GB |
| 11 | 5 cores, 21 GB | 55 cores, 231 GB | 1 core, 20 GB |
| 12 | 4 cores, 20 GB | 48 cores, 240 GB | 8 cores, 11 GB |

- **Decided (Q4): 5 cores + 20 GB per GPU**, sized for 11 GPUs from day one, so the size never shrinks.
  - With 11 GPUs, jobs use 55 cores and 220 GB, leaving the system 1 core and 31 GB.
  - With 10 GPUs, 6 cores and 51 GB stay unused. Unsold capacity costs nothing; the node just has headroom.
  - 5 cores is 10 threads, which clouds would call 10 vCPUs. That's within the usual range for GPU cloud offers (roughly 4–16 vCPUs per GPU). In GPU jobs the CPU mostly feeds data to the GPU, and 10 threads is enough for typical data loading.
  - The memory left over matters: the OS, the GPU driver and the file cache need it. If jobs could take every last GB, the node could freeze and take every job on it down.
- Note: 20 GB of RAM per 16 GB GPU is lean for machine-learning work. A common rule of thumb is 1.5–2× the GPU's memory. A RAM upgrade would allow more, so check what's installed (todo, next up).
- **Defaults:** a job gets the full per-GPU share unless it asks for less (`DefCpuPerGPU`, `DefMemPerGPU`). It can't ask for more. A job that needs more RAM takes more GPUs.
- **Checked at submission:** Slurm has a "default memory per GPU" setting but no "maximum per GPU" one. A short `job_submit.lua` script (run by Slurm on every submission) therefore rejects oversized jobs with a clear message, e.g. "gpu partition: at most 5 cores and 20 GB per GPU". `EnforcePartLimits=ALL` rejects jobs that break partition limits at submission instead of leaving them queued forever.
- **Enforced while running:** cgroups hold each job to what it was given. A job that goes over its memory is killed and recorded as `OUT_OF_MEMORY`. It only sees its own GPUs.
- **GPU nodes run GPU jobs only:** a job in `gpu` must ask for at least one GPU. Otherwise a CPU-only job could take the cores and memory and leave GPUs that nobody can use.
- **Billing safety net:** `PriorityFlags=MAX_TRES` bills a job for the **largest share of the node** it holds, whether that's GPUs, cores or memory. With the fixed size per GPU this just equals the GPU count. It matters if we loosen the size later, and on CPU nodes: 1 core with all the RAM is billed as the whole node.
- **Other limits** (from `customers.yml`): GPUs held at once per user and per customer, maximum job length (plan D23: 7 days, 1 hour default), and a cap on queued jobs per user.
- **CPU nodes (later):** a default and maximum memory per core, billed with the same largest-share rule.

## 8. What's recorded for each job
**In Slurm's accounting (kept forever):**
- **Who and where:** job ID, name, user, customer account, partition, QOS, working directory, node(s), and which GPUs.
- **When:** submitted, started and ended; time limit; elapsed time; time spent waiting in the queue.
- **Allocated:** CPUs, memory, GPUs by model, and billing units. This is what's charged.
- **Outcome:** final state (completed, failed, cancelled, timeout, out of memory, node failure) and exit code. A node failure triggers an automatic refund (plan D31).
- **Actual use, sampled every 30 s** (`jobacct_gather/cgroup`): CPU time, peak and average RAM, disk read/write, for each job step.
- **GPU use** from NVIDIA's NVML: GPU utilization and GPU memory per job (`gres/gpuutil`, `gres/gpumem`). Customers can see how well they used what they paid for, but we still charge for what was allocated (plan 12.1).
- **GPU energy per job** (`acct_gather_energy/gpu`), so we know the electricity cost of each job and customer.

**Job scripts: kept 60 days, then deleted** (decided, Q5).
- Slurm keeps job records forever and has no separate expiry for scripts. Scripts are therefore kept outside Slurm's database: when a job starts, a copy of its script goes into a root-only folder on anton, and a nightly cleanup deletes copies older than 60 days.
- The terms tell customers that scripts are kept for 60 days.
- Tested: the copy exists, customers can't read it, and it's gone after day 60.

**Possible, but not recorded:**
- **Environment variables** (`AccountingStoreFlags=job_env`). They often contain passwords and API tokens.
- **Detailed time-series profiles** of every job (the HDF5 profiling plugin): lots of disk for little benefit.
- **Whole-node power from the BMC** (IPMI): Slurm runs one energy source at a time, and GPU energy covers most of the power draw.
- **InfiniBand and Lustre counters:** we have neither.

**Outside Slurm:** nothing records what happens inside a job (the commands, files or network traffic). Logins (who, when and from which IP) and every admin action are logged (plan section 15).

## 9. Prices and credits
### Prices
- `config/rates.yml` is the **default price list**: per GPU-hour by GPU model, per CPU-core-hour, and per GB-month of storage.
- A customer can have its own prices under `rates:` in `customers.yml` (section 2). Anything not listed there comes from the default list. Alternatively, a customer gets `discount_percent: 15` off the whole default list. Where a customer has both, their own `rates:` win for the items listed.
- Prices have start dates. A job is charged at the prices in effect when it started. Changing a default price doesn't affect a customer who has their own price for that item. The statement shows the price used on every line.
- Slurm only measures resource units, the same for everyone. Prices are applied by our charging script, and each customer's Slurm limit is worked out from their balance at their own prices.

### Credits
The full design is in plan section 12.2. In short:
- Customers buy credits up front. An append-only **ledger** is the money record. Every top-up, job charge, refund, adjustment and expiry is one entry, and the balance is their sum.
- **Slurm enforces the balance.** Each customer gets a QOS (a Slurm limit group) with `Flags=NoDecay` and `GrpTRESMins=billing=<balance>`, plus `AccountingStorageEnforce=associations,limits,qos,safe`.
  - "NoDecay" means used credits never come back on their own. Fair-share scheduling still works normally, because it uses a separate measure that does decay.
  - "safe" means a job only starts if the balance covers its whole time limit.
  - When the balance runs out, new jobs wait with a clear reason, and running jobs finish.
- **Storage draws credits as the month's peak rises.** Each hourly reading above the month's previous peak charges the difference, so by month end the storage charge equals peak × price, with no surprise bill.
- Low-balance emails at 20% and 5%. The `credits` command shows the balance, the expiry dates, this month's use and the projected cost of running jobs.
- **At zero balance** (decided, Q6): jobs stop. Files stay and storage keeps charging, so the balance can go negative for storage only. After 30 days negative, with email warnings before then, the files are deleted.

### Expiry (Q7)
- Each top-up is its own **batch** of credits that expires 12 months after purchase (decided, Q7). There are no free trials (plan D43).
- Charges use the **batch that expires soonest** first. With equal terms that's simply oldest first (FIFO). Using newest first would let more of a customer's credits expire, which is unfair and invites disputes.
- When a batch expires, whatever is left in it becomes an `expiry` entry in the ledger. Customers get a warning 30 days before, and statements show each batch and its expiry date.
- Edge cases, each with a test:
  - A charge bigger than the soonest batch takes the rest from the next one.
  - A job still running when a batch expires: what it will owe is held back from that batch until it finishes.
  - A refund comes back as a new batch valid 12 months.
  - Expiry happens at midnight UTC on the date shown.
  - The Slurm limit drops the moment a batch expires.
- Not hard if built into the ledger from the start; harder to add later. It's one of the most heavily tested parts.
- Have the terms checked by whoever reviews contracts. Expiring prepaid credits are normal between businesses, but rules for consumer prepaid cards differ by state.

## 10. Ready-made packages considered
- **OpenHPC:** prebuilt Slurm and HPC tools for Rocky 9. It would save building Slurm, but Slurm upgrades then wait on its release schedule, and its NVIDIA GPU support would need checking. Building from SchedMD's source is one `rpmbuild` command in a script, so we keep our own build (plan section 9).
- **ColdFront** and **Waldur:** allocation portals that drive Slurm. ColdFront is built for universities (grants and allocations, not money); Waldur is a full cloud marketplace. Both are big systems to run for this size. Not now.
- **Open XDMoD:** usage reports and dashboards from Slurm data. Maybe later.
- **Open OnDemand:** a web portal for customers (files, jobs, Jupyter). Later (plan D26).
- **Payments:** we don't build payment handling. When customers pay online, a payment service (e.g. Stripe) records top-ups in our ledger (plan D33, D44).

**Result:** Slurm's own features do the accounting, limits and credit enforcement. Our own code is small: `./cluster apply`, the ledger and charging script, the storage collector, statements, and `job_submit.lua`.

## 11. Test accounts and test suite
**Test accounts**
- Two test customers (`c0001`, `c0002`), so tests can check that one customer can't see the other.
- Test users have reserved usernames starting with `zz` (`zz01`, `zz02`, …), which are never given to real people.
- Test accounts never appear on statements or invoices. Their credits are test grants.
- They can log in only from anton, not from the internet. Their keys are root-only on anton.

**`./cluster test` runs the suite, in three layers:**
1. **Code tests** take seconds and don't need the cluster. They cover the ledger, credit batches and expiry, price overrides, storage peak charging, what `apply` would change, and the username generator. GitHub Actions runs them on every push, and a failure marks the commit red on GitHub.
2. **Live tests** run on the real cluster as the test users:
   - **isolation:** can't see the other test customer's jobs, files or processes; no sudo; can't log into a node without a running job; `df` shows only their own limit
   - **limits:** an oversized job is rejected; a job over its memory is killed; a job sees only its own GPUs; a CPU-only job in `gpu` is rejected
   - **credits:** a job doesn't start at zero balance, or if its time limit wouldn't fit the balance; charges match the expected amount to the cent
   - **storage:** writing past the quota fails; the hourly collector recorded a reading
   - **GPUs:** a short CUDA test on every GPU
   - **access:** admin login from outside the VPN is refused
   - **backups:** last night's database dump exists and restores into a scratch database
3. **Each SOP's own checks:** every SOP ends with verification steps, and they're added to the live suite. The suite grows with the cluster.

**When:** live tests weekly (Sunday night, on a systemd timer), and a quick subset after every `./cluster apply` or upgrade. If customer jobs are using the GPUs, GPU tests wait up to a few hours, then report "skipped: busy" rather than failing.

**Results:** every run is logged like any `./cluster` run, with a summary by email (plan D34). A failure gets an ops-log entry saying what broke and how it was fixed.

## 12. Admin commands
Every routine admin task is a `./cluster` command. Each is plain code (Python plus Ansible) in this repo, with tests and no AI inside. A person, a cron job or an AI agent can call it, and it does the same thing every time.

| Area | Commands (proposal) |
|---|---|
| Customers and users | `customer add/show/list`, `user add/show/suspend/resume/remove`, `user set kx47 max_gpus=6`, `apply` |
| Credits | `credits balance <customer>`, `credits topup <customer> <amount> --ref <invoice>`, `credits refund <jobid> --reason …`, `credits adjust <customer> <amount> --reason …`, `credits expiring --within 30d`, `credits statement <customer> <month>` |
| Billing | `billing report <month>`, `billing check` (ledger vs Slurm cross-check) |
| Storage | `storage usage [<customer>]` |
| Nodes and maintenance | `node status`, `node drain/resume <node> --reason …`, `node reboot <node>` (drain, wait for jobs, reboot, run checks, resume), `maintenance start/end`, `upgrade <node>` (OS, driver or Slurm; one node at a time) |
| Software | `software list`, `software install <name> <version>` (from a recipe in the repo, as an Lmod module), `software remove <name> <version>` |
| Health, tests, backups | `health` (one-screen status), `test [--quick\|--live]`, `backup run`, `backup verify` |

**Rules for every command**
- **Same result every time:** running a command twice is safe. A top-up needs an invoice reference, so the same invoice can't be added twice.
- **Settings stay in one place:** commands that change settings (`user set`, `user suspend`, …) edit `customers.yml`, apply it and commit it. The file stays the single source of truth.
- **Preview first:** a change shows what it will do and asks. `--dry-run` only shows; `--yes` skips the question, for cron jobs and agents.
- **Readable by programs:** `--json` output, and clear exit codes: 0 done, 1 failed, 2 refused (bad input or not allowed).
- **Logged:** every run records who ran it, when, with which arguments and repo version, and the full output (`/var/log/cluster-ops/`). Money changes are also ledger entries.
- **Permissions by role:** only admins can run `./cluster`. A cron job or agent gets a role listing exactly which commands it may run. For example, a reporting agent may run `credits balance` but not `credits topup`.

## Open questions
- ~~Q1. Usernames~~ → **decided:** two letters + two digits, random (section 3).
- ~~Q2. Hide nodes and GPUs?~~ → **decided:** customers can see them (section 5).
- **Q3.** Admin logins only through a WireGuard VPN (also in the office), since the upstream network is shared?
- ~~Q4. Size per GPU~~ → **decided:** 5 cores + 20 GB, sized for 11 GPUs (section 7).
- ~~Q5. Store job scripts?~~ → **decided:** yes, 60 days (section 8).
- ~~Q6. Files at zero balance?~~ → **decided:** kept and charged; deleted after 30 days negative (section 9).
- ~~Q7. Credit expiry~~ → **decided:** 12 months, soonest-expiring first; no free trials (section 9).
