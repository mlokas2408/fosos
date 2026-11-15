# FosOS release notes

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
