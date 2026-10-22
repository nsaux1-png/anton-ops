# 2026-10-21: douglas1 joins the cluster (build plan phases 4–7 on the GPU node)

## Why
douglas1 is back (ops log [2026-10-21-douglas1-back](2026-10-21-douglas1-back.md)). The user asked to carry on with the douglas1 steps, without reboots.

## Housekeeping first
- **A password in douglas1's shell history** (typed at the prompt by mistake, line 74 of papaya's `~/.bash_history`) was deleted at the user's request, without printing it. `histappend` is on, so the console session still logged in won't write it back.
  - The same password appears twice as a username in `/var/log/secure-20261018`, from login attempts at the console on 10-14 and 10-16. That log was left as it is. The user was told to change the password.
- **douglas1's console (`tty1`) is still logged in as papaya** since 2026-10-20 16:18. The user was asked whether to log it out.

## 1. System logs kept on disk (SOP-106, new)
- Neither machine had `/var/log/journal`, so journald kept logs in memory only. That's why the 10-19 failure left nothing.
- New role `journal` (every machine, tag `journal`), with live tests `tests/live/test_logs.py` (3 tests).
- Applied: `./cluster apply --tags journal`, log `20261021-162557-apply.log`, "Done and settled". Tests 3/3.
- **Proof run:**
  1. Undid it on both machines (the SOP's undo steps). The old journal folders were kept as `/var/log/journal-before-proof-20261021`.
  2. The tests failed on both machines, 6 failures as expected.
  3. One apply from the repo (`20261021-163031-apply.log`) fixed it. Tests 3/3 again.

## 2. douglas1's kernel options recorded (SOP-107, new)
- New role `kernel_args` (every machine, tag `kernel_args`). It adds the options listed in `config/nodes.yml` (`kernel_args`) to every boot entry with `grubby`, and takes off any listed in `kernel_args_remove`. It never reboots. Live tests: `tests/live/test_kernel.py` (3 tests).
- douglas1's eight extra options recorded as they were. The first apply changed nothing (`20261021-163430-apply.log`).
- **The proof run found a bug in `./cluster apply` itself:**
  1. With `initcall_debug` taken off by hand, the tests failed as expected.
  2. But the apply said **"Nothing to change"** and didn't put it back.
  3. Cause: the preview runs Ansible in check mode, which skips `command`/`shell` tasks without counting them as changes. A change made only by such a task was invisible to the preview, and to the "settled" check after an apply.
- **Same blind spot in three older roles:**
  - the initramfs rebuild (`nvidia_driver`)
  - enabling the NVIDIA driver stream (`nvidia_driver`)
  - the quota remount (`storage`)

  They only ever ran because other changes happened in the same run.
- **Fix:** the check task in front of each of these now reports the pending change in check mode (`changed_when: ansible_check_mode and ...`).
  - New code test `tests/code/test_roles.py`: every command/shell task in every role must be read-only, run its own `--check`, use `creates`/`removes`, be explicitly real-run only, or be gated on such a check task.
  - Run on the previous versions of the roles, it flags exactly those five tasks. Code tests: 110/110.
  - The billing `setup`/`sync` tasks stay real-run only, with a comment saying why: they follow the code and config the preview does show, and the hourly run repeats the sync.
- **Proof run again, from the start:**
  1. Applied (`20261021-164011-apply.log`): put back `initcall_debug`, "Done and settled". Tests 3/3.
  2. Took it off by hand: the tests failed (2).
  3. One apply (`20261021-164052-apply.log`) put it back, "Done and settled". Tests 3/3.
- The proof runs moved `initcall_debug` to the end of the options. Order doesn't matter.

## 3. Accounts, logins and shared storage on douglas1 (SOP-130, 141, 142)
- A spare SSH connection to douglas1 was kept open (`ssh -M`, a control socket), so a mistake in the login rules could be undone through it.
- `./cluster apply --limit douglas1 --dry-run`: 13 changes, all expected:
  - the test customers' groups and users
  - root-owned customer SSH keys and the customer `sshd` rules
  - process hiding for `sshd` and `user@.service`
  - the NFS client and the `/cluster` mount
- `./cluster apply --limit douglas1` (`20261021-164438-apply.log`): "Done and settled".
  - A new SSH login (not through the spare connection) works.
  - `/cluster` is mounted from `anton:/raiddrive/cluster` over NFS 4.2.
  - `zz01` has uid 10100, gid 20000, as on anton.
- **Full live suite: 116 tests pass, 1 skipped** (the per-user GPU limit, which needs Slurm on a GPU node).
  - That includes customer logins, process hiding, the same files on every node, accounts with the same IDs everywhere, and the customer network limits.
  - Since this was douglas1's first run of these roles, straight from the repo with no improvising, it also counts as their proof run on a compute node. They were proved on anton on 2026-10-20.

## 4. Slurm on douglas1 (SOP-152, SOP-155 new)
### 4a. Packages, munge and configuration (`slurm_common` on compute nodes)
- The first preview failed safely: munge's restart handler ran in a first-run preview, before munge was installed. Guarded like the squid and NFS handlers.
- Applied (`20261021-170106-apply.log`). A munge credential made on anton decodes on douglas1.
- `slurmd -C` on douglas1: 112 CPUs, 1 socket, 56 cores, 2 threads, 257,056 MB, `gpu:nvidia_geforce_rtx_5070_ti:10`. Recorded in `nodes.yml`: memory 257,000 (a little lower) and the GPU type.
- **`slurmd` started too early.** The "Restart Slurm daemons" handler did a plain restart, which also starts a stopped daemon. So `slurmd` ran before its firewall, `gres.conf` and login rules were in place.
  - It registered with 0 GPUs, and Slurm marked the node invalid and drained it, so no job could start.
  - Stopped it. The handler now uses `systemctl try-restart`.
- **Two plugin errors in `slurmd`'s log:**
  - PMIx: the library wasn't on the node. `pmix` is now installed on nodes.
  - The HTTP parser: never built. Per Slurm's docs, only `slurmrestd` needs it, and we don't use it. `CommunicationParameters=disable_http` in `slurm.conf`, so the daemons don't answer HTTP, and the error is gone.
- **Two more preview blind spots:** `slurmd`'s start and the NVIDIA key import ran only for real. Fixed. `test_roles.py` now also requires a reason for any task that runs only for real.

### 4b. `slurm.conf` with the GPU type and HTTP off, on both machines
- Applied (`20261021-171704-apply.log`). `slurmctld` restarted. Controller tests: 23 pass, 1 skipped.

### 4c. `slurm_node` on douglas1
- **The first apply blocked new SSH logins to douglas1** (`20261021-173221-apply.log`).
  - The firewall task used a template as a parameter *name*, which Ansible doesn't expand, so it failed. By then the task before it had already sent cluster-network traffic into the new, empty zone.
  - New logins got "No route to host", firewalld's reject. Existing sessions kept working.
  - Fixed through the spare session: `firewall-cmd --zone=cluster --add-service=ssh` and `--add-port=6818/tcp`, runtime only. Logins worked again.
- **Fix in the role:** SSH, `slurmd` and the `srun` ports are opened first, then the traffic is routed to the zone.
  - New code test: no templated parameter names in any role. It flags the old task.
  - New live tests: the node's ports, and that the running and saved firewall rules match.
- Second apply (`20261021-173918-apply.log`): "Done and settled". A new admin login works.
  - The node was resumed from the earlier drain: `scontrol update nodename=douglas1 state=resume`.
- **Test jobs waited forever (`QOSGrpBillingMinutes`):** the test customers had no credit. That's billing working.
  - Granted 50 test credits each (`TEST-CREDIT-2026-10-21-c0001` and `-c0002`, SOP-211).
  - The tests now fail at once, with the fix in the message, if test credit runs out.
- **The new live tests found that `pam_slurm_adopt` never ran.** A test user with no job logged in to douglas1.
  - password-auth's account part ends with `sufficient pam_localuser.so`. Pulled into sshd with `include`, that ends the check for every local user, before `pam_slurm_adopt`.
  - Now a `substack` (`20261021-180346-apply.log`).
  - Only test users exist, so no customer could have used this.
- **Then every login with a job was refused** ("no active jobs on this node").
  - Found with `pam_slurm_adopt log_level=debug5` (by hand, for one attempt; the next apply put the line back) and the audit log.
  - SELinux keeps sshd (`sshd_t`) from the job steps' sockets in `/var/spool/slurmd` (`var_spool_t`) and from `slurmstepd` (`unconfined_service_t`).
  - I briefly switched off the hiding of SELinux denials (`semodule -DB`, then `-B`) while looking. The denials that mattered weren't hidden ones.
  - New SELinux module `cluster_pam_slurm_adopt`, adapted from the example in Slurm's `pam_slurm_adopt` documentation. Built and loaded by the role (`20261021-182032-apply.log`).
- Test fixes found along the way:
  - Slurm 26.05 gives job cgroups opaque names, not `job_<id>`.
  - Adopted logins land in the job's `step_extern`.
  - Job-step lines in `slurmd.log` aren't `slurmd` errors.
  - `sinfo` adds `(S:0)` to the GPUs and shows "completing" for a few seconds after a job.
- **`./cluster test --live -k test_slurm_node`: 16 of 16 pass.** They cover:
  - `slurmd` running and enabled, with no plugin errors
  - the node up with all 10 GPUs, matching `nodes.yml`
  - the firewall: ports open to the cluster network only, rules permanent
  - one-GPU and two-GPU jobs see exactly their GPUs
  - a job gets 10 threads and 20 GB per GPU
  - jobs can't see another customer's processes, and can't reach the internet or the admin proxy
  - finished jobs are recorded with their GPUs and billing units
  - admins log in without a job; a customer without a job is refused; a customer with a job gets in, lands inside the job, and causes no SELinux denials
  - the SELinux module is loaded

## 5. Billing with real jobs (SOP-161)
- New live tests, `tests/live/test_billing_jobs.py`:
  - exact charges, against a calculation from `rates.yml` made independently of the billing code
  - running jobs charged every hour and finally once
  - the monthly cross-check
  - running out of credit mid-job: the 10-minute grace, the job's `USR1` warning, new jobs waiting, no kill over the limit, the stop at the new limit, and the grace being charged
- **The first run found that hourly billing had failed on every real job:** `cluster-billing: job record 15106908804199296000 isn't tracked`, exit 2.
  - **Cause:** Slurm 26.05's job record IDs (`sacct -D` `DBIndex`) are above 2^63. The ledger's `job_charges.db_index` was a signed `BIGINT`. `INSERT IGNORE` let MariaDB clamp the value to 2^63−1 instead of refusing it, so the record couldn't be found to charge.
  - **What it affected:** one clamped tracking row (job 22, nothing charged). The ledger had no charge entries at all, so no money was recorded wrongly. The hourly timer had been failing since the first real job, about 18:00; `./cluster health` would have flagged it after the next timer run.
  - **Fix:**
    - `db_index BIGINT UNSIGNED`
    - schema version 2, with a migration that changes the column and drops clamped rows holding no money (it stops for a person if one holds any)
    - strict SQL mode, and `INSERT ... ON DUPLICATE KEY` instead of `INSERT IGNORE` (also for storage readings)
  - **New ledger database tests** (21 in all): a 26.05 ID kept exactly and charged, two big IDs stay two jobs, a too-big ID refused rather than clamped, and both migration paths.
  - **Applied to anton** (`20261021-184326-apply.log`): the real ledger is migrated (column unsigned, version 2, the clamped row gone). Hourly billing then charged every one of today's test jobs.
  - `cluster-billing check 2026-10`: 27 finished jobs checked, the ledger agrees with Slurm.
- `./cluster health` now also checks munge and slurmd on compute nodes, and on GPU nodes that every GPU is there with no Xid, fallen-off-the-bus or PCIe hardware errors since boot (SOP-171).
- **Real-job billing tests, `tests/live/test_billing_jobs.py`: 4 of 4 pass.**
  - An earlier run was cut off when the session ended. The test's clean-up had already run: c0002's credit was back, with each test adjustment paired with its "-back" entry, and no jobs were left.
  - The grace test then failed once, because of a bug in the test itself: it read Slurm's first "None" reason, given before the scheduler had looked at the job. Slurm's records showed that job never started. Fixed to wait for `QOSGrpBillingMinutes`.
  - The full grace run then passed (697 s), confirming each step: time limit cut to now + 10 minutes, the `USR1` warning delivered, new jobs held for credit, no kill by Slurm over the limit ("safe", as Slurm's docs say), a TIMEOUT stop at the new limit, and the grace minutes charged.

## 6. Plan for the rest of the session (user away; "push forward", option A for shared software)
1. Base user environment on the login node and GPU nodes: compilers, Python 3.12, common libraries, Apptainer, `module`, a welcome message, and customers' temporary files kept in their own space.
2. Shared software in `/cluster/software` (option A): a PyTorch environment and a matching container image, built by a script in the repo, with module files.
3. Per-job private `/tmp` and `/dev/shm` on douglas1's new 4 TB NVMe (D5).
4. Login node: per-user CPU and memory limits for customers (anton has 31 GB of RAM and runs the billing database and Slurm controller), and customers kept off the office network and the cluster's admin services.
5. A third test customer added with the real onboarding commands (SOP-210's live proof), with room for software tests.
6. New-user tests: installing software, containers, first jobs, common mistakes.
7. User guide, SOPs, code index, then a full test run.

Not without the user: reboots (no BMC yet), the package mirror (tens of GB), the one-hour full-load GPU test (someone near the machine), SSH lockdown (1.6), alerts (D34), off-site backups (D39).

## 7. What customers get (SOP-143, new)
- New role `user_environment` (every machine, tag `user_environment`; the login-node parts on the new `login_nodes` group, which is anton).
  - 56 packages: compilers and build tools, git and git-lfs, Python 3.12 with headers, common libraries, everyday tools, Apptainer with squashfuse, and environment-modules. All 56 names checked against the repositories first.
  - Unprivileged containers work as they are: user namespaces are on (126,812 allowed), and `/dev/fuse` is open to users.
- Applied to both machines (`20261021-210858-apply.log`, 805 s, mostly package installs): "Done and settled".
- **Also in this step: Slurm's task prolog sets `TMPDIR=/tmp` in jobs.** On the login node, a customer's `TMPDIR` is their own `~/.tmp`, and `sbatch` passes the login session's environment on to the job, so without this a job would write its temporary files into the home folder over NFS.
- `tests/live/test_user_environment.py`: 12 of 12 on the first run.
- **Proof run** (`--tags user_environment`):
  1. Undid the settings on both machines: profile script, welcome message, module path and Apptainer bind. Also removed two harmless packages, `tree` and `screen`. I left compilers alone, since the NVIDIA driver's DKMS rebuilds need them.
  2. The tests failed, 9 failures, as expected.
  3. One apply (`20261021-213607-apply.log`) fixed everything. 12 of 12 again.

## 8. Shared software, option A (SOP-144, new)
- **Decided with the user:** shared software on the RAID (`/cluster/software`), read over NFS by every node, free for customers. Customers add their own packages on top.
- **Design point:** each stack is a conda environment (Miniforge), not a Python venv. A venv made from a venv doesn't see the first venv's packages, so a customer's `python -m venv --system-site-packages` on top only works with a real base interpreter underneath.
- **Pins** (`config/versions.yml`):
  - Miniforge 26.7.2-1, with conda-forge's published SHA-256
  - PyTorch 2.14.1 for CUDA 13.0, with torchvision 0.29.1
  - `pytorch/pytorch:2.14.1-cuda13.0-cudnn9-runtime`, pinned by digest
- **Why these:**
  - 2.14.1 is the newest PyTorch release. It has builds for CUDA 12.6, 13.0 and 13.2: 12.6 can't run on Blackwell (it needs 12.8 or newer), and 13.2 needs a newer driver than R580, which tops out at CUDA 13.0.
  - torchaudio is left out: its newest build, 2.11.0, is tied to an older torch.
- **Code:**
  - `clusterlib/software.py` (13 code tests) and the root tool `clusterlib/software_cli.py` (`cluster-software`)
  - role `shared_software`, and `./cluster software list | build | check`
- **Built:** `./cluster software build` (`20261021-213507-software.log`), 270 s, about 8 GB downloaded.
  - Sizes: Miniforge 816 MB, PyTorch 5.5 GB, the image 3.1 GB.
  - Module files: `pytorch/2.14.1-cu130` (the default) and `miniforge/26.7.2-1`, plus the README.
- **`./cluster test --live -k test_software`: 12 of 12 on the first run.**
  - PyTorch on a Blackwell GPU (capability 12.0, results match the CPU's), and two GPUs talking over NCCL.
  - `import torch` in a job takes 1.6 s over NFS.
  - A customer's venv on top sees both stacks, their own versions win, and it stays under 200 MB.
  - The shared conda makes environments in the customer's folder, used in a job.
  - The image runs with its GPU.
  - Customers can't change the shared software or pip-install into it.
- **Proof run:**
  1. Deleted the Miniforge stack, every module file and the README. `check` found 2 problems.
  2. One `build` rebuilt Miniforge from the pinned, checksum-checked installer, and republished everything (`20261021-214138-software.log`).
  3. `check` passed, and the tests are 12 of 12 again.

  PyTorch and the image weren't re-downloaded for the proof (7 GB over the shared office network). Their first build already came straight from the config.

## 9. Job scratch: each job's private /tmp on the new NVMe (SOP-132, new)
- New role `scratch`: douglas1's 4 TB NVMe (`/dev/disk/by-id/nvme-Fanxiang_S660_4TB_26070712629000533`), checked empty with `wipefs -n`, formatted XFS once, mounted at `/scratch` with `nofail`.
- **Slurm's per-job namespace:**
  - **First try, `namespace/linux` with `namespace.yaml`: slurmd stopped.** "fatal: serializer_required: could not find plugin for application/x-yaml". Our Slurm build has no YAML serializer, because `libyaml-devel` wasn't there at build time; only `serializer/url_encoded` was built. douglas1 was out of service for about 15 minutes.
  - **Switched to `namespace/tmpfs`** (formerly `job_container/tmpfs`), with a plain two-line `job_container.conf`. To-do: rebuild Slurm with `libyaml-devel` and `json-c-devel`.
- **Then the important finding: `/scratch` was mounted only inside sshd's own mount namespace.**
  - sshd runs with `ProtectProc=invisible` (customer process hiding, SOP-142), so systemd gives it a mount namespace of its own: a one-way copy of the host's ("shared:217 master:1").
  - `ansible.posix.mount` with `state: mounted` mounts in the namespace Ansible runs in. Over SSH, that's sshd's. So the host (PID 1) and slurmd never saw `/scratch`, and jobs' `/tmp` would have gone to the system disk.
  - douglas1's `/cluster` NFS mount only worked because it was made through a connection opened before sshd got the setting. anton's mounts predate it too.
  - **Fix in the `scratch`, `shared_storage` and `storage` roles:** `fstab` with `state: present`, then the systemd mount unit (`systemctl start scratch.mount`), which PID 1 mounts on the host. The quota remount runs under `nsenter -t 1 -m`.
  - New code test: no other mount states, and shell mounts need `nsenter`. It flags the four old tasks.
  - The live tests now check mounts in PID 1's and slurmd's namespaces.
  - The copy stuck in sshd's namespace was unmounted by hand first.
- `TmpDisk` for douglas1: 3,800,000 MB (`/scratch` is 3,813,585 MB), so jobs can use `--tmp`.
  - The controller learned the new figure before the old slurmd re-registered, so the node was drained once for "Low TmpDisk". Resumed. This is noted in SOP-155; it's not automated, because the same reason reports real hardware loss.
- **Logins into a job saw the host's `/tmp`.** SELinux denied sshd reading the job's namespace file (`nsfs_t`), giving `setns(-1) failed`. The module, now version 1.1, has the three rules from Slurm's `namespace/tmpfs` example. I tried it by hand first, then applied it through the role (`20261021-224055-apply.log`).
- **Tests:** `test_scratch` 7 of 7, `test_slurm_node` 16 of 16.
- **Proof run:**
  1. Unmounted `/scratch` on the host and removed its `fstab` line and `job_container.conf`. Three tests failed.
  2. That also exposed a weak test: "on the scratch disk" compared `/tmp` with `/scratch`, which are the same disk when it's unmounted. It now compares with the device itself, and failed as it should.
  3. One apply (`20261021-225233-apply.log`) restored everything. 7 of 7 again.

## 10. The login node for customers (SOP-145, new)
- New role `login_node` (the `login_nodes` group, which is anton).
  - **Limits for each customer user:** 4 cores, 6 GB, no swap, 512 processes, as a systemd slice drop-in for their UID. anton is also the head node, with 31 GB of RAM for the billing database and the Slurm controller.
  - **Network rules for customer UIDs** (nftables `cluster_login_egress`, loaded at boot):
    - allowed: the internet, SSH and slurmd on the compute nodes, Slurm here, and answers on their own connections (`srun`'s output from the nodes needs that)
    - blocked: the office network, every other private range and link-local, the rest of the cluster network, and this machine's admin services (proxy, MariaDB, Cockpit, NFS, mail)
  - SSH tunnels run as the customer, so the rules cover them too.
- The first preview failed safely: in the account data the username field is `name`, not `username`. Fixed.
- Applied (`20261021-230720-apply.log`). **`test_login_node`: 14 of 14**, including:
  - tunnels refused to the office network and to MariaDB
  - the guide's Jupyter recipe (`ssh -J` into your own job's node) landing inside the job
  - a 7 GB program in a customer's session stopped with exit 137
- **Proof run:**
  1. Disabled the rules and removed the slice drop-ins. 14 failures, but two tests still passed: "office network" and "private ranges". Nothing listens on those ports anyway, so failing to connect proves nothing.
  2. Those tests now require the rules' own reject counters to go up. With the rules gone they failed, as they should.
  3. One apply (`20261021-231401-apply.log`) restored everything. 14 of 14.
- **Found for COP-44:** the compute nodes' customer rules allow the whole cluster network. If douglas1's BMC gets a cluster-network address, customers' jobs could reach its login page. Added to the to-do: block BMC addresses for customers on the compute nodes, or give the BMCs a network of their own (Albert's call in COP-44). The login node's rules already block them.

## 11. Onboarding proved live, and a new customer's first day (SOP-210)
- **`customer add --test` and test users added to the commands.** A test customer takes the lowest free code (c0001–c0099). Its users take the lowest free `zzNN`, with a key the next apply generates.
  - The sandbox the command tests run in now fakes `sudo` and has its own test-key folder (`CLUSTER_TEST_KEY_DIR`). Otherwise a sandbox test would have run a real `sudo ssh-keygen` into `/etc/cluster/test-keys`; the real keys were checked untouched. Code tests: 132.
- **The real commands, as for a real customer:**
  1. `./cluster customer add --test --name "Test customer 3" --billing-email test-c0003@localhost --storage-gb 25 --max-gpus 2 --yes` gave c0003: committed, IDs given out (group 20002), applied, settled (`20261021-232146-customer.log`, 830 s).
  2. `./cluster user add c0003 --name "Test user 5" --email test-zz05@localhost --manager --yes` gave zz05: committed, uid 10104, key generated, applied, settled (`20261021-233555-user.log`, 847 s).
  3. `./cluster credits grant c0003 50 --ref TEST-CREDIT-2026-10-21-c0003`, then the sync: limit 0 → 60,000 billing-minutes.
- **`tests/live/test_new_user.py`: 17 of 17**, as zz05 through a real SSH login with their own key:
  - looking around: credit, prices, storage, GPUs, modules, their folders
  - getting things in: scp, downloading on the login node, a package on top of the shared PyTorch
  - jobs: a guide-style training job with a checkpoint trap, with its cost showing in `myusage`; an interactive `srun --pty`; a job array; project data read in a job
  - mistakes, each refused or stopped with its reason: no GPU, over 7 days, Windows line endings, `--mem=0`, more GPUs than the company may hold (waits with the reason), `pip install` in a job (fails fast, no internet), and over the memory limit (stopped, `OUT_OF_MEMORY`)
  - The first run had 15 of 17. Both failures were display quirks: `sacct` cut the state to "OUT_OF_ME+", and the pty echoed a NUL as "^@".
- A plain `#!/bin/bash` job script can use `module`, so the guide doesn't need `#!/bin/bash -l`.
- **The customers' guide rewritten** for what exists now: copying files in, the login node's limits, each job's private `/tmp` and `--tmp`, interactive sessions and arrays, the shared software and packages on top, conda, containers, compiling, Jupyter and VS Code, internet on the login node only, and the mistakes. Compute is billed per second, which the code always did; the guide said per minute.
  - Published at `/cluster/docs/guide.md` (`20261021-235247-apply.log`).

## 12. SOP-155 proof run, health additions, and the whole suite (2026-10-22, just after midnight)
- **`./cluster health`** now also checks:
  - `/scratch` as the host sees it (PID 1's mount namespace), and its fill level
  - that the shared software is complete (`cluster-software check`)
  - that the login node's customer rules are loaded
  - (from earlier) munge, slurmd, all 10 GPUs, and no GPU or PCIe errors since boot

  Code tests 133. All healthy.
- **SOP-155 proof run on douglas1**, with the node idle and the spare SSH session open:
  1. Undid everything `slurm_node` sets up:
     - slurmd stopped and disabled
     - the `pam_slurm_adopt` block, the substack and `pam_systemd`
     - the cluster firewall zone
     - `gres.conf`, `job_container.conf`, the task prolog and slurmd's drop-in
     - the SELinux module, and PMIx

     A new admin login still worked.
  2. `test_slurm_node`: 12 failures, as expected, including "a customer without a job is refused".
  3. One apply (`20261022-001658-apply.log`), "Done and settled": admin login fine, slurmd active, node idle, with no drain this time.
  - SOP-155's undo steps were brought up to date with today's additions.
- **The whole suite** (`20261022-002727-test.log`, 1169 s):
  - code tests: **133 of 133**
  - live tests: **197 of 198**. The one failure was the old per-user GPU-limit test in `test_slurm.py`, running for the first time with a GPU node up. It read Slurm's initial "None" reason, the same race as the grace test. Fixed, and it passes.
- `docs/status.md` (where things stand) and the to-do's "Before the first real customer" list written for the user.

## 13. The weekly test run had never worked (SOP-191)
- I started `cluster-tests-weekly.service` by hand, to see the suite run under systemd rather than in my session. It failed at once: `Failed to locate executable /home/papaya/cluster/cluster: Permission denied` (status 203/EXEC).
  - The audit log: `avc: denied { execute } … scontext=init_t tcontext=user_home_t`. SELinux won't let systemd execute a file in a home folder.
  - The timer was installed on 2026-10-20 and hadn't fired yet, so the first Sunday run would have failed silently. `./cluster health` would have shown it, but no alerts exist yet.
- **Fix:** `ExecStart=/usr/bin/python3 <repo>/cluster test`. Python is a system program, which systemd may run, and it reads the script. Applied (`20261022-004918-apply.log`).
- New live test `tests/live/test_schedule.py`: every cluster timer is enabled with a next run, and each service starts a program systemd may execute (not `user_home_t`). It failed on the old unit and passes on the new one.
- Then started the weekly run under systemd for real; its result is below.
- **First weekly run under systemd** (`20261022-005421-test.log`): it worked, with 133 of 133 code tests and 199 of 200 live tests.
  - The one failure: `test_a_grant_counts_once_and_raises_the_slurm_limit` was off by one billing-minute. It read c0002's balance before an hourly run, and that run also charged c0002's finished test jobs.
  - Fixed: the limit is compared with the balance after the run, and the price comes from `rates.yml` instead of the placeholder 0.50.
- **Second run under systemd** (`20261022-011522-test.log`): **133 of 133 code tests, 200 of 200 live tests.** Result=success, so `./cluster health` shows the weekly timer green.
- Guide: Hugging Face caches in the project folder, and `HF_HUB_OFFLINE=1` in jobs. Published.

## 14. 10 GPUs on douglas1, so 5 cores + 24 GB per GPU (2026-10-22)
- The user: douglas1 stays at 10 GPUs, with no 11th. The share had been sized for 11 (5 cores + 20 GB), which left about 50 GB of RAM unused. Raised to **24 GB per GPU** ("yea raise to 24gb"). That's 1.5× each 16 GB GPU; the machine is 256 GB against 160 GB of GPU memory, 1.6×.
- **Caught before it shipped: billing.** The partition's fixed `TRESBillingWeights="CPU=1,Mem=0.5G,GRES/gpu=10"` with `MAX_TRES` would have billed 24 GB as 12 units against the GPU's 10, so every standard job would have cost 20% more than the GPU price.
  - The weights are now computed from the share in `slurm.conf.j2`: `CPU=1,Mem=0.416666G,GRES/gpu=10`. The memory weight is rounded down, so a full share's memory (9.99998 units) never bills above its GPU; Slurm truncates the billing number.
- **Changed:**
  - `slurm_mem_per_gpu_mb` 24576 and `slurm_billing_units_per_gpu` 10 (`slurm_common` defaults)
  - `gpu_slots` 10, so `MemSpecLimit` leaves the system 11,240 MB
  - `job_submit.lua` and `DefMemPerGPU` follow the setting
  - the welcome message, the guide, the design (Q4 changed), the decisions log, SOP-152/153/155, the status page and the `rates.yml` comment
- **New tests:**
  - Slurm's weights make a full share of CPUs, memory or a GPU the same units, never more (live)
  - `rates.yml` and Slurm agree on units per GPU (code)
  - the welcome message states the real share
  - the out-of-memory test goes 1 GB over the share
- **Applied** (`20261022-045153-apply.log`): "Done and settled", node idle, no drain. Slurm shows `DefMemPerGPU=24576`, the new weights, and `MemSpecLimit=11240`.
- **Tests:** code 134/134; live `test_slurm` 42/42, `test_slurm_node` 17/17 (a job's cgroup holds 24 GB; a standard job bills 10 units), `test_new_user` 17/17, `test_user_environment` 12/12, `test_billing_jobs` 4/4.
