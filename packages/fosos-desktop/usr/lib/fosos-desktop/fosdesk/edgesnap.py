"""Drag a window to screen edges/corners to snap (Win-like), with zone preview."""

from __future__ import annotations

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gdk, GLib, Gtk, Wnck

from .panel import HEIGHT, SKIP_TYPES
from .snaplayouts import (
    BOTTOM_LEFT,
    BOTTOM_RIGHT,
    LEFT,
    RIGHT,
    TOP_LEFT,
    TOP_RIGHT,
    Slot,
    apply_slot,
    remember_normal_geometry,
    slot_rect,
    work_area_for_point,
)
from .ui import add_classes, load_css

TOP_EDGE_PX = 12
SIDE_EDGE_PX = 16
CORNER_PX = 48
POLL_MS = 50


class SnapZoneOverlay(Gtk.Window):
    """Translucent rectangle showing the pending snap target."""

    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
        self.set_accept_focus(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_decorated(False)
        screen = self.get_screen()
        visual = screen.get_rgba_visual() if screen is not None else None
        if visual is not None and screen.is_composited():
            self.set_visual(visual)
            self.set_app_paintable(True)
        add_classes(self, "fos-root", "fos-snap-zone")
        self._box = add_classes(Gtk.EventBox(), "fos-snap-zone-fill")
        self.add(self._box)
        self._box.show()

    def show_rect(self, x: int, y: int, w: int, h: int) -> None:
        load_css()
        self.resize(max(1, w), max(1, h))
        self.move(x, y)
        if not self.get_visible():
            self.show_all()
        else:
            self.present()

    def hide_zone(self) -> None:
        if self.get_visible():
            self.hide()


class EdgeSnap:
    """Poll pointer button state; preview zones while dragging; snap on release."""

    def __init__(self) -> None:
        self._was_pressed = False
        self._press_geom: tuple[int, tuple[int, int, int, int]] | None = None
        self._disp = None
        self._root = None
        self._overlay = SnapZoneOverlay()
        self._zone_key: str | None = None
        try:
            from Xlib import X
            from Xlib import display as xdisplay

            self._X = X
            self._disp = xdisplay.Display()
            self._root = self._disp.screen().root
            GLib.timeout_add(POLL_MS, self._poll)
        except Exception:
            self._disp = None

    def _poll(self) -> bool:
        if self._disp is None or self._root is None:
            return False
        try:
            pointer = self._root.query_pointer()
        except Exception:
            return True
        pressed = bool(pointer.mask & self._X.Button1Mask)
        root_x, root_y = pointer.root_x, pointer.root_y
        if pressed and not self._was_pressed:
            self._remember_press()
        # Selecting text (or anything else inside the window) also holds
        # button 1. Snap only after the window itself has been dragged.
        kind = self._drag_kind()
        if pressed:
            if kind == "move":
                self._update_preview(root_x, root_y)
            else:
                self._overlay.hide_zone()
                self._zone_key = None
        elif self._was_pressed:
            self._overlay.hide_zone()
            self._zone_key = None
            if kind == "move":
                self._maybe_snap(root_x, root_y)
            self._press_geom = None
        else:
            self._overlay.hide_zone()
            self._zone_key = None
        self._was_pressed = pressed
        return True

    def _remember_press(self) -> None:
        window = self._drag_window_ok()
        if window is None:
            self._press_geom = None
            return
        self._press_geom = (window.get_xid(), window.get_geometry())

    def _drag_kind(self) -> str:
        """How this button-1 hold changed the active window: move, resize, or none.

        A text selection holds the button and can reach the screen edge without
        moving the window. Edge snap runs only for a real title-bar drag.
        """
        if self._press_geom is None:
            return "none"
        xid, (x, y, width, height) = self._press_geom
        window = self._drag_window_ok()
        if window is None or window.get_xid() != xid:
            return "none"
        new_x, new_y, new_width, new_height = window.get_geometry()
        dx = abs(new_x - x)
        dy = abs(new_y - y)
        dw = abs(new_width - width)
        dh = abs(new_height - height)
        # Pulling the left or top edge keeps the opposite edge put.
        right_fixed = dw >= 8 and abs((new_x + new_width) - (x + width)) <= 8
        bottom_fixed = dh >= 8 and abs((new_y + new_height) - (y + height)) <= 8
        if right_fixed or bottom_fixed:
            return "resize"
        # Right/bottom edge: origin stays, size changes.
        if (dw >= 8 or dh >= 8) and dx < 8 and dy < 8:
            return "resize"
        if dx >= 8 or dy >= 8:
            return "move"
        return "none"

    def _target_at(
        self, root_x: int, root_y: int
    ) -> tuple[str, Slot | None, bool, Gdk.Rectangle] | None:
        display = Gdk.Display.get_default()
        if display is None:
            return None
        monitor = display.get_monitor_at_point(root_x, root_y)
        if monitor is None:
            monitor = display.get_primary_monitor() or display.get_monitor(0)
        geom = monitor.get_geometry()
        work = work_area_for_point(root_x, root_y)

        near_left = root_x <= geom.x + SIDE_EDGE_PX
        near_right = root_x >= geom.x + geom.width - SIDE_EDGE_PX
        near_top = root_y <= geom.y + TOP_EDGE_PX
        near_bottom = root_y >= geom.y + geom.height - HEIGHT - SIDE_EDGE_PX
        near_top_corner = root_y <= geom.y + CORNER_PX
        near_bottom_corner = root_y >= geom.y + geom.height - HEIGHT - CORNER_PX

        if near_left and near_top_corner:
            return ("top-left", TOP_LEFT, False, work)
        if near_right and near_top_corner:
            return ("top-right", TOP_RIGHT, False, work)
        if near_left and near_bottom_corner:
            return ("bottom-left", BOTTOM_LEFT, False, work)
        if near_right and near_bottom_corner:
            return ("bottom-right", BOTTOM_RIGHT, False, work)
        if near_top and not near_left and not near_right:
            return ("maximize", None, True, work)
        if near_left:
            return ("left", LEFT, False, work)
        if near_right:
            return ("right", RIGHT, False, work)
        if near_bottom:
            return None
        return None

    def _drag_window_ok(self) -> Wnck.Window | None:
        screen = Wnck.Screen.get_default()
        screen.force_update()
        window = screen.get_active_window()
        if window is None:
            return None
        if window.is_skip_tasklist() or window.get_window_type() in SKIP_TYPES:
            return None
        _x, _y, _w, height = window.get_geometry()
        if height <= HEIGHT + 8:
            return None
        return window

    def _reduce_motion(self) -> bool:
        try:
            from .settings_pages import load_kv, truthy

            return truthy(load_kv("accessibility", {}).get("reduce_motion"), False)
        except Exception:
            return False

    def _update_preview(self, root_x: int, root_y: int) -> None:
        if self._reduce_motion():
            self._overlay.hide_zone()
            self._zone_key = None
            return
        if self._drag_window_ok() is None:
            self._overlay.hide_zone()
            self._zone_key = None
            return
        target = self._target_at(root_x, root_y)
        if target is None:
            self._overlay.hide_zone()
            self._zone_key = None
            return
        key, slot, maximize, work = target
        if key == self._zone_key and self._overlay.get_visible():
            return
        self._zone_key = key
        if maximize:
            self._overlay.show_rect(work.x, work.y, work.width, work.height)
        else:
            assert slot is not None
            x, y, w, h = slot_rect(work, slot)
            self._overlay.show_rect(x, y, w, h)

    def _maybe_snap(self, root_x: int, root_y: int) -> None:
        target = self._target_at(root_x, root_y)
        if target is None:
            return
        _key, slot, maximize, work = target
        window = self._drag_window_ok()
        # The window under the pointer can change when the front one closes
        # mid-click. Never snap that newly focused window.
        if window is None or self._press_geom is None or window.get_xid() != self._press_geom[0]:
            return

        stamp = int(GLib.get_monotonic_time() / 1000)
        if maximize:
            if window.is_maximized():
                return
            remember_normal_geometry(window)
            window.maximize()
            window.activate(stamp)
            return
        assert slot is not None
        apply_slot(window, slot, work)
        window.activate(stamp)
