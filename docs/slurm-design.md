# Slurm system design

**Status: DRAFT, 2026-10-19.** Built from the user's requirements given that day. This page is the overall shape; [`plan.md`](plan.md) has the details of each piece.

## Requirements (user, 2026-10-19)
1. Track usage per user.
2. One simple config file to change people's settings.
3. The admin side is completely closed to users.
4. Track both compute usage and disk space. Disk space has limits, and storage is billed on the month's peak usage.
5. Users shouldn't be able to see the total disk space.
6. Ready for more GPU nodes and CPU nodes of different kinds.

## 1. Tracking per user
- Slurm's accounting (`slurmdbd` + MariaDB on anton) records every job: user, customer account, partition, CPUs, memory, GPUs (by model), start and end time, and final state. Records are kept forever.
- Each user belongs to a customer account. Bills are per customer, broken down by user.
- Actual GPU use per job (utilization and memory, from NVIDIA's NVML) is recorded too, so customers can see how well they used what they paid for. We still charge for allocated resources (plan 12.1).

## 2. The config file
The admin edits one file, `config/customers.yml`:

```yaml
defaults:                      # apply unless a customer or user overrides them
  storage_gb: 100              # each user's home folder limit
  max_gpus: 4                  # GPUs one user can hold at once

customers:
  acme:
    name: Acme Robotics
    billing_email: ap@acme.example
    project_storage_gb: 1000   # shared project folder for the whole customer
    max_gpus: 8                # across all of the customer's users
    users:
      alice:
        email: alice@acme.example
        ssh_key: ssh-ed25519 AAAA... alice@laptop
        max_gpus: 6            # override for this user
      bob:
        email: bob@acme.example
        ssh_key: ssh-ed25519 AAAA... bob@desktop
        status: suspended      # active (default) | suspended | removed
```

- `./cluster apply` shows what will change (for example "alice: max GPUs 4 → 6") and asks before doing anything. It then updates Linux accounts, SSH keys, Slurm limits and disk quotas on every machine, logs the run, and commits the file. The git history shows who changed what, and when.
- User IDs (UIDs) are assigned automatically when a user first appears and kept in a generated file (`config/uids.yml`) that nobody edits by hand. A UID is never reused.
- Prices go in `config/rates.yml` and machines in `config/nodes.yml`.

## 3. Admin side closed off
- Customers have no sudo. They can only log into a compute node while one of their own jobs is running on it (`pam_slurm_adopt`).
- Customers only see their own data:
  - their own jobs and usage (Slurm `PrivateData`)
  - their own files (home folders `0700`; a project folder is readable only by that customer)
  - their own processes (`/proc` mounted with `hidepid`)
- Admin material is readable by root only: this repo and the config files, the vault password, the ops logs, the database credentials (`slurmdbd.conf`, mode `0600`) and the munge key. Only admin accounts are Slurm administrators.
- Admin accounts can only log in from the local network (or a VPN later). Customers log in from the internet with SSH keys only, so a stolen customer key gives no route to an admin account.
- The commands customers get (`myusage`, `mystorage`) only show the caller's own data.
- Any Linux user can list the usernames on a system. Usernames therefore shouldn't reveal which company someone belongs to (Q1).

## 4. Compute and storage: tracking, limits, billing
- **Compute** comes from Slurm accounting (section 1), priced per GPU-hour (by GPU model) and per CPU-hour (plan D29).
- **Storage limits:** XFS project quotas on `/raiddrive`, one for each user's home folder and one for each customer's project folder. The hard limit is the most a customer can use; writing past it fails. An email warning goes out at 90%.
- **Storage measurement:** every hour a collector records each user's and each customer's usage in the accounting database.
- **Storage billing:** the month's **peak**, meaning the highest hourly reading, times the price per GB. The quota is only a ceiling; customers pay for what they actually used at the peak.
- Scratch space on compute nodes is wiped after each job and isn't billed separately.
- **Monthly statement** per customer: compute by user plus peak storage, built from the same database.

## 5. Hiding the total disk space
- With XFS project quotas, `df` and `quota` show a user **their own limit** as the size of the disk, not the 3.7 TB.
- Limitation: on the machine that physically holds the disks (anton today), a technical user can still read the raw disk sizes, for example with `lsblk`. Hiding them completely means customers log into a separate login node that only reaches storage over NFS (plan D6). The medium-size plan already needs that node within the year.
- During the build we log in as a test customer and record exactly what is visible.
- Optionally, Slurm can also hide how many nodes and GPUs exist (`PrivateData=nodes`) (Q2).

## 6. Mixed GPU and CPU nodes
- Each node is one entry in `config/nodes.yml`: name, type, CPU sockets and cores, memory, GPU model and count, local scratch. Slurm's node list is generated from it.
- Partitions by node type, starting with `gpu` and `cpu`. GPUs are registered with their model (`gpu:rtx5070ti`), so a job can ask for a model (`--gpus=rtx5070ti:2`), and each model can have its own price.
- Node features let jobs pick CPU type, memory size and so on (`--constraint`).
- By default a GPU job gets a fair share of the node's CPUs and RAM per GPU (a tenth of douglas1 per GPU) unless it asks for more.
- On dual-socket CPU nodes, a job's cores are kept on one socket where possible (cgroups plus CPU affinity).
- A job can use several GPUs in one node; they talk over PCIe, since the 5070 Ti has no NVLink. Jobs spread across several nodes would need a much faster network than 10 Gb (for example 100 Gb InfiniBand). That isn't planned for now.

## Open questions
- **Q1.** Usernames: neutral (`u10023`) or name-based (`alice.chen`)?
- **Q2.** Hide the number of nodes and GPUs from customers too?
- **Q3.** Admin logins only from the local network?
