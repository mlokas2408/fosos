"""Fullscreen lock screen. Authenticates the current user with PAM."""

from __future__ import annotations

import getpass
import os
import sys

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from .desktop import draw_wallpaper
from .ui import BRAND, add_classes, brand_title, button, label, load_css, mark

PREVIEW = "--preview" in sys.argv


def authenticate(user: str, password: str) -> bool:
    if PREVIEW:
        return True
    try:
        import pam  # type: ignore
    except ImportError:
        return False
    handle = pam.pam()
    return bool(handle.authenticate(user, password, service="login"))


class LockScreen(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_title("FosOS Lock")
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_accept_focus(True)
        self.set_app_paintable(True)
        self.stick()
        add_classes(self, "fos-root", "fos-lock")
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("draw", self._on_draw)
        self.connect("key-press-event", self._on_key)
        self.connect("delete-event", lambda *_a: True)
        self.connect("realize", self._on_realize)

        self.user = getpass.getuser()
        overlay = Gtk.Overlay()
        self.add(overlay)
        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        center.set_halign(Gtk.Align.CENTER)
        center.set_valign(Gtk.Align.CENTER)
        center.set_margin_start(24)
        center.set_margin_end(24)
        overlay.add_overlay(center)

        center.pack_start(mark("lg", inverse=True), False, False, 0)
        title = brand_title(22)
        title.set_xalign(0.5)
        title.set_halign(Gtk.Align.CENTER)
        center.pack_start(title, False, False, 0)
        center.pack_start(label(BRAND["tagline"], "fos-text", "fos-muted", xalign=0.5), False, False, 0)
        center.pack_start(label(self.user, "fos-title", xalign=0.5), False, False, 8)

        self.password = add_classes(Gtk.Entry(), "fos-input")
        self.password.set_visibility(False)
        self.password.set_placeholder_text("Password")
        self.password.set_width_chars(28)
        self.password.set_hexpand(False)
        self.password.connect("activate", lambda _e: self._try_unlock())
        center.pack_start(self.password, False, False, 0)

        row = Gtk.Box(spacing=8)
        row.set_halign(Gtk.Align.CENTER)
        unlock = button("Unlock", variant="default")
        unlock.connect("clicked", lambda _b: self._try_unlock())
        row.pack_start(unlock, False, False, 0)
        if PREVIEW:
            cancel = button("Close preview", variant="ghost")
            cancel.connect("clicked", lambda _b: Gtk.main_quit())
            row.pack_start(cancel, False, False, 0)
        center.pack_start(row, False, False, 0)

        self.message = label("", "fos-small", "fos-muted", xalign=0.5)
        self.message.set_line_wrap(True)
        center.pack_start(self.message, False, False, 0)
        if PREVIEW:
            self.message.set_text("Preview mode. Escape or Close preview exits.")

        self._place()
        screen = Gdk.Screen.get_default()
        screen.connect("monitors-changed", lambda _s: self._place())
        screen.connect("size-changed", lambda _s: self._place())

    def _place(self) -> None:
        screen = Gdk.Screen.get_default()
        width, height = screen.get_width(), screen.get_height()
        self.move(0, 0)
        self.set_size_request(width, height)
        self.resize(width, height)
        self.queue_draw()

    def _on_realize(self, *_args) -> None:
        window = self.get_window()
        if window is not None:
            window.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), "default"))
        self.fullscreen()
        GLib.idle_add(self.password.grab_focus)

    def _on_draw(self, _widget, cr) -> bool:
        display = Gdk.Display.get_default()
        for index in range(display.get_n_monitors()):
            draw_wallpaper(cr, display.get_monitor(index).get_geometry())
        return False

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape and PREVIEW:
            Gtk.main_quit()
            return True
        return False

    def _try_unlock(self) -> None:
        password = self.password.get_text()
        if not password and not PREVIEW:
            self.message.set_text("Enter your password.")
            return
        if authenticate(self.user, password):
            Gtk.main_quit()
            return
        self.password.set_text("")
        self.message.set_text("Incorrect password.")
        self.password.grab_focus()


def main() -> int:
    # Only one locker at a time.
    if not PREVIEW:
        try:
            import fcntl
        except ImportError:
            fcntl = None  # type: ignore
        else:
            lock_path = f"/run/user/{os.getuid()}/fosos-lock.lock"
            try:
                os.makedirs(os.path.dirname(lock_path), exist_ok=True)
                handle = open(lock_path, "w", encoding="utf-8")
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return 0

    GLib.set_prgname("fosos-lock")
    load_css()
    screen = LockScreen()
    screen.show_all()
    Gtk.main()
    return 0
