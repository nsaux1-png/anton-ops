# Machines

Recorded 2026-10-17.

## anton (head node)

| | |
|---|---|
| Hardware | Supermicro, H11SSL-i motherboard |
| OS | Rocky Linux 9.8, kernel 5.14.0-687.57.1.el9_8 |
| CPU | AMD EPYC 7551P, 32 cores / 64 threads, 1.2–2.0 GHz |
| RAM | 32 GB, plus 16 GB swap |
| Boot disk | 256 GB NVMe (FIKWOT FN501Pro): `/` 70 GB, `/home` 152 GB, `/boot` 1 GB (LVM, volume group `rl`) |
| Data disks | 2× 4 TB HGST Ultrastar (`sda`, `sdb`) in an mdadm RAID1 mirror `md0` (name `anton:0`), XFS, 3.7 TB, mounted at `/raiddrive`. Empty as of 2026-10-18. |
| GPU | None (ASPEED onboard video only) |
| Network | `eno1` 192.168.5.200/22 (1 Gb, upstream); `eno2` 172.16.50.1/24 (1 Gb, cluster network) |
| SELinux | Enforcing |
| Services | firewalld, chronyd and sshd active; IP forwarding off |
| Repos | BaseOS, AppStream, Extras, EPEL |

## douglas1 (GPU compute node)

| | |
|---|---|
| OS | Rocky Linux 9.8 |
| CPU | AMD EPYC 7663, 56 cores / 112 threads |
| RAM | 251 GB |
| Disk | 256 GB NVMe (FIKWOT FN501Pro) only: `/` 70 GB, `/home` 163 GB |
| GPUs | 10× NVIDIA GeForce RTX 5070 Ti (GB203). **No NVIDIA driver installed yet.** |
| Network | `enp66s0f1np1` 172.16.50.11/24 (cluster network); `enp66s0f0np0` down; `enp72s0f3u2u3c2` 172.16.99.201/24 (USB interface, purpose unknown) |
| Internet | None: no default route, and DNS servers are unreachable |
| Secure Boot | Disabled |
| SELinux | Enforcing |
| Services | firewalld and chronyd active |

## Users present on both machines

| User | UID |
|---|---|
| papaya | 1000 |
