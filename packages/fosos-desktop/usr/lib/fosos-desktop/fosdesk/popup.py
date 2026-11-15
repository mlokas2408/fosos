"""Popup windows anchored to the panel: Start menu, volume, network and more."""

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from .ui import add_classes

GAP = 1


class Popup(Gtk.Window):
    """An override-redirect window that grabs input until it is dismissed.

    Clicks outside close it, as does Escape. Clicks on other FosOS shell
    windows are still delivered to them, so the panel buttons keep working.
    """

    def __init__(self, width: int = 320) -> None:
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
        self.set_resizable(False)
        self.width = width
        self.set_size_request(width, -1)
        add_classes(self, "fos-root", "fos-popup")
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("button-press-event", self._on_button_press)
        self.connect("key-press-event", self._on_key_press)
        self.connect("grab-broken-event", lambda *_args: self.dismiss())
        self.on_dismiss = None
        self._grabbed = False
        self.focus_widget = None

    def show_at(self, x: int, bottom: int, monitor: Gdk.Rectangle) -> None:
        """Show with the bottom edge at `bottom`, kept inside `monitor`."""
        self._anchor = (x, bottom, monitor)
        self.show_all()
        self._place()
        self.present()
        GLib.idle_add(self._grab)

    def relayout(self) -> None:
        """Keep the bottom edge anchored after the content changes size."""
        GLib.idle_add(self._place)

    def _place(self) -> bool:
        anchor = getattr(self, "_anchor", None)
        if anchor is None or not self.get_visible():
            return False
        x, bottom, monitor = anchor
        _minimum, natural = self.get_preferred_size()
        width = max(self.width, natural.width)
        height = natural.height
        x = max(monitor.x, min(x, monitor.x + monitor.width - width))
        y = max(monitor.y, bottom - height - GAP)
        self.resize(width, height)
        self.move(x, y)
        return False

    def _grab(self) -> bool:
        window = self.get_window()
        if window is None or not self.get_visible():
            return False
        seat = Gdk.Display.get_default().get_default_seat()
        status = seat.grab(window, Gdk.SeatCapabilities.ALL, True, None, None, None)
        self._grabbed = status == Gdk.GrabStatus.SUCCESS
        event = Gdk.Event.new(Gdk.EventType.FOCUS_CHANGE)
        event.focus_change.window = window
        event.focus_change.in_ = True
        self.send_focus_change(event)
        if self.focus_widget is not None:
            self.focus_widget.grab_focus()
        return False

    def dismiss(self) -> None:
        if not self.get_visible():
            return
        if self._grabbed:
            Gdk.Display.get_default().get_default_seat().ungrab()
            self._grabbed = False
        self.hide()
        if self.on_dismiss is not None:
            self.on_dismiss()

    def _on_button_press(self, _widget, event: Gdk.EventButton) -> bool:
        window = self.get_window()
        if window is None:
            return False
        _ok, origin_x, origin_y = window.get_origin()
        width = window.get_width()
        height = window.get_height()
        inside = (
            origin_x <= event.x_root < origin_x + width
            and origin_y <= event.y_root < origin_y + height
        )
        if not inside:
            self.dismiss()
            return True
        return False

    def _on_key_press(self, _widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.dismiss()
            return True
        return False
