# FosOS testing

Aligned to the current product (`fosos-desktop` **1.13.20**). Development
images are built in Debian WSL and tested on bare metal (and optionally
Hyper-V). A release image is built again on the dedicated Debian 13 VM,
then put through the same soak before USB. See [BUILDING.md](BUILDING.md).

## How to record results

1. Copy [SOAK-LOG.md](SOAK-LOG.md) to a dated file, for example
   `docs/soak-logs/2026-11-18-hyperv.md` (create the folder if needed), **or**
   edit [SOAK-LOG.md](SOAK-LOG.md) in place for a single working copy.
2. Fill the header (ISO path, builder, machine, date, tester).
3. For each row set **Status** to one of:
   - `pass` — behaved as described
   - `fail` — wrong or broken; **Comment** must say what you saw
   - `skip` — not run (no hardware, no second monitor, etc.); optional note
4. Leave Comment empty on passes unless useful.
5. When fixing bugs, filter the log for `fail` and work those IDs first.
   After a fix, re-run only the failed IDs (and close dependents) on a fresh
   boot or install as needed.

Test **IDs** below match the columns in the soak log. Do not renumber IDs
casually; append new ones at the end of a section if the product grows.

## Credentials

| Context | Account | Password |
| --- | --- | --- |
| Live image | `user` | `live` (TTY / lock; `sudo` is passwordless) |
| Installed system | Account created in Calamares | As chosen |

Live image autologins to **FosOS Desktop** via LightDM. Root stays locked.
Console auto-login is off so a TTY does not steal the graphical session.

## Headless desktop check (before Hyper-V)

On Debian 13 WSL, from the repository root:

```bash
sudo bash scripts/test-desktop.sh
```

Review screenshots in `output/desktop/`. This does not replace the Hyper-V
soak; it catches shell crashers and layout regressions early.

## Hyper-V setup

1. Generation 2 VM, ~4 GB RAM, 2 vCPUs. Attach a ≥16 GB VHD when testing install.
2. Attach `output/FosOS-trixie-amd64.iso` as DVD; boot DVD first.
3. **Secure Boot on** with template **MicrosoftUEFICertificateAuthority**
   (required for Debian `shim-signed`). `scripts/hyperv-smoke.ps1` sets this.
4. Prefer `hyperv_drm` (image blacklists `hyperv_fb`). If the desktop paints
   but mouse/keyboard are dead, check TTY / rebuild with the DRM hook; see
   [RECOVERY.md](RECOVERY.md).

## Suites

Run **A** on every image. Run **B** when testing install. Run **C–J** on
live and again on an installed system before a release tag. Mark each ID in
the soak log.

### A — Boot and greeter

| ID | Check |
| --- | --- |
| A01 | After firmware logo: no blue GRUB / no grey three-dot text fallback / no boot console text; Dawn Aperture Plymouth logo+spinner until greeter (Shift shows GRUB). Needs theme ≥0.7.5 (early KMS + framebuffer splash). Live ISO also shows FosOS Live menu when Shift held. Shut down / Restart show the same splash with Shutting down / Restarting (not terminal stop text). |
| A02 | Live boots and autologins to **FosOS Desktop** (taskbar, Start, wallpaper) |
| A03 | Mouse and keyboard work in the live session |
| A04 | Sign out → greeter is two-column FosOS Sign in (not gtk-greeter / Greybird) |
| A05 | Greeter has no session picker (always Desktop); no Xfce Session entry |
| A06 | Greeter power menu: Shut down, Restart, Suspend |
| A07 | Sign in as `user` / `live` returns to FosOS Desktop |
| A08 | Ctrl+Alt+F2 TTY accepts `user` / `live`; Ctrl+Alt+F7 returns to desktop |

### B — Install

| ID | Check |
| --- | --- |
| B01 | **Install FosOS** (Calamares): language, keyboard, disk, optional encryption, account |
| B02 | After reboot (ISO detached): greeter Sign in; default session FosOS Desktop |
| B03 | Welcome shows network status; can open guide / updates; finish setup |
| B04 | Installed account can `sudo` without a password; root remains locked |

### C — Taskbar, Start, tray, clipboard

| ID | Check |
| --- | --- |
| C01 | Taskbar: Start, Task View button (no numbered 1–4 pager), pins, status cluster, clock, Show Desktop strip |
| C02 | Super tap / Super+Space / Alt+F1 opens Start |
| C03 | Start search: clear (×); Esc clears then dismisses; finds app, settings panel, recent file |
| C04 | Start: Down/Up highlight + Enter launch; All apps under home with A–Z; Account left / Power right |
| C05 | Start Account menu: home, Lock, Sign out; Power confirm (Shut down / Restart / Suspend / Lock) |
| C06 | Taskbar: pin/unpin, drag reorder survives restart, middle-click opens new window |
| C07 | Taskbar right-click empty → Taskbar settings; Show Desktop strip = Win+D |
| C08 | Super+V clipboard history: several copies listed; pick pastes; Clear all empties |
| C09 | Status Notifier tray left of status cluster (e.g. nm-applet); left-click activates |

### D — Windows, snap, multitasking

| ID | Check |
| --- | --- |
| D01 | Super+E / Super+I / Ctrl+Alt+T / Super+L / Super+R / Super+X work |
| D02 | Alt+Tab: larger selected tile; Esc cancels without switch; release Alt focuses |
| D03 | Super+↑ maximize; Super+←/→ tile above panel; Super+↓ restore-from-snap then minimize |
| D04 | Drag to edge/corner: zone preview then half/quarter; top edge maximizes |
| D05 | Win+Z snap layouts; remaining regions fill on next focus; Clear assist works |
| D06 | CardWindow titlebar right-click: Restore / Minimize / Maximize / Snap layouts / Close |
| D07 | Maximize button right-click opens snap layouts |
| D08 | Win+Tab Task View: four desktops; click window to switch; Esc closes |
| D09 | Move window to Desktop N (Task View or taskbar app menu); Super+1…4 / Ctrl+Win+←/→ |
| D10 | Super+Shift+S / Shift+Print region capture; Print full → under Pictures |
| D11 | Taskbar: focused single window toggles minimize; multi-window cycles |

### E — Status flyouts and notifications

| ID | Check |
| --- | --- |
| E01 | Sound / Battery / Brightness icons open their own flyouts; network opens Network & Bluetooth; Win+A opens Quick Settings |
| E02 | Win+A: 2×2 tiles (Wi-Fi, Bluetooth, Focus assist, Mute) + volume/brightness sliders; no Lock / Sign out / Suspend |
| E03 | QS footers: Settings / Sound… / Network… (Network… → flyout with scan/join) |
| E03b | Network flyout: Wi-Fi list + Bluetooth toggle; Network… / Bluetooth… footers; Settings → Network still embeds Wi-Fi picker |
| E03c | Network flyout opens on first click (no multi-click); join open/WPA2 SSID without freezing desktop; Refresh stays responsive |
| E04 | Focus assist (QS tile or NC footer) hides new toasts; history still in Win+N |
| E05 | `notify-send Test "Hello"` toast above panel; hover pauses expire |
| E06 | Win+N / clock / bell: right-edge calendar + history; Clear all; click item focuses app when possible |
| E07 | Mute / Unmute on a history card suppresses that app’s toasts only |
| E08 | Lock / Sign out / Suspend only from Start (account / power), not from status flyouts |

### F — Files and desktop

| ID | Check |
| --- | --- |
| F01 | Files: Ctrl+C/X/V, multi-select, Delete → Recycle Bin, restore |
| F02 | Files: F2, Alt+Up, Ctrl+L; Search keeps focus; Esc clears Search |
| F03 | Files context menus (item vs empty folder); drag into folders |
| F04 | Desktop icons (Computer, Files, Recycle Bin — no Home); grid snap; no overlap; restart keeps place |
| F05 | Desktop right-click: Refresh, Auto arrange, Display, Personalize, New folder, Open Files/Terminal |
| F06 | Personalize single-click vs double-click; Reset icon positions + F5 |

### G — Settings and theme

| ID | Check |
| --- | --- |
| G01 | Settings card chrome (min/max/close) matches Files |
| G02 | Wallpaper Apply refreshes desktop; Taskbar toggles Task View / clock date / bell |
| G03 | Notifications: Focus assist + per-app mute list after apps have notified |
| G04 | Keyboard, mouse, default apps, power panels; Display (`arandr`) apply; `en_US.UTF-8` (or chosen LANG) present in `locale -a` with no Gtk locale warnings |
| G05 | Updates / About / Storage sensible; Check/Install updates open Terminal with `fos …` |
| G06 | Theme: Welcome `--again`, greeter/lock card tokens, shared 16px popup padding |

### H — Remote Desktop

| ID | Check |
| --- | --- |
| H01 | Settings → Remote Desktop off by default; enable → pkexec → IP, port 3389, separate session |
| H02 | Desktop `FosOS-Remote-Desktop.rdp` helper appears on enable |
| H03 | Windows mstsc: cert once → FosOS xrdp login → separate FosOS Desktop (not console share) |
| H04 | Second local user RDP works; console/greeter unaffected |
| H05 | Disable refuses new connections; `fosos-remote` connects out to another RDP host |

### I — Recovery and session health

| ID | Check |
| --- | --- |
| I01 | Sign out → FosOS Recovery session: Openbox + terminal |
| I02 | Kill `fosos-shell` until recovery terminal; can restart shell / use Recovery / TTY |
| I03 | Shutdown, reboot, suspend/resume (VM or hardware) |
| I04 | Multi-monitor (if available): panel per display; windows on correct taskbar |

### J — Packages, release, USB

| ID | Check |
| --- | --- |
| J01 | Installed: `fos update` / `fos upgrade` (or apt) of FosOS packages |
| J02 | ISO byte size recorded in [ISO-SIZE.md](ISO-SIZE.md) after rebuild |
| J03 | Release ISO built on dedicated Debian 13 VM (not WSL-only) and re-soaked in Hyper-V |
| J04 | USB UEFI smoke: network, display, keyboard/touchpad, audio, suspend, boot/reboot on disposable media only |
| J05 | Laptop Wi-Fi: `wlan*` present (`ip link`); scan shows SSIDs; join WPA2 via tray/QS or Settings; reconnect after suspend if practical |
| J06 | Secure Boot on: live ISO boots; after Calamares install, reboot with Secure Boot still on (Hyper-V Gen2 + selected bare metal) |

## Release gate

Before tagging a release:

1. Rebuild on the dedicated Debian 13 VM ([BUILDING.md](BUILDING.md)).
2. Complete a soak log with no open `fail` rows (or explicitly accepted skips).
3. Record ISO size in [ISO-SIZE.md](ISO-SIZE.md).
4. Note the result against [RELEASE-NOTES.md](RELEASE-NOTES.md).

Do not publish an ISO that was built only in WSL.
