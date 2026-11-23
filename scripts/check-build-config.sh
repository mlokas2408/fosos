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
  "$repo_root/packages/fosos-installer/etc/calamares/modules/mount.conf"
  "$repo_root/packages/fosos-installer/usr/bin/calamares-install-fosos"
  "$repo_root/packages/fosos-installer/usr/libexec/fosos-calamares"
  "$repo_root/packages/fosos-installer/usr/libexec/fosos-grub-install"
  "$repo_root/packages/fosos-installer/usr/share/polkit-1/actions/com.fosos.installer.policy"
  "$repo_root/packages/fosos-installer/usr/share/calamares/branding/fosos/show.qml"
  "$repo_root/packages/fosos-installer/usr/share/calamares/branding/fosos/slide1.png"
  "$repo_root/packages/fosos-installer/usr/share/calamares/branding/fosos/slide2.png"
  "$repo_root/packages/fosos-installer/usr/share/calamares/branding/fosos/slide3.png"
  "$repo_root/packages/fosos-installer/usr/share/calamares/branding/fosos/slide4.png"
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
  "$repo_root/packages/fosos-cli/etc/sudoers.d/10-fosos"
  "$repo_root/packages/fosos-cli/etc/polkit-1/rules.d/49-fosos-admin.rules"
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
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-remote"
  "$repo_root/packages/fosos-desktop/usr/share/fosos-desktop/xsettingsd.conf"
  "$repo_root/packages/fosos-desktop/usr/libexec/fosos-remote-host"
  "$repo_root/packages/fosos-desktop/usr/share/fosos-desktop/xrdp/xrdp.ini"
  "$repo_root/packages/fosos-desktop/usr/share/fosos-desktop/xrdp/sesman.ini"
  "$repo_root/packages/fosos-desktop/usr/share/fosos-desktop/xrdp/startwm.sh"
  "$repo_root/packages/fosos-desktop/usr/share/fosos-desktop/xrdp/fosos-dawn-aperture.bmp"
  "$repo_root/packages/fosos-desktop/usr/share/fosos-desktop/xrdp/fosos-rdp-login-banner.bmp"
  "$repo_root/packages/fosos-desktop/usr/share/fosos-desktop/xrdp/fosos-rdp-login-bg.bmp"
  "$repo_root/packages/fosos-desktop/usr/share/polkit-1/actions/org.fosos.remote-host.policy"
  "$repo_root/scripts/_gen_xrdp_logo.py"
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-files"
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-terminal"
  "$repo_root/packages/fosos-desktop/usr/bin/fosos-notepad"
  "$repo_root/packages/fosos-desktop/usr/share/applications/fosos-files.desktop"
  "$repo_root/packages/fosos-desktop/usr/share/applications/fosos-terminal.desktop"
  "$repo_root/packages/fosos-desktop/usr/share/applications/fosos-notepad.desktop"
  "$repo_root/packages/fosos-desktop/usr/share/applications/fosos-remote.desktop"
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
if ! grep -q '^[[:space:]]*desktopFile: "fosos-desktop"$' \
  "$repo_root/packages/fosos-installer/etc/calamares/modules/displaymanager.conf"; then
  echo "Calamares desktopFile must be fosos-desktop, without the .desktop suffix." >&2
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
pkg_list="$repo_root/build/live-build/config/package-lists/fosos-base.list.chroot"
desktop_control="$repo_root/packages/fosos-desktop/DEBIAN/control"
if ! grep -qE '^xrdp$' "$pkg_list" || ! grep -qE '^xorgxrdp$' "$pkg_list"; then
  echo "Remote Desktop host: image package list must install xrdp and xorgxrdp." >&2
  exit 1
fi
if grep -qE '^freerdp3-shadow' "$pkg_list"; then
  echo "Remote Desktop host: freerdp3-shadow must not be on the image list (use xrdp)." >&2
  exit 1
fi
if ! grep -qE '(^|[, ])xrdp([, ]|$)' "$desktop_control" \
  || ! grep -qE '(^|[, ])xorgxrdp([, ]|$)' "$desktop_control"; then
  echo "fosos-desktop must Recommend xrdp and xorgxrdp." >&2
  exit 1
fi
if grep -qE 'freerdp3-shadow' "$desktop_control"; then
  echo "fosos-desktop must not Recommend freerdp3-shadow (replaced by xrdp)." >&2
  exit 1
fi
if ! grep -q 'name=FosOS Desktop' \
  "$repo_root/packages/fosos-desktop/usr/share/fosos-desktop/xrdp/xrdp.ini"; then
  echo "xrdp.ini must offer a single FosOS Desktop session stanza." >&2
  exit 1
fi
if ! grep -q 'exec fosos-session' \
  "$repo_root/packages/fosos-desktop/usr/share/fosos-desktop/xrdp/startwm.sh"; then
  echo "xrdp startwm.sh must exec fosos-session." >&2
  exit 1
fi
if [[ -e "$repo_root/packages/fosos-desktop/usr/libexec/fosos-rdp-shadow-run" ]] \
  || [[ -e "$repo_root/packages/fosos-desktop/usr/lib/systemd/system/fosos-rdp-shadow.service" ]]; then
  echo "FreeRDP shadow host files must be removed (replaced by xrdp)." >&2
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

# live-build replaces every line containing LINUX_LIVE (sed matches comments
# too), so the placeholder must appear exactly once or the GRUB menu duplicates.
if [[ "$(grep -c 'LINUX_LIVE' "$repo_root/build/live-build/config/bootloaders/grub-pc/grub.cfg")" -ne 1 ]]; then
  echo "grub.cfg must contain the LINUX_LIVE placeholder exactly once: bootloaders/grub-pc/grub.cfg" >&2
  exit 1
fi

# Calamares runs mkfs.fat to create the UEFI partition; without dosfstools the
# installer fails at "Create file system 'fat32'".
if ! grep -qx 'dosfstools' "$repo_root/build/live-build/config/package-lists/fosos-base.list.chroot"; then
  echo "The image package list must install dosfstools (mkfs.fat for the EFI partition)." >&2
  exit 1
fi
if ! grep -qx 'console-setup' "$repo_root/build/live-build/config/package-lists/fosos-base.list.chroot"; then
  echo "The image package list must install console-setup so the text console uses the chosen keyboard layout." >&2
  exit 1
fi
# Hyper-V: avoid hyperv_fb input freeze; need DRM path + libinput + guest daemons.
if ! grep -q 'module_blacklist=hyperv_fb' "$repo_root/build/live-build/config/binary"; then
  echo "LB_BOOTAPPEND_LIVE must include module_blacklist=hyperv_fb for Hyper-V Gen2." >&2
  exit 1
fi
if ! grep -q 'blacklist hyperv_fb' \
  "$repo_root/build/live-build/config/hooks/normal/0100-graphical-session.hook.chroot"; then
  echo "Hyper-V graphical hook must blacklist hyperv_fb and prefer hyperv_drm." >&2
  exit 1
fi
if ! grep -qx 'xserver-xorg-input-libinput' "$repo_root/build/live-build/config/package-lists/fosos-base.list.chroot" \
  || ! grep -qx 'hyperv-daemons' "$repo_root/build/live-build/config/package-lists/fosos-base.list.chroot"; then
  echo "Image list must include xserver-xorg-input-libinput and hyperv-daemons." >&2
  exit 1
fi
if ! grep -q 'dosfstools' "$repo_root/packages/fosos-installer/DEBIAN/control"; then
  echo "fosos-installer must depend on dosfstools (mkfs.fat for the EFI partition)." >&2
  exit 1
fi
if ! grep -q 'device: /dev' "$repo_root/packages/fosos-installer/etc/calamares/modules/mount.conf"; then
  echo "mount.conf must bind-mount /dev into the target so grub-install can see /boot/efi." >&2
  exit 1
fi
settings_conf="$repo_root/packages/fosos-installer/etc/calamares/settings.conf"
if ! grep -q 'config: shellprocess_prepare.conf' "$settings_conf" \
  || ! grep -q 'config: shellprocess_sources.conf' "$settings_conf"; then
  echo "settings.conf must name the shellprocess instance config files." >&2
  exit 1
fi

if ! grep -qE -- '--bootloaders "grub-pc grub-efi"' "$repo_root/scripts/build-iso.sh"; then
  echo 'build-iso.sh must use --bootloaders "grub-pc grub-efi" for hybrid USB (Etcher).' >&2
  exit 1
fi
if ! grep -qE -- '--binary-images iso-hybrid' "$repo_root/scripts/build-iso.sh"; then
  echo "build-iso.sh must use --binary-images iso-hybrid." >&2
  exit 1
fi
if ! grep -qE -- '--debian-installer none' "$repo_root/scripts/build-iso.sh"; then
  echo "build-iso.sh must use --debian-installer none (not deprecated false)." >&2
  exit 1
fi
for pkg in zstd plymouth plymouth-label plymouth-themes; do
  if ! grep -qx "$pkg" "$repo_root/build/live-build/config/package-lists/fosos-base.list.chroot"; then
    echo "fosos-base.list.chroot must list $pkg (splash/initramfs warnings)." >&2
    exit 1
  fi
done
for pkg in \
  firmware-linux \
  firmware-iwlwifi \
  firmware-realtek \
  firmware-atheros \
  firmware-brcm80211 \
  firmware-mediatek \
  firmware-misc-nonfree \
  wireless-regdb; do
  if ! grep -qx "$pkg" "$repo_root/build/live-build/config/package-lists/fosos-base.list.chroot"; then
    echo "fosos-base.list.chroot must list $pkg (laptop Wi-Fi firmware)." >&2
    exit 1
  fi
done

bash -n "$repo_root/scripts/build-iso.sh"
bash -n "$repo_root/scripts/check-build-config.sh"
bash -n "$repo_root/scripts/stage-deb.sh"
bash -n "$repo_root/scripts/apt-archive.sh"
bash -n "$repo_root/scripts/test-apt-archive.sh"
bash -n "$repo_root/scripts/test-desktop.sh"
sh -n "$repo_root/packages/fosos-installer/usr/bin/calamares-install-fosos"
sh -n "$repo_root/packages/fosos-installer/usr/libexec/fosos-calamares"
sh -n "$repo_root/packages/fosos-installer/usr/libexec/fosos-grub-install"
sh -n "$repo_root/packages/fosos-cli/usr/bin/fos"
sudoers="$repo_root/packages/fosos-cli/etc/sudoers.d/10-fosos"
if ! grep -qE '^%sudo[[:space:]]+ALL=\(ALL:ALL\)[[:space:]]+NOPASSWD:[[:space:]]*ALL$' "$sudoers"; then
  echo "fosos-cli sudoers must grant passwordless sudo to group sudo." >&2
  exit 1
fi
if command -v visudo >/dev/null 2>&1 && ! visudo -cf "$sudoers"; then
  echo "fosos-cli sudoers failed visudo -cf." >&2
  exit 1
fi
if ! grep -q 'subject.isInGroup("sudo")' \
  "$repo_root/packages/fosos-cli/etc/polkit-1/rules.d/49-fosos-admin.rules"; then
  echo "fosos-cli polkit rule must allow active sudo group members without a prompt." >&2
  exit 1
fi
if ! grep -qE '(^|,)[[:space:]]*fosos-cli([,[:space:]]|$)' "$repo_root/packages/fosos-desktop/DEBIAN/control"; then
  echo "fosos-desktop must Depend on fosos-cli (passwordless admin + fos)." >&2
  exit 1
fi
if ! grep -q 'gnome-keyring-daemon --start' "$repo_root/packages/fosos-desktop/usr/bin/fosos-session"; then
  echo "fosos-session must start gnome-keyring-daemon for the OS keyring / Secret Service." >&2
  exit 1
fi
if ! grep -qE 'gnome-keyring|libpam-gnome-keyring' "$repo_root/packages/fosos-desktop/DEBIAN/control"; then
  echo "fosos-desktop must Depend on gnome-keyring and libpam-gnome-keyring." >&2
  exit 1
fi
sh -n "$repo_root/packages/fosos-desktop/usr/bin/fosos-session"
sh -n "$repo_root/packages/fosos-desktop/usr/bin/fosos-recovery-session"
sh -n "$repo_root/packages/fosos-desktop/usr/libexec/fosos-shell-recovery"
sh -n "$repo_root/packages/fosos-desktop/usr/libexec/fosos-remote-host"
sh -n "$repo_root/packages/fosos-desktop/usr/share/fosos-desktop/xrdp/startwm.sh"

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
    root / "packages/fosos-desktop/usr/bin/fosos-remote",
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
