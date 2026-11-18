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
  **xrdp** + **xorgxrdp** for a **separate** FosOS Desktop session (any local
  user via PAM; works with nobody on the console). FosOS-branded login chrome,
  TLS negotiate, Desktop `.rdp` helper. Off until enabled in Settings →
  Remote Desktop.
- Start search supports clear, Esc-clears-first, and arrow/Enter selection.
  Home shows Pinned and Recommended with All apps under the scroller; the
  footer is Account (left) and Power (right).
- Edge snap shows a zone preview while dragging; Super+arrows use the panel
  work area and restore snapped sizes on Super+Down. CardWindow titlebars
  offer a context menu and maximize right-click → snap layouts.
- Taskbar status icons open dedicated flyouts (Sound, Network & Bluetooth,
  Brightness, Battery). Clock / bell open a right-edge calendar + notifications
  panel with Focus assist; toast Mute is per-app; toast timers pause on hover.
- Win+A Quick Settings keeps the 2×2 tile grid and sliders (no Lock / Sign out /
  Suspend — those stay in Start). QS Wi-Fi / Network… still open the network
  flyout; Settings → Network embeds the same Wi-Fi picker.
- Super+V opens clipboard history (text). The taskbar hosts a Status Notifier
  tray for nm-applet and other SNI apps.
- `fosos-lock` is the screen locker (`xss-lock` on idle / before suspend).
- `gnome-keyring-daemon` provides the Secret Service (PAM unlock at login)
  for Cursor/Electron and other credential stores.

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
| xrdp host (optional) | Separate-session RDP via xrdp/xorgxrdp → `fosos-session`; off until Settings enables it |

## Keyboard shortcuts

| Keys | Action |
| --- | --- |
| Super (tap) / Super+Space / Alt+F1 | Start menu |
| Super+X | Quick links |
| Super+A | Quick settings |
| Super+N | Notification center |
| Super+V | Clipboard history |
| Super+R | Run |
| Super+E | Files |
| Ctrl+Alt+T | Terminal |
| Super+I | Settings |
| Super+L | Lock |
| Super+D | Show desktop (also far-right taskbar strip) |
| Super+↑ / ↓ / ← / → | Maximize / restore-from-snap then minimize / tile left / right |
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
grid, and polish Files search / folder background menus. **1.5.0** added
bidirectional RDP (FreeRDP shadow). **1.6.0** replaces inbound hosting with
xrdp (separate FosOS Desktop session + `fosos-remote` client). **1.7.0**
polishes Start search, keyboard launch, All apps placement, and the
Account + Power footer. **1.8.0** adds snap zone previews, restore-from-snap,
CardWindow titlebar menus, and clearer Alt+Tab selection. **1.9.0** deepens
Quick Settings (Focus assist tile, 2×2 grid) and per-app notification mutes.
**1.10.0** adds Super+V clipboard history and a Status Notifier tray.
