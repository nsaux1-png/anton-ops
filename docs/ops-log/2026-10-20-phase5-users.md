# 2026-10-20: Build phase 5 (customers, users and logins) on anton

## Why
Build plan phase 5, so Slurm (phase 6) has accounts to work with. douglas1 is down, so only anton is done; its accounts come with the next full apply.

## Done
By Claude Code (a session on anton as papaya), while the user was away.
1. **`clusterlib/config.py`:** loads and checks `customers.yml`, gives out IDs into `uids.yml` (never reused), picks usernames and customer codes, and makes the text edits that keep comments. 38 code tests.
2. **`config/customers.yml`** with the fixed test customers:
   - c0001: zz01 (manager), zz02, zz04 (always suspended), with a 1 GiB limit
   - c0002: zz03
3. **`./cluster` changes:**
   - **Before every apply:** check the config, give out IDs (and commit them), make test keys.
   - **New commands:** `user add/set/suspend/resume/remove/list` and `customer add/set/list`, with 10 end-to-end code tests in a sandbox.
4. **Roles:**
   - `accounts` on every machine
   - `customer_storage` on anton: folders, plus the `cluster-quota` tool for the group and project limits
   - `customer_access` on every machine: root-owned keys, the sshd `Match` rules, and `ProtectProc=invisible` for sshd
5. **`tests/live/test_customers.py`:** 20 tests (accounts, folders, limits, quota escapes, logins, hidden processes).

## Problems found and fixed on the way
- **The command tests had a side effect.** One older test ran the real `./cluster apply` against stand-ins. With the new config step it gave out the test accounts' IDs **in the real repo** and committed them (d0e1d48, "Give out IDs: c0001=20000, zz01=10100, …", pushed). It also made the test users' SSH keys in `/etc/cluster/test-keys/`.
  - The IDs and keys are exactly what the real apply would have made, so they're kept.
  - All command tests now run in a sandbox copy of the repo (`tests/code/sandbox.py`) and can't touch the real one.
- **First preview failed:** the standard shell files can't be copied into home folders that don't exist yet. Fixed: that step waits in a first-run preview.
- **First test run (5 failures on anton):**
  - three were test bugs: reading a file's group without sudo, and a command that's meant to fail
  - **suspended users' expiry was day 0**, which some tools read as "never expires". Now it's day 1 (2 Jan 1970).
  - **real escape:** `systemd-run --user` processes run under the user's own service manager (`user@.service`), not sshd, and could see everyone's processes. Fixed by giving `user@.service` the same `ProtectProc=invisible`.
- After the fixes: all anton tests pass. The 11 douglas1 checks error because douglas1 is down.

## Proof run
- **Removed everything:** the four test users and two groups, their folders, the group and project limits, `/etc/ssh/authorized_keys`, the sshd block and drop-ins, the `user@` drop-in and `cluster-quota`; then restarted sshd.
- **Rebuilt:** `./cluster apply --yes --limit anton` reported "Done and settled". Log: `20261020-002039-apply.log`.
- `./cluster test --live -k test_customers`: no failures on anton.

## Run logs
`20261020-001447-apply.log` (first apply), `20261020-001748-apply.log` (fixes), `20261020-002039-apply.log` (proof), plus the matching `*-test.log` files.

## Follow-ups
- douglas1: accounts and the login rules with the next full `./cluster apply`. The sshd restart there must be done with a safety connection open.
- The admin password question (build plan 1.6) is still open, so admin password logins are unchanged.
