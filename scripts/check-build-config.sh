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
  "$repo_root/packages/fosos-theme/etc/xdg/autostart/fosos-polkit-agent.desktop"
  "$repo_root/packages/fosos-theme/usr/share/backgrounds/fosos/fosos-wallpaper.png"
  "$repo_root/packages/fosos-theme/usr/share/fosos/logo/fosos-dawn-aperture.svg"
  "$repo_root/packages/fosos-theme/usr/share/fosos/logo/fosos-dawn-aperture-512.png"
  "$repo_root/packages/fosos-desktop/usr/share/fosos-desktop/logo/fosos-dawn-aperture.svg"
  "$repo_root/packages/fosos-desktop/usr/share/fosos-desktop/logo/fosos-dawn-aperture-mark.svg"
  "$repo_root/build/live-build/config/bootloaders/grub-pc/splash.png"
  "$repo_root/build/live-build/config/bootloaders/grub-pc/splash.svg"
  "$repo_root/build/live-build/config/bootloaders/grub-pc/config.cfg"
  "$repo_root/build/live-build/config/bootloaders/grub-pc/theme.cfg"
  "$repo_root/build/live-build/config/bootloaders/grub-pc/live-theme/theme.txt"
  "$repo_root/build/live-build/config/bootloaders/grub-pc/grub.cfg"
  "$repo_root/build/live-build/config/bootloaders/grub-efi/splash.png"
  "$repo_root/build/live-build/config/hooks/live/0200-fosos-grub-logo.hook.binary"
  "$repo_root/scripts/_render_grub_splash.mjs"
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
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-recovery-session"
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-shell"
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-lock"
  "$repo_root/packages/fosos-desktop/etc/pam.d/fosos-lock"
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-greeter"
  "$repo_root/packages/fosos-desktop/usr/share/xgreeters/fosos-greeter.desktop"
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-screenshot"
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-settings"
  "$repo_root/packages/fosos-desktop/usr/share/fosos-desktop/xsettingsd.conf"
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-files"
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-terminal"
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-notepad"
  "$repo_root/packages/fosos-desktop/usr/share/applications/fosos-files.desktop"
  "$repo_root/packages/fosos-desktop/usr/share/applications/fosos-terminal.desktop"
  "$repo_root/packages/fosos-desktop/usr/share/applications/fosos-notepad.desktop"
  "$repo_root/packages/fosos-desktop/usr/lib/fosos-desktop/fosdesk/files.py"
  "$repo_root/packages/fosos-desktop/usr/lib/fosos-desktop/fosdesk/terminal.py"
  "$repo_root/packages/fosos-desktop/usr/lib/fosos-desktop/fosdesk/windowchrome.py"
  "$repo_root/packages/fosos-desktop/usr/lib/fosos-desktop/fosdesk/wallpaper.py"
  "$repo_root/packages/fosos-desktop/usr/lib/fosos-desktop/fosdesk/authui.py"
  "$repo_root/packages/fosos-desktop/usr/lib/fosos-desktop/fosdesk/greeter.py"
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
  "$repo_root/packages/fosos-desktop/usr/libexec/fosos-shell-recovery"
  "$repo_root/packages/fosos-desktop/usr/share/doc/fosos-desktop/RECOVERY.md"
  "$repo_root/docs/RECOVERY.md"
  "$repo_root/docs/RELEASE-NOTES.md"
  "$repo_root/docs/ISO-SIZE.md"
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
if ! grep -q '^OnlyShowIn=FosOS;$' "$agent_desktop" || ! grep -q '^Exec=/usr/bin/lxpolkit$' "$agent_desktop"; then
  echo "FosOS authentication agent autostart is incomplete: $agent_desktop" >&2
  exit 1
fi
if ! grep -q '^lxpolkit$' "$repo_root/build/live-build/config/package-lists/fosos-base.list.chroot"; then
  echo "The image package list must install lxpolkit so APT does not choose ukui-polkit." >&2
  exit 1
fi

default_session="$repo_root/packages/fosos-desktop/etc/lightdm/lightdm.conf.d/50-fosos-default-session.conf"
live_session="$repo_root/build/live-build/config/includes.chroot/etc/lightdm/lightdm.conf.d/90-fosos-live.conf"
if ! grep -q '^user-session=fosos-desktop$' "$default_session"; then
  echo "Installed default session must be fosos-desktop: $default_session" >&2
  exit 1
fi
if ! grep -q '^greeter-session=fosos-greeter$' "$default_session"; then
  echo "Installed default greeter must be fosos-greeter: $default_session" >&2
  exit 1
fi
if ! grep -q '^user-session=fosos-desktop$' "$live_session" \
  || ! grep -q '^autologin-session=fosos-desktop$' "$live_session"; then
  echo "Live image must autologin to fosos-desktop: $live_session" >&2
  exit 1
fi
if ! grep -q '^greeter-session=fosos-greeter$' "$live_session"; then
  echo "Live image greeter must be fosos-greeter: $live_session" >&2
  exit 1
fi
if ! grep -q 'gir1.2-lightdm-1' "$repo_root/packages/fosos-desktop/DEBIAN/control"; then
  echo "fosos-desktop must depend on gir1.2-lightdm-1 for the greeter." >&2
  exit 1
fi
if ! grep -q 'python3-pamela' "$repo_root/packages/fosos-desktop/DEBIAN/control"; then
  echo "fosos-desktop must depend on python3-pamela for fosos-lock." >&2
  exit 1
fi
if grep -qE '(^|[, ])python3-pam([, ]|$)' "$repo_root/packages/fosos-desktop/DEBIAN/control"; then
  echo "fosos-desktop must not depend on python3-pam (wrong module name PAM)." >&2
  exit 1
fi
if ! grep -q 'desktopFile: "fosos-desktop.desktop"' \
  "$repo_root/packages/fosos-installer/etc/calamares/modules/displaymanager.conf"; then
  echo "Calamares must default to fosos-desktop.desktop." >&2
  exit 1
fi
if ! grep -q '^Name=FosOS Desktop$' \
  "$repo_root/packages/fosos-desktop/usr/share/xsessions/fosos-desktop.desktop"; then
  echo "xsessions entry must be named FosOS Desktop." >&2
  exit 1
fi
if [[ ! -f "$repo_root/packages/fosos-desktop/usr/share/xsessions/fosos-recovery.desktop" ]]; then
  echo "Missing FosOS Recovery xsessions entry." >&2
  exit 1
fi
if [[ ! -f "$repo_root/packages/fosos-desktop/usr/bin/fosos-recovery-session" ]]; then
  echo "Missing fosos-recovery-session." >&2
  exit 1
fi
if grep -qE '^xfce4$' "$repo_root/build/live-build/config/package-lists/fosos-base.list.chroot"; then
  echo "Phase 7a: do not install the xfce4 metapackage in the image list." >&2
  exit 1
fi
if grep -qE 'xfce4-' "$repo_root/packages/fosos-desktop/DEBIAN/control" \
  || grep -qE 'xfce4-' "$repo_root/packages/fosos-theme/DEBIAN/control"; then
  echo "Phase 7b: fosos-desktop and fosos-theme must not Depend on xfce4-* packages." >&2
  exit 1
fi
if grep -qE '^xfce4-' "$repo_root/build/live-build/config/package-lists/fosos-base.list.chroot"; then
  echo "Phase 7b: image package list must not list xfce4-* packages." >&2
  exit 1
fi
if grep -qE 'greybird-gtk-theme|elementary-xfce-icon-theme' \
  "$repo_root/packages/fosos-theme/DEBIAN/control"; then
  echo "Phase 7c: fosos-theme must not Depend on greybird or elementary-xfce." >&2
  exit 1
fi
if ! grep -q '^Version: 0\.6\.' "$repo_root/packages/fosos-theme/DEBIAN/control"; then
  echo "Phase 7c: fosos-theme should be 0.6.x after dropping greybird/elementary." >&2
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
sh -n "$repo_root/packages/fosos-desktop/usr/bin/fosos-recovery-session"
sh -n "$repo_root/packages/fosos-desktop/usr/libexec/fosos-shell-recovery"

# Parse the Python sources without writing bytecode into the package tree.
python3 - "$repo_root" <<'PY'
import ast
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
sources = [
    root / "packages/fosos-welcome/usr/bin/fosos-welcome",
    root / "packages/fosos-desktop/usr/bin/fosos-shell",
    root / "packages/fosos-desktop/usr/bin/fosos-lock",
    root / "packages/fosos-desktop/usr/bin/fosos-greeter",
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
