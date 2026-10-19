# Architecture

Status: planned. Nothing below is installed yet unless marked otherwise.

## Roles

### anton: head node
- **Slurm controller** (`slurmctld`): schedules jobs onto compute nodes.
- **Slurm accounting** (`slurmdbd` + MariaDB): records every job (user, account, CPUs, GPUs, memory, time). This is the basis for billing.
- **Login point:** users SSH into anton and submit jobs from there. They do not log into compute nodes directly.
- **Shared storage:** the 2×4 TB RAID1 mirror (`/dev/md0`, XFS) is exported over NFS for `/home` and shared software.
- **Gateway:** compute nodes reach the internet through anton (outbound NAT only). Nothing outside can reach the compute nodes.
- **Time server** (chrony): munge, Slurm's authentication, fails if clocks drift between machines.
- **Ansible control node:** this repo lives here and configures every machine, including anton itself.

### Compute nodes (douglas1 and future nodes)
- `slurmd`, munge, NFS mounts from anton.
- GPU nodes: NVIDIA driver, with GPUs registered in Slurm as GRES so jobs can request them (`--gres=gpu:N`).
- cgroup limits, so a job only gets the CPUs, GPUs and memory it asked for.

## Networks

| Network | Purpose | anton | douglas1 |
|---|---|---|---|
| 192.168.5.0/22 | Upstream LAN and internet, SSH from outside | 192.168.5.200 (`eno1`) | none |
| 172.16.50.0/24 | Cluster network | 172.16.50.1 (`eno2`) | 172.16.50.11 (`enp66s0f1np1`) |
| 172.16.99.0/24 | Internal link between douglas1 and its own BMC (virtual USB network). Not part of the cluster; left alone. | none | 172.16.99.201 |

## Billing

- Slurm **accounts** represent customers or groups, and users belong to accounts.
- Jobs are charged using billing weights per resource (GPU-hours, CPU-hours, possibly memory), set per partition.
- Users who aren't registered under an account can't submit jobs (`AccountingStorageEnforce`), so no usage goes unbilled.
- A monthly report script produces usage per account for invoicing.

## Source of truth and automation

- Ansible playbooks, wrapped by a `./cluster` command (`add-node`, `add-user`, `apply`, `billing-report`, ...).
- Data files define the cluster: `nodes.yml`, `users.yml`, billing rates.
- User and group IDs are assigned centrally and are identical on every machine.
- Every run is logged with its timestamp, operator, git commit and output.
