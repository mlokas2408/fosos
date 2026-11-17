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

## Current baseline (`fosos-desktop` 1.6.1)

- Live and installable Debian-based ISO with Calamares and FosOS APT keyring
- FosOS Desktop as the only full session; Recovery + TTY documented
- First-party Files, Terminal, Notepad, Settings, Welcome, greeter, lock
- Win-habit shell: Start, taskbar pins, Quick Settings, Notification Center,
  snap layouts, Task View, desktop icons, muscle-memory shortcuts
- Task View button + Show Desktop strip (no numbered pager); icon grid with
  no overlap; Files search and folder-background menus
- Bidirectional RDP: `fosos-remote` client + xrdp host (separate FosOS
  Desktop session for any local user; off until Settings → Remote Desktop)
- No `xfce4-*` Depends on `fosos-desktop` / `fosos-theme`

See [DESKTOP.md](docs/DESKTOP.md) and [ISO-SIZE.md](docs/ISO-SIZE.md).

## Next work

Prioritized. Prefer Windows *behavior* over Windows *pixels*; keep square
FosOS cards, Dawn Aperture, Inter.

### 1 — Start menu and search polish

**Goal:** Start feels closer to Windows for find-and-launch without a full
redesign.

Candidates: stronger Search affordance, pinned vs recommended clarity,
keyboard focus order, All apps scrolling, power/account placement.

**Exit:** daily apps are findable and launchable from Start without fighting
focus or layout.

### 2 — Window chrome and snap feedback

**Goal:** maximize / snap / restore cues match Windows expectations (layouts
already exist).

Candidates: clearer snap zones, restore-from-snap, titlebar context menu
parity, Alt+Tab preview polish.

**Exit:** multi-window tiling and restore feel predictable without manual
resize math.

### 3 — Notifications and Quick Settings depth

**Goal:** hubs feel complete for everyday controls.

Candidates: per-app notification toggles, Quick Settings tile layout, Focus
assist naming, toast stacking.

**Exit:** volume, network, brightness, and notification habits work in at
most two clicks without hunting full Settings pages.

### 4 — Optional convenience backlog

Pick only high-frequency items after 1–3 feel solid.

| Item | Guidance |
| --- | --- |
| Clipboard history (Win+V) | High value |
| Status Notifier tray | High compatibility value |
| Jump lists / recent docs per app | Medium |
| Widgets / news / Fluent acrylic / centered bar | Skip — fights brand and lightness |

**Exit:** each accepted item has a soak note; skipped items stay non-goals.

### 5 — Release hygiene

Complete the Hyper-V soak in [TESTING.md](docs/TESTING.md) (and USB where
needed) before tagging a release ISO. Promote APT packages only after VM
testing.

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
- [TESTING.md](docs/TESTING.md) — soak checklists
- [RECOVERY.md](docs/RECOVERY.md) — Recovery, TTY, Hyper-V, rollback
- [RELEASE-NOTES.md](docs/RELEASE-NOTES.md) — what shipped
