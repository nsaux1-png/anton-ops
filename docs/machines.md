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
| Network | `eno1` 192.168.5.200/22 (1 Gb, upstream; also has a public IPv6 address `2600:6c82:…`); `eno2` 172.16.50.1/24 (1 Gb, cluster network). Both are Intel `igb` ports, **1 Gb maximum**. |
| Free slots | 5 free PCIe 3.0 slots (x8: SLOT1, SLOT3, SLOT5; x16: SLOT4, SLOT6), checked 2026-10-19. Room for a 10 Gb card. |
| SELinux | Enforcing |
| Services | firewalld, chronyd and sshd active; IP forwarding off |
| Repos | BaseOS, AppStream, Extras, EPEL |

## douglas1 (GPU compute node)

| | |
|---|---|
| Hardware | ASRock Rack ROMED8-2T motherboard, with a BMC (remote management) |
| OS | Rocky Linux 9.8 |
| CPU | AMD EPYC 7663, 56 cores / 112 threads |
| RAM | 251 GB usable: 8× 32 GB DDR4-2133 RDIMM (Samsung M393A4K40BB0-CPB), all 8 slots full; board maximum 4 TB (checked 2026-10-19). Upgrade: Linear COP-43. |
| Disk | 256 GB NVMe (FIKWOT FN501Pro): `/` 70 GB, `/home` 163 GB. **Added 2026-10-20: a 4 TB NVMe** (Fanxiang S660, `nvme1n1`, PCI `0000:05:00.0`), first seen in the 15:46 boot. It's blank: no partitions yet (checked 2026-10-21). Its use (scratch, D5, and/or local software copies) is to be decided. Before: free M.2 slot `M2_1` and two OCuLink ports (`OCU1`, `OCU2`). |
| GPUs | 10× NVIDIA GeForce RTX 5070 Ti (GB203). **No NVIDIA driver installed yet.** |
| Network | Broadcom BCM57416, **two 10 Gb ports (10GBASE-T)**: `enp66s0f1np1` 172.16.50.11/24 (cluster network, running at 1 Gb because anton's side is 1 Gb); `enp66s0f0np0` not cabled. `enp72s0f3u2u3c2` 172.16.99.201/24 is the BMC's virtual USB network link (AMI "Virtual Ethernet"), internal between the server and its own BMC. |
| Internet | None: no default route, and DNS servers are unreachable |
| Secure Boot | Disabled |
| SELinux | Enforcing |
| Services | firewalld and chronyd active |

## Users present on both machines

| User | UID |
|---|---|
| papaya | 1000 |
