"""Snap layout picker (Win+Z) and window geometry helpers."""

from __future__ import annotations

from dataclasses import dataclass

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gdk, GLib, Gtk, Wnck

from .panel import HEIGHT, SKIP_TYPES, x_timestamp
from .ui import add_classes, button, clear, label


@dataclass(frozen=True)
class Slot:
    """Normalized work-area slot: x,y,w,h in 0..1 fractions."""

    x: float
    y: float
    w: float
    h: float
    label: str = ""


@dataclass(frozen=True)
class Layout:
    name: str
    slots: tuple[Slot, ...]


LAYOUTS: tuple[Layout, ...] = (
    Layout(
        "Two columns",
        (
            Slot(0, 0, 0.5, 1, "Left"),
            Slot(0.5, 0, 0.5, 1, "Right"),
        ),
    ),
    Layout(
        "Three columns",
        (
            Slot(0, 0, 0.25, 1, "Left"),
            Slot(0.25, 0, 0.5, 1, "Center"),
            Slot(0.75, 0, 0.25, 1, "Right"),
        ),
    ),
    Layout(
        "Four corners",
        (
            Slot(0, 0, 0.5, 0.5, "Top left"),
            Slot(0.5, 0, 0.5, 0.5, "Top right"),
            Slot(0, 0.5, 0.5, 0.5, "Bottom left"),
            Slot(0.5, 0.5, 0.5, 0.5, "Bottom right"),
        ),
    ),
    Layout(
        "Left tall",
        (
            Slot(0, 0, 0.5, 1, "Left"),
            Slot(0.5, 0, 0.5, 0.5, "Top right"),
            Slot(0.5, 0.5, 0.5, 0.5, "Bottom right"),
        ),
    ),
    Layout(
        "Right tall",
        (
            Slot(0, 0, 0.5, 0.5, "Top left"),
            Slot(0, 0.5, 0.5, 0.5, "Bottom left"),
            Slot(0.5, 0, 0.5, 1, "Right"),
        ),
    ),
)


def work_area_for_point(root_x: int, root_y: int) -> Gdk.Rectangle:
    display = Gdk.Display.get_default()
    monitor = display.get_monitor_at_point(root_x, root_y)
    if monitor is None:
        monitor = display.get_primary_monitor() or display.get_monitor(0)
    area = monitor.get_geometry()
    return Gdk.Rectangle(area.x, area.y, area.width, max(1, area.height - HEIGHT))


def work_area_for_window(window: Wnck.Window) -> Gdk.Rectangle:
    x, y, w, h = window.get_geometry()
    return work_area_for_point(x + w // 2, y + h // 2)


def slot_rect(area: Gdk.Rectangle, slot: Slot) -> tuple[int, int, int, int]:
    x = area.x + int(round(area.width * slot.x))
    y = area.y + int(round(area.height * slot.y))
    # Size from remaining fraction so adjacent slots share edges without gaps.
    x2 = area.x + int(round(area.width * (slot.x + slot.w)))
    y2 = area.y + int(round(area.height * (slot.y + slot.h)))
    return x, y, max(1, x2 - x), max(1, y2 - y)


def target_window(screen: Wnck.Screen | None = None) -> Wnck.Window | None:
    screen = screen or Wnck.Screen.get_default()
    screen.force_update()
    window = screen.get_active_window()
    if window is not None and not window.is_skip_tasklist() and window.get_window_type() not in SKIP_TYPES:
        return window
    # When the shell popup steals focus, use the previously active client.
    for candidate in reversed(screen.get_windows_stacked()):
        if candidate.is_skip_tasklist() or candidate.get_window_type() in SKIP_TYPES:
            continue
        if candidate.is_minimized():
            continue
        return candidate
    return None


def apply_slot(window: Wnck.Window, slot: Slot, area: Gdk.Rectangle | None = None) -> None:
    area = area or work_area_for_window(window)
    x, y, w, h = slot_rect(area, slot)
    if window.is_maximized():
        window.unmaximize()
    if window.is_minimized():
        stamp = int(GLib.get_monotonic_time() / 1000)
        window.activate(stamp)
    gravity = Wnck.WindowGravity.STATIC
    mask = (
        Wnck.WindowMoveResizeMask.X
        | Wnck.WindowMoveResizeMask.Y
        | Wnck.WindowMoveResizeMask.WIDTH
        | Wnck.WindowMoveResizeMask.HEIGHT
    )
    window.set_geometry(gravity, mask, x, y, w, h)


def move_window_to_workspace(window: Wnck.Window, index: int) -> None:
    screen = Wnck.Screen.get_default()
    screen.force_update()
    if index < 0 or index >= screen.get_workspace_count():
        return
    workspace = screen.get_workspace(index)
    if workspace is None:
        return
    window.move_to_workspace(workspace)


class SnapAssist:
    """After placing one slot, offer remaining slots to the next focused window."""

    def __init__(self, shell) -> None:
        self.shell = shell
        self.pending: list[Slot] = []
        self.area: Gdk.Rectangle | None = None
        self._exclude_xid: int | None = None
        self._handler_id = 0

    def arm(self, remaining: list[Slot], area: Gdk.Rectangle, placed: Wnck.Window) -> None:
        self.clear()
        if not remaining:
            return
        self.pending = list(remaining)
        self.area = area
        self._exclude_xid = placed.get_xid()
        screen = Wnck.Screen.get_default()
        self._handler_id = screen.connect("active-window-changed", self._on_active)

    def clear(self) -> None:
        if self._handler_id:
            try:
                Wnck.Screen.get_default().disconnect(self._handler_id)
            except Exception:
                pass
            self._handler_id = 0
        self.pending = []
        self.area = None
        self._exclude_xid = None

    def _on_active(self, screen: Wnck.Screen, _previous=None) -> None:
        if not self.pending or self.area is None:
            self.clear()
            return
        window = screen.get_active_window()
        if window is None:
            return
        if window.get_xid() == self._exclude_xid:
            return
        if window.is_skip_tasklist() or window.get_window_type() in SKIP_TYPES:
            return
        slot = self.pending.pop(0)
        apply_slot(window, slot, self.area)
        self._exclude_xid = window.get_xid()
        if not self.pending:
            self.clear()
            self.shell.notify_self("Snap layouts", "Layout filled.")
        else:
            left = len(self.pending)
            self.shell.notify_self(
                "Snap layouts",
                f"Placed window. Focus {left} more window{'s' if left != 1 else ''} to fill.",
            )


class SnapLayouts(Gtk.Window):
    """FosOS card with layout diagrams; click a cell to place the focused window."""

    def __init__(self, shell) -> None:
        super().__init__(type=Gtk.WindowType.POPUP)
        self.shell = shell
        self.assist = SnapAssist(shell)
        self.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        add_classes(self, "fos-root", "fos-popup")
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("key-press-event", self._on_key)
        self.connect("button-press-event", self._on_button)
        self.connect("grab-broken-event", lambda *_a: self.hide_picker())

        self.frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card", "fos-snap-layouts")
        self.add(self.frame)
        header = add_classes(Gtk.Box(), "fos-card-header")
        header.pack_start(label("Snap layouts", "fos-title"), False, False, 0)
        self.frame.pack_start(header, False, False, 0)
        body = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "fos-card-content")
        self.frame.pack_start(body, False, False, 0)
        tip = label("Pick a region for the focused window. Remaining regions fill next.", "fos-small", "fos-muted")
        tip.set_line_wrap(True)
        body.pack_start(tip, False, False, 0)
        self.grid = Gtk.Box(spacing=12)
        body.pack_start(self.grid, False, False, 0)
        self._grabbed = False
        self._build()

    def _build(self) -> None:
        clear(self.grid)
        for layout in LAYOUTS:
            card = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6), "fos-snap-layout")
            card.pack_start(label(layout.name, "fos-small", "fos-muted", xalign=0.5), False, False, 0)
            diagram = Gtk.Fixed()
            diagram.set_size_request(120, 72)
            add_classes(diagram, "fos-snap-diagram")
            for index, slot in enumerate(layout.slots):
                cell = add_classes(Gtk.Button(), "fos-btn", "outline", "fos-snap-cell")
                cell.set_can_focus(False)
                cell.set_tooltip_text(slot.label or layout.name)
                cell.connect("clicked", lambda _b, lay=layout, idx=index: self._pick(lay, idx))
                px = int(round(120 * slot.x)) + 2
                py = int(round(72 * slot.y)) + 2
                pw = max(20, int(round(120 * slot.w)) - 4)
                ph = max(16, int(round(72 * slot.h)) - 4)
                cell.set_size_request(pw, ph)
                diagram.put(cell, px, py)
            card.pack_start(diagram, False, False, 0)
            self.grid.pack_start(card, False, False, 0)

        actions = Gtk.Box(spacing=8)
        maximize = button("Maximize", variant="outline", size="sm")
        maximize.connect("clicked", lambda _b: self._maximize())
        actions.pack_start(maximize, False, False, 0)
        clear_btn = button("Clear assist", variant="ghost", size="sm")
        clear_btn.connect("clicked", lambda _b: self._clear_assist())
        actions.pack_start(clear_btn, False, False, 0)
        self.frame.pack_start(actions, False, False, 0)

    def toggle(self) -> None:
        if self.get_visible():
            self.hide_picker()
        else:
            self.open_picker()

    def open_picker(self) -> None:
        self.shell.close_popups(keep="snaplayouts")
        if target_window() is None:
            self.shell.notify_self("Snap layouts", "Focus a window first.")
            return
        self.show_all()
        self._show_centered()
        GLib.idle_add(self._grab)

    def hide_picker(self) -> None:
        if self._grabbed:
            Gdk.Display.get_default().get_default_seat().ungrab()
            self._grabbed = False
        self.hide()

    def _show_centered(self) -> None:
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        area = monitor.get_geometry()
        _minimum, natural = self.get_preferred_size()
        width = natural.width
        height = natural.height
        self.resize(width, height)
        x = area.x + (area.width - width) // 2
        y = area.y + max(24, (area.height - HEIGHT - height) // 3)
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

    def _pick(self, layout: Layout, index: int) -> None:
        window = target_window()
        if window is None:
            self.hide_picker()
            return
        area = work_area_for_window(window)
        slot = layout.slots[index]
        apply_slot(window, slot, area)
        remaining = [s for i, s in enumerate(layout.slots) if i != index]
        self.assist.arm(remaining, area, window)
        self.hide_picker()
        if remaining:
            self.shell.notify_self(
                "Snap layouts",
                f"Placed in {slot.label or 'region'}. Focus another window to fill the next region.",
            )

    def _maximize(self) -> None:
        window = target_window()
        if window is None:
            self.hide_picker()
            return
        self.assist.clear()
        stamp = x_timestamp(self.shell.panel) if self.shell.panel is not None else int(GLib.get_monotonic_time() / 1000)
        window.maximize()
        window.activate(stamp)
        self.hide_picker()

    def _clear_assist(self) -> None:
        self.assist.clear()
        self.shell.notify_self("Snap layouts", "Fill assist cleared.")

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.hide_picker()
            return True
        return False

    def _on_button(self, _widget, event: Gdk.EventButton) -> bool:
        # Clicks on children are handled by buttons; empty chrome dismisses.
        if event.window == self.get_window():
            self.hide_picker()
            return True
        return False
