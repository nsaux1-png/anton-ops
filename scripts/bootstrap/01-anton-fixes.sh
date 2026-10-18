#!/usr/bin/env bash
# One-time fixes on anton before Ansible takes over.
#   1. Rename the RAID array from douglas1:0 to anton:0
#   2. Fix the UUID typo in /etc/fstab and mount /raiddrive
#   3. Install the temporary passwordless-sudo file on anton
#   4. Install the same file on douglas1 (asks for douglas1's sudo password)
#
# Run from a normal SSH terminal on anton (not Claude Code's ! prefix):
#   sudo bash ~/cluster/scripts/bootstrap/01-anton-fixes.sh
#
# Safe to re-run: each step checks first and skips if already done.
# Output is logged to /var/log/cluster-ops/.

set -euo pipefail

DOUGLAS1=172.16.50.11
SUDOERS_FILE=/etc/sudoers.d/90-papaya-temp
FSTAB_BAD=000658eb-Z151-432f-b0e9-d7c43b3f1439
FSTAB_GOOD=000658eb-2151-432f-b0e9-d7c43b3f1439

if [[ $EUID -ne 0 || -z "${SUDO_USER:-}" ]]; then
  echo "Run this with sudo from your own account:  sudo bash $0" >&2
  exit 1
fi
if [[ ! -t 0 ]]; then
  echo "Run this from a real terminal (step 4 needs to ask for douglas1's password)." >&2
  exit 1
fi
if [[ "$(hostname)" != anton ]]; then
  echo "This script is for anton, but this machine is $(hostname). Stopping." >&2
  exit 1
fi

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p /var/log/cluster-ops
LOG=/var/log/cluster-ops/$(date +%Y%m%d-%H%M%S)-01-anton-fixes.log
exec > >(tee -a "$LOG") 2>&1

echo "== 01-anton-fixes  $(date -Is)  operator=$SUDO_USER  commit=$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"

step() { echo; echo "== $*"; }
ok()   { echo "   OK: $*"; }
skip() { echo "   SKIP: $*"; }

# A sudoers file is validated before it is installed, so a mistake can't lock anyone out of sudo.
sudoers_line() { echo "$SUDO_USER ALL=(ALL) NOPASSWD: ALL"; }

# ---------------------------------------------------------------------------
step "1. RAID array name"
md_name=$(mdadm --detail /dev/md0 | awk -F' : ' '/^ *Name :/{print $2}' | awk '{print $1}')
echo "   current name: $md_name"
if [[ "$md_name" == anton:* ]]; then
  skip "already named $md_name"
elif findmnt -S /dev/md0 >/dev/null; then
  echo "   ERROR: /dev/md0 is mounted; unmount it before renaming. Stopping." >&2
  exit 1
else
  members=$(mdadm --detail /dev/md0 | awk '/active sync/{print $NF}' | tr '\n' ' ')
  echo "   members: $members"
  [[ $(wc -w <<<"$members") -eq 2 ]] || { echo "   ERROR: expected 2 active members. Stopping." >&2; exit 1; }
  mdadm --stop /dev/md0
  # shellcheck disable=SC2086
  mdadm --assemble /dev/md0 --update=homehost --homehost=anton $members
  ok "renamed to $(mdadm --detail /dev/md0 | awk -F' : ' '/^ *Name :/{print $2}')"
fi
grep -E '^md0' -A1 /proc/mdstat | sed 's/^/   /'

# ---------------------------------------------------------------------------
step "2. /etc/fstab and /raiddrive"
real_uuid=$(blkid -s UUID -o value /dev/md0)
[[ "$real_uuid" == "$FSTAB_GOOD" ]] || { echo "   ERROR: md0 UUID is $real_uuid, expected $FSTAB_GOOD. Stopping." >&2; exit 1; }
if grep -q "$FSTAB_BAD" /etc/fstab; then
  backup=/etc/fstab.bak-$(date +%Y%m%d-%H%M%S)
  cp -a /etc/fstab "$backup"
  sed -i "s/$FSTAB_BAD/$FSTAB_GOOD/" /etc/fstab
  systemctl daemon-reload
  ok "fixed UUID typo (backup: $backup)"
else
  skip "no typo in /etc/fstab"
fi
grep raiddrive /etc/fstab | sed 's/^/   /'
if findmnt /raiddrive >/dev/null; then
  skip "/raiddrive already mounted"
else
  mount /raiddrive
  ok "mounted /raiddrive"
fi
findmnt /raiddrive | sed 's/^/   /'
df -h /raiddrive | sed 's/^/   /'
echo "   top-level contents:"
ls -la /raiddrive | sed 's/^/     /'

# ---------------------------------------------------------------------------
step "3. Temporary passwordless sudo on anton"
if [[ -f $SUDOERS_FILE ]] && grep -qxF "$(sudoers_line)" "$SUDOERS_FILE"; then
  skip "$SUDOERS_FILE already in place"
else
  tmp=$(mktemp)
  sudoers_line >"$tmp"
  visudo -cqf "$tmp"
  install -m 0440 -o root -g root "$tmp" "$SUDOERS_FILE"
  rm -f "$tmp"
  ok "installed $SUDOERS_FILE"
fi
visudo -cq && ok "sudoers configuration is valid"

# ---------------------------------------------------------------------------
step "4. Temporary passwordless sudo on douglas1 ($DOUGLAS1)"
echo "   You'll be asked for your sudo password on douglas1."
remote_cmd="set -e
if [ -f $SUDOERS_FILE ] && grep -qxF '$(sudoers_line)' $SUDOERS_FILE; then echo '   SKIP: already in place on douglas1'; exit 0; fi
tmp=\$(mktemp)
echo '$(sudoers_line)' > \$tmp
visudo -cqf \$tmp
install -m 0440 -o root -g root \$tmp $SUDOERS_FILE
rm -f \$tmp
visudo -cq
echo '   OK: installed $SUDOERS_FILE on douglas1'"
sudo -u "$SUDO_USER" ssh -t "$SUDO_USER@$DOUGLAS1" "sudo bash -c $(printf %q "$remote_cmd")"

# ---------------------------------------------------------------------------
echo
echo "== Done. Log saved to $LOG"
