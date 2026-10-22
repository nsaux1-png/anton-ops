# SOP-143: What customers get: packages, Python, containers, modules, temporary files
**Status:** draft 2026-10-21

## Purpose
Customers install their own software (requirement 16): pip and venvs, conda, containers. This SOP covers what only root can provide, the same on the login node and every compute node, so whatever builds on the login node runs in a job:
- **Packages** (`ansible/roles/user_environment/defaults/main.yml`):
  - compilers and build tools
  - git and git-lfs
  - **Python 3.12**, with headers for building Python packages
  - libraries common packages expect (OpenCV needs libGL and the X libraries even without a screen)
  - everyday tools
- **Apptainer**, which runs containers (any Docker or NVIDIA image) without root. Images are mounted with squashfuse. Containers see all of `/cluster`: home, projects and the shared software.
- **The `module` command** (`environment-modules`, part of Rocky). It also looks in `/cluster/software/modulefiles`, the shared software (SOP-144).
- **Temporary files:**
  - On the login node, a customer's temporary files (`TMPDIR`) go to `~/.tmp`, which counts against their storage limit. So a big pip build or container pull can't fill the system disk the cluster's services need.
  - In jobs, Slurm's task prolog sets `TMPDIR=/tmp`, the job's own.
- **On the login node, a welcome message** (`/etc/motd.d/cluster-welcome`) and the customers' guide at `/cluster/docs/guide.md`, copied from `docs/user-guide.md`.

Role: `ansible/roles/user_environment` (every machine; the login-node parts on the `login_nodes` group in `config/nodes.yml`, which is anton for now).

## When
Automatically on every `./cluster apply`. To add a package: put it in the list, commit, apply.

## Steps
1. `./cluster apply --dry-run`
2. `./cluster apply`

## Checks
- **Automated:** `./cluster test --live -k test_user_environment`, run as a test user:
  - every package on every machine customers use
  - the same Python 3.12 everywhere
  - `module` on the login node and in a job, with the shared path
  - `TMPDIR` in the customer's own folder on the login node, `/tmp` in a job; admins unaffected
  - Apptainer pulls an image on the login node and runs it there, and in a job, as the customer, seeing `/cluster`
  - a program built on the login node runs in a job
  - the welcome message and the guide
  - a real SSH login sets it all up

## Undo
Remove the role from `ansible/site.yml`, and delete `/etc/profile.d/cluster-user.sh`, `/etc/motd.d/cluster-welcome` and `/cluster/docs`. Remove packages only if nothing needs them.

## History
- 2026-10-21: first version.
