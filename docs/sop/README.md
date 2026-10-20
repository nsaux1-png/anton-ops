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
