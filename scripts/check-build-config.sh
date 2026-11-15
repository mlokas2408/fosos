#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

required_files=(
  "$repo_root/build/live-build/config/package-lists/fosos-base.list.chroot"
  "$repo_root/build/live-build/config/includes.chroot/etc/fosos-release"
  "$repo_root/build/live-build/config/includes.chroot/etc/lightdm/lightdm.conf.d/90-fosos-live.conf"
  "$repo_root/build/live-build/config/hooks/normal/0100-graphical-session.hook.chroot"
  "$repo_root/build/live-build/config/hooks/live/0100-enable-hook-runner.hook.chroot"
  "$repo_root/build/live-build/config/includes.chroot/etc/default/keyboard"
  "$repo_root/packages/fosos-theme/DEBIAN/control"
  "$repo_root/packages/fosos-theme/DEBIAN/postinst"
  "$repo_root/packages/fosos-theme/usr/libexec/fosos-apply-defaults"
  "$repo_root/packages/fosos-theme/etc/xdg/autostart/fosos-polkit-agent.desktop"
  "$repo_root/packages/fosos-theme/usr/share/backgrounds/fosos/fosos-wallpaper.png"
  "$repo_root/packages/fosos-installer/DEBIAN/control"
  "$repo_root/packages/fosos-installer/etc/calamares/settings.conf"
  "$repo_root/packages/fosos-installer/usr/bin/calamares-install-fosos"
  "$repo_root/packages/fosos-welcome/DEBIAN/control"
  "$repo_root/packages/fosos-welcome/usr/bin/fosos-welcome"
  "$repo_root/packages/fosos-welcome/usr/share/doc/fosos/guide.html"
  "$repo_root/packages/fosos-archive-keyring/DEBIAN/control"
  "$repo_root/packages/fosos-archive-keyring/DEBIAN/postinst"
  "$repo_root/packages/fosos-archive-keyring/usr/lib/fosos-archive-keyring/fosos.sources"
  "$repo_root/packages/fosos-archive-keyring/usr/libexec/fosos-enable-archive"
  "$repo_root/build/live-build/config/hooks/normal/0150-fosos-archive-source.hook.chroot"
  "$repo_root/packages/fosos-archive-keyring/usr/share/keyrings/fosos-archive-keyring.gpg"
  "$repo_root/packages/fosos-cli/DEBIAN/control"
  "$repo_root/packages/fosos-cli/usr/bin/fos"
  "$repo_root/packages/fosos-desktop/DEBIAN/control"
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-session"
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-shell"
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-settings"
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-files"
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-terminal"
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-notepad"
  "$repo_root/packages/fosos-desktop/usr/share/applications/fosos-files.desktop"
  "$repo_root/packages/fosos-desktop/usr/share/applications/fosos-terminal.desktop"
  "$repo_root/packages/fosos-desktop/usr/share/applications/fosos-notepad.desktop"
  "$repo_root/packages/fosos-desktop/usr/lib/fosos-desktop/fosdesk/files.py"
  "$repo_root/packages/fosos-desktop/usr/lib/fosos-desktop/fosdesk/terminal.py"
  "$repo_root/packages/fosos-desktop/usr/lib/fosos-desktop/fosdesk/windowchrome.py"
  "$repo_root/packages/fosos-desktop/etc/xdg/fosos-desktop/mimeapps.list"
  "$repo_root/packages/fosos-desktop/usr/share/xsessions/fosos-desktop.desktop"
  "$repo_root/packages/fosos-desktop/usr/share/fosos-desktop/fosos-desktop.css"
  "$repo_root/packages/fosos-desktop/usr/share/fosos-desktop/openbox/rc.xml"
  "$repo_root/packages/fosos-desktop/usr/share/themes/FosOS/openbox-3/themerc"
  "$repo_root/packages/fosos-desktop/usr/share/themes/FosOS/openbox-3/close.xbm"
  "$repo_root/packages/fosos-desktop/usr/share/themes/FosOS/openbox-3/max.xbm"
  "$repo_root/packages/fosos-desktop/usr/share/themes/FosOS/openbox-3/iconify.xbm"
  "$repo_root/packages/fosos-desktop/usr/share/themes/FosOS/gtk-3.0/gtk.css"
  "$repo_root/packages/fosos-desktop/usr/share/themes/FosOS/index.theme"
  "$repo_root/packages/fosos-desktop/usr/share/icons/FosOS/index.theme"
  "$repo_root/packages/fosos-desktop/usr/share/icons/FosOS/scalable/places/folder.svg"
  "$repo_root/packages/fosos-desktop/DEBIAN/postinst"
  "$repo_root/packages/fosos-desktop/etc/lightdm/lightdm.conf.d/50-fosos-default-session.conf"
  "$repo_root/archive/distributions.in"
  "$repo_root/scripts/stage-deb.sh"
  "$repo_root/scripts/apt-archive.sh"
  "$repo_root/docs/BUILDING.md"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing required build file: $file" >&2
    exit 1
  fi
done

agent_desktop="$repo_root/packages/fosos-theme/etc/xdg/autostart/fosos-polkit-agent.desktop"
if ! grep -q '^OnlyShowIn=XFCE;$' "$agent_desktop" || ! grep -q '^Exec=/usr/bin/lxpolkit$' "$agent_desktop"; then
  echo "XFCE authentication agent autostart is incomplete: $agent_desktop" >&2
  exit 1
fi
if ! grep -q '^lxpolkit$' "$repo_root/build/live-build/config/package-lists/fosos-base.list.chroot"; then
  echo "The image package list must install lxpolkit so APT does not choose ukui-polkit." >&2
  exit 1
fi

bash -n "$repo_root/scripts/build-iso.sh"
bash -n "$repo_root/scripts/check-build-config.sh"
bash -n "$repo_root/scripts/stage-deb.sh"
bash -n "$repo_root/scripts/apt-archive.sh"
bash -n "$repo_root/scripts/test-apt-archive.sh"
bash -n "$repo_root/scripts/test-desktop.sh"
sh -n "$repo_root/packages/fosos-cli/usr/bin/fos"
sh -n "$repo_root/packages/fosos-desktop/usr/bin/fosos-session"

# Parse the Python sources without writing bytecode into the package tree.
python3 - "$repo_root" <<'PY'
import ast
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
sources = [
    root / "packages/fosos-welcome/usr/bin/fosos-welcome",
    root / "packages/fosos-desktop/usr/bin/fosos-shell",
    root / "packages/fosos-desktop/usr/bin/fosos-settings",
    *sorted((root / "packages/fosos-desktop/usr/lib/fosos-desktop/fosdesk").glob("*.py")),
]
for source in sources:
    ast.parse(source.read_text(encoding="utf-8"), str(source))
PY

python3 - "$repo_root/packages/fosos-desktop/usr/share/fosos-desktop/openbox/rc.xml" \
  "$repo_root/packages/fosos-desktop/usr/share/fosos-desktop/openbox/menu.xml" <<'PY'
import sys
import xml.etree.ElementTree as ET

for path in sys.argv[1:]:
    ET.parse(path)
PY

echo "FosOS build configuration is structurally valid."
