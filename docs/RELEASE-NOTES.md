# FosOS release notes

## FosOS theme 0.7.2 — Quiet shut down / restart splash

- Same Dawn Aperture Plymouth logo+spinner covers shut down and restart
  (not a scrolling systemd console)
- Kernel cmdline and systemd `ShowStatus=no` suppress unit stop text;
  Plymouth `SuppressMessages` on shutdown/reboot modes

## FosOS theme 0.7.1 — Visible Plymouth logo + larger spinner

- Boot splash now puts the Dawn Aperture mark in `throbber-*` frames (what
  Plymouth shows with `UseEndAnimation=false`); previously the logo lived
  only in unused `animation-*` frames, so boots showed a tiny spinner alone
- Larger mark (~280px) and spinner (~128px) for 1080p / HiDPI screens

## FosOS theme 0.7.0 — Quiet boot (logo + spinner)

- After the firmware logo: hidden GRUB (Shift shows menu), Dawn Aperture
  splash theme, then graphical Plymouth (logo + spinner on `#0a0a0a`) until
  the greeter — no blue menu or boot console text by default
- Kernel cmdline: `quiet splash loglevel=3 rd.udev.log_level=3
  vt.global_cursor_default=0` via `/etc/default/grub.d/fosos-boot.cfg`
- Plymouth theme switched from text to `two-step`; postinst runs
  `plymouth-set-default-theme -R` so the splash is in the initramfs
- Live `bootappend` matches; image hook rebuilds Plymouth into the squashfs

## FosOS installer 1.0.4 / CLI 0.2.6 — UEFI Secure Boot

- Live image: `--uefi-secure-boot enable`; ship `shim-signed`,
  `grub-efi-amd64-signed`, `grub-efi-amd64`, `mokutil` (APT recommends off)
- Installer Depends match; `fosos-grub-install` prefers `--uefi-secure-boot`
  when Debian-signed binaries are present; prepare-target marks them manual
- Hyper-V scripts enable Secure Boot with
  `MicrosoftUEFICertificateAuthority`; TESTING adds soak **J06**
- `fos upgrade` uses `apt-get full-upgrade` so new Depends are not kept back

## FosOS 1.13.20 — Baremetal soak fixes (icons + locales)

- Prune retired **Home** desktop-icon positions and ignore orphan ids so
  Computer / Files / Recycle Bin cannot share a cell after upgrades
- Depend on `locales`; postinst enables/generates `en_US.UTF-8` (and the
  system LANG when set) so GTK no longer warns “Locale not supported”
- Live image: ship `locales` and generate the Region Settings locale set
- Sync Settings About / `VERSION` with the package (was stuck on 1.13.0)
- Region labels: add Croatian (`hr_HR.UTF-8`)

## FosOS 1.13.19 — Bluetooth pairing agent

- Start `blueman-applet` with the desktop session so BlueZ always has an agent
  to confirm passkeys (mice/keyboards no longer fail with AuthenticationFailed)
- Depend on `blueman` alongside the existing Settings → Bluetooth UI

## FosOS 1.13.18 — Real audio + Start Quick Link menu

- Ship `firmware-sof-signed`, `firmware-intel-sound`, and `alsa-ucm-conf`
  (APT recommends are off). Without them Intel SOF/SST machines only expose
  PipeWire “Dummy Output” and volume has no hardware device
- Start button right-click opens the Win+X Quick Link menu (Terminal, Files,
  Settings, power submenu, Desktop, …) like Windows 11

## FosOS 1.13.17 — Volume click + unmute on adjust

- Play the freedesktop `audio-volume-change` click (debounced) when changing
  volume or unmuting — Windows-like OSD feedback via `pw-play`
- Moving the volume slider unmutes the sink so level changes are audible
- Depend on `sound-theme-freedesktop` and `pipewire-bin` for the feedback sound

## FosOS 1.13.16 — Brightness actually works

- Depend on `brightness-udev` so laptop backlight sysfs is writable by the
  `video` group (APT recommends are off on the ISO, so `brightnessctl` alone
  left the slider moving with no screen change)

## FosOS 1.13.15 — Full-screen Settings (Windows-like)

- Settings opens maximized with a left nav, search, Home hero and Back
- Display: brightness, resolution, orientation, primary monitor (xrandr);
  optional arandr for rearrange
- Sound: volume/mute, default output and input devices (wpctl); optional
  pavucontrol for advanced mixer
- Power: battery status, brightness, screen blank + DPMS sleep timers,
  Suspend / Hibernate when available
- Window titlebars tightened to ~32px (CardWindow, GTK CSD, Openbox) to
  match Windows 11 chrome height
- Dark tooltips (muted surface + light text) instead of harsh white/black
  inverted tips on the taskbar and apps

## FosOS 1.13.14 — Status controls, Region, desktop icons

- Fix volume slider / mute (`wpctl -l` before `set-volume`) and brightness
  percent parsing (`brightnessctl -m` field with `%`; sysfs preferred)
- Taskbar shows battery percentage beside the icon
- Settings → Region: calendar, clock date/time and number formats follow the
  selected locale (generated locales only)
- Default desktop icons: Computer, Files, Recycle Bin (Home removed)

## FosOS 1.13.13 — Professional desktop polish

- Named `fos_frame` / `fos_frame_inactive` tokens; Inter **11** across
  shell, xsettingsd, Openbox, and greeter fallback
- Flat CSD frames (no drop shadow) matching Openbox and CardWindow
- Flyout width scale: S 280 / M 360 / L 420; Notification Center 360
- Start/Task View 40×36 hit targets; focused task underline 3px; Start
  8px spacing grid and clearer section labels
- Desktop icon selection uses frame greys; boot/greeter/Plymouth neutrals
  aligned to `#0a0a0a` (`fosos-theme` 0.6.2)

## FosOS 1.13.12 — Clearer window frames

- Openbox and CardWindow borders use palette greys (`#737373` active /
  `#404040` inactive) so overlapping windows no longer melt together
- Maximized windows drop the frame (Openbox `keepBorder` off; CardWindow
  CSS); GTK CSD apps keep a soft drop shadow when restored

## FosOS 1.13.1 — Taskbar network freeze polish

- Wi-Fi scan / refresh no longer blocks the GTK main thread (async `nmcli`)
- Network flyout and Settings → Network open immediately, then fill the list
- Secured Wi-Fi password prompt uses FosDialog and holds the flyout grab so
  connecting does not freeze or dismiss the desktop shell
- Right-side taskbar flyouts show first and refresh on idle; duplicate clicks
  while opening are ignored so icons no longer need several tries to open

## FosOS 1.13.0 — Split taskbar status flyouts

- Taskbar icons open dedicated flyouts: Sound, Network & Bluetooth, Brightness,
  Battery; keyboard layout menu unchanged
- Clock / bell open a right-edge calendar + notifications panel (Focus assist
  toggle in the footer)
- Lock / Sign out / Suspend removed from Quick Settings (Start menu only);
  Win+A still opens the tile + slider Quick Settings pane
- Task View button uses a two-pane glyph like Windows 11 (not a generic grid)
- Default taskbar pins: Files, Terminal, Settings, Firefox (Notepad / Remote
  Desktop no longer pre-pinned)
- Taskbar pins: no idle indicator; underline only while open; app icons larger
  than the status-cluster icons
- Desktop icons are full-size (48px) on the wallpaper, not small glyphs in a
  bordered tile

## FosOS 1.12.1 — Taskbar status cluster and Sign out

- Volume and network (with battery/brightness) open one Quick Settings pane
- Taskbar keyboard layout selector (US / PL / …); Settings Apply refreshes it
- Quick Settings adds Sign out beside Lock and Suspend
- Start account Sign out no longer no-ops when the account menu steals the grab

## FosOS 1.12.0 — OS keyring (Secret Service)

- Session starts `gnome-keyring-daemon` (secrets / pkcs11 / ssh) and exports
  sockets to D-Bus so Cursor, Electron, and libsecret clients work
- Depends on `gnome-keyring`, `libpam-gnome-keyring`, and `libsecret-1-0`
  so LightDM can unlock the login keyring with the user password

## FosOS 1.11.0 — Wi-Fi network flyout and Settings

- Taskbar network icon opens a Network flyout (radio switch, scan, join with
  password prompt) instead of only Quick Settings
- Quick Settings Wi-Fi tile and “Network…” open the same flyout
- Settings → Network embeds the Wi-Fi list; Advanced still opens
  `nm-connection-editor`
- Status icon treats `connected (…)` nmcli states as online

## ISO — laptop Wi-Fi firmware

- Live image ships Debian `non-free-firmware` Wi-Fi blobs: `firmware-iwlwifi`,
  `firmware-realtek`, `firmware-atheros`, `firmware-brcm80211`,
  `firmware-mediatek`, `firmware-misc-nonfree`, plus `wireless-regdb`
- Fixes bare-metal installs where the adapter never appeared or could not
  scan because only free `firmware-linux` was present

## FosOS 1.10.0 — Clipboard history and Status Notifier tray

- Super+V clipboard history popup (text snippets, Clear all, paste via
  Ctrl+V inject); history persisted under `~/.config/fosos-desktop/`
- Status Notifier tray on the taskbar (SNI host); nm-applet and other
  StatusNotifierItem apps appear left of Quick Settings

## FosOS 1.9.0 — Notifications and Quick Settings depth

- Quick Settings 2×2 tiles: Wi-Fi, Bluetooth, Focus assist, Mute
- Focus assist naming (was Do not disturb); toggle from Win+A or Settings
- Per-app toast mutes in Settings and Mute/Unmute on Notification Center cards
- Toast timers pause while the pointer is over a popup; stack restacks on resize

## FosOS 1.8.0 — Window chrome and snap feedback

- Edge snap: translucent zone preview while dragging to edges/corners/top
- Win+Left/Right tile to work area (above panel); Win+Down restores from
  maximize or snap, then minimizes; Win+Up maximizes with geometry memory
- CardWindow titlebar: right-click menu (Restore / Minimize / Maximize /
  Snap layouts… / Close); maximize right-click opens snap layouts
- Alt+Tab: larger tiles, stronger selection, Desktop N caption when
  multiple workspaces; Esc / click-chrome dismiss without switching

## FosOS 1.7.0 — Start menu and search polish

- Search: “Type here to search”, clear (×) icon, Esc clears query before
  dismissing; Down/Up highlight results and pinned/recommended rows; Enter
  launches the selection
- Home: Pinned (count only) and Recommended; All apps fixed under the home
  scroller; empty pinned hint; home body scrolls at a fixed height
- Footer: Account (home / Lock / Sign out) on the left, Power only on the
  right (Settings via pin or search)

## FosOS 1.6.1 — xrdp session start + login chrome

- Remove obsolete `ip=` from the Xorg session stanza (xrdp 0.10 uses a
  UNIX socket to sesman; `ip=` caused “‘ip’ is not needed” and bad startup)
- Replace incomplete `sesman.ini` with a Debian 0.10-compatible file
  (`Policy=Separate`, correct `DisconnectedTimeLimit` keys, stock `[Xorg]`
  params using `/usr/lib/xorg/Xorg`)
- `startwm.sh` loads `/etc/profile` then starts `fosos-session` (no longer
  clears `XDG_RUNTIME_DIR`)
- FosOS-branded RDP login: Dawn Aperture banner (“FosOS / Sign in”), dark
  square card, borderless field (`scripts/_gen_xrdp_logo.py`)

## ISO build — hybrid bootloaders for Etcher/USB

- `build-iso.sh` now uses `--bootloaders "grub-pc grub-efi"` with
  `iso-hybrid` so the ISO has an MBR/partition table
- Avoids Balena Etcher “Missing partition table” and broken
  `/run/live/medium` mounts on real USB installs
- Post-build `file` probe warns if the output is not hybrid
- `--debian-installer none` (replaces deprecated `false`)
- Live image includes `zstd`, `plymouth`, `plymouth-label`, and
  `plymouth-themes` to clear initramfs/splash build warnings

## FosOS installer 1.0.2 — harder live squashfs bind for USB

- Replace incomplete/empty `/run/live/medium` mounts before Calamares starts
- Ignore dangling symlinks; search findiso/cdrom fallbacks
- Fixes laptop USB installs that still hit unpackfs “filesystem.squashfs
  does not exist” after 1.0.1

## FosOS installer 1.0.1 — live squashfs path for USB install

- `fosos-calamares` binds `/lib/live/mount/medium` onto `/run/live/medium`
  when needed so Calamares unpackfs finds `live/filesystem.squashfs` on
  real USB boots (Balena Etcher / dd hybrid ISO)
- Fixes “The source filesystem …/filesystem.squashfs does not exist”

## FosOS 1.6.0 — Windows-like RDP host (xrdp)

- Inbound hosting via **xrdp** + **xorgxrdp**: separate FosOS Desktop session
  for any local user; works with nobody signed in on the console
- FosOS-branded xrdp login (Dawn Aperture logo, dark square card chrome)
- Settings → Remote Desktop enable/disable (off by default); Desktop
  `FosOS-Remote-Desktop.rdp` helper on enable
- TLS negotiate + self-signed cert (accept once in mstsc)
- Outbound `fosos-remote` (FreeRDP) unchanged
- Removes FreeRDP console-shadow host from 1.5.0

## FosOS 1.5.0 — bidirectional RDP

- `fosos-remote`: outbound RDP client (FreeRDP) with FosOS card chrome
- Inbound hosting via FreeRDP **shadow** (`freerdp3-shadow-x11`) shares the
  console desktop with mstsc (TLS + PAM, fitted resolution, Desktop `.rdp`
  helper) — superseded by xrdp in 1.6.0
- Off until enabled in Settings → Remote Desktop
- Live image: sign in as `user` / `live` (or use the Desktop `.rdp` file)

## FosOS 1.4.0 — UI improvements (taskbar, desktop grid, Files)

- Taskbar: remove numbered desktop pager; Task View button after Start;
  far-right Show Desktop strip; Ctrl+Win+Left/Right switches desktops;
  right-click empty taskbar → Taskbar settings
- Desktop icons snap to a grid and never overlap; Auto arrange on
  right-click; saved positions migrate onto the grid
- Files: Search keeps focus while typing (Esc clears, Ctrl+F / F3 focus);
  empty-folder vs item context menus; Paste / New folder from background menu

## FosOS 1.3.14 — Phase 14 Settings depth

- Built-in Wallpaper (Dawn / Steel / Graphite / Ink), Taskbar, Notifications
  (Do not disturb, toast duration), Storage, and Updates pages
- Display / Sound / Network / Bluetooth open through chromed Settings pages
- About shows storage summary and reboot-required hint
- Default apps: PDF, archives, images (`.deb` still uses Install Package)

## FosOS 1.3.13 — Phase 13 snap layouts and Task View

- Win+Z / maximize right-click: snap layout presets (2-col, 3-col, 2×2, tall)
  with fill-next assist for remaining regions
- Win+Tab Task View: overview of windows on all four virtual desktops
- Taskbar and Task View: Move to Desktop N
- Drag to left/right edges for halves; corners for quarters; top edge maximizes

## FosOS 1.3.12 — Phase 12 desktop and right-click world

- Desktop context menu: Refresh, Display settings, Personalize, New folder,
  Open Files / Terminal here
- Icons: Home, Computer, Files, Recycle Bin (Install when live); drag to
  reposition; positions saved under `~/.config/fosos-desktop/`
- Settings → Personalize: single- vs double-click icons; reset positions;
  Dawn Aperture wallpaper note

## FosOS 1.3.11 — Phase 11 Files Explorer parity

- Cut / Copy / Paste, multi-select, Select all, F2, Alt+Up, Ctrl+L address bar
- Delete to Recycle Bin with restore; Recycle Bin in sidebar and on the desktop
- Context: Open with, Properties, Copy path, Open Terminal here
- Drag-and-drop between folders with progress for larger transfers

## FosOS 1.3.10 — Phase 10 Quick Settings & Notification Center

- Status cluster opens Quick Settings (Wi-Fi, Bluetooth, volume, brightness, power)
- Clock / bell open Notification Center (calendar + history, Clear all, click-to-focus)
- Shortcuts: Win+A Quick Settings, Win+N Notification Center

## FosOS 1.3.9 — Phase 9 taskbar and Start

- Taskbar: right-click Pin/Unpin, Close window(s), Open new window; drag to reorder pins
- Start search covers apps, settings panels, and recent files
- Recommended recent files/folders; All apps grouped A–Z; account menu Lock / Sign out

## FosOS 1.3.8 — Phase 8 muscle memory

- Super alone opens Start (`xcape`); Super+Space still works
- Win+R Run, Win+X quick links, Win+Shift+S region screenshot
- Alt+Tab hold-to-preview switcher (icon + title)
- Drag window to top edge to maximize; taskbar click cycles/minimizes

## FosOS 1.3.7 — Install downloaded .deb packages

- Opening a `.deb` (Files or browser) launches Install Package instead of xarchiver
- Confirm dialog, then `pkexec apt-get install` for the local file

## FosOS 1.3.6 — Lock screen unlock on live

- Lock used `import pam`, but Debian’s `python3-pam` exports `PAM` — unlock
  always failed with “Incorrect password”
- Switch to `python3-pamela` and `/etc/pam.d/fosos-lock`
- Live unlock accepts blank or password `live`

## FosOS theme 0.6.0 — Phase 7c image shrink

- Dropped `greybird-gtk-theme` and `elementary-xfce-icon-theme` Depends
- gtk-greeter fallback uses FosOS / Adwaita themes
- Live ISO **854405120** bytes (~815 MiB), ~24 MiB under the pre–Phase 7
  baseline — see [ISO-SIZE.md](ISO-SIZE.md)
- Finish Hyper-V soak in [TESTING.md](TESTING.md) before tagging a release ISO

## FosOS 1.3.5 — Login power menu

- Sign in and Unlock: power button bottom-right (Shut down, Restart, Suspend)
- Greeter uses LightDM power APIs; lock uses `systemctl`

## FosOS 1.3.4 / theme 0.5.0 — Dawn Aperture logo + boot menu

- Official mark: **Dawn Aperture** (`fosos-dawn-aperture.svg`)
- Used in the greeter/lock mark, Start header, Settings, desktop watermark
- Live GRUB first screen: dark FosOS splash (logo + FosOS / phos · light),
  neutral menu theme, entries labelled **FosOS Live**, 8s timeout
- Theme package **0.5.0**, desktop **1.3.4**

## FosOS 1.3.3 — Single-session Sign in

- Greeter always starts **FosOS Desktop** (no Session dropdown)
- FosOS Recovery remains installed; select it via `~/.dmrc` or use a TTY

## FosOS 1.3.2 — Shell survives CSS/data faults

- `fosos-shell` crash log: `~/.config/fosos-desktop/shell-crash.log` and `shell.log`
- CSS load failures no longer abort the shell
- Desktop keeps a solid background if wallpaper module is missing
- Session sets a fallback root colour via `xsetroot`

## FosOS 1.3.1 — Greeter black-screen fix

- Greeter no longer imports the Wnck/panel shell stack (caused LightDM seat failure / black screen on live)
- Wallpaper drawing lives in `fosdesk.wallpaper` for greeter + lock + desktop
- Crash log at `/var/log/lightdm/fosos-greeter-crash.log` (or `/tmp`)
- Live greeter defaults to username `user` and completes LightDM autologin hints
- Live and installed systems both use `fosos-greeter` (GTK greeter remains installed as fallback)

### Packages to ship

- `fosos-desktop` **1.3.1**

## FosOS 1.3.0 — FosOS greeter

- `fosos-greeter` replaces `lightdm-gtk-greeter` as the default LightDM greeter
- Two-column Sign in layout (brand panel + form), matching the desktop mockup
- Lock screen uses the same layout (Unlock)
- Session picker removed in **1.3.3** (always FosOS Desktop)
- `lightdm-gtk-greeter` remains installed as a fallback

## FosOS 1.2.x — Phase 7 complete (packaging)

Phase 7a–7c packaging is ready for a rebuilt ISO:

- No XFCE login session; FosOS Recovery + TTY fallback
- No `xfce4-*` Depends on `fosos-desktop` / `fosos-theme`
- Built-in settings panels, `arandr`, `fosos-screenshot`, `xsettingsd`
- Theme cleanup: removed XFCE xfconf defaults (`fosos-theme` **0.4.0**)
- Size tracking: [ISO-SIZE.md](ISO-SIZE.md) — fill in after your rebuild

### Packages to ship

- `fosos-desktop` **1.2.0**
- `fosos-theme` **0.4.0**

## FosOS 1.2 — Unbundled settings (Phase 7b)

No `xfce4-*` packages remain in `fosos-desktop` or `fosos-theme` Depends.

- Built-in Settings panels for keyboard, mouse, default apps and power
- Display layout via `arandr`
- `fosos-screenshot` (`scrot`) replaces `xfce4-screenshooter`
- `xsettingsd` replaces `xfsettingsd` / xfconf theme switching
- Packages: `fosos-desktop` **1.2.0**, `fosos-theme` **0.3.0**

## FosOS 1.1 — FosOS-only desktop (Phase 7a)

FosOS Desktop remains the default session. The XFCE login session is removed
from the image. **FosOS Recovery** (Openbox + terminal) and text consoles are
the fallback. The live package list drops the `xfce4` metapackage, Thunar,
Mousepad, xfce4-terminal and XFCE panel/notification plugins to shrink the ISO.
Shared `xfce4-settings` / power-manager / screenshooter packages remain until
Phase 7b.

### Packages

- `fosos-desktop` **1.1.0** — recovery session, no Thunar/xfce4-terminal Depends
- `fosos-theme` **0.2.0** — drops `xfdesktop4`; polkit autostart is FosOS-only

### Upgrade notes

- Accounts with `Session=xfce` in `~/.dmrc` should pick **FosOS Desktop** or
  **FosOS Recovery** on the greeter after upgrade (XFCE will no longer be listed).
- See [RECOVERY.md](RECOVERY.md).

## FosOS 1.0 — FosOS Desktop default

FosOS 1.0 made **FosOS Desktop** the default login session. XFCE was still
selectable as a fallback at that release; that fallback is removed in 1.1.

### What changed in 1.0

- Default LightDM session is `fosos-desktop`
- Session entry labelled **FosOS Desktop**
- Failed-shell recovery terminal and [RECOVERY.md](RECOVERY.md)

### Desktop features (from Phase 5)

- Panel, Start menu, desktop, notifications
- Files, Terminal, Notepad, Settings
- Screen lock, multi-monitor taskbars, battery/brightness, four workspaces

### Test before promoting

Run the soak in [TESTING.md](TESTING.md), including FosOS Recovery and TTY
paths. Prefer the dedicated Debian 13 release builder for the ISO you ship.
