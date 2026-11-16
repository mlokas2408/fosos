# FosOS Desktop

FosOS Desktop is the default and only full FosOS session. It ships as the
`fosos-desktop` package. If it fails, choose **FosOS Recovery** on the login
screen (Openbox + terminal) or use a text console (Ctrl+Alt+F2). See
[RECOVERY.md](RECOVERY.md).

The look follows the FosOS Desktop design mockup: a neutral dark palette,
square corners, the Inter font, a bottom taskbar, a Start menu and a drawn
wallpaper. The brand mark is **Dawn Aperture** (φως / light). The LightDM
greeter and lock screen use the mockup’s two-column sign-in layout. The
mockup itself is a visual reference only and is not built or shipped.

## Architecture decision

FosOS Desktop is an X11 shell on the Openbox window manager. It is not a
Wayland compositor, and FosOS does not build one at this stage.

- Openbox manages windows with a FosOS-specific config.
- `fosos-shell` is one Python and GTK 3 process for the taskbar, Start menu,
  desktop, notifications and status menus.
- `xsettingsd` publishes theme, icon and font settings (no `xfsettingsd`).
- Display layout uses `arandr`. Keyboard, mouse, default apps and power are
  built into `fosos-settings`.
- Screenshots use `fosos-screenshot` (`scrot`).
- `fosos-files`, `fosos-terminal` and `fosos-notepad` are first-party apps.
- `fosos-lock` is the screen locker (`xss-lock` on idle / before suspend).

Revisit Wayland when the shell is stable for daily use.

## Components

| Component | What it does |
| --- | --- |
| `fosos-session` | Login session: xsettingsd, agents, xss-lock, shell, Welcome, Openbox |
| `fosos-recovery-session` | Minimal Openbox + terminal |
| `fosos-greeter` | LightDM greeter (two-column Sign in; always Desktop; power menu) |
| `fosos-shell` | Taskbar, Start menu, desktop, notifications, status menus |
| `fosos-lock` | Fullscreen lock screen (same layout + power menu) |
| `fosos-settings` | Settings shell (Wallpaper, Taskbar, Notifications, Updates, Storage, chromed system tools) |
| `fosos-screenshot` | Full / region / window capture |

## Keyboard shortcuts

| Keys | Action |
| --- | --- |
| Super (tap) / Super+Space / Alt+F1 | Start menu |
| Super+X | Quick links |
| Super+A | Quick settings |
| Super+N | Notification center |
| Super+R | Run |
| Super+E | Files |
| Ctrl+Alt+T | Terminal |
| Super+I | Settings |
| Super+L | Lock |
| Super+D | Show desktop |
| Super+↑ / ↓ / ← / → | Maximize / restore or minimize / tile left / right |
| Super+Z | Snap layouts (right-click maximize also) |
| Super+Tab | Task View (desktops + windows) |
| Alt+Tab / Alt+Shift+Tab | Window switcher |
| Super+1 … Super+4 | Workspaces |
| Print / Shift+Print / Super+Shift+S | Screenshot full / region |

## Testing

```bash
sudo bash scripts/test-desktop.sh
```

## Phase status

**Phase 7b** removed remaining `xfce4-*` package dependencies. **7c** drops
Greybird / elementary-xfce from the image, records ISO size in
[ISO-SIZE.md](ISO-SIZE.md), and completes the Hyper-V soak in
[TESTING.md](TESTING.md). **Phase 8** adds Win-like shortcuts, Alt+Tab
preview, Run / Quick links, and drag-to-top maximize. **Phase 9** deepens
the taskbar and Start launcher. **Phase 10** adds Quick Settings and
Notification Center. **Phase 11** brings Files Explorer parity (trash,
clipboard, drag-drop). **Phase 12** adds the desktop right-click menu,
draggable icons with remembered positions, and Personalize (single/double
click). **Phase 13** adds snap layouts (Win+Z), Task View (Win+Tab),
move-to-desktop, and edge/corner snaps. **Phase 14** deepens Settings
(Wallpaper, Taskbar, Notifications, Storage, Updates, chromed system tools,
richer About) in `fosos-desktop` 1.3.14.
