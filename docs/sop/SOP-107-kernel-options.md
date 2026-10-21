# SOP-107: Extra kernel options
**Status:** draft 2026-10-21

## Purpose
Some machines need extra kernel options. douglas1 has these:

| Option | Why |
|---|---|
| `video=efifb:off video=vesafb:off iommu=pt pcie_aspm=off pci=realloc=on` | Added by hand during the GPU bring-up, before this repo. The usual settings for many GPUs on one board: no firmware framebuffer on the GPUs, IOMMU passthrough, no PCIe power saving, and room for every GPU's 16 GB memory window. |
| `initcall_debug` | Leftover debugging (very verbose boot log). To be taken off at the next planned reboot. |
| `rd.driver.blacklist=nouveau rd.driver.blacklist=nova-core` | Come with NVIDIA's driver packages (SOP-111). |

They're listed in `config/nodes.yml` (`kernel_args`), so a rebuilt machine gets the same ones, and the tests notice if one goes missing.

Role: `ansible/roles/kernel_args` (every machine; a machine without `kernel_args` is left alone).
- It adds missing options to every boot entry with `grubby --update-kernel=ALL`, and takes off any listed in `kernel_args_remove`.
- `grubby` also updates `/etc/default/grub` and `/etc/kernel/cmdline`, which kernels installed later read.
- **It never reboots.** A change takes effect at the next boot.
- Options not in either list are left alone, including the installer's own (`root=`, `crashkernel=`, `rd.lvm.lv=` and so on).

## When
Automatically on every `./cluster apply`. Only part: `./cluster apply --tags kernel_args`.

To change an option:
1. Edit `kernel_args` or `kernel_args_remove` in `config/nodes.yml`, and commit.
2. `./cluster apply --tags kernel_args`
3. Reboot the machine the safe way (SOP-111's supervised reboot, with the BMC reachable).

## Checks
- **Automated:** `./cluster test --live -k KernelOptions` checks that every option is:
  - on every boot entry
  - in `/etc/default/grub` and `/etc/kernel/cmdline`
  - on the running kernel (`/proc/cmdline`)
  
  After a change, the running-kernel check fails until the machine has rebooted.
- **By hand:** `sudo grubby --info=ALL | grep ^args`

## Undo
Move the option from `kernel_args` to `kernel_args_remove`, apply, then reboot when it's safe.

## History
- 2026-10-21: first version. douglas1's existing options recorded as they were. Nothing changed on the machine.
