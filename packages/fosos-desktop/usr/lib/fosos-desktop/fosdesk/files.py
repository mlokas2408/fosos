"""FosOS Files: mockup-style explorer with a real filesystem."""

from __future__ import annotations

import datetime
import os
import shutil
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from . import apps as appmod
from .ui import add_classes, button, clear, icon, label, load_css, separator, set_class
from .windowchrome import CardWindow

APP_ID = "org.fosos.Files"
URI_TARGET = [Gtk.TargetEntry.new("text/uri-list", 0, 0)]
TRASH_FILES = Path.home() / ".local/share/Trash/files"
TRASH_INFO = Path.home() / ".local/share/Trash/info"


def special_dir(kind, fallback: str) -> Path:
    return appmod.user_dir(kind, fallback)


def trash_dir() -> Path:
    TRASH_FILES.mkdir(parents=True, exist_ok=True)
    TRASH_INFO.mkdir(parents=True, exist_ok=True)
    return TRASH_FILES


def is_trash_path(path: Path) -> bool:
    try:
        return path.resolve() == trash_dir().resolve() or path.resolve().is_relative_to(trash_dir().resolve())
    except (OSError, ValueError, AttributeError):
        return False


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024**2:
        return f"{size / 1024:.0f} KB"
    if size < 1024**3:
        return f"{size / 1024**2:.1f} MB"
    return f"{size / 1024**3:.1f} GB"


def format_mtime(mtime: float) -> str:
    day = datetime.date.fromtimestamp(mtime)
    today = datetime.date.today()
    if day == today:
        return "Today"
    if day == today - datetime.timedelta(days=1):
        return "Yesterday"
    return day.strftime("%b %d").replace(" 0", " ")


def path_display(path: Path) -> str:
    try:
        if is_trash_path(path) and path.resolve() == trash_dir().resolve():
            return "Recycle Bin"
        home = Path.home()
        if path == home:
            return "Home"
        if path == Path("/"):
            return "FosOS"
        if path.is_relative_to(home):
            parts = ["FosOS", *path.relative_to(home).parts]
            return " \\ ".join(parts)
    except (OSError, ValueError, AttributeError):
        pass
    return str(path)


def entry_icon(path: Path) -> str:
    if path.is_dir():
        return "folder-symbolic"
    mime, _ = Gio.content_type_guess(str(path), None)
    if mime:
        themed = Gio.content_type_get_symbolic_icon(mime)
        if themed is not None:
            names = themed.get_names()
            if names:
                return names[0]
    return "text-x-generic-symbolic"


def unique_dest(directory: Path, name: str) -> Path:
    target = directory / name
    if not target.exists():
        return target
    stem = Path(name).stem
    suffix = Path(name).suffix
    index = 1
    while True:
        candidate = directory / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def path_size(path: Path) -> int:
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += (Path(root) / name).stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


class FilesWindow(CardWindow):
    def __init__(self, app: "FilesApp", start: Path | None = None) -> None:
        super().__init__(
            app,
            title="File Explorer",
            icon_name="folder-symbolic",
            default_width=980,
            default_height=640,
        )
        self.app = app
        self.history: list[Path] = []
        self.history_index = -1
        self.view_mode = "list"
        self.selected: set[Path] = set()
        self._anchor: Path | None = None
        self._nav_busy = False
        self._clipboard: list[Path] = []
        self._clipboard_cut = False
        self._entries_cache: list[Path] = []
        self._address_mode = False

        home = Path.home()
        downloads = special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD, "Downloads")
        self.quick_access = [
            ("Home", "user-home-symbolic", home),
            ("Desktop", "user-desktop-symbolic", special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP, "Desktop")),
            ("Documents", "folder-documents-symbolic", special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS, "Documents")),
            ("Downloads", "folder-download-symbolic", downloads),
            ("Pictures", "folder-pictures-symbolic", special_dir(GLib.UserDirectory.DIRECTORY_PICTURES, "Pictures")),
            ("Music", "folder-music-symbolic", special_dir(GLib.UserDirectory.DIRECTORY_MUSIC, "Music")),
            ("Recycle Bin", "user-trash-symbolic", trash_dir()),
            ("FosOS", "drive-harddisk-symbolic", Path("/")),
        ]

        toolbar = add_classes(Gtk.Box(spacing=4), "fos-app-toolbar")
        self.back_btn = button(icon_name="go-previous-symbolic", size="icon-xs", tooltip="Back", icon_size=14)
        self.fwd_btn = button(icon_name="go-next-symbolic", size="icon-xs", tooltip="Forward", icon_size=14)
        self.up_btn = button(icon_name="go-up-symbolic", size="icon-xs", tooltip="Up", icon_size=14)
        self.refresh_btn = button(icon_name="view-refresh-symbolic", size="icon-xs", tooltip="Refresh", icon_size=14)
        self.back_btn.connect("clicked", lambda _b: self.go_back())
        self.fwd_btn.connect("clicked", lambda _b: self.go_forward())
        self.up_btn.connect("clicked", lambda _b: self.go_up())
        self.refresh_btn.connect("clicked", lambda _b: self.refresh())
        for btn in (self.back_btn, self.fwd_btn, self.up_btn, self.refresh_btn):
            toolbar.pack_start(btn, False, False, 0)
        toolbar.pack_start(separator(length=22), False, False, 4)

        self.breadcrumb = add_classes(Gtk.Box(spacing=4), "fos-breadcrumb")
        self.breadcrumb.set_hexpand(True)
        toolbar.pack_start(self.breadcrumb, True, True, 0)

        self.address = add_classes(Gtk.Entry(), "fos-input")
        self.address.set_no_show_all(True)
        self.address.connect("activate", self._on_address_activate)
        self.address.connect("focus-out-event", lambda *_a: self._hide_address() or False)
        toolbar.pack_start(self.address, True, True, 0)

        self.search = add_classes(Gtk.Entry(), "fos-input")
        self.search.set_placeholder_text("Search")
        self.search.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "system-search-symbolic")
        self.search.set_width_chars(16)
        self.search.connect("changed", lambda _e: self.refresh())
        toolbar.pack_start(self.search, False, False, 0)
        toolbar.pack_start(separator(length=22), False, False, 4)

        self.grid_btn = button(icon_name="view-grid-symbolic", size="icon-xs", tooltip="Grid view", icon_size=14)
        self.list_btn = button(icon_name="view-list-symbolic", size="icon-xs", tooltip="List view", icon_size=14)
        self.grid_btn.connect("clicked", lambda _b: self.set_view_mode("grid"))
        self.list_btn.connect("clicked", lambda _b: self.set_view_mode("list"))
        toolbar.pack_start(self.grid_btn, False, False, 0)
        toolbar.pack_start(self.list_btn, False, False, 0)
        self.body.pack_start(toolbar, False, False, 0)

        content = Gtk.Box()
        content.set_hexpand(True)
        content.set_vexpand(True)
        self.body.pack_start(content, True, True, 0)

        sidebar = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2), "fos-files-sidebar")
        sidebar.set_size_request(176, -1)
        sidebar.set_border_width(8)
        sidebar.pack_start(label("QUICK ACCESS", "fos-small", "fos-muted"), False, False, 0)
        self.nav_buttons: dict[str, Gtk.Button] = {}
        for name, icon_name, path in self.quick_access:
            nav = button(name, icon_name=icon_name, variant="ghost", size="sm", icon_size=14)
            nav.get_child().set_halign(Gtk.Align.START)
            nav.connect("clicked", lambda _b, p=path: self.navigate(p, push=True))
            try:
                self.nav_buttons[str(path.resolve())] = nav
            except OSError:
                self.nav_buttons[str(path)] = nav
            sidebar.pack_start(nav, False, False, 0)
        content.pack_start(sidebar, False, False, 0)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.pack_start(main, True, True, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        self.listing = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0), "fos-files-listing")
        self.listing.set_border_width(12)
        self.listing.drag_dest_set(Gtk.DestDefaults.ALL, URI_TARGET, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        self.listing.connect("drag-data-received", self._on_drag_data_received)
        scroller.add(self.listing)
        main.pack_start(scroller, True, True, 0)

        self.footer = add_classes(Gtk.Box(spacing=12), "fos-app-footer")
        self.status_left = label("", "fos-small", "fos-muted")
        self.status_right = label("", "fos-small", "fos-muted", xalign=1.0)
        self.status_right.set_hexpand(True)
        self.footer.pack_start(self.status_left, False, False, 0)
        self.footer.pack_start(self.status_right, True, True, 0)
        self.body.pack_start(self.footer, False, False, 0)

        self.connect("key-press-event", self._on_key)
        self.view_mode = "list"
        set_class(self.grid_btn, "ghost", True)
        set_class(self.list_btn, "secondary", True)
        set_class(self.list_btn, "ghost", False)
        initial = start if start is not None else home
        if not initial.exists():
            initial = home
        self.navigate(initial, push=True)

    def current(self) -> Path | None:
        if not self.history or self.history_index < 0:
            return None
        return self.history[self.history_index]

    def primary_selected(self) -> Path | None:
        if not self.selected:
            return None
        if self._anchor is not None and self._anchor in self.selected:
            return self._anchor
        return next(iter(self.selected))

    def set_view_mode(self, mode: str) -> None:
        self.view_mode = mode
        set_class(self.grid_btn, "secondary", mode == "grid")
        set_class(self.grid_btn, "ghost", mode != "grid")
        set_class(self.list_btn, "secondary", mode == "list")
        set_class(self.list_btn, "ghost", mode != "list")
        self.refresh()

    def navigate(self, path: Path, push: bool = False) -> None:
        try:
            path = path.expanduser().resolve()
        except OSError:
            return
        if path == trash_dir().resolve():
            trash_dir()
        if not path.is_dir():
            return
        if push:
            self.history = self.history[: self.history_index + 1]
            self.history.append(path)
            self.history_index = len(self.history) - 1
        elif self.history_index >= 0:
            self.history[self.history_index] = path
        else:
            self.history = [path]
            self.history_index = 0
        self.selected = set()
        self._anchor = None
        self._hide_address()
        self.refresh()

    def go_back(self) -> None:
        if self.history_index > 0:
            self.history_index -= 1
            self.selected = set()
            self._anchor = None
            self.refresh()

    def go_forward(self) -> None:
        if self.history_index + 1 < len(self.history):
            self.history_index += 1
            self.selected = set()
            self._anchor = None
            self.refresh()

    def go_up(self) -> None:
        current = self.current()
        if current is None:
            return
        parent = current.parent
        if parent != current:
            self.navigate(parent, push=True)

    def refresh(self) -> None:
        path = self.current()
        if path is None:
            return
        badge = "Recycle Bin" if is_trash_path(path) and path.resolve() == trash_dir().resolve() else (path.name if path != Path("/") else "FosOS")
        self.set_badge(badge)
        if not self._address_mode:
            self._rebuild_breadcrumb(path)
        self._rebuild_listing(path)
        self._update_nav(path)
        self.back_btn.set_sensitive(self.history_index > 0)
        self.fwd_btn.set_sensitive(self.history_index + 1 < len(self.history))
        self.up_btn.set_sensitive(path != path.parent)
        count = len(self._entries_cache)
        nsel = len(self.selected)
        selected = f" · {nsel} selected" if nsel else ""
        self.status_left.set_text(f"{count} items{selected}")
        self.status_right.set_text(path_display(path))
        self.show_all()

    def _entries(self, path: Path) -> list[Path]:
        query = self.search.get_text().strip().lower()
        try:
            entries = [p for p in path.iterdir() if not p.name.startswith(".")]
        except OSError:
            return []
        if query:
            entries = [p for p in entries if query in p.name.lower()]
        entries.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
        return entries

    def _rebuild_breadcrumb(self, path: Path) -> None:
        clear(self.breadcrumb)
        self.breadcrumb.show()
        self.breadcrumb.pack_start(icon("user-home-symbolic", 14), False, False, 0)
        try:
            if path.resolve() == trash_dir().resolve():
                parts = [(trash_dir(), "Recycle Bin")]
            else:
                home = Path.home()
                if path == Path("/"):
                    parts = [(Path("/"), "FosOS")]
                elif path == home or path.is_relative_to(home):
                    parts = [(home, "FosOS")]
                    current = home
                    if path != home:
                        for part in path.relative_to(home).parts:
                            current = current / part
                            parts.append((current, part))
                else:
                    parts = [(Path("/"), "/")]
                    current = Path("/")
                    for part in path.parts[1:]:
                        current = current / part
                        parts.append((current, part))
        except (OSError, ValueError, AttributeError):
            parts = [(path, path.name or str(path))]

        for index, (target, name) in enumerate(parts):
            if index > 0:
                chev = label("›", "fos-small", "fos-muted", xalign=0.5)
                chev.set_margin_start(2)
                chev.set_margin_end(2)
                self.breadcrumb.pack_start(chev, False, False, 0)
            crumb = button(name, variant="ghost", size="sm")
            if index == len(parts) - 1:
                add_classes(crumb, "fos-strong")
            crumb.connect("clicked", lambda _b, p=target: self.navigate(p, push=True))
            self.breadcrumb.pack_start(crumb, False, False, 0)

    def _show_address(self) -> None:
        current = self.current()
        if current is None:
            return
        self._address_mode = True
        self.breadcrumb.hide()
        self.address.set_text(str(current))
        self.address.show()
        self.address.grab_focus()
        self.address.select_region(0, -1)

    def _hide_address(self) -> None:
        if not self._address_mode:
            return
        self._address_mode = False
        self.address.hide()
        self.breadcrumb.show()
        path = self.current()
        if path is not None:
            self._rebuild_breadcrumb(path)
            self.breadcrumb.show_all()

    def _on_address_activate(self, entry: Gtk.Entry) -> None:
        text = entry.get_text().strip()
        self._hide_address()
        if not text:
            return
        target = Path(text).expanduser()
        if target.is_dir():
            self.navigate(target, push=True)
        elif target.exists():
            self.navigate(target.parent, push=True)
            self.selected = {target.resolve()}
            self._anchor = target.resolve()
            self.refresh()

    def _update_nav(self, path: Path) -> None:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        for nav_key, nav in self.nav_buttons.items():
            active = nav_key == key
            set_class(nav, "secondary", active)
            set_class(nav, "ghost", not active)

    def _rebuild_listing(self, path: Path) -> None:
        clear(self.listing)
        entries = self._entries(path)
        self._entries_cache = entries
        # Drop selections that left the folder.
        self.selected = {p for p in self.selected if p in entries}
        if self._anchor is not None and self._anchor not in self.selected:
            self._anchor = next(iter(self.selected), None)
        if not entries:
            empty = "Recycle Bin is empty." if is_trash_path(path) else (
                "This folder is empty." if not self.search.get_text() else "No matching items."
            )
            self.listing.pack_start(label(empty, "fos-text", "fos-muted"), False, False, 8)
            return
        if self.view_mode == "list":
            self._build_list(entries)
        else:
            self._build_grid(entries)

    def _build_list(self, entries: list[Path]) -> None:
        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-files-table")
        header = add_classes(Gtk.Box(spacing=8), "fos-files-table-header")
        header.pack_start(label("Name", "fos-small", "fos-muted"), True, True, 0)
        modified = label("Modified", "fos-small", "fos-muted")
        modified.set_size_request(100, -1)
        size = label("Size", "fos-small", "fos-muted", xalign=1.0)
        size.set_size_request(72, -1)
        header.pack_start(modified, False, False, 0)
        header.pack_start(size, False, False, 0)
        frame.pack_start(header, False, False, 0)
        for entry in entries:
            frame.pack_start(self._list_row(entry), False, False, 0)
        self.listing.pack_start(frame, False, False, 0)

    def _list_row(self, path: Path) -> Gtk.Button:
        selected = path in self.selected
        row = button(variant="secondary" if selected else "ghost")
        add_classes(row, "fos-files-row")
        box = Gtk.Box(spacing=8)
        box.pack_start(icon(entry_icon(path), 14), False, False, 0)
        name = label(path.name, "fos-text", ellipsize=True)
        name.set_hexpand(True)
        box.pack_start(name, True, True, 0)
        try:
            st = path.stat()
            mtime = format_mtime(st.st_mtime)
            size_text = "" if path.is_dir() else format_size(st.st_size)
        except OSError:
            mtime, size_text = "—", "—"
        modified = label(mtime, "fos-small", "fos-muted")
        modified.set_size_request(100, -1)
        size = label(size_text or "—", "fos-small", "fos-muted", xalign=1.0)
        size.set_size_request(72, -1)
        box.pack_start(modified, False, False, 0)
        box.pack_start(size, False, False, 0)
        row.add(box)
        self._wire_item(row, path)
        return row

    def _build_grid(self, entries: list[Path]) -> None:
        folders = [p for p in entries if p.is_dir()]
        files = [p for p in entries if not p.is_dir()]
        if folders:
            self.listing.pack_start(label("Folders", "fos-label"), False, False, 0)
            self.listing.pack_start(self._grid_for(folders), False, False, 0)
        if folders and files:
            self.listing.pack_start(separator(vertical=False), False, False, 8)
        if files:
            self.listing.pack_start(label("Files", "fos-label"), False, False, 0)
            self.listing.pack_start(self._grid_for(files), False, False, 0)

    def _grid_for(self, entries: list[Path]) -> Gtk.Grid:
        grid = Gtk.Grid(column_spacing=8, row_spacing=8, column_homogeneous=True)
        for index, path in enumerate(entries):
            tile_btn = button(variant="secondary" if path in self.selected else "outline")
            add_classes(tile_btn, "tile")
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            col.set_halign(Gtk.Align.CENTER)
            col.pack_start(icon(entry_icon(path), 28), False, False, 0)
            name = label(path.name, "fos-small", xalign=0.5, ellipsize=True)
            name.set_max_width_chars(12)
            col.pack_start(name, False, False, 0)
            tile_btn.add(col)
            self._wire_item(tile_btn, path)
            grid.attach(tile_btn, index % 4, index // 4, 1, 1)
        return grid

    def _wire_item(self, widget: Gtk.Widget, path: Path) -> None:
        widget.connect("button-press-event", self._on_item_press, path)
        widget.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, URI_TARGET, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        widget.connect("drag-data-get", self._on_drag_data_get)
        if path.is_dir():
            widget.drag_dest_set(Gtk.DestDefaults.ALL, URI_TARGET, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
            widget.connect("drag-data-received", self._on_drag_data_received_folder, path)

    def _on_item_press(self, _widget, event: Gdk.EventButton, path: Path) -> bool:
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        if event.button == 3:
            if path not in self.selected:
                self.selected = {path}
                self._anchor = path
            GLib.idle_add(self._select_and_menu, path, event)
            return True
        if event.button != 1:
            return False
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            GLib.idle_add(self.open_path, path)
            return True
        if shift and self._anchor is not None and self._entries_cache:
            try:
                start = self._entries_cache.index(self._anchor)
                end = self._entries_cache.index(path)
            except ValueError:
                self.selected = {path}
                self._anchor = path
            else:
                lo, hi = sorted((start, end))
                self.selected = set(self._entries_cache[lo : hi + 1])
        elif ctrl:
            if path in self.selected:
                self.selected.remove(path)
            else:
                self.selected.add(path)
            self._anchor = path
        else:
            self.selected = {path}
            self._anchor = path
        GLib.idle_add(self.refresh)
        return True

    def _select_and_menu(self, path: Path, event: Gdk.EventButton) -> bool:
        self.refresh()
        self._popup_menu(path, event)
        return False

    def open_path(self, path: Path) -> None:
        if path.is_dir():
            self.navigate(path, push=True)
            return
        if path.suffix.lower() == ".deb":
            if not appmod.spawn(["fosos-install-package", str(path.resolve())]):
                self._alert("Could not open package installer", "fosos-install-package is missing.")
            return
        context = Gdk.Display.get_default().get_app_launch_context()
        try:
            Gio.AppInfo.launch_default_for_uri(path.as_uri(), context)
        except GLib.Error:
            pass

    def _popup_menu(self, path: Path, event: Gdk.EventButton) -> None:
        menu = Gtk.Menu()
        paths = list(self.selected) if self.selected else [path]
        in_trash = is_trash_path(path)
        current = self.current()

        open_label = "Install" if path.is_file() and path.suffix.lower() == ".deb" else "Open"
        if len(paths) == 1:
            open_item = Gtk.MenuItem(label=open_label)
            open_item.connect("activate", lambda _i: self.open_path(path))
            menu.append(open_item)
            if path.is_file():
                open_with = Gtk.MenuItem(label="Open with…")
                open_with.connect("activate", lambda _i: self._open_with(path))
                menu.append(open_with)

        menu.append(Gtk.SeparatorMenuItem())
        cut = Gtk.MenuItem(label="Cut")
        cut.connect("activate", lambda _i: self._clipboard_set(paths, cut=True))
        menu.append(cut)
        copy = Gtk.MenuItem(label="Copy")
        copy.connect("activate", lambda _i: self._clipboard_set(paths, cut=False))
        menu.append(copy)
        paste = Gtk.MenuItem(label="Paste")
        paste.set_sensitive(bool(self._clipboard) and current is not None and not in_trash)
        paste.connect("activate", lambda _i: self._paste())
        menu.append(paste)

        menu.append(Gtk.SeparatorMenuItem())
        if in_trash:
            restore = Gtk.MenuItem(label="Restore")
            restore.connect("activate", lambda _i: self._restore_paths(paths))
            menu.append(restore)
            delete = Gtk.MenuItem(label="Delete permanently")
            delete.connect("activate", lambda _i: self._delete_permanent(paths))
            menu.append(delete)
        else:
            if current is not None and all(p.parent == current for p in paths):
                rename = Gtk.MenuItem(label="Rename")
                rename.set_sensitive(len(paths) == 1)
                rename.connect("activate", lambda _i: self._rename(path))
                menu.append(rename)
            trash = Gtk.MenuItem(label="Move to Recycle Bin")
            trash.connect("activate", lambda _i: self._trash_paths(paths))
            menu.append(trash)

        menu.append(Gtk.SeparatorMenuItem())
        copy_path = Gtk.MenuItem(label="Copy path")
        copy_path.connect("activate", lambda _i: self._copy_path_text(paths))
        menu.append(copy_path)
        if len(paths) == 1:
            props = Gtk.MenuItem(label="Properties")
            props.connect("activate", lambda _i: self._properties(path))
            menu.append(props)

        if current is not None and not in_trash:
            menu.append(Gtk.SeparatorMenuItem())
            new_folder = Gtk.MenuItem(label="New folder")
            new_folder.connect("activate", lambda _i: self._new_folder())
            menu.append(new_folder)
            terminal = Gtk.MenuItem(label="Open Terminal here")
            terminal.connect("activate", lambda _i: self._open_terminal(path if path.is_dir() else current))
            menu.append(terminal)

        menu.show_all()
        menu.popup_at_pointer(event)

    # Clipboard / trash / transfer

    def _clipboard_set(self, paths: list[Path], cut: bool) -> None:
        self._clipboard = [p.resolve() for p in paths]
        self._clipboard_cut = cut
        self.status_left.set_text(f"{'Cut' if cut else 'Copied'} {len(paths)} item(s)")

    def _copy_path_text(self, paths: list[Path]) -> None:
        text = "\n".join(str(p) for p in paths)
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        clipboard.store()

    def _paste(self) -> None:
        current = self.current()
        if current is None or not self._clipboard:
            return
        if is_trash_path(current):
            return
        self._transfer(self._clipboard, current, move=self._clipboard_cut)
        if self._clipboard_cut:
            self._clipboard = []
            self._clipboard_cut = False

    def _trash_paths(self, paths: list[Path]) -> None:
        failed = []
        for path in paths:
            try:
                Gio.File.new_for_path(str(path)).trash(None)
            except GLib.Error:
                failed.append(path.name)
        self.selected = set()
        self._anchor = None
        self.refresh()
        if failed:
            self._alert("Could not trash some items", ", ".join(failed[:5]))

    def _delete_permanent(self, paths: list[Path]) -> None:
        if not self._confirm(f"Permanently delete {len(paths)} item(s)?"):
            return
        for path in paths:
            info = TRASH_INFO / f"{path.name}.trashinfo"
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
                if info.exists():
                    info.unlink()
            except OSError:
                pass
        self.selected = set()
        self._anchor = None
        self.refresh()

    def _restore_paths(self, paths: list[Path]) -> None:
        for path in paths:
            info = TRASH_INFO / f"{path.name}.trashinfo"
            dest = None
            if info.is_file():
                try:
                    for line in info.read_text(encoding="utf-8").splitlines():
                        if line.startswith("Path="):
                            dest = Path(line[5:])
                            break
                except OSError:
                    dest = None
            if dest is None:
                dest = Path.home() / path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest = unique_dest(dest.parent, dest.name)
            try:
                shutil.move(str(path), str(dest))
                if info.exists():
                    info.unlink()
            except OSError:
                pass
        self.selected = set()
        self._anchor = None
        self.refresh()

    def _transfer(self, sources: list[Path], dest_dir: Path, move: bool = False) -> None:
        sources = [p for p in sources if p.exists()]
        if not sources:
            return
        total = sum(path_size(p) for p in sources) or 1
        large = total > 8 * 1024 * 1024 or len(sources) > 3
        dialog = None
        bar = None
        if large:
            dialog = Gtk.Dialog(title="Copying…" if not move else "Moving…", transient_for=self, modal=True)
            box = dialog.get_content_area()
            box.set_border_width(16)
            box.pack_start(label("Working with files…", "fos-text"), False, False, 0)
            bar = Gtk.ProgressBar()
            bar.set_show_text(True)
            box.pack_start(bar, False, False, 8)
            dialog.show_all()
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)

        done = 0
        errors: list[str] = []
        for source in sources:
            target = unique_dest(dest_dir, source.name)
            try:
                if move:
                    shutil.move(str(source), str(target))
                elif source.is_dir():
                    shutil.copytree(source, target)
                else:
                    shutil.copy2(source, target)
            except OSError as exc:
                errors.append(f"{source.name}: {exc}")
            done += path_size(source) or 1
            if bar is not None:
                bar.set_fraction(min(1.0, done / total))
                bar.set_text(source.name)
                while Gtk.events_pending():
                    Gtk.main_iteration_do(False)
            time.sleep(0)  # yield

        if dialog is not None:
            dialog.destroy()
        self.refresh()
        if errors:
            self._alert("Some items could not be transferred", "\n".join(errors[:8]))

    def _on_drag_data_get(self, _widget, _context, data, _info, _time) -> None:
        paths = list(self.selected) if self.selected else []
        if not paths:
            return
        uris = [p.resolve().as_uri() for p in paths]
        data.set_uris(uris)

    def _on_drag_data_received(self, _widget, context, _x, _y, data, _info, time) -> None:
        current = self.current()
        if current is None or is_trash_path(current):
            context.finish(False, False, time)
            return
        self._receive_uris(data, current, context, time)

    def _on_drag_data_received_folder(self, _widget, context, _x, _y, data, _info, time, folder: Path) -> None:
        self._receive_uris(data, folder, context, time)

    def _receive_uris(self, data, dest: Path, context, time) -> None:
        uris = data.get_uris()
        if not uris:
            context.finish(False, False, time)
            return
        sources = []
        for uri in uris:
            try:
                sources.append(Path(GLib.filename_from_uri(uri)[0]))
            except (GLib.Error, TypeError, ValueError):
                continue
        move = context.get_selected_action() == Gdk.DragAction.MOVE
        self._transfer(sources, dest, move=move)
        context.finish(True, False, time)

    # Dialogs / actions

    def _new_folder(self) -> None:
        current = self.current()
        if current is None or is_trash_path(current):
            return
        name = self._ask_text("New folder", "Folder name", "New folder")
        if not name:
            return
        target = current / name
        try:
            target.mkdir(exist_ok=False)
        except OSError:
            self._alert("Could not create folder", name)
            return
        self.selected = {target}
        self._anchor = target
        self.refresh()

    def _rename(self, path: Path) -> None:
        name = self._ask_text("Rename", "New name", path.name)
        if not name or name == path.name:
            return
        target = path.with_name(name)
        try:
            path.rename(target)
        except OSError:
            self._alert("Could not rename", path.name)
            return
        self.selected = {target}
        self._anchor = target
        self.refresh()

    def _open_with(self, path: Path) -> None:
        mime, _ = Gio.content_type_guess(str(path), None)
        apps = list(Gio.AppInfo.get_all_for_type(mime)) if mime else []
        if not apps:
            self._alert("No apps available", f"Nothing is registered for {mime or 'this file'}.")
            return
        dialog = Gtk.Dialog(title="Open with", transient_for=self, modal=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Open", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_border_width(12)
        box.pack_start(label(f"Open “{path.name}” with:", "fos-text"), False, False, 0)
        store = Gtk.ListStore(str, object)
        for app in apps:
            store.append([app.get_display_name(), app])
        combo = Gtk.ComboBox.new_with_model(store)
        renderer = Gtk.CellRendererText()
        combo.pack_start(renderer, True)
        combo.add_attribute(renderer, "text", 0)
        combo.set_active(0)
        box.pack_start(combo, False, False, 8)
        dialog.show_all()
        response = dialog.run()
        active = combo.get_active_iter()
        dialog.destroy()
        if response != Gtk.ResponseType.OK or active is None:
            return
        app = store[active][1]
        try:
            app.launch([Gio.File.new_for_path(str(path))], None)
        except GLib.Error as exc:
            self._alert("Could not open", exc.message)

    def _properties(self, path: Path) -> None:
        try:
            st = path.stat()
        except OSError as exc:
            self._alert("Properties unavailable", str(exc))
            return
        mime, _ = Gio.content_type_guess(str(path), None)
        size = "—" if path.is_dir() else format_size(st.st_size)
        if path.is_dir():
            try:
                count = sum(1 for _ in path.iterdir())
                size = f"{count} items"
            except OSError:
                size = "Folder"
        modified = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
        mode = oct(st.st_mode & 0o777)
        rows = [
            ("Name", path.name),
            ("Type", "Folder" if path.is_dir() else (mime or "File")),
            ("Size", size),
            ("Modified", modified),
            ("Permissions", mode),
            ("Location", str(path.parent)),
        ]
        dialog = Gtk.Dialog(title="Properties", transient_for=self, modal=True)
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        box = dialog.get_content_area()
        box.set_border_width(16)
        grid = Gtk.Grid(column_spacing=16, row_spacing=8)
        for index, (key, value) in enumerate(rows):
            grid.attach(label(key, "fos-text", "fos-muted"), 0, index, 1, 1)
            val = label(value, "fos-text", ellipsize=True)
            val.set_selectable(True)
            val.set_max_width_chars(48)
            grid.attach(val, 1, index, 1, 1)
        box.pack_start(grid, False, False, 0)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def _open_terminal(self, path: Path) -> None:
        cwd = path if path.is_dir() else path.parent
        if not appmod.spawn(["fosos-terminal", str(cwd)]):
            appmod.spawn(["fosos-terminal"])

    def _ask_text(self, title: str, label_text: str, initial: str) -> str | None:
        dialog = Gtk.Dialog(title=title, transient_for=self, modal=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("OK", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_border_width(12)
        box.pack_start(label(label_text, "fos-text"), False, False, 0)
        entry = add_classes(Gtk.Entry(), "fos-input")
        entry.set_text(initial)
        entry.set_activates_default(True)
        box.pack_start(entry, False, False, 8)
        dialog.show_all()
        response = dialog.run()
        text = entry.get_text().strip()
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not text:
            return None
        return text

    def _confirm(self, text: str) -> bool:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=text,
        )
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.OK

    def _alert(self, title: str, body: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=title,
        )
        dialog.format_secondary_text(body)
        dialog.run()
        dialog.destroy()

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        key = Gdk.keyval_name(event.keyval) or ""
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        current = self.current()

        if key == "F5":
            self.refresh()
            return True
        if ctrl and key.lower() == "l":
            self._show_address()
            return True
        if key == "F2" and len(self.selected) == 1:
            self._rename(self.primary_selected())
            return True
        if key == "BackSpace" and not ctrl:
            self.go_up()
            return True
        if key in ("Return", "KP_Enter") and self.primary_selected() is not None:
            self.open_path(self.primary_selected())
            return True
        if key == "Delete" and self.selected:
            if current is not None and is_trash_path(current):
                self._delete_permanent(list(self.selected))
            elif shift:
                self._delete_permanent(list(self.selected))
            else:
                self._trash_paths(list(self.selected))
            return True
        if ctrl and key.lower() == "a" and self._entries_cache:
            self.selected = set(self._entries_cache)
            self.refresh()
            return True
        if ctrl and key.lower() == "c" and self.selected:
            self._clipboard_set(list(self.selected), cut=False)
            return True
        if ctrl and key.lower() == "x" and self.selected:
            self._clipboard_set(list(self.selected), cut=True)
            return True
        if ctrl and key.lower() == "v":
            self._paste()
            return True
        if (event.state & Gdk.ModifierType.MOD1_MASK) and key in ("Up", "KP_Up"):
            self.go_up()
            return True
        return False


class FilesApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN | Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window: FilesWindow | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_prgname("fosos-files")
        GLib.set_application_name("File Explorer")
        load_css()

    def do_activate(self) -> None:
        self._ensure_window(None)
        self.window.present()

    def do_open(self, files, _n_files, _hint) -> None:
        path = None
        if files:
            path = Path(files[0].get_path() or "")
            if path.is_file():
                path = path.parent
        self._ensure_window(path if path and path.exists() else None)
        self.window.present()

    def do_command_line(self, command_line):
        argv = command_line.get_arguments()[1:]
        path = None
        if argv:
            candidate = Path(argv[0]).expanduser()
            if candidate.exists():
                path = candidate if candidate.is_dir() else candidate.parent
        self._ensure_window(path)
        self.window.present()
        return 0

    def _ensure_window(self, path: Path | None) -> None:
        if self.window is None:
            self.window = FilesWindow(self, start=path)
            self.window.show_all()
        elif path is not None:
            self.window.navigate(path, push=True)


def main() -> int:
    return FilesApp().run(sys.argv)
