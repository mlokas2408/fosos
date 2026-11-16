# FosOS implementation plan

## Product definition

FosOS is a lightweight, development-friendly desktop operating system for
personal and internal company use. It is a Debian Stable derivative, not an
independent Linux From Scratch package ecosystem.

The initial system provides a complete basic desktop: Firefox, networking,
audio, file management, terminal, settings, updates, firmware, and recovery
tools. Development tools and applications such as Git, Node.js, Docker, VS
Code, Cursor, and language SDKs are optional; users install only what they
need from Debian or an upstream vendor.

## Technical direction

| Area | Initial choice |
| --- | --- |
| Distribution base | Debian Stable |
| Architecture | x86_64/amd64 with UEFI boot only |
| Desktop | FosOS Desktop (`fosos-desktop`) on Openbox; no XFCE session |
| Fallback | FosOS Recovery (Openbox + terminal) and text consoles |
| Browser | Firefox |
| Package management | APT and Debian repositories |
| FosOS packages | Native `.deb` packages in a signed FosOS APT archive |
| ISO builder | Debian `live-build` in a clean, scripted build environment |
| Test targets | Hyper-V for WSL development builds; a dedicated Debian VM rebuilds release ISOs, then USB boot on selected hardware |

## Scope boundaries

FosOS does not initially try to maintain a replacement repository for the
entire Linux ecosystem. Debian supplies the kernel, security updates, drivers,
libraries, and optional software such as Git and Node.js. FosOS maintains only
the components it owns: branding, desktop, installer, setup wizard, settings,
and update experience.

The `mockup/` directory is the visual reference for FosOS Desktop. It is not
built, shipped, or imported by anything in the image.

## Repository layout

This repository remains a private monorepo while the project is developed.

```text
fosos/
  build/                 # live-build configuration and ISO scripts
  packages/              # source and Debian packaging for FosOS components
    fosos-desktop/
    fosos-theme/
    fosos-welcome/
    fosos-settings/
    fosos-installer/
    fosos-archive-keyring/
  config/                # XFCE defaults, branding, system configuration
  scripts/               # build, test, release and validation helpers
  docs/                  # contributor and operational documentation
  .github/workflows/     # CI build and test workflows
```

Package output is published separately to a public `fosos-apt` archive. The
archive holds only signed `.deb` files and APT metadata; it does not contain
the private source repository.

## Delivery phases

### Phase 0 — project foundation

**Goal:** establish a reproducible development environment before building an
ISO.

- Create the repository structure above.
- Document the supported target: Debian Stable, amd64, UEFI.
- Use Debian 13 WSL for development builds and Hyper-V for pre-release testing.
- Keep a Debian Stable VM dedicated to release ISO builds.
- Add a single script that can prepare build dependencies.
- Record all versions and build prerequisites in version-controlled files.
- Add a CI smoke check for scripts and package metadata.

**Exit condition:** a new developer machine can prepare the build environment
using documented, scripted steps.

### Phase 1 — bootable FosOS base ISO

**Goal:** produce a minimal live and installable Debian-based image.

- Configure `live-build` for Debian Stable.
- Add UEFI boot, a configured kernel, firmware, locale, timezone, and users.
- Include APT, the Debian keyring, and the FosOS archive keyring package.
- Configure Debian repositories and a placeholder FosOS APT source.
- Build development ISOs in Debian WSL and the release ISO on the dedicated VM.
- Boot-test the image in Hyper-V.

**Exit condition:** the ISO boots reliably and reaches a usable console on a
fresh virtual machine.

### Phase 2 — usable branded XFCE desktop

**Goal:** deliver a lightweight daily-use desktop with no development stack
preinstalled.

- Add XFCE and set it as the default desktop session.
- Install Firefox, NetworkManager, Wi-Fi firmware, PipeWire, Bluetooth support,
  a terminal emulator, file manager, archive support, screenshot tool, and
  basic editor.
- Create `fosos-theme` for wallpapers, icons, GTK theme, cursor, fonts, boot
  splash, login appearance, and XFCE defaults.
- Add sensible power, display, networking, audio, and keyboard defaults.
- Keep a recovery terminal and an XFCE fallback path available.

**Exit condition:** a new user can boot, connect to Wi-Fi, browse with Firefox,
manage files, open a terminal, change common settings, and install optional
software through APT.

### Phase 3 — installation and first-run experience

**Goal:** make FosOS installable without requiring command-line expertise.

- Select and configure a proven Debian-compatible installer backend.
- Build the FosOS-branded installer interface and validate partitioning,
  encrypted-install, user-account, locale, and timezone flows.
- Build `fosos-welcome` for first login: updates, network status, optional
  documentation, and setup completion.
- Do not offer Chrome; Firefox is the only preinstalled browser.
- Test full install, first boot, and reinstall paths in VMs.

**Exit condition:** a fresh machine can install and boot FosOS through a
repeatable, documented flow.

### Phase 4 — FosOS-owned package workflow

**Goal:** update FosOS components independently of the ISO.

- Package each FosOS component as a `.deb`.
- Implement `fosos-archive-keyring`, installed by the ISO, with the archive
  public signing key and APT source configuration.
- Create the public `fosos-apt` archive using `reprepro` and signed `InRelease`
  metadata.
- Publish `testing` first, then promote tested packages to `stable`.
- Build a minimal `fos` command as a friendly wrapper for safe common APT
  actions; initially it should not replace APT.
- Test install, removal, upgrade, and failure recovery in clean VMs.

**Exit condition:** a new `fosos-theme` or `fosos-welcome` package can reach an
existing FosOS installation with `apt update` and `apt upgrade`.

### Phase 5 — custom FosOS Desktop, experimental

**Goal:** develop the custom desktop without risking the usable OS.

- Create `packages/fosos-desktop` in this monorepo.
- Ship `fosos-desktop` in the ISO but leave XFCE as the default session.
- Register the desktop as a separate login-session entry.
- Start with visible, high-value components: FosOS panel, launcher,
  notifications, settings shell, and workflow conventions.
- Decide deliberately whether the mature desktop is an XFCE-based shell or an
  independent Wayland session; do not build a compositor prematurely.
- Preserve XFCE as a login-screen fallback through the experimental period.

**Decision:** the experimental desktop is an X11 shell on Openbox, written in
Python and GTK 3, reusing the XFCE settings daemon and settings tools. No
compositor is built. Wayland is reconsidered once the shell is in daily use.
See [FosOS Desktop](docs/DESKTOP.md).

**Exit condition:** FosOS Desktop is stable enough for daily internal testing
and can be upgraded as a standalone package.

**Status:** Phase 5 exit is met. The session includes the panel, Start menu,
Files, Terminal, Notepad, notifications, settings shell, screen locker,
multi-monitor taskbars, battery and brightness indicators, and four
workspaces.

### Phase 6 — FosOS Desktop default

**Goal:** promote the custom desktop only after it is dependable.

- Make FosOS Desktop the default session in a major FosOS release.
- Retain XFCE as a supported fallback/recovery session.
- Test login, lock/unlock, display changes, multi-monitor use, network,
  audio, notifications, shutdown, suspend, upgrades, and failed-session
  recovery.
- Publish clear release notes and a rollback/recovery guide.

**Exit condition:** the custom session is more reliable for its supported use
cases than the XFCE default it replaces.

**Status:** Phase 6 packaging and documentation are in place for FosOS 1.0:
LightDM and Calamares default to `fosos-desktop`, failed-shell recovery opens
a recovery terminal, and [RELEASE-NOTES.md](docs/RELEASE-NOTES.md) /
[RECOVERY.md](docs/RECOVERY.md) cover the release and rollback. Complete the
soak checklist in [TESTING.md](docs/TESTING.md) on Hyper-V (and USB hardware)
before tagging the release ISO. The XFCE greeter fallback is removed in
Phase 7.

### Phase 7 — FosOS-only desktop, smaller ISO

**Goal:** ship a single desktop product and shrink the image by dropping the
XFCE session, without breaking settings that still use shared tools.

#### 7a — product cutover (this change)

- Remove the XFCE login session from the image (do not install `xfce4` /
  `xfce4-session`).
- Keep FosOS Desktop as the only full desktop; add **FosOS Recovery**
  (Openbox + terminal) on the greeter and document TTY recovery.
- Drop Thunar, Mousepad, xfce4-terminal, xfce4-notifyd and panel plugins from
  the image list; first-party apps cover those roles.
- Keep `xfce4-settings`, `xfce4-power-manager` and `xfce4-screenshooter` as
  temporary dependencies of FosOS Desktop.

**Exit condition:** a fresh ISO boots only FosOS Desktop (or Recovery), with
no Xfce Session entry, and is smaller than the Phase 6 image.

#### 7b — unbundle settings tools

- Replace or wrap display, keyboard, mouse, mime and power dialogs so the
  image no longer needs `xfce4-settings` / `xfce4-power-manager`.
- Replace `xfce4-screenshooter` with a FosOS-owned or smaller tool.
- Drop remaining XFCE package dependencies from `fosos-desktop` and
  `fosos-theme`.

**Exit condition:** `apt depends fosos-desktop` lists no `xfce4-*` packages.

**Status:** Phase 7b is implemented. Settings use built-in keyboard/mouse/
defaults/power panels plus `arandr` for display; screenshots use
`fosos-screenshot` (`scrot`); the session uses `xsettingsd` instead of
`xfsettingsd`. `fosos-desktop` 1.2.0 and `fosos-theme` 0.3.0 have no
`xfce4-*` Depends.

#### 7c — ISO size and soak

- Remove leftover XFCE libraries pulled only by the old session.
- Measure live ISO size before/after; target a clear reduction vs Phase 6.
- Re-run the Hyper-V soak with Recovery and TTY paths.

**Exit condition:** documented ISO size delta and a passed soak with Recovery
as the only graphical fallback.

**Status:** Phase 7c implemented. XFCE session leftovers and greeter-only
Greybird / elementary-xfce themes are gone (`fosos-theme` **0.6.0**). ISO
size is recorded in [ISO-SIZE.md](docs/ISO-SIZE.md). Complete the Hyper-V
soak checklist in [TESTING.md](docs/TESTING.md) on the rebuilt image before
tagging a release ISO.

### Phase 8 — muscle memory and window behavior

**Goal:** Windows-trained users can move, switch, lock, and snap without
relearning shortcuts, while keeping the FosOS look.

- Bind Super alone to Start (keep Super+Space as an alias).
- Add familiar shortcuts where cheap: Win+R Run, Win+X quick links,
  Win+Shift+S region screenshot (alias of existing capture).
- Improve Alt+Tab to a hold-to-preview switcher (icon + title), not only
  instant Openbox cycle.
- Titlebar / edge behavior: drag to top maximizes; drag down restores.
- Taskbar click rules: focused → minimize; minimized → restore; same-app
  windows cycle (refine what Phase 5 already started).

**Exit condition:** a Windows user can tile left/right, switch apps, lock,
and open Start / Files / Settings from muscle memory on a stock install.

**Constraint:** behavior and shortcuts only — no Fluent acrylic, rounded
taskbar, or Windows blue. Stay on Openbox + `fosos-shell`.

**Status:** Phase 8 implemented in `fosos-desktop` **1.3.8**. Super alone
opens Start via `xcape` → Alt+F1 (Super+Space kept). Win+R Run, Win+X quick
links, Win+Shift+S region screenshot, Alt+Tab hold-to-preview switcher,
drag-to-top maximize (EdgeSnap), and taskbar click cycle/minimize rules.
Soak the shortcuts on Hyper-V before treating the exit condition as closed.

### Phase 9 — taskbar and Start launcher

**Goal:** the taskbar and Start menu are the primary way to run the machine.

**Taskbar**

- Right-click: Pin / Unpin, Close window(s), Open new window.
- Drag-reorder pinned apps and persist order.
- Middle-click opens a new window when the app supports it.

**Start**

- Search across apps, settings pages, and recent files (not apps only).
- Recommended strip: recent folders and files.
- Clear Lock / Sign out in the user or power area.
- All apps list scannable in alphabetical sections.

**Exit condition:** pin, find, and launch daily apps without Terminal or
browsing `/usr/share/applications`.

**Status:** Phase 9 implemented in `fosos-desktop` **1.3.9**. Taskbar
right-click Pin/Unpin, Close, Open new window; drag-reorder pinned apps;
middle-click new window. Start searches apps, settings and files; Recommended
uses recent paths; All apps is A–Z sectioned; account menu has Lock / Sign out.

### Phase 10 — Quick Settings and Notification Center

**Goal:** replace scattered indicator popups with Win11-like hubs in FosOS
card styling.

- Clock / date opens calendar plus notification history.
- Network / volume / battery cluster opens one Quick Settings panel: Wi-Fi,
  Bluetooth, volume, brightness, battery, power links, and a Settings footer.
- Shortcuts: Win+A Quick Settings, Win+N notifications (or the clock flyout).
- Keep toast popups; Clear all and click-to-focus must be reliable.

**Exit condition:** volume, Wi-Fi, brightness, and notifications are
adjustable in at most two clicks without opening full Settings tools.

**Status:** Phase 10 implemented in `fosos-desktop` **1.3.10**. Status icons
open Quick Settings (Wi-Fi, Bluetooth, mute, volume, brightness, battery,
Lock/Suspend). Clock and bell open Notification Center (calendar + history,
Clear all, click-to-focus). Win+A / Win+N shortcuts; toasts kept.

### Phase 11 — Files Explorer parity

**Goal:** File Explorer covers ordinary file chores without a third-party
manager or Terminal.

- Clipboard: Cut / Copy / Paste; Delete to Trash (`gio trash` / FreeDesktop).
- Multi-select, Select all, F2 rename, Alt+Up, address-bar focus.
- Recycle Bin in the sidebar and on the desktop.
- Context menu: Open with, Properties, Copy path, Open Terminal here.
- Drag-and-drop between folders; progress for large copies.
- Keep FosOS Quick Access; make Downloads and Home one click from everywhere.

**Exit condition:** copy, move, trash, restore, and open-with work for common
desktop files without leaving Files.

**Status:** Phase 11 implemented in `fosos-desktop` **1.3.11**. Files supports
Cut/Copy/Paste, multi-select, trash/restore, Open with, Properties, Copy path,
Open Terminal here, drag-and-drop with progress, Ctrl+L address bar, Recycle
Bin in the sidebar and on the desktop; Home is the default folder.

### Phase 12 — desktop and right-click world

**Goal:** an empty desktop still feels owned and discoverable.

- Desktop context menu: Refresh, Display settings, Personalize (wallpaper),
  New folder, Open Files / Terminal here.
- Icons: Recycle Bin, Home (or user folder), optional Computer (`/`); remember
  positions.
- Single-click vs double-click preference in Settings.
- Keep Show Desktop (Win+D) and the Dawn Aperture watermark as-is.

**Exit condition:** first-hour “right-click the desktop” habits work without
opening Settings from Start.

**Status:** Phase 12 implemented in `fosos-desktop` **1.3.12**. Desktop
context menu covers Refresh / Display / Personalize / New folder / Files /
Terminal here; icons (Home, Computer, Files, Recycle Bin, Install when live)
drag and remember positions; Settings → Personalize sets single- vs
double-click.

### Phase 13 — multitasking (snap layouts and Task View)

**Goal:** go beyond 50/50 tiling for multi-window work.

- Snap layouts: hover maximize or Win+Z → 2×2 / three-column presets in a
  FosOS card UI; place the focused window, then optional fill-next assist.
- Task View (Win+Tab): overview of windows and the existing four virtual
  desktops with thumbnails.
- Move window to another desktop from overview or the taskbar menu.
- Optional: drag to corners for quarter snaps.

**Exit condition:** multi-window layouts and desktop switching work without
manual resize math.

**Note:** heaviest Openbox phase. Prefer “layouts + desktop switcher” first,
full Task View second, if the WM fights overview UI.

**Status:** Phase 13 implemented in `fosos-desktop` **1.3.13**. Win+Z /
maximize right-click open snap layouts with fill-next assist; Win+Tab Task
View shows all four desktops; taskbar and Task View can move windows between
desktops; edge/corner drag snaps halves and quarters.

### Phase 14 — Settings and personalization depth

**Goal:** Settings feels like one FosOS product, not only a launcher for
external tools.

- Built-in pages: Wallpaper, Taskbar options, Notifications, richer About /
  Storage summary.
- Wrap or chrome external tools (display, sound, network) where cheap.
- Updates page with last-checked / reboot-needed status (not only a Terminal
  script).
- Extend Default apps for common types (PDF, archives, `.deb` already
  installs via Install Package).

**Exit condition:** common personalization and update checks happen inside
`fosos-settings` without hunting GNOME/XFCE dialogs.

**Status:** Phase 14 implemented in `fosos-desktop` **1.3.14**. Wallpaper /
Taskbar / Notifications / Storage / Updates are built-in; Display / Sound /
Network / Bluetooth are chromed wrappers; About shows storage + reboot hint;
Default apps cover PDF, archives, and images.

### Phase 15 — convenience backlog (optional)

**Goal:** pick only high-frequency Win11 conveniences after Phases 8–12 feel
solid.

| Item | Win11 analog | Guidance |
| --- | --- | --- |
| Clipboard history (Win+V) | Yes | High value, medium work |
| Status Notifier tray | System tray | High compatibility value |
| Run dialog (Win+R) | Yes | Cheap; may land in Phase 8 |
| Jump lists / recent docs per app | Yes | Medium |
| Widgets / news | Widgets | Skip — fights brand and lightness |
| Acrylic / Mica / centered Fluent bar | Fluent look | Skip — keep square FosOS cards |

**Exit condition:** each accepted item has its own soak note; skipped items
stay documented as non-goals.

## Build, test, and release flow

```text
Change source or package metadata
  -> build a `.deb` in a clean FosOS/Debian-compatible builder
  -> install and test it in a fresh VM
  -> publish to FosOS testing archive
  -> test upgrade from the previous package
  -> promote the exact tested package to FosOS stable
  -> include it in the next ISO for new installations
```

ISOs are for fresh installations and milestone releases. Existing systems
receive ordinary FosOS fixes through APT.

```bash
sudo apt update
sudo apt upgrade
```

## Debian major upgrades

A Debian major release becomes a FosOS major release.

```text
FosOS 1.x -> Debian 13
FosOS 2.x -> Debian 14
```

Before offering an in-place upgrade, produce and test the new ISO, rebuild and
test FosOS packages against the new Debian release, and validate upgrades from
the prior FosOS release. The future `fos upgrade` command should require a
fully updated system, warn about third-party repositories, recommend a backup,
switch both Debian and FosOS sources together, run `apt full-upgrade`, execute
migrations, and reboot.

## Security and operational rules

- Never use `apt-key`; use a dedicated keyring and `signed-by` source entries.
- Keep the archive signing private key out of Git and out of package hosting.
- Treat CI-produced packages as candidates; publish to stable only after VM
  testing.
- Pin all build inputs and verify upstream source checksums.
- Keep the base ISO small: no Git, compilers, language runtimes, Docker, VS
  Code, Cursor, or Chrome by default.
- Maintain release notes, a tested recovery path, and regular ISO tests.
