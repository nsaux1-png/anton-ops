# SOP-155: Slurm on GPU nodes
**Status:** proved 2026-10-22 on douglas1 ([ops log](../ops-log/2026-10-21-douglas1-setup.md)): undone, the tests failed, one apply rebuilt it

## Purpose
A GPU node runs customers' jobs and nothing else:
- **`slurmd`** finds the GPUs and their model through NVIDIA's library (`gres.conf`: `AutoDetect=nvml`).
- **Each job gets exactly what it asked for.** Its cgroup holds it to its cores, memory and GPUs (`cgroup.conf`, SOP-152). With the standard share, that's 10 hardware threads (5 cores) and 20 GB per GPU.
- **Job processes see only their own user's processes.** `slurmd` runs with systemd's `ProtectProc=invisible`, as `sshd` does (SOP-142).
- **Jobs can't reach the internet, the office network or the admin proxy.** They run under customer UIDs, which the node's egress rules stop (SOP-104).
- **Customers log in to a node only while they have a job there** (`pam_slurm_adopt`). The login is put inside that job, so it's limited and billed like the job. Admins (group `wheel`) always get in. `pam_systemd` is off on nodes, because it would move adopted logins out of the job.
  - sshd pulls in `password-auth` as a **substack**: with `include`, its `sufficient pam_localuser.so` ended the check before `pam_slurm_adopt`.
  - With SELinux enforcing, the `cluster_pam_slurm_adopt` policy module lets sshd reach the job steps (`files/cluster_pam_slurm_adopt.te`).
- **Firewall:** a `cluster` zone for the cluster network with SSH, `slurmd` (6818) and the `srun` port range. `srun` inside a job script listens there for multi-node jobs.
- **PMIx** for MPI jobs (`srun --mpi=pmix`).

Roles: `ansible/roles/slurm_common` (packages, munge key, `slurm.conf`, `cgroup.conf`; every machine) and `ansible/roles/slurm_node` (the rest; compute nodes).

The node's hardware is in `config/nodes.yml`:
- CPUs, sockets, cores, threads
- `slurm_real_memory_mb`, a little below what `slurmd -C` reports
- `slurm_gpu_type`, as NVML names it
- `gpu_count`, and `gpu_slots` (the number of GPUs each share is sized for)

A core and the memory beyond `gpu_slots` × 20 GB are kept for the system (`CoreSpecCount`, `MemSpecLimit`).

## When
- A new GPU node, after its OS, driver (SOP-111) and storage (SOP-130) are in place.
- Automatically on every `./cluster apply` after that.

## Before you start
- **Keep a spare SSH session to the node open** for the whole run, so a mistake in the login rules or firewall can be undone through it. Either a second terminal, or `ssh -o ControlMaster=yes -o ControlPersist=yes -S /tmp/<you>-node.sock -fN <node>`, then `ssh -S /tmp/<you>-node.sock <node>` to use it.
- The test customers need credit, or their test jobs wait forever (`QOSGrpBillingMinutes`): `./cluster credits balance`. If needed, `./cluster credits grant c0001 50 --ref TEST-CREDIT-<date>-c0001 --note "test credit"` (SOP-211), and the same for c0002.

## Steps
1. On the node, read what Slurm sees: `ssh <node> sudo slurmd -C`. Put CPUs, sockets, cores, threads, memory (a little lower) and the GPU type into `config/nodes.yml`, and commit.
2. `./cluster apply --dry-run`, then `./cluster apply`.
3. From a **new** terminal, log in to the node as yourself. If that fails, use the spare session (see "If something goes wrong").
4. `sinfo -N`: the node should be `idle`. If it's `drained` or `inval` with an old reason, fix the reason, then `sudo scontrol update nodename=<node> state=resume`.
   - **After raising a node's figures in `config/nodes.yml`** (memory, `TmpDisk`), expect one "Low …" drain. The controller gets the new figures first, and the old slurmd re-registers before it restarts. If `slurmd -C` on the node now shows enough, resume it. This isn't automated, because the same reason is how Slurm reports real loss, like a failed memory stick.
5. `./cluster test --live -k test_slurm_node`

## Checks
- **Automated:** `./cluster test --live -k test_slurm_node`
  - `slurmd` runs and starts at boot, with no plugin errors since it started
  - the node is up with all its GPUs, and matches `config/nodes.yml`
  - its firewall ports are open to the cluster network only, and the rules are permanent
  - one-GPU and two-GPU jobs see exactly their GPUs
  - a job gets 10 threads and 20 GB per GPU
  - a job can't see another customer's processes, and can't reach the internet or the admin proxy
  - finished jobs are recorded with their GPUs and billing units
  - admins log in without a job; a customer without a job is refused; a customer with a job gets in and lands inside it
- **By hand:** `sinfo -N -o '%N %T %G'`, and `scontrol show node <node>`.

## If something goes wrong
- **New SSH logins to the node are refused** ("No route to host" is firewalld's reject):
  1. Through the spare session: `sudo firewall-cmd --zone=cluster --add-service=ssh`.
  2. Fix the role, then apply again.
- **Logins refused for admins:** through the spare session, remove the `# BEGIN/END pam_slurm_adopt` block from `/etc/pam.d/sshd`.
- **A customer with a job is refused ("no active jobs on this node"):**
  1. Add `log_level=debug5` to the `pam_slurm_adopt.so` line for one attempt, and read `journalctl -t pam_slurm_adopt`.
  2. Look in the audit log for sshd denials: `sudo grep 'comm="sshd-session"' /var/log/audit/audit.log | grep denied | tail`.
  3. If SELinux denies something new, add it to `files/cluster_pam_slurm_adopt.te`, then apply.
- **A customer without a job gets in:** check that `/etc/pam.d/sshd` has `account substack password-auth`, not `include`.
- **Jobs wait with `QOSGrpBillingMinutes`:** that customer has no credit. That's billing working (SOP-161).

## Undo
Through a spare SSH session to the node:
1. `sudo systemctl disable --now slurmd`
2. The login rules:
   - delete the `# BEGIN/END pam_slurm_adopt` block from `/etc/pam.d/sshd`
   - change `account substack password-auth` back to `include`
   - un-comment `pam_systemd` in `/etc/authselect/password-auth`
3. `sudo firewall-cmd --permanent --delete-zone=cluster && sudo firewall-cmd --reload`. Cluster traffic falls back to the `public` zone, which allows SSH.
4. `sudo rm -rf /etc/slurm/gres.conf /etc/slurm/job_container.conf /etc/slurm/task_prolog.sh /etc/systemd/system/slurmd.service.d /usr/local/share/cluster/selinux && sudo systemctl daemon-reload`
5. `sudo semodule -r cluster_pam_slurm_adopt` and `sudo dnf remove pmix`
6. Remove `slurm_node` from the compute play in `ansible/site.yml`.

## History
- 2026-10-21: first version, applied to douglas1 ([ops log](../ops-log/2026-10-21-douglas1-setup.md)).
  - The first run cut off new SSH logins: the firewall task was broken, and it ran after the step that sends cluster traffic into the new zone. Fixed through the spare session; the role now opens the zone first.
  - `pam_slurm_adopt` never ran: `include password-auth` let `sufficient pam_localuser.so` end the check first. Now a substack.
  - Then logins with a job were refused: SELinux kept sshd from the job steps' sockets. The role now loads the `cluster_pam_slurm_adopt` module.
  - Tests: 16/16.
