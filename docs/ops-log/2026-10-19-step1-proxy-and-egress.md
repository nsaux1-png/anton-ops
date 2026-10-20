# 2026-10-19: Build steps 1.3–1.4: admin proxy, cluster firewall zone, customer network limits

## Why
The user's rule, 2026-10-19: customers' jobs mustn't reach the internet, but admins must be able to install things on douglas1, through a proxy. The user said "continue with step 3 - go".

## Before (read-only checks)
- **anton:**
  - firewalld has a single zone, `public`, holding both `eno1` (upstream) and `eno2` (cluster), with services `cockpit`, `dhcpv6-client` and `ssh`.
  - IP forwarding is off. squid isn't installed.
- **douglas1:**
  - firewalld is active, with `public` holding the cluster port and the BMC link. The only nft table is `firewalld`.
  - `dnf` has no proxy and no route to the internet.
  - The only account with UID ≥ 1000 is papaya (1000).
- **Found:** `cockpit` (a web admin console) is open on anton's upstream side. It's left unchanged pending the user's answer.

## Done
By Claude Code (a session on anton as papaya).
1. **Wrote the roles:**
   - `firewall` (anton): a zone called `cluster` for source `172.16.50.0/24`, with `ssh` and `squid` open
   - `admin_proxy` (anton): squid on `172.16.50.1:3128`, no cache, every request logged, plus a systemd drop-in so it starts after the network and restarts on failure
   - `egress` (compute nodes): the nftables table, its boot unit, `dnf`'s proxy setting, and the proxy variables for admin shells

   Added the `compute` group and the proxy and UID variables to `config/nodes.yml`.
2. **First preview failed:** the squid restart handler ran in preview before squid existed, so nothing was changed. I made the handler skip in that case (commit 3716289), and the second preview was clean, with 8 changes.
3. **`./cluster apply --yes`:** 16 changes, then "Done and settled". Log: `/var/log/cluster-ops/20261019-224343-apply.log`.
4. **Verified:**
   - squid listens only on `172.16.50.1:3128`, and the `public` zone is unchanged.
   - As an admin on douglas1, HTTPS through the proxy returned 200, and `dnf makecache` and `dnf repolist` worked.
   - squid's log shows the requests from `172.16.50.11`.
   - As a made-up customer (UID 10001, via `setpriv`):
     - proxy → refused
     - `1.1.1.1` → couldn't connect (no route)
     - BMC link `172.16.99.200` → rejected by the rule
     - anton's SSH port on the cluster network → reachable
5. **Proof run:**
   - Undid everything on anton: stopped and removed squid, deleted `/etc/squid` and the drop-in, deleted the `cluster` zone and reloaded.
   - Undid everything on douglas1: disabled the unit, removed the rules file, unit file and profile script, and removed `proxy=` from `dnf.conf`.
   - Checked it was all gone, then ran `./cluster apply --yes`: "Done and settled". Log: `20261019-224730-apply.log`.
   - Re-ran the checks: all as in step 4.

## Also this session
- **Independent plan review:** saved as `docs/reviews/2026-10-19-plan-review.md` and applied to the design (commit 45b7bfc and earlier).
- Removed `tests/__pycache__` from git and added `.gitignore`.
- **Read-only:** `sudo sshd -T` on anton shows `passwordauthentication yes` and `permitrootlogin without-password`, listening on all IPv4 and IPv6 addresses (anton has a public IPv6 address). Build plan 1.6 fixes this once the user confirms they log in with a key.

## Follow-ups
- The boot loading of `cluster-egress` gets checked at the driver-install reboot (SOP-111).
- User: whether Cockpit should stay open on the upstream network.
