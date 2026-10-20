# SOP-101: Install Ansible on anton
**Status:** proved 2026-10-19 ([ops log](../ops-log/2026-10-19-step1-ansible.md))

## Purpose
Ansible makes every change to the machines. It's installed on anton only. The other machines just need SSH and Python, which Rocky already has.

## When
Once, when setting up anton or a replacement head node. Safe to re-run.

## Before you start
- You're on anton with your admin account (`id` shows `wheel`) and can use sudo.
- The repo is at `~/cluster`.
- anton can reach Rocky's AppStream repo and EPEL: `dnf -q repolist` lists `appstream` and `epel`.

## Steps
1. `sudo bash ~/cluster/scripts/bootstrap/02-install-ansible.sh`
2. `cd ~/cluster && ./cluster ping`

## Expected result
- Step 1 ends with `== Done.` On a re-run, both of its parts say `SKIP`.
- Versions installed on 2026-10-19:
  - ansible-core 2.14.18-3.el9_8.1 (AppStream)
  - ansible-collection-ansible-posix 1.6.2-1.el9 (EPEL)
  - ansible-collection-community-general 7.5.0-1.el9 (EPEL)
- Step 2: `SUCCESS` for every machine.

## Checks
- `rpm -q ansible-core ansible-collection-ansible-posix ansible-collection-community-general`
- `stat -c '%U:%G %a' /var/log/cluster-ops` → `root:wheel 2770`
- `./cluster ping` → `exit=0`

## Undo
`sudo dnf remove ansible-core ansible-collection-ansible-posix ansible-collection-community-general`. The log folder stays.

## Notes
- Ansible and `./cluster` use the system Python (`/usr/bin/python3`, version 3.9), which has the dnf and SELinux bindings. On anton and douglas1, the `python3` in papaya's PATH is a Miniconda Python 3.14; it isn't used.
- dnf installs the newest versions available. If a later run gets different versions, record them here.

## History
- 2026-10-19: written and run. Proof run: removed the three packages, ran the script again (it reinstalled them), then once more (all `SKIP`). The script was committed in 5634478, just after these runs; their logs show the commit before it, bc309f7.
