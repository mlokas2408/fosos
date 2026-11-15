"""Fullscreen lock screen. Authenticates the current user with PAM."""

from __future__ import annotations

import getpass
import os
import sys

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from .apps import is_live
from .authui import AuthWidgets, build_auth_ui, focus_first
from .ui import add_classes, load_css

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
        self.stick()
        add_classes(self, "fos-root", "fos-lock")
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("key-press-event", self._on_key)
        self.connect("delete-event", lambda *_a: True)
        self.connect("realize", self._on_realize)

        self.user = getpass.getuser()
        self.ui: AuthWidgets = build_auth_ui(
            mode="lock",
            username=self.user,
            live=is_live(),
            show_username=True,
            username_editable=False,
        )
        self.add(self.ui.root)
        self.ui.password.connect("activate", lambda _e: self._try_unlock())
        self.ui.submit.connect("clicked", lambda _b: self._try_unlock())
        if PREVIEW:
            self.ui.message.set_text("Preview mode. Escape exits.")

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

    def _on_realize(self, *_args) -> None:
        window = self.get_window()
        if window is not None:
            window.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), "default"))
        self.fullscreen()
        GLib.idle_add(lambda: focus_first(self.ui) or False)

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape and PREVIEW:
            Gtk.main_quit()
            return True
        return False

    def _try_unlock(self) -> None:
        password = self.ui.password.get_text()
        if not password and not PREVIEW:
            self.ui.message.set_text("Enter your password.")
            return
        if authenticate(self.user, password):
            Gtk.main_quit()
            return
        self.ui.password.set_text("")
        self.ui.message.set_text("Incorrect password.")
        self.ui.password.grab_focus()


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
