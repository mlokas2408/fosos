"""fosos-shell: panel, Start menu, desktop and notifications in one process."""

import sys
import traceback
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Wnck

from . import apps as appmod
from .desktop import Desktop
from .indicators import (
    BatteryPopup,
    BrightnessPopup,
    ClockPopup,
    NetworkPopup,
    VolumePopup,
    battery_state,
    brightness_icon,
    network_state,
    read_brightness,
    read_volume,
    volume_icon,
)
from .notifications import NotificationList, NotificationServer
from .panel import Panel, x_timestamp
from .popup import Popup
from .startmenu import StartMenu
from .ui import add_classes, button, load_css

APP_ID = "org.fosos.Shell"
CLOSE_WAIT_SECONDS = 4


def _crash_log(exc: BaseException | None = None) -> None:
    text = traceback.format_exc() if exc is None else "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    sys.stderr.write(text)
    try:
        path = Path(GLib.get_user_config_dir()) / "fosos-desktop" / "shell-crash.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError:
        pass


class Shell(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.panel: Panel | None = None
        self.panels: list[Panel] = []
        self._apps: list[appmod.App] | None = None
        self.popups: dict[str, Popup] = {}
        self.pinned: appmod.Pinned | None = None
        self._ending = False
        self._watched_windows: set[int] = set()

    # Lifecycle

    def do_startup(self) -> None:
        try:
            self._startup()
        except Exception as exc:  # noqa: BLE001 - always capture shell boot failures
            _crash_log(exc)
            raise

    def _startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_prgname("fosos-shell")
        load_css()
        self.pinned = appmod.Pinned()
        self.pinned.listeners.append(self._on_pins_changed)
        self.desktop = Desktop(self)
        self.add_window(self.desktop)
        self.notifications = NotificationServer(self)
        self.start_menu = StartMenu(self)
        self.popups = {
            "start": self.start_menu,
            "volume": VolumePopup(self),
            "network": NetworkPopup(self),
            "clock": ClockPopup(self),
            "battery": BatteryPopup(self),
            "brightness": BrightnessPopup(self),
            "notifications": NotificationList(self.notifications),
        }
        self.start_menu.on_dismiss = lambda: self._set_start_open(False)
        self.desktop.show_all()
        Wnck.set_client_type(Wnck.ClientType.PAGER)
        self.screen = Wnck.Screen.get_default()
        self.screen.force_update()
        for signal in ("window-opened", "window-closed"):
            self.screen.connect(signal, self._on_windows_changed)
        for signal in ("active-window-changed", "window-stacking-changed", "active-workspace-changed"):
            self.screen.connect(signal, lambda *_a: self._refresh_panels())
        self.screen.connect("workspace-created", lambda *_a: self._rebuild_workspaces())
        self.screen.connect("workspace-destroyed", lambda *_a: self._rebuild_workspaces())
        self._rebuild_panels()
        display_screen = Gdk.Screen.get_default()
        display_screen.connect("monitors-changed", lambda _s: self._rebuild_panels())
        display_screen.connect("size-changed", lambda _s: self._place_panels())
        self.update_status()
        GLib.timeout_add_seconds(10, self._poll_status)
        Gio.AppInfoMonitor.get().connect("changed", lambda _m: self._invalidate_apps())
        self.hold()

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        args = command_line.get_arguments()[1:]
        if "--toggle-start" in args:
            self.toggle_start()
        elif "--toggle-popup" in args:
            index = args.index("--toggle-popup")
            name = args[index + 1] if index + 1 < len(args) else ""
            panel = self.panel
            anchor = panel.popup_anchors().get(name) if panel is not None else None
            if anchor is None:
                command_line.printerr(
                    f"Unknown popup: {name}. Use volume, network, notifications, clock, battery or brightness.\n"
                )
                return 2
            self.toggle_popup(name, anchor, panel)
        elif "--workspace" in args:
            index = args.index("--workspace")
            try:
                number = int(args[index + 1]) - 1
            except (IndexError, ValueError):
                command_line.printerr("Usage: fosos-shell --workspace N\n")
                return 2
            self.switch_workspace(number)
        elif "--lock" in args:
            self.lock_screen()
        elif "--quit" in args:
            self.quit()
        return 0

    # Panels

    def _rebuild_panels(self) -> None:
        for panel in self.panels:
            self.remove_window(panel)
            panel.destroy()
        self.panels = []
        self.panel = None
        display = Gdk.Display.get_default()
        primary = display.get_primary_monitor()
        for index in range(display.get_n_monitors()):
            monitor = display.get_monitor(index)
            is_primary = monitor == primary or (primary is None and index == 0)
            panel = Panel(self, monitor, is_primary=is_primary)
            self.panels.append(panel)
            self.add_window(panel)
            panel.show_all()
            panel.place()
            if is_primary:
                self.panel = panel
        if self.panel is None and self.panels:
            self.panel = self.panels[0]
            self.panel.is_primary = True
        self.update_status()

    def _place_panels(self) -> None:
        for panel in self.panels:
            panel.place()

    def _on_windows_changed(self, *_args) -> None:
        for window in self.screen.get_windows():
            key = window.get_xid()
            if key in self._watched_windows:
                continue
            self._watched_windows.add(key)
            window.connect("state-changed", lambda *_a: self._refresh_panels())
            window.connect("name-changed", lambda *_a: self._refresh_panels())
            window.connect("geometry-changed", lambda *_a: self._rebuild_tasks())
            window.connect("workspace-changed", lambda *_a: self._rebuild_tasks())
        self._rebuild_tasks()

    def _rebuild_tasks(self) -> None:
        for panel in self.panels:
            panel.rebuild_tasks()

    def _refresh_panels(self) -> None:
        for panel in self.panels:
            panel.refresh_workspaces()
            panel.refresh_tasks()

    def _rebuild_workspaces(self) -> None:
        for panel in self.panels:
            panel.rebuild_workspaces()
            panel.rebuild_tasks()

    def _on_pins_changed(self) -> None:
        self._rebuild_tasks()

    def _set_start_open(self, is_open: bool) -> None:
        for panel in self.panels:
            panel.set_start_open(is_open)

    # Apps

    def app_cache(self, refresh: bool = False) -> list[appmod.App]:
        if self._apps is None or refresh:
            self._apps = appmod.all_apps()
        return self._apps

    def _invalidate_apps(self) -> None:
        self._apps = None
        self.pinned.load()
        for panel in self.panels:
            panel.rebuild_tasks()

    def open_settings(self) -> None:
        app = appmod.load_app("fosos-settings.desktop")
        if app is None or not app.launch():
            appmod.spawn(["fosos-settings"])

    # Popups

    def close_popups(self, keep: str | None = None) -> None:
        for name, popup in self.popups.items():
            if name != keep and popup.get_visible():
                popup.dismiss()

    def toggle_start(self, panel: Panel | None = None) -> None:
        panel = panel or self.panel
        if panel is None:
            return
        if self.start_menu.get_visible():
            self.start_menu.dismiss()
            return
        self.close_popups()
        area = panel.area()
        self._set_start_open(True)
        panel.set_start_open(True)
        self.start_menu.open(area.x, panel.top(), area)

    def toggle_popup(self, name: str, anchor: Gtk.Widget, panel: Panel | None = None) -> None:
        popup = self.popups[name]
        if popup.get_visible():
            popup.dismiss()
            return
        self.close_popups()
        if hasattr(popup, "refresh"):
            popup.refresh()
        if name == "notifications":
            self.notifications.mark_read()
        panel = panel or self.panel
        if panel is None:
            return
        area = panel.area()
        alloc = anchor.get_allocation()
        x = panel.anchor_x(anchor) + alloc.width - popup.width
        popup.show_at(x, panel.top(), area)

    def show_desktop_menu(self, x: int, y: int) -> None:
        self.close_popups()
        menu = self.popups.get("desktop")
        if menu is None:
            menu = Popup(width=200)
            frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2), "fos-card")
            frame.set_border_width(4)
            for text, icon_name, app_id in (
                ("Open Files", "folder-symbolic", "fosos-files.desktop"),
                ("Open Terminal", "utilities-terminal-symbolic", "fosos-terminal.desktop"),
                ("Open Notepad", "accessories-text-editor-symbolic", "fosos-notepad.desktop"),
                ("Settings", "preferences-system-symbolic", "fosos-settings.desktop"),
            ):
                item = button(text, icon_name=icon_name, variant="ghost")
                item.get_child().set_halign(Gtk.Align.START)
                item.connect("clicked", lambda _b, a=app_id: self._menu_launch(a))
                frame.pack_start(item, False, False, 0)
            menu.add(frame)
            self.popups["desktop"] = menu
        monitor = Gdk.Display.get_default().get_monitor_at_point(x, y).get_geometry()
        menu.show_all()
        _minimum, natural = menu.get_preferred_size()
        menu.show_at(x, y + natural.height + 1, monitor)

    def _menu_launch(self, app_id: str) -> None:
        self.close_popups()
        if app_id == "fosos-settings.desktop":
            self.open_settings()
            return
        app = appmod.load_app(app_id)
        if app is not None:
            app.launch()

    # Status

    def update_status(self) -> None:
        state = read_volume()
        if state is None:
            volume = ("audio-volume-muted-symbolic", "Sound is not available")
        else:
            level, muted = state
            volume = (volume_icon(level, muted), "Muted" if muted else f"Volume {level}%")
        network = network_state()
        battery = battery_state()
        brightness = None
        level = read_brightness()
        if level is not None:
            brightness = (brightness_icon(level), f"Brightness {level}%")
        for panel in self.panels:
            panel.apply_status(volume, network, battery, brightness)
            if panel.unread_dot is not None:
                panel.set_unread(self.notifications.unread > 0)

    def _poll_status(self) -> bool:
        self.update_status()
        return True

    # Workspaces and lock

    def switch_workspace(self, index: int) -> None:
        screen = Wnck.Screen.get_default()
        screen.force_update()
        if index < 0 or index >= screen.get_workspace_count():
            return
        workspace = screen.get_workspace(index)
        if workspace is None:
            return
        stamp = x_timestamp(self.panel) if self.panel is not None else 0
        workspace.activate(stamp)
        for panel in self.panels:
            panel.refresh_workspaces()
            panel.rebuild_tasks()

    def lock_screen(self) -> None:
        self.close_popups()
        appmod.spawn(["fosos-lock"])

    # Session

    def notify_self(self, summary: str, body: str) -> None:
        self.notifications.notify("FosOS", 0, "dialog-information-symbolic", summary, body, [], {}, -1)

    def end_session(self, action: str) -> None:
        """Close windows first so apps can ask to save, then end the session."""
        if action == "suspend":
            appmod.spawn(["systemctl", "suspend"])
            return
        if action == "lock":
            self.lock_screen()
            return
        if self._ending:
            return
        self._ending = True
        stamp = x_timestamp(self.panel) if self.panel is not None else 0
        windows = self.panel.all_session_windows() if self.panel is not None else []
        for window in windows:
            window.close(stamp)
        GLib.timeout_add(250, self._wait_for_windows, action, CLOSE_WAIT_SECONDS * 4)

    def _wait_for_windows(self, action: str, tries: int) -> bool:
        Wnck.Screen.get_default().force_update()
        remaining = self.panel.all_session_windows() if self.panel is not None else []
        if remaining and tries > 0:
            GLib.timeout_add(250, self._wait_for_windows, action, tries - 1)
            return False
        self._ending = False
        if remaining:
            names = ", ".join(sorted({w.get_name() for w in remaining}))[:120]
            self.notify_self(
                "Some apps are still open",
                f"Save your work and close {names}, then try again.",
            )
            return False
        if action == "logout":
            if not appmod.spawn(["openbox", "--exit"]):
                self.quit()
        elif action == "reboot":
            appmod.spawn(["systemctl", "reboot"])
        elif action == "poweroff":
            appmod.spawn(["systemctl", "poweroff"])
        return False


def main() -> int:
    return Shell().run(sys.argv)
