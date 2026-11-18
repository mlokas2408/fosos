"""The Start menu: search, pinned apps, recommended and power."""

from __future__ import annotations

import datetime
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from . import apps as appmod
from .popup import Popup
from .settings import PANELS, panel_available
from .ui import BRAND, add_classes, badge, brand_title, button, clear, kbd, label, mark, set_class, tile

WIDTH = 420
HOME_SCROLL = 320


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


def path_icon(path: Path) -> str:
    if path.is_dir():
        return "folder-symbolic"
    mime, _ = Gio.content_type_guess(str(path), None)
    if mime and mime.startswith("image/"):
        return "image-x-generic-symbolic"
    if mime and mime.startswith("text/"):
        return "text-x-generic-symbolic"
    if mime and "pdf" in mime:
        return "application-x-pdf-symbolic"
    return "text-x-generic-symbolic"


def letter_key(name: str) -> str:
    if not name:
        return "#"
    char = name[0].upper()
    return char if char.isalpha() else "#"


class StartMenu(Popup):
    def __init__(self, shell) -> None:
        super().__init__(width=WIDTH)
        self.shell = shell
        self.all_apps: list[appmod.App] = []
        self._search_launch = None
        self._nav_items: list[tuple[Gtk.Widget, callable]] = []
        self._nav_index = -1
        self._home_scroller: Gtk.ScrolledWindow | None = None
        self._all_scroller: Gtk.ScrolledWindow | None = None

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
        self.search.set_placeholder_text("Type here to search")
        self.search.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "system-search-symbolic")
        self.search.connect("changed", self._on_search_changed)
        self.search.connect("activate", self._on_search_activate)
        self.search.connect("icon-press", self._on_search_icon)
        self.search.connect("key-press-event", self._on_search_key)
        self.focus_widget = self.search
        content.pack_start(self.search, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.stack.set_vhomogeneous(False)
        self.stack.set_interpolate_size(True)
        content.pack_start(self.stack, True, True, 0)

        home_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.home = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self._home_scroller = self._scroller(self.home, HOME_SCROLL)
        home_page.pack_start(self._home_scroller, True, True, 0)
        all_apps_row = Gtk.Box()
        all_apps_btn = button("All apps", variant="ghost", size="sm")
        all_apps_btn.connect("clicked", lambda _b: self.show_all_apps())
        all_apps_row.pack_end(all_apps_btn, False, False, 0)
        home_page.pack_start(all_apps_row, False, False, 0)
        self.stack.add_named(home_page, "home")

        self.results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.stack.add_named(self._scroller(self.results_box, HOME_SCROLL), "results")

        self.all_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        all_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        all_header = Gtk.Box()
        all_header.pack_start(label("All apps", "fos-label"), True, True, 0)
        back = button("Back", variant="ghost", size="sm")
        back.connect("clicked", lambda _b: self.show_home())
        all_header.pack_end(back, False, False, 0)
        all_page.pack_start(all_header, False, False, 0)
        self._all_scroller = self._scroller(self.all_box, HOME_SCROLL)
        all_page.pack_start(self._all_scroller, True, True, 0)
        self.stack.add_named(all_page, "all")

        footer = add_classes(Gtk.Box(spacing=4), "fos-card-footer")
        user = button(variant="ghost", size="sm")
        user_row = Gtk.Box(spacing=8)
        avatar = tile("avatar-default-symbolic", "avatar", size=12)
        user_row.pack_start(avatar, False, False, 0)
        user_row.pack_start(label(appmod.user_display_name()), False, False, 0)
        user.add(user_row)
        user.set_tooltip_text("Account: home, lock, sign out")
        user.connect("button-press-event", self._on_user_press)
        footer.pack_start(user, False, False, 0)
        power = button(
            icon_name="system-shutdown-symbolic",
            variant="outline",
            size="icon-sm",
            tooltip="Power",
        )
        power.connect("clicked", self._on_power)
        footer.pack_end(power, False, False, 0)
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

    def _scroll_to_top(self, scroller: Gtk.ScrolledWindow | None) -> None:
        if scroller is None:
            return
        adj = scroller.get_vadjustment()
        if adj is not None:
            adj.set_value(adj.get_lower())

    def _ensure_visible(self, widget: Gtk.Widget) -> None:
        page = self.stack.get_visible_child_name()
        scroller = None
        if page == "home":
            scroller = self._home_scroller
        elif page == "results":
            child = self.stack.get_visible_child()
            if isinstance(child, Gtk.ScrolledWindow):
                scroller = child
        elif page == "all":
            scroller = self._all_scroller
        if scroller is None:
            return
        child = scroller.get_child()
        adj = scroller.get_vadjustment()
        if child is None or adj is None:
            return
        coords = widget.translate_coordinates(child, 0, 0)
        if coords is None:
            return
        _x, y = coords
        alloc = widget.get_allocation()
        top = adj.get_value()
        bottom = top + adj.get_page_size()
        height = max(alloc.height, 1)
        if y < top:
            adj.set_value(y)
        elif y + height > bottom:
            adj.set_value(max(adj.get_lower(), y + height - adj.get_page_size()))

    # Opening

    def open(self, x: int, bottom: int, monitor: Gdk.Rectangle) -> None:
        self.all_apps = self.shell.app_cache(refresh=True)
        self.search.set_text("")
        self._update_clear_icon()
        self._search_launch = None
        self._clear_nav()
        self.confirm_revealer.set_reveal_child(False)
        self.show_home()
        self.show_at(x, bottom, monitor)

    def show_home(self) -> None:
        clear(self.home)
        self._clear_nav()
        pinned = self.shell.pinned.apps()

        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        head = Gtk.Box()
        head.pack_start(label("Pinned", "fos-label"), True, True, 0)
        count = "1 app" if len(pinned) == 1 else f"{len(pinned)} apps"
        head.pack_end(label(count, "fos-small", "fos-muted"), False, False, 0)
        section.pack_start(head, False, False, 0)

        if not pinned:
            section.pack_start(
                label("Pin apps from All apps", "fos-text", "fos-muted"),
                False,
                False,
                0,
            )
        else:
            grid = Gtk.Grid(column_spacing=8, row_spacing=8, column_homogeneous=True)
            for index, app in enumerate(pinned):
                tile_btn = self._pinned_tile(app)
                grid.attach(tile_btn, index % 3, index // 3, 1, 1)
                self._register_nav(tile_btn, lambda a=app: self._launch(a))
            section.pack_start(grid, False, False, 0)
        self.home.pack_start(section, False, False, 0)

        recommended = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        recommended.pack_start(label("Recommended", "fos-label"), False, False, 0)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        recent = appmod.recent_paths(6)
        if not recent:
            recent = [Path.home()]
        for path in recent:
            row = self._path_row(path)
            rows.pack_start(row, False, False, 0)
            self._register_nav(row, lambda p=path: self._open(p))
        recommended.pack_start(rows, False, False, 0)
        self.home.pack_start(recommended, False, False, 0)

        self.home.show_all()
        self._scroll_to_top(self._home_scroller)
        self.stack.set_visible_child_name("home")
        self.relayout()

    def show_all_apps(self) -> None:
        clear(self.all_box)
        self._clear_nav()
        current = None
        for app in self.all_apps:
            key = letter_key(app.name)
            if key != current:
                current = key
                header = label(current, "fos-label")
                header.set_margin_top(8 if self.all_box.get_children() else 0)
                header.set_margin_bottom(2)
                self.all_box.pack_start(header, False, False, 0)
            row = self._app_row(app, pin_toggle=True)
            self.all_box.pack_start(row, False, False, 0)
            launch_btn = row.get_children()[0]
            self._register_nav(launch_btn, lambda a=app: self._launch(a))
        self.all_box.show_all()
        self._scroll_to_top(self._all_scroller)
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
        widget.connect("button-press-event", lambda _w, e, a=app: self._pinned_press(a, e))
        return widget

    def _pinned_press(self, app: appmod.App, event: Gdk.EventButton) -> bool:
        if event.button != 3:
            return False
        menu = Gtk.Menu()
        unpin = Gtk.MenuItem(label="Unpin from Start")
        unpin.connect("activate", lambda _i: self._unpin_home(app))
        menu.append(unpin)
        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def _unpin_home(self, app: appmod.App) -> None:
        self.shell.pinned.unpin(app.id)
        self.show_home()

    def _path_row(self, path: Path) -> Gtk.Button:
        widget = button(variant="ghost")
        add_classes(widget, "row")
        row = Gtk.Box(spacing=12)
        row.pack_start(tile(path_icon(path), "muted", small=True), False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        texts.set_valign(Gtk.Align.CENTER)
        title = path.name or str(path)
        if path.is_dir():
            subtitle = folder_summary(path)
        elif path.parent == Path.home():
            subtitle = "Home"
        else:
            try:
                subtitle = str(path.parent.relative_to(Path.home()))
            except ValueError:
                subtitle = str(path.parent)
        texts.pack_start(label(title, "fos-text", "fos-strong", ellipsize=True), False, False, 0)
        texts.pack_start(label(subtitle, "fos-small", "fos-muted", ellipsize=True), False, False, 0)
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
        if not pin_toggle:
            return widget
        outer = Gtk.Box(spacing=4)
        outer.pack_start(widget, True, True, 0)
        pinned = self.shell.pinned.contains(app.id)
        toggle = button("Unpin" if pinned else "Pin", variant="ghost", size="sm")
        toggle.set_valign(Gtk.Align.CENTER)
        toggle.connect("clicked", lambda _b: self._toggle_pin(app))
        outer.pack_end(toggle, False, False, 0)
        return outer

    def _settings_row(self, title: str, desc: str, icon_name: str, action: dict) -> Gtk.Button:
        widget = button(variant="ghost")
        add_classes(widget, "row")
        row = Gtk.Box(spacing=12)
        row.pack_start(tile(icon_name, "muted", small=True), False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        texts.set_valign(Gtk.Align.CENTER)
        texts.pack_start(label(title, "fos-text", "fos-strong", ellipsize=True), False, False, 0)
        texts.pack_start(label(desc or "Settings", "fos-small", "fos-muted", ellipsize=True), False, False, 0)
        row.pack_start(texts, True, True, 0)
        badge_label = label("Settings", "fos-small", "fos-muted")
        row.pack_end(badge_label, False, False, 0)
        widget.add(row)
        widget.connect("clicked", lambda _b: self._open_settings(action))
        return widget

    def _section(self, title: str, children: list[Gtk.Widget]) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(label(title, "fos-label"), False, False, 0)
        for child in children:
            box.pack_start(child, False, False, 0)
        return box

    # Navigation

    def _clear_nav(self) -> None:
        for widget, _action in self._nav_items:
            set_class(widget, "fos-start-selected", False)
        self._nav_items = []
        self._nav_index = -1

    def _register_nav(self, widget: Gtk.Widget, action: callable) -> None:
        self._nav_items.append((widget, action))

    def _set_nav_index(self, index: int) -> None:
        if not self._nav_items:
            self._nav_index = -1
            return
        if self._nav_index >= 0 and self._nav_index < len(self._nav_items):
            set_class(self._nav_items[self._nav_index][0], "fos-start-selected", False)
        self._nav_index = max(-1, min(index, len(self._nav_items) - 1))
        if self._nav_index >= 0:
            widget, _action = self._nav_items[self._nav_index]
            set_class(widget, "fos-start-selected", True)
            self._ensure_visible(widget)

    def _move_nav(self, delta: int) -> bool:
        if not self._nav_items:
            return False
        if self._nav_index < 0:
            next_index = 0 if delta > 0 else len(self._nav_items) - 1
        else:
            next_index = self._nav_index + delta
            if next_index < 0:
                self._set_nav_index(-1)
                if self.focus_widget is not None:
                    self.focus_widget.grab_focus()
                return True
            if next_index >= len(self._nav_items):
                next_index = len(self._nav_items) - 1
        self._set_nav_index(next_index)
        return True

    def _activate_nav(self) -> bool:
        if 0 <= self._nav_index < len(self._nav_items):
            _widget, action = self._nav_items[self._nav_index]
            action()
            return True
        return False

    def _on_search_key(self, _entry: Gtk.Entry, event: Gdk.EventKey) -> bool:
        if event.keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            return self._move_nav(1)
        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            return self._move_nav(-1)
        return False

    def _on_key_press(self, _widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            if self.search.get_text().strip():
                self.search.set_text("")
                return True
            self.dismiss()
            return True
        if event.keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            return self._move_nav(1)
        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            return self._move_nav(-1)
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.search.has_focus():
                return False
            if self._activate_nav():
                return True
        return False

    # Search

    def _update_clear_icon(self) -> None:
        if self.search.get_text():
            self.search.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "edit-clear-symbolic")
        else:
            self.search.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, None)

    def _on_search_icon(self, _entry: Gtk.Entry, position: Gtk.EntryIconPosition, _event) -> None:
        if position == Gtk.EntryIconPosition.SECONDARY:
            self.search.set_text("")
            self.search.grab_focus()

    def _settings_matches(self, query: str) -> list[tuple]:
        query = query.strip().lower()
        matches = []
        for entry in PANELS:
            group, title, desc, icon_name, action = entry
            if not panel_available(action):
                continue
            hay = f"{group} {title} {desc}".lower()
            if query in hay:
                matches.append(entry)
        return matches[:6]

    def _on_search_changed(self, entry: Gtk.Entry) -> None:
        self._update_clear_icon()
        query = entry.get_text()
        if not query.strip():
            self._search_launch = None
            self.show_home()
            return
        clear(self.results_box)
        self._clear_nav()
        apps = appmod.search_apps(query, self.all_apps)[:8]
        settings = self._settings_matches(query)
        files = appmod.search_paths(query, limit=6)
        self._search_launch = None
        if apps:
            self._search_launch = ("app", apps[0])
        elif settings:
            self._search_launch = ("settings", settings[0][4])
        elif files:
            self._search_launch = ("path", files[0])

        if not apps and not settings and not files:
            empty = label(f"No results for “{query.strip()}”.", "fos-text", "fos-muted")
            empty.set_line_wrap(True)
            empty.set_ellipsize(Pango.EllipsizeMode.NONE)
            self.results_box.pack_start(empty, False, False, 8)
        else:
            if apps:
                app_rows = []
                for app in apps:
                    row = self._app_row(app)
                    app_rows.append(row)
                    self._register_nav(row, lambda a=app: self._launch(a))
                self.results_box.pack_start(self._section("Apps", app_rows), False, False, 0)
            if settings:
                rows = []
                for _group, title, desc, icon_name, action in settings:
                    row = self._settings_row(title, desc, icon_name, action)
                    rows.append(row)
                    self._register_nav(row, lambda a=action: self._open_settings(a))
                self.results_box.pack_start(self._section("Settings", rows), False, False, 0)
            if files:
                file_rows = []
                for path in files:
                    row = self._path_row(path)
                    file_rows.append(row)
                    self._register_nav(row, lambda p=path: self._open(p))
                self.results_box.pack_start(self._section("Files", file_rows), False, False, 0)
        self.results_box.show_all()
        self.stack.set_visible_child_name("results")
        if self._nav_items:
            self._set_nav_index(0)
        self.relayout()

    def _on_search_activate(self, _entry: Gtk.Entry) -> None:
        if self._activate_nav():
            return
        if self._search_launch is None:
            return
        kind, payload = self._search_launch
        if kind == "app":
            self._launch(payload)
        elif kind == "settings":
            self._open_settings(payload)
        elif kind == "path":
            self._open(payload)

    # Actions

    def _launch(self, app: appmod.App) -> None:
        self.dismiss()
        app.launch()

    def _open(self, path: Path) -> None:
        self.dismiss()
        appmod.open_path(path)

    def _open_settings(self, action: dict) -> None:
        self.dismiss()
        self.shell.open_settings_action(action)

    def _toggle_pin(self, app: appmod.App) -> None:
        self.shell.pinned.toggle(app.id)
        self.show_all_apps()

    def _on_user_press(self, _button, event: Gdk.EventButton) -> bool:
        if event.button not in (1, 3):
            return False
        # Keep Start open while the account menu steals the seat grab.
        self._hold_grab = True
        menu = Gtk.Menu()
        home = Gtk.MenuItem(label="Open home folder")
        home.connect("activate", lambda _i: self._open(Path.home()))
        menu.append(home)
        lock = Gtk.MenuItem(label="Lock")
        lock.connect("activate", lambda _i: self._on_lock(None))
        menu.append(lock)
        sign = Gtk.MenuItem(label="Sign out…")
        sign.connect("activate", lambda _i: self._on_sign_out(None))
        menu.append(sign)
        menu.connect("deactivate", lambda *_a: self._on_account_menu_closed())
        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def _on_account_menu_closed(self) -> None:
        self._hold_grab = False
        if self.get_visible():
            GLib.idle_add(self._grab)

    def _on_lock(self, _button) -> None:
        self.dismiss()
        self.shell.lock_screen()

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
        # Account Gtk.Menu can dismiss Start via grab-broken; fall back to
        # logging out directly so Sign out never silently no-ops.
        if not self.get_visible():
            self.shell.end_session("logout")
            return
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
                ("Lock", "ghost", lambda: self._session("lock")),
            ],
        )

    def _session(self, action: str) -> None:
        self.dismiss()
        self.shell.end_session(action)
