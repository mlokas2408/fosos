"""The Start menu: search, pinned apps, recent folders and power."""

import datetime
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango

from . import apps as appmod
from .popup import Popup
from .ui import BRAND, add_classes, badge, brand_title, button, clear, icon, kbd, label, mark, tile

WIDTH = 420


def relative_day(timestamp: float) -> str:
    day = datetime.date.fromtimestamp(timestamp)
    today = datetime.date.today()
    if day == today:
        return "Today"
    if day == today - datetime.timedelta(days=1):
        return "Yesterday"
    return day.strftime("%b %-d")


def folder_summary(path: Path) -> str:
    try:
        entries = [p for p in path.iterdir() if not p.name.startswith(".")]
    except OSError:
        return "Folder"
    if not entries:
        return "Empty folder"
    entries.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return " · ".join(p.name for p in entries[:3])


class StartMenu(Popup):
    def __init__(self, shell) -> None:
        super().__init__(width=WIDTH)
        self.shell = shell
        self.all_apps: list[appmod.App] = []

        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)

        header = add_classes(Gtk.Box(spacing=10), "fos-card-header")
        header.pack_start(mark("md", inverse=True), False, False, 0)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        titles.pack_start(brand_title(14), False, False, 0)
        titles.pack_start(label(BRAND["etymology"], "fos-text", "fos-muted"), False, False, 0)
        titles.set_valign(Gtk.Align.CENTER)
        header.pack_start(titles, True, True, 0)
        actions = Gtk.Box(spacing=6)
        actions.set_valign(Gtk.Align.START)
        actions.pack_start(badge(BRAND["tagline"], "secondary"), False, False, 0)
        actions.pack_start(kbd("Esc"), False, False, 0)
        header.pack_end(actions, False, False, 0)
        frame.pack_start(header, False, False, 0)

        content = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20), "fos-card-content")
        frame.pack_start(content, True, True, 0)

        self.search = add_classes(Gtk.Entry(), "fos-input")
        self.search.set_placeholder_text("Search FosOS")
        self.search.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "system-search-symbolic")
        self.search.connect("changed", self._on_search_changed)
        self.search.connect("activate", self._on_search_activate)
        self.focus_widget = self.search
        content.pack_start(self.search, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.stack.set_vhomogeneous(False)
        self.stack.set_interpolate_size(True)
        content.pack_start(self.stack, True, True, 0)

        self.home = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.stack.add_named(self.home, "home")
        self.results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.stack.add_named(self._scroller(self.results_box, 320), "results")
        self.all_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        all_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        all_header = Gtk.Box()
        all_header.pack_start(label("All apps", "fos-label"), True, True, 0)
        back = button("Back", variant="ghost", size="sm")
        back.connect("clicked", lambda _b: self.show_home())
        all_header.pack_end(back, False, False, 0)
        all_page.pack_start(all_header, False, False, 0)
        all_page.pack_start(self._scroller(self.all_box, 320), True, True, 0)
        self.stack.add_named(all_page, "all")

        footer = add_classes(Gtk.Box(spacing=4), "fos-card-footer")
        user = button(variant="ghost", size="sm")
        user_row = Gtk.Box(spacing=8)
        avatar = tile("avatar-default-symbolic", "avatar", size=12)
        user_row.pack_start(avatar, False, False, 0)
        user_row.pack_start(label(appmod.user_display_name()), False, False, 0)
        user.add(user_row)
        user.set_tooltip_text("Open your home folder")
        user.connect("clicked", lambda _b: self._open(Path.home()))
        footer.pack_start(user, False, False, 0)
        for icon_name, tooltip, handler in (
            ("system-shutdown-symbolic", "Power", self._on_power),
            ("system-log-out-symbolic", "Sign out", self._on_sign_out),
            ("preferences-system-symbolic", "Settings", self._on_settings),
        ):
            action = button(icon_name=icon_name, variant="outline", size="icon-sm", tooltip=tooltip)
            action.connect("clicked", handler)
            footer.pack_end(action, False, False, 0)
        frame.pack_start(footer, False, False, 0)

        self.confirm_revealer = Gtk.Revealer()
        self.confirm_revealer.set_transition_type(Gtk.RevealerTransitionType.NONE)
        self.confirm_box = add_classes(Gtk.Box(spacing=6), "fos-card-footer")
        self.confirm_revealer.add(self.confirm_box)
        frame.pack_start(self.confirm_revealer, False, False, 0)

    def _scroller(self, child: Gtk.Widget, height: int) -> Gtk.ScrolledWindow:
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(height)
        scroller.set_max_content_height(height)
        scroller.set_propagate_natural_height(True)
        scroller.add(child)
        return scroller

    # Opening

    def open(self, x: int, bottom: int, monitor: Gdk.Rectangle) -> None:
        self.all_apps = self.shell.app_cache(refresh=True)
        self.search.set_text("")
        self.confirm_revealer.set_reveal_child(False)
        self.show_home()
        self.show_at(x, bottom, monitor)

    def show_home(self) -> None:
        clear(self.home)
        pinned = self.shell.pinned.apps()

        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        head = Gtk.Box()
        head.pack_start(label("Pinned", "fos-label"), True, True, 0)
        count = "1 app" if len(pinned) == 1 else f"{len(pinned)} apps"
        head.pack_end(label(count, "fos-small", "fos-muted"), False, False, 0)
        all_button = button("All apps", variant="ghost", size="sm")
        all_button.connect("clicked", lambda _b: self.show_all_apps())
        head.pack_end(all_button, False, False, 6)
        section.pack_start(head, False, False, 0)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8, column_homogeneous=True)
        for index, app in enumerate(pinned):
            grid.attach(self._pinned_tile(app), index % 3, index // 3, 1, 1)
        section.pack_start(grid, False, False, 0)
        self.home.pack_start(section, False, False, 0)

        recommended = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        recommended.pack_start(label("Recommended", "fos-label"), False, False, 0)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for kind, fallback in (
            (GLib.UserDirectory.DIRECTORY_DOCUMENTS, "Documents"),
            (GLib.UserDirectory.DIRECTORY_DOWNLOAD, "Downloads"),
        ):
            path = appmod.user_dir(kind, fallback)
            if path.is_dir():
                rows.pack_start(self._folder_row(path), False, False, 0)
        if not rows.get_children():
            rows.pack_start(self._folder_row(Path.home()), False, False, 0)
        recommended.pack_start(rows, False, False, 0)
        self.home.pack_start(recommended, False, False, 0)

        self.home.show_all()
        self.stack.set_visible_child_name("home")
        self.relayout()

    def show_all_apps(self) -> None:
        clear(self.all_box)
        for app in self.all_apps:
            self.all_box.pack_start(self._app_row(app, pin_toggle=True), False, False, 0)
        self.all_box.show_all()
        self.stack.set_visible_child_name("all")
        self.relayout()

    # Rows and tiles

    def _pinned_tile(self, app: appmod.App) -> Gtk.Button:
        widget = button(variant="outline")
        add_classes(widget, "tile")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.pack_start(tile(app.icon_name(), "primary"), False, False, 0)
        name = label(app.name, "fos-small", "fos-strong", xalign=0.5, ellipsize=True)
        name.set_max_width_chars(12)
        box.pack_start(name, False, False, 0)
        widget.add(box)
        widget.set_tooltip_text(app.description or app.name)
        widget.connect("clicked", lambda _b: self._launch(app))
        return widget

    def _folder_row(self, path: Path) -> Gtk.Button:
        widget = button(variant="ghost")
        add_classes(widget, "row")
        row = Gtk.Box(spacing=12)
        row.pack_start(tile("folder-symbolic", "muted", small=True), False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        texts.set_valign(Gtk.Align.CENTER)
        texts.pack_start(label(path.name or str(path), "fos-text", "fos-strong", ellipsize=True), False, False, 0)
        texts.pack_start(label(folder_summary(path), "fos-small", "fos-muted", ellipsize=True), False, False, 0)
        row.pack_start(texts, True, True, 0)
        try:
            when = relative_day(path.stat().st_mtime)
        except OSError:
            when = ""
        row.pack_end(label(when, "fos-small", "fos-muted"), False, False, 0)
        widget.add(row)
        widget.connect("clicked", lambda _b: self._open(path))
        return widget

    def _app_row(self, app: appmod.App, pin_toggle: bool = False) -> Gtk.Widget:
        outer = Gtk.Box(spacing=4)
        widget = button(variant="ghost")
        add_classes(widget, "row")
        row = Gtk.Box(spacing=12)
        row.pack_start(tile(app.icon_name(), "muted", small=True), False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        texts.set_valign(Gtk.Align.CENTER)
        texts.pack_start(label(app.name, "fos-text", "fos-strong", ellipsize=True), False, False, 0)
        if app.description:
            desc = label(app.description, "fos-small", "fos-muted", ellipsize=True)
            desc.set_max_width_chars(40)
            texts.pack_start(desc, False, False, 0)
        row.pack_start(texts, True, True, 0)
        widget.add(row)
        widget.connect("clicked", lambda _b: self._launch(app))
        outer.pack_start(widget, True, True, 0)
        if pin_toggle:
            pinned = self.shell.pinned.contains(app.id)
            toggle = button("Unpin" if pinned else "Pin", variant="ghost", size="sm")
            toggle.set_valign(Gtk.Align.CENTER)
            toggle.connect("clicked", lambda _b: self._toggle_pin(app))
            outer.pack_end(toggle, False, False, 0)
        return outer

    # Search

    def _on_search_changed(self, entry: Gtk.Entry) -> None:
        query = entry.get_text()
        if not query.strip():
            self.stack.set_visible_child_name("home")
            self.relayout()
            return
        clear(self.results_box)
        results = appmod.search_apps(query, self.all_apps)[:12]
        if not results:
            empty = label(f"No apps match “{query.strip()}”.", "fos-text", "fos-muted")
            empty.set_line_wrap(True)
            empty.set_ellipsize(Pango.EllipsizeMode.NONE)
            self.results_box.pack_start(empty, False, False, 8)
        for app in results:
            self.results_box.pack_start(self._app_row(app), False, False, 0)
        self.results_box.show_all()
        self.stack.set_visible_child_name("results")
        self.relayout()

    def _on_search_activate(self, entry: Gtk.Entry) -> None:
        results = appmod.search_apps(entry.get_text(), self.all_apps)
        if results:
            self._launch(results[0])

    # Actions

    def _launch(self, app: appmod.App) -> None:
        self.dismiss()
        app.launch()

    def _open(self, path: Path) -> None:
        self.dismiss()
        appmod.open_path(path)

    def _toggle_pin(self, app: appmod.App) -> None:
        self.shell.pinned.toggle(app.id)
        self.show_all_apps()

    def _on_settings(self, _button) -> None:
        self.dismiss()
        self.shell.open_settings()

    def _confirm(self, text: str, actions: list[tuple[str, str, callable]]) -> None:
        clear(self.confirm_box)
        self.confirm_box.pack_start(label(text, "fos-text", "fos-strong"), True, True, 0)
        for title, variant, handler in actions:
            action = button(title, variant=variant, size="sm")
            action.connect("clicked", lambda _b, h=handler: h())
            self.confirm_box.pack_end(action, False, False, 0)
        self.confirm_box.show_all()
        self.confirm_revealer.set_reveal_child(True)
        self.confirm_revealer.show_all()
        self.relayout()

    def _cancel_confirm(self) -> None:
        self.confirm_revealer.set_reveal_child(False)
        self.relayout()

    def _on_sign_out(self, _button) -> None:
        self._confirm(
            "Sign out of FosOS Desktop?",
            [
                ("Sign out", "destructive", lambda: self._session("logout")),
                ("Cancel", "ghost", self._cancel_confirm),
            ],
        )

    def _on_power(self, _button) -> None:
        self._confirm(
            "Power",
            [
                ("Shut down", "destructive", lambda: self._session("poweroff")),
                ("Restart", "outline", lambda: self._session("reboot")),
                ("Suspend", "outline", lambda: self._session("suspend")),
            ],
        )

    def _session(self, action: str) -> None:
        self.dismiss()
        self.shell.end_session(action)
