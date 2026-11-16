"""Win+R style Run dialog."""

from __future__ import annotations

import os
import shlex

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from . import apps as appmod
from .ui import add_classes, button, label


class RunDialog(Gtk.Window):
    def __init__(self, shell) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.shell = shell
        self.set_title("Run")
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_modal(True)
        add_classes(self, "fos-root", "fos-popup")
        self.set_default_size(420, -1)
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("key-press-event", self._on_key)
        self.connect("delete-event", lambda *_a: self.hide() or True)
        self.connect("focus-out-event", self._on_focus_out)

        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "fos-card")
        frame.set_border_width(16)
        self.add(frame)
        frame.pack_start(label("Run", "fos-title"), False, False, 0)
        frame.pack_start(
            label("Type a command, app name, or path, then press Enter.", "fos-text", "fos-muted"),
            False,
            False,
            0,
        )
        self.entry = add_classes(Gtk.Entry(), "fos-input")
        self.entry.set_activates_default(True)
        self.entry.connect("activate", lambda _e: self._run())
        frame.pack_start(self.entry, False, False, 0)
        self.error = label("", "fos-small", "fos-muted")
        frame.pack_start(self.error, False, False, 0)
        row = Gtk.Box(spacing=8)
        row.set_halign(Gtk.Align.END)
        cancel = button("Cancel", variant="ghost", size="sm")
        cancel.connect("clicked", lambda _b: self.hide())
        ok = button("OK", variant="default", size="sm")
        ok.connect("clicked", lambda _b: self._run())
        row.pack_start(cancel, False, False, 0)
        row.pack_start(ok, False, False, 0)
        frame.pack_start(row, False, False, 0)

    def open_dialog(self) -> None:
        self.shell.close_popups()
        self.error.set_text("")
        self.entry.set_text("")
        self.show_all()
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        area = monitor.get_geometry()
        self.resize(420, 1)
        _minimum, natural = self.get_preferred_size()
        width = max(420, natural.width)
        height = natural.height
        self.resize(width, height)
        self.move(area.x + (area.width - width) // 2, area.y + int(area.height * 0.28))
        self.present()
        GLib.idle_add(self.entry.grab_focus)

    def _on_focus_out(self, _widget, _event) -> bool:
        # Keep the dialog when a child takes focus; hide when focus leaves the window.
        GLib.idle_add(self._maybe_hide)
        return False

    def _maybe_hide(self) -> bool:
        if self.get_visible() and not self.is_active():
            self.hide()
        return False

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False

    def _run(self) -> None:
        text = self.entry.get_text().strip()
        if not text:
            return
        if self._launch_app(text):
            self.hide()
            return
        if self._launch_command(text):
            self.hide()
            return
        self.error.set_text(f"Could not run “{text}”.")

    def _launch_app(self, text: str) -> bool:
        needle = text.lower()
        for app in self.shell.app_cache():
            name = app.name.lower()
            if name == needle or needle in name:
                return app.launch()
            desktop = (app.id or "").lower().removesuffix(".desktop")
            if desktop == needle or desktop.endswith("." + needle):
                return app.launch()
        return False

    def _launch_command(self, text: str) -> bool:
        path = os.path.expanduser(text)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return appmod.spawn([path])
        if os.path.isdir(path):
            return appmod.spawn(["fosos-files", path])
        try:
            argv = shlex.split(text, posix=True)
        except ValueError:
            return False
        if not argv:
            return False
        return appmod.spawn(argv)
