"""Alt+Tab hold-to-preview window switcher."""

from __future__ import annotations

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Wnck

from .panel import HEIGHT, SKIP_TYPES, x_timestamp
from .ui import add_classes, clear, icon, label, set_class

MAX_ITEMS = 12


def switchable_windows(screen: Wnck.Screen) -> list[Wnck.Window]:
    screen.force_update()
    result = []
    for window in reversed(screen.get_windows_stacked()):
        if window.is_skip_tasklist() or window.get_window_type() in SKIP_TYPES:
            continue
        if window.is_skip_pager():
            continue
        result.append(window)
    return result[:MAX_ITEMS]


class AltTabSwitcher(Gtk.Window):
    def __init__(self, shell) -> None:
        super().__init__(type=Gtk.WindowType.POPUP)
        self.shell = shell
        self.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        add_classes(self, "fos-root", "fos-popup")
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.KEY_RELEASE_MASK)
        self.connect("key-press-event", self._on_key_press)
        self.connect("key-release-event", self._on_key_release)

        self.frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card", "fos-alttab")
        self.add(self.frame)
        body = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10), "fos-card-content")
        self.frame.pack_start(body, False, False, 0)
        self.row = Gtk.Box(spacing=8)
        self.row.set_halign(Gtk.Align.CENTER)
        body.pack_start(self.row, False, False, 0)
        self.caption = label("", "fos-text", xalign=0.5, ellipsize=True)
        body.pack_start(self.caption, False, False, 0)

        self.windows: list[Wnck.Window] = []
        self.index = 0
        self._grabbed = False
        self._items: list[Gtk.Button] = []

    def cycle(self, direction: int = 1) -> None:
        windows = switchable_windows(Wnck.Screen.get_default())
        if not windows:
            self.hide_switcher()
            return
        if len(windows) == 1:
            self._activate(windows[0])
            self.hide_switcher()
            return

        if not self.get_visible():
            self.windows = windows
            active = Wnck.Screen.get_default().get_active_window()
            try:
                start = self.windows.index(active) if active in self.windows else 0
            except ValueError:
                start = 0
            self.index = (start + direction) % len(self.windows)
            self._rebuild()
            self._show_centered()
            GLib.idle_add(self._grab)
            return

        if not self.windows:
            self.windows = windows
        self.index = (self.index + direction) % len(self.windows)
        self._refresh_selection()

    def hide_switcher(self) -> None:
        if self._grabbed:
            Gdk.Display.get_default().get_default_seat().ungrab()
            self._grabbed = False
        self.hide()
        self.windows = []
        self._items = []

    def _rebuild(self) -> None:
        clear(self.row)
        self._items = []
        for index, window in enumerate(self.windows):
            item = add_classes(Gtk.Button(), "fos-btn", "ghost", "fos-alttab-item")
            item.set_can_focus(False)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.set_size_request(88, -1)
            pixbuf = window.get_icon()
            if pixbuf is not None:
                scaled = pixbuf.scale_simple(32, 32, GdkPixbuf.InterpType.BILINEAR)
                image = Gtk.Image.new_from_pixbuf(scaled)
            else:
                image = icon("application-x-executable-symbolic", 32)
            box.pack_start(image, False, False, 0)
            title = label(window.get_name() or "Window", "fos-small", xalign=0.5, ellipsize=True)
            box.pack_start(title, False, False, 0)
            item.add(box)
            item.connect("clicked", lambda _b, i=index: self._pick(i))
            self.row.pack_start(item, False, False, 0)
            self._items.append(item)
        self._refresh_selection()
        self.row.show_all()

    def _refresh_selection(self) -> None:
        if not self.windows:
            return
        self.index %= len(self.windows)
        for index, item in enumerate(self._items):
            selected = index == self.index
            set_class(item, "default", selected)
            set_class(item, "ghost", not selected)
        window = self.windows[self.index]
        self.caption.set_text(window.get_name() or "Window")

    def _show_centered(self) -> None:
        self.show_all()
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        area = monitor.get_geometry()
        _minimum, natural = self.get_preferred_size()
        width = natural.width
        height = natural.height
        self.resize(width, height)
        x = area.x + (area.width - width) // 2
        y = area.y + max(24, (area.height - HEIGHT - height) // 2)
        self.move(x, y)
        self.present()

    def _grab(self) -> bool:
        window = self.get_window()
        if window is None or not self.get_visible():
            return False
        seat = Gdk.Display.get_default().get_default_seat()
        status = seat.grab(window, Gdk.SeatCapabilities.ALL, True, None, None, None)
        self._grabbed = status == Gdk.GrabStatus.SUCCESS
        return False

    def _pick(self, index: int) -> None:
        self.index = index
        self._activate_selected()

    def _activate_selected(self) -> None:
        if self.windows:
            self._activate(self.windows[self.index])
        self.hide_switcher()

    def _activate(self, window: Wnck.Window) -> None:
        stamp = x_timestamp(self.shell.panel) if self.shell.panel is not None else int(GLib.get_monotonic_time() / 1000)
        workspace = window.get_workspace()
        if workspace is not None:
            workspace.activate(stamp)
        window.activate(stamp)

    def _on_key_press(self, _widget, event: Gdk.EventKey) -> bool:
        key = event.keyval
        state = event.state
        if key in (Gdk.KEY_Escape, Gdk.KEY_ISO_Left_Tab) and not (state & Gdk.ModifierType.SHIFT_MASK):
            if key == Gdk.KEY_Escape:
                self.hide_switcher()
                return True
        if key == Gdk.KEY_Tab:
            direction = -1 if state & Gdk.ModifierType.SHIFT_MASK else 1
            self.index = (self.index + direction) % max(len(self.windows), 1)
            self._refresh_selection()
            return True
        if key in (Gdk.KEY_Left, Gdk.KEY_Right):
            direction = -1 if key == Gdk.KEY_Left else 1
            self.index = (self.index + direction) % max(len(self.windows), 1)
            self._refresh_selection()
            return True
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self._activate_selected()
            return True
        return True

    def _on_key_release(self, _widget, event: Gdk.EventKey) -> bool:
        if event.keyval in (Gdk.KEY_Alt_L, Gdk.KEY_Alt_R, Gdk.KEY_Meta_L, Gdk.KEY_Meta_R):
            self._activate_selected()
            return True
        return False
