"""Undecorated card window chrome matching the FosOS Desktop mockup."""

from __future__ import annotations

import subprocess

import cairo
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

from .ui import add_classes, badge, button, icon, label

# Pixel grids captured from Cursor window controls (# = ink), on a 12×12 canvas.
_CAPTION_GLYPHS: dict[str, tuple[str, ...]] = {
    "minimize": (
        "............",
        "............",
        "............",
        "............",
        "............",
        ".##########.",
        "............",
        "............",
        "............",
        "............",
        "............",
        "............",
    ),
    "maximize": (
        "............",
        ".########...",
        ".#......#...",
        ".#......#...",
        ".#......#...",
        ".#......#...",
        ".#......#...",
        ".#......#...",
        ".########...",
        "............",
        "............",
        "............",
    ),
    # Exact restore silhouette from Cursor.
    "restore": (
        "............",
        "...#######..",
        "..........#.",
        "..######..#.",
        ".#......#.#.",
        ".#......#.#.",
        ".#......#.#.",
        ".#......#.#.",
        ".#......#.#.",
        ".#......#...",
        ".########...",
        "............",
    ),
    "close": (
        "............",
        ".#......#...",
        "..#....#....",
        "...#..#.....",
        "....##......",
        "....##......",
        "...#..#.....",
        "..#....#....",
        ".#......#...",
        "............",
        "............",
        "............",
    ),
}


def _caption_pixbuf(kind: str) -> GdkPixbuf.Pixbuf:
    """Rasterize Cursor-matching caption glyphs to a pixbuf."""
    rows = _CAPTION_GLYPHS[kind]
    height = len(rows)
    width = len(rows[0])
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    cr.set_source_rgba(0.96, 0.96, 0.96, 1.0)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == "#":
                cr.rectangle(x, y, 1, 1)
    cr.fill()
    pixbuf = Gdk.pixbuf_get_from_surface(surface, 0, 0, width, height)
    if pixbuf is None:
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, width, height)
        pixbuf.fill(0x00000000)
    return pixbuf


def caption_image(kind: str) -> Gtk.Image:
    """Cursor-matching caption glyph (minimize / maximize / restore / close)."""
    return Gtk.Image.new_from_pixbuf(_caption_pixbuf(kind))


def _caption_button(kind: str, tooltip: str) -> Gtk.Button:
    widget = button(size="icon-xs", tooltip=tooltip)
    widget.add(caption_image(kind))
    return widget


# Outer pixels that start a resize. Undecorated windows have no Openbox frame,
# and there is no compositor, so these are client-side input-only windows
# (the same trick GTK uses for CSD borders). 6px stays above the centered
# caption glyphs. Corners are shown after edges so they win the overlap.
_EDGE_PX = 6
_CORNER_PX = 14

_RESIZE_EDGES: tuple[tuple[Gdk.WindowEdge, str], ...] = (
    (Gdk.WindowEdge.NORTH, "n-resize"),
    (Gdk.WindowEdge.SOUTH, "s-resize"),
    (Gdk.WindowEdge.WEST, "w-resize"),
    (Gdk.WindowEdge.EAST, "e-resize"),
    (Gdk.WindowEdge.NORTH_WEST, "nw-resize"),
    (Gdk.WindowEdge.NORTH_EAST, "ne-resize"),
    (Gdk.WindowEdge.SOUTH_WEST, "sw-resize"),
    (Gdk.WindowEdge.SOUTH_EAST, "se-resize"),
)


class CardWindow(Gtk.ApplicationWindow):
    """A borderless window with a mockup-style title bar."""

    def __init__(
        self,
        application: Gtk.Application,
        *,
        title: str,
        icon_name: str = "folder-symbolic",
        default_width: int = 960,
        default_height: int = 640,
    ) -> None:
        super().__init__(application=application, title=title)
        self.set_default_size(default_width, default_height)
        self.set_decorated(False)
        self.set_resizable(True)
        add_classes(self, "fos-root", "fos-window", "fos-card-window")

        self._maximized = False
        self._fullscreen = False
        self._resize_windows: list[tuple[Gdk.WindowEdge, Gdk.Window]] = []
        self._resize_by_xid: dict[int, Gdk.WindowEdge] = {}
        self._resize_show_queued = False
        self._resize_press: tuple[Gdk.WindowEdge, int, int, int, int] | None = None
        self._resize_grabbed = False
        self._close_queued = False

        self.frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card", "fos-app-frame")
        self.add(self.frame)

        # EventBox owns the titlebar Gdk window so empty chrome (and Terminal
        # tab filler) can begin_move_drag. Undecorated windows have no Openbox
        # Titlebar context — move is entirely app-driven. Gtk.Box cannot
        # set_has_window(True).
        self.header_shell = add_classes(Gtk.EventBox(), "fos-app-header")
        self.header_shell.set_visible_window(True)
        # Match Cursor / VS Code custom titlebar (~30–31px).
        self.header_shell.set_size_request(-1, 30)
        # Padding lives on the inner box — EventBox ignores CSS padding for layout.
        self.header = add_classes(Gtk.Box(spacing=4), "fos-app-header-inner")
        self.header_shell.add(self.header)

        # Plain icon like Cursor — no fos-tile background plate.
        self.header_icon = icon(icon_name, 14)
        self.header_icon.set_valign(Gtk.Align.CENTER)
        self.header_icon.set_margin_end(10)
        self.header.pack_start(self.header_icon, False, False, 0)

        # Center slot: title by default, or tabs (Terminal), etc.
        self.header_center = Gtk.Box(spacing=4)
        self.header_center.set_hexpand(True)
        self.header_center.set_valign(Gtk.Align.CENTER)
        self.title_label = label(title, "fos-title", ellipsize=True)
        self.title_label.set_valign(Gtk.Align.CENTER)
        self.header_center.pack_start(self.title_label, True, True, 0)
        self.header.pack_start(self.header_center, True, True, 0)

        self.badge_label = badge("", "secondary")
        self.badge_label.set_no_show_all(True)
        self.badge_label.hide()
        self.header.pack_start(self.badge_label, False, False, 0)

        # Tight Cursor-like caption cluster (no gap between hit targets).
        self.min_btn = _caption_button("minimize", "Minimize")
        self.max_btn = _caption_button("maximize", "Maximize")
        self.close_btn = _caption_button("close", "Close")
        add_classes(self.close_btn, "close")
        self.min_btn.connect("clicked", lambda _b: self.iconify())
        self.max_btn.connect("clicked", lambda _b: self.toggle_maximize())
        self.max_btn.connect("button-press-event", self._on_max_press)
        self.close_btn.connect("clicked", self._queue_close)
        captions = add_classes(Gtk.Box(spacing=0), "fos-caption-buttons")
        for btn in (self.min_btn, self.max_btn, self.close_btn):
            captions.pack_start(btn, False, False, 0)
        self.header.pack_start(captions, False, False, 0)

        self.header_shell.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.BUTTON1_MOTION_MASK
        )
        self.header_shell.connect("button-press-event", self._on_header_press)
        self.frame.pack_start(self.header_shell, False, False, 0)

        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.body.set_hexpand(True)
        self.body.set_vexpand(True)
        self.frame.pack_start(self.body, True, True, 0)

        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("realize", self._create_resize_windows)
        self.connect("unrealize", self._destroy_resize_windows)
        self.connect("size-allocate", self._layout_resize_windows)
        self.connect("map", self._queue_show_resize_windows)
        self.connect("button-press-event", self._on_resize_press)
        self.connect("motion-notify-event", self._on_resize_motion)
        self.connect("button-release-event", self._on_resize_release)
        self.connect("window-state-event", self._on_window_state)

    def set_badge(self, text: str | None) -> None:
        if text:
            self.badge_label.set_text(text)
            self.badge_label.show()
        else:
            self.badge_label.hide()

    def set_header_title(self, text: str) -> None:
        self.title_label.set_text(text)
        self.set_title(text)

    def set_header_center(self, widget: Gtk.Widget) -> None:
        """Replace the default title with a custom header center (e.g. tabs)."""
        for child in list(self.header_center.get_children()):
            self.header_center.remove(child)
        self.header_center.pack_start(widget, True, True, 0)
        self.header_center.show_all()

    def toggle_maximize(self) -> None:
        if self._maximized:
            self.unmaximize()
        else:
            self.maximize()

    def _open_snap_layouts(self) -> None:
        try:
            subprocess.Popen(
                ["fosos-shell", "--snap-layouts"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass

    def _popup_title_menu(self, event: Gdk.EventButton) -> None:
        menu = Gtk.Menu()
        restore = Gtk.MenuItem(label="Restore")
        restore.set_sensitive(self._maximized)
        restore.connect("activate", lambda _i: self.unmaximize())
        menu.append(restore)
        minimize = Gtk.MenuItem(label="Minimize")
        minimize.connect("activate", lambda _i: self.iconify())
        menu.append(minimize)
        maximize = Gtk.MenuItem(label="Maximize")
        maximize.set_sensitive(not self._maximized)
        maximize.connect("activate", lambda _i: self.maximize())
        menu.append(maximize)
        snap = Gtk.MenuItem(label="Snap layouts…")
        snap.connect("activate", lambda _i: self._open_snap_layouts())
        menu.append(snap)
        menu.append(Gtk.SeparatorMenuItem())
        close = Gtk.MenuItem(label="Close")
        close.connect("activate", self._queue_close)
        menu.append(close)
        menu.show_all()
        menu.popup_at_pointer(event)

    def _on_max_press(self, _button, event: Gdk.EventButton) -> bool:
        if event.button == 3:
            self._open_snap_layouts()
            return True
        return False

    def _resize_allowed(self) -> bool:
        return self.get_resizable() and not self._maximized and not self._fullscreen

    def _create_resize_windows(self, *_args) -> None:
        parent = self.get_window()
        if parent is None or self._resize_windows:
            return
        display = self.get_display()
        for edge, cursor_name in _RESIZE_EDGES:
            cursor = Gdk.Cursor.new_from_name(display, cursor_name)
            if cursor is None:
                cursor = Gdk.Cursor.new_for_display(display, Gdk.CursorType.FLEUR)
            attr = Gdk.WindowAttr()
            attr.x = 0
            attr.y = 0
            attr.width = 1
            attr.height = 1
            attr.window_type = Gdk.WindowType.CHILD
            attr.wclass = Gdk.WindowWindowClass.INPUT_ONLY
            attr.event_mask = (
                Gdk.EventMask.BUTTON_PRESS_MASK
                | Gdk.EventMask.BUTTON_RELEASE_MASK
                | Gdk.EventMask.POINTER_MOTION_MASK
                | Gdk.EventMask.ENTER_NOTIFY_MASK
            )
            attr.cursor = cursor
            gdk_window = Gdk.Window.new(parent, attr, Gdk.WindowAttributesType.CURSOR)
            self.register_window(gdk_window)
            self._resize_windows.append((edge, gdk_window))
            self._resize_by_xid[gdk_window.get_xid()] = edge
        self._layout_resize_windows()

    def _destroy_resize_windows(self, *_args) -> None:
        self._cancel_resize_press()
        for _edge, gdk_window in self._resize_windows:
            self.unregister_window(gdk_window)
            gdk_window.destroy()
        self._resize_windows = []
        self._resize_by_xid = {}

    def _layout_resize_windows(self, *_args) -> None:
        if not self._resize_windows:
            return
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        if width < 2 or height < 2:
            return
        edge_px = min(_EDGE_PX, width // 4, height // 4)
        corner = min(_CORNER_PX, width // 3, height // 3)
        corner = max(corner, edge_px)
        rects = {
            Gdk.WindowEdge.NORTH: (corner, 0, max(1, width - 2 * corner), edge_px),
            Gdk.WindowEdge.SOUTH: (corner, height - edge_px, max(1, width - 2 * corner), edge_px),
            Gdk.WindowEdge.WEST: (0, corner, edge_px, max(1, height - 2 * corner)),
            Gdk.WindowEdge.EAST: (width - edge_px, corner, edge_px, max(1, height - 2 * corner)),
            Gdk.WindowEdge.NORTH_WEST: (0, 0, corner, corner),
            Gdk.WindowEdge.NORTH_EAST: (width - corner, 0, corner, corner),
            Gdk.WindowEdge.SOUTH_WEST: (0, height - corner, corner, corner),
            Gdk.WindowEdge.SOUTH_EAST: (width - corner, height - corner, corner, corner),
        }
        allowed = self._resize_allowed()
        for edge, gdk_window in self._resize_windows:
            x, y, rect_w, rect_h = rects[edge]
            gdk_window.move_resize(int(x), int(y), int(rect_w), int(rect_h))
            if not allowed:
                gdk_window.hide()
            elif not gdk_window.is_visible():
                gdk_window.show()
            else:
                # show() would raise and can disturb an in-progress resize.
                gdk_window.show_unraised()

    def _queue_show_resize_windows(self, *_args) -> None:
        # Content windows map after us and land above the grips. Show again
        # once this flush finishes so a press on the outer pixels hits them.
        if self._resize_show_queued:
            return
        self._resize_show_queued = True
        GLib.idle_add(self._show_resize_windows_idle)

    def _show_resize_windows_idle(self) -> bool:
        self._resize_show_queued = False
        self._layout_resize_windows()
        if self._resize_allowed():
            # Corners are last, so this raise leaves them above the edges.
            for _edge, gdk_window in self._resize_windows:
                gdk_window.show()
        return False

    def _edge_at_event(self, event: Gdk.EventButton) -> Gdk.WindowEdge | None:
        window = event.window
        if window is None:
            return None
        return self._resize_by_xid.get(window.get_xid())

    def _queue_close(self, *_args) -> None:
        # Destroying inside the click handler replays the click onto the
        # window underneath, which then resizes if the pointer is on its edge.
        if self._close_queued:
            return
        self._close_queued = True
        GLib.idle_add(self._close_after_click)

    def _close_after_click(self) -> bool:
        self._close_queued = False
        if self.get_realized():
            self._cancel_resize_press()
            self.close()
        return False

    def _cancel_resize_press(self) -> None:
        grabbed = self._resize_grabbed
        self._resize_press = None
        self._resize_grabbed = False
        if not grabbed:
            return
        display = self.get_display()
        if display is not None:
            display.get_default_seat().ungrab()

    def _on_resize_press(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button != 1 or event.type != Gdk.EventType.BUTTON_PRESS:
            return False
        edge = self._edge_at_event(event)
        if edge is None or not self._resize_allowed():
            return False
        strip = event.window
        if strip is None:
            return False
        self._resize_press = (
            edge,
            int(event.x_root),
            int(event.y_root),
            int(event.button),
            int(event.time),
        )
        # A click that closes the window above can be replayed here. Hold it
        # until the pointer actually moves, so a plain click does not resize.
        seat = self.get_display().get_default_seat()
        status = seat.grab(
            strip,
            Gdk.SeatCapabilities.ALL_POINTING,
            False,
            strip.get_cursor(),
            event,
            None,
        )
        self._resize_grabbed = status == Gdk.GrabStatus.SUCCESS
        GLib.timeout_add(200, self._drop_resize_if_released)
        return True

    def _drop_resize_if_released(self) -> bool:
        if self._resize_press is None:
            return False
        gdk_window = self.get_window()
        display = self.get_display()
        if gdk_window is None or display is None:
            self._cancel_resize_press()
            return False
        device = display.get_default_seat().get_pointer()
        _under, _x, _y, mask = gdk_window.get_device_position(device)
        if not (mask & Gdk.ModifierType.BUTTON1_MASK):
            self._cancel_resize_press()
        return False

    def _on_resize_motion(self, _widget, event: Gdk.EventMotion) -> bool:
        pending = self._resize_press
        if pending is None:
            return False
        _edge, x_root, y_root, _button, _time = pending
        if abs(event.x_root - x_root) < 5 and abs(event.y_root - y_root) < 5:
            return True
        self._begin_pending_resize()
        return True

    def _on_resize_release(self, _widget, event: Gdk.EventButton) -> bool:
        if self._resize_press is None or event.button != 1:
            return False
        self._cancel_resize_press()
        return True

    def _begin_pending_resize(self) -> None:
        pending = self._resize_press
        grabbed = self._resize_grabbed
        self._resize_press = None
        self._resize_grabbed = False
        if pending is None:
            return
        if grabbed:
            display = self.get_display()
            if display is not None:
                display.get_default_seat().ungrab()
        edge, x_root, y_root, button, time = pending
        gdk_window = self.get_window()
        if gdk_window is None or not self._resize_allowed():
            return
        gdk_window.begin_resize_drag(edge, button, x_root, y_root, time)

    def _on_window_state(self, _window, event: Gdk.EventWindowState) -> bool:
        state = event.new_window_state
        self._maximized = bool(state & Gdk.WindowState.MAXIMIZED)
        self._fullscreen = bool(state & Gdk.WindowState.FULLSCREEN)
        self._layout_resize_windows()
        style = self.get_style_context()
        if self._maximized:
            style.add_class("maximized")
        else:
            style.remove_class("maximized")
        child = self.max_btn.get_child()
        if isinstance(child, Gtk.Image):
            kind = "restore" if self._maximized else "maximize"
            child.set_from_pixbuf(_caption_pixbuf(kind))
        self.max_btn.set_tooltip_text("Restore" if self._maximized else "Maximize")
        return False

    def begin_titlebar_move(self, event: Gdk.EventButton) -> bool:
        """Start an interactive window move from a titlebar / drag-area press.

        Windows 11: dragging a maximized (or fullscreen) titlebar restores the
        window to its normal size under the pointer, then moves it.
        """
        if event.button != 1:
            return False
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self.toggle_maximize()
            return True
        window = self.get_window()
        if window is None:
            return False
        if self._maximized or self._fullscreen:
            return self._begin_move_from_maximized(event)
        Gdk.Window.begin_move_drag(
            window,
            int(event.button),
            int(event.x_root),
            int(event.y_root),
            int(event.time),
        )
        return True

    def _begin_move_from_maximized(self, event: Gdk.EventButton) -> bool:
        """Unmaximize/unfullscreen, place under the cursor, then start the drag."""
        px = int(event.x_root)
        py = int(event.y_root)
        ox, oy = self.get_position()
        ow, oh = self.get_size()
        # Keep the grab point on the same relative spot of the restored titlebar.
        rel_x = (px - ox) / max(ow, 1)
        rel_x = max(0.08, min(rel_x, 0.92))
        title_y = max(8, int(event.y))
        button = int(event.button)
        time = int(event.time)
        want_unmax = self._maximized
        want_unfs = self._fullscreen

        if want_unfs:
            self.unfullscreen()
        if want_unmax:
            self.unmaximize()

        def start_drag(pass_no: int = 0) -> bool:
            if (want_unmax and self._maximized) or (want_unfs and self._fullscreen):
                if pass_no < 12:
                    GLib.timeout_add(16, lambda n=pass_no + 1: start_drag(n))
                return False
            w, h = self.get_size()
            # If the WM has not restored a floating size yet, shrink to a
            # Windows-like portion of the work area so the drag is usable.
            screen = self.get_screen()
            if screen is not None and (w >= screen.get_width() - 8 or h >= screen.get_height() - 48):
                mon = screen.get_monitor_geometry(screen.get_monitor_at_point(px, py))
                w = max(480, min(w, int(mon.width * 0.55)))
                h = max(320, min(h, int(mon.height * 0.55)))
                self.resize(w, h)
                w, h = self.get_size()
            new_x = int(px - rel_x * w)
            new_y = int(py - title_y)
            self.move(new_x, new_y)
            gdk_window = self.get_window()
            if gdk_window is not None:
                Gdk.Window.begin_move_drag(gdk_window, button, px, py, time)
            return False

        GLib.idle_add(lambda: start_drag(0))
        return True

    def _on_header_press(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button == 3:
            self._popup_title_menu(event)
            return True
        if event.button != 1:
            return False
        # Gtk.Button children consume their own presses; remaining header clicks drag.
        return self.begin_titlebar_move(event)
