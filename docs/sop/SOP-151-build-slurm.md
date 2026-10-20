# SOP-151: Build Slurm
**Status:** proved 2026-10-20 ([ops log](../ops-log/2026-10-20-phase6-slurm.md))

## Purpose
We run Slurm built from SchedMD's own source, not EPEL's old package. The build includes:
- NVIDIA GPU support (NVML), so GPUs are detected and per-job GPU use is recorded
- Lua, for `job_submit.lua` (SOP-153)
- PMIx (for MPI), hwloc, NUMA and cgroup v2

`./cluster build slurm` runs `scripts/build/slurm-rpms.sh` with the version and checksum in `config/versions.yml`. It installs the build dependencies, downloads the source, **checks it against the SHA-256 SchedMD published**, builds the RPMs, checks the four key plugins are in them, and publishes them as a package repository in `/raiddrive/repos/slurm/<version>/`. The full build output is kept next to the RPMs (`build.log`).

## When
- once, when the cluster is set up
- again for each Slurm upgrade

## Steps (an upgrade)
1. Get the new version and its SHA-256 from SchedMD's GitHub release (https://github.com/SchedMD/slurm/releases; the digest is shown next to the `.tar.bz2`).
2. Change `slurm.version` and `slurm.sha256` in `config/versions.yml`, and commit.
3. `./cluster build slurm` takes about 4 minutes. It ends with `OK` for `gpu_nvml.so`, `job_submit_lua.so`, `mpi_pmix.so` and `cgroup_v2.so`.
4. Install it with SOP-152. A version that's already published is skipped.

## Checks
- `ls /raiddrive/repos/slurm/<version>/` lists the RPMs, `repodata/` and `build.log`.
- After installing: `./cluster test --live -k test_version_is_the_one_we_built`.

## Notes
- Slurm 26.05 needs `libcurl-devel` to build (found 2026-10-20).
- NVIDIA's repo is on anton only for `cuda-nvml-devel-13-0` (role `nvidia_repo`).

## History
- 2026-10-20: Slurm 26.05.5 (SHA-256 `4680cafc…4f68`), built and published. Three runs:
  - libcurl-devel was missing
  - the plugin check gave a false "missing" (`grep -q` under `pipefail`); fixed
  - a clean build
