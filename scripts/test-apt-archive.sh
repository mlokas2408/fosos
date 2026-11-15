#!/usr/bin/env bash
# Exercise the local FosOS archive: signature, install, upgrade, removal, repair.
# Uses the reprepro work directory. It does not promote testing to stable.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work_dir="${FOSOS_APT_WORK:-/var/tmp/fosos-apt}"
export GNUPGHOME="${FOSOS_GNUPGHOME:-/root/.local/share/fosos/archive-gnupg}"
root="${FOSOS_APT_TEST_ROOT:-/var/tmp/fosos-apt-test}"
public_gpg="$repo_root/packages/fosos-archive-keyring/usr/share/keyrings/fosos-archive-keyring.gpg"
sources_file="$repo_root/packages/fosos-archive-keyring/usr/lib/fosos-archive-keyring/fosos.sources"

refresh_lists() {
  rm -f "$root"/var/lib/apt/lists/_srv_fosos-apt_*
  chroot "$root" apt-get update
}

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo." >&2
  exit 1
fi

if [[ ! -f "$work_dir/dists/testing/InRelease" ]]; then
  echo "Publish the testing suite before running this test." >&2
  exit 1
fi

grep -q 'https://mlokas2408.github.io/fosos-apt' "$sources_file"
grep -q 'Signed-By: /usr/share/keyrings/fosos-archive-keyring.gpg' "$sources_file"
if grep -q 'apt-key' "$sources_file"; then
  echo "The FosOS source entry must not use apt-key." >&2
  exit 1
fi

gpg --no-default-keyring --keyring "$public_gpg" --verify "$work_dir/dists/testing/InRelease" >/dev/null

if [[ ! -x "$root/usr/bin/apt-get" ]]; then
  if command -v eatmydata >/dev/null 2>&1; then
    eatmydata debootstrap --variant=minbase trixie "$root" https://deb.debian.org/debian
  else
    debootstrap --variant=minbase trixie "$root" https://deb.debian.org/debian
  fi
fi

mkdir -p "$root/dev/pts"
if ! mountpoint -q "$root/dev/pts"; then
  mount -t devpts devpts "$root/dev/pts"
fi
mkdir -p "$root/srv/fosos-apt"
if ! mountpoint -q "$root/srv/fosos-apt"; then
  mount --bind "$work_dir" "$root/srv/fosos-apt"
fi
cleanup() {
  if mountpoint -q "$root/dev/pts"; then
    umount "$root/dev/pts" || true
  fi
  if mountpoint -q "$root/srv/fosos-apt"; then
    umount "$root/srv/fosos-apt"
  fi
}
trap cleanup EXIT

rm -f "$root/etc/resolv.conf"
cat /etc/resolv.conf > "$root/etc/resolv.conf"
mkdir -p "$root/etc/apt/apt.conf.d"
printf 'APT::Sandbox::User "root";\n' > "$root/etc/apt/apt.conf.d/00fosos-test"
keyring_deb="$(find "$work_dir/pool" -name 'fosos-archive-keyring_*_all.deb' -print -quit)"
mkdir -p "$root/tmp/fosos-debs"
cp -a "$keyring_deb" "$root/tmp/fosos-debs/"
chroot "$root" dpkg -i "/tmp/fosos-debs/$(basename "$keyring_deb")"

cat > "$root/etc/apt/sources.list.d/fosos.sources" <<'EOF'
Types: deb
URIs: file:/srv/fosos-apt
Suites: testing
Components: main
Signed-By: /usr/share/keyrings/fosos-archive-keyring.gpg
EOF

refresh_lists
chroot "$root" dpkg --purge fosos-cli >/dev/null 2>&1 || true
chroot "$root" dpkg --purge fosos-archive-test-broken >/dev/null 2>&1 || true
printf 'y\n' | chroot "$root" apt-get install fosos-cli
test "$(chroot "$root" dpkg-query -W -f '${Version}' fosos-cli)" = "0.1.0"
set +e
chroot "$root" fos install -y fosos-cli
status=$?
set -e
if [[ "$status" -ne 2 ]]; then
  echo "fos accepted an APT option (status $status)." >&2
  exit 1
fi

upgrade_dir="$(mktemp -d /var/tmp/fosos-apt-upgrade.XXXXXX)"
cp -a "$work_dir/." "$upgrade_dir/"
cli_stage="$(mktemp -d /var/tmp/fosos-cli.XXXXXX)"
cp -a "$repo_root/packages/fosos-cli/." "$cli_stage/"
sed -i 's/^Version: .*/Version: 0.1.1/' "$cli_stage/DEBIAN/control"
find "$cli_stage" -type d -exec chmod 755 {} +
find "$cli_stage" -type f -exec chmod 644 {} +
chmod 755 "$cli_stage/usr/bin/fos"
cli_deb="$upgrade_dir/fosos-cli_0.1.1_all.deb"
dpkg-deb --root-owner-group -Zgzip --build "$cli_stage" "$cli_deb"
reprepro -b "$upgrade_dir" includedeb testing "$cli_deb"
umount "$root/srv/fosos-apt"
mount --bind "$upgrade_dir" "$root/srv/fosos-apt"
refresh_lists
printf 'y\n' | chroot "$root" fos install fosos-cli
test "$(chroot "$root" dpkg-query -W -f '${Version}' fosos-cli)" = "0.1.1"

printf 'y\n' | chroot "$root" fos remove fosos-cli
if chroot "$root" test -e /usr/bin/fos; then
  echo "fos remained installed after removal." >&2
  exit 1
fi
printf 'y\n' | chroot "$root" apt-get install fosos-cli

broken="$(mktemp -d /var/tmp/fosos-broken.XXXXXX)"
mkdir -p "$broken/DEBIAN"
cat > "$broken/DEBIAN/control" <<'EOF'
Package: fosos-archive-test-broken
Version: 0.0.1
Section: misc
Priority: optional
Architecture: all
Depends: fosos-package-that-does-not-exist
Maintainer: FosOS <dev@fosos.local>
Description: intentional broken package for recovery tests
 This package is not published to the FosOS archive.
EOF
find "$broken" -type d -exec chmod 755 {} +
find "$broken" -type f -exec chmod 644 {} +
broken_deb="/tmp/fosos-debs/fosos-archive-test-broken_0.0.1_all.deb"
dpkg-deb --root-owner-group -Zgzip --build "$broken" "$root$broken_deb"
chroot "$root" dpkg --force-depends -i "$broken_deb"
printf 'y\n' | chroot "$root" fos repair
if chroot "$root" dpkg-query -W fosos-archive-test-broken >/dev/null 2>&1; then
  echo "fos repair left the broken package installed." >&2
  exit 1
fi
test "$(chroot "$root" dpkg-query -W -f '${Version}' fosos-cli)" = "0.1.1"

tampered="$(mktemp -d /var/tmp/fosos-apt-tamper.XXXXXX)"
cp -a "$work_dir/dists" "$tampered/dists"
cp -a "$work_dir/pool" "$tampered/pool"
python3 - <<PY
from pathlib import Path
root = Path("$tampered")
files = list(root.glob("dists/testing/main/**/Packages"))
files += list(root.glob("dists/testing/main/**/Packages.gz"))
if not files:
    raise SystemExit("no package index found")
for packages in files:
    data = bytearray(packages.read_bytes())
    data[-1] ^= 0x01
    packages.write_bytes(data)
PY
umount "$root/srv/fosos-apt"
mount --bind "$tampered" "$root/srv/fosos-apt"
if refresh_lists; then
  echo "A changed package index was accepted." >&2
  exit 1
fi

echo "FosOS archive install, upgrade, removal, and repair checks passed."
rm -rf -- "$upgrade_dir" "$cli_stage" "$broken" "$tampered"
