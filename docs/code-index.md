# Code index: everything that runs the cluster

Everything below is plain code in this repo: Python, Bash, Ansible and one Lua file. It runs the same way every time, from a person, cron or an agent. Nothing in it calls an AI or makes a judgement. Claude writes and changes the code through commits, like any developer, and every change is in git.

**Updated:** 2026-10-21. Add a line here with every new script, role or command.

## 1. `./cluster`: the one admin command (SOP-001)
Every run is logged in `/var/log/cluster-ops/`: who, when, which commit, the full output, the exit code.

| Command | What it does | SOP |
|---|---|---|
| `./cluster apply [--dry-run] [--limit M] [--tags T]` | Brings every machine in line with the repo, in four parts: preview, a question, the change, then a check that nothing is left to change ("settled") | 001 |
| `./cluster ping` | Checks that Ansible reaches every machine and can become root | 001 |
| `./cluster runs` | Recent runs from the log | 001 |
| `./cluster test [--code] [--live] [-k NAME]` | Code tests, and live tests on the machines | 191 |
| `./cluster upgrade` | OS updates on compute nodes, one at a time, with reboots | 201 |
| `./cluster customer add / set / list` | Customers in `config/customers.yml`: shows the change, commits it, applies it | 210 |
| `./cluster user add / set / suspend / resume / remove / list` | Users: picks the username and fixed IDs, commits, applies | 210 |
| `./cluster credits topup / grant / adjust / refund / balance / statement / hourly / check` | Money: payments, grants, corrections, refunds, balances, statements, the monthly cross-check | 211 |
| `./cluster backup run / verify / list` | Backups now, and restoring them into scratch databases to check them | 181, 301 |
| `./cluster health [--json]` | One screen of everything that should be true; exit code 1 if anything isn't | 171 |
| `./cluster build slurm` | Builds Slurm from SchedMD's checked source, version from `config/versions.yml` | 151 |

## 2. The code behind it: `cluster` and `clusterlib/`
| File | What it is |
|---|---|
| `cluster` | The command itself: argument parsing, logging, the apply flow |
| `clusterlib/config.py` | Reads and checks `customers.yml`, `uids.yml` and the prices; picks usernames and IDs; edits the files safely |
| `clusterlib/billing.py` | The money logic: prices, job costs, credit batches used soonest-expiring first, expiry, storage peaks, Slurm credit limits, the grace period. No database or Slurm in it, so it's fully testable |
| `clusterlib/ledger.py` | The ledger in MariaDB (`cluster_ledger`): every credit movement, append-only, one customer at a time |
| `clusterlib/billing_cli.py` | `cluster-billing` on anton: hourly charging, sync, the admin money commands, what customers see |
| `clusterlib/health.py` | `./cluster health` |

## 3. Configuration: `config/`, the only files edited by hand
| File | What's in it |
|---|---|
| `nodes.yml` | Machines, addresses, hardware, Slurm node sizes, kernel options, the GPUs' PCIe links |
| `customers.yml` | Customers and their users. Normally changed through `./cluster customer` and `./cluster user` |
| `uids.yml` | Fixed user and group IDs, given out by code, never reused |
| `rates.yml` | Default prices, each from a date (placeholders until D29) |
| `versions.yml` | Pinned Slurm version and checksum; the CUDA version the tests build with |

## 4. Ansible roles: `ansible/roles/`, run by `./cluster apply` in the order of `ansible/site.yml`
| Role | Machines | What it sets up | SOP |
|---|---|---|---|
| `hosts` | all | `/etc/hosts` from `nodes.yml` | 102 |
| `journal` | all | System logs kept on disk | 106 |
| `kernel_args` | all | Extra kernel options from `nodes.yml`; never reboots | 107 |
| `repos` | all | Package repositories (CRB, EPEL without its Slurm) | 110 |
| `accounts` | all | Customer groups and users, with fixed IDs | 141 |
| `customer_access` | all | Customer logins: root-owned SSH keys, no passwords, other users' processes hidden | 142 |
| `firewall` | anton | The cluster-network zone | 103 |
| `fail2ban` | anton | Blocks addresses that keep failing to log in | 142 |
| `time` | all | anton serves time; nodes follow it | 105 |
| `admin_proxy` | anton | The admins' web proxy, on the cluster network only | 103 |
| `storage` | anton | `/raiddrive` quotas, `/cluster`, NFS export | 130 |
| `customer_storage` | anton | Customer folders and storage limits | 141 |
| `nvidia_repo` | anton, GPU nodes | NVIDIA's repository and signing key | 111 |
| `nvidia_driver` | GPU nodes | The NVIDIA driver at one pinned version | 111 |
| `egress` | compute nodes | No internet or office network for customer accounts | 104 |
| `shared_storage` | compute nodes | `/cluster` mounted over NFS | 130 |
| `slurm_common` | all | munge, our Slurm packages, `slurm.conf`, `cgroup.conf` | 152 |
| `slurm_db` | anton | The accounting database (MariaDB) | 152 |
| `slurm_controller` | anton | `slurmctld`, `slurmdbd`, the job-size rules (`job_submit.lua`) | 152, 153 |
| `slurm_accounts` | anton | Slurm accounts, users and limits from `customers.yml` | 154 |
| `slurm_node` | compute nodes | `slurmd`, GPU detection, hidden job processes, logins only with a job, its SELinux module | 155 |
| `billing` | anton | The ledger, `cluster-billing`, the hourly run, the customer commands | 161, 162 |
| `backup` | anton | Nightly dumps, hourly binary-log copies | 181 |
| `test_schedule` | anton | The weekly test run | 191 |

## 5. What those roles install on the machines
| Where | What |
|---|---|
| anton, `/usr/local/sbin/` (root only) | `cluster-billing`, `cluster-billingdb-setup`, `cluster-slurmdb-setup`, `cluster-slurm-accounts`, `cluster-quota`, `cluster-backup` |
| anton, `/usr/local/bin/` (customers) | `credits`, `myusage`, `prices`, `mystorage`: each shows only the caller's own data |
| anton, timers | `cluster-billing-hourly` (hourly), `cluster-backup-binlogs` (hourly), `cluster-backup-nightly` (01:30), `cluster-tests-weekly` (Sunday 03:00) |
| compute nodes | `cluster-egress.service` (customer network rules at boot); the `cluster_pam_slurm_adopt` SELinux module |
| Slurm | `job_submit.lua`: the job-size rules, checked on every submission |

## 6. Scripts: `scripts/`
| Script | What it does |
|---|---|
| `bootstrap/01-anton-fixes.sh` | One-time fixes on anton before Ansible took over (2026-10-17/18) |
| `bootstrap/02-install-ansible.sh` | Installs Ansible on anton (SOP-101) |
| `build/slurm-rpms.sh` | Builds the Slurm RPMs and publishes them as a local repository (SOP-151) |
| `git-hooks/post-commit` | Pushes every commit to GitHub at once |

## 7. Tests: `tests/`
| Folder | What |
|---|---|
| `tests/code/` (113 tests) | The code without the cluster: the `./cluster` command in a throwaway copy of the repo (`sandbox.py`), config and usernames, billing logic, `job_submit.lua`, Slurm account plans, health, and the roles' rules (previews can see every change, no templated parameter names) |
| `tests/live/` (16 files) | Real checks on the machines: hosts, logs, kernel options, repos, proxy, customer network, time, storage, accounts and logins, the GPU driver and GPU work, Slurm's controller and job rules, Slurm on GPU nodes (real jobs, logins), billing, the ledger, backups |
| `tests/ledger/` | The ledger against a real scratch database |
