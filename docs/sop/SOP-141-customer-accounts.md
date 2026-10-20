# SOP-141: Customer accounts, folders and storage limits
**Status:** proved on anton 2026-10-20 ([ops log](../ops-log/2026-10-20-phase5-users.md)). Compute nodes get the accounts when douglas1 is back.

## Purpose
Turn `config/customers.yml` into real accounts, on every machine:
- **Groups:** one per customer. The group name is the customer code (`c4821`), with a GID from `config/uids.yml` (20000 and up).
- **Users:**
  - the same UID everywhere (10100 and up), given out once and never reused
  - the customer's group as their **only** group
  - no password (`!!`), so SSH keys only
  - an empty name field: real names stay in `customers.yml`, never in `/etc/passwd`
- **Suspended or removed users:** shell `/sbin/nologin`, account expired on 2 Jan 1970, SSH key removed.

On the storage server (anton):
- **Folders:**
  - `/cluster/home/<user>`: `0700`, with the standard shell files
  - `/cluster/projects/<customer>`: `root:<customer>`, `2770`. setgid, so new files belong to the customer.
- **Limits:** the `cluster-quota` tool sets each customer's **group quota** (the limit that's enforced and billed) and a **project quota** on the customer's folders (so `df` shows the limit). Sizes are GiB.

Roles: `ansible/roles/accounts` (every machine) and `ansible/roles/customer_storage` (anton). The data comes from `ansible/filter_plugins/cluster_accounts.py` → `clusterlib/config.py`.

## When
Automatically on every `./cluster apply`. Before each apply, `./cluster` checks `customers.yml` and refuses a broken file, gives out IDs to new customers and users (committing `uids.yml`), and makes SSH keys for new test users (`/etc/cluster/test-keys/`).

Day-to-day changes go through SOP-210 (`./cluster user …`, `./cluster customer …`).

## Steps
1. `./cluster apply --dry-run`
2. `./cluster apply`

## Expected result
`./cluster user list` and `./cluster customer list` show everyone with their IDs, and `getent passwd <user>` gives the same line on every machine.

## Checks
- **Automated:** `./cluster test --live -k test_customers`, which uses the fixed test accounts:
  - c0001: zz01 (manager), zz02, and zz04 (always suspended)
  - c0002: zz03

  It checks:
  - IDs and groups are the same everywhere; no passwords; no real names; suspended users expired
  - folder ownership and modes; customers can't see each other's folders, nor users each other's homes; the project folder is shared within the customer
  - group and project limits match the config, and folders carry the customer's project ID
  - `df` shows the limit; writing past it fails
  - **changing a file's project ID doesn't move it out of the limit**, and files can't be moved to another customer's group
- **Code tests:** `./cluster test --code` covers checking `customers.yml`, giving out IDs, defaults, usernames and the quota input.

## Undo (a test customer, say)
`sudo userdel <user>` and `sudo groupdel <code>` on every machine, `sudo rm -rf /raiddrive/cluster/home/<user> /raiddrive/cluster/projects/<code>`, and `sudo xfs_quota -x -c "limit -g bhard=0 <gid>" /raiddrive` (and `-p`). Then take them out of `customers.yml`. **Never take them out of `uids.yml`**: an ID is never reused.

## History
- 2026-10-20: first version, applied to anton.
  - Proof run: all test accounts, folders and limits removed, then rebuilt with one `./cluster apply --limit anton`. The tests passed again (nothing failed on anton; the douglas1 checks wait for douglas1).
