# SOP-152: Slurm controller, accounting database and shared configuration
**Status:** proved on anton 2026-10-20 ([ops log](../ops-log/2026-10-20-phase6-slurm.md)). Compute nodes get theirs with SOP-155 once douglas1 is back.

## Purpose
- **Every machine** (role `slurm_common`):
  - the `slurm` user (UID 450 everywhere)
  - munge, with one key made on anton and copied to the nodes. The key is base64 text, so copying can't damage it.
  - our Slurm packages (SOP-151)
  - the same `slurm.conf` and `cgroup.conf`
- **anton** (roles `slurm_db`, `slurm_controller`):
  - MariaDB on 127.0.0.1 only, crash-safe (`innodb_flush_log_at_trx_commit=1`, `sync_binlog=1`), with **binary logs** (14 days) so the accounting and money records can be restored to the minute
  - the database password, made on anton in `/etc/cluster/secrets/` (root only) and **never in the repo**. It's copied into `slurmdbd.conf` (`0600`, slurm only).
  - `slurmdbd` and `slurmctld`
  - ports 6817 and 60001-63000 open to the cluster network only
- **What `slurm.conf` sets** (why: `slurm-design.md` sections 6-9):
  - cgroups: cores, memory and GPUs held to what was given; no swap
  - `PrologFlags=Contain`, `DisableRootJobs=YES`, `EnforcePartLimits=ALL`, `KillWait=60`
  - accounting enforced with `safe`
  - GPU use recorded per job
  - job scripts stored; slurmdbd deletes them after 60 days (`PurgeJobScriptAfter=60days`)
  - `PrivateData` in both `slurm.conf` and `slurmdbd.conf`
  - `PriorityFlags=MAX_TRES` and integer billing weights (`CPU=1,Mem=0.5G,GRES/gpu=10`)
  - douglas1 with one core reserved (`CoreSpecCount=1`), and `MemSpecLimit` sized so exactly 11 × 20 GB is left for jobs
  - partition `gpu`: 10 CPUs and 20 GB per GPU by default; 7 days maximum, 1 hour default

## When
Automatically on every `./cluster apply`.

## Steps
1. `./cluster apply --dry-run`
2. `./cluster apply`

## Checks
- **Automated:** `./cluster test --live -k test_slurm`. It covers daemons, munge, the version, the database (local only, binary logs, no anonymous users), secret file permissions, firewall, accounts and limits, privacy, and the job rules.
- **By hand:** `scontrol ping`, `sinfo`, `sacctmgr show assoc`.

## Undo (on anton)
```
sudo systemctl disable --now slurmctld slurmdbd mariadb munge
sudo dnf remove 'slurm*' mariadb-server munge
sudo rm -rf /var/lib/mysql /etc/my.cnf.d/slurm.cnf /etc/slurm /var/spool/slurmctld /var/log/slurm \
  /etc/munge/munge.key /etc/cluster/secrets /usr/local/sbin/cluster-slurm* /etc/yum.repos.d/cluster-slurm.repo
```
⚠️ Deleting `/var/lib/mysql` deletes all accounting, which is the billing record. **Only for a cluster with no customers yet.** Then remove the firewall ports and the roles from `ansible/site.yml`.

## Notes
- slurmdbd logs `Unknown system variable 'innodb_snapshot_isolation'` at start. Slurm's own next line says it's harmless with MariaDB 10.5.
- `RealMemory` for douglas1 (257000 MB in `config/nodes.yml`) is a placeholder until `slurmd -C` can run on it.

## History
- 2026-10-20: first version on anton; 22 of 23 Slurm tests passed (one needs a GPU node up).
  - Proof run: Slurm, munge, MariaDB, the database files, secrets, tools and firewall ports were all removed, then rebuilt with one `./cluster apply --limit anton` ("Done and settled"). Same test result.
