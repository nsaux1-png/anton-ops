# SOP-145: The login node for customers: limits and network
**Status:** draft 2026-10-21

## Purpose
Customers log in to the login node (the `login_nodes` group: anton until a separate machine exists, Q8) to install software, edit and submit jobs. The work itself runs in jobs. anton is also the head node: the billing database, the Slurm controller and every admin tool, on 31 GB of RAM. So:

- **Limits for each customer user**: 4 cores, 6 GB of memory, no swap, 512 processes. They're set as a systemd slice for their UID (`/etc/systemd/system/user-<uid>.slice.d/50-cluster-login.conf`). A program over the limit is stopped, and the cluster's services keep their memory. Values are in `ansible/roles/login_node/defaults/main.yml`.
- **Network rules for customer accounts** (UID 2000 and up), in nftables table `cluster_login_egress`:

| | Customers can reach |
|---|---|
| The internet | **yes**: installs and downloads happen here |
| Compute nodes, SSH and slurmd (22, 6818) | **yes**: SSH into their own jobs, and `srun` |
| Slurm's controller and accounting on this machine | **yes** |
| Answers on connections made to them (`srun`'s output from the nodes) | **yes** |
| This machine's admin services: the proxy, MariaDB, Cockpit, NFS, mail | **no** |
| The rest of the cluster network: BMCs, NFS, other ports | **no** |
| The office network and every other private range, link-local | **no** |

**SSH tunnels run as the customer, so the same rules apply to them.** A tunnel through the login node reaches only what the customer could reach directly. The Jupyter recipe in the guide is a second SSH hop into the node of their own running job (`ssh -J`), which works because SSH to the compute nodes is allowed and `pam_slurm_adopt` lets them in (SOP-155).

Admins (UID below 2000) and root aren't limited.

Role: `ansible/roles/login_node` (the `login_nodes` group). The rules load at boot through `cluster-login-egress.service`, like the compute nodes' (SOP-104).

## When
Automatically on every `./cluster apply`. A new customer user gets their limits on the next apply.

## Steps
1. `./cluster apply --dry-run`
2. `./cluster apply`

## Checks
- **Automated:** `./cluster test --live -k test_login_node`, run as a customer:
  - the internet, SSH and slurmd on the nodes, Slurm here, and `srun` output coming back all work
  - the office network, other private ranges, the rest of the cluster network and each blocked local port are refused
  - tunnels obey the same rules
  - the Jupyter-style jump into your own job lands inside the job
  - the session limits are set
  - a program over the memory limit is stopped
  - admins aren't limited
- **By hand:** `sudo nft list table inet cluster_login_egress` (the counters show what was refused), and `systemctl show user-<uid>.slice -p MemoryMax`.

## Undo
`sudo systemctl disable --now cluster-login-egress`, and `sudo rm -r /etc/systemd/system/user-*.slice.d/50-cluster-login.conf && sudo systemctl daemon-reload`. Then remove the role from `ansible/site.yml`.

## History
- 2026-10-21: first version.
