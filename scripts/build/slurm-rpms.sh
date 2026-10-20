#!/usr/bin/env bash
# Build Slurm RPMs from SchedMD's source and publish them as a package repository on anton (SOP-151).
# Support built in: NVIDIA GPUs (NVML), Lua (job_submit.lua), PMIx (MPI), hwloc, NUMA, cgroup v2.
#
# Run it through ./cluster build slurm, which reads the version and checksum from config/versions.yml
# and logs everything:   slurm-rpms.sh <version> <sha256> <cuda, e.g. 13-0>
#
# Safe to re-run: a version that's already published is left alone.

set -euo pipefail

VERSION=$1 SHA256=$2 CUDA=$3
BUILD=/var/tmp/cluster-build
TOP=$BUILD/rpmbuild-$VERSION
TARBALL=slurm-$VERSION.tar.bz2
NVML=/usr/local/cuda-${CUDA/-/.}
REPO_DIR=/raiddrive/repos/slurm/$VERSION

step() { echo; echo "== $*"; }

if [[ -f $REPO_DIR/repodata/repomd.xml ]]; then
  echo "Slurm $VERSION is already built and published in $REPO_DIR. Nothing to do."
  exit 0
fi

step "1. Build dependencies"
sudo dnf -y -q install rpm-build gcc make autoconf automake pkgconf createrepo_c kernel-headers \
  dbus-devel munge-devel munge-libs readline-devel mariadb-devel pam-devel perl-ExtUtils-MakeMaker \
  perl-devel python3 lua-devel hwloc-devel numactl-devel pmix-devel lz4-devel zlib-devel \
  "cuda-nvml-devel-$CUDA"
echo "   OK"

step "2. Source, checked against the published SHA-256"
mkdir -p "$BUILD"
cd "$BUILD"
[[ -f $TARBALL ]] || curl -sSfL -o "$TARBALL" "https://download.schedmd.com/slurm/$TARBALL"
echo "$SHA256  $TARBALL" | sha256sum -c -

step "3. Build (full output: $TOP/build.log)"
rm -rf "$TOP"
mkdir -p "$TOP"
if ! rpmbuild -ta "$TARBALL" \
      --with cgroupv2 --with hwloc --with lua --with numa --with pmix --with nvml \
      --define "_with_nvml --with-nvml=$NVML" --define "_with_pmix --with-pmix=/usr" \
      --define "_topdir $TOP" > "$TOP/build.log" 2>&1; then
  tail -n 40 "$TOP/build.log"
  echo "   BUILD FAILED; see $TOP/build.log"
  exit 1
fi
grep -E "checking (for nvml|for lua|whether to build pmix|for hwloc)|NVML|nvml.h" "$TOP/build.log" | sort -u | head -20 || true
ls "$TOP/RPMS/x86_64/"

step "4. Check the GPU, Lua and PMIx support made it in"
for plugin in gpu_nvml.so job_submit_lua.so mpi_pmix.so cgroup_v2.so; do
  if rpm -qlp "$TOP"/RPMS/x86_64/slurm-*.rpm 2>/dev/null | grep -q "/$plugin\$"; then
    echo "   OK: $plugin"
  else
    echo "   MISSING: $plugin"
    exit 1
  fi
done

step "5. Publish to $REPO_DIR"
sudo install -d -m 0755 "$REPO_DIR"
sudo cp "$TOP"/RPMS/x86_64/*.rpm "$REPO_DIR"/
sudo cp "$TOP/build.log" "$REPO_DIR/build.log"
sudo createrepo_c -q "$REPO_DIR"
ls -la "$REPO_DIR"
echo
echo "== Done. Slurm $VERSION is ready to install (SOP-152: ./cluster apply)."
