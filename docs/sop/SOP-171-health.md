# SOP-171: Cluster health at a glance
**Status:** first version 2026-10-20. Alerts (email) wait for plan D34.

## Purpose
`./cluster health` checks everything that should be true and prints one line per check, then exits 1 if anything fails:
- every machine answers over SSH
- anton's services: sshd, firewalld, chronyd, munge, mariadb, slurmdbd, slurmctld, nfs-server, squid
- each timer's last run succeeded and wasn't too long ago:
  - billing: 2 h
  - binary logs: 2 h
  - nightly backup: 26 h
  - weekly tests: 8 days
- the RAID mirror has both disks in sync
- `/` and `/raiddrive` are under 85% full
- the newest backup is under 26 h old
- the Slurm controller answers, and no node is down, drained or failing
- anton's time is in sync
- on each reachable compute node: sshd, chronyd, the customer network limits, munge and slurmd
- on each GPU node:
  - nvidia-persistenced
  - every GPU it should have is there (`nvidia-smi -L` against `gpu_count`)
  - no NVIDIA Xid errors, no GPU "fallen off the bus", and no PCIe hardware errors in the kernel log since boot. Even corrected PCIe errors count: on 2026-10-20 they pointed at a badly seated GPU.

`--json` gives the same as data, for scripts and agents. Every run is logged.

## Checks
- **Code tests:** `./cluster test --code -k health` (RAID, disk, backup age, timers, node states, GPU count, GPU and PCIe errors, the summary).

## History
- 2026-10-20: first version. Its first run correctly flagged douglas1 (down) and the backup timers (just reinstalled, not run yet).
- 2026-10-21: munge and slurmd on compute nodes; GPU count and GPU/PCIe errors on GPU nodes.
