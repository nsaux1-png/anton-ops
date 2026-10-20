# 2026-10-19: Build step 1 begins: Ansible, `./cluster`, `/etc/hosts`

## Why
Build order step 1 (plan section 18). The user said go ahead on 2026-10-19.

## Done
By Claude Code (a session on anton as papaya).

1. **Read-only checks** on both machines:
   - `id`: papaya is in `wheel` on both.
   - `sudo -n true`: the temporary passwordless sudo works on both.
   - `/usr/bin/python3` is 3.9 with the dnf and SELinux bindings on both. The `python3` in papaya's PATH is Miniconda's 3.14.
   - Read `/etc/hosts` on both.
   - douglas1 has no default route, so no internet.
   - `/var/log/cluster-ops` was `root:root 755`, and the 01 bootstrap log in it was world-readable.
   - `known_hosts` has douglas1 both by name and by IP, with the same key.
   - On anton: `dnf list --available ansible-core ansible-collection-ansible-posix ansible-collection-community-general`.
2. **Installed Ansible** by writing `scripts/bootstrap/02-install-ansible.sh` and running it. It installed ansible-core 2.14.18 (AppStream), ansible.posix 1.6.2 and community.general 7.5.0 (EPEL). It also made `/var/log/cluster-ops` `root:wheel 2770` and its logs `0640`.
3. **Proof run of SOP-101:** removed the three packages and ran the script again, which installed them. A third run reported `SKIP` for both parts.
4. **Wrote the code:**
   - `./cluster` with `ping`, `apply` and `runs`
   - `config/nodes.yml`
   - `ansible/`: the Ansible config, `site.yml` and the `hosts` role
   - `tests/test_cluster.py`, whose 8 tests pass

   It was committed (5634478) before any `apply`.
5. **`./cluster ping`:** both machines returned `SUCCESS`.
6. **`/etc/hosts`:** ran `./cluster apply --dry-run`, then `./cluster apply --yes`. `/etc/hosts` was rewritten on both machines from the template:
   - anton kept the same entries, reordered under a header.
   - douglas1 gained entries for anton and douglas1.

   Backups were left as `/etc/hosts.<pid>.<time>~`.
7. **Proof run of SOP-102:** a second `apply` found "Nothing to change". Drift test: I appended `10.9.9.9 drift-test` to douglas1's `/etc/hosts`; `apply` showed and removed it, then reported "Done and settled".
8. **douglas1's memory**, from `sudo dmidecode -t memory` (read-only):
   - 8× 32 GB DDR4-2133 RDIMM (Samsung M393A4K40BB0-CPB)
   - all 8 slots full; the board's maximum is 4 TB

   At the user's request I added Linear **COP-43**, "Add 128 GB RAM to douglas1", noting that the sticks have to be replaced.

## Run logs (`/var/log/cluster-ops/`)
- `20261019-221036-02-install-ansible.log` (install), `-221058-` (proof reinstall), `-221106-` (re-run, all `SKIP`)
- `20261019-221144-ping.log`
- `20261019-221146-apply.log` (dry run), `-221202-apply.log` (apply), `-221222-apply.log` (nothing to change), `-221229-apply.log` (drift test)

## Verified
- `./cluster ping` returns `exit=0` for both machines.
- `getent hosts` resolves both names on both machines (SOP-102 checks).
- `/usr/bin/python3 -m unittest discover -s tests -v`: 8 tests, all `ok`.

## Follow-ups
- The user decided that compute nodes get no internet. The next step is the package mirror on anton, not a NAT gateway (`docs/decisions.md`).
- New open question: Miniconda in papaya's home on both machines.
