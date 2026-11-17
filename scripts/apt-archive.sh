#!/usr/bin/env bash
# Publish FosOS packages with reprepro.
# The private signing key stays in FOSOS_GNUPGHOME and is never copied
# into the public fosos-apt checkout.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/stage-deb.sh
source "$repo_root/scripts/stage-deb.sh"

gnupg_home="${FOSOS_GNUPGHOME:-/root/.local/share/fosos/archive-gnupg}"
export GNUPGHOME="$gnupg_home"
work_dir="${FOSOS_APT_WORK:-/var/tmp/fosos-apt}"
apt_dir="${FOSOS_APT_DIR:-$(cd "$repo_root/.." && pwd)/fosos-apt}"
key_email="archive@fosos.local"
fingerprint_file="$repo_root/archive/signing-key.txt"
public_gpg="$repo_root/packages/fosos-archive-keyring/usr/share/keyrings/fosos-archive-keyring.gpg"

packages=(
  fosos-archive-keyring
  fosos-cli
  fosos-desktop
  fosos-installer
  fosos-theme
  fosos-welcome
)

usage() {
  cat <<'EOF'
Usage: apt-archive.sh <publish|promote> [package...]

  publish          Build the FosOS packages and publish them to testing.
                   Optional package names limit the publish to those packages.
  promote [PKG...] Copy packages from testing to stable.
                   With no names, every FosOS package is promoted.

The signing private key is created on first publish, under
/root/.local/share/fosos/archive-gnupg, and is not written to git.
Each publish and promote rebuilds the local reprepro database from
the public fosos-apt checkout so any machine with the key can run it.
EOF
}

require_tools() {
  local missing=()
  local tool
  for tool in gpg reprepro rsync dpkg-deb gzip; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      missing+=("$tool")
    fi
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "Missing tools: ${missing[*]}. Install gnupg and reprepro." >&2
    exit 1
  fi
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this script with sudo so the signing key stays in $gnupg_home." >&2
    exit 1
  fi
}

ensure_key() {
  export GNUPGHOME="$gnupg_home"
  mkdir -p "$gnupg_home"
  chmod 700 "$gnupg_home"
  cat > "$gnupg_home/gpg.conf" <<'EOF'
no-tty
batch
yes
pinentry-mode loopback
EOF
  cat > "$gnupg_home/gpg-agent.conf" <<'EOF'
allow-loopback-pinentry
EOF
  chmod 600 "$gnupg_home/gpg.conf" "$gnupg_home/gpg-agent.conf"
  gpgconf --kill gpg-agent >/dev/null 2>&1 || true

  if ! gpg --batch --list-secret-keys "$key_email" >/dev/null 2>&1; then
    if [[ -f "$fingerprint_file" || -f "$public_gpg" ]]; then
      echo "The public key is already recorded, but the private key is missing from $gnupg_home." >&2
      echo "Refusing to generate a different signing key." >&2
      exit 1
    fi
    cat > "$gnupg_home/keygen.conf" <<EOF
%echo Generating the FosOS archive signing key
Key-Type: EDDSA
Key-Curve: Ed25519
Key-Usage: sign
Name-Real: FosOS Archive
Name-Email: $key_email
Expire-Date: 0
%no-protection
%commit
EOF
    gpg --batch --generate-key "$gnupg_home/keygen.conf" >&2
    rm -f "$gnupg_home/keygen.conf"
  fi

  local fingerprint recorded
  fingerprint="$(gpg --batch --with-colons --list-secret-keys "$key_email" | awk -F: '/^fpr:/ {print $10; exit}')"
  if [[ -z "$fingerprint" ]]; then
    echo "Could not read the archive signing key fingerprint." >&2
    exit 1
  fi
  if [[ -f "$fingerprint_file" ]]; then
    recorded="$(tr -d '[:space:]' < "$fingerprint_file")"
    if [[ "$recorded" != "$fingerprint" ]]; then
      echo "Refusing to replace recorded signing key $recorded." >&2
      exit 1
    fi
  else
    printf '%s\n' "$fingerprint" > "$fingerprint_file"
  fi

  mkdir -p "$(dirname "$public_gpg")"
  gpg --batch --export "$fingerprint" > "$public_gpg"
  chmod 644 "$public_gpg"
  printf '%s\n' "default-key $fingerprint" >> "$gnupg_home/gpg.conf"
  printf '%s\n' "$fingerprint"
}

prepare_reprepro() {
  local fingerprint="$1"
  mkdir -p "$work_dir/conf" "$work_dir/dists" "$work_dir/pool"
  sed "s/@FINGERPRINT@/$fingerprint/g" "$repo_root/archive/distributions.in" > "$work_dir/conf/distributions"
  cp "$repo_root/archive/options" "$work_dir/conf/options"
  sed -i 's/\r$//' "$work_dir/conf/distributions" "$work_dir/conf/options"
}

assert_public_checkout() {
  if [[ ! -d "$apt_dir/.git" ]]; then
    echo "FOSOS_APT_DIR is not the fosos-apt checkout: $apt_dir" >&2
    exit 1
  fi
  if [[ -e "$apt_dir/private-keys-v1.d" || -e "$apt_dir/secring.gpg" || -e "$apt_dir/trustdb.gpg" ]]; then
    echo "Refusing to publish: private key material is inside $apt_dir." >&2
    exit 1
  fi
}

list_suite_filenames() {
  local suite="$1"
  local packages_file="$apt_dir/dists/$suite/main/binary-amd64/Packages"
  local packages_gz="${packages_file}.gz"
  if [[ -f "$packages_file" ]]; then
    awk '/^Filename:/{print $2}' "$packages_file"
  elif [[ -f "$packages_gz" ]]; then
    gzip -dc "$packages_gz" | awk '/^Filename:/{print $2}'
  fi
}

rebuild_work_from_public() {
  local fingerprint="$1"
  local suite filename
  assert_public_checkout
  rm -rf -- "$work_dir/db" "$work_dir/dists" "$work_dir/pool"
  prepare_reprepro "$fingerprint"
  for suite in testing stable; do
    while IFS= read -r filename; do
      [[ -z "$filename" ]] && continue
      if [[ ! -f "$apt_dir/$filename" ]]; then
        echo "Missing package file for $suite: $apt_dir/$filename" >&2
        exit 1
      fi
      reprepro -b "$work_dir" includedeb "$suite" "$apt_dir/$filename"
    done < <(list_suite_filenames "$suite")
  done
  if [[ -d "$work_dir/db" ]]; then
    reprepro -b "$work_dir" export
  fi
}

sync_public() {
  local fingerprint="$1"
  assert_public_checkout
  mkdir -p "$apt_dir/dists" "$apt_dir/pool"
  rsync -a --delete "$work_dir/dists/" "$apt_dir/dists/"
  rsync -a --delete "$work_dir/pool/" "$apt_dir/pool/"
  cp -a "$public_gpg" "$apt_dir/fosos-archive-keyring.gpg"
  printf '%s\n' "$fingerprint" > "$apt_dir/FINGERPRINT"
  if find "$apt_dir" \( -name 'private-keys-v1.d' -o -name 'secring.gpg' -o -name 'trustdb.gpg' \) | grep -q .; then
    echo "Private key material appeared in the public archive." >&2
    exit 1
  fi
}

publish_testing() {
  local fingerprint debs_dir deb name
  local names=("$@")
  if [[ ${#names[@]} -eq 0 ]]; then
    names=("${packages[@]}")
  fi
  fingerprint="$(ensure_key)"
  rebuild_work_from_public "$fingerprint"
  debs_dir="$(mktemp -d /var/tmp/fosos-debs.XXXXXX)"
  for name in "${names[@]}"; do
    deb="$(stage_deb "$repo_root" "$name" "$debs_dir")"
    if ! reprepro -b "$work_dir" includedeb testing "$deb"; then
      reprepro -b "$work_dir" remove testing "$name" || true
      reprepro -b "$work_dir" includedeb testing "$deb"
    fi
  done
  reprepro -b "$work_dir" export
  sync_public "$fingerprint"
  rm -rf -- "$debs_dir"
  echo "Published to testing: $apt_dir"
  echo "Signing key: $fingerprint"
}

promote_stable() {
  local fingerprint
  fingerprint="$(ensure_key)"
  rebuild_work_from_public "$fingerprint"
  if [[ ! -d "$work_dir/db" ]]; then
    echo "Nothing to promote. Publish to testing first." >&2
    exit 1
  fi
  if [[ "$#" -eq 0 ]]; then
    set -- "${packages[@]}"
  fi
  if ! reprepro -b "$work_dir" copy stable testing "$@"; then
    reprepro -b "$work_dir" remove stable "$@" || true
    reprepro -b "$work_dir" copy stable testing "$@"
  fi
  reprepro -b "$work_dir" export
  sync_public "$fingerprint"
  echo "Promoted to stable: $*"
}

require_root
require_tools

case "${1:-}" in
publish)
  shift
  publish_testing "$@"
  ;;
promote)
  shift
  promote_stable "$@"
  ;;
*)
  usage >&2
  exit 2
  ;;
esac
