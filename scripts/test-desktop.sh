#!/usr/bin/env bash
# Run FosOS Desktop headless in a throwaway Debian root and save screenshots.
# This checks that the shell starts, draws, opens its menus and receives
# notifications. It does not replace a Hyper-V session test.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
root="${FOSOS_DESKTOP_TEST_ROOT:-/var/tmp/fosos-desktop-test}"
out_dir="$repo_root/output/desktop"
mirror="${FOSOS_MIRROR:-http://deb.debian.org/debian}"

packages=(
  xvfb openbox dbus dbus-x11 x11-utils xdotool libnotify-bin mousepad
  python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-wnck-3.0 gir1.2-vte-2.91 python3-xlib
  fonts-inter fonts-liberation libgtk-3-0 adwaita-icon-theme elementary-xfce-icon-theme librsvg2-common
)

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo." >&2
  exit 1
fi

mounted=()
cleanup() {
  if [[ -d "$root/proc/1" ]]; then
    chroot "$root" pkill -f Xvfb >/dev/null 2>&1 || true
    chroot "$root" pkill -f dbus-daemon >/dev/null 2>&1 || true
  fi
  local i
  for ((i = ${#mounted[@]} - 1; i >= 0; i--)); do
    umount -l "${mounted[$i]}" 2>/dev/null || true
  done
}
trap cleanup EXIT

mount_into() {
  local type="$1" source="$2" target="$root/$3"
  mkdir -p "$target"
  if [[ "$type" == bind ]]; then
    mount --bind "$source" "$target"
  else
    mount -t "$type" "$source" "$target"
  fi
  mounted+=("$target")
}

if [[ ! -f "$root/.fosos-desktop-ready" ]]; then
  rm -rf -- "$root"
  debootstrap --variant=minbase trixie "$root" "$mirror"
fi

cat /etc/resolv.conf > "$root/etc/resolv.conf"
echo 'APT::Sandbox::User "root";' > "$root/etc/apt/apt.conf.d/99fosos-test"
mount_into proc proc proc
mount_into sysfs sysfs sys
mount_into bind /dev dev
mount_into devpts devpts dev/pts

if [[ ! -f "$root/.fosos-desktop-ready" ]]; then
  chroot "$root" apt-get update
  DEBIAN_FRONTEND=noninteractive chroot "$root" apt-get install -y --no-install-recommends "${packages[@]}"
  chroot "$root" dbus-uuidgen --ensure
  touch "$root/.fosos-desktop-ready"
fi

# Stage the package tree the same way the .deb is built: LF endings, executable bins.
rm -rf -- "$root/opt/fosos-desktop"
cp -a "$repo_root/packages/fosos-desktop" "$root/opt/fosos-desktop"
find "$root/opt/fosos-desktop" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$root/opt/fosos-desktop" -type f -exec sed -i 's/\r$//' {} +
chmod 755 "$root/opt/fosos-desktop/usr/bin/"*
mkdir -p "$root/usr/share/themes"
rm -rf -- "$root/usr/share/themes/FosOS" "$root/usr/share/icons/FosOS"
cp -a "$root/opt/fosos-desktop/usr/share/themes/FosOS" "$root/usr/share/themes/FosOS"
cp -a "$root/opt/fosos-desktop/usr/share/icons/FosOS" "$root/usr/share/icons/FosOS"
if chroot "$root" command -v gtk-update-icon-cache >/dev/null 2>&1; then
  chroot "$root" gtk-update-icon-cache -f -t /usr/share/icons/FosOS >/dev/null 2>&1 || true
fi

ln -sfn /opt/fosos-desktop/usr/share/fosos-desktop "$root/usr/share/fosos-desktop"

# Stand-ins for apps and settings tools the test root does not install, so the
# pinned row and the settings grid are complete.
mkdir -p "$root/usr/local/share/applications" "$root/usr/local/bin"
for stub in "thunar:Thunar File Manager" "xfce4-terminal:Xfce Terminal" "firefox-esr:Firefox ESR"; do
  id="${stub%%:*}"
  name="${stub#*:}"
  printf '[Desktop Entry]\nType=Application\nName=%s\nExec=true\nIcon=%s\n' "$name" "$id" \
    > "$root/usr/local/share/applications/$id.desktop"
done
for tool in xfce4-display-settings pavucontrol nm-connection-editor blueman-manager \
  xfce4-keyboard-settings xfce4-mouse-settings xfce4-mime-settings xfce4-terminal fosos-welcome; do
  printf '#!/bin/sh\nexit 0\n' > "$root/usr/local/bin/$tool"
  chmod 755 "$root/usr/local/bin/$tool"
done

cat > "$root/opt/run-desktop-test.sh" <<'EOF'
#!/bin/bash
set -u
export HOME=/root LANG=C.UTF-8 DISPLAY=:99 NO_AT_BRIDGE=1
export XDG_CURRENT_DESKTOP=FosOS GTK_THEME=FosOS GTK_ICON_THEME_NAME=FosOS
export XDG_DATA_DIRS=/opt/fosos-desktop/usr/share:/usr/local/share:/usr/share
export PATH=/opt/fosos-desktop/usr/bin:$PATH
out=/opt/shots
rm -rf "$out" && mkdir -p "$out"
mkdir -p ~/Documents/Projects ~/Documents/Reports ~/Downloads
touch ~/Documents/"Meeting notes.md" ~/Downloads/report.pdf
printf 'org.xfce.mousepad.desktop\n' > /tmp/extra-pin
mkdir -p ~/.config/fosos-desktop
cat /opt/fosos-desktop/usr/share/fosos-desktop/pinned /tmp/extra-pin | grep -v '^#' > ~/.config/fosos-desktop/pinned

shot() {
  python3 - "$out/$1.png" <<'PY'
import sys
import gi
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk
root = Gdk.get_default_root_window()
pixbuf = Gdk.pixbuf_get_from_window(root, 0, 0, root.get_width(), root.get_height())
pixbuf.savev(sys.argv[1], "png", [], [])
PY
  echo "screenshot: $1"
}

Xvfb :99 -screen 0 1366x768x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
sleep 2
eval "$(dbus-launch --sh-syntax)"
openbox --config-file /opt/fosos-desktop/usr/share/fosos-desktop/openbox/rc.xml >/tmp/openbox.log 2>&1 &
sleep 1
fosos-shell >/tmp/shell.log 2>&1 &
sleep 4
shot 01-desktop

fosos-files /root/Documents >/tmp/files.log 2>&1 &
sleep 3
shot 02-window

fosos-terminal >/tmp/terminal.log 2>&1 &
sleep 2
shot 02b-terminal
pkill -f fosos-terminal || true
sleep 0.5

printf 'Hello from FosOS Notepad.\n' > /tmp/sample-note.txt
fosos-notepad /tmp/sample-note.txt >/tmp/notepad.log 2>&1 &
sleep 2
shot 02c-notepad
pkill -f fosos-notepad || true
sleep 0.5

fosos-shell --toggle-start
sleep 1.5
shot 03-start-menu

xdotool type --delay 60 "text"
sleep 1.5
shot 04-search
xdotool key Escape
sleep 0.5

notify-send -a Firefox -i web-browser "Download complete" "report.pdf was saved to Downloads."
notify-send -a FosOS -u critical "Updates available" "3 packages can be upgraded."
sleep 1.5
shot 05-notifications

fosos-shell --toggle-popup notifications
sleep 1
shot 06-notification-list
xdotool key Escape
sleep 0.5

fosos-shell --toggle-popup clock
sleep 1
shot 07-clock
xdotool key Escape
sleep 0.5

fosos-settings >/tmp/settings.log 2>&1 &
sleep 3
shot 08-settings
xdotool key ctrl+q 2>/dev/null
pkill -f fosos-settings
sleep 1

# Coordinates assume the 1366x768 screen above and the default Start menu layout.
fosos-shell --toggle-start
sleep 1
xdotool mousemove 327 295 click 1
sleep 1
shot 09-all-apps
xdotool key Escape
sleep 0.5
fosos-shell --toggle-start
sleep 1
xdotool mousemove 388 687 click 1
sleep 1
shot 10-power
xdotool key Escape

echo "--- shell log"
cat /tmp/shell.log
echo "--- files log"
cat /tmp/files.log 2>/dev/null || true
echo "--- terminal log"
cat /tmp/terminal.log 2>/dev/null || true
echo "--- settings log"
cat /tmp/settings.log
echo "--- openbox log"
cat /tmp/openbox.log
pkill -f fosos-settings; pkill -f fosos-files; pkill -f fosos-terminal; pkill -f fosos-notepad; pkill -f fosos-shell; pkill mousepad; pkill openbox
sleep 1

# The real session script: it must start the shell and end cleanly on sign-out.
fosos-session >/tmp/session.log 2>&1 &
session_pid=$!
sleep 5
shot 11-session
result=0
if ! pgrep -f fosos-shell >/dev/null; then
  echo "FAIL: fosos-session did not start fosos-shell"
  result=1
fi
openbox --exit
for _ in 1 2 3 4 5 6 7 8 9 10; do
  kill -0 "$session_pid" 2>/dev/null || break
  sleep 0.5
done
if kill -0 "$session_pid" 2>/dev/null; then
  echo "FAIL: fosos-session did not end after openbox --exit"
  result=1
fi
sleep 1
if pgrep -f fosos-shell >/dev/null; then
  echo "FAIL: fosos-shell is still running after sign-out"
  result=1
fi
[ "$result" -eq 0 ] && echo "session start and sign-out: ok"
echo "--- session log"
cat /tmp/session.log

kill "$DBUS_SESSION_BUS_PID" 2>/dev/null
pkill Xvfb
exit "$result"
EOF
chmod 755 "$root/opt/run-desktop-test.sh"

chroot "$root" /opt/run-desktop-test.sh

mkdir -p "$out_dir"
cp "$root"/opt/shots/*.png "$out_dir/"
echo "Screenshots: $out_dir"
