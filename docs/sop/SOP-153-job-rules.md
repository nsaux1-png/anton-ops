# SOP-153: Job-size rules (`job_submit.lua`)
**Status:** proved on the real controller 2026-10-20 ([ops log](../ops-log/2026-10-20-phase6-slurm.md))

## Purpose
Slurm runs `/etc/slurm/job_submit.lua` (template `ansible/roles/slurm_controller/templates/job_submit.lua.j2`) for every submitted or changed job. On GPU partitions:
- **at least one GPU**, or the job is rejected (a CPU-only job would strand the GPUs)
- **at most 10 CPUs (5 cores) and 20 GB per GPU.** This counts every way of asking: `-c`, `-n`, `--cpus-per-gpu`, `--mem`, `--mem-per-cpu` and `--mem-per-gpu`.
- **no `--mem=0` and no `--exclusive`**
- no GPUs per socket (customers are asked to use per job, per node or per task instead)

On every partition, **customers can't change a waiting job's size or partition** (`scontrol update`); they cancel and resubmit. Root and the slurm user can.

Every rejection tells the customer the numbers, e.g. "2 GPU(s) come with at most 20 CPUs (10 cores); this job asks for 30." The settings come from `ansible/roles/slurm_common/defaults/main.yml` (`slurm_cpus_per_gpu`, `slurm_mem_per_gpu_mb`).

The script does no file or network access: Slurm runs it while holding its locks.

## When
- Installed by every `./cluster apply` (role `slurm_controller`). slurmctld restarts when it changes.
- To change a rule, edit the template and its tests, then apply.

## Checks
- **Code tests:** `./cluster test --code -k job_submit`, 13 tests. They run the real template in a Lua interpreter with a stand-in for Slurm.
- **Live tests:** `./cluster test --live -k JobRules`. These are real `sbatch`/`scontrol` calls as the test users:
  - accepted: a normal job
  - rejected: CPU-only, too many CPUs, too much memory (`--mem` and `--mem-per-gpu`), `--mem=0`, `--exclusive`, a suspended user's job, root's job
  - a customer can't resize a waiting job, but can change its time limit

## History
- 2026-10-20: first version. The field names worked with Slurm 26.05.5 on the first try. The per-user GPU limit test needs a GPU node up.
