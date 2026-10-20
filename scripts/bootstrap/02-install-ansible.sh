#!/usr/bin/env bash
# Install Ansible on anton, the machine every ./cluster command runs from (SOP-101).
#   1. ansible-core (Rocky AppStream) and the two collections we use (EPEL)
#   2. The run-log folder /var/log/cluster-ops: admins (group wheel) can write, nobody else can read
#
# Run on anton from your own account:
#   sudo bash ~/cluster/scripts/bootstrap/02-install-ansible.sh
#
# Safe to re-run: each step checks first and skips if already done.
# Output is logged to /var/log/cluster-ops/.

set -euo pipefail
umask 027

PACKAGES=(ansible-core ansible-collection-ansible-posix ansible-collection-community-general)
LOG_DIR=/var/log/cluster-ops

if [[ $EUID -ne 0 || -z "${SUDO_USER:-}" ]]; then
  echo "Run this with sudo from your own account:  sudo bash $0" >&2
  exit 1
fi
if [[ "$(hostname)" != anton ]]; then
  echo "This script is for anton, but this machine is $(hostname). Stopping." >&2
  exit 1
fi

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$LOG_DIR"
LOG=$LOG_DIR/$(date +%Y%m%d-%H%M%S)-02-install-ansible.log
exec > >(tee -a "$LOG") 2>&1

echo "== 02-install-ansible  $(date -Is)  operator=$SUDO_USER  commit=$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"

step() { echo; echo "== $*"; }
ok()   { echo "   OK: $*"; }
skip() { echo "   SKIP: $*"; }

# ---------------------------------------------------------------------------
step "1. Ansible packages"
missing=()
for p in "${PACKAGES[@]}"; do
  rpm -q "$p" >/dev/null 2>&1 || missing+=("$p")
done
if [[ ${#missing[@]} -eq 0 ]]; then
  skip "already installed"
else
  echo "   installing: ${missing[*]}"
  dnf -y -q install "${missing[@]}"
  ok "installed"
fi
rpm -q "${PACKAGES[@]}" | sed 's/^/   /'
ansible --version | head -1 | sed 's/^/   /'

# ---------------------------------------------------------------------------
step "2. Run-log folder $LOG_DIR"
# Admins write here through ./cluster. Customers must not read it: logs show config, names and output.
if [[ "$(stat -c '%G %a' "$LOG_DIR")" == "wheel 2770" ]]; then
  skip "already root:wheel, mode 2770"
else
  chgrp wheel "$LOG_DIR"
  chmod 2770 "$LOG_DIR"
  ok "root:wheel, mode 2770 (new files inherit group wheel)"
fi
# Older logs, including this one, were created before the folder belonged to wheel.
find "$LOG_DIR" -maxdepth 1 -type f ! -group wheel -exec chgrp wheel {} +
find "$LOG_DIR" -maxdepth 1 -type f -perm /o=rwx -exec chmod o-rwx {} +
ls -la "$LOG_DIR" | sed 's/^/   /'

echo
echo "== Done. Next: from your own account, run  ./cluster ping  in the repo (SOP-001)."
