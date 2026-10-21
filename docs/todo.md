# To do

**Owner** says who does it: **you** = a person at a terminal or in a web UI; **Claude** = can be done from Claude Code once access is in place.
Tick items off here and commit, so the history shows when each was done.

## Next up (2026-10-19): NVIDIA driver on douglas1
The full step-by-step plan is [`build-plan.md`](build-plan.md).
- [x] **Claude:** Ansible + `./cluster` with run logging (2026-10-19, SOP-001, SOP-101). `/etc/hosts` managed too (SOP-102).
- [x] **Claude:** Admin web proxy on anton, and network limits for customer accounts on douglas1 (2026-10-19, SOP-103, SOP-104).
- [ ] Package mirror: moved to build plan phase 3, before the second node or the first customer.
- [ ] **Claude:** Read-only checks on douglas1: Secure Boot, BIOS (Above 4G decoding, Resizable BAR), kernel headers.
- [x] **Claude:** douglas1's memory sticks: 8× 32 GB DDR4-2133, all 8 slots full (2026-10-19). Upgrade in Linear COP-43.
- [ ] **Claude:** SOP + Ansible role for the NVIDIA driver; install on douglas1; `nvidia-smi` shows all 10 GPUs; persistence mode on.
- [ ] **Claude + you:** Full-load test of all 10 GPUs (D47), watching temperatures and power.

## When douglas1 is back (it hung at boot after the NVIDIA driver install, 2026-10-19)
- [ ] **Albert:** douglas1's BMC port onto the cluster switch, a fixed address from anton, and its login recorded, so its console and power button can be reached remotely (Linear COP-44, 2026-10-20; Albert's opinion asked there). anton's own BMC is probably already on that switch, asking for an address.
- [x] **you:** Someone at douglas1's console got it running on 2026-10-20 (up since 16:17).
- [x] **Claude:** Read douglas1's logs (2026-10-21, ops log 2026-10-21-douglas1-back). The driver loads fine; the 10-19 reboot stopped before any boot started, probably hardware around GPU `0000:01:00.0`. The failed restart left no log.
- [ ] **you:** Who was at the console on 10-20, and what did they see and change (screen messages, GPU `0000:01:00.0` reseated, BIOS settings)?
- [x] **Claude:** A persistent journal on every machine (2026-10-21, SOP-106), so a failed boot leaves a log.
- [ ] **Claude:** douglas1's kernel options into Ansible, so they're recorded and checked. Drop `initcall_debug` at the next planned reboot.
- [ ] **Claude:** A supervised reboot test, the self-recovering way (hardware watchdog `sp5100_tco` plus a one-time GRUB entry), only after COP-44.
- [ ] **Claude:** `slurmd -C`: set `slurm_real_memory_mb` in `config/nodes.yml`, and the GPU type (`slurm_gpu_type`) from what NVML reports.
- [ ] **Claude:** A full `./cluster apply`: accounts, logins, `/cluster` over NFS and the Slurm packages on douglas1. Keep a second SSH session to douglas1 open while sshd changes.
- [ ] **Claude:** Wire in `slurm_node` (prepared, untested: slurmd, NVML, `pam_slurm_adopt`, hidden job processes). Test logins with and without a job, as admin and as a test user.
- [ ] **Claude:** GPU job tests, the skipped per-user GPU limit test, real-job charging, running out of credit → grace → stop, and the GPU check program on every GPU.
- [ ] **you + Claude:** The one-hour full-load test (D47).

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
