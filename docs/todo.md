# To do

**Owner** says who does it: **you** = a person at a terminal or in a web UI; **Claude** = can be done from Claude Code once access is in place.
Tick items off here and commit, so the history shows when each was done.

## 1. Finish renaming anton (remove every "douglas1" that refers to this machine)
- [x] Hostname → `anton` (2026-10-17)
- [ ] **you:** Rename the RAID array from `douglas1:0` to `anton:0`. It's unmounted, so this is the right moment. Claude will give the exact commands.
- [ ] **you or Claude:** Search the root-only files in `/etc` for "douglas1". 23 files couldn't be read without sudo; needs sudo.
- [ ] **you:** Rename the SSH entry for 192.168.5.200 on your laptop(s) from douglas1 to anton.
- [ ] **you:** Check the router/DNS and other machines for a "douglas1" name pointing at anton's addresses (192.168.5.200 or 172.16.50.1).
- [ ] **you:** Decide the name for 172.16.50.11 in `/etc/hosts`: currently `douglas1_gpu`. That machine really *is* douglas1, so this line stays pointed at it; only the name is in question.
- Not to rename: `~/.ssh/known_hosts` "douglas1" (the real douglas1's key, checked), and `~/.bash_history` (old history).

## 2. Mount the RAID at /raiddrive
- [ ] **you:** Fix the typo in `/etc/fstab`: the UUID says `000658eb-Z151-…` but the real one is `000658eb-2151-…`. Then mount it. See `ops-log/2026-10-18-raiddrive.md`.
- [ ] **Claude:** Check what's on it (read-only) and record it.

## 3. Access
- [ ] **you:** Add the temporary passwordless sudo file on anton and on douglas1.
- [ ] **you:** Add anton's GitLab key to GitLab, create an empty project, and send Claude its address (and say whether it's gitlab.com or self-hosted).
- [ ] **Claude:** Connect this repo to GitLab and push.

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

## 9. Repeatable operations (Claude)
- [ ] `./cluster add-user`, `add-node`, `add-gpu`, `add-disk`, `apply`, `billing-report`, each documented in `docs/procedures/`.

## 10. Wrap-up
- [ ] **you or Claude:** Remove `/etc/sudoers.d/90-papaya-temp` from every machine.
