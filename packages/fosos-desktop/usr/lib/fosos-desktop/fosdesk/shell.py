"""fosos-shell: panel, Start menu, desktop and notifications in one process."""

import sys

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Wnck

from . import apps as appmod
from .desktop import Desktop
from .indicators import ClockPopup, NetworkPopup, VolumePopup, network_state, read_volume, volume_icon
from .notifications import NotificationList, NotificationServer
from .panel import Panel, x_timestamp
from .popup import Popup
from .startmenu import StartMenu
from .ui import add_classes, button, load_css

APP_ID = "org.fosos.Shell"
CLOSE_WAIT_SECONDS = 4


class Shell(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.panel: Panel | None = None
        self._apps: list[appmod.App] | None = None
        self.popups: dict[str, Popup] = {}
        self.pinned: appmod.Pinned | None = None
        self._ending = False

    # Lifecycle

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_prgname("fosos-shell")
        load_css()
        self.pinned = appmod.Pinned()
        self.desktop = Desktop(self)
        self.add_window(self.desktop)
        self.panel = Panel(self)
        self.add_window(self.panel)
        self.notifications = NotificationServer(self)
        self.start_menu = StartMenu(self)
        self.popups = {
            "start": self.start_menu,
            "volume": VolumePopup(self),
            "network": NetworkPopup(self),
            "clock": ClockPopup(self),
            "notifications": NotificationList(self.notifications),
        }
        self.start_menu.on_dismiss = lambda: self.panel.set_start_open(False)
        self.desktop.show_all()
        self.panel.show_all()
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
            anchor = self.panel.popup_anchors().get(name)
            if anchor is None:
                command_line.printerr(f"Unknown popup: {name}. Use volume, network, notifications or clock.\n")
                return 2
            self.toggle_popup(name, anchor)
        elif "--quit" in args:
            self.quit()
        return 0

    # Apps

    def app_cache(self, refresh: bool = False) -> list[appmod.App]:
        if self._apps is None or refresh:
            self._apps = appmod.all_apps()
        return self._apps

    def _invalidate_apps(self) -> None:
        self._apps = None
        self.pinned.load()
        self.panel.rebuild_tasks()

    def open_settings(self) -> None:
        app = appmod.load_app("fosos-settings.desktop")
        if app is None or not app.launch():
            appmod.spawn(["fosos-settings"])

    # Popups

    def close_popups(self, keep: str | None = None) -> None:
        for name, popup in self.popups.items():
            if name != keep and popup.get_visible():
                popup.dismiss()

    def toggle_start(self) -> None:
        if self.start_menu.get_visible():
            self.start_menu.dismiss()
            return
        self.close_popups()
        area = self.panel.area()
        self.panel.set_start_open(True)
        self.start_menu.open(area.x, self.panel.top(), area)

    def toggle_popup(self, name: str, anchor: Gtk.Widget) -> None:
        popup = self.popups[name]
        if popup.get_visible():
            popup.dismiss()
            return
        self.close_popups()
        if hasattr(popup, "refresh"):
            popup.refresh()
        if name == "notifications":
            self.notifications.mark_read()
        area = self.panel.area()
        alloc = anchor.get_allocation()
        x = self.panel.anchor_x(anchor) + alloc.width - popup.width
        popup.show_at(x, self.panel.top(), area)

    def show_desktop_menu(self, x: int, y: int) -> None:
        self.close_popups()
        menu = self.popups.get("desktop")
        if menu is None:
            menu = Popup(width=200)
            frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2), "fos-card")
            frame.set_border_width(4)
            for text, icon_name, app_id in (
                ("Open Files", "folder-symbolic", "thunar.desktop"),
                ("Open Terminal", "utilities-terminal-symbolic", "xfce4-terminal.desktop"),
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
            self.panel.set_volume_icon("audio-volume-muted-symbolic", "Sound is not available")
        else:
            level, muted = state
            self.panel.set_volume_icon(volume_icon(level, muted), "Muted" if muted else f"Volume {level}%")
        name, text = network_state()
        self.panel.set_network_icon(name, text)

    def _poll_status(self) -> bool:
        self.update_status()
        return True

    # Session

    def notify_self(self, summary: str, body: str) -> None:
        self.notifications.notify("FosOS", 0, "dialog-information-symbolic", summary, body, [], {}, -1)

    def end_session(self, action: str) -> None:
        """Close windows first so apps can ask to save, then end the session."""
        if action == "suspend":
            appmod.spawn(["systemctl", "suspend"])
            return
        if self._ending:
            return
        self._ending = True
        stamp = x_timestamp(self.panel)
        for window in self.panel.windows():
            window.close(stamp)
        GLib.timeout_add(250, self._wait_for_windows, action, CLOSE_WAIT_SECONDS * 4)

    def _wait_for_windows(self, action: str, tries: int) -> bool:
        Wnck.Screen.get_default().force_update()
        remaining = self.panel.windows()
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
