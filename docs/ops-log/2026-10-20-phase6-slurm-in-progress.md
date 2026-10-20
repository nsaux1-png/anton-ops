# 2026-10-20: Build phase 6 (Slurm): in progress, stopped at the usage limit

## Done
- `./cluster build slurm` and `scripts/build/slurm-rpms.sh`, using version and checksum from `config/versions.yml`: Slurm 26.05.5, SHA-256 checked against SchedMD's GitHub release.
  - The first build failed: 26.05 needs `libcurl-devel`, which is now added.
  - The second build was started in the background; its result is in the newest `/var/log/cluster-ops/*-build.log`.
- The `nvidia_repo` role is applied to anton, which needs the NVML headers to build Slurm.
- `job_submit.lua` (the GPU job-size rules) is written, with 13 code tests that pass.
- `cluster-slurm-accounts` (customers.yml → Slurm accounts and limits) is written, with 8 code tests that pass.

## Written but NOT applied or tested yet
These are in `ansible/site.yml`:
- `slurm_common`: munge, packages, `slurm.conf`, `cgroup.conf`
- `slurm_db`: MariaDB with binary logs
- `slurm_controller`
- `slurm_accounts`
- firewall ports 6817 and 60001-63000

**The next `./cluster apply` runs them.** Before that:
1. Check the build log; RPMs must be in `/raiddrive/repos/slurm/26.05.5/`.
2. Run `./cluster apply --dry-run --limit anton` and fix whatever the preview finds.
3. Note: `PurgeJobScriptAfter` in `slurmdbd.conf` is unconfirmed; if slurmdbd rejects it, look up the right setting.
4. Live tests for Slurm still need writing (`tests/live/test_slurm.py`), followed by the SOPs (151-154) and a proof run.

## Still blocked
douglas1 is down since the NVIDIA driver reboot (ops log 2026-10-19-step2-gpu-driver). It needs someone at its screen or BMC.
