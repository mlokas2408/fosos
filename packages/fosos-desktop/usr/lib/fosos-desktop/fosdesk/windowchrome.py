"""Undecorated card window chrome matching the FosOS Desktop mockup."""

from __future__ import annotations

import subprocess

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk

from .ui import add_classes, badge, button, label, tile


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

        self.frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card", "fos-app-frame")
        self.add(self.frame)

        self.header = add_classes(Gtk.Box(spacing=6), "fos-app-header")
        self.header.set_size_request(-1, 40)

        self.header_icon = tile(icon_name, "primary", size=14, small=True)
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

        self.min_btn = button(icon_name="window-minimize-symbolic", size="icon-xs", tooltip="Minimize", icon_size=14)
        self.max_btn = button(icon_name="window-maximize-symbolic", size="icon-xs", tooltip="Maximize", icon_size=14)
        self.close_btn = button(icon_name="window-close-symbolic", size="icon-xs", tooltip="Close", icon_size=14)
        add_classes(self.close_btn, "close")
        self.min_btn.connect("clicked", lambda _b: self.iconify())
        self.max_btn.connect("clicked", lambda _b: self.toggle_maximize())
        self.max_btn.connect("button-press-event", self._on_max_press)
        self.close_btn.connect("clicked", lambda _b: self.close())
        for btn in (self.min_btn, self.max_btn, self.close_btn):
            self.header.pack_start(btn, False, False, 0)

        self.header.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.BUTTON1_MOTION_MASK
        )
        self.header.connect("button-press-event", self._on_header_press)
        self.frame.pack_start(self.header, False, False, 0)

        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.body.set_hexpand(True)
        self.body.set_vexpand(True)
        self.frame.pack_start(self.body, True, True, 0)

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
        close.connect("activate", lambda _i: self.close())
        menu.append(close)
        menu.show_all()
        menu.popup_at_pointer(event)

    def _on_max_press(self, _button, event: Gdk.EventButton) -> bool:
        if event.button == 3:
            self._open_snap_layouts()
            return True
        return False

    def _on_window_state(self, _window, event: Gdk.EventWindowState) -> bool:
        self._maximized = bool(event.new_window_state & Gdk.WindowState.MAXIMIZED)
        child = self.max_btn.get_child()
        if isinstance(child, Gtk.Image):
            name = "window-maximize-symbolic"
            # Prefer restore when maximized if the icon exists.
            theme = Gtk.IconTheme.get_default()
            if self._maximized and theme.has_icon("window-restore-symbolic"):
                name = "window-restore-symbolic"
            child.set_from_icon_name(name, Gtk.IconSize.MENU)
            child.set_pixel_size(14)
        self.max_btn.set_tooltip_text("Restore" if self._maximized else "Maximize")
        return False

    def _on_header_press(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button == 3:
            self._popup_title_menu(event)
            return True
        if event.button != 1:
            return False
        # Gtk.Button children consume their own presses; remaining header clicks drag.
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self.toggle_maximize()
            return True
        window = self.get_window()
        if window is not None:
            Gdk.Window.begin_move_drag(
                window,
                int(event.button),
                int(event.x_root),
                int(event.y_root),
                int(event.time),
            )
            return True
        return False
