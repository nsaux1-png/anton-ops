# SOP-142: How customers log in
**Status:** proved on anton 2026-10-20 ([ops log](../ops-log/2026-10-20-phase5-users.md))

## Purpose
- **SSH keys only, and only the ones we set.** Customers' keys are in root-owned files (`/etc/ssh/authorized_keys/<user>`), written from `customers.yml`. A key a customer adds to `~/.ssh/authorized_keys` is ignored, so they can't add keys or share their account.
- **No password logins for customers**, through a `Match Group <customer codes>` block in `sshd_config`. Admin accounts aren't affected: their password setting waits for the user's decision (build plan 1.6).
- **Test users (`zz*`) can log in only from anton itself and the cluster network**, never from outside.
- **Customers see only their own processes.** sshd, and each user's own service manager (`user@.service`, used by `systemd-run --user`), run with systemd's `ProtectProc=invisible`. Mounting `/proc` with `hidepid` isn't supported on Rocky 9. Without the setting on `user@.service`, `systemd-run --user` was a way around it; the tests caught that.
- Customers have no sudo, except to see their own billing (SOP-162).
- **fail2ban** (role `fail2ban`, on anton): an address that fails to log in over SSH 5 times in 10 minutes is blocked for an hour by a firewalld rule. Local addresses and the cluster network are never blocked; the office network isn't exempt, because it's shared.

Role: `ansible/roles/customer_access` (every machine). The `sshd_config` block is checked with `sshd -t` before it's saved. sshd restarts keep open sessions (`KillMode=process`).

## When
Automatically on every `./cluster apply`. A new or suspended user's key file changes on the next apply.

## Steps
1. `./cluster apply --dry-run`
2. `./cluster apply`

## Checks
- **Automated:** `./cluster test --live -k Logins` covers:
  - logging in with the right key
  - a key the customer added doesn't work
  - a suspended user can't log in
  - the sshd settings for customers and for test users from outside
  - no sudo
  - only their own processes are visible, through a login and through `systemd-run --user`
- **By hand:** `sudo sshd -T -C user=<user>,host=x,addr=<ip> | grep -E 'passwordauthentication|authorizedkeysfile|pubkeyauthentication'`

## Undo
`sudo rm -rf /etc/ssh/authorized_keys /etc/systemd/system/sshd.service.d /etc/systemd/system/user@.service.d`, delete the `# BEGIN/END customer access` block from `/etc/ssh/sshd_config`, then `sudo sshd -t && sudo systemctl daemon-reload && sudo systemctl restart sshd`. Then remove the role from `ansible/site.yml`.

## History
- 2026-10-20: fail2ban added, with live tests (`-k BruteForce`): the jail is on; a ban becomes a firewall rule and lifts again; the cluster network is exempt. Proof run: removed and rebuilt with one apply.
- 2026-10-20: first version, applied to anton.
  - The first test run found `systemd-run --user` processes seeing everyone's processes; fixed with the setting on `user@.service`.
  - Proof run: everything removed and rebuilt with one apply. The tests passed again.
