# SOP-181: Backups
**Status:** proved 2026-10-20 ([ops log](../ops-log/2026-10-20-phase9-backups.md)). Off-site copy still to come (plan D39).

## Purpose
- **Nightly at 01:30** (`cluster-backup-nightly.timer`, i.e. `cluster-backup run`), into `/raiddrive/backups/daily/<date>/` (root only, `0700`):
  - the ledger (`cluster_ledger`): a consistent dump. It also starts a new binary log, so this dump plus the logs after it are the complete history.
  - Slurm accounting (`slurm_acct_db`): structure and data. **Job scripts and environments are left out** (only their tables' structure is kept), so no backup keeps a script past its 60 days (design Q5).
  - `files.tar.gz`: `/etc/cluster` (secrets, applied config, test keys), the munge key, `/etc/slurm`, Slurm's controller state, and the database settings
  - `manifest.json`: checksums of every file, and the ledger's fingerprint (last entry, count, sum)

  Kept 30 days.
- **Hourly at :15** (`cluster-backup-binlogs.timer`): the database's binary logs are copied to `/raiddrive/backups/binlog/`, kept 14 days. A failed NVMe then loses at most the last hour.
- The backups are on `/raiddrive`, the HDD mirror, which is a different disk from the databases (anton's NVMe). **That's not off-site:** a fire or theft takes both. The off-site copy waits for plan D39.

Role: `ansible/roles/backup`. Tool: `/usr/local/sbin/cluster-backup`.

## Commands
- `./cluster backup run`: a backup now.
- `./cluster backup verify [YYYY-MM-DD]`: the restore check (SOP-301).
- `./cluster backup list`

## Checks
- **Automated:** `./cluster test --live -k test_backup`. It checks the timers, makes a fresh backup and restores it cleanly, checks the backups are root-only, and that the binary logs get copied.

## History
- 2026-10-20: first version.
  - Two bugs fixed before it worked: Python can't hand a gzip file object to a program as its input or output, so dumps and restores are now piped through `gzip`/`zcat`.
  - Proof run: timers, tool and backups removed, then rebuilt with one apply. The tests passed again.
