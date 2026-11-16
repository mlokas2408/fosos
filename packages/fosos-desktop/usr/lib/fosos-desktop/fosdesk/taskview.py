"""Task View (Win+Tab): windows and virtual desktops overview."""

from __future__ import annotations

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Wnck

from .panel import HEIGHT, SKIP_TYPES, x_timestamp
from .snaplayouts import move_window_to_workspace
from .ui import add_classes, clear, icon, label


def overview_windows(screen: Wnck.Screen) -> list[Wnck.Window]:
    screen.force_update()
    result = []
    for window in reversed(screen.get_windows_stacked()):
        if window.is_skip_tasklist() or window.get_window_type() in SKIP_TYPES:
            continue
        if window.is_skip_pager():
            continue
        result.append(window)
    return result


class TaskView(Gtk.Window):
    def __init__(self, shell) -> None:
        super().__init__(type=Gtk.WindowType.POPUP)
        self.shell = shell
        self.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_app_paintable(True)
        add_classes(self, "fos-root", "fos-taskview")
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("key-press-event", self._on_key)
        self.connect("button-press-event", self._on_button)
        self.connect("draw", self._on_draw)
        self.connect("grab-broken-event", lambda *_a: self.hide_view())

        self.outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.outer.set_margin_start(24)
        self.outer.set_margin_end(24)
        self.outer.set_margin_top(24)
        self.outer.set_margin_bottom(24)
        self.add(self.outer)

        header = Gtk.Box(spacing=12)
        header.pack_start(label("Task View", "fos-title"), False, False, 0)
        tip = label("Click a window or desktop. Right-click a window to move it.", "fos-small", "fos-muted")
        tip.set_halign(Gtk.Align.END)
        tip.set_hexpand(True)
        header.pack_end(tip, True, True, 0)
        self.outer.pack_start(header, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        scroller.add(self.content)
        self.outer.pack_start(scroller, True, True, 0)

        self._grabbed = False
        self._workspace_boxes: list[Gtk.Box] = []

    def toggle(self) -> None:
        if self.get_visible():
            self.hide_view()
        else:
            self.open_view()

    def open_view(self) -> None:
        self.shell.close_popups(keep="taskview")
        if self.shell.alt_tab.get_visible():
            self.shell.alt_tab.hide_switcher()
        self._rebuild()
        self._place_fullscreen()
        self.show_all()
        self.present()
        GLib.idle_add(self._grab)

    def hide_view(self) -> None:
        if self._grabbed:
            Gdk.Display.get_default().get_default_seat().ungrab()
            self._grabbed = False
        self.hide()
        clear(self.content)
        self._workspace_boxes = []

    def _place_fullscreen(self) -> None:
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        area = monitor.get_geometry()
        # Cover the work area above the panel.
        height = max(200, area.height - HEIGHT)
        self.move(area.x, area.y)
        self.resize(area.width, height)
        self.set_size_request(area.width, height)

    def _grab(self) -> bool:
        window = self.get_window()
        if window is None or not self.get_visible():
            return False
        seat = Gdk.Display.get_default().get_default_seat()
        status = seat.grab(window, Gdk.SeatCapabilities.ALL, True, None, None, None)
        self._grabbed = status == Gdk.GrabStatus.SUCCESS
        return False

    def _rebuild(self) -> None:
        clear(self.content)
        self._workspace_boxes = []
        screen = Wnck.Screen.get_default()
        screen.force_update()
        windows = overview_windows(screen)
        active_ws = screen.get_active_workspace()
        active_xid = None
        active_win = screen.get_active_window()
        if active_win is not None:
            active_xid = active_win.get_xid()

        row = Gtk.Box(spacing=16)
        row.set_halign(Gtk.Align.CENTER)
        count = screen.get_workspace_count()
        for index in range(count):
            workspace = screen.get_workspace(index)
            name = workspace.get_name() if workspace is not None else f"Desktop {index + 1}"
            is_active = active_ws is not None and workspace is not None and active_ws == workspace
            card = self._workspace_card(index, name, is_active, windows, active_xid)
            row.pack_start(card, False, False, 0)
            self._workspace_boxes.append(card)
        self.content.pack_start(row, False, False, 0)

    def _workspace_card(
        self,
        index: int,
        name: str,
        is_active: bool,
        windows: list[Wnck.Window],
        active_xid: int | None,
    ) -> Gtk.Box:
        card = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), "fos-card", "fos-taskview-desk")
        if is_active:
            add_classes(card, "active")
        card.set_size_request(280, -1)

        title_btn = add_classes(Gtk.Button(), "fos-btn", "ghost")
        title_btn.set_can_focus(False)
        title_box = Gtk.Box(spacing=8)
        title_box.pack_start(label(name, "fos-text", "fos-strong"), False, False, 0)
        if is_active:
            title_box.pack_start(label("Current", "fos-small", "fos-muted"), False, False, 0)
        title_btn.add(title_box)
        title_btn.connect("clicked", lambda _b, i=index: self._activate_workspace(i))
        card.pack_start(title_btn, False, False, 0)

        screen = Wnck.Screen.get_default()
        workspace = screen.get_workspace(index)
        local = []
        for window in windows:
            ws = window.get_workspace()
            if window.is_pinned() or (ws is not None and workspace is not None and ws == workspace):
                local.append(window)

        if not local:
            empty = label("No windows", "fos-small", "fos-muted", xalign=0.5)
            empty.set_margin_top(24)
            empty.set_margin_bottom(24)
            card.pack_start(empty, False, False, 0)
            return card

        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_max_children_per_line(2)
        flow.set_min_children_per_line(1)
        flow.set_homogeneous(True)
        flow.set_column_spacing(8)
        flow.set_row_spacing(8)
        for window in local:
            flow.add(self._window_tile(window, window.get_xid() == active_xid, index))
        card.pack_start(flow, False, False, 0)
        return card

    def _window_tile(self, window: Wnck.Window, is_active: bool, workspace_index: int) -> Gtk.Button:
        tile = add_classes(Gtk.Button(), "fos-btn", "ghost", "fos-taskview-window")
        if is_active:
            add_classes(tile, "default")
        tile.set_can_focus(False)
        tile.set_size_request(120, 100)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        pixbuf = window.get_icon()
        if pixbuf is not None:
            scaled = pixbuf.scale_simple(40, 40, GdkPixbuf.InterpType.BILINEAR)
            box.pack_start(Gtk.Image.new_from_pixbuf(scaled), False, False, 0)
        else:
            box.pack_start(icon("application-x-executable-symbolic", 40), False, False, 0)
        title = label(window.get_name() or "Window", "fos-small", xalign=0.5, ellipsize=True)
        box.pack_start(title, False, False, 0)
        tile.add(box)
        tile.connect("clicked", lambda _b, w=window: self._activate_window(w))
        tile.connect("button-press-event", lambda _b, event, w=window, wi=workspace_index: self._on_window_press(w, wi, event))
        return tile

    def _on_window_press(self, window: Wnck.Window, workspace_index: int, event: Gdk.EventButton) -> bool:
        if event.button != 3:
            return False
        menu = Gtk.Menu()
        screen = Wnck.Screen.get_default()
        count = screen.get_workspace_count()
        for index in range(count):
            if index == workspace_index and not window.is_pinned():
                continue
            ws = screen.get_workspace(index)
            name = ws.get_name() if ws is not None else f"Desktop {index + 1}"
            item = Gtk.MenuItem(label=f"Move to {name}")
            item.connect("activate", lambda _i, w=window, idx=index: self._move_and_refresh(w, idx))
            menu.append(item)
        activate = Gtk.MenuItem(label="Switch to")
        activate.connect("activate", lambda _i, w=window: self._activate_window(w))
        menu.append(Gtk.SeparatorMenuItem())
        menu.append(activate)
        close = Gtk.MenuItem(label="Close")
        close.connect("activate", lambda _i, w=window: self._close_window(w))
        menu.append(close)
        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def _move_and_refresh(self, window: Wnck.Window, index: int) -> None:
        move_window_to_workspace(window, index)
        self._rebuild()
        self.content.show_all()

    def _close_window(self, window: Wnck.Window) -> None:
        stamp = x_timestamp(self.shell.panel) if self.shell.panel is not None else int(GLib.get_monotonic_time() / 1000)
        window.close(stamp)
        GLib.timeout_add(200, self._refresh_keep_open)

    def _refresh_keep_open(self) -> bool:
        if self.get_visible():
            self._rebuild()
            self.content.show_all()
        return False

    def _activate_workspace(self, index: int) -> None:
        self.hide_view()
        self.shell.switch_workspace(index)

    def _activate_window(self, window: Wnck.Window) -> None:
        stamp = x_timestamp(self.shell.panel) if self.shell.panel is not None else int(GLib.get_monotonic_time() / 1000)
        workspace = window.get_workspace()
        if workspace is not None:
            workspace.activate(stamp)
        window.activate(stamp)
        self.hide_view()

    def _on_draw(self, _widget, cr) -> bool:
        alloc = self.get_allocation()
        cr.set_source_rgba(0.04, 0.04, 0.04, 0.88)
        cr.rectangle(0, 0, alloc.width, alloc.height)
        cr.fill()
        return False

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.hide_view()
            return True
        if event.keyval == Gdk.KEY_Tab and (event.state & Gdk.ModifierType.SUPER_MASK):
            # Super still held + Tab again cycles workspaces while open.
            screen = Wnck.Screen.get_default()
            active = screen.get_active_workspace()
            count = screen.get_workspace_count()
            if count and active is not None:
                nxt = (active.get_number() + 1) % count
                self.shell.switch_workspace(nxt)
                self._rebuild()
                self.content.show_all()
            return True
        return True

    def _on_button(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button == 1 and event.window == self.get_window():
            self.hide_view()
            return True
        return False
