# SOP-103: Admin web proxy on anton, and anton's cluster-network firewall zone
**Status:** proved 2026-10-19 ([ops log](../ops-log/2026-10-19-step1-proxy-and-egress.md))

## Purpose
Compute nodes have no route to the internet. Root and admin accounts on them reach the web through a proxy on anton (squid):
- It listens on the cluster network only.
- Every request is logged.
- Customer accounts on the nodes are blocked from it by the node's own firewall (SOP-104).

anton's firewall treats traffic from the cluster network as its own zone, `cluster`, so services opened for the cluster never open on the upstream (office) network.

Roles: `ansible/roles/firewall` and `ansible/roles/admin_proxy` (anton), plus the proxy settings in `ansible/roles/egress` (compute nodes).

## When
Automatically on every `./cluster apply`. Use the proxy whenever an admin needs the internet on a compute node.

## Before you start
The preconditions of SOP-001.

## Steps
1. `./cluster apply --dry-run`, then check the diff.
2. `./cluster apply`, and answer `y`.

**Using the proxy:**
- On a compute node, admin login shells get `http_proxy` and `https_proxy` automatically (`/etc/profile.d/admin-proxy.sh`), so `curl`, `pip` and `git` over HTTPS work.
- `dnf` uses it through `proxy=` in `/etc/dnf/dnf.conf`.
- Under plain `sudo` the variables aren't passed on. Use `sudo -i`, or `sudo https_proxy=http://anton:3128 <command>`.
- Only web traffic goes through it (ports 80 and 443).

## Expected result
- anton: `squid` is active and listening on `172.16.50.1:3128` only.
- `firewall-cmd --get-active-zones` shows `cluster` (source `172.16.50.0/24`) and `public` (`eno1`, `eno2`).
- The `cluster` zone allows `ssh` and `squid`. The `public` zone is unchanged; squid isn't in it.

## Checks
- **Automated:** `./cluster test --live -k test_admin_proxy`. It covers everything below, including a tagged request that has to show up in squid's log.
- On anton: `sudo ss -ltn | grep 3128` → `172.16.50.1:3128` only.
- On anton: `sudo firewall-cmd --zone=cluster --list-all` → `sources: 172.16.50.0/24`, `services: squid ssh`.
- On douglas1, as an admin: `bash -lc 'curl -sS -o /dev/null -w "%{http_code}\n" https://rockylinux.org/'` → `200`.
- On douglas1: `sudo dnf -q repolist` lists the Rocky and EPEL repos.
- On anton: `sudo tail /var/log/squid/access.log` shows those requests, from `172.16.50.11`.

## Undo
On anton:
```
sudo systemctl disable --now squid
sudo dnf -y remove squid
sudo rm -rf /etc/squid /etc/systemd/system/squid.service.d
sudo systemctl daemon-reload
sudo firewall-cmd --permanent --delete-zone=cluster && sudo firewall-cmd --reload
```
On each compute node:
```
sudo sed -i '/^proxy=/d' /etc/dnf/dnf.conf
sudo rm -f /etc/profile.d/admin-proxy.sh
```
Then remove the roles from `ansible/site.yml`, or the next `apply` puts everything back.

## Notes
- The request log is `/var/log/squid/access.log`, rotated by the squid package's logrotate settings. Its retention follows plan D38.
- Ansible prints `Collection ansible.posix does not support Ansible version 2.14.18`. The firewalld module works on this version; the warning comes from the collection's declared minimum.

## History
- 2026-10-19: first version, commit 3716289.
  - Proof run: everything undone on both machines (squid removed, zone deleted, node files removed), then rebuilt with one `./cluster apply`, which ended "Done and settled". All checks passed again.
