# SOP-144: Shared software (`/cluster/software`)
**Status:** proved 2026-10-21 ([ops log](../ops-log/2026-10-21-douglas1-setup.md))

## Purpose
Software every customer can use without spending their own storage on it (decided 2026-10-21: "it's not fair to force people to use up 20 GB of their storage on software"). It lives on the RAID, and every node sees it over NFS. It's read-only for customers, and free.

| What | Where | How customers use it |
|---|---|---|
| Miniforge (conda and mamba) | `/cluster/software/miniforge/<version>` | `module load miniforge`, then `conda create -p ~/envs/x …`. Their environments and conda's cache go in their own folder. |
| PyTorch: a conda environment with PyTorch's own wheels | `/cluster/software/pytorch/<version>` | `module load pytorch`. Their own packages go on top: `python -m venv --system-site-packages ~/envs/mine`. Their versions come first, ours fill in. |
| Container images (Apptainer) | `/cluster/software/containers/<name>.sif` | `apptainer exec --nv <image> python train.py` |
| Module files and a README | `/cluster/software/modulefiles`, `/cluster/software/README.md` | `module avail` |

Each stack is a conda environment (a Python of its own), not a venv. A venv made from a venv wouldn't see the first venv's packages, so layering a customer's venv on top wouldn't work.

**What's built** is set in `config/versions.yml` (`software:`): versions, checksums, the image digest. Each version is built once into its own folder and never changed. A new version is a new entry, built next to the old one, and becomes the default when it's marked `default: true`. A failed build removes what it half built.

**The pieces:**
- `clusterlib/software.py`: what to build, and the module files and README. It has code tests.
- `clusterlib/software_cli.py`: the root tool `cluster-software`, installed by the `shared_software` role on the storage server.
- `./cluster software list | build [name] | check`

## When
- First setup, and whenever `config/versions.yml` gets a new version.
- Choosing a new PyTorch: the newest release with a build for the CUDA version the driver supports (R580: up to 13.0) and for these GPUs (Blackwell: 12.8 or newer). For example, 2.14.1 has builds for 12.6, 13.0 and 13.2: 12.6 can't run on Blackwell and 13.2 needs a newer driver, so it's 13.0. torchvision's matching release goes with it. torchaudio is left out while its releases lag behind torch's.

## Steps
1. Edit `config/versions.yml` and commit.
2. `./cluster apply`: installs the new `versions.yml` for the tool.
3. `./cluster software build`: downloads and builds whatever isn't built yet. PyTorch is about 4 GB of downloads, an image about 3 GB, so expect tens of minutes.
4. `./cluster software check`, then the tests.

## Checks
- **Code tests:** `./cluster test --code -k test_software`
- **Live tests:** `./cluster test --live -k test_software`, run as a test user:
  - the modules are there, and `module load pytorch` picks the default
  - PyTorch on one GPU (Blackwell, the right version; the result matches the CPU's)
  - two GPUs talking over NCCL
  - the start-up time over NFS (logged; must be under 2 minutes)
  - a customer's venv on top: the job sees both, their versions win, and only the extras use their storage
  - the shared conda makes environments in their folder, used in a job
  - the container image runs with its GPU
  - customers can't change the shared software or pip-install into it

## Undo
- A version: delete its folder, its `.cluster-built` file and its module file, and take it out of `config/versions.yml`. Only after telling customers, since jobs may use it.
- Everything: remove the `shared_software` role from `ansible/site.yml`, then delete `/cluster/software/*` except the folder itself.

## History
- 2026-10-21: first version. Built Miniforge 26.7.2-1, PyTorch 2.14.1 for CUDA 13.0 and the matching image in 270 s; 12 live tests. Proof run: Miniforge and all module files deleted, `check` failed, one `build` restored them.
