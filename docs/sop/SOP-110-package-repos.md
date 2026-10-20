# SOP-110: Package repositories
**Status:** proved 2026-10-19 ([ops log](../ops-log/2026-10-19-step2-gpu-driver.md))

## Purpose
Every machine has the same repository settings (role `ansible/roles/repos`):
- **CRB on.** EPEL packages, DKMS (for the NVIDIA driver) and our Slurm build need its development packages.
- **EPEL never supplies Slurm** (`excludepkgs=slurm*`). EPEL ships an old Slurm (22.05), and ours is built from SchedMD's source. Without this, a routine update could swap in the wrong Slurm.

The NVIDIA repo is added only on GPU nodes, by SOP-111. Compute nodes reach all repos through the admin proxy (SOP-103) until the package mirror exists (build plan phase 3).

## When
Automatically on every `./cluster apply`.

## Steps
1. `./cluster apply --dry-run`, then check the `.repo` diffs.
2. `./cluster apply`, and answer `y`.

## Checks
- **Automated:** `./cluster test --live -k test_repos`.
- By hand: `dnf repolist` lists `crb`; `dnf -q list --available 'slurm*'` lists nothing from EPEL.

## Undo
`sudo sed -i '/^\[crb\]/,/^\[/ s/^enabled=1/enabled=0/' /etc/yum.repos.d/rocky.repo` and remove the `excludepkgs=slurm*` line from `[epel]` in `/etc/yum.repos.d/epel.repo`. Then remove `repos` from `ansible/site.yml`.

## History
- 2026-10-19: first version, applied to anton and douglas1.
