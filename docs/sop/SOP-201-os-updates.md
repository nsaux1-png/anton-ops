# SOP-201: OS updates on compute nodes
**Status:** proved 2026-10-19 on douglas1 ([ops log](../ops-log/2026-10-19-step2-gpu-driver.md))

## Purpose
`./cluster upgrade` brings the compute nodes up to date (`ansible/upgrade.yml`):
- one node at a time
- every package updated, except version-locked ones (the NVIDIA driver, SOP-111), which stay put
- a reboot only when `dnf needs-restarting -r` says one is needed (new kernel or core libraries)
- the NVIDIA driver is rebuilt for a new kernel automatically by DKMS

The head node (anton) isn't included. Rebooting it stops the whole cluster, so it gets its own procedure.

**Before Slurm runs jobs**, this is safe at any time. **Once it does**, the playbook must first drain the node and wait for its jobs. That gets added with Slurm (build plan phase 6), before customers.

## When
Monthly, or when a security update matters. Not while customers' jobs are running, until the drain step exists.

## Steps
1. `./cluster upgrade --dry-run` lists what would be updated.
2. `./cluster upgrade` (or `--limit <node>`), and answer `y`.
3. `./cluster test --live` afterwards.

## Expected result
"Done and settled": a second preview finds nothing left to update. A node that needed it was rebooted and came back.

## Checks
- `./cluster test --live`: everything still passes. That includes the GPUs, the driver being built for the running kernel, and the customer network limits loaded after the reboot.
- `ssh <node> uname -r` shows the newest installed kernel.

## Undo
Updates aren't rolled back package by package. If a new kernel misbehaves, boot the previous one: `sudo grubby --set-default /boot/vmlinuz-<previous>`, then reboot. dnf keeps the last three kernels.

## History
- 2026-10-19: first run on douglas1. 15 packages updated, including kernel `5.14.0-687.57.1` → `5.14.0-687.58.1`. It rebooted, and the second preview found nothing left to update. The customer network limits loaded at boot (`./cluster test --live -k test_customer_network`: 7/7).
