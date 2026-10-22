# Standard operating procedures

Every build step and routine task on the cluster is an SOP: a page here, plus a script or `./cluster` command that does the work. Plan section 17 explains how an SOP is made: a discovery run, then the written steps, then a proof run from a clean state with no improvising.

## Numbering
- **SOP-0xx:** how we work (running commands, logging)
- **SOP-1xx:** building the cluster, in build order
- **SOP-2xx:** routine operations (users, credits, maintenance)
- **SOP-3xx:** recovery (failures, restores)

## Index
| SOP | Title | Status |
|---|---|---|
| [SOP-001](SOP-001-cluster-command.md) | Running `./cluster` commands | proved 2026-10-19 |
| [SOP-101](SOP-101-install-ansible.md) | Install Ansible on anton | proved 2026-10-19 |
| [SOP-102](SOP-102-hosts-file.md) | `/etc/hosts` on every machine | proved 2026-10-19 |
| [SOP-103](SOP-103-admin-proxy.md) | Admin web proxy on anton; cluster-network firewall zone | proved 2026-10-19 |
| [SOP-104](SOP-104-customer-network-limits.md) | Network limits for customer accounts on compute nodes | proved 2026-10-19 (boot loading checked at next reboot) |
| [SOP-105](SOP-105-time.md) | Time sync | proved 2026-10-19 |
| [SOP-106](SOP-106-system-logs.md) | System logs kept on disk | proved 2026-10-21 |
| [SOP-107](SOP-107-kernel-options.md) | Extra kernel options | proved 2026-10-21 |
| [SOP-110](SOP-110-package-repos.md) | Package repositories | applied 2026-10-19 |
| SOP-111 | NVIDIA driver | ◐ driver installed and tested (2026-10-21); written with the proof runs, after douglas1's BMC (COP-44) |
| [SOP-130](SOP-130-shared-storage.md) | Shared storage: quotas, `/cluster`, NFS | proved on anton 2026-10-20; douglas1 2026-10-21 |
| [SOP-141](SOP-141-customer-accounts.md) | Customer accounts, folders and storage limits | proved on anton 2026-10-20; douglas1 2026-10-21 |
| [SOP-142](SOP-142-customer-logins.md) | How customers log in | proved on anton 2026-10-20; douglas1 2026-10-21 |
| [SOP-151](SOP-151-build-slurm.md) | Build Slurm | proved 2026-10-20 |
| [SOP-152](SOP-152-slurm-controller.md) | Slurm controller, database and shared configuration | proved on anton 2026-10-20 |
| [SOP-153](SOP-153-job-rules.md) | Job-size rules (`job_submit.lua`) | proved 2026-10-20 |
| [SOP-154](SOP-154-slurm-accounts.md) | Slurm accounts and limits | proved on anton 2026-10-20 |
| [SOP-161](SOP-161-billing.md) | Billing and credits: how it works | proved on anton 2026-10-20 |
| [SOP-162](SOP-162-what-customers-see.md) | What customers see about their own billing | proved 2026-10-20 |
| [SOP-171](SOP-171-health.md) | Cluster health at a glance (`./cluster health`) | first version 2026-10-20 |
| [SOP-181](SOP-181-backups.md) | Backups | proved 2026-10-20 (off-site still to come) |
| [SOP-191](SOP-191-weekly-tests.md) | The weekly test run | timer installed 2026-10-20 |
| [SOP-155](SOP-155-slurm-nodes.md) | Slurm on GPU nodes | applied and tested on douglas1 2026-10-21; proof run to do |
| [SOP-201](SOP-201-os-updates.md) | OS updates on compute nodes (`./cluster upgrade`) | proved 2026-10-19 on douglas1 |
| [SOP-210](SOP-210-customers-and-users.md) | Adding and changing customers and users | commands tested in a sandbox |

## Template
Copy this for a new SOP, named `SOP-NNN-short-name.md`:

```markdown
# SOP-NNN: Title
**Status:** draft | proved YYYY-MM-DD (link to the ops-log entry)

## Purpose
What this does and why.

## When
When to run it, and who runs it.

## Before you start
Preconditions, with the commands that check them.

## Steps
Numbered. Exact commands to copy; nothing to improvise.

## Expected result
What the output looks like when it worked.

## Checks
Commands that prove it worked. These join the test suite.

## Undo
How to reverse it.

## History
Date: what changed, commit, ops-log link.
```
| [SOP-211](SOP-211-credits.md) | Top-ups, refunds, adjustments, balances, statements | tested 2026-10-20 |
| [SOP-301](SOP-301-restore.md) | Checking backups restore, and restoring for real | check proved 2026-10-20 |
