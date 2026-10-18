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
- **D1. Who are the customers?** (a) external paying companies, (b) internal teams with chargeback, (c) both. This affects isolation, contracts and security. *Recommended: plan for (c) and design for external customers.*
- **D2. Expected size in a year:** number of users, number of nodes. *Needed to size the head node, storage and network. Rough guesses are fine.*
- **D3. Service level:** is this best-effort ("we fix it next business day"), or do customers expect uptime guarantees? *Recommended: best-effort at launch, stated in the terms.*

---

## 2. Machines and roles

| Role | Machine | Runs |
|---|---|---|
| Head node | anton | Slurm controller, accounting DB, login, NFS server, gateway, time server, Ansible, monitoring |
| GPU compute | douglas1 | slurmd, NVIDIA driver, 10× RTX 5070 Ti |
| Future GPU compute | TBD | same as douglas1 |
| Future CPU compute | dual-socket nodes, TBD | slurmd |

**Concerns with current hardware**
- **anton's network is 1 Gb.** Every compute node reads `/home` and datasets from anton over that link. With 10 GPUs on douglas1, this will be the main bottleneck for data-heavy jobs.
- **douglas1 has only a 256 GB disk** for 10 GPUs, so there's no room for local scratch or datasets.
- **anton is both head and login node.** If customers run heavy work on the login node (compiling, unpacking big files), it slows the scheduler and the NFS server. That's fine at small scale, but it's the first thing to split off as we grow.
- **Power and cooling:** 10 GPUs is roughly 3 kW under load. Is there a UPS, and is the room cooled for it?

**Decisions**
- **D4. Network upgrade:** add a 10 Gb (or faster) link between anton and compute nodes? douglas1 already has a second, unused port (`enp66s0f0np0`), likely fast; anton would need a NIC and there'd need to be a switch. *Recommended: yes, before paying customers run data-heavy GPU work.*
- **D5. Local scratch on GPU nodes:** add NVMe drives to douglas1 for fast per-job scratch? *Recommended: yes, 2–4 TB.*
- **D6. Separate login node later:** *Recommended: start with anton as login node, split when we pass ~10 active users or see login-node load problems.*
- **D7. UPS:** is there one? If so, can it signal shutdown?

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
- **Outbound internet** for nodes through anton (NAT), already agreed.
- **Firewall on anton:** upstream side allows only SSH (and later, monitoring for admins); cluster side trusted.
- **Customer access:** SSH to anton from the internet, keys only. Possibly a VPN instead (see D10).
- **BMC/IPMI** (remote power and console for each server): put them on their own management network, reachable only from anton or admins.

**Decisions**
- **D8. Node naming scheme.** *Recommended: keep personal names if that's your convention, but keep the type in the inventory (Slurm doesn't care).* Or switch to `gpu01`/`cpu01`.
- **D9. What is 172.16.99.0/24** on douglas1's USB network interface? Probably the BMC host interface. *Needs checking.*
- **D10. How customers reach the cluster:** (a) SSH directly from the internet to anton, (b) VPN first, then SSH. *Recommended: (a) with keys only and fail2ban to start, (b) if a customer requires it.*
- **D11. Is the 192.168.5.0/22 upstream network shared with other office machines?** Affects firewall rules.

---

## 4. Operating system and installing new nodes

**Proposal**
- Rocky Linux 9 everywhere, same minor version across the cluster.
- **New node procedure:** install Rocky by hand from USB (choose minimal install, set hostname and cluster IP), add one SSH key, then run `./cluster add-node`. Ansible does everything else. A kickstart file in the repo makes the install answers identical every time.
- **Updates:** monthly maintenance window. Packages are updated on one node first, then the rest. Kernel updates need a reboot and a matching NVIDIA driver, so they're always done in the window, never automatically.
- **SELinux stays enforcing.**

**Decisions**
- **D12. Network installs (PXE)** instead of USB? *Recommended: not now. Worth it at ~10+ nodes.*
- **D13. Maintenance window:** day and time each month, and how much notice customers get. *Recommended: one fixed slot per month, 1 week notice.*

---

## 5. Configuration management (how everything stays repeatable)

**Proposal**
- **Ansible** (agreed), run from anton. Repo layout:
  ```
  cluster                     the one command operators run
  inventory/nodes.yml         every machine: name, IPs, type, GPUs, disks
  inventory/users.yml         every user: name, UID, account, SSH keys, status
  inventory/accounts.yml      customers/projects and their billing settings
  inventory/group_vars/       cluster-wide settings (Slurm, NFS, rates…)
  playbooks/                  one per job: site.yml (everything), add-node, add-user…
  roles/                      one per component: common, nfs, slurm-controller, slurm-node, nvidia, …
  scripts/                    helpers (billing report, bootstrap)
  docs/                       plan, decisions, procedures, ops log
  ```
- **Every run is logged** to `/var/log/cluster-ops/` with: timestamp, operator, command, git commit, whether the repo had uncommitted changes, and full output. The command refuses to run with uncommitted changes, unless forced, so every change to the cluster matches a commit.
- **Secrets** (munge key, DB passwords) are encrypted in the repo with Ansible Vault. The vault password lives only on anton, readable by root.
- **Dry-run first:** every command supports `--check` to show what would change.

**Decisions**
- **D14. Who are the operators?** Just you, or more people? Do they each get their own admin account? *Recommended: one named admin account per person, never shared; papaya is yours.*
- **D15. GitLab as the official copy:** pushes after every change? Merge requests for review? *Recommended: push after every change; merge requests once there's more than one operator.*

---

## 6. Users, accounts and access

**Proposal**
- **Source of truth:** `inventory/users.yml`. Each user has a name, UID (fixed forever, never reused), primary account, SSH public keys, email, and status (active/suspended/removed).
- **UID ranges:** admins 1000–1999, customers 10000+. Group IDs match.
- **Logins:** SSH keys only, no passwords. Users can't use sudo.
- **Slurm accounts:** one per customer, with sub-accounts per project if a customer wants separate bills. Users can belong to several accounts.
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
- **D19. Quotas:** default home quota and default project quota. *Recommended: 50 GB home; project quota set per customer.*
- **D20. Charge for storage?** *Recommended: yes, per GB-month above a free allowance, at least for projects.*
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
- **GPU requests:** `--gpus=N` or `--gres=gpu:N`. CPUs and memory per GPU have defaults, so a job asking for 1 GPU gets ~1/10 of douglas1's CPU and RAM unless it asks for more.
- **Node health check** before and between jobs; a sick node is drained automatically.
- **Interactive use:** `srun --pty` / `salloc` for interactive sessions, billed the same as batch jobs.

**Decisions**
- **D23. Maximum job time limit.** *Recommended: 7 days max, 1 hour default if unspecified.*
- **D24. Priority model:** pure fair-share, or customers who pay more get priority (QOS tiers)? *Recommended: fair-share now, design the QOS levels so a "priority" tier can be sold later.*
- **D25. Preemption:** can high-priority jobs interrupt others? *Recommended: no, at launch.*
- **D26. Jupyter/web access** (Open OnDemand)? *Recommended: later; SSH first.*

---

## 10. GPU stack

**Proposal**
- **NVIDIA driver** (open kernel modules, required for RTX 50-series), pinned to a tested version in the repo. Kernel and driver are updated together in the maintenance window.
- **CUDA:** users bring their own through conda/pip/containers; the driver supports them. We also provide a few CUDA versions as modules for people compiling code.
- **Containers:** Apptainer (the HPC-standard container runtime, runs without root), so customers can bring Docker images.
- **GPU monitoring:** NVIDIA DCGM for per-GPU health and usage.
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

## 12. Accounting and billing

**Proposal**
- **What's measured:** for each job, Slurm records the allocated CPUs, memory, GPUs and elapsed time, per user and account.
- **What's charged:** **allocated** resources × time, not "used" (industry norm: a GPU you reserved and left idle still costs us).
- **Rates** live in the repo (`inventory/accounts.yml` / billing config): price per GPU-hour, per CPU-hour, possibly per GB-hour of memory, possibly different per node type.
- **Enforcement:** jobs from users who aren't in an active account are rejected at submission. Accounts can have spending caps (Slurm limits on billing units) so nobody is surprised by their bill.
- **Reporting:** `./cluster billing-report 2026-10` produces a per-account, per-user CSV for the month, with totals. It's built from the accounting database, so it can be re-run and gives the same answer.
- **Customer self-service:** a command on the login node showing a user's and account's usage and cost so far this month.

**Decisions**
- **D29. Rates:** price per GPU-hour, CPU-hour, memory? Same price for all GPU types? *Your call; Claude can suggest market comparisons.*
- **D30. Pricing model:** pay as you go (bill monthly in arrears), prepaid credits, or reserved capacity (fixed monthly for N GPUs)? *Recommended: pay-as-you-go plus optional spending caps at launch; prepaid credits are easy to add because Slurm can enforce them as limits.*
- **D31. Failed jobs:** charged? *Recommended: yes for job failures (the resources were held), no for node failures (our fault); the report marks which is which.*
- **D32. Minimum billing increment:** per second, minute, or hour? *Recommended: per minute.*
- **D33. Invoicing:** which tool sends invoices, and who reviews the report first? *Is there an accounting system (e.g. QuickBooks, Stripe) the CSV should feed?*

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
- **D36. Sensitive data:** will customers bring regulated data (health, personal data)? If yes, this plan needs a stricter version.
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
- **Must back up:** Slurm accounting DB (nightly dump), `/etc` of anton, the vault password (stored offline by you), the repo (GitLab).
- **Customer data:** depends on D21.
- **Off-site target:** TBD (cloud storage bucket, another site).

**Decisions**
- **D39. Off-site backup destination.** *Recommended: a cloud storage bucket, encrypted.*

---

## 17. Standard procedures (each becomes a `./cluster` command plus a page in `docs/procedures/`)

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

1. **Foundations:** Ansible + repo layout + `./cluster` with logging; hosts, time, firewall, gateway; douglas1 gets internet.
2. **Storage:** `/raiddrive` layout, NFS, quotas.
3. **Users:** users.yml, admin accounts, SSH hardening.
4. **GPU:** NVIDIA driver on douglas1.
5. **Slurm:** build, accounting DB, controller, douglas1 as first node, partitions, enforcement.
6. **Billing:** accounts, rates, limits, report; dry-run a month on test jobs.
7. **Monitoring and alerts.**
8. **Backups**, then a restore test.
9. **User guide and terms**, onboard a friendly first customer.
10. **Remove temporary sudo**; security review.

Each step ends with a test, written down in the ops log.
