# Slurm system design

**Status: DRAFT, 2026-10-19 (eighth round).** Built from the user's requirements given that day. This page is the overall shape; [`plan.md`](plan.md) has the details of each piece.

## Changes by round (2026-10-19)
1. First draft from requirements 1–6.
2. Job sizes, what's recorded per job, credits, ready-made packages. Decided: usernames, nodes visible to customers.
3. Sizes for 11 and 12 GPUs, prices with overrides, credit expiry, tests. Decided: 60-day job scripts, files at zero balance.
4. Decided: 5 cores + 20 GB per GPU, 12-month expiry, no free trials. Added: admin commands as code.
5. Decided: 10-minute grace period with signals, 150 GB per customer on `/raiddrive`, VPN later. Added: what customers can see.
6. Decided: no internet from compute nodes. Found: douglas1's memory slots are full, so more RAM means new sticks (COP-43).
7. Corrected: no internet for **customers' jobs**; admins reach the internet from compute nodes through a logged proxy on anton. System packages come from a mirror before the second node. Step-by-step build plan in [`build-plan.md`](build-plan.md).
8. Independent plan review applied ([`reviews/2026-10-19-plan-review.md`](reviews/2026-10-19-plan-review.md)). Fixed: the credit limit formula, storage enforced by group quotas, Slurm's own job-script purge, no GPU energy accounting, `ProtectProc` instead of `hidepid`, integer billing units, one partition per GPU model, running jobs charged hourly, CUDA 12.8+. New questions Q8–Q9.
9. Tests are written with each build step and run on the cluster, not GitHub. Customer folders live under `/cluster`, so admin home folders stay local.
10. Built (2026-10-20): amounts are whole micro-credits; prices are recorded per customer with the time they took effect; every apply sets prices and Slurm credit limits (`cluster-billing sync`); customers' only sudo is their four billing views (SOP-162).

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
13. A job that's still running when its customer runs out of credits gets a grace period, with a warning signal to the code before it's stopped.
14. Customers can see their own usage, charges, prices and price history.
15. Customers' jobs can't reach the internet. Admins can, from the compute nodes too, to install things.
16. Customers install their own software (user, 2026-10-21), with tests that it works. How much we install by default is Q10.

## 1. Tracking per user
- Slurm's accounting (`slurmdbd` + MariaDB on anton) records every job and keeps the records forever. Section 8 lists exactly what's recorded.
- Each user belongs to a customer account. Bills are per customer, broken down by user.

## 2. The config file
The admin edits one file, `config/customers.yml`:

```yaml
defaults:                      # apply unless a customer or user overrides them
  storage_gb: 150              # per customer: all its users' home folders plus its project folder
  max_gpus: 4                  # GPUs one user can hold at once

customers:
  c4821:                       # neutral customer code (section 3)
    name: Acme Robotics        # admin-only; never copied onto the cluster
    billing_email: ap@acme.example
    storage_gb: 1000           # override: this customer bought more
    max_gpus: 8                # across all of the customer's users
    rates:                     # only the prices that differ from the default (section 9)
      gpu_hour.rtx5070ti: 0.40
    users:
      kx47:
        name: Alice Chen       # admin-only
        email: alice@acme.example
        ssh_key: ssh-ed25519 AAAA... alice@laptop
        max_gpus: 6            # override for this user
        role: manager          # sees all of this customer's usage and charges (section 9)
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
- Customers have no sudo. They can only log into a compute node while one of their own jobs is running on it (`pam_slurm_adopt` with `action_adopt_failure=deny`, Slurm's `PrologFlags=contain`, and `pam_systemd` removed from sshd's login steps). Slurm doesn't run jobs as root (`DisableRootJobs=YES`).
- Customers' SSH keys are kept in root-owned files (`/etc/ssh/authorized_keys/<user>`), so a customer can't add keys and share an account.
- Customers only see their own data:
  - their own jobs and usage (Slurm `PrivateData=jobs,usage,users,accounts`, set in both `slurm.conf` and `slurmdbd.conf`. Without the second, `sacct` shows other customers' data.)
  - their own files (home folders `0700`, the folder holding them `0711` so it can't be listed; a project folder is readable only by that customer)
  - their own processes. Mounting `/proc` with `hidepid` isn't supported on Rocky 9 (it breaks systemd), so sshd and slurmd run with systemd's `ProtectProc=invisible` instead. Everything a customer starts inherits a `/proc` that hides other users' processes. To be tested.
- Admin material is readable by root only: this repo and the config files, the vault password, the ops logs, the database credentials (`slurmdbd.conf`, mode `0600`), the munge key and the saved job scripts. Only admin accounts are Slurm administrators.
- **Admin logins through a VPN, later** (decided, Q3: on the to-do list, not needed at launch).
  - anton's upstream network is shared with other machines (plan D11), so "from the local network only" isn't private enough.
  - Until then, admin accounts log in with SSH keys from the local network. Later, they can log in only through a WireGuard VPN on anton (in the office too) and from the cluster network.
  - Root can't log in over SSH at all.
  - Customers log in from the internet with SSH keys only, so a stolen customer key gives no route to an admin account.
  - Before direct admin logins are switched off, the VPN login is tested and a way back in is checked (a screen and keyboard on anton, or its BMC).
- **No internet for customers' jobs; admins can reach it** (decided 2026-10-19).
  - anton doesn't route traffic, so compute nodes have no direct internet, and nothing outside can reach a node.
  - **Admins** on a compute node reach the web through a proxy on anton (squid), which listens on the cluster network only and logs every request. That covers `dnf`, `curl`, `pip` and `git` over HTTPS (plan SOP-103).
  - **Customer accounts** (UID 2000 and up) on compute nodes can reach only the cluster network: not the internet, the office network, the BMC, or the admin proxy. The node's own firewall enforces this by account, so it applies to everything a job runs, containers included (SOP-104).
  - System packages come from a mirror on anton before the second node or first customer (plan D46). Until then douglas1 installs through the proxy, with the key versions pinned.
  - Customers download data, code and Python packages on anton (the login node) into their shared folders, and their jobs use them from there.
  - A weekly test checks that a job can't get out.
- On the upstream network, anton offers only SSH (and later the VPN port). Slurm, munge, the database and NFS listen only on the cluster network.
- The commands customers get (`credits`, `myusage`, `mystorage`, `prices`) only show the caller's own data (section 9).
- **Usernames: two letters + two digits** (e.g. `kx47`), random, unrelated to the person's name (decided, Q1).
  - Letters that look like digits (`i`, `l`, `o`) aren't used, and `zz` is reserved for test accounts (section 11). That still leaves about 52,000 names.
  - Customer groups and Slurm accounts get neutral codes too (e.g. `c4821`).
  - Real names, emails and company names stay in the admin config. They are never written into `/etc/passwd`, which every user can read.

## 4. Compute and storage: tracking, limits, billing
- **Compute** comes from Slurm accounting, priced per GPU-hour (by GPU model) and per CPU-hour (section 9, plan D29).
- **Where:** all shared storage is on `/raiddrive` on anton (the 3.7 TB mirrored pair), shared to the nodes over NFS. That covers home folders, customer project folders and shared software. Scratch is local to each node. If storage moves to a bigger server later (plan D22), the paths customers see stay the same. Customers see it as `/cluster/home/<user>`, `/cluster/projects/<customer>` and `/cluster/software` on every machine. Admin home folders stay in `/home`, local to each machine.
- **Storage limits: 150 GB per customer by default** (decided 2026-10-19), overridable per customer. Writing past the limit fails. An email warning goes out at 90%.
  - The limit is enforced and billed as an XFS **group quota** on the customer's group. Each user's only group is their customer's group, and project folders are setgid, so every file they create counts against it. A user can't move a file to a group they're not in.
  - A project quota on its own isn't safe: a file's owner can change the file's project ID and escape both the limit and the bill. So the project quota on each customer's folders is kept only so that `df` shows their limit.
  - User quotas give the per-user breakdown.
  - Each user therefore belongs to exactly one customer. A person working for two customers gets two accounts.
  - `/raiddrive` is mounted without quotas today. Turning them on needs an fstab change and a full unmount and mount (a remount silently ignores quota options), done while it's still empty.
  - Tested weekly: changing a file's project ID or group doesn't move it out of the customer's limit or bill.
- **Storage measurement:** every hour a collector records each user's and each customer's usage in the accounting database.
- **Storage billing:** the month's **peak**, meaning the highest hourly reading, times the price per GB. The quota is only a ceiling; customers pay for what they actually used at the peak. Section 9 explains how this draws credits during the month.
- Scratch space on compute nodes is wiped after each job and isn't billed separately.
- **Monthly statement** per customer: compute by user plus peak storage, built from the same database.

## 5. Hiding the total disk space
- With a project quota on the customer's folders, `df` on a path inside them shows **their customer's limit** as the size of the disk, not the 3.7 TB. A plain `df` of the whole filesystem still lists 3.7 TB, and `quota` doesn't show project quotas to normal users. `mystorage` shows customers their real numbers.
- Limitation: on the machine that physically holds the disks (anton today), a technical user can still read the raw disk sizes, for example with `lsblk`. Hiding them completely means customers log into a separate login node that only reaches storage over NFS (plan D6). The medium-size plan already needs that node within the year.
- During the build we log in as a test customer and record exactly what is visible.
- **Nodes and GPUs stay visible** (decided, Q2): customers can see with `sinfo` which nodes and GPUs exist and which are busy.

## 6. Mixed GPU and CPU nodes
- Each node is one entry in `config/nodes.yml`: name, type, CPU sockets and cores, memory, GPU model and count, local scratch, and its per-GPU job size (section 7). Slurm's node list is generated from it.
- Partitions by node type, starting with `gpu` and `cpu`. GPUs are registered with their model (`gpu:rtx5070ti`), so a job can ask for a model (`--gpus=rtx5070ti:2`), and each model can have its own price.
- Billing weights can only be set per partition, so each GPU model gets its own partition once there's a second model (e.g. `gpu-5070ti`). A job can still say "any GPU" by listing several partitions.
- These GPUs (Blackwell) need code built with CUDA 12.8 or newer, or shipped with PTX. Older PyTorch builds fail on them. The user guide says so, and the weekly test checks it.
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
- Note: 20 GB of RAM per 16 GB GPU is lean for machine-learning work. A common rule of thumb is 1.5–2× the GPU's memory. All 8 memory slots already hold 32 GB sticks (DDR4-2133), so more RAM means replacing them. For example, 8× 64 GB DDR4-3200 = 512 GB is roughly 44 GB per GPU with 11 GPUs, and faster memory too (Linear COP-43). The per-GPU size would be raised then.
- **Defaults:** a job gets the full per-GPU share unless it asks for less: `DefCpuPerGPU=10` (Slurm counts each hardware thread as a CPU, so 5 cores is 10) and `DefMemPerGPU=20G`. It can't ask for more. A job that needs more RAM takes more GPUs.
- **Checked at submission:** Slurm has a "default memory per GPU" setting but no "maximum per GPU" one. A short `job_submit.lua` script (run by Slurm on every submission) therefore rejects oversized jobs with a clear message, e.g. "gpu partition: at most 5 cores and 20 GB per GPU". `EnforcePartLimits=ALL` rejects jobs that break partition limits at submission instead of leaving them queued forever.
  - The script also checks changes to waiting jobs (`scontrol update`), rejects `--mem=0` and `--exclusive`, and handles every way of asking for GPUs. It does no file or network access, because Slurm runs it while holding its locks.
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
- **Not GPU energy:** Slurm's GPU energy plugin only works with AMD's library, so it records nothing on NVIDIA cards. If we want electricity cost per job, a small sampler can record `nvidia-smi` power readings outside Slurm (later, optional).

**Job scripts: kept 60 days, then deleted** (decided, Q5).
- Slurm stores them itself (`AccountingStoreFlags=job_script`) and deletes them after 60 days (`PurgeJobScriptAfter=60days` in `slurmdbd.conf`). Customers can read their own with `sacct -B`.
- The nightly database backups leave out the job-script table, so no copy outlives the 60 days.
- The terms tell customers that scripts are kept for 60 days.
- Tested: the script is stored, other customers can't read it, and it's gone after day 60.

**Possible, but not recorded:**
- **Environment variables** (`AccountingStoreFlags=job_env`). They often contain passwords and API tokens.
- **Detailed time-series profiles** of every job (the HDF5 profiling plugin): lots of disk for little benefit.
- **Whole-node power from the BMC** (IPMI): possible later, if we want electricity cost per job.
- **InfiniBand and Lustre counters:** we have neither.

**Outside Slurm:** nothing records what happens inside a job (the commands, files or network traffic). Logins (who, when and from which IP) and every admin action are logged (plan section 15).

## 9. Prices and credits
### Prices
- `config/rates.yml` is the **default price list**: per GPU-hour by GPU model, per CPU-core-hour (Slurm counts threads; the charging script converts), and per GB-month of storage. Amounts are stored as whole numbers of the smallest unit (D40), never as floating point.
- A customer can have its own prices under `rates:` in `customers.yml` (section 2). Anything not listed there comes from the default list. Alternatively, a customer gets `discount_percent: 15` off the whole default list. Where a customer has both, their own `rates:` win for the items listed.
- Prices have start dates. A job is charged at the prices in effect when it started. Changing a default price doesn't affect a customer who has their own price for that item. The statement shows the price used on every line.
- Slurm only measures resource units, the same for everyone. Slurm stores them as whole numbers, so the weights are integers. On douglas1, 1 unit is a tenth of one GPU's share (`TRESBillingWeights=CPU=1,Mem=0.5G,GRES/gpu=10`), so a 1-GPU job (10 threads, 20 GB) is 10 units whichever share is largest. Prices are applied by our charging script.

### Credits
The full design is in plan section 12.2. In short:
- Customers buy credits up front. An append-only **ledger** is the money record. Every top-up, job charge, refund, adjustment and expiry is one entry, and the balance is their sum.
- **Slurm enforces the balance.** Each customer gets a QOS (a Slurm limit group) with `Flags=NoDecay`, plus `AccountingStorageEnforce=associations,limits,qos,safe`.
  - Slurm compares the limit with the QOS's lifetime usage. So every few minutes the sync sets `GrpTRESMins=billing=` to **usage so far + what the balance still buys − what running jobs have used but not yet been charged**. Usage is never reset. If Slurm's state is ever lost, the next sync recomputes the limit from the ledger.
  - The balance is converted to units at the customer's highest price per unit, so a mix of partitions can't overspend.
  - "NoDecay" means used credits never come back on their own. Fair-share scheduling still works normally, because it uses a separate measure that does decay.
  - "safe" means a job only starts if the balance covers its whole time limit.
  - When the balance runs out, new jobs wait with a clear reason. Running jobs get a 10-minute grace period (below).
- **Running jobs are charged every hour**, and finally when they end. The balance stays close to real time.
- **Storage draws credits as the month's peak rises.** Each hourly reading above the month's previous peak charges the difference, so by month end the storage charge equals peak × price, with no surprise bill. The first reading each month charges the full current use, because each month's peak starts from zero. A storage price change takes effect on the 1st of the following month.
- **Charges are keyed on Slurm's database record ID** (`DBIndex`, read with `sacct -D`), not the job ID. A requeued job keeps its ID, and IDs restart if the controller's state is lost. Each run rescans several days back, in case records reached the database late.
- Low-balance emails at 20% and 5%.
- **At zero balance** (decided, Q6): jobs stop. Files stay and storage keeps charging. The balance can go slightly negative, but only through storage and the 10-minute grace; the next top-up covers that first. Starting a job never overdraws (plan D41). After 30 days negative, with email warnings, an admin deletes the files with a confirmed command (`./cluster customer purge`). It's never automatic.

### Stopping a running job early
This covers running out of credits, emergency maintenance and, later, preemption.
- With the "safe" rule a job only starts if the balance covers its whole time limit, so running out mid-job is rare. It can still happen when storage charges or an expiry lower the balance while a job runs.
- **Our script stops the job, not Slurm.** With `safe`, Slurm never kills a running job over a limit, even if the limit drops after the job started. So a job that outlives the balance keeps running until the grace step shortens it.
- **Grace step: 10 minutes** (decided 2026-10-19). The job's time limit is shortened to "now + 10 minutes" (`scontrol update JobId=… TimeLimit=…`), and the customer gets an email. Slurm's normal end-of-job sequence then takes over.
- **Signals (the warning to the code):**
  - At the end of the time limit, Slurm sends `SIGTERM` ("stop now and save your work"), waits `KillWait` (set to 60 s), then sends `SIGKILL` (forced stop).
  - A customer can ask for an earlier warning. `#SBATCH --signal=B:USR1@600` means "send my script `SIGUSR1` 10 minutes before the end". Their script catches it and saves a checkpoint. When we shorten the time limit, this warning fires right away (tested).
  - We never send a signal the job didn't ask for. A program that doesn't handle `SIGUSR1` is killed by it, so an unrequested "warning" would be the shutdown itself.
  - The user guide has a ready-to-copy checkpoint example.
- **The grace minutes are charged** like any other usage. The balance goes slightly negative, and the next top-up covers it.
- **Planned maintenance doesn't kill jobs.** It's scheduled ahead as a Slurm reservation. Jobs whose time limit would overlap it don't start, so running jobs finish first. Emergency maintenance uses the grace step (`./cluster maintenance start --now`).
- **Preemption** (not at launch, plan D25) would use the same signals: `GraceTime=600` gives a preempted job 10 minutes after its `SIGTERM`.

### Expiry (Q7)
- Each top-up is its own **batch** of credits that expires 12 months after purchase (decided, Q7). There are no free trials (plan D43).
- Charges use the **batch that expires soonest** first. With equal terms that's simply oldest first (FIFO). Using newest first would let more of a customer's credits expire, which is unfair and invites disputes.
- When a batch expires, whatever is left in it becomes an `expiry` entry in the ledger. Customers get a warning 30 days before, and statements show each batch and its expiry date.
- Edge cases, each with a test:
  - A charge bigger than the soonest batch takes the rest from the next one.
  - A job still running when a batch expires has already paid for its earlier hours from that batch (hourly charging); later hours come from the next batch.
  - A refund comes back as a new batch valid 12 months.
  - Expiry happens at midnight UTC on the date shown.
  - The Slurm limit drops the moment a batch expires.
- Not hard if built into the ledger from the start; harder to add later. It's one of the most heavily tested parts.
- Have the terms checked by whoever reviews contracts. Expiring prepaid credits are normal between businesses, but rules for consumer prepaid cards differ by state.

### What customers can see
All of it is the customer's own data only. Each command takes `--json`.
- `credits`: the balance, each credit batch with its expiry date, and every ledger entry (top-ups, charges, refunds, expiries).
- `myusage [--month 2026-10]`: every job with its resources, run time, the price used and the charge, plus totals by month.
- `prices`: the customer's prices now, and every past price with the dates it applied, marked as their own price or the default list.
- `mystorage`: current use, the month's peak so far, the limit, and what that peak costs.
- **Monthly statement** by email on the 1st.
- **Managers:** users marked `role: manager` in `customers.yml` see all of their customer's usage and charges. Other users see only their own. Managers aren't Slurm "coordinators", which could change limits and cancel jobs.
- These commands go through a small read-only helper that knows who's calling and returns only that caller's data. Customers never read the database directly.
- A web page can come later (plan D26).

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

Tests are written in the same build step as the thing they test ([`build-plan.md`](build-plan.md)), and they run on the cluster itself.

**`./cluster test` runs the suite, in three layers:**
1. **Code tests** take seconds and don't need the cluster. They cover the ledger, credit batches and expiry, price overrides, storage peak charging, what `apply` would change, and the username generator. They run on anton, as part of every `./cluster test`. `./cluster apply` runs them first and stops if one fails.
2. **Live tests** run on the real cluster as the test users:
   - **isolation:** can't see the other test customer's jobs, files or processes; no sudo; can't log into a node without a running job; `df` shows only their own limit
   - **limits:** an oversized job is rejected; a job over its memory is killed; a job sees only its own GPUs; a CPU-only job in `gpu` is rejected
   - **credits:** a job doesn't start at zero balance, or if its time limit wouldn't fit the balance; charges match the expected amount to the cent
   - **storage:** writing past the quota fails; changing a file's project ID or group doesn't move it out of the customer's limit or bill; the hourly collector recorded a reading
   - **GPUs:** a short CUDA test on every GPU, built with CUDA 12.8+
   - **access:** password login is refused; once the VPN is in place, admin login from the upstream network is refused
   - **network:** a job on a compute node can't reach the internet, the office network, the BMC or the admin proxy
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
| Software | `software list`, `software build [name]` (whatever `config/versions.yml` pins and isn't built), `software check` (SOP-144) |
| Packages | `mirror sync` (take a new dated snapshot), `mirror use <date>` (point the nodes at a snapshot) |
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
- ~~Q3. Admin logins through a VPN?~~ → **decided:** yes, later; it's on the to-do list (section 3).
- ~~Q4. Size per GPU~~ → **decided:** 5 cores + 20 GB, sized for 11 GPUs (section 7).
- ~~Q5. Store job scripts?~~ → **decided:** yes, 60 days (section 8).
- ~~Q6. Files at zero balance?~~ → **decided:** kept and charged; deleted after 30 days negative (section 9).
- ~~Q7. Credit expiry~~ → **decided:** 12 months, soonest-expiring first; no free trials (section 9).
- **Q8.** A separate login host for customers before the first customer (at minimum a VM on anton)? Today customers would log into anton, which holds the money records, every key and the admin tools. The review rates this the biggest risk.
- **Q9.** Keep customers' names and emails encrypted in the repo (Ansible Vault)? Today they'd be plain text in `customers.yml`, pushed to GitHub.
- ~~**Q10.** How much software do we install?~~ → **decided 2026-10-21:** a shared default stack in `/cluster/software`, free and read-only, on the RAID over NFS (option A). That's Miniforge, PyTorch and its container image, with modules, plus Apptainer and the base packages. Customers install everything else themselves, on top (SOP-143, SOP-144). The discussion is kept below.
  - **Recommendation:** customers install everything themselves: pip and venvs, conda or micromamba, their own CUDA (12.8 or newer, for these GPUs), and containers. We install only what needs root:
    - the NVIDIA driver
    - a fixed list of system packages on the login node and every GPU node: compilers, build tools and common libraries (most are already there)
    - Apptainer, so any Docker or NVIDIA NGC image runs without root
  - No shared software modules (Lmod), so section 12's `software install` command would go, unless customers ask for it.
  - Installs need the internet, so they happen on the login node. Today that's anton, which adds weight to Q8.
