# 2026-10-19: Build phase 2: douglas1 OS update and NVIDIA driver. ⚠️ douglas1 didn't come back from the driver reboot

## Why
Build plan phase 2. The user asked for the build to continue while they were away.

## 2.1 Read-only checks on douglas1
- **Secure Boot is disabled** (`mokutil --sb-state`), so the driver needs no module signing.
- **BIOS:** every GPU has a 16 GB prefetchable BAR mapped above 4 GB, so Above 4G decoding is on and Resizable BAR is in effect.
- **PCIe links** (`lspci -vv`, GPUs idle without a driver):
  - capable of 32 GT/s x16 (Gen5)
  - currently 2.5 GT/s, because idle GPUs slow their links down
  - wired **x8**, except `0000:01:00.0` at **x4**
  - EPYC 7663 tops out at Gen4
- **Software:**
  - `nouveau` loaded
  - CRB disabled
  - 15 updates pending, including kernel `687.58.1`
  - kernel-devel present for the installed kernels
  - NVIDIA's repo reachable through the admin proxy
- **Driver branches** in NVIDIA's RHEL 9 repo: 560 to 615. According to https://docs.nvidia.com/datacenter/tesla/drivers/supported-drivers-and-cuda-toolkit-versions.html:
  - R580: long-term support branch, end of life June 2028, CUDA 13
  - R595: production branch, end of life March 2027
  - R610: new-feature branch

  **Chose R580, open kernel modules (`580-open`), version 580.105.08.** NVIDIA's repo key fingerprint is `610C 7B14 E068 A878 070D A4E9 9CD0 A493 D42D 0685`. The key is committed in the role.

## 2.2a OS update (`./cluster upgrade`, new command, SOP-201)
- Saved the package list first (1192 packages).
- `./cluster upgrade --yes` updated 15 packages, including the kernel (`687.57.1` → `687.58.1`), and rebooted, then reported "Done and settled". Log: `20261019-231455-upgrade.log`.
- douglas1 came back in about 3 minutes. The **customer network limits loaded at boot** (`cluster-egress` active, `test_customer_network` 7/7), which settles SOP-104's open boot check.

## 2.2b Repos and NVIDIA driver (`./cluster apply`)
1. The first preview failed: Ansible read the `rpm --qf` format string as template syntax. Fixed with `!unsafe` (commit "nvidia_driver: keep the rpm format string out of templating").
2. The first apply, log `20261019-232201-apply.log`:
   - set up the repo settings (CRB on, Slurm excluded from EPEL) on both machines
   - installed the NVIDIA key and repo, DKMS and kernel-devel-matched, and the nouveau blacklist
   - enabled the `580-open` stream, installed the driver packages and locked them
   - DKMS built `nvidia/580.105.08` for `5.14.0-687.58.1`

   It then **failed starting `nvidia-persistenced`**: nouveau was still loaded, since the role hadn't rebooted yet. The nouveau blacklist's initramfs rebuild was a handler, so it never ran after the failure.
3. **Fixed the role:**
   - the initramfs is now checked directly with `lsinitrd` and rebuilt if the blacklist is missing
   - the reboot comes before `nvidia-persistenced`
   - the handler is gone
4. The second apply, log `20261019-232807-apply.log`:
   - rebuilt the initramfs (`dracut --regenerate-all --force`) and installed the CUDA 13.0 compiler
   - **rebooted douglas1 at about 23:33**

   **douglas1 hasn't come back.** Ansible gave up after 20 minutes ("Timed out waiting for last boot time check"), and I kept checking until about 00:10.
   - ~~anton's `eno2` link stays up, so douglas1 has power and link.~~ **Wrong, corrected 2026-10-20:** anton's `eno2` goes to a switch, not straight to douglas1, so its link says nothing about douglas1 (see "Remote checks" below).
   - douglas1 doesn't answer ARP (`172.16.50.11 dev eno2 FAILED/INCOMPLETE`), so its OS network isn't up.
   - The previous reboot, 20 minutes earlier, took about 3 minutes.
   - There's no remote console from anton: douglas1's BMC isn't reachable from here.

## Most likely cause
The boot is stuck once the NVIDIA module loads. With nouveau blocked, udev loads `nvidia` for the 10 GPUs during boot. The only changes since the last good boot are:
- the NVIDIA driver (open modules, built for all three installed kernels)
- the nouveau blacklist
- a regenerated initramfs

An emergency-mode stop from a broken initramfs is less likely but possible. The screen will say which.

## What the user needs to do (at douglas1's screen or through its BMC's remote console)
1. Look at the screen and note what it shows (a photo is enough).
2. To get it booting without the NVIDIA driver:
   - Reboot. At the GRUB menu, press `e` on the first entry.
   - Add `modprobe.blacklist=nvidia,nvidia_drm,nvidia_modeset,nvidia_uvm` to the end of the `linux` line.
   - Boot with Ctrl-X.

   All three kernels have the module built, so an older kernel alone won't help.
3. Once it's up, Claude reads the failed boot's log (`journalctl -b -1`) and takes it from there.

## Changes to the procedure because of this (SOP-111)
- Before any reboot that loads a new driver:
  - enable the hardware watchdog, so a hung boot resets the machine
  - make the first boot a one-time GRUB entry (`grub2-reboot`), so a failed boot falls back to a known-good entry without the driver
- Find and record douglas1's BMC address, so there's always a remote console.

## State of the repo
The `nvidia_driver` role is in `ansible/site.yml`. Until douglas1 is back, anton-only work runs with `./cluster apply --limit anton`.

## Remote checks, 2026-10-20 06:40–06:50 (the user is in another city)
- douglas1 still doesn't answer ping or SSH ("No route to host").
- anton's `eno2` has had no link changes since anton booted on 2026-10-15, including during douglas1's two reboots on 10-19. So it's connected to a switch, which sends LLDP from `c8:33:74:36:0b:17`. The earlier "link up, so douglas1 has power" was wrong.
- Listened on the cluster network for about a minute (`tcpdump -i eno2`): **no packets from douglas1 at all.** The only other device is a Supermicro BMC (`ac:1f:6b:e8:0e:d7`, DHCP client `udhcp 1.23.1`) asking for an address every few seconds and getting none, because the cluster network has no DHCP server. douglas1's board is ASRock Rack, so this is probably anton's own BMC.
- Ping sweep of 172.16.50.2–254, plus an IPv6 all-nodes ping on `eno2`: nothing answers.
- **From here, douglas1's state can't be known:** hung during boot, stopped at a prompt, or powered off. Its BMC isn't on the cluster network, or has no address, so there's no remote console. Someone has to be at the machine, or plug its BMC port into the cluster switch so it can be reached from anton.
