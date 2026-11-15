"""FosOS Files: mockup-style explorer with a real filesystem."""

from __future__ import annotations

import datetime
import shutil
import sys
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from . import apps as appmod
from .ui import add_classes, button, clear, icon, label, load_css, separator, set_class
from .windowchrome import CardWindow

APP_ID = "org.fosos.Files"


def special_dir(kind, fallback: str) -> Path:
    return appmod.user_dir(kind, fallback)


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
        self.selected: Path | None = None
        self._nav_busy = False

        self.quick_access = [
            ("Home", "user-home-symbolic", Path.home()),
            ("Desktop", "user-desktop-symbolic", special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP, "Desktop")),
            ("Documents", "folder-documents-symbolic", special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS, "Documents")),
            ("Downloads", "folder-download-symbolic", special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD, "Downloads")),
            ("Pictures", "folder-pictures-symbolic", special_dir(GLib.UserDirectory.DIRECTORY_PICTURES, "Pictures")),
            ("Music", "folder-music-symbolic", special_dir(GLib.UserDirectory.DIRECTORY_MUSIC, "Music")),
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
            self.nav_buttons[str(path.resolve())] = nav
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
        # Set the mode without refreshing: history is still empty here.
        self.view_mode = "list"
        set_class(self.grid_btn, "ghost", True)
        set_class(self.list_btn, "secondary", True)
        set_class(self.list_btn, "ghost", False)
        initial = start if start is not None else special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS, "Documents")
        if not initial.exists():
            initial = Path.home()
        self.navigate(initial, push=True)

    def current(self) -> Path | None:
        if not self.history or self.history_index < 0:
            return None
        return self.history[self.history_index]

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
        self.selected = None
        self.refresh()

    def go_back(self) -> None:
        if self.history_index > 0:
            self.history_index -= 1
            self.selected = None
            self.refresh()

    def go_forward(self) -> None:
        if self.history_index + 1 < len(self.history):
            self.history_index += 1
            self.selected = None
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
        self.set_badge(path.name if path != Path("/") else "FosOS")
        self._rebuild_breadcrumb(path)
        self._rebuild_listing(path)
        self._update_nav(path)
        self.back_btn.set_sensitive(self.history_index > 0)
        self.fwd_btn.set_sensitive(self.history_index + 1 < len(self.history))
        self.up_btn.set_sensitive(path != path.parent)
        count = len(self._entries(path))
        selected = f" · {self.selected.name}" if self.selected is not None else ""
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
        self.breadcrumb.pack_start(icon("user-home-symbolic", 14), False, False, 0)
        try:
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

    def _update_nav(self, path: Path) -> None:
        key = str(path.resolve())
        for nav_key, nav in self.nav_buttons.items():
            active = nav_key == key
            set_class(nav, "secondary", active)
            set_class(nav, "ghost", not active)

    def _rebuild_listing(self, path: Path) -> None:
        clear(self.listing)
        entries = self._entries(path)
        if not entries:
            self.listing.pack_start(
                label("This folder is empty." if not self.search.get_text() else "No matching items.", "fos-text", "fos-muted"),
                False,
                False,
                8,
            )
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
        selected = self.selected == path
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
        row.connect("button-press-event", self._on_item_press, path)
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
            tile_btn = button(variant="secondary" if self.selected == path else "outline")
            add_classes(tile_btn, "tile")
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            col.set_halign(Gtk.Align.CENTER)
            col.pack_start(icon(entry_icon(path), 28), False, False, 0)
            name = label(path.name, "fos-small", xalign=0.5, ellipsize=True)
            name.set_max_width_chars(12)
            col.pack_start(name, False, False, 0)
            tile_btn.add(col)
            tile_btn.connect("button-press-event", self._on_item_press, path)
            grid.attach(tile_btn, index % 4, index // 4, 1, 1)
        return grid

    def _on_item_press(self, _widget, event: Gdk.EventButton, path: Path) -> bool:
        if event.button != 1:
            if event.button == 3:
                self.selected = path
                # Defer rebuild so GTK is not destroying the clicked widget mid-handler.
                GLib.idle_add(self._select_and_menu, path, event)
            return False
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            GLib.idle_add(self.open_path, path)
            return True
        self.selected = path
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
        context = Gdk.Display.get_default().get_app_launch_context()
        try:
            Gio.AppInfo.launch_default_for_uri(path.as_uri(), context)
        except GLib.Error:
            pass

    def _popup_menu(self, path: Path, event: Gdk.EventButton) -> None:
        menu = Gtk.Menu()
        open_item = Gtk.MenuItem(label="Open")
        open_item.connect("activate", lambda _i: self.open_path(path))
        menu.append(open_item)
        current = self.current()
        if current is not None and path.parent == current:
            new_folder = Gtk.MenuItem(label="New folder")
            new_folder.connect("activate", lambda _i: self._new_folder())
            menu.append(new_folder)
            rename = Gtk.MenuItem(label="Rename")
            rename.connect("activate", lambda _i: self._rename(path))
            menu.append(rename)
            delete = Gtk.MenuItem(label="Delete")
            delete.connect("activate", lambda _i: self._delete(path))
            menu.append(delete)
        menu.show_all()
        menu.popup_at_pointer(event)

    def _new_folder(self) -> None:
        current = self.current()
        if current is None:
            return
        name = self._ask_text("New folder", "Folder name", "New folder")
        if not name:
            return
        target = current / name
        try:
            target.mkdir(exist_ok=False)
        except OSError:
            return
        self.refresh()

    def _rename(self, path: Path) -> None:
        current = self.current()
        name = self._ask_text("Rename", "New name", path.name)
        if not name or name == path.name:
            return
        target = path.with_name(name)
        try:
            path.rename(target)
        except OSError:
            return
        self.selected = target if current is not None and target.parent == current else None
        self.refresh()

    def _delete(self, path: Path) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=f"Delete “{path.name}”?",
        )
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError:
            return
        self.selected = None
        self.refresh()

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

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        key = Gdk.keyval_name(event.keyval) or ""
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        if key == "F5":
            self.refresh()
            return True
        if key == "BackSpace" and not ctrl:
            self.go_up()
            return True
        if key in ("Return", "KP_Enter") and self.selected is not None:
            self.open_path(self.selected)
            return True
        if key == "Delete" and self.selected is not None:
            self._delete(self.selected)
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
