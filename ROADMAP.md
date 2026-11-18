# FosOS roadmap

Forward-looking guide for FosOS development. Historical phase logs are gone;
use [release notes](docs/RELEASE-NOTES.md) for what shipped when.

## Product

FosOS is a lightweight, development-friendly desktop OS for personal and
internal company use. It is a Debian Stable derivative, not an independent
package ecosystem.

The base image is a complete daily desktop: Firefox, networking, audio, file
management, terminal, settings, updates, firmware, and recovery. Development
tools (Git, Node.js, Docker, VS Code, Cursor, SDKs) stay optional — install
from Debian or upstream as needed.

## Technical direction

| Area | Choice |
| --- | --- |
| Base | Debian Stable |
| Arch / boot | x86_64/amd64, UEFI only (Secure Boot not yet) |
| Desktop | FosOS Desktop (`fosos-desktop`) on Openbox; no XFCE session |
| Fallback | FosOS Recovery (Openbox + terminal) and text consoles |
| Browser | Firefox only (no Chrome by default) |
| Packages | APT; FosOS-owned components as signed `.deb` in the FosOS archive |
| ISO | Debian `live-build`; WSL for development builds, Debian VM for release |
| Test | Hyper-V soak; USB on selected hardware before tagging a release ISO |

FosOS owns branding, desktop, installer, welcome, settings, and update UX.
Debian supplies the kernel, drivers, libraries, and optional software.

The `mockup/` directory is a visual reference only. Do not build, ship, or
import it.

## Current baseline (`fosos-desktop` 1.12.1)

- Live and installable Debian-based ISO with Calamares and FosOS APT keyring
- FosOS Desktop as the only full session; Recovery + TTY documented
- First-party Files, Terminal, Notepad, Settings, Welcome, greeter, lock
- Win-habit shell: Start, taskbar pins, Quick Settings, Notification Center,
  snap layouts, Task View, desktop icons, muscle-memory shortcuts
- Start: search clear + Esc-clears-first, arrow/Enter launch, Pinned /
  Recommended / All apps under home scroller, Account + Power footer
- Snap: edge zone preview; Win+arrows tile/restore via work area; CardWindow
  titlebar menu; Alt+Tab selection polish
- Quick Settings 2×2 (Wi-Fi / Bluetooth / Focus assist / Mute); per-app
  toast mutes; toast hover pauses expire
- Super+V clipboard history; Status Notifier tray (nm-applet and peers)
- Network flyout + Settings Wi-Fi picker (scan/join; not nm-connection-editor-only)
- Task View button + Show Desktop strip (no numbered pager); icon grid with
  no overlap; Files search and folder-background menus
- Bidirectional RDP: `fosos-remote` client + xrdp host (separate FosOS
  Desktop session for any local user; off until Settings → Remote Desktop)
- No `xfce4-*` Depends on `fosos-desktop` / `fosos-theme`

See [DESKTOP.md](docs/DESKTOP.md) and [ISO-SIZE.md](docs/ISO-SIZE.md).

## Next work

Prioritized. Prefer Windows *behavior* over Windows *pixels*; keep square
FosOS cards, Dawn Aperture, Inter.

### 1 — Start menu and search polish — done (1.7.0)

Shipped: stronger Search, Pinned/Recommended/All apps layout, keyboard
nav, home scrolling, Account + Power footer.

### 2 — Window chrome and snap feedback — done (1.8.0)

Shipped: edge snap zone overlay, restore-from-snap (Win+Down), work-area
Win+Left/Right, CardWindow titlebar menu, Alt+Tab selection polish.

### 3 — Notifications and Quick Settings depth — done (1.9.0)

Shipped: Focus assist naming + QS tile, 2×2 Quick Settings grid, per-app
toast mutes, toast hover pause / restack.

### 4 — Optional convenience backlog — partial (1.10.0)

| Item | Status |
| --- | --- |
| Clipboard history (Win+V) | Done (1.10.0) |
| Status Notifier tray | Done (1.10.0) |
| Jump lists / recent docs per app | Deferred |
| Widgets / news / Fluent acrylic / centered bar | Skip — non-goal |

### 5 — Release hygiene

Complete a Hyper-V soak log ([TESTING.md](docs/TESTING.md) /
[SOAK-LOG.md](docs/SOAK-LOG.md), and USB where needed) with no open `fail`
rows before tagging a release ISO. Promote APT packages only after VM testing.

### 6 — UEFI Secure Boot

**Goal:** boot the live and installed system with Secure Boot enabled
(Hyper-V Gen2 default and typical hardware), without asking users to turn
it off.

Today the image is UEFI-only but not Secure Boot–ready: no Microsoft-trusted
`shim`, no signed GRUB/kernel path for the FosOS live bootloader. Testing
docs and Hyper-V scripts disable Secure Boot for that reason.

Candidates: Debian `shim-signed` + signed GRUB EFI packages in the live
image; keep FosOS GRUB branding where signing allows; verify live ISO and
Calamares-installed system under Secure Boot on Hyper-V and USB hardware;
update [TESTING.md](docs/TESTING.md) / Hyper-V scripts when green.

**Exit:** Gen2 Hyper-V and selected hardware boot FosOS with Secure Boot
on; docs no longer require turning it off.

## Working rules

- Prefer Windows behavior over Windows chrome; stay on Openbox + `fosos-shell`.
- Update [TESTING.md](docs/TESTING.md) in the same change as UI behavior.
- Keep the base ISO small: no Git, compilers, language runtimes, Docker, VS
  Code, Cursor, or Chrome by default.
- Never use `apt-key`; keep the archive signing private key out of Git.
- Do not import or build `mockup/`.

## Related docs

- [DESKTOP.md](docs/DESKTOP.md) — architecture and shortcuts
- [BUILDING.md](docs/BUILDING.md) — ISO and package builds
- [TESTING.md](docs/TESTING.md) — test suites; [SOAK-LOG.md](docs/SOAK-LOG.md) — pass/fail log
- [RECOVERY.md](docs/RECOVERY.md) — Recovery, TTY, Hyper-V, rollback
- [RELEASE-NOTES.md](docs/RELEASE-NOTES.md) — what shipped
