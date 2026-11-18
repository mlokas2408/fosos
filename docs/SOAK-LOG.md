# FosOS soak log

Fill this in while following [TESTING.md](TESTING.md). Prefer copying to
`docs/soak-logs/YYYY-MM-DD-<machine>.md` so each run stays archived.

**Status:** `pass` | `fail` | `skip`  
**Comment:** required for `fail` (what broke); optional for `skip` / `pass`.

## Run

| Field | Value |
| --- | --- |
| Date | |
| Tester | |
| ISO | `output/FosOS-trixie-amd64.iso` (path / size / builder: WSL or Debian VM) |
| Machine | Hyper-V Gen2 / USB hardware (name) |
| Image | live / installed |
| Desktop | `fosos-desktop` version if known |
| Notes | |

## Failed IDs (summary)

After the run, list every `fail` here for triage:

| ID | Comment |
| --- | --- |
| | |

## A — Boot and greeter

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| A01 | GRUB splash / FosOS Live | | |
| A02 | Live autologin FosOS Desktop | | |
| A03 | Mouse and keyboard work | | |
| A04 | Greeter two-column Sign in | | |
| A05 | No session picker / no Xfce | | |
| A06 | Greeter power menu | | |
| A07 | Sign in as user/live | | |
| A08 | TTY F2 / return F7 | | |

## B — Install

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| B01 | Calamares Install FosOS | | |
| B02 | Installed greeter / Desktop | | |
| B03 | Welcome / finish setup | | |
| B04 | sudo works; root locked | | |

## C — Taskbar, Start, tray, clipboard

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| C01 | Taskbar layout (no pager) | | |
| C02 | Super opens Start | | |
| C03 | Start search / clear / Esc | | |
| C04 | Keyboard nav / All apps / footer | | |
| C05 | Account + Power | | |
| C06 | Pin / reorder / middle-click | | |
| C07 | Taskbar menu / Show Desktop | | |
| C08 | Super+V clipboard history | | |
| C09 | Status Notifier tray | | |

## D — Windows, snap, multitasking

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| D01 | Core Super shortcuts | | |
| D02 | Alt+Tab | | |
| D03 | Super+arrows tile / restore | | |
| D04 | Edge snap + zone preview | | |
| D05 | Win+Z snap layouts | | |
| D06 | CardWindow titlebar menu | | |
| D07 | Maximize right-click → layouts | | |
| D08 | Task View | | |
| D09 | Move to desktop / Super+1…4 | | |
| D10 | Screenshots | | |
| D11 | Taskbar minimize / cycle | | |

## E — Quick Settings and notifications

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| E01 | Open Quick Settings / network flyout | | |
| E02 | 2×2 tiles + sliders | | |
| E03 | QS footers | | |
| E03b | Wi-Fi scan/join UI | | |
| E04 | Focus assist | | |
| E05 | Toast + hover pause | | |
| E06 | Notification Center | | |
| E07 | Per-app mute | | |

## F — Files and desktop

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| F01 | Files clipboard / trash | | |
| F02 | Files nav / search | | |
| F03 | Files menus / drag | | |
| F04 | Desktop icons / grid | | |
| F05 | Desktop context menu | | |
| F06 | Personalize / reset icons | | |

## G — Settings and theme

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| G01 | Settings card chrome | | |
| G02 | Wallpaper / Taskbar prefs | | |
| G03 | Notifications prefs | | |
| G04 | Input / display panels | | |
| G05 | Updates / About / Storage | | |
| G06 | Theme alignment | | |

## H — Remote Desktop

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| H01 | Enable host (xrdp) | | |
| H02 | Desktop .rdp helper | | |
| H03 | mstsc separate session | | |
| H04 | Second user / console OK | | |
| H05 | Disable + outbound client | | |

## I — Recovery and session health

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| I01 | FosOS Recovery session | | |
| I02 | Shell crash recovery | | |
| I03 | Power / suspend | | |
| I04 | Multi-monitor | | |

## J — Packages, release, USB

| ID | Check | Status | Comment |
| --- | --- | --- | --- |
| J01 | fos update / upgrade | | |
| J02 | ISO size in ISO-SIZE.md | | |
| J03 | Release VM rebuild + re-soak | | |
| J04 | USB UEFI smoke | | |
| J05 | Laptop Wi-Fi scan/join | | |
