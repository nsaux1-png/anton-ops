# Decision log

Newest at the bottom. Each entry gives the date, the decision, and the reason.

## 2026-10-17: Machine roles
anton is the head node; douglas1 is the first compute node. Future GPU and dual-socket CPU nodes join as compute nodes.

## 2026-10-17: Rename the head node to anton
The head node was misnamed `douglas1`, while the machine at 172.16.50.11 is the real douglas1. It was renamed with `hostnamectl set-hostname anton`. See `ops-log/2026-10-17-rename-anton.md`.

## 2026-10-18: Ansible, wrapped in a `./cluster` command
**Why:** Ansible steps check before changing anything, so re-running is safe across many machines, which is hard to get right in plain bash. The wrapper gives operators short, memorable commands and does the logging.

## 2026-10-18: Compute nodes get outbound internet through anton (NAT)
**Why:** this is the norm for research and commercial clusters: nodes sit on a private network nobody outside can reach, and outbound traffic goes through the head node's firewall. Customers expect pip, conda and dataset downloads to work. Full isolation with local mirrors is for regulated data and can be added later for one partition if a customer needs it.

## 2026-10-18: Keep anton's existing RAID1 mirror as it is
The 2×4 TB mirror (`md0`, XFS) stays as it is, internal label included. Its contents get checked read-only before it is mounted for `/home` and shared software.

## 2026-10-18: Temporary passwordless sudo during the build
**Why:** Claude's shell can't answer a sudo password prompt. A drop-in file `/etc/sudoers.d/90-papaya-temp` on each machine allows it during the build. **It must be removed when the build is done.** This may be revisited.

## 2026-10-18: Separate SSH keys per purpose
anton's `~/.ssh/id_ed25519` is only for reaching cluster nodes. GitLab gets its own key, so a leak of one doesn't expose the other.

## 2026-10-18: Everything is recorded in this repo, hosted on our GitLab
Discussions, decisions, procedures and scripts all live here.

## 2026-10-18: 172.16.50.11 is named `douglas1`
The `douglas1_gpu` name in anton's `/etc/hosts` was replaced with `douglas1` (backup kept as `/etc/hosts.bak-*`). Ansible will manage `/etc/hosts` from now on.

## 2026-10-18: Repo hosted at gitlab.com/nicolas478/anton-ops, pushed on every commit
Private project under @nicolas478; can be moved to a group later without losing history. A post-commit hook (`scripts/git-hooks/post-commit`) pushes each commit right away; a failed push is reported and retried on the next commit. Each new clone must enable it with `git config core.hooksPath scripts/git-hooks`. anton pushes with its own key, `~/.ssh/id_ed25519_gitlab`.

## 2026-10-19: Repo moved to GitHub, github.com/nsaux1-png/anton-ops
**Why:** the user prefers GitHub. It's a private repo under @nsaux1-png, with full history, and the post-commit hook pushes there now. anton pushes with a new key of its own, `~/.ssh/id_ed25519_github`, added to that one repo as a **deploy key** with write access. If the key leaks, only this repo is exposed, not the whole GitHub account. The GitLab project is no longer updated.

## 2026-10-19: Scope (plan D1, D2, D3, D36)
- **D1 Customers: external only.** Anyone internal uses the cluster through the same system as a customer, with the same accounts, billing and isolation.
- **D2 Size in a year: medium**, 20–100 users and 4–10 compute nodes. Within the year this means a 10 Gb switch, a separate login node (D6) and a larger storage server (D22). PXE installs (D12) become worth it toward the top of that range.
- **D3 Service level: best effort**, stated in the terms. We fix problems promptly, typically the next business day, with no uptime guarantee.
- **D36 Sensitive data: none at launch.** The terms say no regulated data (health, personal data). A stricter, isolated partition can be added later for a customer who needs it.

**Why:** the user's answers, 2026-10-19. Designing for external customers only keeps one set of rules for everyone.

## 2026-10-19: Power (plan D7, D47)
- **D7 UPS: none.** A power cut stops everything at once. To limit the damage: the accounting database uses crash-safe settings and is dumped nightly (D21), and jobs lost in an outage are refunded as node failures (D31).
- **D47 Power for douglas1: adequate.** The user confirmed the circuits are sized for douglas1's full load (about 3.3–3.6 kW), so GPUs run at full power with no software cap. A full-load test after the driver install still checks temperatures and stability.

## 2026-10-19: Network upgrade (plan D4)
**D4: buy a 10 Gb card for anton** (10GBASE-T copper, e.g. Intel X550-T2) and cable it straight to douglas1's free 10 Gb port. A 10 Gb switch comes with the second compute node. Tracked in Linear as COP-42 (Purchasing Tracking List).

**Why:** douglas1 already has 10 Gb ports; anton is 1 Gb only. It's the cheapest fix, and two machines don't need a switch. Shared storage is then limited by anton's hard drives (~200–400 MB/s) rather than the network.

## 2026-10-19: Usernames and what customers can see (design Q1, Q2)
- **Q1 Usernames: two letters + two digits** (e.g. `kx47`), chosen at random, with letters unrelated to the person's name. A username is never reused. Customer groups and Slurm accounts get neutral codes too. Real names and company names are kept only in the admin config, never in `/etc/passwd`, which every user can read.
- **Q2 Customers can see the cluster's nodes and GPUs** (`sinfo`), including which are busy. Jobs, usage and files stay private.

**Why:** the user's answers, 2026-10-19. Every user can list usernames, so usernames mustn't reveal who the customers are.

## 2026-10-19: Shared upstream network, job scripts, zero balance, tests (plan D11; design Q5, Q6)
- **D11: anton's upstream network is shared** with other machines on the same switch, so nothing on it is trusted. Cluster services listen only on the cluster network, and admin logins need more than "being on the LAN" (design Q3).
- **Q5: job scripts are kept 60 days**, then deleted. Environment variables aren't kept. The terms say so.
- **Q6: at zero balance** jobs stop. Files stay and storage keeps charging, so the balance can go negative for storage only. After 30 days negative, with email warnings, the files are deleted.
- **Tests are required:** test accounts and a test suite (`./cluster test`), with live tests weekly. Every SOP ends with checks that join the suite.
- **NVIDIA driver on douglas1 moved up** to step 2 of the build order.

**Why:** the user's answers, 2026-10-19. Job scripts help investigate abuse; 60 days is long enough for that without holding customer code forever.

## 2026-10-19: GPU job size, credit expiry, no free trials, how SOPs are made (design Q4, Q7; plan D42, D43)
- **Q4: 5 cores + 20 GB RAM per GPU**, sized for an eventual 11 GPUs on douglas1, so the size never shrinks. With 11 GPUs the system keeps 1 core and 31 GB.
- **Q7 / D42: credits expire 12 months after purchase.** The batch that expires soonest is used first.
- **D43: no free trials.** Compute is a commodity; customers buy credits from the start.
- **SOPs:** discovery run, then script plus SOP page, then a proof run from a clean state with no improvising. Running an SOP needs no AI (plan section 17).

**Why:** the user's answers, 2026-10-19.

## 2026-10-19: Admin tasks are commands, not AI
Every routine admin task (credits, users, software, maintenance, reports) is a `./cluster` command written as plain code, with tests. People, cron jobs and AI agents call these commands. The commands themselves contain no AI. See `slurm-design.md` section 12.

**Why:** the user, 2026-10-19: the core functions must be robust, real code that can be called from cron or an agent.
