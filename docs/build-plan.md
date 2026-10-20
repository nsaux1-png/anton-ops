# Build plan: what gets done, step by step

This is the concrete version of plan section 18 (build order): what Claude actually does in each step, which SOP each step becomes, and what needs **you**. Each step follows plan section 17:
1. **Discovery run:** work it out on the real machine, logged in the ops log.
2. **Write it down:** an Ansible role or script, run by `./cluster`, plus an SOP page.
3. **Proof run:** undo it and run the SOP again exactly as written.
4. **Tests:** the step's checks become thorough automated tests in `./cluster test`, written in the same step and run on the cluster itself (anton and the nodes, not GitHub). Every later change re-runs them, so nothing quietly breaks.

Then commit and push. Status as of 2026-10-19.

## Phase 1: Foundations
**Tests written in this phase:** `./cluster` itself (code tests); `/etc/hosts` on every machine; the proxy works for admins and logs every request; customer accounts on compute nodes are blocked from the proxy, the internet and the BMC but reach the cluster network; time is in sync everywhere.

| # | What Claude does | SOP | You | Status |
|---|---|---|---|---|
| 1.1 | Install Ansible on anton; `./cluster` command with run logs and tests | 001, 101 | | ✅ done 2026-10-19 |
| 1.2 | `/etc/hosts` on every machine from `config/nodes.yml` | 102 | | ✅ done 2026-10-19 |
| 1.3 | **Admin web proxy on anton** (squid), on the cluster network only. Every request is logged. douglas1's `dnf` and admin shells use it. anton's firewall gets a separate zone for the cluster network, so cluster services never open on the upstream network. | 103 | | ✅ done 2026-10-19 |
| 1.4 | **Network limits for customer jobs** on compute nodes: customer accounts (UID 2000 and up) can reach only the cluster network. That rules out the internet, the office network, the BMC and the admin proxy. Root and admin accounts aren't limited. | 104 | | ✅ done 2026-10-19 |
| 1.5 | Time: anton serves time (chrony) to the cluster network; nodes sync from it | 105 | | ✅ done 2026-10-19 |
| 1.6 | **SSH lockdown, moved up by the review:** password login off, no root login, then check from outside whether anton's public IPv6 address is reachable | 106 | Confirm you log in with an SSH key, not a password; run the outside check from your phone's hotspot | |

## Phase 2: GPU node (douglas1)
**Tests written in this phase:** all 10 GPUs present with the pinned driver; each GPU's PCIe link; a CUDA test program runs on every GPU; persistence mode on; the driver module built for every installed kernel; the customer network limits still loaded after a reboot.

| # | What Claude does | SOP | You | Status |
|---|---|---|---|---|
| 2.1 | Read-only checks: Secure Boot, BIOS settings (Above 4G decoding, Resizable BAR), kernel headers | (ops log) | Change BIOS settings if needed (console or BMC) | ✅ done 2026-10-19 |
| 2.2 | NVIDIA driver, in this order:<br>1. Update douglas1 to the newest kernel and reboot.<br>2. Install `kernel-devel-matched`.<br>3. Enable CRB and EPEL (for DKMS), with EPEL's Slurm excluded.<br>4. Install NVIDIA's `nvidia-driver:<branch>-open` module stream, version-locked.<br>5. Turn on persistence mode.<br><br>Checks: `nvidia-smi` shows all 10 GPUs, each GPU's PCIe link, and whether GPU use, memory and power readings work on GeForce. Proof runs: uninstall and reinstall, and a DKMS rebuild after a kernel update. | 111 | | ⚠️ blocked: douglas1 didn't come back from the driver reboot (ops log 2026-10-19-step2-gpu-driver) |
| 2.3 | Full-load test: all GPUs at full power for 1 hour, watching temperatures, power and errors | 112 | Be there and watch the room and power | |

## Phase 3: Package mirror (before the second node or the first customer)
**Done after phase 7**: it's needed before the second node or the first customer, not before Slurm.

**Tests written in this phase:** every node installs only from the mirror; installed versions match the snapshot.

| # | What Claude does | SOP | You | Status |
|---|---|---|---|---|
| 3.1 | Mirror on anton (keeping the DNF module metadata NVIDIA's and AppStream's repos need): dated snapshots of Rocky BaseOS/AppStream, EPEL, NVIDIA's repo and our Slurm builds on `/raiddrive`, served over HTTP to the cluster network only. `./cluster mirror sync` and `mirror use <date>`. | 121 | | |
| 3.2 | Switch douglas1's `dnf` from the proxy to the mirror; check that versions are identical | 122 | | |

## Phase 4: Storage
**Tests written in this phase:** quotas on; writing past a customer's limit fails; changing a file's project ID or group doesn't escape the limit; `df` inside a customer's folder shows their limit; NFS mounted on every node; customers can't read each other's folders.

| # | What Claude does | SOP | You | Status |
|---|---|---|---|---|
| 4.0 | Customer folders live under `/cluster` (`/cluster/home`, `/cluster/projects`, `/cluster/software`), not `/home`, so admin home folders (with the repo and keys) stay local and untouched | 130 | | ✅ decided 2026-10-20 |
| 4.1 | `/raiddrive` layout (`home`, `projects`, `software`, `mirror`), with user, group and project quotas on. That needs an fstab change and a full unmount and mount, done while it's still empty. | 131 | | ✅ done on anton 2026-10-20 |
| 4.2 | NFS: export to the cluster network only; mount on douglas1 | 132 | | ◐ anton exporting; douglas1's mount waits for douglas1 |
| 4.3 | Per-customer group quota (150 GB default), per-user usage, the hourly storage collector, the 90% warning; test that a file can't escape the quota | 133 | | ◐ limits done on anton 2026-10-20; hourly collector and 90% warning come with billing (phase 7) |

## Phase 5: Users and access
**Tests written in this phase:** test customers and users exist on every machine with the right UIDs and groups; customers can't add SSH keys, use sudo or see other users' processes; suspended users can't log in or submit jobs; the `./cluster user` commands (code tests).

| # | What Claude does | SOP | You | Status |
|---|---|---|---|---|
| 5.1 | `config/customers.yml` and `uids.yml`; `./cluster user add/suspend/remove`, `apply`; test customers `c0001`/`c0002` with `zz` users | 141, 201 | | ✅ done on anton 2026-10-20 (douglas1 when it's back) |
| 5.2 | fail2ban, root-owned customer SSH keys, hidden `/proc` (`ProtectProc=invisible`), home folder permissions, `0700` admin files | 142 | | ◐ root-owned keys, no customer passwords, hidden processes done on anton 2026-10-20; fail2ban and the admin password question (1.6) open |

## Phase 6: Slurm
**Tests written in this phase:** CPU job, 1 GPU, several GPUs; oversized jobs and CPU-only jobs on a GPU node rejected, also through `scontrol update`; the memory limit kills; a job sees only its own GPUs; customers can't see other customers' jobs in `squeue`, `sacct` or `sreport`; no SSH into a node without a job; a job can't reach the internet; signals and the grace step; accounting records match what ran.

| # | What Claude does | SOP | You | Status |
|---|---|---|---|---|
| 6.1 | Build Slurm RPMs from SchedMD source with NVIDIA (NVML) and Lua support | 151 | | |
| 6.2 | munge, MariaDB, `slurmdbd`, `slurmctld` on anton | 152 | | |
| 6.3 | `slurmd` on douglas1: GPUs by model, cgroups, reserved system cores and memory, 5 cores + 20 GB per GPU (`job_submit.lua`), `pam_slurm_adopt` | 153 | | |
| 6.4 | Accounting: private data (in `slurm.conf` and `slurmdbd.conf`), GPU use per job, job scripts kept 60 days by Slurm's own purge | 154 | | |
| 6.5 | Tests: CPU job, 1 GPU, several GPUs, limits, memory kill, a job can't reach the internet, signals and grace | 155 | | |

## Phase 7: Billing and credits
**Tests written in this phase:** code tests for the ledger arithmetic, credit batches and expiry, price overrides and history, storage peak, hourly charging, and re-runs never double-charging. End to end on the test accounts: top up, run jobs, charges correct to the cent, run out mid-job → grace → stop, expiry, statement totals equal Slurm's totals.

| # | What Claude does | SOP | You | Status |
|---|---|---|---|---|
| 7.1 | `rates.yml` and per-customer prices; the ledger (whole-number amounts); credit batches with 12-month expiry; hourly charging keyed on `DBIndex`; Slurm limits sync (usage + what the balance buys); the 10-minute grace step | 161 | Set the prices (D29) and what 1 credit is worth (D40) | |
| 7.2 | Customer commands: `credits`, `myusage`, `prices`, `mystorage` | 162 | | |
| 7.3 | Admin commands: `credits topup/refund/adjust`, statements, `billing check`. Dry-run a month on the test accounts. | 211 | Review a test statement | |

## Phase 8: Monitoring and alerts
**Tests written in this phase:** each alert fires on a simulated fault.

| # | What Claude does | SOP | You | Status |
|---|---|---|---|---|
| 8.1 | Node, GPU, disk and service health; email alerts | 171 | Say where alerts go (D34) | |

## Phase 9: Backups
**Tests written in this phase:** a backup restores into a scratch database and matches the original.

| # | What Claude does | SOP | You | Status |
|---|---|---|---|---|
| 9.1 | Database binlogs or hourly dumps to `/raiddrive` and off-site (the money records are on one disk); config and ledger backup; a restore test | 181, 301 | Pick the off-site destination (D39) | |

## Phase 10: Scheduling the test suite
The tests themselves are written in each phase above. This phase only schedules and reports them.
| # | What Claude does | SOP | You | Status |
|---|---|---|---|---|
| 10.1 | The whole suite weekly (Sunday night) on a systemd timer; a quick run after every `./cluster apply` or `upgrade`; results by email | 191 | | |

## Phase 11: Launch
| # | What Claude does | SOP | You | Status |
|---|---|---|---|---|
| 11.1 | User guide (log in, submit jobs, checkpointing with signals, see costs) | | | |
| 11.2 | Terms (prices, credits expire after 12 months, scripts kept 60 days, no regulated data) | | Have them reviewed | |
| 11.3 | Separate login host for customers (design Q8), remove the temporary passwordless sudo, security review | | Decide Q8 | |
| 11.4 | First friendly customer | | Pick one | |

## Later
- WireGuard VPN for admin logins (design Q3).
- 10 Gb link anton ↔ douglas1 once the card arrives (Linear COP-42).
- RAM upgrade for douglas1 (Linear COP-43), then raise the per-GPU memory.
- Separate login node (plan D6) and a bigger storage server (D22) as the cluster grows.
