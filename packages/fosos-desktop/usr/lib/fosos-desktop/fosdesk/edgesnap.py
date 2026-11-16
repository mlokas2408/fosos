"""Drag a window to screen edges/corners to snap (Win-like)."""

from __future__ import annotations

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gdk, GLib, Wnck

from .panel import HEIGHT, SKIP_TYPES
from .snaplayouts import Slot, apply_slot, work_area_for_point

TOP_EDGE_PX = 12
SIDE_EDGE_PX = 16
CORNER_PX = 48
POLL_MS = 50

# Named slots for edge/corner release targets.
TOP = Slot(0, 0, 1, 1, "Maximize")  # special-cased
LEFT = Slot(0, 0, 0.5, 1, "Left")
RIGHT = Slot(0.5, 0, 0.5, 1, "Right")
TOP_LEFT = Slot(0, 0, 0.5, 0.5, "Top left")
TOP_RIGHT = Slot(0.5, 0, 0.5, 0.5, "Top right")
BOTTOM_LEFT = Slot(0, 0.5, 0.5, 0.5, "Bottom left")
BOTTOM_RIGHT = Slot(0.5, 0.5, 0.5, 0.5, "Bottom right")


class EdgeSnap:
    """Poll pointer button state; on left-button release near an edge, snap."""

    def __init__(self) -> None:
        self._was_pressed = False
        self._disp = None
        self._root = None
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
        if self._was_pressed and not pressed:
            self._maybe_snap(pointer.root_x, pointer.root_y)
        self._was_pressed = pressed
        return True

    def _maybe_snap(self, root_x: int, root_y: int) -> None:
        display = Gdk.Display.get_default()
        if display is None:
            return
        monitor = display.get_monitor_at_point(root_x, root_y)
        if monitor is None:
            monitor = display.get_primary_monitor() or display.get_monitor(0)
        geom = monitor.get_geometry()
        work = work_area_for_point(root_x, root_y)

        near_left = root_x <= geom.x + SIDE_EDGE_PX
        near_right = root_x >= geom.x + geom.width - SIDE_EDGE_PX
        near_top = root_y <= geom.y + TOP_EDGE_PX
        # Bottom edge is above the panel strip.
        near_bottom = root_y >= geom.y + geom.height - HEIGHT - SIDE_EDGE_PX
        near_top_corner = root_y <= geom.y + CORNER_PX
        near_bottom_corner = root_y >= geom.y + geom.height - HEIGHT - CORNER_PX

        slot: Slot | None = None
        maximize = False
        if near_left and near_top_corner:
            slot = TOP_LEFT
        elif near_right and near_top_corner:
            slot = TOP_RIGHT
        elif near_left and near_bottom_corner:
            slot = BOTTOM_LEFT
        elif near_right and near_bottom_corner:
            slot = BOTTOM_RIGHT
        elif near_top and not near_left and not near_right:
            maximize = True
        elif near_left:
            slot = LEFT
        elif near_right:
            slot = RIGHT
        elif near_bottom:
            # Bottom edge alone does nothing (show-desktop territory).
            return
        else:
            return

        screen = Wnck.Screen.get_default()
        screen.force_update()
        window = screen.get_active_window()
        if window is None:
            return
        if window.is_skip_tasklist() or window.get_window_type() in SKIP_TYPES:
            return
        _x, _y, _w, height = window.get_geometry()
        if height <= HEIGHT + 8:
            return

        stamp = int(GLib.get_monotonic_time() / 1000)
        if maximize:
            if window.is_maximized():
                return
            window.maximize()
            window.activate(stamp)
            return
        assert slot is not None
        apply_slot(window, slot, work)
        window.activate(stamp)
