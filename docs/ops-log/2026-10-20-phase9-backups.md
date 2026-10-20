# 2026-10-20: Build phase 9 (backups) on anton

## Why
Build plan phase 9. The money records (ledger) and Slurm accounting are on anton's single NVMe, with no UPS (review R2). Backups and binary-log copies protect them now. An off-site copy waits for the user's choice of destination (D39).

## Done
By Claude Code (a session on anton as papaya), while the user was away.
1. **Read-only:** Slurm's tables (the job-script tables are `main_job_script_table` and `main_job_env_table`), and the binary logs in `/var/lib/mysql`.
2. **Role `backup` and the `cluster-backup` tool:**
   - nightly dumps, a tarball of the cluster files, and a manifest
   - hourly binary-log copies
   - `verify`: restore into scratch databases and check that the ledger matches the live ledger exactly up to its last entry
   - `./cluster backup run|verify|list`
   - `tests/live/test_backup.py`
3. **Two bugs found by the first runs:**
   - Restores handed `mysql` a gzip file object, which passes the compressed bytes. Restores are now streamed through `zcat`.
   - Dumps wrote straight past the gzip wrapper. Dumps are now piped through `gzip`.

   After both fixes: "backup 2026-10-20: restores cleanly; the ledger matches the live ledger exactly up to entry 5 (5 entries); Slurm's 6 job records restored; job scripts left out as they should be".
4. **Proof run:** removed the timers, tool and `/raiddrive/backups`, then `./cluster apply --yes --limit anton` reported "Done and settled". Log: `20261020-025519-apply.log`. The backup tests passed again (4/4).

## Follow-ups
- Off-site copy (D39): the user picks a destination. An encrypted copy of `/raiddrive/backups` then goes there nightly.
- The `/raiddrive` data itself (customers' files) isn't backed up; only the mirror protects it. Whether customers' files get backed up is a product decision (plan section 16).
