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
| Arch / boot | x86_64/amd64, UEFI only; Secure Boot via `shim-signed` (verify on new ISO) |
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

## Current baseline (`fosos-desktop` 1.13.20)

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
FosOS cards, Dawn Aperture, Inter. Prefer baremetal soak over Hyper-V.

### 0 — Baremetal release hardening — partial (1.13.20)

ThinkPad T14 retest: **F04** / **G04** cleared (no open `fail` rows). Still
open on hardware: greeter sign-out round-trip, suspend/resume, Network
flyout join, Files trash/clipboard. `fos upgrade` now uses `full-upgrade`
(fosos-cli 0.2.6).

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

### 6 — UEFI Secure Boot — implemented (pending ISO verify)

Live-build uses `--uefi-secure-boot enable`; the squashfs ships
`shim-signed`, `grub-efi-amd64-signed`, and `grub-efi-amd64`. Calamares
install prefers `grub-install --uefi-secure-boot`. Hyper-V scripts enable
Secure Boot with template `MicrosoftUEFICertificateAuthority`. FosOS GRUB
splash/theme stay unsigned data; EFI binaries remain Debian-signed.

**Still needed:** rebuild ISO, pass soak **J06** (live + installed) on Gen2
Hyper-V and selected bare metal. Existing installs without shim need a
reinstall from the new ISO (or a manual shim/grub-signed install +
`grub-install`).

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
