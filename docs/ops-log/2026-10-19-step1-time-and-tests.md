# 2026-10-19: Build step 1.5 (time sync) and the live test suite

## Why
- **Time:** build plan 1.5. munge needs synchronized clocks, and job times are billed.
- **Tests:** the user, 2026-10-19: tests must be thorough, written with each step, and run on the cluster, not on GitHub.

## Before (read-only)
- anton's `/etc/chrony.conf`: `server _gateway iburst`, synced through the office router.
- douglas1's `/etc/chrony.conf`: the same file, but douglas1 has no gateway, so it had **no time source** (`chronyc tracking`: Stratum 0, reference time 1970).
- douglas1: Secure Boot **disabled** (`mokutil --sb-state`); kernel `5.14.0-687.57.1.el9_8`; 4 GB swap.

## Done
By Claude Code (a session on anton as papaya), while the user was away. They'd asked for the build to continue.
1. **`./cluster test`:** code tests in `tests/code` (the old `tests/test_cluster.py` moved there), live tests in `tests/live`, `-k` to filter. `./cluster apply` now runs the code tests first.
2. **Live tests for the finished steps:** `test_hosts`, `test_admin_proxy`, `test_customer_network`, `test_time`.
   - The first run found two bugs in the tests, not the cluster:
     - on anton, `getent hosts anton` returns its IPv6 address first (nss `myhostname`), so the test now uses `getent ahostsv4`
     - squid leaves query strings out of its log, so the proxy test now tags the URL path instead
   - A third bug, in parsing `chronyc` output, was fixed after the time role went in.
3. **The `time` role:** anton keeps the router, adds the Rocky pool, serves `172.16.50.0/24` and keeps serving if every upstream is lost (`local stratum 10`). douglas1 uses only `server anton`. `ntp` is open in anton's `cluster` zone.
4. **`./cluster apply --yes`** ("Done and settled", log `20261019-230129-apply.log`). douglas1 synced to anton within seconds (stratum 3, offset about 0.1 ms).
5. **Proof run:**
   - Restored both machines' original `chrony.conf` from the backups, removed `ntp` from the zone and restarted chronyd.
   - `./cluster apply --yes` rebuilt it ("Done and settled", log `20261019-230654-apply.log`).
   - `./cluster test --live -k test_time`: 4/4 passed.

## Verified
`./cluster test`: all code tests and all live tests pass (hosts, proxy, customer network, time).

## Follow-ups
None.
