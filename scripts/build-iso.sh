#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_build_dir="$repo_root/build/live-build"
output_dir="$repo_root/output"
suite="${FOSOS_DEBIAN_SUITE:-trixie}"
work_dir="${FOSOS_WORK_DIR:-$source_build_dir}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo: sudo ./scripts/build-iso.sh" >&2
  exit 1
fi

if ! command -v lb >/dev/null 2>&1; then
  echo "Debian's current live-build is required. See docs/BUILDING.md." >&2
  exit 1
fi

if ! lb config --help 2>&1 | grep -q -- '--bootloaders'; then
  cat >&2 <<'EOF'
Unsupported live-build version.
FosOS requires the current Debian 13 live-build with UEFI GRUB support.
Ubuntu's legacy live-build 3.0~a57 does not support the required
--bootloaders option and cannot produce the FosOS UEFI image.
See docs/BUILDING.md for the supported Debian builder setup.
EOF
  exit 1
fi

if [[ -z "$work_dir" || "$work_dir" == "/" ]]; then
  echo "FOSOS_WORK_DIR must name a safe, non-root build directory." >&2
  exit 1
fi

mkdir -p "$output_dir"

# WSL cannot reliably run live-build chroots on a Windows-mounted filesystem.
# When FOSOS_WORK_DIR is set, copy only the tracked live-build configuration to
# a Linux-native scratch directory and leave the source checkout untouched.
# Keep cache/ so a rebuild does not download Debian again.
if [[ "$work_dir" != "$source_build_dir" ]]; then
  saved_cache=""
  if [[ -d "$work_dir/cache" ]]; then
    saved_cache="$(mktemp -d /var/tmp/fosos-cache.XXXXXX)"
    mv "$work_dir/cache" "$saved_cache/cache"
  fi
  rm -rf -- "$work_dir"
  mkdir -p "$work_dir"
  cp -a "$source_build_dir/config" "$work_dir/config"
  if [[ -n "$saved_cache" ]]; then
    mv "$saved_cache/cache" "$work_dir/cache"
    rmdir -- "$saved_cache"
  fi
fi

cd "$work_dir"

# lb clean removes the previous chroot and ISO. It keeps cache/ unless --purge
# is passed. Generated config directories are removed below so a previous host
# cannot change this build.
lb clean

# lb clean intentionally preserves generated config files. Remove only those
# generated directories so every build starts with the options below, rather
# than inheriting a previous host-specific live-build configuration.
rm -rf -- \
  "$work_dir/config/binary" \
  "$work_dir/config/bootstrap" \
  "$work_dir/config/chroot" \
  "$work_dir/config/common" \
  "$work_dir/config/source"

# shellcheck source=scripts/stage-deb.sh
source "$repo_root/scripts/stage-deb.sh"

mkdir -p "$work_dir/config/packages.chroot"
rm -f "$work_dir/config/packages.chroot/"*.deb
stage_deb "$repo_root" fosos-archive-keyring "$work_dir/config/packages.chroot" >/dev/null
stage_deb "$repo_root" fosos-cli "$work_dir/config/packages.chroot" >/dev/null
stage_deb "$repo_root" fosos-theme "$work_dir/config/packages.chroot" >/dev/null
stage_deb "$repo_root" fosos-installer "$work_dir/config/packages.chroot" >/dev/null
stage_deb "$repo_root" fosos-welcome "$work_dir/config/packages.chroot" >/dev/null
stage_deb "$repo_root" fosos-desktop "$work_dir/config/packages.chroot" >/dev/null

lb config noauto \
  --architectures amd64 \
  --archive-areas "main contrib non-free-firmware" \
  --apt-recommends false \
  --binary-images iso-hybrid \
  --bootloaders grub-efi \
  --bootappend-live "boot=live components hostname=fosos nottyautologin splash" \
  --distribution "$suite" \
  --firmware-binary false \
  --firmware-chroot false \
  --ignore-system-defaults \
  --iso-application "FosOS" \
  --iso-volume "FOSOS_LIVE" \
  --mirror-binary "https://deb.debian.org/debian/" \
  --mirror-binary-security "https://security.debian.org/debian-security/" \
  --mirror-bootstrap "https://deb.debian.org/debian/" \
  --mirror-chroot "https://deb.debian.org/debian/" \
  --mirror-chroot-security "https://security.debian.org/debian-security/" \
  --initsystem systemd \
  --mode debian

lb build

iso_path="$(find . -maxdepth 1 -type f -name 'live-image-amd64.hybrid.iso' -print -quit)"
if [[ -z "$iso_path" ]]; then
  echo "live-build completed but the expected ISO was not found." >&2
  exit 1
fi

target="$output_dir/FosOS-${suite}-amd64.iso"
if ! cp "$iso_path" "$target"; then
  target="$output_dir/FosOS-${suite}-amd64-new.iso"
  cp "$iso_path" "$target"
  echo "The usual ISO path was busy. Built $target" >&2
else
  echo "Built $target"
fi
