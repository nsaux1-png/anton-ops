# 2026-10-19: Independent plan review

**By:** a separate Claude agent (Fable, max effort), at the user's request. Read-only: it made no changes, used no SSH and no sudo, and checked claims against official documentation and source code.
**Reviewed:** commit 6958601.

## What we did with it
**Fixed in the docs right away** (`slurm-design.md`, `plan.md`, `build-plan.md`):
- **W1** The credit limit is now "usage so far + what the balance buys".
- **W2** Storage is enforced and billed with group quotas, with a live test against escaping the quota.
- **W3** Turning on quotas needs a full unmount and mount.
- **W4** Charges are keyed on `DBIndex`.
- **W5** With `safe`, Slurm doesn't kill running jobs over limits.
- **W6** Dropped GPU energy accounting.
- **W7** Job scripts use Slurm's own 60-day purge, and backups skip the script table.
- **W8** `hidepid` replaced by `ProtectProc=invisible`, to be tested.
- **W9** `PrivateData` goes in both config files.
- **W10** Code must be built with CUDA 12.8+.
- **R3** Billing units are integers, Slurm counts threads, and there's one partition per GPU model.
- **R4** `job_submit.lua` rules.
- **R5** Root-owned SSH keys, `pam_slurm_adopt` settings, no Slurm coordinators.
- **R6** A priority tier is a partition, not a QOS.
- **R9** Integer amounts, storage price changes, and file deletion as a confirmed command.
- All the inconsistencies listed below.
- **Simplify:** running jobs are charged hourly.

**Folded into the build plan:**
- the driver install order and checks (kernel update first, CRB + EPEL, DNF module stream, versionlock, DKMS rebuild test, PCIe link check, exclude EPEL's Slurm)
- admin home folders off `/home` before NFS
- quota types decided while `/raiddrive` is empty
- ledger prerequisites
- database binlogs or hourly dumps (R2)

**Fixed in the repo:** `tests/__pycache__` was committed; it's removed, and a `.gitignore` is added (Build order 7).

**Needs the user's decision:**
- **R1:** a separate login host before the first customer
- **R7:** encrypt customer names and emails in the repo
- **R8:** SSH password login is on, on a public IPv6 address
- whether to close Cockpit to the office network
- **R9:** legal and tax questions, for counsel

## Report
The report as delivered, lightly formatted. Line numbers refer to commit 6958601.

### WRONG (factual errors)
1. **slurm-design.md:186: the credit limit formula `GrpTRESMins=billing=<balance>` is wrong.** With NoDecay, Slurm starts a job only if its full cost plus what running jobs still hold fits under (limit − the QOS's lifetime usage). So once lifetime spend passes the current balance, the customer is blocked, and a second top-up appears to do nothing. That lifetime usage is kept in slurmctld's state files, not in the database. Fix: each sync sets limit = current usage + (balance − cost so far of running jobs), and never resets the usage; this also recovers on its own if the state files are lost. Per-item price overrides mean there's no single money-to-units rate: convert at the customer's highest price per unit, or allow only `discount_percent` at launch. Sources: https://slurm.schedmd.com/qos.html (NoDecay), Slurm source acct_policy.c and assoc_mgr.c. VERIFIED.
2. **slurm-design.md:100,107: customers can get around XFS project quotas, and the df/quota claim is overstated.** The owner of a file can change its project ID (`chattr -p 0`); the kernel only blocks this inside user namespaces. Project 0 is never limited, so a customer can move data out of both the limit and the storage bill. (Linux v5.14 fs/ioctl.c and current fs/file_attr.c; xfs_quota(8) says only privileged users can do this, but the kernel code says otherwise.) `quota` never shows project quotas to non-root users (quota(1)). `df` shows the limit only for paths inside the customer's folder tree; a plain `df` still lists 3.7 TB. Fix: mount with user, group and project quotas (the filesystem is XFS v5, so all three can be on at once). Make the customer group each user's only group, and set setgid on project folders. Enforce and bill on the group quota, since users can't chown or chgrp to a group they're not in. Use the user quota for per-user usage, and keep the project quota only for `df`. Add a live test: a test user runs `chattr -p 0` and the bill doesn't change. VERIFIED in upstream source; confirm on RHEL's kernel with that test.
3. **build-plan.md:35: "needs one remount" won't turn quotas on.** XFS accepts quota options on remount, reports success, and ignores them (xfs_super.c: "silently ignore all options that we can't actually change"). /raiddrive is mounted `noquota` today. Fix: change fstab, do a full unmount and mount, then check with `xfs_quota -x -c state`. VERIFIED.
4. **plan.md:257: "the job ID is the key" will miss charges.** A requeue keeps the job ID, and IDs restart from 1 if the controller's state is lost. sacct shows only the latest record unless `-D` is given, so a reused ID would be skipped as "already charged". Records can also arrive late: when slurmdbd is down, slurmctld queues them and drops any past its queue limit. Fix: key charges on sacct's `DBIndex`, query with `-D`, and rescan several days back on each run. Sources: https://slurm.schedmd.com/sacct.html, https://slurm.schedmd.com/accounting.html. VERIFIED.
5. **slurm-design.md:197: "Slurm kills them immediately" is not true with `safe`.** The docs say "a job won't be killed due to limits, even if the limits are changed after the job was started", and the source returns early when `safe` is set. Harmless, but the rule "never set the limit below what running jobs need" isn't needed. Source: https://slurm.schedmd.com/resource_limits.html. VERIFIED.
6. **slurm-design.md:161: `acct_gather_energy/gpu` records nothing on NVIDIA GPUs.** The docs say "Only available for rsmi at present" (rsmi is AMD's library), and the NVML plugin's `gpu_p_energy_read()` is an empty stub. Fix: drop it, or sample `nvidia-smi` power readings outside Slurm. VERIFIED.
7. **slurm-design.md:164: Slurm does expire job scripts on its own.** `AccountingStoreFlags=job_script` plus `PurgeJobScriptAfter=60days` in slurmdbd.conf does it, and customers can read their own scripts with `sacct -B`. That replaces the copy script, the folder and the nightly cleanup. Either way, database dumps keep scripts past 60 days unless backups are kept 60 days or less. Source: https://slurm.schedmd.com/slurmdbd.conf.html. VERIFIED.
8. **slurm-design.md:75: mounting /proc with `hidepid` is unsupported on RHEL 9.** Red Hat says `hidepid=2` "is not recommended at all on RHEL7 and later", and user@.service fails on RHEL 9. systemd's maintainers say "We do not support it, full stop." Fix: add `ProtectProc=invisible` to sshd.service and slurmd.service so customer processes inherit a hidden /proc. Sources: https://access.redhat.com/solutions/6704531, https://www.openwall.com/lists/oss-security/2024/02/02/7. The problem is VERIFIED; the fix is UNVERIFIED and needs testing.
9. **slurm-design.md:73: `PrivateData` must go in both slurm.conf and slurmdbd.conf.** In slurm.conf, the accounts and users values and the sacct part of jobs are marked "NON-SlurmDBD ACCOUNTING ONLY". Without slurmdbd.conf, `sacct`, `sacctmgr` and `sreport` show other customers' data. VERIFIED.
10. **plan.md:210: older CUDA builds won't run on the 5070 Ti.** Blackwell needs code built with CUDA 12.8+ or shipped with PTX; NVIDIA says "An application fails to execute if it does not include PTX". Older PyTorch wheels fail. Fix: state the minimum in the user guide and test it weekly. Source: https://docs.nvidia.com/cuda/blackwell-compatibility-guide/. VERIFIED.

### RISKY / MISSING
1. **anton as the customer login node (plan.md:46, D6).** anton holds the ledger, the database credentials, the munge key, the vault password, the Ansible key that is root on every node, the GitHub deploy key and customer personal data. It's now also the only place customers can reach the internet, and it sits on the shared office LAN. One local-root bug exposes everything, and customer /tmp and /dev/shm compete with MariaDB for RAM and the root disk. Fix: a separate login host before the first external customer (at minimum a VM on anton). On it, set per-user memory, CPU and task limits, a per-user /tmp, and egress rules that block customer accounts from 192.168.4.0/22 and the LAN's IPv6 ranges (the new egress role covers compute nodes only). Also set `DisableRootJobs=YES`, and check where douglas1's BMC network port sits and change its password.
2. **plan.md:182: the money records sit on one unmirrored disk.** The ledger, Slurm accounting and the controller state are on one consumer NVMe, with no UPS and nightly dumps only. That's up to 24 hours of money records at risk. Fix: database binlogs or hourly dumps to /raiddrive and off-site; consider a small UPS for anton alone.
3. **Billing units.** Slurm stores the billing number as a truncated integer, so "1 GPU = 1" weights (slurm-design.md:149) bill small CPU jobs as 0, and those jobs also escape the credit limit. Slurm counts each hardware thread as a CPU, so `DefCpuPerGPU` and the job_submit cap must be 10, and a "CPU-core-hour" price (:178) is off by 2× unless converted. Billing weights can only be set per partition, so mixed GPU models in one `gpu` partition (:114) can't be weighted correctly. Fix: integer weights (e.g. 1 unit = 1 thread, GPU = 10, memory = 0.5 per GB) and one partition per node type. Source: https://slurm.schedmd.com/tres.html. VERIFIED.
4. **job_submit.lua.** Users can change pending jobs with `scontrol update`, so it also needs `slurm_job_modify`. It should reject `--mem=0` and `--exclusive`, and handle every way of asking for GPUs. It runs while slurmctld holds its locks, so it must do no file or network I/O. VERIFIED.
5. **Access controls.** Keep customer SSH keys in root-owned `/etc/ssh/authorized_keys/%u`, so customers can't add keys and share accounts. pam_slurm_adopt needs `PrologFlags=contain`, pam_systemd removed from sshd's PAM stack, and `action_adopt_failure=deny` (the default "allow" is for testing only). Don't make managers (:228) Slurm coordinators: coordinators "can change limits on account and user associations" and can cancel or requeue jobs. VERIFIED.
6. **Priority tiers (plan.md:195, D24).** A job has only one QOS, so a "priority" QOS sold later would bypass the credit limit. Sell priority as a separate partition instead.
7. **Admin control and audit.** Agent roles (:285) mean nothing while `./cluster` runs from an account with full sudo. The run logs (folder mode 2770, group wheel) can be edited by any admin. Customer names and emails in customers.yml are committed and auto-pushed to GitHub; encrypt them with Vault.
8. **Exposed right now.** sshd listens on all IPv6 addresses, anton has a public IPv6 address, both network ports are in firewalld's `public` zone, and passwordless sudo is active. Check `sshd -T` and scan the IPv6 address from outside today.
9. **Money and terms** (legal points UNVERIFIED). Store integer amounts and decide what 1 credit is worth (D40). On the 1st of the month the full current storage use is charged at once. Mid-month storage price changes are undefined. Deleting files after 30 days negative should be a confirmed manual command. Get counsel on state sales tax and unclaimed-property rules for expired credits, on sanctions screening, and on the abuse contact.

### INCONSISTENT
- `users.yml`, `accounts.yml` and `inventory/` (plan.md:114, 135, 374; todo.md; architecture.md:39) vs `config/customers.yml`, `uids.yml` and `rates.yml` (slurm-design.md:66-67).
- plan.md:373-374 puts the mirror in step 1 as a prerequisite for the driver; decisions.md and build-plan.md say proxy first. plan.md:98 still says "User jobs still use the NAT".
- Negative balance "for storage only" (slurm-design.md:192, decisions.md:64) vs grace minutes being charged (:204) vs D41 "no overdraft" (plan.md:283).
- plan.md:189 says "24 GB" per GPU; the decision is 20 GB.
- plan.md:66 says "cluster side trusted"; the new firewall role (correctly) opens only named services.
- slurm-design.md:256 tests "admin login from outside the VPN is refused", but the VPN is now "later".
- plan.md:381-382 onboards a customer before removing temporary sudo.
- D20's "free allowance" (plan.md:164) vs billing on peak × price.
- The docs/procedures → docs/sop rename is done in plan section 17 and todo; only plan.md:120 still says "procedures".

### SIMPLIFY
- Use Slurm's own job-script purge (Wrong 7).
- Drop GPU energy accounting, and DCGM in plan.md:294 (DCGM has only limited functionality on GeForce).
- Allow one price-override mechanism at launch.
- Charge running jobs hourly, like storage, so expiry no longer needs "held back" amounts.
- Build the package mirror later, as now decided. NVIDIA's and AppStream's repos use DNF modules, so the mirror must keep their module metadata; `reposync --newest-only` leaves metadata pointing at missing RPMs (dnf-reposync(8)).

### BUILD ORDER
1. Today: SSH hardening and the IPv6 check.
2. NVIDIA driver: set up the proxy and chrony first. Update douglas1 to the newest 9.8 kernel and reboot, then install `kernel-devel-matched`. Enable CRB plus EPEL (for dkms), then the `nvidia-driver:<branch>-open` stream, and versionlock it (https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/rocky-linux.html). Prove the DKMS rebuild on a kernel update. Check each GPU's PCIe link, and whether GPU utilization, memory and power readings work on GeForce. Exclude `slurm*` from EPEL, which ships Slurm 22.05.11, and add CRB to the mirror list.
3. Move admin home folders off /home before NFS (plan.md:160). papaya's home holds the repo and keys on anton, and the authorized_keys Ansible uses on douglas1; mounting the shared /home over them breaks `./cluster`.
4. Decide the quota types and do the single full unmount while /raiddrive is still empty.
5. Before writing the ledger: D40, integer amounts, the sync formula and `DBIndex` keys.
6. Before the first customer: separate login host, temporary sudo removed, backups restored once as a test.
7. `tests/__pycache__/*.pyc` is committed and there's no .gitignore. A fresh clone rewrites it, and `./cluster apply` then refuses because the repo has uncommitted changes.

### CHECKED AND FINE (VERIFIED)
- `DefMemPerGPU` and `DefCpuPerGPU` exist and there is no max-per-GPU setting, so job_submit.lua is needed.
- `MAX_TRES` behaves as described; NoDecay and `safe` work as described for starting jobs.
- `EnforcePartLimits=ALL`, `CoreSpecCount` and `MemSpecLimit` are correct.
- `gres/gpuutil` and `gres/gpumem` exist (they need `AutoDetect=nvml`).
- RTX 50-series requires the open kernel modules.
- Several folders can share one quota, and `df` works over NFS for paths inside it.
- The RAID mirror has a write-intent bitmap, so a power cut means a quick resync.
- Per-job /tmp is `NamespaceType=namespace/linux` in current Slurm.
- The new per-account egress rules and the firewall zone look right, and `./cluster` follows its stated rules.

## Follow-up check by the main session (read-only, 2026-10-19)
`sudo sshd -T` on anton:
- `passwordauthentication yes`
- `permitrootlogin without-password` (root can log in with a key)
- listening on `0.0.0.0:22` and `[::]:22`

anton's global IPv6 addresses on `eno1` are `2600:6c82:…/64` (public) and `fd1b:…/64` (private). Whether the public one is reachable from the internet depends on the router's IPv6 firewall; that has to be tested from outside.
