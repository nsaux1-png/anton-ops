# 2026-10-18: Why /raiddrive isn't mounted

## Found
- The RAID1 array is healthy: `md0` = `sda` + `sdb`, both members active (`[UU]`), 3.6 TB usable, XFS.
- The intended mount point is **`/raiddrive`** (not `/etc/raiddrive`). The empty directory exists, owned by root, created 2026-10-15.
- `/etc/fstab` has:
  ```
  UUID="000658eb-Z151-432f-b0e9-d7c43b3f1439" /raiddrive xfs defaults,nofail 0 0
  ```
  but the filesystem's real UUID is `000658eb-2151-432f-b0e9-d7c43b3f1439`. The `Z` should be a `2`.
- Because of `nofail`, the failed mount at boot is silent, so `/raiddrive` has stayed empty and `raiddrive.mount` is inactive.
- `/etc/mdadm.conf` identifies the array by UUID only. The `douglas1:0` name is stored in the array's own metadata on the disks.

## Fix (to run with sudo)
```
sudo cp /etc/fstab /etc/fstab.bak
sudo sed -i 's/000658eb-Z151-432f/000658eb-2151-432f/' /etc/fstab
sudo systemctl daemon-reload
sudo mount /raiddrive
findmnt /raiddrive
```

## Done (2026-10-18 00:28, `scripts/bootstrap/01-anton-fixes.sh`, run by papaya)
- Array renamed `douglas1:0` → `anton:0`. Both members in sync, state clean.
- fstab typo fixed (backup `/etc/fstab.bak-20261018-002853`); `/raiddrive` mounted.
- Contents: empty. 3.7 TB filesystem; the 26 GB shown as used is XFS metadata reservation.
- Temporary passwordless sudo installed on anton and douglas1 (`/etc/sudoers.d/90-papaya-temp`).
- Full output: `/var/log/cluster-ops/20261018-002852-01-anton-fixes.log` on anton.
