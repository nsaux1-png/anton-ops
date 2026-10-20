# SOP-301: Checking backups restore, and restoring for real
**Status:** the check is proved 2026-10-20 ([ops log](../ops-log/2026-10-20-phase9-backups.md)). A real restore has never been needed.

## The check (do it monthly, and after any change to backups)
`./cluster backup verify` restores the newest backup into scratch databases, checks it, then drops them. It checks:
- every file matches its checksum in the manifest
- the restored ledger's last entry, count and sum match the manifest
- **the live ledger is identical up to that entry** (count, sum and a checksum of every row). The ledger only ever appends, so this must match exactly.
- Slurm's tables all restore, the job-script tables are empty, and there are no more job records than the live database has
- `files.tar.gz` holds the secrets, the munge key and `slurm.conf`

It ends with "restores cleanly", or lists each problem. `./cluster test --live -k test_backup` runs it as part of the weekly tests.

## Restoring for real (anton's NVMe died, or the database is damaged)
This is a checklist, not a script: it needs judgement.
1. Stop billing and Slurm: `sudo systemctl stop cluster-billing-hourly.timer slurmctld slurmdbd`.
2. Rebuild anton from the repo (SOP-101, then `./cluster apply --limit anton`). This makes empty databases.
3. Restore the newest backup:
   ```
   D=/raiddrive/backups/daily/<date>
   zcat $D/cluster_ledger.sql.gz | sudo mysql cluster_ledger
   zcat $D/slurm_acct_db.schema.sql.gz | sudo mysql slurm_acct_db
   zcat $D/slurm_acct_db.data.sql.gz   | sudo mysql slurm_acct_db
   sudo tar -xzf $D/files.tar.gz -C /     # secrets, munge key, Slurm state
   ```
4. Replay what happened since the backup from the binary logs: find the log the dump started (`zcat $D/cluster_ledger.sql.gz | grep -m1 'CHANGE MASTER'`), then `sudo mysqlbinlog <that log and the later ones from /raiddrive/backups/binlog/> | sudo mysql`.
5. Start `slurmdbd`, `slurmctld`, then the billing timer. Run `./cluster credits hourly`, then `./cluster test`.
6. Write an ops-log entry: what failed, which backup was used, and what was replayed.

## History
- 2026-10-20: the check written and passing.
