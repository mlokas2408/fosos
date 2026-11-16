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
- `fosos-settings` and `fosos-welcome` use the same undecorated card chrome
  (`CardWindow` / `fos-card`) as Files, Terminal and Notepad.
- First-party dialogs (alerts, confirms, prompts, file chooser, install
  package) use shared `fosdesk.ui` helpers instead of stock GTK dialog chrome.
- `fosos-remote` is the outbound RDP client (FreeRDP). Inbound hosting uses
  FreeRDP **shadow** (`freerdp3-shadow-x11`) to share the **console** desktop
  with mstsc (TLS + PAM login, fitted resolution, Desktop `.rdp` helper) — no
  xrdp, no second Xorg. Off until enabled in Settings → Remote Desktop.
- `fosos-lock` is the screen locker (`xss-lock` on idle / before suspend).

On Hyper-V Gen2 the image blacklists `hyperv_fb` and uses `hyperv_drm`
(modesetting / DRM FB) so the desktop does not paint then freeze mouse and
keyboard. See [RECOVERY.md](RECOVERY.md) if an older ISO still freezes input.

Revisit Wayland when the shell is stable for daily use.

## Components

| Component | What it does |
| --- | --- |
| `fosos-session` | Login session: xsettingsd, agents, xss-lock, shell, Welcome, Openbox |
| `fosos-recovery-session` | Minimal Openbox + terminal |
| `fosos-greeter` | LightDM greeter (two-column Sign in; always Desktop; power menu) |
| `fosos-shell` | Taskbar, Start menu, desktop, notifications, status menus |
| `fosos-lock` | Fullscreen lock screen (same layout + power menu) |
| `fosos-settings` | Settings shell (card chrome; Wallpaper, Taskbar, Notifications, Remote Desktop, Updates, Storage, chromed system tools) |
| `fosos-remote` | RDP client (card chrome; FreeRDP to Windows / Ubuntu / other hosts) |
| `fosos-welcome` | First-login / `--again` welcome (card chrome; guide, install, updates) |
| `fosos-screenshot` | Full / region / window capture |
| `fosos-rdp-shadow` (optional host) | Shares the console over RDP via FreeRDP shadow; off until Settings enables it |

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
| Super+D | Show desktop (also far-right taskbar strip) |
| Super+↑ / ↓ / ← / → | Maximize / restore or minimize / tile left / right |
| Super+Z | Snap layouts (right-click maximize also) |
| Super+Tab | Task View (desktops + windows; taskbar button) |
| Ctrl+Super+← / → | Previous / next virtual desktop |
| Alt+Tab / Alt+Shift+Tab | Window switcher |
| Super+1 … Super+4 | Jump to workspace 1–4 |
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
richer About). **UI improvements 1.4.0** replace the taskbar desktop pager
with a Task View button and Show Desktop strip, snap desktop icons to a
grid, and polish Files search / folder background menus. **1.5.0** adds
bidirectional RDP (FreeRDP shadow host + `fosos-remote` client).
