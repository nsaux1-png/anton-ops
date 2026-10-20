# Slurm system design

**Status: DRAFT, 2026-10-19 (second round).** Built from the user's requirements given that day. This page is the overall shape; [`plan.md`](plan.md) has the details of each piece.

## Requirements (user, 2026-10-19)
1. Track usage per user.
2. One simple config file to change people's settings.
3. The admin side is completely closed to users.
4. Track both compute usage and disk space. Disk space has limits, and storage is billed on the month's peak usage.
5. Users shouldn't be able to see the total disk space.
6. Ready for more GPU nodes and CPU nodes of different kinds.
7. Limits on how much memory and CPU a job can take with its GPUs. Nobody can take 3 GPUs and all of the node's memory.
8. Prepaid credits that are drawn down as customers use the cluster.

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
- Prices go in `config/rates.yml` and machines in `config/nodes.yml`.

## 3. Admin side closed off
- Customers have no sudo. They can only log into a compute node while one of their own jobs is running on it (`pam_slurm_adopt`).
- Customers only see their own data:
  - their own jobs and usage (Slurm `PrivateData=jobs,usage,users,accounts`)
  - their own files (home folders `0700`, the folder holding them `0711` so it can't be listed; a project folder is readable only by that customer)
  - their own processes (`/proc` mounted with `hidepid`)
- Admin material is readable by root only: this repo and the config files, the vault password, the ops logs, the database credentials (`slurmdbd.conf`, mode `0600`) and the munge key. Only admin accounts are Slurm administrators.
- **Admin logins only from the local network** (pending Q3). sshd allows the admin group only from the LAN and the cluster network. Root can't log in over SSH at all. Customers log in from the internet with SSH keys only, so a stolen customer key gives no route to an admin account. Remote admin later goes through a VPN (WireGuard) into the LAN.
- The commands customers get (`credits`, `myusage`, `mystorage`) only show the caller's own data.
- **Usernames: two letters + two digits** (e.g. `kx47`), random, unrelated to the person's name (decided, Q1). Letters that look like digits (`i`, `l`, `o`) aren't used, which still leaves 52,900 names. Customer groups and Slurm accounts get neutral codes too (e.g. `c4821`). Real names, emails and company names stay in the admin config. They are never written into `/etc/passwd`, which every user can read.

## 4. Compute and storage: tracking, limits, billing
- **Compute** comes from Slurm accounting, priced per GPU-hour (by GPU model) and per CPU-hour (plan D29).
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
douglas1 has 56 cores (112 threads), 251 GB RAM and 10 GPUs.

- **Reserved for the system:** 2 cores and about 11 GB stay with the OS and Slurm (`CoreSpecCount`, `MemSpecLimit`). No job can starve the node itself.
- **Per GPU:** at most **5 cores (10 threads) and 24 GB RAM**, which is a tenth of what's left. A job gets exactly that by default (`DefCpuPerGPU`, `DefMemPerGPU`). It can ask for less, but not more. A job that needs more RAM takes more GPUs (Q4).
- **Checked at submission:** Slurm has a "default memory per GPU" setting but no "maximum per GPU" one. A short `job_submit.lua` script (run by Slurm on every submission) therefore rejects oversized jobs with a clear message, e.g. "gpu partition: at most 5 cores and 24 GB per GPU". `EnforcePartLimits=ALL` rejects jobs that break partition limits at submission instead of leaving them queued forever.
- **Enforced while running:** cgroups hold each job to what it was given. A job that goes over its memory is killed and recorded as `OUT_OF_MEMORY`. It only sees its own GPUs.
- **GPU nodes run GPU jobs only:** a job in `gpu` must ask for at least one GPU. Otherwise a CPU-only job could take the cores and memory and leave GPUs that nobody can use.
- **Billing safety net:** `PriorityFlags=MAX_TRES` bills a job for the **largest share of the node** it holds, whether that's GPUs, cores or memory. With the fixed size per GPU this just equals the GPU count. It matters if we loosen the size later, and on CPU nodes: 1 core with all the RAM is billed as the whole node.
- **Other limits** (from `customers.yml`): GPUs held at once per user and per customer, maximum job length (plan D23: 7 days, 1 hour default), and a cap on queued jobs per user.
- **CPU nodes (later):** a default and maximum memory per core, billed with the same largest-share rule.

## 8. What Slurm records for each job
**Recorded (kept forever):**
- **Who and where:** job ID, name, user, customer account, partition, QOS, working directory, node(s), and which GPUs.
- **When:** submitted, started and ended; time limit; elapsed time; time spent waiting in the queue.
- **Allocated:** CPUs, memory, GPUs by model, and billing units. This is what's charged.
- **Outcome:** final state (completed, failed, cancelled, timeout, out of memory, node failure) and exit code. A node failure triggers an automatic refund (plan D31).
- **Actual use, sampled every 30 s** (`jobacct_gather/cgroup`): CPU time, peak and average RAM, disk read/write, for each job step.
- **GPU use** from NVIDIA's NVML: GPU utilization and GPU memory per job (`gres/gpuutil`, `gres/gpumem`). Customers can see how well they used what they paid for, but we still charge for what was allocated (plan 12.1).
- **GPU energy per job** (`acct_gather_energy/gpu`), so we know the electricity cost of each job and customer.

**Possible, but not recorded (proposal):**
- **The job script and environment variables** (`AccountingStoreFlags=job_script,job_env`). They're the customer's code and often contain passwords or API tokens, so we'd be holding secrets we'd have to protect. Billing doesn't need them. The cost: abuse or a dispute is harder to investigate (Q5).
- **Detailed time-series profiles** of every job (the HDF5 profiling plugin): lots of disk for little benefit.
- **Whole-node power from the BMC** (IPMI): Slurm runs one energy source at a time, and GPU energy covers most of the power draw.
- **InfiniBand and Lustre counters:** we have neither.

**Outside Slurm:** nothing records what happens inside a job (the commands, files or network traffic). Logins (who, when and from which IP) and every admin action are logged (plan section 15).

## 9. Credits
The full design is in plan section 12.2. In short:
- Customers buy credits up front. An append-only **ledger** is the money record. Every top-up, job charge, refund and adjustment is one entry, and the balance is their sum.
- **Slurm enforces the balance.** Each customer gets a QOS (a Slurm limit group) with `Flags=NoDecay` and `GrpTRESMins=billing=<balance>`, plus `AccountingStorageEnforce=associations,limits,qos,safe`. "NoDecay" means used credits never come back on their own. Fair-share scheduling still works normally, because it uses a separate measure that does decay. "safe" means a job only starts if the balance covers its whole time limit. When the balance runs out, new jobs wait with a clear reason, and running jobs finish.
- **Storage draws credits as the month's peak rises.** Each hourly reading above the month's previous peak charges the difference, so by month end the storage charge equals peak × price, with no surprise bill.
- Low-balance emails at 20% and 5%. The `credits` command shows the balance, this month's use and the projected cost of running jobs.
- Open: what happens to a customer's files when the balance hits zero (Q6).

## 10. Ready-made packages considered
- **OpenHPC:** prebuilt Slurm and HPC tools for Rocky 9. It would save building Slurm, but Slurm upgrades then wait on its release schedule, and its NVIDIA GPU support would need checking. Building from SchedMD's source is one `rpmbuild` command in a script, so we keep our own build (plan section 9).
- **ColdFront** and **Waldur:** allocation portals that drive Slurm. ColdFront is built for universities (grants and allocations, not money); Waldur is a full cloud marketplace. Both are big systems to run for this size. Not now.
- **Open XDMoD:** usage reports and dashboards from Slurm data. Maybe later.
- **Open OnDemand:** a web portal for customers (files, jobs, Jupyter). Later (plan D26).
- **Payments:** we don't build payment handling. When customers pay online, a payment service (e.g. Stripe) records top-ups in our ledger (plan D33, D44).

**Result:** Slurm's own features do the accounting, limits and credit enforcement. Our own code is small: `./cluster apply`, the ledger and charging script, the storage collector, statements, and `job_submit.lua`.

## Open questions
- ~~Q1. Usernames~~ → **decided:** two letters + two digits, random (section 3).
- ~~Q2. Hide nodes and GPUs?~~ → **decided:** customers can see them (section 5).
- **Q3.** Admin logins only from the local network, with a VPN for remote admin later? Depends on who else is on the upstream network (plan D11).
- **Q4.** Fixed size per GPU (5 cores, 24 GB, no more), or let a job take up to double that and pay for the largest share it holds?
- **Q5.** Store job scripts (not environment variables), e.g. for 30 days, to investigate abuse?
- **Q6.** When a customer's balance hits zero: jobs stop, but what about their files? Proposal: the files stay and storage keeps charging, letting the balance go negative for storage only. After 30 days in the negative (with warnings) the files are deleted.
