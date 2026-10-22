# SOP-132: Job scratch on GPU nodes (each job's private `/tmp`)
**Status:** draft 2026-10-21

## Purpose
- **Each GPU node's own NVMe is its scratch disk.** douglas1 has a 4 TB one, fitted on 2026-10-20 (plan D5). It's formatted once (XFS) and mounted at `/scratch`.
- **Every job gets a private `/tmp` there, and its own fresh `/dev/shm`**, via Slurm's `namespace/linux` plugin (`/etc/slurm/namespace.yaml`). Both are deleted when the job ends.
- This means:
  - jobs never fill the node's 70 GB system disk
  - one customer's job can't see another's temporary files, even on the same node at the same time
  - jobs get fast local space for datasets, checkpoints and compile caches
- **Logins adopted into a job** (`pam_slurm_adopt`, SOP-155) join its namespace, so they see the job's `/tmp`.
- Slurm reports `/scratch` as the node's temporary space (`TmpFS`), so jobs can ask for it with `--tmp`.

**The pieces:**
- Role `ansible/roles/scratch`: the disk and the mount. The disk is named by its stable `/dev/disk/by-id/…` name in `config/nodes.yml` (`scratch_device`). It's never reformatted: a disk that already has a filesystem is left as it is.
- `namespace.yaml`, in role `slurm_node`.
- The plugin lines, in `slurm.conf` (role `slurm_common`).

The mount has `nofail` and a 30-second device timeout, so a dead scratch disk can never stop the node from booting.

## When
- A new GPU node, with its NVMe fitted.
- **`namespace.yaml` changes only with the node idle.** Changing it while jobs run can disturb them (namespace.yaml(5)). Drain first (`sudo scontrol update nodename=<node> state=drain reason="namespace change"`), wait for jobs to end, apply, then resume.

## Before you start
- The disk is the right one, and empty: `ls -l /dev/disk/by-id/ | grep <serial>`, then `sudo wipefs -n <device>` prints nothing.

## Steps
1. Put `scratch_device: /dev/disk/by-id/nvme-…` for the node in `config/nodes.yml`, and commit.
2. `./cluster apply --dry-run`, then `./cluster apply`.
3. `./cluster test --live -k test_scratch`

## Checks
- **Automated:** `./cluster test --live -k test_scratch`, run as two test users of different customers:
  - `/scratch` is the node's own disk, XFS, mounted with `nofail`
  - Slurm reports it as the node's temporary space
  - a job's `/tmp` is its own (owner, mode 700, empty at the start) and on the scratch disk
  - two customers' jobs at the same time can't see each other's `/tmp` or `/dev/shm`
  - a job's folder is gone when it ends
  - 2 GB written to a job's `/tmp` doesn't grow the system disk
  - a login into your own job sees its `/tmp`

## Undo
1. Drain the node and wait for its jobs to end.
2. Remove `NamespaceType` and `TmpFS` from `slurm.conf.j2`, and the `namespace.yaml` task from `slurm_node`. Apply, which restarts slurmd.
3. `sudo umount /scratch`, and remove its line from `/etc/fstab`. The data on the disk stays.
4. Remove the role from `ansible/site.yml`.

## History
- 2026-10-21: first version.
