# 2026-10-19: Hardware survey of anton and douglas1 (read-only)

## Why
To answer open questions D4, D5, D7 and D9 before deciding on hardware purchases. Nothing was changed on either machine.

## Commands
By Claude Code. Run on both machines (douglas1 over SSH):
```
ip -br link; ip -br addr
cat /sys/class/net/<port>/speed
sudo ethtool <port>                # supported link speeds
lspci; lsusb
sudo dmidecode -s baseboard-product-name
sudo dmidecode -t slot             # free PCIe / M.2 slots
lsblk -d -o NAME,SIZE,MODEL,TRAN
```
anton only: `ip neigh show dev eno1`, `ip route`, `rpm -q nut apcupsd`, `rpm -qf /etc/grafana/grafana.ini`, `systemctl is-active grafana-server`.

## Found
**anton** (Supermicro H11SSL-i)
- Network: two Intel `igb` ports, **1 Gb maximum**. `eno1` is upstream; `eno2` is the cluster network.
- `eno1` also has a **public IPv6 address** (`2600:6c82:…`). If the router allows incoming IPv6, anton can be reached from the internet directly, not only through IPv4.
- 5 free PCIe 3.0 slots: x8 SLOT1, SLOT3, SLOT5; x16 SLOT4, SLOT6.
- Storage: LSI SAS2308 HBA (SAS-2) holding the two 4 TB HGST drives.
- Only the router (192.168.4.1) was in the upstream neighbour table. That doesn't prove nothing else is on that network (D11 still open).
- No UPS on USB, no UPS software.
- **Grafana 10.2.6 is installed but inactive and disabled.** It wasn't installed by this project.

**douglas1** (ASRock Rack ROMED8-2T)
- Network: Broadcom BCM57416, **two 10 Gb copper ports (10GBASE-T)**. `enp66s0f1np1` is the cluster link, running at 1 Gb because anton's side is 1 Gb. `enp66s0f0np0` isn't cabled.
- `enp72s0f3u2u3c2` (172.16.99.201) is the BMC's virtual USB network link (AMI "Virtual Ethernet"). It's internal to the server, which answers D9.
- Disks: only the 256 GB NVMe system disk. **Free: M.2 slot `M2_1` and OCuLink ports `OCU1` and `OCU2`.**
- 10 NVIDIA GPUs visible on PCI (20 functions: GPU plus audio for each). No driver yet.

## Outcome
- Machine details updated in `docs/machines.md` and `docs/architecture.md`.
- Decisions recorded in `docs/decisions.md`: D4 (10 Gb card), D7 (no UPS), D47 (power is adequate). D9 is answered.
- Purchase tracked in Linear: **COP-42 "Expand cluster network to 10 Gb"** (project Purchasing Tracking List).
- New open question: what to do with the Grafana package on anton.
