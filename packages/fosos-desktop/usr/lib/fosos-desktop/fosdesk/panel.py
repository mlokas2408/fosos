"""The FosOS taskbar along the bottom of each monitor."""

import time

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gdk, GdkX11, GLib, Gtk, Wnck  # noqa: F401 (GdkX11 enables get_xid)

from . import apps as appmod
from .indicators import battery_present, brightness_available
from .ui import (
    BRAND,
    add_classes,
    badge,
    button,
    clear,
    icon,
    label,
    separator,
    set_class,
    start_icon,
    task_view_icon,
)

HEIGHT = 48
SKIP_TYPES = (Wnck.WindowType.DESKTOP, Wnck.WindowType.DOCK, Wnck.WindowType.SPLASHSCREEN)
PIN_DRAG_TARGET = [Gtk.TargetEntry.new("application/x-fosos-pin", Gtk.TargetFlags.SAME_APP, 0)]


def primary_monitor() -> Gdk.Rectangle:
    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor() or display.get_monitor(0)
    return monitor.get_geometry()


def x_timestamp(widget: Gtk.Widget) -> int:
    stamp = Gtk.get_current_event_time()
    if stamp:
        return stamp
    window = widget.get_window()
    if window is not None:
        return GdkX11.x11_get_server_time(window)
    return int(time.time())


def set_struts(window: Gdk.Window, area: Gdk.Rectangle, height: int) -> None:
    """Reserve the panel strip so maximized windows stop above it."""
    try:
        from Xlib import Xatom
        from Xlib import display as xdisplay
    except ImportError:
        return
    screen = Gdk.Screen.get_default()
    root_height = screen.get_height()
    bottom = root_height - (area.y + area.height) + height
    disp = xdisplay.Display()
    try:
        xwin = disp.create_resource_object("window", window.get_xid())
        partial = [0, 0, 0, bottom, 0, 0, 0, 0, 0, 0, area.x, area.x + area.width - 1]
        xwin.change_property(disp.intern_atom("_NET_WM_STRUT_PARTIAL"), Xatom.CARDINAL, 32, partial)
        xwin.change_property(disp.intern_atom("_NET_WM_STRUT"), Xatom.CARDINAL, 32, [0, 0, 0, bottom])
        disp.flush()
    finally:
        disp.close()


def window_center(window: Wnck.Window) -> tuple[int, int]:
    x, y, width, height = window.get_geometry()
    return x + width // 2, y + height // 2


def point_in_rect(x: int, y: int, area: Gdk.Rectangle) -> bool:
    return area.x <= x < area.x + area.width and area.y <= y < area.y + area.height


class TaskButton(Gtk.Box):
    """A pinned or running app with its running indicator underneath."""

    def __init__(self, panel: "Panel", app: appmod.App | None, window: Wnck.Window | None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.panel = panel
        self.app = app
        self.lone_window = window
        if app is not None:
            name, icon_name = app.name, app.icon_name()
        else:
            name = window.get_class_group_name() or window.get_name()
            icon_name = None
        # Pinned / running apps use a larger glyph than the status cluster.
        self.button = button(variant="ghost", size="icon", tooltip=name)
        add_classes(self.button, "fos-task-btn")
        if icon_name:
            self.button.add(icon(icon_name, 20))
        else:
            self.button.add(icon("application-x-executable-symbolic", 20))
        self.button.connect("clicked", self._on_clicked)
        self.button.connect("button-press-event", self._on_press)
        self.button.connect("button-release-event", self._on_release)
        self.indicator = Gtk.Box()
        self.indicator.set_halign(Gtk.Align.CENTER)
        self.indicator.set_no_show_all(True)
        self.indicator.hide()
        add_classes(self.indicator, "fos-indicator")
        self.pack_start(self.button, False, False, 0)
        self.pack_start(self.indicator, False, False, 0)
        self.set_valign(Gtk.Align.CENTER)
        self._setup_pin_drag()

    def _setup_pin_drag(self) -> None:
        if self.app is None or not self.panel.shell.pinned.contains(self.app.id):
            return
        self.button.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            PIN_DRAG_TARGET,
            Gdk.DragAction.MOVE,
        )
        self.button.drag_source_set_icon_name(self.app.icon_name())
        self.button.connect("drag-data-get", self._on_drag_data_get)
        self.button.drag_dest_set(
            Gtk.DestDefaults.ALL,
            PIN_DRAG_TARGET,
            Gdk.DragAction.MOVE,
        )
        self.button.connect("drag-data-received", self._on_drag_data_received)
        self.button.connect("drag-motion", self._on_drag_motion)

    def windows(self) -> list[Wnck.Window]:
        if self.app is None:
            return [self.lone_window] if self.lone_window is not None else []
        return self.panel.windows_for(self.app)

    def refresh(self) -> None:
        windows = self.windows()
        running = bool(windows)
        active = self.panel.active_window()
        focused = active is not None and active in windows
        shown = any(not w.is_minimized() for w in windows)
        set_class(self.button, "secondary", running and shown)
        set_class(self.button, "ghost", not (running and shown))
        set_class(self.indicator, "focused", focused and shown)
        # Line only while the app is open — never a mark under idle pins.
        if running:
            self.indicator.set_size_request(22 if focused and shown else 18, 2)
            self.indicator.show()
        else:
            self.indicator.hide()
        if self.app is None and self.lone_window is not None:
            self.button.set_tooltip_text(self.lone_window.get_name())

    def _on_clicked(self, _button) -> None:
        self.panel.shell.close_popups()
        windows = self.windows()
        stamp = x_timestamp(self)
        if not windows:
            if self.app is not None:
                self.app.launch()
            return
        active = self.panel.active_window()
        stacked = [w for w in self.panel.screen.get_windows_stacked() if w in windows]
        if active is not None and active in windows and not active.is_minimized():
            # One focused window → minimize. Several → cycle like Win taskbar groups.
            if len(windows) == 1:
                active.minimize()
                return
            try:
                index = stacked.index(active)
            except ValueError:
                index = len(stacked) - 1
            target = stacked[(index + 1) % len(stacked)]
            target.activate(stamp)
            return
        target = stacked[-1] if stacked else windows[0]
        target.activate(stamp)

    def _on_press(self, _button, event: Gdk.EventButton) -> bool:
        if event.button == 3:
            self._popup_menu(event)
            return True
        return False

    def _on_release(self, _button, event: Gdk.EventButton) -> bool:
        if event.button == 2 and self.app is not None:
            self.app.launch()
            return True
        return False

    def _popup_menu(self, event: Gdk.EventButton) -> None:
        self.panel.shell.close_popups()
        menu = Gtk.Menu()
        windows = self.windows()

        if self.app is not None:
            pinned = self.panel.shell.pinned.contains(self.app.id)
            pin_item = Gtk.MenuItem(label="Unpin from taskbar" if pinned else "Pin to taskbar")
            pin_item.connect("activate", lambda _i: self._toggle_pin())
            menu.append(pin_item)
            new_item = Gtk.MenuItem(label="Open new window")
            new_item.connect("activate", lambda _i: self.app.launch())
            menu.append(new_item)

        if windows:
            if self.app is not None or len(windows) > 1:
                menu.append(Gtk.SeparatorMenuItem())
            move_target = windows[0] if len(windows) == 1 else None
            if move_target is not None:
                move_menu = Gtk.Menu()
                screen = self.panel.screen
                active_ws = move_target.get_workspace()
                for index in range(screen.get_workspace_count()):
                    workspace = screen.get_workspace(index)
                    name = workspace.get_name() if workspace is not None else f"Desktop {index + 1}"
                    item = Gtk.MenuItem(label=name)
                    if active_ws is not None and workspace is not None and active_ws == workspace:
                        item.set_sensitive(False)
                    item.connect(
                        "activate",
                        lambda _i, w=move_target, idx=index: self.panel.shell.move_window_to_workspace(w, idx),
                    )
                    move_menu.append(item)
                move_item = Gtk.MenuItem(label="Move to")
                move_item.set_submenu(move_menu)
                menu.append(move_item)
                menu.append(Gtk.SeparatorMenuItem())
            if len(windows) == 1:
                close_item = Gtk.MenuItem(label="Close window")
                close_item.connect("activate", lambda _i: self._close_windows(windows))
                menu.append(close_item)
            else:
                close_item = Gtk.MenuItem(label=f"Close all windows ({len(windows)})")
                close_item.connect("activate", lambda _i: self._close_windows(windows))
                menu.append(close_item)

        if not menu.get_children():
            return
        menu.show_all()
        menu.popup_at_pointer(event)

    def _toggle_pin(self) -> None:
        if self.app is None:
            return
        self.panel.shell.pinned.toggle(self.app.id)

    def _close_windows(self, windows: list[Wnck.Window]) -> None:
        stamp = x_timestamp(self)
        for window in list(windows):
            window.close(stamp)

    def _on_drag_data_get(self, _widget, _context, data, _info, _time) -> None:
        if self.app is not None:
            data.set_text(self.app.id, -1)

    def _on_drag_motion(self, _widget, context, _x, _y, time) -> bool:
        Gdk.drag_status(context, Gdk.DragAction.MOVE, time)
        return True

    def _on_drag_data_received(self, _widget, context, _x, _y, data, _info, time) -> None:
        source_id = data.get_text()
        if not source_id or self.app is None:
            context.finish(False, False, time)
            return
        pinned = self.panel.shell.pinned
        if source_id not in pinned.ids or self.app.id not in pinned.ids:
            context.finish(False, False, time)
            return
        target_index = pinned.ids.index(self.app.id)
        pinned.move(source_id, target_index)
        context.finish(True, False, time)


class Panel(Gtk.Window):
    def __init__(self, shell, monitor: Gdk.Monitor, is_primary: bool = True) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.shell = shell
        self.monitor = monitor
        self.is_primary = is_primary
        self.set_title("FosOS Panel" if is_primary else "FosOS Panel (secondary)")
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.stick()
        add_classes(self, "fos-root", "fos-panel")

        Wnck.set_client_type(Wnck.ClientType.PAGER)
        self.screen = Wnck.Screen.get_default()
        self.screen.force_update()

        row = Gtk.Box(spacing=4)
        row.set_margin_start(8)
        row.set_margin_end(8)
        self.add(row)

        self.start_button = button(variant="ghost", size="icon", tooltip=BRAND["name"])
        self.start_icon = start_icon()
        self.start_button.add(self.start_icon)
        self.start_button.connect("clicked", lambda _b: self.shell.toggle_start(self))
        row.pack_start(self.start_button, False, False, 0)

        # Task View (Win+Tab) — two-pane glyph like Windows 11 Task View.
        self.task_view_button = button(variant="ghost", size="icon", tooltip="Task View")
        self.task_view_button.add(task_view_icon())
        self.task_view_button.set_no_show_all(True)
        self.task_view_button.connect("clicked", lambda _b: self.shell.toggle_task_view())
        row.pack_start(self.task_view_button, False, False, 0)
        row.pack_start(separator(), False, False, 4)

        self.tasks = Gtk.Box(spacing=2)
        row.pack_start(self.tasks, False, False, 0)

        row.pack_start(Gtk.Box(), True, True, 0)

        if is_primary and appmod.is_live():
            live = badge(BRAND["live_label"], "outline")
            live.set_margin_end(4)
            row.pack_start(live, False, False, 0)

        self.battery_button = None
        self.brightness_button = None
        self.volume_button = None
        self.network_button = None
        self.keyboard_button = None
        self.keyboard_label = None
        self.bell_button = None
        self.unread_dot = None
        self.tray_box = None
        self.tray_sep = None

        if is_primary:
            # Status Notifier tray (left of Quick Settings cluster).
            self.tray_box = Gtk.Box(spacing=2)
            self.tray_box.set_no_show_all(True)
            self.tray_box.hide()
            row.pack_start(self.tray_box, False, False, 0)
            self.tray_sep = separator()
            self.tray_sep.set_no_show_all(True)
            self.tray_sep.hide()
            row.pack_start(self.tray_sep, False, False, 4)

            # Status cluster: each icon opens its own flyout (Win+A still opens Quick Settings).
            if battery_present():
                self.battery_button = button(
                    icon_name="battery-good-symbolic", size="icon-sm", tooltip="Battery"
                )
                self.battery_button.connect(
                    "clicked", lambda b: self.shell.toggle_popup("battery", b)
                )
                row.pack_start(self.battery_button, False, False, 0)

            if brightness_available():
                self.brightness_button = button(
                    icon_name="display-brightness-symbolic", size="icon-sm", tooltip="Brightness"
                )
                self.brightness_button.connect(
                    "clicked", lambda b: self.shell.toggle_popup("brightness", b)
                )
                row.pack_start(self.brightness_button, False, False, 0)

            self.volume_button = button(
                icon_name="audio-volume-high-symbolic", size="icon-sm", tooltip="Sound"
            )
            self.volume_button.connect("clicked", lambda b: self.shell.toggle_popup("volume", b))
            row.pack_start(self.volume_button, False, False, 0)

            self.network_button = button(
                icon_name="network-wireless-symbolic", size="icon-sm", tooltip="Network & Bluetooth"
            )
            self.network_button.connect("clicked", lambda b: self.shell.toggle_popup("network", b))
            row.pack_start(self.network_button, False, False, 0)

            # Keyboard layout selector (code like US / PL), then bell + clock.
            self.keyboard_button = button(variant="ghost", tooltip="Keyboard layout")
            add_classes(self.keyboard_button, "fos-kbd-layout")
            self.keyboard_label = label("US", "fos-small", "fos-strong", xalign=0.5)
            self.keyboard_button.add(self.keyboard_label)
            self.keyboard_button.set_size_request(36, 36)
            self.keyboard_button.connect("clicked", self._on_keyboard_clicked)
            row.pack_start(self.keyboard_button, False, False, 0)
            self.refresh_keyboard()

            # Bell + clock → Notification Center (calendar + history, Win+N).
            open_nc = lambda b: self.shell.toggle_popup("clock", b)
            self.bell_overlay = Gtk.Overlay()
            self.bell_button = button(
                icon_name="preferences-system-notifications-symbolic",
                size="icon-sm",
                tooltip="Notifications",
            )
            self.bell_button.connect("clicked", open_nc)
            self.bell_overlay.add(self.bell_button)
            self.unread_dot = Gtk.Box()
            self.unread_dot.set_halign(Gtk.Align.END)
            self.unread_dot.set_valign(Gtk.Align.START)
            self.unread_dot.set_margin_top(4)
            self.unread_dot.set_margin_end(4)
            self.unread_dot.set_no_show_all(True)
            add_classes(self.unread_dot, "fos-dot")
            self.bell_overlay.add_overlay(self.unread_dot)
            self.bell_overlay.set_overlay_pass_through(self.unread_dot, True)
            row.pack_start(self.bell_overlay, False, False, 0)
            row.pack_start(separator(), False, False, 4)
        else:
            self.bell_overlay = None

        self.clock_button = button(variant="ghost", tooltip="Calendar & notifications")
        clock_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.clock_time = label("", "fos-small", "fos-strong", xalign=1.0)
        self.clock_date = label("", "fos-small", "fos-muted", xalign=1.0)
        clock_box.pack_start(self.clock_time, False, False, 0)
        clock_box.pack_start(self.clock_date, False, False, 0)
        clock_box.set_valign(Gtk.Align.CENTER)
        self.clock_button.add(clock_box)
        self.clock_button.set_size_request(-1, 36)
        self.clock_button.connect("clicked", lambda b: self.shell.toggle_popup("clock", b))
        row.pack_start(self.clock_button, False, False, 0)

        # Far-right Show Desktop strip (same action as Win+D).
        self.show_desktop_strip = Gtk.EventBox()
        self.show_desktop_strip.set_size_request(6, HEIGHT - 8)
        self.show_desktop_strip.set_valign(Gtk.Align.FILL)
        self.show_desktop_strip.set_tooltip_text("Show desktop")
        add_classes(self.show_desktop_strip, "fos-show-desktop")
        self.show_desktop_strip.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.show_desktop_strip.connect("button-press-event", self._on_show_desktop)
        row.pack_start(self.show_desktop_strip, False, False, 0)

        self.task_buttons: list[TaskButton] = []

        self.connect("realize", lambda _w: self.place())
        self.connect("button-press-event", self._on_panel_press)
        self.update_clock()
        GLib.timeout_add_seconds(5, self.update_clock)
        self.rebuild_tasks()
        self.apply_prefs()

    def apply_prefs(self) -> None:
        """Apply taskbar visibility prefs from Settings."""
        from .settings_pages import load_kv, truthy

        prefs = load_kv("taskbar", {"task_view": "1", "clock_date": "1", "bell": "1"})
        if truthy(prefs.get("task_view"), True):
            self.task_view_button.show()
        else:
            self.task_view_button.hide()
        if truthy(prefs.get("clock_date"), True):
            self.clock_date.show()
        else:
            self.clock_date.hide()
        if self.bell_overlay is not None:
            if truthy(prefs.get("bell"), True):
                self.bell_overlay.show()
            else:
                self.bell_overlay.hide()

    def rebuild_tray(self) -> None:
        """Refresh Status Notifier icons on the primary panel."""
        if self.tray_box is None:
            return
        from .tray import build_tray_button

        clear(self.tray_box)
        watcher = getattr(self.shell, "tray_watcher", None)
        items = list(watcher.items.values()) if watcher is not None else []
        if not items:
            self.tray_box.hide()
            if self.tray_sep is not None:
                self.tray_sep.hide()
            return
        for item in items:
            self.tray_box.pack_start(build_tray_button(item), False, False, 0)
        self.tray_box.show_all()
        if self.tray_sep is not None:
            self.tray_sep.show()

    # Geometry

    def area(self) -> Gdk.Rectangle:
        return self.monitor.get_geometry()

    def place(self) -> None:
        area = self.area()
        self.set_size_request(area.width, HEIGHT)
        self.resize(area.width, HEIGHT)
        self.move(area.x, area.y + area.height - HEIGHT)
        window = self.get_window()
        if window is not None:
            set_struts(window, area, HEIGHT)

    def popup_anchors(self) -> dict[str, Gtk.Widget]:
        anchors = {"clock": self.clock_button, "notifications": self.clock_button}
        if self.volume_button is not None:
            anchors["volume"] = self.volume_button
            anchors["quicksettings"] = self.volume_button
        if self.battery_button is not None:
            anchors["battery"] = self.battery_button
        if self.brightness_button is not None:
            anchors["brightness"] = self.brightness_button
        if self.network_button is not None:
            anchors["network"] = self.network_button
        if self.bell_button is not None:
            anchors["notifications"] = self.bell_button
        return anchors

    def top(self) -> int:
        area = self.area()
        return area.y + area.height - HEIGHT

    def anchor_x(self, widget: Gtk.Widget) -> int:
        window = widget.get_window()
        if window is None:
            return self.area().x
        _ok, origin_x, _origin_y = window.get_origin()
        alloc = widget.get_allocation()
        return origin_x + alloc.x

    # Workspaces (pager removed; Task View + shortcuts handle switching)

    def rebuild_workspaces(self) -> None:
        """Kept for shell hooks; numbered pager UI is gone."""
        self.refresh_workspaces()

    def refresh_workspaces(self) -> None:
        """Highlight Task View while the overview is open."""
        open_ = False
        task_view = getattr(self.shell, "task_view", None)
        if task_view is not None:
            open_ = bool(task_view.get_visible())
        set_class(self.task_view_button, "default", open_)
        set_class(self.task_view_button, "ghost", not open_)

    def _on_show_desktop(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button != 1:
            return False
        self.shell.close_popups()
        self.shell.toggle_show_desktop()
        return True

    def refresh_keyboard(self) -> None:
        if self.keyboard_label is None:
            return
        from .settings_pages import current_layout, layout_display_code

        code = current_layout()
        self.keyboard_label.set_text(layout_display_code(code))
        if self.keyboard_button is not None:
            self.keyboard_button.set_tooltip_text(f"Keyboard layout ({code})")

    def _on_keyboard_clicked(self, widget: Gtk.Button) -> None:
        from .settings_pages import current_layout, panel_layout_choices, persist_layout

        self.shell.close_popups()
        menu = Gtk.Menu()
        current = current_layout()
        group = None
        for code, name in panel_layout_choices():
            item = Gtk.RadioMenuItem.new_with_label(group, f"{name} ({code})")
            group = item.get_group()
            item.set_active(code == current)
            item.connect(
                "toggled",
                lambda i, c=code: self._set_keyboard_layout(c) if i.get_active() else None,
            )
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        settings = Gtk.MenuItem(label="Keyboard settings")
        settings.connect(
            "activate",
            lambda _i: appmod.spawn(["fosos-settings", "--builtin", "keyboard"]),
        )
        menu.append(settings)
        menu.show_all()
        menu.popup_at_widget(widget, Gdk.Gravity.NORTH_WEST, Gdk.Gravity.SOUTH_WEST, None)

    def _set_keyboard_layout(self, code: str) -> None:
        from .settings_pages import current_layout, persist_layout

        if code == current_layout():
            return
        if persist_layout(code):
            self.refresh_keyboard()

    def _on_panel_press(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button != 3:
            return False
        self._popup_taskbar_menu(event)
        return True

    def _popup_taskbar_menu(self, event: Gdk.EventButton) -> None:
        self.shell.close_popups()
        menu = Gtk.Menu()
        settings = Gtk.MenuItem(label="Taskbar settings")
        settings.connect(
            "activate",
            lambda _i: appmod.spawn(["fosos-settings", "--builtin", "taskbar"]),
        )
        menu.append(settings)
        show = Gtk.MenuItem(label="Show desktop")
        show.connect("activate", lambda _i: self.shell.toggle_show_desktop())
        menu.append(show)
        menu.show_all()
        menu.popup_at_pointer(event)

    # Windows and tasks

    def _on_this_monitor(self, window: Wnck.Window) -> bool:
        display = Gdk.Display.get_default()
        if display.get_n_monitors() <= 1:
            return True
        cx, cy = window_center(window)
        area = self.area()
        if point_in_rect(cx, cy, area):
            return True
        # Prefer the primary panel for windows whose centre falls outside every
        # panel (rare during moves) so they stay reachable.
        for index in range(display.get_n_monitors()):
            if point_in_rect(cx, cy, display.get_monitor(index).get_geometry()):
                return False
        return self.is_primary

    def _on_active_workspace(self, window: Wnck.Window) -> bool:
        if window.is_pinned():
            return True
        active = self.screen.get_active_workspace()
        workspace = window.get_workspace()
        if active is None or workspace is None:
            return True
        return workspace == active

    def windows(self) -> list[Wnck.Window]:
        result = []
        for window in self.screen.get_windows():
            if window.is_skip_tasklist() or window.get_window_type() in SKIP_TYPES:
                continue
            if not self._on_active_workspace(window):
                continue
            if not self._on_this_monitor(window):
                continue
            result.append(window)
        return result

    def all_session_windows(self) -> list[Wnck.Window]:
        """Windows to close on sign-out / power-off, across monitors and workspaces."""
        result = []
        for window in self.screen.get_windows():
            if window.is_skip_tasklist() or window.get_window_type() in SKIP_TYPES:
                continue
            result.append(window)
        return result

    def window_matches(self, window: Wnck.Window, app: appmod.App) -> bool:
        classes = app.window_classes()
        group = (window.get_class_group_name() or "").lower()
        instance = (window.get_class_instance_name() or "").lower()
        return group in classes or instance in classes

    def windows_for(self, app: appmod.App) -> list[Wnck.Window]:
        return [w for w in self.windows() if self.window_matches(w, app)]

    def active_window(self) -> Wnck.Window | None:
        return self.screen.get_active_window()

    def rebuild_tasks(self) -> None:
        for child in self.tasks.get_children():
            self.tasks.remove(child)
            child.destroy()
        self.task_buttons = []
        pinned = self.shell.pinned.apps()
        claimed = set()
        for app in pinned:
            task = TaskButton(self, app, None)
            self.task_buttons.append(task)
            for window in self.windows_for(app):
                claimed.add(window.get_xid())
        groups: dict[str, list[Wnck.Window]] = {}
        for window in self.windows():
            if window.get_xid() in claimed:
                continue
            key = (window.get_class_group_name() or window.get_name() or "").lower()
            groups.setdefault(key, []).append(window)
        for key, windows in groups.items():
            app = self._app_for_group(key)
            if app is not None:
                task = TaskButton(self, app, None)
            else:
                task = TaskButton(self, None, windows[0])
            self.task_buttons.append(task)
        for task in self.task_buttons:
            self.tasks.pack_start(task, False, False, 0)
        self.tasks.show_all()
        self.refresh_tasks()

    def _app_for_group(self, key: str) -> appmod.App | None:
        for app in self.shell.app_cache():
            if key and key in app.window_classes():
                return app
        return None

    def refresh_tasks(self) -> None:
        for task in self.task_buttons:
            task.refresh()

    # Status

    def update_clock(self) -> bool:
        now = GLib.DateTime.new_now_local()
        self.clock_time.set_text(now.format("%H:%M"))
        self.clock_date.set_text(now.format("%a, %b %-d"))
        return True

    def set_start_open(self, is_open: bool) -> None:
        set_class(self.start_button, "default", is_open)
        set_class(self.start_button, "ghost", not is_open)

    def set_unread(self, unread: bool) -> None:
        if self.unread_dot is not None:
            self.unread_dot.set_visible(unread)

    def set_volume_icon(self, name: str, tooltip: str) -> None:
        if self.volume_button is None:
            return
        self.volume_button.get_child().set_from_icon_name(name, Gtk.IconSize.MENU)
        self.volume_button.set_tooltip_text(tooltip)

    def set_network_icon(self, name: str, tooltip: str) -> None:
        if self.network_button is None:
            return
        self.network_button.get_child().set_from_icon_name(name, Gtk.IconSize.MENU)
        self.network_button.set_tooltip_text(tooltip)

    def set_battery_icon(self, name: str, tooltip: str) -> None:
        if self.battery_button is None:
            return
        self.battery_button.get_child().set_from_icon_name(name, Gtk.IconSize.MENU)
        self.battery_button.set_tooltip_text(tooltip)

    def set_brightness_icon(self, name: str, tooltip: str) -> None:
        if self.brightness_button is None:
            return
        self.brightness_button.get_child().set_from_icon_name(name, Gtk.IconSize.MENU)
        self.brightness_button.set_tooltip_text(tooltip)

    def apply_status(
        self,
        volume: tuple[str, str] | None,
        network: tuple[str, str],
        battery: tuple[str, str] | None,
        brightness: tuple[str, str] | None,
    ) -> None:
        if volume is not None:
            self.set_volume_icon(*volume)
        self.set_network_icon(*network)
        if battery is not None:
            self.set_battery_icon(*battery)
        if brightness is not None:
            self.set_brightness_icon(*brightness)
        self.refresh_keyboard()
