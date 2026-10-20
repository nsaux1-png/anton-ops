# SOP-104: Network limits for customer accounts on compute nodes
**Status:** proved 2026-10-19 ([ops log](../ops-log/2026-10-19-step1-proxy-and-egress.md)). Loading at boot is checked at the next reboot (driver install, SOP-111).

## Purpose
Customers' jobs can't reach the internet (user's decision, 2026-10-19). On each compute node, customer accounts (UID 2000 and up, from `customer_uid_min` in `config/nodes.yml`) can reach only the cluster network. That rules out:
- the internet
- the office network
- the BMC link
- the admin proxy on anton

The rule is applied per account by the node's own firewall (an nftables table, `cluster_egress`), so it covers everything a job runs, including containers. Root and admin accounts (UID below 2000) aren't limited. Packets not sent by a customer's process, such as the kernel's own replies, pass untouched.

Role: `ansible/roles/egress`. The files on the node:
- `/etc/nftables/cluster-egress.nft`: the rules
- `cluster-egress.service`: loads them at boot, before the network

## When
Automatically on every `./cluster apply`. Every new compute node gets it when it's added to the `compute` group in `config/nodes.yml`.

## Before you start
The preconditions of SOP-001.

## Steps
1. `./cluster apply --dry-run`, then check the diff.
2. `./cluster apply`, and answer `y`.

## Expected result
`sudo nft list table inet cluster_egress` on the node shows:
- the `output` chain sending `meta skuid >= 2000` to the `customer` chain
- the `customer` chain allowing `lo` and `172.16.50.0/24`, rejecting the proxy port, and rejecting everything else

## Checks
**Automated:** `./cluster test --live -k test_customer_network`. It covers the internet, the office network, every other local network on the node (such as the BMC link), the proxy, the cluster network, and admins not being limited.

By hand, on the compute node: `setpriv` runs a command as a made-up customer UID, so no account is needed.
```
C="sudo setpriv --reuid=10001 --regid=10001 --clear-groups"
$C curl -sS -m 5 -o /dev/null -x http://anton:3128 https://rockylinux.org/   # → Connection refused
$C curl -sS -m 5 -o /dev/null http://172.16.99.200/                          # → No route to host
$C timeout 5 bash -c 'echo > /dev/tcp/172.16.50.1/22' && echo reachable     # → reachable
systemctl is-enabled cluster-egress                                          # → enabled
```
The reject counters in `sudo nft list table inet cluster_egress` go up with each blocked attempt.

## Undo
On the node:
```
sudo systemctl disable --now cluster-egress
sudo rm -f /etc/systemd/system/cluster-egress.service /etc/nftables/cluster-egress.nft
sudo systemctl daemon-reload
```
Then remove `egress` from `ansible/site.yml`, or the next `apply` puts it back.

## Notes
- The BMC link (172.16.99.0/24, douglas1's internal USB network to its own BMC) can be reached from douglas1, so without this rule a customer job could reach the BMC's login. The check above confirms that it's blocked.
- Customers download data and software on anton, the login node, into their shared folders (`slurm-design.md` section 3).

## History
- 2026-10-19: first version, commit 3716289.
  - Proof run: everything undone on douglas1, then rebuilt with one `./cluster apply`, which ended "Done and settled". All checks passed again.
