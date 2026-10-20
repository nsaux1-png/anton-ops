# Cluster plan

**Status: DRAFT, being worked out together. Nothing in here is installed yet.**

How to read this:
- Each section gives a **proposal** (what Claude suggests) and **decisions** marked **D1, D2, …** with a recommended answer.
- When we agree a decision, it moves to [`decisions.md`](decisions.md) with the date and reason, and the plan text is updated.
- Nothing is built until the sections it depends on are agreed.

---

## 1. Goals and scope

**Goal:** a Slurm cluster we can sell compute time on. Customers log in, run CPU and GPU jobs, and are billed accurately for what they used. Every change to the cluster is scripted, logged and repeatable.

**Proposal**
- One head node (anton) and a growing set of compute nodes: GPU nodes like douglas1, plus dual-socket CPU nodes.
- Everything is driven from this repo: adding a user, node, GPU or disk is an edit plus a re-run.
- Users only touch the cluster through Slurm. No direct logins to compute nodes, except into nodes where they have a running job.

**Decisions**
- **D1. Who are the customers?** (a) external paying companies, (b) internal teams with chargeback, (c) both. This affects isolation, contracts and security. *Recommended: plan for (c) and design for external customers.* **→ Decided 2026-10-19: external only; internal users go through the same system.**
- **D2. Expected size in a year:** number of users, number of nodes. *Needed to size the head node, storage and network. Rough guesses are fine.* **→ Decided 2026-10-19: medium, 20–100 users, 4–10 nodes.**
- **D3. Service level:** is this best-effort ("we fix it next business day"), or do customers expect uptime guarantees? *Recommended: best-effort at launch, stated in the terms.* **→ Decided 2026-10-19: best effort.**

---

## 2. Machines and roles

| Role | Machine | Runs |
|---|---|---|
| Head node | anton | Slurm controller, accounting DB, login, NFS server, package mirror, time server, Ansible, monitoring |
| GPU compute | douglas1 | slurmd, NVIDIA driver, 10× RTX 5070 Ti |
| Future GPU compute | TBD | same as douglas1 |
| Future CPU compute | dual-socket nodes, TBD | slurmd |

**Concerns with current hardware**
- **anton's network is 1 Gb.** Every compute node reads `/home` and datasets from anton over that link. With 10 GPUs on douglas1, this will be the main bottleneck for data-heavy jobs.
- **douglas1 has only a 256 GB disk** for 10 GPUs, so there's no room for local scratch or datasets.
- **anton is both head and login node.** If customers run heavy work on the login node (compiling, unpacking big files), it slows the scheduler and the NFS server. That's fine at small scale, but it's the first thing to split off as we grow.
- **Power and cooling:** 10 GPUs is roughly 3 kW under load. Is there a UPS, and is the room cooled for it?

**Decisions**
- **D4. Network upgrade:** add a 10 Gb (or faster) link between anton and compute nodes? douglas1 already has a second, unused port (`enp66s0f0np0`), likely fast; anton would need a NIC and there'd need to be a switch. *Recommended: yes, before paying customers run data-heavy GPU work.* **→ Decided 2026-10-19: 10 Gb card in anton, cabled straight to douglas1; switch with the second node. Linear COP-42.**
- **D5. Local scratch on GPU nodes:** add NVMe drives to douglas1 for fast per-job scratch? *Recommended: yes, 2–4 TB.*
- **D6. Separate login node later:** *Recommended: start with anton as login node, split when we pass ~10 active users or see login-node load problems.*
- **D7. UPS:** is there one? If so, can it signal shutdown? **→ Decided 2026-10-19: no UPS.**
- **D47. Power for douglas1** (about 3.3–3.6 kW at full load). **→ Decided 2026-10-19: the power supply is adequate; GPUs run at full power, no software cap.**

---

## 3. Network

**Proposal**
- **Cluster network 172.16.50.0/24**, private, never reachable from outside.
- **Address plan** (written down so new nodes don't collide):
  - `.1` anton
  - `.2–.9` reserved for infrastructure (future login node, storage server)
  - `.10–.49` GPU nodes (douglas1 = `.11`)
  - `.50–.99` CPU nodes
  - `.100–.199` reserved
  - `.200–.254` BMC/IPMI, if they get moved onto this network
- **Naming:** `douglas1`, `douglas2`, … for GPU nodes? Or a pattern by type (e.g. `gpu01`, `cpu01`)? See D8.
- **Name resolution:** `/etc/hosts` on every machine, generated from the inventory. A DNS server isn't needed until much larger.
- **No internet for customers' jobs** (user, 2026-10-19; replaces the earlier NAT plan). anton doesn't route traffic. Admins on compute nodes reach the web through a logged proxy on anton; customer accounts there can reach only the cluster network (SOP-103, SOP-104). Nodes get packages from anton's mirror (D46) and time from anton. Customers download data and software on anton, the login node, into their shared folders.
- **Firewall on anton:** upstream side allows only SSH (and later, monitoring for admins); cluster side gets its own zone with only named services open (SOP-103).
- **Customer access:** SSH to anton from the internet, keys only. Possibly a VPN instead (see D10).
- **BMC/IPMI** (remote power and console for each server): put them on their own management network, reachable only from anton or admins.

**Decisions**
- **D8. Node naming scheme.** *Recommended: keep personal names if that's your convention, but keep the type in the inventory (Slurm doesn't care).* Or switch to `gpu01`/`cpu01`.
- **D9. What is 172.16.99.0/24** on douglas1's USB network interface? **→ Answered 2026-10-19: the BMC's virtual USB link, internal to the server. Left alone.**
- **D10. How customers reach the cluster:** (a) SSH directly from the internet to anton, (b) VPN first, then SSH. *Recommended: (a) with keys only and fail2ban to start, (b) if a customer requires it.*
- **D11. Is the 192.168.4.0/22 upstream network shared with other office machines?** Affects firewall rules. **→ Answered 2026-10-19: yes, anton's switch has other machines on it. Nothing upstream is trusted; see [`slurm-design.md`](slurm-design.md) Q3 for admin logins.**

---

## 4. Operating system and installing new nodes

**Proposal**
- Rocky Linux 9 everywhere, same minor version across the cluster.
- **New node procedure:** install Rocky by hand from USB (choose minimal install, set hostname and cluster IP), add one SSH key, then run `./cluster add-node`. Ansible does everything else. A kickstart file in the repo makes the install answers identical every time.
- **Updates:** monthly maintenance window. Packages are updated on one node first, then the rest. Kernel updates need a reboot and a matching NVIDIA driver, so they're always done in the window, never automatically.
- **SELinux stays enforcing.**

### Where nodes get their packages from

Compute nodes have no direct internet (section 3); admins reach it only through a proxy. That still leaves a separate question: **where do system packages (OS updates, NVIDIA driver, Slurm) come from?** Professional clusters use one of three approaches:

| Approach | How it works | Pros | Cons |
|---|---|---|---|
| **Direct from the internet** | each node's `dnf` downloads from Rocky/EPEL/NVIDIA mirrors | nothing to set up | nodes installed a month apart get different package versions; breaks if the internet is down |
| **Proxy on the head node** | nodes download through a caching proxy (e.g. Squid) on anton | one controlled way out; caches downloads | versions still drift between nodes; another service to run |
| **Local repository mirror (snapshots)** | anton downloads the repos into dated snapshots on `/raiddrive` (e.g. `repos/2026-10-18/`); nodes install only from anton | **every node gets identical versions**; upgrades = switch to a newer snapshot, test, roll out; works with no internet; fast | ~50–100 GB per snapshot; a sync script to maintain |

Manually copying `.rpm` files over is not how it's done; the "mirror" approach is the professional version of copying, done automatically by a script.

**Proposal:** a **local snapshot mirror on anton** for system packages (Rocky BaseOS/AppStream, EPEL, NVIDIA's repo, plus our own Slurm builds). This fits "repeatable" best: a node added in six months gets exactly what douglas1 has, unless we deliberately move everyone to a newer snapshot.

**Decisions**
- **D46. Package source for nodes:** (a) direct, (b) proxy, (c) local snapshot mirror. *Recommended: (c). It can start in step 1 of the build, so no node is ever installed from a moving target.* **→ Decided 2026-10-19: (c), in place before the second node or the first customer ([`build-plan.md`](build-plan.md) phase 3). Until then douglas1 installs through the admin proxy, with the key versions pinned.**
- **D12. Network installs (PXE)** instead of USB? *Recommended: not now. Worth it at ~10+ nodes.*
- **D13. Maintenance window:** day and time each month, and how much notice customers get. *Recommended: one fixed slot per month, 1 week notice.*

---

## 5. Configuration management (how everything stays repeatable)

**Proposal**
- **Ansible** (agreed), run from anton. Repo layout:
  ```
  cluster                     the one command operators run
  config/nodes.yml            every machine: name, IPs, type, GPUs, disks (Ansible's inventory)
  config/customers.yml        customers and users: limits, prices, SSH keys, status
  config/rates.yml            the default price list (customers.yml holds overrides)
  ansible/group_vars/         cluster-wide settings (Slurm, NFS, rates…)
  playbooks/                  one per job: site.yml (everything), add-node, add-user…
  roles/                      one per component: common, nfs, slurm-controller, slurm-node, nvidia, …
  scripts/                    helpers (billing report, bootstrap)
  docs/                       plan, decisions, SOPs, ops log
  ```
- **Every run is logged** to `/var/log/cluster-ops/` with: timestamp, operator, command, git commit, whether the repo had uncommitted changes, and full output. The command refuses to run with uncommitted changes, unless forced, so every change to the cluster matches a commit.
- **Secrets** (munge key, DB passwords) are encrypted in the repo with Ansible Vault. The vault password lives only on anton, readable by root.
- **Dry-run first:** every command supports `--check` to show what would change.

**Decisions**
- **D14. Who are the operators?** Just you, or more people? Do they each get their own admin account? *Recommended: one named admin account per person, never shared; papaya is yours.*
- **D15. GitHub as the official copy:** pushes after every change? Merge requests for review? *Recommended: push after every change; merge requests once there's more than one operator.*

---

## 6. Users, accounts and access

**Proposal**
- **Source of truth:** `config/customers.yml` ([`slurm-design.md`](slurm-design.md) section 2). Each user has a name, UID (fixed forever, never reused), primary account, SSH public keys, email, and status (active/suspended/removed).
- **UID ranges:** admins 1000–1999, customers 10000+. Group IDs match.
- **Logins:** SSH keys only, no passwords. Users can't use sudo.
- **Slurm accounts:** one per customer, with sub-accounts per project if a customer wants separate bills. Each user belongs to exactly one customer (a person working for two customers gets two accounts); storage quotas depend on it.
- **Suspending a user:** keeps their files and history, but blocks login and job submission.
- **Removing a user:** login and jobs blocked, files kept for N days (D18), then deleted. Their UID is never reused, so old accounting records stay unambiguous.

**Decisions**
- **D16. Managed list vs directory service (FreeIPA/LDAP).** *Recommended: managed list in the repo now. Move to FreeIPA if we pass ~50 users or need password logins or web self-service.*
- **D17. Account structure:** one per customer, or per customer and project? *Recommended: customer → project, even if most customers only have one project.*
- **D18. Data retention after offboarding:** how many days? *Recommended: 30, stated in the terms.*

---

## 7. Storage

**Proposal**
- **anton `/raiddrive`** (3.7 TB mirror) shared over NFS:
  - `/raiddrive/home` → `/home` on all nodes (small, code and configs)
  - `/raiddrive/projects/<account>` → shared data per customer project
  - `/raiddrive/software` → shared software (modules, containers)
- **Per-node local scratch** (`/scratch`, wiped after each job) once douglas1 has local disks (D5).
- **Quotas** on home and project directories, enforced by XFS project quotas, so one customer can't fill the disk for everyone.
- **Permissions:** each home and project folder is private to its owner or account group.
- **Health:** RAID and SMART monitoring with alerts (section 13).
- **The anton OS `/home`** (152 GB on the NVMe) is no longer used for users. It's shadowed by the shared `/home`, with admin homes kept separately (`/var/lib/admin-homes`? To be settled in the build).

**Decisions**
- **D19. Quotas:** default home quota and default project quota. *Recommended: 50 GB home; project quota set per customer.* **→ Decided 2026-10-19: 150 GB per customer by default, one quota covering all its users' home folders and its project folder ([`slurm-design.md`](slurm-design.md) section 4).**
- **D20. Charge for storage?** *Recommended: yes, per GB-month above a free allowance, at least for projects.* **→ Decided 2026-10-19: yes, the month's peak × price per GB, with no free allowance ([`slurm-design.md`](slurm-design.md) section 4).**
- **D21. Backups:** RAID protects against a disk dying, not against deleted files, ransomware, or the server being lost. What's backed up, and where? *Recommended: the Slurm accounting database and the repo nightly, off-site, without exception; customer data backed up only if we sell that, and the terms say so.*
- **D22. More storage:** 3.7 TB is small for a GPU service. Plan when to add a larger storage server. *Revisit with D2's numbers.*

---

## 8. Time

**Proposal:** anton syncs from public time servers, and all nodes sync from anton. Munge and Slurm stop working if clocks drift.

*(No decisions needed.)*

---

## 9. Slurm

**Proposal**
- **Version:** current stable release from SchedMD, built into RPMs on anton by a script in the repo, with NVIDIA support (NVML), so GPUs are detected and per-job GPU use is recorded. Every node runs the same version.
- **Controller and accounting:** `slurmctld`, `slurmdbd`, MariaDB on anton. The database is on anton's NVMe, dumped nightly (D21).
- **Partitions** (queues):
  - `gpu`: GPU nodes
  - `cpu`: CPU nodes
  - maybe `debug`: short jobs, high priority, for testing
- **Resource enforcement:** cgroup v2. A job only sees the CPUs, memory and GPUs it asked for and can't use more.
- **Scheduling:** backfill, fair-share between accounts so one customer can't monopolize the cluster, time limits per partition.
- **GPU requests:** `--gpus=N` or `--gres=gpu:N`. Each GPU comes with a fixed share of CPU and RAM (on douglas1: up to 5 cores and 20 GB per GPU). See [`slurm-design.md`](slurm-design.md) section 7.
- **Node health check** before and between jobs; a sick node is drained automatically.
- **Interactive use:** `srun --pty` / `salloc` for interactive sessions, billed the same as batch jobs.

**Decisions**
- **D23. Maximum job time limit.** *Recommended: 7 days max, 1 hour default if unspecified.*
- **D24. Priority model:** pure fair-share, or customers who pay more get priority (QOS tiers)? *Recommended: fair-share now, design the QOS levels so a "priority" tier can be sold later.* **Note (review 2026-10-19): a job has only one QOS, and the QOS carries the credit limit, so a priority tier has to be a separate partition, not a QOS.**
- **D25. Preemption:** can high-priority jobs interrupt others? *Recommended: no, at launch.*
- **D26. Jupyter/web access** (Open OnDemand)? *Recommended: later; SSH first.*

---

## 10. GPU stack

**Proposal**
- **Checks before the driver install** (read-only, on each GPU node):
  - Secure Boot state. If it's on, the driver's kernel module must be signed and the signing key enrolled.
  - BIOS: "Above 4G decoding" and "Resizable BAR" on.
  - Kernel headers for the running kernel are available.
- **NVIDIA driver** (open kernel modules, required for RTX 50-series), from NVIDIA's repo for RHEL 9, built with DKMS so it's rebuilt for each new kernel. It's pinned to a tested version in the repo. Kernel and driver are updated together in the maintenance window.
- **Other hardware needs nothing extra.** The AMD EPYC CPUs, the Broadcom 10 Gb ports (`bnxt_en`), the NVMe disks and anton's LSI disk controller all use drivers built into Rocky's kernel.
- **CUDA:** users bring their own through conda/pip/containers; the driver supports them. We also provide a few CUDA versions as modules for people compiling code.
- **Containers:** Apptainer (the HPC-standard container runtime, runs without root), so customers can bring Docker images.
- **GPU monitoring:** NVML/`nvidia-smi` for per-GPU health and usage. NVIDIA DCGM targets data-center GPUs and much of it isn't supported on GeForce cards, so test what it offers here before relying on it.
- **Persistence mode** on, so GPUs don't reinitialize between jobs.
- **Known limits of RTX 5070 Ti:** 16 GB memory each, no NVLink (GPUs talk over PCIe), no ECC memory. Fine for many workloads; not ideal for very large models across many GPUs. Customers should be told.

**Decisions**
- **D27. Containers:** Apptainer only, or also Docker? *Recommended: Apptainer only. Docker gives root on the node, which isn't safe in a shared cluster.*

---

## 11. Software for users

**Proposal**
- **Lmod modules** for shared software (compilers, CUDA versions, common tools), installed under `/raiddrive/software`.
- **Conda/Miniforge** for users to install their own Python stacks in their home or project folders.
- **Apptainer** for containers (section 10).
- A short **user guide** in the repo: how to log in, submit a CPU job, submit a GPU job, check usage and costs.

**Decisions**
- **D28. Software policy:** do we install software on request, or do customers handle everything themselves? *Recommended: we maintain a small base set; customers install the rest themselves.*

---

## 12. Accounting, billing and credits

### 12.1 Measuring usage
- For every job, Slurm records the **allocated** CPUs, memory, GPUs and elapsed time, per user and account. It's kept forever in the accounting database.
- **We charge for allocated resources × time, not "used"** (industry norm: a GPU you reserved and left idle still couldn't be sold to anyone else).
- Each job's cost is expressed in **billing units**, computed by Slurm from weights we set per partition: e.g. 1 GPU-hour on douglas1 = 100 units, 1 CPU-hour = 1 unit. Different node types can have different weights, so a faster GPU can cost more.

### 12.2 The credit system

**Proposal: prepaid credits, with a ledger as the money record and Slurm as the enforcer.**

- **Credits are what customers buy.** 1 credit = a fixed amount of money (D40). Every job's cost in credits = its billing units × the credit rate.
- **The ledger** is the source of truth for money: an append-only record (database on anton, backed up nightly, D21) of every credit movement for every account:
  | Entry type | Example |
  |---|---|
  | `topup` | customer bought 1,000 credits (invoice #, who entered it) |
  | `grant` | goodwill or promotional credits, and test accounts' credits (no free trials, D43) |
  | `charge` | job 12345 used 37.5 credits |
  | `refund` | job 12345 refunded, node failure |
  | `adjustment` | correction, with a written reason |
  | `expiry` | unused credits expired (if D42 says they expire) |

  Nothing is ever edited or deleted; corrections are new entries. **Balance = sum of entries.** Every number on an invoice or statement can be traced back to jobs and entries.
- **Charging:** a script runs every few minutes, finds jobs that finished since the last run, and writes one `charge` entry per job. Each job is charged exactly once, keyed on Slurm's database record ID (`DBIndex`, not the job ID, which repeats), so re-running the script never double-charges ([`slurm-design.md`](slurm-design.md) section 9).
- **Enforcement in Slurm:** each account gets a spending limit in Slurm equal to its credit balance. When the account runs out:
  - **new jobs don't start** and show a clear reason ("account out of credits");
  - **running jobs aren't killed**;
  - Slurm can be set to **only start a job if the balance covers its full requested time limit**, so a job can't overdraw the account by running long. Customers who set realistic time limits get their jobs started sooner.
- **Sync:** after every top-up or charge, the script updates the account's Slurm limit from the ledger. Slurm is never the money record; it only enforces.
- **Known trap we avoid:** Slurm normally "forgets" old usage over time for fair-share purposes. The credit limit has to be set up so that usage **never decays**, or customers would silently regain credits. This is a specific configuration choice in the build, and it gets a test.
- **Customer-facing:**
  - `credits` command on the login node: current balance, usage this month by user and project, running jobs' projected cost.
  - Before submitting: an estimate of what a job will cost at most (its time limit × resources).
  - **Low-balance warnings** by email at e.g. 20% and 5% remaining.
  - Monthly statement per account: opening balance, top-ups, charges by user/project, refunds, closing balance.
- **Projects within a customer** (D17) can get their own sub-budgets carved out of the customer's credits, so a lab can cap each project.
- **Admin side:** `./cluster credits topup <account> <amount> --ref <invoice>`, `./cluster credits refund <jobid> --reason ...`, `./cluster credits statement <account> <month>`. Every one of these is logged like any other `./cluster` run.

### 12.3 Reporting and invoicing
- `./cluster billing-report 2026-10`: per-account, per-user CSV for the month, built from the ledger, so it re-runs to the same answer.
- Cross-check each month: ledger charges vs. Slurm's own usage totals. Any mismatch is flagged before anything goes to a customer.

**Decisions**
- **D29. Rates:** price per GPU-hour, CPU-hour, memory? Same price for all GPU types? *Your call; Claude can suggest market comparisons.*
- **D30. Pricing model:** prepaid credits only, or also pay-as-you-go (billed monthly in arrears) for trusted customers? *Recommended: prepaid credits for everyone at launch. Postpaid can be done later with the same ledger (allowing the balance to go negative up to a set limit).*
- **D31. Failed jobs:** charged? *Recommended: yes for job failures (the resources were held), automatic refund for node failures (our fault); the statement marks which is which.*
- **D32. Minimum billing increment:** per second, minute, or hour? *Recommended: per minute.*
- **D33. Invoicing:** which tool sends invoices and takes payment, and who reviews before it goes out? *Is there an accounting system (e.g. QuickBooks, Stripe) top-ups should come from?*
- **D40. What 1 credit is worth:** a fixed money amount (e.g. 1 credit = $0.01), or 1 GPU-hour-equivalent? *Recommended: tie credits to money. Prices can then change without changing anyone's balance.*
- **D41. Running out mid-job:** with the "must cover full time limit" rule a job can't overdraw by much. Do we also allow a small overdraft (grace) so jobs aren't blocked at e.g. 0.5 credits short? *Recommended: no overdraft at launch.* **→ 2026-10-19: no overdraft for starting jobs. The balance can still go slightly negative through storage and the 10-minute grace ([`slurm-design.md`](slurm-design.md) section 9).**
- **D42. Do credits expire?** *Recommended: after 12 months, stated in the terms. Expired credits are a ledger entry, not a silent deletion.* **→ Decided 2026-10-19: credits expire 12 months after purchase; the batch that expires soonest is used first. Design in [`slurm-design.md`](slurm-design.md) section 9.**
- **D43. Free trial credits** for new customers? How many? **→ Decided 2026-10-19: none. Compute is a commodity; customers buy credits from the start.**
- **D44. Top-ups:** entered by an admin after payment is received, or automatic from a payment system (e.g. Stripe webhook)? *Recommended: admin-entered at launch; automate once volume justifies it.*
- **D45. Ledger storage:** a table in the same MariaDB as Slurm accounting, or a separate database? *Recommended: same MariaDB server, separate database, backed up together.*

---

## 13. Monitoring and alerts

**Proposal**
- **Prometheus + Grafana** on anton, collecting: node health (CPU, memory, disk, network), GPU health (DCGM: temperature, errors, utilization), Slurm (queue, node states, usage), RAID and SMART status.
- **Alerts** to email or Slack for: node down or drained, RAID degraded, disk filling up, GPU errors, accounting database problems, backups failing.
- **Dashboards** for operators, and later per-customer usage views.

**Decisions**
- **D34. Where alerts go:** email, Slack, both? Who gets woken up?

---

## 14. Security

**Proposal**
- **SSH:** keys only, no root login, fail2ban, only anton exposed to the internet.
- **Customer isolation:** users can't see each other's files or processes (`hidepid` on `/proc`, private home and project folders), and can only log into compute nodes where they have a running job (`pam_slurm_adopt`).
- **Least privilege:** customers never get sudo. Admins have personal accounts with sudo, and actions are logged.
- **Updates:** security updates in the monthly window; critical ones sooner.
- **Audit trail:** who logged in when (kept), every admin run of `./cluster` (kept), sudo logs.
- **Remove the temporary passwordless sudo** once the build is done.
- **Terms of use** for customers: acceptable use (no crypto mining, no attacks), data responsibility, retention.

**Decisions**
- **D35. Two-factor login** for customers? *Recommended: not at launch; add if a customer requires it.*
- **D36. Sensitive data:** will customers bring regulated data (health, personal data)? If yes, this plan needs a stricter version. **→ Decided 2026-10-19: no regulated data at launch.**
- **D37. How Claude keeps working on the cluster after the build:** its own admin account with limited sudo, or only through operators? *Recommended: decide after the build; remove broad passwordless sudo either way.*

---

## 15. Logging and audit

**Proposal**
- System logs from all nodes forwarded to anton and kept 90 days.
- Ops run logs (`/var/log/cluster-ops/`) kept indefinitely and backed up.
- Slurm accounting kept indefinitely (it's the billing record).

**Decisions**
- **D38. Retention periods:** confirm 90 days for system logs; indefinite for accounting and ops logs.

---

## 16. Backup and disaster recovery

**Proposal**
- **Rebuild-from-repo:** anton or any node can be reinstalled and reconfigured from this repo plus the vault password. We test that once, on purpose.
- **Must back up:** Slurm accounting DB (nightly dump), `/etc` of anton, the vault password (stored offline by you), the repo (GitHub).
- **Customer data:** depends on D21.
- **Off-site target:** TBD (cloud storage bucket, another site).

**Decisions**
- **D39. Off-site backup destination.** *Recommended: a cloud storage bucket, encrypted.*

---

## 17. Standard procedures (each becomes a `./cluster` command plus a page in `docs/sop/`)

**How an SOP is made (2026-10-19)**
1. **Discovery run:** the first time, Claude works the step out on the real machine. Every command and finding goes in the ops log.
2. **Written down:** the steps become an Ansible role or script, run by a `./cluster` command, plus an SOP page covering purpose, preconditions, command, expected output, checks and rollback.
3. **Proof run:** the SOP is run again from a clean state (e.g. undo, then redo) exactly as written, with no improvising. Only then is it done. Its checks join the test suite.
4. **Running an SOP needs no AI.** Billing, credits and limits are plain code with tests. Where judgment can't be avoided (hardware faults, unfamiliar errors), the SOP is a checklist: "if this, do that; otherwise escalate".

| Procedure | What it does |
|---|---|
| `add-user` | create user on all machines, SSH key, Slurm association, quotas, welcome email text |
| `suspend-user` / `remove-user` | block login and jobs; schedule data deletion |
| `add-account` | new customer or project with billing settings and limits |
| `add-node` | bootstrap a freshly installed machine into the cluster |
| `add-gpu` | after physically adding GPUs: update inventory, driver check, Slurm config, restart node |
| `add-disk` | format, mount, add to inventory, (for anton) extend storage |
| `drain-node` / `resume-node` | take a node out of service for maintenance and back |
| `apply` | re-run everything; fixes drift |
| `billing-report` | monthly usage and cost per account |
| `upgrade` | rolling OS/driver/Slurm upgrades in the maintenance window |

---

## 18. Build order (once the plan is agreed)

Step by step, with what Claude does in each step and its SOP: [`build-plan.md`](build-plan.md).

In short: foundations (Ansible, `./cluster`, firewall, admin proxy, network limits, time) → GPU driver → package mirror → storage → users and access → Slurm → billing and credits → monitoring → backups → test suite → launch. A separate login host and removing the temporary sudo come before the first customer. [`build-plan.md`](build-plan.md) is the authoritative order.

Each step ends with a test, written down in the ops log, and that test joins the weekly test suite ([`slurm-design.md`](slurm-design.md) section 11).
