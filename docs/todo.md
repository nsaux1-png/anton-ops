# To do

**Owner** says who does it: **you** = a person at a terminal or in a web UI; **Claude** = can be done from Claude Code once access is in place.
Tick items off here and commit, so the history shows when each was done.

## Next up (2026-10-19): NVIDIA driver on douglas1
- [ ] **Claude:** Ansible + `./cluster` with run logging (first item of section 4). Every following step runs through it.
- [ ] **Claude:** anton as gateway, so douglas1 can download packages (section 4).
- [ ] **Claude:** Read-only checks on douglas1: Secure Boot, BIOS (Above 4G decoding, Resizable BAR), kernel headers, which memory sticks are installed (for a possible RAM upgrade).
- [ ] **Claude:** SOP + Ansible role for the NVIDIA driver; install on douglas1; `nvidia-smi` shows all 10 GPUs; persistence mode on.
- [ ] **Claude + you:** Full-load test of all 10 GPUs (D47), watching temperatures and power.

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
- [ ] **you:** Buy a 10 Gb card for anton plus a Cat6a cable to douglas1 (Linear COP-42). Then **Claude:** configure the link and move cluster traffic onto it.

## 4. Foundations (Claude, once sudo is in place)
- [ ] Install Ansible; set up the playbook skeleton, inventory (`nodes.yml`), and the `./cluster` command with run logging.
- [ ] Manage `/etc/hosts` on all machines from the inventory.
- [ ] Time sync: anton as chrony server, nodes as clients.
- [ ] anton as gateway: IP forwarding plus NAT on `eno1`, cluster network outbound only. Verify douglas1 reaches the internet.
- [ ] Firewall zones on anton (upstream vs cluster network).
- [ ] NFS: export from `/raiddrive` (home + shared software) to the cluster network; mount on nodes.
- [ ] `users.yml` with fixed UID/GIDs, applied to every machine.
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
