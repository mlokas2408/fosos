"""The FosOS taskbar along the bottom of the primary monitor."""

import time

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gdk, GdkX11, GLib, Gtk, Wnck  # noqa: F401 (GdkX11 enables get_xid)

from . import apps as appmod
from .ui import BRAND, add_classes, badge, button, icon, label, separator, set_class, start_icon

HEIGHT = 48
SKIP_TYPES = (Wnck.WindowType.DESKTOP, Wnck.WindowType.DOCK, Wnck.WindowType.SPLASHSCREEN)


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
        self.button = button(variant="ghost", size="icon", tooltip=name)
        if icon_name:
            self.button.add(icon(icon_name, 16))
        else:
            # Prefer a monochrome symbolic icon over the app's coloured mini icon.
            self.button.add(icon("application-x-executable-symbolic", 16))
        self.button.connect("clicked", self._on_clicked)
        self.button.connect("button-release-event", self._on_release)
        self.indicator = Gtk.Box()
        self.indicator.set_halign(Gtk.Align.CENTER)
        add_classes(self.indicator, "fos-indicator")
        self.pack_start(self.button, False, False, 0)
        self.pack_start(self.indicator, False, False, 0)
        self.set_valign(Gtk.Align.CENTER)

    def windows(self) -> list[Wnck.Window]:
        if self.app is None:
            return [self.lone_window]
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
        self.indicator.set_size_request(16 if running else 0, 2)
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
        if active is not None and active in windows and not active.is_minimized():
            active.minimize()
            return
        stacked = [w for w in self.panel.screen.get_windows_stacked() if w in windows]
        target = stacked[-1] if stacked else windows[0]
        target.activate(stamp)

    def _on_release(self, _button, event: Gdk.EventButton) -> bool:
        if event.button == 2 and self.app is not None:
            self.app.launch()
            return True
        return False


class Panel(Gtk.Window):
    def __init__(self, shell) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.shell = shell
        self.set_title("FosOS Panel")
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
        self.start_button.connect("clicked", lambda _b: self.shell.toggle_start())
        row.pack_start(self.start_button, False, False, 0)
        row.pack_start(separator(), False, False, 4)

        self.tasks = Gtk.Box(spacing=2)
        row.pack_start(self.tasks, False, False, 0)

        row.pack_start(Gtk.Box(), True, True, 0)

        if appmod.is_live():
            live = badge(BRAND["live_label"], "outline")
            live.set_margin_end(4)
            row.pack_start(live, False, False, 0)

        self.volume_button = button(icon_name="audio-volume-high-symbolic", size="icon-sm", tooltip="Volume")
        self.volume_button.connect("clicked", lambda b: self.shell.toggle_popup("volume", b))
        row.pack_start(self.volume_button, False, False, 0)

        self.network_button = button(icon_name="network-wireless-symbolic", size="icon-sm", tooltip="Network")
        self.network_button.connect("clicked", lambda b: self.shell.toggle_popup("network", b))
        row.pack_start(self.network_button, False, False, 0)

        bell = Gtk.Overlay()
        self.bell_button = button(
            icon_name="preferences-system-notifications-symbolic", size="icon-sm", tooltip="Notifications"
        )
        self.bell_button.connect("clicked", lambda b: self.shell.toggle_popup("notifications", b))
        bell.add(self.bell_button)
        self.unread_dot = Gtk.Box()
        self.unread_dot.set_halign(Gtk.Align.END)
        self.unread_dot.set_valign(Gtk.Align.START)
        self.unread_dot.set_margin_top(4)
        self.unread_dot.set_margin_end(4)
        self.unread_dot.set_no_show_all(True)
        add_classes(self.unread_dot, "fos-dot")
        bell.add_overlay(self.unread_dot)
        bell.set_overlay_pass_through(self.unread_dot, True)
        row.pack_start(bell, False, False, 0)

        row.pack_start(separator(), False, False, 4)

        self.clock_button = button(variant="ghost", tooltip="Date & time")
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

        self.task_buttons: list[TaskButton] = []
        self.shell.pinned.listeners.append(self.rebuild_tasks)
        for signal in ("window-opened", "window-closed"):
            self.screen.connect(signal, self._on_screen_changed)
        for signal in ("active-window-changed", "window-stacking-changed"):
            self.screen.connect(signal, lambda *_a: self.refresh_tasks())
        self._watched = set()

        display_screen = Gdk.Screen.get_default()
        display_screen.connect("monitors-changed", lambda _s: self.place())
        display_screen.connect("size-changed", lambda _s: self.place())
        self.connect("realize", lambda _w: self.place())

        self.update_clock()
        GLib.timeout_add_seconds(5, self.update_clock)
        self.rebuild_tasks()

    # Geometry

    def area(self) -> Gdk.Rectangle:
        return primary_monitor()

    def place(self) -> None:
        area = self.area()
        self.set_size_request(area.width, HEIGHT)
        self.resize(area.width, HEIGHT)
        self.move(area.x, area.y + area.height - HEIGHT)
        window = self.get_window()
        if window is not None:
            set_struts(window, area, HEIGHT)

    def popup_anchors(self) -> dict[str, Gtk.Widget]:
        return {
            "volume": self.volume_button,
            "network": self.network_button,
            "notifications": self.bell_button,
            "clock": self.clock_button,
        }

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

    # Windows and tasks

    def windows(self) -> list[Wnck.Window]:
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

    def _on_screen_changed(self, *_args) -> None:
        for window in self.screen.get_windows():
            key = window.get_xid()
            if key not in self._watched:
                self._watched.add(key)
                window.connect("state-changed", lambda *_a: self.refresh_tasks())
                window.connect("name-changed", lambda *_a: self.refresh_tasks())
        self.rebuild_tasks()

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
        self.unread_dot.set_visible(unread)

    def set_volume_icon(self, name: str, tooltip: str) -> None:
        self.volume_button.get_child().set_from_icon_name(name, Gtk.IconSize.MENU)
        self.volume_button.set_tooltip_text(tooltip)

    def set_network_icon(self, name: str, tooltip: str) -> None:
        self.network_button.get_child().set_from_icon_name(name, Gtk.IconSize.MENU)
        self.network_button.set_tooltip_text(tooltip)
