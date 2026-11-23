#!/usr/bin/env bash
# Build one FosOS binary package.
# Source this file from bash, then call:
#   stage_deb REPO_ROOT PACKAGE_NAME DEST_DIR
# The built file is DEST_DIR/PACKAGE_VERSION_all.deb.
# The .deb path is written to stdout. Progress stays on stderr.

stage_deb() {
  local repo_root="$1"
  local name="$2"
  local dest_dir="$3"
  local src stage version dest

  src="$repo_root/packages/$name"
  if [[ ! -f "$src/DEBIAN/control" ]]; then
    echo "No Debian package at $src" >&2
    return 1
  fi

  stage="$(mktemp -d "/var/tmp/fosos-pkg.XXXXXX")"
  cp -a "$src/." "$stage/"
  find "$stage" -type d -name '__pycache__' -print0 | xargs -0 -r rm -rf

  if [[ "$name" == "fosos-installer" ]]; then
    mkdir -p "$stage/usr/share/calamares/branding/fosos"
    cp -a "$repo_root/packages/fosos-theme/usr/share/backgrounds/fosos/fosos-wallpaper.png" \
      "$stage/usr/share/calamares/branding/fosos/welcome.png"
  fi

  find "$stage" -type d -exec chmod 755 {} +
  find "$stage" -type f ! -name '*.png' ! -name '*.gpg' -exec sed -i 's/\r$//' {} +
  find "$stage" -type f -exec chmod 644 {} +
  if [[ -d "$stage/etc/sudoers.d" ]]; then
    # sudo rejects sudoers.d files that are group/world writable.
    find "$stage/etc/sudoers.d" -type f -exec chmod 440 {} +
  fi
  if [[ -f "$stage/DEBIAN/postinst" ]]; then
    chmod 755 "$stage/DEBIAN/postinst"
  fi
  if [[ -d "$stage/usr/bin" ]]; then
    find "$stage/usr/bin" -type f -exec chmod 755 {} +
  fi
  if [[ -d "$stage/usr/libexec" ]]; then
    find "$stage/usr/libexec" -type f -exec chmod 755 {} +
  fi

  version="$(awk '/^Version:/{print $2; exit}' "$stage/DEBIAN/control")"
  if [[ -z "$version" ]]; then
    echo "Package $name has no Version field." >&2
    rm -rf -- "$stage"
    return 1
  fi

  mkdir -p "$dest_dir"
  dest="$dest_dir/${name}_${version}_all.deb"
  dpkg-deb --root-owner-group -Zgzip --build "$stage" "$dest" >&2
  rm -rf -- "$stage"
  printf '%s\n' "$dest"
}
