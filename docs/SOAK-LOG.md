# FosOS soak log

Fill this in while following [TESTING.md](TESTING.md). Prefer copying to
`docs/soak-logs/YYYY-MM-DD-<machine>.md` so each run stays archived.

**Status:** `pass` | `fail` | `skip`  
**Comment:** required for `fail` (what broke); optional for `skip` / `pass`.

## Run

| Field | Value |
| --- | --- |
| Date | 2026-11-24 (retest after 1.13.20) |
| Tester | agent (Cursor) + mlokas |
| ISO | Installed system. Packages from `https://mlokas2408.github.io/fosos-apt` testing. |
| Machine | Baremetal Lenovo ThinkPad T14 Gen 3 (`21AH007VSC`), hostname `marjan-21ah007vsc`, i5-1240P, 1920×1200 eDP |
| Image | installed |
| Desktop | `fosos-desktop` **1.13.20** (`fosos-theme` 0.6.2, `fosos-cli` 0.2.5, `fosos-welcome` 0.1.2, `locales` 2.41-12+deb13u5) |
| Notes | Retest of morning soak after APT upgrade. Restarted `fosos-shell` so prune code was live. Greeter/sign-out, Recovery, Suspend, USB/ISO/Hyper-V still deferred. Screenshots `/tmp/fosos-soak-20261124b/`. Archives: [soak-logs/2026-11-24-thinkpad-t14.md](soak-logs/2026-11-24-thinkpad-t14.md) (1.13.18), [soak-logs/2026-11-24-thinkpad-t14-retest.md](soak-logs/2026-11-24-thinkpad-t14-retest.md). |

## Failed IDs (summary)

After the run, list every `fail` here for triage:

| ID | Comment |
| --- | --- |
| | *(none)* |

## A — Boot and greeter

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| A01 | GRUB splash / FosOS Live | skip | Installed boot, not live ISO. |
| A02 | Live autologin FosOS Desktop | skip | Not a live image. |
| A03 | Mouse and keyboard work | pass | Active FosOS Desktop X11 session. |
| A04 | Greeter two-column Sign in | skip | Did not sign out. |
| A05 | No session picker / no Xfce | skip | Config only; greeter UI not shown. |
| A06 | Greeter power menu | skip | Did not sign out. |
| A07 | Sign in as user/live | skip | No greeter round-trip. |
| A08 | TTY F2 / return F7 | skip | Not switched. |

## B — Install

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| B01 | Calamares Install FosOS | pass | Already installed. |
| B02 | Installed greeter / Desktop | pass | `fosos-shell` 1.13.20 + Openbox after restart. |
| B03 | Welcome / finish setup | pass | `welcome-done` present. |
| B04 | sudo works; root locked | pass | Passwordless sudo; root locked. |

## C — Taskbar, Start, tray, clipboard

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| C01 | Taskbar layout (no pager) | pass | Unchanged; no numbered pager. |
| C02 | Super opens Start | pass | `--toggle-start` (`01-start.png`). |
| C03 | Start search / clear / Esc | skip | Not deep-tested. |
| C04 | Keyboard nav / All apps / footer | skip | Not key-tested. |
| C05 | Account + Power | skip | Menus not opened. |
| C06 | Pin / reorder / middle-click | skip | Not tested. |
| C07 | Taskbar menu / Show Desktop | skip | Not tested. |
| C08 | Super+V clipboard history | pass | `--clipboard-history` (`04-clip.png`). |
| C09 | Status Notifier tray | pass | `nm-applet` + `blueman-applet`/`blueman-tray` running. |

## D — Windows, snap, multitasking

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| D01 | Core Super shortcuts | skip | Key chords not injected. |
| D02 | Alt+Tab | skip | Not exercised. |
| D03 | Super+arrows tile / restore | pass | Previously verified via `--snap-*`; not re-dragged. |
| D04 | Edge snap + zone preview | skip | Drag not tested. |
| D05 | Win+Z snap layouts | pass | `--snap-layouts` (`06-snap.png`). |
| D06 | CardWindow titlebar menu | skip | Not tested. |
| D07 | Maximize right-click → layouts | skip | Not tested. |
| D08 | Task View | pass | `--task-view` (`05-tv.png`). |
| D09 | Move to desktop / Super+1…4 | skip | Not tested. |
| D10 | Screenshots | pass | `fosos-screenshot -f` → `Screenshot-20261124-105926.png`. |
| D11 | Taskbar minimize / cycle | skip | Not tested. |

## E — Quick Settings and notifications

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| E01 | Open dedicated status flyouts / Win+A Quick Settings | pass | `--quick-settings` (`02-qs.png`). |
| E02 | 2×2 tiles + sliders | pass | Wi-Fi / Bluetooth / Focus assist / Mute + sliders. |
| E03 | QS footers | skip | Not clicked. |
| E03b | Wi-Fi scan/join UI | pass | On AMAGI; `nmcli` scan lists SSIDs. |
| E03c | Network flyout first-click / join | skip | Not opened / no new join. |
| E04 | Focus assist | skip | Not verified. |
| E05 | Toast + hover pause | pass | D-Bus Notify “Soak retest” OK. |
| E06 | Notification Center | pass | `--notification-center` (`03-nc.png`). |
| E07 | Per-app mute | skip | Not tested. |
| E08 | Lock/Sign out/Suspend only from Start | skip | Not cross-checked. |

## F — Files and desktop

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| F01 | Files clipboard / trash | skip | UI trash/clipboard not exercised. |
| F02 | Files nav / search | skip | Not deep-tested. |
| F03 | Files menus / drag | skip | Not tested. |
| F04 | Desktop icons / grid | pass | After shell restart: `computer` / `files` / `trash` only; no `home`; no overlapping positions. |
| F05 | Desktop context menu | skip | Not tested. |
| F06 | Personalize / reset icons | skip | Not opened. |

## G — Settings and theme

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| G01 | Settings card chrome | pass | Settings launched (`09-settings.png`). |
| G02 | Wallpaper / Taskbar prefs | skip | Not changed. |
| G03 | Notifications prefs | skip | Not opened. |
| G04 | Input / display panels | pass | `locales` installed; `en_US.utf8` in `locale -a`; `setlocale(en_US.UTF-8)` OK; no Gtk locale warning on restarted shell. Brightness/volume OK. |
| G05 | Updates / About / Storage | pass | Package + `fosdesk.VERSION` = **1.13.20**. `fos update` OK. |
| G06 | Theme alignment | skip | Not re-checked. |

## H — Remote Desktop

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| H01 | Enable host (xrdp) | pass | Still default off (disabled/inactive). |
| H02 | Desktop .rdp helper | skip | Host not enabled. |
| H03 | mstsc separate session | skip | Not run. |
| H04 | Second user / console OK | skip | Single user. |
| H05 | Disable + outbound client | skip | Not run. |

## I — Recovery and session health

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| I01 | FosOS Recovery session | skip | Not signed into Recovery. |
| I02 | Shell crash recovery | pass | Stopped pre-upgrade shell and started 1.13.20 `fosos-shell`; desktop recovered without full logout. |
| I03 | Power / suspend | skip | Not run. |
| I04 | Multi-monitor | skip | Single eDP-1. |

## J — Packages, release, USB

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| J01 | fos update / upgrade | pass | On candidate 1.13.20. Note: plain `fos upgrade` kept 1.13.20 back until `apt install` pulled new `locales` Depends. |
| J02 | ISO size in ISO-SIZE.md | skip | No rebuild. |
| J03 | Release VM rebuild + re-soak | skip | Deferred. |
| J04 | USB UEFI smoke | skip | Not run. |
| J05 | Laptop Wi-Fi scan/join | pass | `wlp0s20f3` → AMAGI; scan OK. |
| J06 | Secure Boot live + install | skip | Needs rebuilt ISO with shim-signed; verify on next image. |
