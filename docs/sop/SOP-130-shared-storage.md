# SOP-130: Shared storage
**Status:** proved on anton 2026-10-20 ([ops log](../ops-log/2026-10-20-phase4-storage.md)). The compute-node side is applied when douglas1 is back.

## Purpose
- **`/raiddrive`** (anton's 3.7 TB RAID1 mirror) is mounted with **user, group and project quotas**. The group quota is each customer's storage limit and bill; the project quota makes `df` show it; the user quota gives the per-user breakdown (`slurm-design.md` section 4).
- **Customer folders** live in `/raiddrive/cluster`, which every machine sees as **`/cluster`**:
  - `/cluster/home/<user>` (`0700`)
  - `/cluster/projects/<customer>`
  - `/cluster/software`

  The `home` and `projects` folders are `0711`, so customers can't list who else is there. On anton, `/cluster` is a bind mount; on compute nodes, it's NFS.
- **NFS version 4 only**, exported to the cluster network only, with `root_squash`: root on a compute node is nobody on the storage.
- **Safety:** `/raiddrive` is `nofail`, so anton still boots if the array breaks. The NFS server and `/cluster` require `/raiddrive` to be mounted, so an empty mount point is never shared and customers' files can never land on anton's system disk.

Roles: `ansible/roles/storage` (anton) and `ansible/roles/shared_storage` (compute nodes). anton's firewall opens `nfs` in the `cluster` zone only.

## When
Automatically on every `./cluster apply`.

## Before you start
- The preconditions of SOP-001.
- **Turning quotas on needs a full unmount of `/raiddrive`.** The role does it only when quotas are off, and it fails safely if anything is using `/raiddrive`. With customers on the cluster, that's a maintenance window. Check first with `sudo fuser -vm /raiddrive`.

## Steps
1. `./cluster apply --dry-run`
2. `./cluster apply`

## Expected result
- `sudo xfs_quota -x -c state /raiddrive` shows `Enforcement: ON` for user, group and project.
- `findmnt /cluster` on anton shows `/dev/md0[/cluster]`; on compute nodes it shows `nfs4`.
- `sudo exportfs -v` shows `/raiddrive/cluster 172.16.50.0/24(…rw,…root_squash…)`.

## Checks
- **Automated:** `./cluster test --live -k test_storage`. Server: quotas, fstab, folder modes, bind mount, export options, NFS v3 off, firewall, mount dependency. Compute nodes: the same files are visible, and root is squashed.

## Undo
On anton:
```
sudo systemctl disable --now nfs-server
sudo rm -f /etc/exports.d/cluster.exports; sudo rm -rf /etc/systemd/system/nfs-server.service.d
sudo sed -i '/^vers3=n/d' /etc/nfs.conf
sudo umount /cluster && sudo sed -i '\| /cluster |d' /etc/fstab
# only if nothing is stored there:  sudo rm -rf /raiddrive/cluster
# quotas off: put /raiddrive's fstab options back to defaults,nofail, then:
sudo umount /raiddrive && sudo mount /raiddrive
sudo firewall-cmd --permanent --zone=cluster --remove-service=nfs && sudo firewall-cmd --reload
```
On compute nodes: `sudo umount /cluster`, then remove its fstab line. Then remove the roles from `ansible/site.yml`.

## History
- 2026-10-20: first version, applied to anton (douglas1 was down).
  - Proof run: everything undone, including NFS removed, quotas off with a full remount, and the folders deleted (`/raiddrive` was empty). Then rebuilt with one `./cluster apply --limit anton` ("Done and settled"). The server tests passed again (8/8).
