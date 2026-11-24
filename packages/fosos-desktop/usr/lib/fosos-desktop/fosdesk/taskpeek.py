"""Hover peek thumbnails for taskbar app groups (Win11-style preview strip)."""

from __future__ import annotations

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Wnck

from .panel import HEIGHT, x_timestamp
from .ui import add_classes, clear, label


class TaskPeek(Gtk.Window):
    """Horizontal strip of window previews anchored above a task button."""

    def __init__(self, shell) -> None:
        super().__init__(type=Gtk.WindowType.POPUP)
        self.shell = shell
        self.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        add_classes(self, "fos-root", "fos-taskpeek")
        self.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect("enter-notify-event", self._on_enter)
        self.connect("leave-notify-event", self._on_leave)

        self.box = Gtk.Box(spacing=8)
        self.box.set_margin_start(10)
        self.box.set_margin_end(10)
        self.box.set_margin_top(10)
        self.box.set_margin_bottom(10)
        self.add(self.box)

        self._hide_id = 0
        self._owner: Gtk.Widget | None = None

    def show_for(self, anchor: Gtk.Widget, windows: list[Wnck.Window], panel) -> None:
        if not windows:
            self.hide_peek()
            return
        self.cancel_hide()
        self._owner = anchor
        clear(self.box)
        for window in windows:
            card = self._card(window)
            self.box.pack_start(card, False, False, 0)
        self.box.show_all()
        self.shell.close_popups(keep="taskpeek")

        area = panel.area()
        self.realize()
        self.show_all()
        alloc = self.get_allocation()
        width = max(alloc.width, self.get_preferred_width()[1])
        height = max(alloc.height, self.get_preferred_height()[1])
        ax = panel.anchor_x(anchor)
        aw = anchor.get_allocation().width
        x = ax + aw // 2 - width // 2
        x = max(area.x + 8, min(x, area.x + area.width - width - 8))
        y = panel.top() - height - 8
        self.move(x, y)
        self.resize(width, height)

    def _card(self, window: Wnck.Window) -> Gtk.Button:
        btn = Gtk.Button()
        add_classes(btn, "fos-btn", "ghost", "fos-taskpeek-card")
        btn.set_relief(Gtk.ReliefStyle.NONE)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        pixbuf = window.get_icon()
        if pixbuf is not None:
            scaled = pixbuf.scale_simple(96, 96, GdkPixbuf.InterpType.BILINEAR)
            inner.pack_start(Gtk.Image.new_from_pixbuf(scaled), False, False, 0)
        title = window.get_name() or "Window"
        if len(title) > 28:
            title = title[:25] + "…"
        caption = label(title, "fos-small", xalign=0.5, ellipsize=True)
        caption.set_max_width_chars(18)
        inner.pack_start(caption, False, False, 0)
        btn.add(inner)
        btn.connect("clicked", lambda _b, w=window: self._activate(w))
        return btn

    def _activate(self, window: Wnck.Window) -> None:
        window.activate(x_timestamp(self))
        self.hide_peek()

    def schedule_hide(self, delay_ms: int = 350) -> None:
        self.cancel_hide()

        def hide() -> bool:
            self._hide_id = 0
            self.hide_peek()
            return False

        self._hide_id = GLib.timeout_add(delay_ms, hide)

    def cancel_hide(self) -> None:
        if self._hide_id:
            GLib.source_remove(self._hide_id)
            self._hide_id = 0

    def hide_peek(self) -> None:
        self.cancel_hide()
        self._owner = None
        self.hide()

    def _on_enter(self, _w, _event) -> bool:
        self.cancel_hide()
        return False

    def _on_leave(self, _w, event: Gdk.EventCrossing) -> bool:
        if event.detail == Gdk.NotifyType.INFERIOR:
            return False
        self.schedule_hide()
        return False
