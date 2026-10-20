# 2026-10-20: Build phase 4 (storage) on anton

## Why
Build plan phase 4. douglas1 is down (ops log 2026-10-19-step2-gpu-driver), so only anton's side is done. The compute-node mount is in the repo and gets applied when douglas1 is back.

## Before (read-only)
- `/raiddrive`:
  - fstab: `UUID="000658eb-…" /raiddrive xfs defaults,nofail`
  - mounted `noquota`
  - XFS v5 (`crc=1`), so group and project quotas can both be on
  - **empty**
- `fuser -vm /raiddrive`: only the kernel's own mount.
- nfs-utils not installed.

## Done
By Claude Code (a session on anton as papaya), while the user was away.
1. **Wrote the roles:**
   - `storage` (anton): fstab quota options, a full unmount and mount when quotas are off, the customer folder layout, the `/cluster` bind mount, NFSv4-only, the export to `172.16.50.0/24` with `root_squash`, and an `nfs-server` that requires `/raiddrive`
   - `shared_storage` (compute nodes): the NFS mount at `/cluster`
   - `nfs` added to anton's `cluster` firewall zone; `storage_server` and `storage_device` added to `config/nodes.yml`
   - `tests/live/test_storage.py`
2. **Two preview failures, both fixed:**
   - a `when:` condition containing `: ` needed quoting
   - "restart NFS" ran in preview before NFS was installed; now skipped, as for squid
3. **`./cluster apply --yes --limit anton`:** "Done and settled". Log: `20261020-000019-apply.log`. Quotas are on (user, group, project), `/cluster` is bound, and the export is live.
4. **Tests:** `./cluster test --live -k StorageServer`, 8/8.
5. **Proof run:**
   - Undid everything: stopped and removed NFS, deleted the export and drop-in, unbound `/cluster`, deleted `/raiddrive/cluster`, restored the original fstab line, did a full unmount and mount (`noquota` again), and removed `nfs` from the zone.
   - `./cluster apply --yes --limit anton`: "Done and settled". Log: `20261020-000148-apply.log`.
   - Tests: 8/8 again.

## Follow-ups
- The compute-node side (`/cluster` over NFS on douglas1, and `StorageOnComputeNodes`) is pending douglas1.
- Per-customer limits come with phase 5 (customers and users).
