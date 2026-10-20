# SOP-105: Time sync
**Status:** proved 2026-10-19 ([ops log](../ops-log/2026-10-19-step1-time-and-tests.md))

## Purpose
Every machine needs the same time. munge (Slurm's authentication) rejects messages from a machine whose clock is off, and job times are billed.
- **anton** follows the office router (`_gateway`) and the public Rocky pool. It serves time to the cluster network, and keeps serving from its own clock if every upstream source is lost (`local stratum 10`).
- **Compute nodes** have no internet, so they follow anton only.

Role: `ansible/roles/time`. anton's firewall opens `ntp` in the `cluster` zone only (`ansible/roles/firewall`).

## When
Automatically on every `./cluster apply`.

## Before you start
The preconditions of SOP-001.

## Steps
1. `./cluster apply --dry-run`, then check the `/etc/chrony.conf` diff.
2. `./cluster apply`, and answer `y`.

## Expected result
- On douglas1, `chronyc -n tracking` shows `Reference ID : AC103201 (172.16.50.1)`, `Leap status : Normal` and a system time offset well under 0.1 s.
- On anton, `chronyc -n tracking` shows `Leap status : Normal`.

## Checks
- **Automated:** `./cluster test --live -k test_time` covers both machines in sync, compute nodes following anton, `ntp` open only to the cluster network, and chronyd enabled everywhere.
- **By hand:** `chronyc -n sources` on any machine.

## Undo
Each change leaves a backup next to the file (`/etc/chrony.conf.<pid>.<time>~`). Copy it back and `sudo systemctl restart chronyd`. On anton, also `sudo firewall-cmd --permanent --zone=cluster --remove-service=ntp && sudo firewall-cmd --reload`. Remove `time` from `ansible/site.yml`, or the next `apply` puts it back.

## Notes
- Before this, douglas1 had no working time source (`Stratum 0`): its config pointed at a gateway it doesn't have.

## History
- 2026-10-19: first version.
  - Proof run: both machines' original `chrony.conf` restored and `ntp` removed from the zone, then rebuilt with one `./cluster apply` ("Done and settled"). The time tests passed again.
