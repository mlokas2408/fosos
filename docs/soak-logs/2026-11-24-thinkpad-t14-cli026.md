# FosOS soak log

Fill this in while following [TESTING.md](TESTING.md). Prefer copying to
`docs/soak-logs/YYYY-MM-DD-<machine>.md` so each run stays archived.

**Status:** `pass` | `fail` | `skip`  
**Comment:** required for `fail` (what broke); optional for `skip` / `pass`.

## Run

| Field | Value |
| --- | --- |
| Date | 2026-11-24 (retest after fosos-cli 0.2.6 / installer 1.0.4 publish) |
| Tester | agent (Cursor) + mlokas |
| ISO | Installed system. Packages from `https://mlokas2408.github.io/fosos-apt` testing. |
| Machine | Baremetal Lenovo ThinkPad T14 Gen 3 (`21AH007VSC`), hostname `marjan-21ah007vsc` |
| Image | installed |
| Desktop | `fosos-desktop` **1.13.20**, `fosos-cli` **0.2.6**, `fosos-theme` 0.6.2 (`fosos-installer` not installed on target — expected) |
| Notes | No open `fail` rows. Secure Boot packages (`shim-signed` etc.) **not** on this disk yet — need new ISO / reinstall for J06. Screenshots `/tmp/fosos-soak-20261124c/`. Prior archives under `docs/soak-logs/`. |

## Failed IDs (summary)

| ID | Comment |
| --- | --- |
| | *(none)* |

## A — Boot and greeter

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| A01 | GRUB splash / FosOS Live | skip | Installed boot. NVRAM entry `FosOS` → `\EFI\FosOS\grubx64.efi` (unsigned path). |
| A02 | Live autologin FosOS Desktop | skip | Not live. |
| A03 | Mouse and keyboard work | pass | Active session. |
| A04 | Greeter two-column Sign in | skip | Did not sign out. |
| A05 | No session picker / no Xfce | skip | Config only. |
| A06 | Greeter power menu | skip | Did not sign out. |
| A07 | Sign in as user/live | skip | No greeter round-trip. |
| A08 | TTY F2 / return F7 | skip | Not switched. |

## B — Install

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| B01 | Calamares Install FosOS | pass | Already installed. |
| B02 | Installed greeter / Desktop | pass | `fosos-shell` + Openbox. |
| B03 | Welcome / finish setup | pass | `welcome-done` present. |
| B04 | sudo works; root locked | pass | Passwordless sudo; root locked. |

## C — Taskbar, Start, tray, clipboard

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| C01 | Taskbar layout (no pager) | pass | OK. |
| C02 | Super opens Start | pass | `--toggle-start`. |
| C03 | Start search / clear / Esc | skip | Not deep-tested. |
| C04 | Keyboard nav / All apps / footer | skip | Not key-tested. |
| C05 | Account + Power | skip | Not opened. |
| C06 | Pin / reorder / middle-click | skip | Not tested. |
| C07 | Taskbar menu / Show Desktop | skip | Not tested. |
| C08 | Super+V clipboard history | pass | `--clipboard-history`. |
| C09 | Status Notifier tray | pass | `nm-applet` + `blueman-applet`. |

## D — Windows, snap, multitasking

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| D01 | Core Super shortcuts | skip | Not injected. |
| D02 | Alt+Tab | skip | Not tested. |
| D03 | Super+arrows tile / restore | skip | Not re-run this pass. |
| D04 | Edge snap + zone preview | skip | Not tested. |
| D05 | Win+Z snap layouts | pass | `--snap-layouts`. |
| D06 | CardWindow titlebar menu | skip | Not tested. |
| D07 | Maximize right-click → layouts | skip | Not tested. |
| D08 | Task View | pass | `--task-view`. |
| D09 | Move to desktop / Super+1…4 | skip | Not tested. |
| D10 | Screenshots | pass | `Screenshot-20261124-111720.png`. |
| D11 | Taskbar minimize / cycle | skip | Not tested. |

## E — Quick Settings and notifications

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| E01 | Open dedicated status flyouts / Win+A Quick Settings | pass | `--quick-settings`. |
| E02 | 2×2 tiles + sliders | pass | OK. |
| E03 | QS footers | skip | Not clicked. |
| E03b | Wi-Fi scan/join UI | pass | On AMAGI; scan lists SSIDs. |
| E03c | Network flyout first-click / join | skip | Not opened. |
| E04 | Focus assist | skip | Not verified. |
| E05 | Toast + hover pause | pass | D-Bus Notify OK. |
| E06 | Notification Center | pass | `--notification-center`. |
| E07 | Per-app mute | skip | Not tested. |
| E08 | Lock/Sign out/Suspend only from Start | skip | Not cross-checked. |

## F — Files and desktop

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| F01 | Files clipboard / trash | skip | Not exercised. |
| F02 | Files nav / search | skip | Not deep-tested. |
| F03 | Files menus / drag | skip | Not tested. |
| F04 | Desktop icons / grid | pass | `computer` / `files` / `trash`; no `home`; no overlaps. |
| F05 | Desktop context menu | skip | Not tested. |
| F06 | Personalize / reset icons | skip | Not opened. |

## G — Settings and theme

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| G01 | Settings card chrome | skip | Not re-opened this pass. |
| G02 | Wallpaper / Taskbar prefs | skip | Not changed. |
| G03 | Notifications prefs | skip | Not opened. |
| G04 | Input / display panels | pass | `en_US.utf8` present; `setlocale` OK; brightness/volume OK. |
| G05 | Updates / About / Storage | pass | `VERSION` 1.13.20; apt candidates current. |
| G06 | Theme alignment | skip | Not re-checked. |

## H — Remote Desktop

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| H01 | Enable host (xrdp) | pass | Default off. |
| H02 | Desktop .rdp helper | skip | Host not enabled. |
| H03 | mstsc separate session | skip | Not run. |
| H04 | Second user / console OK | skip | Single user. |
| H05 | Disable + outbound client | skip | Not run. |

## I — Recovery and session health

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| I01 | FosOS Recovery session | skip | Not signed into Recovery. |
| I02 | Shell crash recovery | skip | Not re-killed this pass. |
| I03 | Power / suspend | skip | Not run. |
| I04 | Multi-monitor | skip | Single eDP. |

## J — Packages, release, USB

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| J01 | fos update / upgrade | pass | On `fosos-desktop` 1.13.20 + `fosos-cli` 0.2.6 (`full-upgrade`). |
| J02 | ISO size in ISO-SIZE.md | skip | No rebuild. |
| J03 | Release VM rebuild + re-soak | skip | Deferred. |
| J04 | USB UEFI smoke | skip | Not run. |
| J05 | Laptop Wi-Fi scan/join | pass | AMAGI connected; scan OK. |
| J06 | Secure Boot live + install | skip | No `shim-signed` on this install; boot entry is `\EFI\FosOS\grubx64.efi`. Needs new ISO. |
