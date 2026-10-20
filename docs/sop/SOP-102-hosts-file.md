# SOP-102: `/etc/hosts` on every machine
**Status:** proved 2026-10-19 ([ops log](../ops-log/2026-10-19-step1-ansible.md))

## Purpose
Every machine can reach every other by name on the cluster network. Ansible's `hosts` role writes `/etc/hosts` from `config/nodes.yml`, so the file is the same everywhere.

## When
Automatically on every `./cluster apply`. Run it yourself after adding a machine to `config/nodes.yml`.

## Before you start
- The preconditions of SOP-001.
- The machine is in `config/nodes.yml` with its `cluster_ip`.

## Steps
1. Edit `config/nodes.yml` if needed, and commit.
2. `./cluster apply --dry-run`, and check the `/etc/hosts` diff.
3. `./cluster apply`, and answer `y`.

## Expected result
Every machine's `/etc/hosts` reads:
```
# Managed by Ansible (ansible/roles/hosts) from config/nodes.yml.
# Local edits are overwritten by the next ./cluster apply.
127.0.0.1   localhost localhost.localdomain localhost4 localhost4.localdomain4
::1         localhost localhost.localdomain localhost6 localhost6.localdomain6

# Cluster network 172.16.50.0/24
172.16.50.1 anton
172.16.50.11 douglas1
```

## Checks
- **Automated:** `./cluster test --live -k test_hosts`.
- `./cluster apply --dry-run` → "Nothing to change."
- On anton, `getent hosts douglas1` → `172.16.50.11 douglas1`.
- `ssh douglas1 getent hosts anton` → `172.16.50.1 anton`.

## Undo
- Each change leaves a backup next to the file, e.g. `/etc/hosts.387089.2026-10-19@22:12:12~`. Copy it back.
- Also remove `hosts` from `ansible/site.yml`, or the next `apply` rewrites the file.

## History
- 2026-10-19: first run on anton and douglas1. Commit 5634478.
  - Proof: the second run found "Nothing to change".
  - Drift test: a line added to douglas1's file by hand was shown by the preview and removed by `apply`, which then reported "Done and settled".
