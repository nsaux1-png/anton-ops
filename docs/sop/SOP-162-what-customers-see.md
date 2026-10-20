# SOP-162: What customers see about their own billing
**Status:** proved 2026-10-20 ([ops log](../ops-log/2026-10-20-phase7-billing.md))

## Purpose
Four commands on the login node, each showing **only the caller's own** data (`slurm-design.md` section 9). Each takes `--json`, and `--month YYYY-MM` where it applies.

| Command | Shows |
|---|---|
| `credits` | Available credit, unpaid charges, and each credit batch with its expiry date. **Managers** (`role: manager`) also get the month's statement. |
| `myusage` | Jobs started this month: run time, size, and what each cost. Managers see all their customer's users; others see only their own jobs. |
| `prices` | Their prices now and every earlier price, each with the date it took effect. |
| `mystorage` | Current use, their limit, this month's peak and what it costs. |

**How they're kept private:** each command runs `sudo -n /usr/local/sbin/cluster-billing customer-view …`. That's the **only** thing customers may run with sudo (`/etc/sudoers.d/50-cluster-customer-views`). The tool takes who's asking from sudo itself (`SUDO_USER`), never from the command line, and refuses anyone who isn't a customer.

## Checks
- **Automated:** `./cluster test --live -k WhatCustomersSee`. Each test customer sees their own customer; only managers get the statement; usage shows only the user's jobs; prices and storage work; a normal SSH login has the commands; a non-customer is refused.
- `./cluster test --live -k test_customers_can_run_only_their_own_views_with_sudo`

## History
- 2026-10-20: first version.
