# To do

**Owner** says who does it: **you** = a person at a terminal or in a web UI; **Claude** = can be done from Claude Code once access is in place.
Tick items off here and commit, so the history shows when each was done.

## Before the first real customer (2026-10-22)
The cluster is ready for test customers end to end. These are what's left before real ones:
- [ ] **you:** How customers reach the login node from outside: a public address or port forward to anton, or another way. Then put the login address in `docs/user-guide.md`.
- [ ] **you:** Your SSH login to anton: key or password (build plan 1.6)? Password logins must be off before anton is reachable from the internet.
- [ ] **you:** Real prices (D29), what 1 credit is worth (D40), the terms (11.2), and a support contact for the guide.
- [ ] **you:** Where alerts go (D34). `./cluster health` checks everything, but doesn't tell anyone yet. The same decision covers Slurm's job emails: no mail program yet, so slurmctld logs `Configured MailProg is invalid`.
- [ ] **you:** Where off-site backups go (D39).
- [ ] **you + Albert:** The one-hour full-load test of all 10 GPUs (D47). Someone must be near the machine (heat, power).
- [ ] **you:** Q8, a separate login machine. Today customers log in to anton, which is also the head node. The login-node limits and rules (SOP-145) make that safer, not safe.
- [ ] **Claude:** Rebuild Slurm with `libyaml-devel` and `json-c-devel`, for `--json`/`--yaml` output (SOP-151). Not needed for customers.
- [ ] **Claude, with you around:** The package mirror on anton (build plan 3.1): tens of GB over the office network, before a second node or the first customer.

## douglas1 (2026-10-19 hang, back 2026-10-20)
- [ ] **Albert:** douglas1's BMC port onto the cluster switch, a fixed address from anton, and its login recorded, so its console and power button can be reached remotely (Linear COP-44, 2026-10-20; Albert's opinion asked there). anton's own BMC is probably already on that switch, asking for an address.
- [ ] **Albert / you (COP-44):** if the BMCs get cluster-network addresses, customers' jobs on the compute nodes could reach them, since the compute nodes' customer rules allow the whole cluster network (SOP-104). Either give the BMCs their own network, or Claude adds their addresses to the compute nodes' customer block list. The login node already blocks them (SOP-145).
- [ ] **you:** What Albert saw and changed at the console on 10-20: screen messages, GPU `0000:01:00.0` reseated, the 4 TB NVMe fitted, BIOS settings?
- [ ] **Claude:** After COP-44: a supervised reboot test, the self-recovering way (hardware watchdog `sp5100_tco` plus a one-time GRUB entry). Then drop `initcall_debug` (move it to `kernel_args_remove`), and the driver's proof runs (SOP-111).
- [x] **you:** Someone at douglas1's console got it running on 2026-10-20 (up since 16:17).
- [x] **Claude:** douglas1's logs read (2026-10-21): the driver loads fine; the 10-19 reboot stopped before any boot started, probably hardware around GPU `0000:01:00.0`.
- [x] **Claude, 2026-10-21:**
  - persistent journal (SOP-106) and kernel options (SOP-107)
  - accounts, logins, `/cluster` on douglas1
  - Slurm on douglas1 (SOP-155: `pam_slurm_adopt` with a substack and an SELinux module)
  - `slurmd -C` figures in `nodes.yml`
  - GPU jobs, real-job charging and the grace period, tested live
  - job scratch on the new NVMe (SOP-132)
  - what customers get (SOP-143), shared software (SOP-144), the login node (SOP-145)
  - onboarding proved live (SOP-210)
  - a new customer's first day tested (17 tests)

## 1. Finish renaming anton (remove every "douglas1" that refers to this machine)
- [x] Hostname → `anton` (2026-10-17)
- [x] RAID array renamed `douglas1:0` → `anton:0` (2026-10-18, `scripts/bootstrap/01-anton-fixes.sh`)
- [x] Searched all of `/etc` as root (2026-10-18). Only remaining hits: `/etc/hosts` (the real douglas1) and LVM's history files (see below).
- [ ] **you:** On your own computer, rename the saved SSH connection named "douglas1" that actually goes to anton (192.168.5.200), e.g. in `~/.ssh/config` or iTerm profiles.
- [ ] **you:** Check the router/DNS and other machines for a "douglas1" name pointing at anton's addresses (192.168.5.200 or 172.16.50.1).
- [x] `/etc/hosts` on anton: 172.16.50.11 is named `douglas1` again (was `douglas1_gpu`), 2026-10-18.
- Not to rename: `~/.ssh/known_hosts` "douglas1" (the real douglas1's key, checked); `~/.bash_history` (old history); `/etc/lvm/backup/rl` and `/etc/lvm/archive/` `creation_host = "douglas1"` (a record of where the OS disk's volumes were created at install time; it has no effect, and changing it would mean reinstalling).

## 2. Mount the RAID at /raiddrive
- [x] fstab UUID typo fixed and `/raiddrive` mounted (2026-10-18). See `ops-log/2026-10-18-raiddrive.md`.
- [x] Contents checked: empty (3.7 TB, 26 GB is filesystem overhead).

## 3. Access
- [x] Temporary passwordless sudo on anton and douglas1 (2026-10-18).
- [x] anton's GitLab key added to gitlab.com account @nicolas478 (2026-10-18).
- [x] Repo pushed to https://gitlab.com/nicolas478/anton-ops (private); every commit now pushes automatically (2026-10-18).
- [x] Empty private repo `nsaux1-png/anton-ops` created on GitHub; anton's key (`~/.ssh/id_ed25519_github.pub`) added as a deploy key with write access (2026-10-19).
- [x] `origin` switched to GitHub and full history pushed; the post-commit hook now pushes there (2026-10-19).
- [ ] **you:** Archive or delete the old GitLab project `nicolas478/anton-ops`, and remove anton's key from the GitLab account.
- [x] GitLab removed from anton: `~/.ssh/id_ed25519_gitlab` key pair deleted, `gitlab.com` dropped from `~/.ssh/config` and `known_hosts` (2026-10-19). The key can no longer be used, but still delete it from the GitLab account (item above).

## 3b. Hardware
- [ ] **you:** RAM for douglas1 (Linear COP-43). All 8 slots hold 32 GB DDR4-2133 sticks, so this means replacing them, e.g. 8× 64 GB DDR4-3200 = 512 GB.
- [ ] **you:** Buy a 10 Gb card for anton plus a Cat6a cable to douglas1 (Linear COP-42). Then **Claude:** configure the link and move cluster traffic onto it.

## 4. Foundations (Claude, once sudo is in place)
- [x] Install Ansible; set up the playbook skeleton, inventory (`nodes.yml`), and the `./cluster` command with run logging (2026-10-19, SOP-001, SOP-101).
- [x] Manage `/etc/hosts` on all machines from the inventory (2026-10-19, SOP-102).
- [ ] Time sync: anton as chrony server, nodes as clients.
- [ ] ~~anton as gateway (NAT)~~ Dropped 2026-10-19: compute nodes get no internet. Instead: the admin proxy and customer network limits (Next up), plus a test that a job on douglas1 can't reach the internet.
- [ ] Firewall zones on anton (upstream vs cluster network).
- [ ] NFS: export from `/raiddrive` (home + shared software) to the cluster network; mount on nodes.
- [ ] `config/customers.yml` with generated `uids.yml` (fixed UIDs/GIDs), applied to every machine.
- [ ] munge key, distributed to every node.

## 5. GPU node (Claude)
- [ ] NVIDIA driver on douglas1 (RTX 5070 Ti / Blackwell needs NVIDIA's open kernel modules); `nvidia-smi` shows all 10 GPUs.
- [ ] Decide whether CUDA toolkit goes in shared software or users bring their own via conda/pip.

## 6. Slurm (Claude)
- [ ] Get Slurm packages (current stable from SchedMD, built with NVIDIA support).
- [ ] MariaDB + `slurmdbd` + `slurmctld` on anton.
- [ ] `slurmd` on douglas1 with GPUs as GRES and cgroup enforcement.
- [ ] Test jobs: CPU-only, 1 GPU, multiple GPUs; check limits are enforced.

## 7. Accounting and billing
- [ ] **you:** Decide rates (GPU-hour, CPU-hour, memory?) and account structure (per customer? per project?).
- [ ] **Claude:** Billing weights per partition; enforcement so unregistered users can't run jobs.
- [ ] **Claude:** `./cluster billing-report <month>`, giving usage per account as CSV.

## 8. Before onboarding customers
- [ ] **Claude:** Rebuild Slurm with `libyaml-devel` and `json-c-devel`, so it has its YAML and JSON serializers. That gives `--json`/`--yaml` output for scripts and users, and allows `namespace/linux`. Today only `serializer/url_encoded` is built (found 2026-10-21, SOP-151, SOP-132).
- [ ] **you:** Q10 (`slurm-design.md`): customers install their own software; we add only the base packages and Apptainer?
- [ ] **Claude:** Customers install their own software, with live tests (requirement 16):
  - as a test user on the login node: a venv plus `pip install`, then importing it inside a GPU job on douglas1, which has no internet
  - conda or micromamba in the home folder, used in a job
  - PyTorch (CUDA 12.8+ wheels) built once in a test user's home, then a GPU matrix multiply on every GPU in a job, every week. Rebuilt from scratch monthly, to avoid a few-GB download every week over the office network
  - Apptainer, if Q10 says yes: pull an image on the login node, run it in a job with `--nv`
  - an install over the storage limit fails with "Disk quota exceeded" and leaves the account usable
  - a job that tries to `pip install` gets a clear network error
  - the test customers' 1 GB storage limit is too small for this; a bigger limit for one of them
- [ ] SSH hardening on anton: key-only logins, no root login, fail2ban.
- [ ] Back-up plan for the accounting database and `/raiddrive`.
- [ ] Onboarding procedure and `./cluster add-user`, tested end to end.
- [ ] Test customers `c0001`/`c0002` with `zz` users, and `./cluster test`: code tests on every push (GitHub Actions), live tests weekly (systemd timer). See `slurm-design.md` section 11.

## 9. Repeatable operations (Claude)
- [ ] `./cluster add-user`, `add-node`, `add-gpu`, `add-disk`, `apply`, `billing-report`, each documented in `docs/sop/`.

## 10. Wrap-up
- [ ] **you or Claude:** Remove `/etc/sudoers.d/90-papaya-temp` from every machine.

## 11. Later
- [ ] **Claude:** WireGuard VPN on anton for admin logins, then admin SSH only through it and the cluster network (`slurm-design.md` section 3, Q3). Test the VPN and a way back in (console or BMC) before switching off direct admin logins.
