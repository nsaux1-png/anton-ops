# 2026-10-20: Build phase 6 (Slurm) on anton

## Why
Build plan phase 6. douglas1 is down (ops log 2026-10-19-step2-gpu-driver), so the controller side is done on anton. The node side (`slurmd`, GPUs, `pam_slurm_adopt`) waits for douglas1.

## Done
By Claude Code (a session on anton as papaya), while the user was away.
1. **Build (SOP-151):** `./cluster build slurm` built Slurm 26.05.5, published 13 Oct 2026, with its SHA-256 checked against SchedMD's GitHub release (`4680cafc…4f68`).
   - Run 1 failed: 26.05 needs `libcurl-devel`; added it.
   - Run 2 built correctly, but the plugin check said `gpu_nvml.so` was missing. It wasn't: `grep -q` under `pipefail` made `rpm` fail. The check now lists files into a file first.
   - Run 3: all four plugins present (GPU/NVML, Lua, PMIx, cgroup v2), published to `/raiddrive/repos/slurm/26.05.5/`. Log `20261020-015150-build.log`.
   - NVIDIA's repo was added to anton (role `nvidia_repo`) for the NVML headers.
2. **Code (with code tests):**
   - `job_submit.lua` (13 tests)
   - `cluster-slurm-accounts` (8 tests)
   - roles `slurm_common`, `slurm_db`, `slurm_controller`, `slurm_accounts`
   - firewall ports
   - douglas1's hardware in `config/nodes.yml` (`RealMemory` is a placeholder until `slurmd -C`)
3. **`./cluster apply --yes --limit anton`:** "Done and settled" on the first try. Log: `20261020-015713-apply.log`.
4. **`./cluster test --live -k test_slurm`:** 22 passed. One test, the per-user GPU limit, can't be seen while every GPU node is down: Slurm gives "node down" as the reason first. It now skips with that reason until a node is up.
5. **Proof run:**
   - Removed the Slurm and munge packages, MariaDB, `/var/lib/mysql` (test data only), the configs, state, logs, munge key, secrets, tools, repo file, firewall ports and the slurm user.
   - `./cluster apply --yes --limit anton`: "Done and settled". Log: `20261020-020134-apply.log`.
   - Tests: 22 passed, 1 skipped.

## Findings
- **The job rules' field names work with Slurm 26.05.5's Lua interface.** Every rejection test passed against the real controller.
- slurmdbd logs `Unknown system variable 'innodb_snapshot_isolation'`. Slurm says it's harmless with MariaDB 10.5.
- `PurgeJobScriptAfter=60days` is accepted by slurmdbd 26.05.5 (the review's suggestion).

## Follow-ups
- **douglas1 (when it's back):** fix the driver boot problem, then run `slurmd -C` and set `RealMemory` and the GPU type. After that: the `slurm_node` role (slurmd, `gres.conf` with NVML, `pam_slurm_adopt` with admins exempt, hidden processes for jobs, node firewall), the GPU job tests, and the skipped limit test.
- Per-job `/tmp` and scratch: decision D5 is still open.
