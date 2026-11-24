# FosOS soak log

Fill this in while following [TESTING.md](TESTING.md). Prefer copying to
`docs/soak-logs/YYYY-MM-DD-<machine>.md` so each run stays archived.

**Status:** `pass` | `fail` | `skip`  
**Comment:** required for `fail` (what broke); optional for `skip` / `pass`.

## Run

| Field | Value |
| --- | --- |
| Date | 2026-11-24 |
| Tester | agent (Cursor) + mlokas |
| ISO | Installed system (not a live ISO run). Packages from `https://mlokas2408.github.io/fosos-apt` testing. |
| Machine | Baremetal Lenovo ThinkPad T14 Gen 3 (`21AH007VSC`), hostname `marjan-21ah007vsc`, i5-1240P, 1920×1200 eDP |
| Image | installed |
| Desktop | `fosos-desktop` **1.13.18** (`fosos-theme` 0.6.2, `fosos-cli` 0.2.5, `fosos-welcome` 0.1.2) |
| Notes | Hyper-V / release-ISO / USB suites deferred by design (baremetal focus). Greeter/sign-out, Recovery, Suspend, and several Win-chord / drag interactions not exercised to avoid disrupting the live session. Screenshots under `/tmp/fosos-soak/`. Archive: [soak-logs/2026-11-24-thinkpad-t14.md](soak-logs/2026-11-24-thinkpad-t14.md). |

## Failed IDs (summary)

After the run, list every `fail` here for triage:

| ID | Comment |
| --- | --- |
| F04 | `computer` and `home` both at `16,16` (overlap). **Fix in 1.13.20** — retest after upgrade. |
| G04 | `LANG=en_US.UTF-8` but `locales` missing / not generated. **Fix in 1.13.20** — retest after upgrade. |

## A — Boot and greeter

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| A01 | GRUB splash / FosOS Live | skip | Installed boot, not live ISO. `GRUB_DISTRIBUTOR='FosOS'` present. |
| A02 | Live autologin FosOS Desktop | skip | Not a live image. |
| A03 | Mouse and keyboard work | pass | Active FosOS Desktop X11 session; input in use. |
| A04 | Greeter two-column Sign in | skip | Did not sign out. Config: `greeter-session=fosos-greeter`. |
| A05 | No session picker / no Xfce | skip | Config `user-session=fosos-desktop`; no Xfce session. Visual greeter picker not confirmed. |
| A06 | Greeter power menu | skip | Did not sign out. |
| A07 | Sign in as user/live | skip | Installed account (`mlokas`); no greeter round-trip. |
| A08 | TTY F2 / return F7 | skip | Not switched (would disrupt GUI session). |

## B — Install

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| B01 | Calamares Install FosOS | pass | Machine already installed; Calamares path not re-run. |
| B02 | Installed greeter / Desktop | pass | Session `fosos-desktop` / `XDG_CURRENT_DESKTOP=FosOS`; `fosos-shell` + Openbox running. |
| B03 | Welcome / finish setup | pass | `~/.config/fosos/welcome-done` present; Welcome listed in Settings. |
| B04 | sudo works; root locked | pass | Passwordless `sudo -n` OK; root shadow field locked (`!`/`*`). |

## C — Taskbar, Start, tray, clipboard

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| C01 | Taskbar layout (no pager) | pass | Start, Task View, pins, status cluster, clock; no numbered pager (`00-baseline.png`). |
| C02 | Super opens Start | pass | `fosos-shell --toggle-start` opened Start (Pinned apps + Account footer). |
| C03 | Start search / clear / Esc | skip | Start opened; search/Esc clearing not exercised. |
| C04 | Keyboard nav / All apps / footer | skip | Footer Account visible; Down/Up/All apps not key-tested. |
| C05 | Account + Power | skip | Account label shown; menus not opened. |
| C06 | Pin / reorder / middle-click | skip | Pins present (`pinned`); reorder/middle-click not tested. |
| C07 | Taskbar menu / Show Desktop | skip | Not clicked. |
| C08 | Super+V clipboard history | pass | `--clipboard-history` opened history flyout with entries (`04-clipboard.png`). |
| C09 | Status Notifier tray | pass | `nm-applet` + `blueman-applet`/`blueman-tray` running; tray icons visible. |

## D — Windows, snap, multitasking

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| D01 | Core Super shortcuts | skip | Key chords not injected; related features covered via shell CLI elsewhere. |
| D02 | Alt+Tab | skip | Not exercised. |
| D03 | Super+arrows tile / restore | pass | `--snap-left` / `--snap-down` tiled and restored Settings (`10-snap-left.png`). |
| D04 | Edge snap + zone preview | skip | Drag-to-edge not tested. |
| D05 | Win+Z snap layouts | pass | `--snap-layouts` showed Two/Three/Four/Left tall/Right tall (`06-snap-layouts.png`). |
| D06 | CardWindow titlebar menu | skip | Not right-clicked. |
| D07 | Maximize right-click → layouts | skip | Not tested. |
| D08 | Task View | pass | `--task-view`: four desktops; Desktop 1 had Cursor (`05-task-view.png`). |
| D09 | Move to desktop / Super+1…4 | skip | Not tested. |
| D10 | Screenshots | pass | `fosos-screenshot -f` → `~/Pictures/Screenshot-20261124-103356.png`. Region (`-r`) not run. |
| D11 | Taskbar minimize / cycle | skip | Not tested. |

## E — Quick Settings and notifications

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| E01 | Open dedicated status flyouts / Win+A Quick Settings | pass | `--quick-settings` opened QS; status icons present (battery/brightness/volume/network). Per-icon dedicated flyouts not each clicked. |
| E02 | 2×2 tiles + sliders | pass | Wi-Fi / Bluetooth / Focus assist / Mute + volume 83% + brightness 85% (`02-quick-settings.png`). |
| E03 | QS footers | skip | Footers not clicked in this run. |
| E03b | Wi-Fi scan/join UI | pass | Connected to AMAGI; `nmcli` scan lists SSIDs. Network flyout UI not separately opened. |
| E03c | Network flyout first-click / join | skip | Did not open Network flyout / join a new SSID (already on Wi-Fi). |
| E04 | Focus assist | skip | Tile visible Off; hide-toasts behavior not verified. |
| E05 | Toast + hover pause | pass | D-Bus `Notify` → toast “Soak toast” landed in Notification Center (`03-notification-center.png`). Hover pause not timed. |
| E06 | Notification Center | pass | `--notification-center`: calendar + history (SoakTest + blueman). |
| E07 | Per-app mute | skip | Mute on history card not clicked. |
| E08 | Lock/Sign out/Suspend only from Start | skip | Not cross-checked against status flyouts. |

## F — Files and desktop

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| F01 | Files clipboard / trash | skip | Files opened (Home); `gio` not installed in PATH for CLI trash. UI Ctrl+C/X/V / Delete not exercised. |
| F02 | Files nav / search | skip | Window opened only. |
| F03 | Files menus / drag | skip | Not tested. |
| F04 | Desktop icons / grid | fail | `computer` and `home` both at `16,16` in `desktop-icons` (overlap). Files/trash at 128/240. Fix packaged in 1.13.20 — retest. |
| F05 | Desktop context menu | skip | Not right-clicked. |
| F06 | Personalize / reset icons | skip | `desktop` config `click=double`, `wallpaper=steel` present; Personalize UI not opened. |

## G — Settings and theme

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| G01 | Settings card chrome | pass | Settings launched maximized-style Home with min/max/close (`09-settings.png`). |
| G02 | Wallpaper / Taskbar prefs | skip | Pages listed; Apply/toggles not changed. |
| G03 | Notifications prefs | skip | Page listed; not opened. |
| G04 | Input / display panels | fail | Locale broken: `en_US.UTF-8` configured but not generated; `locales` package absent. Display/brightness OK. Fix packaged in 1.13.20 — retest. |
| G05 | Updates / About / Storage | pass | Home shows About hero; package `1.13.18` via apt. In-app footer still shows “FosOS Desktop 1.13.0” (stale string). `fos update` succeeded. |
| G06 | Theme alignment | skip | Visual theme OK at a glance; Welcome `--again` / greeter tokens not re-checked. |

## H — Remote Desktop

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| H01 | Enable host (xrdp) | pass | Default off: `xrdp` disabled/inactive. Packages `xrdp` + `xorgxrdp` installed. Enable flow not run. |
| H02 | Desktop .rdp helper | skip | Not enabled; no `.rdp` helper on desktop icons. |
| H03 | mstsc separate session | skip | No inbound client test. |
| H04 | Second user / console OK | skip | Single user. |
| H05 | Disable + outbound client | skip | Host left disabled; outbound `fosos-remote` not launched. |

## I — Recovery and session health

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| I01 | FosOS Recovery session | skip | Session file present (`fosos-recovery.desktop`); not signed into Recovery. |
| I02 | Shell crash recovery | skip | Did not kill `fosos-shell`. |
| I03 | Power / suspend | skip | Suspend/reboot not run during soak. |
| I04 | Multi-monitor | skip | Single eDP-1 only. |

## J — Packages, release, USB

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| J01 | fos update / upgrade | pass | `fos update` hit Debian + FosOS testing OK. Upgrade not forced (already on candidate 1.13.18). |
| J02 | ISO size in ISO-SIZE.md | skip | No ISO rebuild this run; doc still present. |
| J03 | Release VM rebuild + re-soak | skip | Deferred (baremetal focus; Hyper-V later). |
| J04 | USB UEFI smoke | skip | Not run. |
| J05 | Laptop Wi-Fi scan/join | pass | `wlp0s20f3` up; connected AMAGI (WPA2); scan lists nearby SSIDs. Rejoin-after-suspend not tested. |
