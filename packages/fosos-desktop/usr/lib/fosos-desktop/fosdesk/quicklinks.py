"""Win+X / Start right-click Quick Link menu (Windows 11 style)."""

from __future__ import annotations

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk

from .popup import Popup
from .ui import add_classes, button, separator


class QuickLinks(Popup):
    """Flyout anchored near Start — same surface as Win+X and Start right-click."""

    def __init__(self, shell) -> None:
        super().__init__(width=280)
        self.shell = shell
        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)

        body = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2), "fos-card-content")
        frame.pack_start(body, False, False, 0)

        self._add_items(
            body,
            (
                ("Terminal", "utilities-terminal-symbolic", "terminal"),
                ("Files", "folder-symbolic", "files"),
            ),
        )
        body.pack_start(separator(vertical=False), False, False, 4)
        self._add_items(
            body,
            (
                ("Device Manager", "computer-symbolic", "devicemgr"),
                ("Task Manager", "utilities-system-monitor-symbolic", "taskmgr"),
                ("Installed apps", "system-software-install-symbolic", "apps"),
                ("Power options", "preferences-system-power-symbolic", "power"),
                ("Network connections", "network-wired-symbolic", "network"),
                ("Map network drive", "folder-remote-symbolic", "mapdrive"),
                ("Storage", "drive-harddisk-symbolic", "storage"),
            ),
        )
        body.pack_start(separator(vertical=False), False, False, 4)
        self._add_items(
            body,
            (
                ("Task View", "view-grid-symbolic", "taskview"),
                ("Settings", "preferences-system-symbolic", "settings"),
                ("Search", "system-search-symbolic", "search"),
                ("Run…", "system-run-symbolic", "run"),
            ),
        )
        body.pack_start(separator(vertical=False), False, False, 4)

        power = button("Shut down or sign out", icon_name="system-shutdown-symbolic", variant="ghost")
        power.get_child().set_halign(Gtk.Align.START)
        power.connect("clicked", self._on_power_menu)
        body.pack_start(power, False, False, 0)

        self._add_items(
            body,
            (
                ("Lock", "system-lock-screen-symbolic", "lock"),
                ("Desktop", "user-desktop-symbolic", "desktop"),
            ),
        )

    def _add_items(self, body: Gtk.Box, items: tuple[tuple[str, str, str], ...]) -> None:
        for text, icon_name, action in items:
            item = button(text, icon_name=icon_name, variant="ghost")
            item.get_child().set_halign(Gtk.Align.START)
            item.connect("clicked", lambda _b, a=action: self._run(a))
            body.pack_start(item, False, False, 0)

    def open_near_start(self, panel) -> None:
        self.shell.close_popups(keep="quicklinks")
        if self.get_visible():
            self.dismiss()
            return
        # Close Start if it was open (Windows replaces Start with Quick Link).
        if self.shell.start_menu.get_visible():
            self.shell.start_menu.dismiss()
        area = panel.area()
        self.show_at(area.x + 8, panel.top(), area)

    def _on_power_menu(self, widget: Gtk.Button) -> None:
        menu = Gtk.Menu()
        add_classes(menu, "context-menu")
        for text, action in (
            ("Sign out", "logout"),
            ("Suspend", "suspend"),
            ("Restart", "reboot"),
            ("Shut down", "poweroff"),
        ):
            item = Gtk.MenuItem(label=text)
            item.connect("activate", lambda _i, a=action: self._run(a))
            menu.append(item)
        menu.show_all()
        # Keep this flyout open while the nested menu steals the seat grab.
        self._hold_grab = True
        menu.connect("deactivate", lambda *_a: self._on_power_menu_closed())
        menu.popup_at_widget(widget, Gdk.Gravity.NORTH_EAST, Gdk.Gravity.NORTH_WEST, None)

    def _on_power_menu_closed(self) -> None:
        self._hold_grab = False
        if self.get_visible():
            from gi.repository import GLib

            GLib.idle_add(self._grab)

    def _run(self, action: str) -> None:
        self.dismiss()
        if action == "terminal":
            from . import apps as appmod

            app = appmod.load_app("fosos-terminal.desktop")
            if app is None or not app.launch():
                appmod.spawn(["fosos-terminal"])
            return
        if action == "files":
            from . import apps as appmod

            app = appmod.load_app("fosos-files.desktop")
            if app is None or not app.launch():
                appmod.spawn(["fosos-files"])
            return
        if action == "devicemgr":
            from . import apps as appmod

            app = appmod.load_app("fosos-devicemgr.desktop")
            if app is None or not app.launch():
                appmod.spawn(["fosos-devicemgr"])
            return
        if action == "taskmgr":
            from . import apps as appmod

            app = appmod.load_app("fosos-taskmgr.desktop")
            if app is None or not app.launch():
                appmod.spawn(["fosos-taskmgr"])
            return
        if action == "apps":
            self.shell.open_settings("apps")
            return
        if action == "power":
            self.shell.open_settings("power")
            return
        if action == "network":
            self.shell.open_settings("network")
            return
        if action == "mapdrive":
            from . import apps as appmod

            if not appmod.spawn(["fosos-files", "--connect"]):
                app = appmod.load_app("fosos-files.desktop")
                if app is not None:
                    app.launch()
            return
        if action == "storage":
            self.shell.open_settings("storage")
            return
        if action == "taskview":
            self.shell.toggle_task_view()
            return
        if action == "settings":
            self.shell.open_settings()
            return
        if action == "search":
            self.shell.toggle_start()
            return
        if action == "run":
            self.shell.open_run()
            return
        if action == "lock":
            self.shell.lock_screen()
            return
        if action == "desktop":
            self.shell.toggle_show_desktop()
            return
        if action in ("logout", "suspend", "reboot", "poweroff"):
            self.shell.end_session(action)
