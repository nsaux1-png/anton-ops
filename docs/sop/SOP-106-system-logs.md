# SOP-106: System logs kept on disk
**Status:** proved 2026-10-21 ([ops log](../ops-log/2026-10-21-douglas1-setup.md))

## Purpose
Every machine keeps its system log (the systemd journal) on disk, in `/var/log/journal`. After a crash or a failed boot, `journalctl -b -1` then shows what happened.

Rocky 9 keeps the journal in memory unless that folder exists. On 2026-10-21 neither machine had it, so douglas1's failed restart on 2026-10-19 left nothing to read ([ops log](../ops-log/2026-10-21-douglas1-back.md)).

Role: `ansible/roles/journal` (every machine). It:
- sets `Storage=persistent` in `/etc/systemd/journald.conf.d/cluster.conf`
- restarts journald and moves the in-memory journal to disk (`journalctl --flush`)
- gives the folder the read access systemd sets at boot, so admins (group `wheel`) can read it without sudo

journald's own size limit applies: 10% of the filesystem, at most 4 GB. rsyslog's `/var/log/messages` is unchanged.

## When
Automatically on every `./cluster apply`. A new machine gets it with its first apply.

## Steps
1. `./cluster apply --dry-run`
2. `./cluster apply`

To apply only this part: `./cluster apply --tags journal`.

## Checks
- **Automated:** `./cluster test --live -k Journal` checks that, on every machine:
  - the setting is on
  - journal files exist on disk
  - a test message reaches the files on disk
  - admins can read the journal without sudo
- **By hand, after a reboot:** `journalctl --list-boots` lists more than one boot, and `journalctl -b -1` shows the previous one.

## Undo
1. `sudo rm /etc/systemd/journald.conf.d/cluster.conf`
2. `sudo mv /var/log/journal /var/log/journal.old` (the old logs stay in that folder).
3. `sudo systemctl restart systemd-journald`
4. Remove the role from `ansible/site.yml`.

## History
- 2026-10-21: first version, applied to anton and douglas1. Proof run: undone on both, the tests failed, one apply fixed it.
