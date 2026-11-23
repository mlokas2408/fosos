"""Win+X style quick links menu near the Start button."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from .popup import Popup
from .ui import add_classes, button, label, separator


class QuickLinks(Popup):
    def __init__(self, shell) -> None:
        super().__init__(width=280)
        self.shell = shell
        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)
        header = add_classes(Gtk.Box(), "fos-card-header")
        header.pack_start(label("Quick links", "fos-title"), False, False, 0)
        frame.pack_start(header, False, False, 0)

        body = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2), "fos-card-content")
        frame.pack_start(body, False, False, 0)

        for text, icon_name, action in (
            ("Terminal", "utilities-terminal-symbolic", "terminal"),
            ("Files", "folder-symbolic", "files"),
            ("Settings", "preferences-system-symbolic", "settings"),
            ("Run…", "system-run-symbolic", "run"),
        ):
            item = button(text, icon_name=icon_name, variant="ghost")
            item.get_child().set_halign(Gtk.Align.START)
            item.connect("clicked", lambda _b, a=action: self._run(a))
            body.pack_start(item, False, False, 0)

        body.pack_start(separator(vertical=False), False, False, 4)

        for text, icon_name, action in (
            ("Lock", "system-lock-screen-symbolic", "lock"),
            ("Sign out", "system-log-out-symbolic", "logout"),
            ("Shut down", "system-shutdown-symbolic", "poweroff"),
        ):
            item = button(text, icon_name=icon_name, variant="ghost")
            item.get_child().set_halign(Gtk.Align.START)
            item.connect("clicked", lambda _b, a=action: self._run(a))
            body.pack_start(item, False, False, 0)

    def open_near_start(self, panel) -> None:
        self.shell.close_popups(keep="quicklinks")
        if self.get_visible():
            self.dismiss()
            return
        area = panel.area()
        self.show_at(area.x + 8, panel.top(), area)

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
        if action == "settings":
            self.shell.open_settings()
            return
        if action == "run":
            self.shell.open_run()
            return
        if action == "lock":
            self.shell.lock_screen()
            return
        if action in ("logout", "poweroff"):
            self.shell.end_session(action)
