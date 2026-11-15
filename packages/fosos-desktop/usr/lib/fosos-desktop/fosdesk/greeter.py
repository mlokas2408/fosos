"""FosOS LightDM greeter: two-column Sign in matching the desktop mockup."""

from __future__ import annotations

import os
import sys
import traceback

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from .apps import is_live
from .authui import AuthWidgets, build_auth_ui, focus_first
from .ui import add_classes, load_css

PREVIEW = "--preview" in sys.argv
LOG_PATHS = (
    "/var/log/lightdm/fosos-greeter-crash.log",
    "/tmp/fosos-greeter-crash.log",
)

try:
    if not PREVIEW:
        gi.require_version("LightDM", "1")
        from gi.repository import LightDM
    else:
        LightDM = None  # type: ignore
except (ValueError, ImportError):
    LightDM = None  # type: ignore


def _log_crash(exc: BaseException | None = None) -> None:
    text = traceback.format_exc() if exc is None else "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    for path in LOG_PATHS:
        try:
            os.makedirs(os.path.dirname(path), mode=0o755, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            return
        except OSError:
            continue
    sys.stderr.write(text)


def _default_username(greeter) -> str:
    # Live image account is "user" (password "live"); "live" is only the password.
    if is_live():
        return "user"
    if greeter is None:
        return ""
    for getter in ("get_autologin_user_hint", "get_hint"):
        try:
            method = getattr(greeter, getter, None)
            if method is None:
                continue
            value = method() if getter != "get_hint" else method("default-user")
            if value:
                return str(value)
        except (AttributeError, GLib.Error, TypeError):
            continue
    return ""


class GreeterWindow(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_title("FosOS Sign in")
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(True)
        add_classes(self, "fos-root", "fos-greeter")
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("key-press-event", self._on_key)
        self.connect("delete-event", self._on_delete)
        self.connect("realize", self._on_realize)

        self._busy = False
        self._pending_password = ""
        self._daemon_error = ""
        self.greeter = None
        if LightDM is not None:
            self.greeter = LightDM.Greeter()
            self.greeter.connect("show-prompt", self._on_show_prompt)
            self.greeter.connect("show-message", self._on_show_message)
            self.greeter.connect("authentication-complete", self._on_auth_complete)
            try:
                self.greeter.connect_to_daemon_sync()
            except GLib.Error as exc:
                self.greeter = None
                self._daemon_error = str(exc)

        default_user = _default_username(self.greeter)

        self.ui: AuthWidgets = build_auth_ui(
            mode="login",
            username=default_user,
            live=is_live(),
            show_username=True,
            username_editable=True,
        )
        self.add(self.ui.root)
        self.ui.password.connect("activate", lambda _e: self._submit())
        if self.ui.username is not None:
            self.ui.username.connect("activate", lambda _e: self.ui.password.grab_focus())
        self.ui.submit.connect("clicked", lambda _b: self._submit())

        if PREVIEW:
            self.ui.message.set_text("Preview mode. Escape exits.")
        elif self.greeter is None:
            self.ui.message.set_text(self._daemon_error or "LightDM greeter API unavailable.")

        self._place()
        screen = Gdk.Screen.get_default()
        if screen is not None:
            screen.connect("monitors-changed", lambda _s: self._place())
            screen.connect("size-changed", lambda _s: self._place())

        if not PREVIEW and self.greeter is not None:
            GLib.idle_add(self._maybe_autologin)

    def _place(self) -> None:
        screen = Gdk.Screen.get_default()
        if screen is None:
            return
        width, height = screen.get_width(), screen.get_height()
        self.move(0, 0)
        self.set_size_request(width, height)
        self.resize(width, height)

    def _on_realize(self, *_args) -> None:
        self.fullscreen()
        GLib.idle_add(lambda: focus_first(self.ui) or False)

    def _on_delete(self, *_args) -> bool:
        return True

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape and PREVIEW:
            Gtk.main_quit()
            return True
        return False

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.ui.submit.set_sensitive(not busy)
        if self.ui.username is not None:
            self.ui.username.set_sensitive(not busy)
        self.ui.password.set_sensitive(not busy)

    def _maybe_autologin(self) -> bool:
        """If LightDM handed us an autologin user, complete sign-in without a prompt."""
        if self.greeter is None or self._busy:
            return False
        user = ""
        try:
            user = self.greeter.get_autologin_user_hint() or ""
        except (AttributeError, GLib.Error, TypeError):
            user = ""
        if not user:
            return False
        if self.ui.username is not None:
            self.ui.username.set_text(user)
        self.ui.password.set_text("")
        self.ui.message.set_text("Signing in…")
        self._submit()
        return False

    def _submit(self) -> None:
        if self._busy:
            return
        username = (self.ui.username.get_text() if self.ui.username else "").strip()
        password = self.ui.password.get_text()
        if not username:
            self.ui.message.set_text("Enter a username.")
            if self.ui.username is not None:
                self.ui.username.grab_focus()
            return

        if PREVIEW or self.greeter is None:
            if PREVIEW:
                Gtk.main_quit()
            else:
                self.ui.message.set_text(self._daemon_error or "Cannot reach LightDM.")
            return

        self._pending_password = password
        self.ui.message.set_text("Signing in…")
        self._set_busy(True)
        try:
            self.greeter.authenticate(username)
        except GLib.Error as exc:
            self._set_busy(False)
            self.ui.message.set_text(str(exc.message) if hasattr(exc, "message") else str(exc))
            self.ui.password.grab_focus()

    def _on_show_prompt(self, greeter, text: str, prompt_type) -> None:
        # LightDM.PromptType.SECRET == 1
        secret = int(prompt_type) == 1 if prompt_type is not None else "password" in (text or "").lower()
        if secret:
            greeter.respond(self._pending_password)
            self._pending_password = ""
        else:
            username = self.ui.username.get_text().strip() if self.ui.username else ""
            greeter.respond(username)

    def _on_show_message(self, _greeter, text: str, _msg_type) -> None:
        if text:
            self.ui.message.set_text(text)

    def _on_auth_complete(self, greeter) -> None:
        if greeter.get_is_authenticated():
            try:
                # None → LightDM default (user-session=fosos-desktop, or ~/.dmrc).
                greeter.start_session_sync(None)
            except GLib.Error as exc:
                self._set_busy(False)
                self.ui.message.set_text(str(exc.message) if hasattr(exc, "message") else str(exc))
                self.ui.password.set_text("")
                self.ui.password.grab_focus()
            return
        self._set_busy(False)
        self.ui.password.set_text("")
        self.ui.message.set_text("Incorrect username or password.")
        self.ui.password.grab_focus()
        try:
            greeter.cancel_authentication()
        except GLib.Error:
            pass


def main() -> int:
    GLib.set_prgname("fosos-greeter")
    os.environ.setdefault("GDK_BACKEND", "x11")

    cache = "/var/cache/lightdm/fosos"
    try:
        os.makedirs(cache, mode=0o755, exist_ok=True)
        if os.access(cache, os.W_OK):
            os.environ["XDG_CACHE_HOME"] = cache
    except OSError:
        pass

    try:
        load_css()
        window = GreeterWindow()
        window.show_all()
        alloc = window.get_allocation()
        if alloc.width and alloc.width < 900:
            window.ui.brand_column.set_visible(False)
        Gtk.main()
    except Exception as exc:  # noqa: BLE001 - greeter must never die silently
        _log_crash(exc)
        return 1
    return 0
