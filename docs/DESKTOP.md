# FosOS Desktop (experimental)

FosOS Desktop is the custom FosOS session. It ships in the ISO as the
`fosos-desktop` package and appears on the login screen as
**FosOS Desktop (experimental)**. XFCE stays the default session and the
fallback: choose **Xfce Session** from the session menu on the login screen to
go back.

The look follows the FosOS Desktop design mockup: a neutral dark palette,
square corners, the Inter font, a bottom taskbar, a Start menu and a drawn
wallpaper with the FosOS mark. The mockup is a visual reference only. Nothing
from it is built or shipped.

## Architecture decision

FosOS Desktop is an X11 shell on the Openbox window manager. It is not a
Wayland compositor, and FosOS does not build one at this stage.

- Openbox manages windows. It reads its own configuration file, so the
  FosOS window theme and shortcuts do not change the XFCE session. `xfwm4`
  was not used because its settings are shared with XFCE.
- `fosos-shell` is one Python and GTK 3 process for the taskbar, Start menu,
  desktop, notifications and status menus.
- `fosos-files` and `fosos-terminal` are first-party apps with the same card
  chrome as the mockup. Thunar and xfce4-terminal stay installed as fallbacks
  and still appear under All apps.
- The XFCE settings daemon still runs, so display, keyboard, mouse and font
  settings, and the XFCE settings dialogs, work in both sessions.
- Applications use the FosOS GTK theme and monochrome FosOS icons in this
  session only (neutral dark palette and square corners). XFCE keeps Greybird
  and elementary-xfce.

Revisit Wayland when the shell is stable for daily use and the supported
hardware is known. Moving would mean a compositor such as labwc in place of
Openbox, with the shell rewritten on layer-shell.

## Components

| Component | What it does |
| --- | --- |
| `fosos-session` | Login session script: settings daemon, password agent, Wi-Fi password agent, the shell with crash restart, Welcome, then Openbox |
| `fosos-shell` | Taskbar, Start menu, desktop, notification server, volume, network and clock menus |
| `fosos-files` | File Explorer: Quick Access, breadcrumbs, list/grid views |
| `fosos-terminal` | Simple Windows-style tabbed terminal |
| `fosos-notepad` | Simple Notepad-style plain text editor |
| `fosos-settings` | Settings shell: Display, Sound, Network, Bluetooth, Keyboard, Mouse, Default apps, Updates, Welcome and About |
| Openbox theme `FosOS` | Flat, square window frames and line-style window buttons |
| GTK theme `FosOS` | App chrome and client areas in the same neutral palette |
| Icon theme `FosOS` | White outline icons for Files and other session apps |

The shell owns `org.freedesktop.Notifications` in this session, so
`notify-send` and application notifications appear above the taskbar and in
the bell menu.

## Workflow conventions

- The taskbar shows pinned apps first, then other open windows. A line under
  an icon means the app is running. A brighter line means it has focus.
- Click a running app to bring it forward. Click the focused app to minimize
  it. Middle-click opens another window.
- Pin and unpin apps from **Start > All apps**. The list is saved in
  `~/.config/fosos-desktop/pinned`.
- Sign out, Restart and Shut down first ask open windows to close. If an app
  has unsaved work, FosOS stops and shows a notification instead of closing it.
- Settings that both sessions share, such as display layout and keyboard,
  are changed once and apply to both.

## Keyboard shortcuts

| Keys | Action |
| --- | --- |
| Super+Space or Alt+F1 | Open or close the Start menu |
| Super+E | Files (`fosos-files`) |
| Ctrl+Alt+T | Terminal (`fosos-terminal`) |
| Super+I | Settings |
| Super+D | Show the desktop |
| Super+Up | Maximize |
| Super+Down | Restore, or minimize |
| Super+Left / Super+Right | Fill the left or right half of the screen |
| Alt+Tab / Alt+Shift+Tab | Switch windows |
| Alt+F4 | Close the window |
| Alt+Space | Window menu |
| Print / Shift+Print | Screenshot of the screen / of a region |
| Ctrl+Shift+T / W | Terminal: new tab / close tab |
| Ctrl+Tab | Terminal: next tab |
| Ctrl+Shift+C / V | Terminal: copy / paste |
| Ctrl+N / O / S | Notepad: new / open / save |
| Ctrl+Shift+S | Notepad: save as |

Super on its own does not open the Start menu. Openbox acts on key press, so
binding Super alone would also fire for every Super shortcut.

To change shortcuts for one account, copy
`/usr/share/fosos-desktop/openbox/rc.xml` to
`~/.config/fosos-desktop/openbox/rc.xml` and edit the copy.

## Testing

`scripts/test-desktop.sh` runs the shell headless in a throwaway Debian root
under Xvfb. It opens the Start menu, searches, sends notifications, opens
Files, Terminal and Settings, starts the real session script and signs out.
It saves screenshots to `output/desktop/`.

```bash
sudo bash scripts/test-desktop.sh
```

The first run downloads a minimal Debian root into
`/var/tmp/fosos-desktop-test`. A Hyper-V session test is still required; see
[the testing guide](TESTING.md).

## Not yet included

- A screen locker. Lock and unlock are tested before FosOS Desktop can become
  the default in Phase 6.
- Multi-monitor layout beyond a taskbar on the primary monitor.
- Battery status and brightness controls in the taskbar.
- Workspaces. The session uses one desktop.
