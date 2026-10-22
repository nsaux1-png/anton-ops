# 2026-10-21: douglas1 is back. What its logs show about the 10-19 hang

## Why
douglas1 didn't come back from the NVIDIA driver reboot on 2026-10-19 ([ops log](2026-10-19-step2-gpu-driver.md)). On 2026-10-21 it answered again, having been up since 2026-10-20 16:17. Everything below was read from anton without changing douglas1, apart from the GPU tests and the link measurement.

Sources:
- `last -x` (login and boot records)
- `/var/log/messages`
- papaya's `~/.bash_history`
- `dnf history`, `lspci -vv`, `nvidia-smi`

douglas1's journal keeps only the current boot, because `/var/log/journal` doesn't exist. So `journalctl -b -1` has nothing.

## What happened
- **2026-10-19 23:30:39: clean shutdown for the driver reboot** (a "shutdown" record in `last`). The last log lines, at 23:30:37, are the NVIDIA module refusing the GPUs nouveau still held. That's expected before the reboot.
- **No boot until 2026-10-20 08:18:04, almost 9 hours later.** So douglas1 stopped between the end of the shutdown and the start of the next boot: the last step of the shutdown, the firmware's start-up checks (POST), or the boot menu. The OS never started, so nothing was logged. We don't know whether anyone saw the screen.
- **2026-10-20 08:18–16:18: 19 boots, with someone at the console** (logged in as papaya on `tty1`).
  - 3 ended with a clean shutdown.
  - 15 ended without one: the power button, reset, or a hang. The logs can't tell which.
  - The last one is still running.
- **The NVIDIA driver loaded in all 19 boots** (`NVRM: loading NVIDIA UNIX Open Kernel Module ... 580.105.08`, about 3 seconds after the kernel started). Each boot reached the login prompt in about 25 seconds. **So the driver doesn't hang the boot, and the "most likely cause" in the 10-19 log was wrong.**
- **The first boot logged corrected PCIe errors (08:18:25)** from root port `0000:00:01.1` (slot 21) and the GPU behind it, `0000:01:00.0`.
  - That's the GPU whose link was x4 instead of x8 on 10-19 (build plan 2.1 checks). It's x8 now, so it was probably reseated, or its riser re-cabled, on 10-20.
  - No PCIe errors were logged in any later boot.
- **Kernel options on every boot entry:**
  - `video=efifb:off video=vesafb:off iommu=pt initcall_debug pcie_aspm=off pci=realloc=on` were added by hand during the GPU bring-up. The shell history has them before the SSH-key setup of 2026-10-17.
  - `rd.driver.blacklist=nouveau rd.driver.blacklist=nova-core` came with the NVIDIA packages: `/etc/default/grub` changed at 2026-10-19 23:24:28, during the driver install.
- **Nothing else changed since the driver install.** No packages (`dnf history`); in `/etc`, only tuned's state files; the network settings are unchanged since 2026-10-16.

## Most likely cause now
Not proven: a hardware problem during the restart, most likely around GPU `0000:01:00.0`, which had a half-width link and logged PCIe errors on the next boot. The driver is ruled out as a boot hang. Whoever was at the console may know what the screen showed.

## State since 2026-10-20 16:17
- Up 23.5 hours. No PCIe errors. 10 GPUs idle at 43–58 °C, 5–32 W.
- **Measured every GPU's link while it works: all gen3 x8.** The root ports are set up as gen3 x8; the 10-19 checks listed the slots as PCIe 3.0. The layout is recorded as `gpu_pcie_links` in `config/nodes.yml`, so the test fails if any GPU drops to a narrower or slower link. The 10-19 x4 link would have been caught.
- **`./cluster test --live -k test_gpu`: 10 of 10 pass.** They cover:
  - driver version and version lock
  - open kernel modules; nouveau not loaded
  - persistence mode
  - built for the running kernel
  - full memory window mapped (Above 4G decoding, Resizable BAR)
  - the readings billing needs
  - a CUDA program on every GPU
  - PCIe links under load
- **Code tests: 107 of 107.**
- A hardware watchdog is available (`sp5100_tco` loads at boot), for the self-recovering reboot in SOP-111.

## Follow-ups
- Who was at the console on 10-20, and what did they see and change? (asked the user)
- A persistent journal on every machine, so the next failure leaves a log.
- The kernel options in Ansible, so they're recorded and checked. Drop `initcall_debug`, which is leftover debugging, at the next planned reboot.
- **No reboots of douglas1 until its BMC is reachable (Linear COP-44)**, and then only the self-recovering way (SOP-111).

## Found later on 2026-10-21
- **A new 4 TB NVMe in douglas1** (Fanxiang S660, `nvme1n1`, PCI `0000:05:00.0`). It first shows up in the boot at 2026-10-20 15:46, so it was fitted during the 10-20 console session. The user says Albert was at the machine. It's blank, with no partitions. `docs/machines.md` is updated.
