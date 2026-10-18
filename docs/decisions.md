# Decision log

Newest at the bottom. Each entry gives the date, the decision, and the reason.

## 2026-10-17: Machine roles
anton is the head node; douglas1 is the first compute node. Future GPU and dual-socket CPU nodes join as compute nodes.

## 2026-10-17: Rename the head node to anton
The head node was misnamed `douglas1`, while the machine at 172.16.50.11 is the real douglas1. It was renamed with `hostnamectl set-hostname anton`. See `ops-log/2026-10-17-rename-anton.md`.

## 2026-10-18: Ansible, wrapped in a `./cluster` command
**Why:** Ansible steps check before changing anything, so re-running is safe across many machines, which is hard to get right in plain bash. The wrapper gives operators short, memorable commands and does the logging.

## 2026-10-18: Compute nodes get outbound internet through anton (NAT)
**Why:** this is the norm for research and commercial clusters: nodes sit on a private network nobody outside can reach, and outbound traffic goes through the head node's firewall. Customers expect pip, conda and dataset downloads to work. Full isolation with local mirrors is for regulated data and can be added later for one partition if a customer needs it.

## 2026-10-18: Keep anton's existing RAID1 mirror as it is
The 2×4 TB mirror (`md0`, XFS) stays as it is, internal label included. Its contents get checked read-only before it is mounted for `/home` and shared software.

## 2026-10-18: Temporary passwordless sudo during the build
**Why:** Claude's shell can't answer a sudo password prompt. A drop-in file `/etc/sudoers.d/90-papaya-temp` on each machine allows it during the build. **It must be removed when the build is done.** This may be revisited.

## 2026-10-18: Separate SSH keys per purpose
anton's `~/.ssh/id_ed25519` is only for reaching cluster nodes. GitLab gets its own key, so a leak of one doesn't expose the other.

## 2026-10-18: Everything is recorded in this repo, hosted on our GitLab
Discussions, decisions, procedures and scripts all live here.

## 2026-10-18: 172.16.50.11 is named `douglas1`
The `douglas1_gpu` name in anton's `/etc/hosts` was replaced with `douglas1` (backup kept as `/etc/hosts.bak-*`). Ansible will manage `/etc/hosts` from now on.
