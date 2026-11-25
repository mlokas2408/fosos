"""FosOS Files: Windows 11–style File Explorer with a real filesystem."""

from __future__ import annotations

import datetime
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk

from . import apps as appmod
from .onedrive import existing_sync_dir
from .ui import (
    FosDialog,
    add_classes,
    button,
    clear,
    fos_alert,
    fos_confirm,
    fos_prompt,
    full_icon,
    icon,
    label,
    load_css,
    separator,
    set_class,
)
from .windowchrome import CardWindow, caption_image

APP_ID = "org.fosos.Files"
URI_TARGET = [Gtk.TargetEntry.new("text/uri-list", 0, 0)]
TRASH_FILES = Path.home() / ".local/share/Trash/files"
TRASH_INFO = Path.home() / ".local/share/Trash/info"
STATE_DIR = Path.home() / ".local/share/fosos-desktop"
PINS_FILE = STATE_DIR / "files-pins.json"
RECENT_FILE = STATE_DIR / "files-recent.json"
OPTS_FILE = STATE_DIR / "files-options.json"

PAGE_THIS_PC = "this_pc"
PAGE_FOLDER = "folder"

SIDEBAR_WIDTH_DEFAULT = 240
SIDEBAR_WIDTH_MIN = 160
SIDEBAR_WIDTH_MAX = 480

VIEW_MODES = ("icons-xl", "icons-l", "icons-m", "icons-s", "list", "details", "tiles")
VIEW_LABELS = {
    "icons-xl": "Extra large icons",
    "icons-l": "Large icons",
    "icons-m": "Medium icons",
    "icons-s": "Small icons",
    "list": "List",
    "details": "Details",
    "tiles": "Tiles",
}
VIEW_ICON_PX = {
    "icons-xl": 96,
    "icons-l": 72,
    "icons-m": 48,
    "icons-s": 32,
    "list": 16,
    "details": 16,
    "tiles": 40,
}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".avif"}


def special_dir(kind, fallback: str) -> Path:
    return appmod.user_dir(kind, fallback)


def trash_dir() -> Path:
    TRASH_FILES.mkdir(parents=True, exist_ok=True)
    TRASH_INFO.mkdir(parents=True, exist_ok=True)
    return TRASH_FILES


def is_trash_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
        root = trash_dir().resolve()
        return resolved == root or resolved.is_relative_to(root)
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
            return "FosOS (C:)"
        if path.is_relative_to(home):
            parts = ["FosOS", *path.relative_to(home).parts]
            return " \\ ".join(parts)
    except (OSError, ValueError, AttributeError):
        pass
    return str(path)


def _icon_is_local(theme: Gtk.IconTheme, name: str, size: int = 16) -> bool:
    """True when the theme resolves `name` from FosOS (not Adwaita inheritance)."""
    info = theme.lookup_icon(name, size, 0)
    if info is None:
        return False
    return "/icons/FosOS/" in (info.get_filename() or "")


def _first_themed_icon(names: list[str], *, symbolic: bool) -> str | None:
    """Pick an existing icon, preferring FosOS glyphs over Adwaita plates."""
    theme = Gtk.IconTheme.get_default()
    ordered: list[str] = []
    for name in names:
        if not name:
            continue
        base = name[:-9] if name.endswith("-symbolic") else name
        # Always try the bare (often FosOS stroke) name before Adwaita -symbolic plates.
        ordered.extend((base, f"{base}-symbolic", name))
    seen: set[str] = set()
    fallback: str | None = None
    for candidate in ordered:
        if candidate in seen:
            continue
        seen.add(candidate)
        if not theme.has_icon(candidate):
            continue
        if _icon_is_local(theme, candidate):
            return candidate
        if fallback is None:
            fallback = candidate
    return fallback


def entry_icon(path: Path, *, symbolic: bool = True) -> str:
    if path.is_dir():
        picked = _first_themed_icon(["folder"], symbolic=symbolic)
        return picked or ("folder-symbolic" if symbolic else "folder")
    if path.suffix.lower() == ".desktop":
        try:
            info = Gio.DesktopAppInfo.new_from_filename(str(path))
        except GLib.Error:
            info = None
        if info is not None:
            gicon = info.get_icon()
            if isinstance(gicon, Gio.ThemedIcon):
                picked = _first_themed_icon(list(gicon.get_names() or []), symbolic=symbolic)
                if picked:
                    return picked
        return _first_themed_icon(["application-x-executable"], symbolic=symbolic) or (
            "application-x-executable-symbolic" if symbolic else "application-x-executable"
        )
    mime, _ = Gio.content_type_guess(str(path), None)
    if mime:
        # Prefer FosOS theme icons so MIME types do not
        # fall through to Adwaita "plate" artwork via a missing -symbolic name.
        themed = Gio.content_type_get_icon(mime)
        names: list[str] = []
        if themed is not None and isinstance(themed, Gio.ThemedIcon):
            names.extend(list(themed.get_names() or []))
        if symbolic:
            sym = Gio.content_type_get_symbolic_icon(mime)
            if sym is not None and isinstance(sym, Gio.ThemedIcon):
                names.extend(list(sym.get_names() or []))
        picked = _first_themed_icon(names, symbolic=symbolic)
        if picked:
            return picked
    return _first_themed_icon(["text-x-generic"], symbolic=symbolic) or (
        "text-x-generic-symbolic" if symbolic else "text-x-generic"
    )


def entry_name(path: Path) -> str:
    """Display name for listings (uses .desktop Name= when present)."""
    if path.suffix.lower() == ".desktop":
        try:
            info = Gio.DesktopAppInfo.new_from_filename(str(path))
        except GLib.Error:
            info = None
        if info is not None and info.get_name():
            return info.get_name()
        return path.stem
    return path.name


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


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def _save_json(path: Path, data) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def default_pins() -> list[dict]:
    home = Path.home()
    entries = [
        ("Desktop", "user-desktop-symbolic", special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP, "Desktop")),
        ("Documents", "folder-documents-symbolic", special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS, "Documents")),
        ("Downloads", "folder-download-symbolic", special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD, "Downloads")),
        ("Pictures", "folder-pictures-symbolic", special_dir(GLib.UserDirectory.DIRECTORY_PICTURES, "Pictures")),
        ("Music", "folder-music-symbolic", special_dir(GLib.UserDirectory.DIRECTORY_MUSIC, "Music")),
        ("Videos", "folder-videos-symbolic", special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS, "Videos")),
    ]
    return [{"name": n, "icon": i, "path": str(p)} for n, i, p in entries if p.exists() or True]


def load_pins() -> list[dict]:
    data = _load_json(PINS_FILE, None)
    if not isinstance(data, list) or not data:
        pins = default_pins()
        _save_json(PINS_FILE, pins)
        return pins
    return data


def save_pins(pins: list[dict]) -> None:
    _save_json(PINS_FILE, pins)


def load_recent(limit: int = 24) -> list[Path]:
    data = _load_json(RECENT_FILE, [])
    out: list[Path] = []
    if isinstance(data, list):
        for item in data:
            try:
                path = Path(str(item))
                if path.exists():
                    out.append(path.resolve())
            except OSError:
                continue
            if len(out) >= limit:
                break
    if len(out) < limit:
        for path in appmod.recent_paths(limit):
            if path not in out:
                out.append(path)
            if len(out) >= limit:
                break
    return out[:limit]


def push_recent(path: Path) -> None:
    try:
        path = path.resolve()
    except OSError:
        return
    items = [str(path)]
    for existing in load_recent(40):
        if existing != path:
            items.append(str(existing))
    _save_json(RECENT_FILE, items[:40])
    try:
        Gtk.RecentManager.get_default().add_item(path.as_uri())
    except GLib.Error:
        pass


def load_options() -> dict:
    data = _load_json(OPTS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    open_to = data.get("open_to", "this_pc")
    if open_to not in ("this_pc", "user"):
        open_to = "this_pc"
    try:
        sidebar_width = int(data.get("sidebar_width", SIDEBAR_WIDTH_DEFAULT))
    except (TypeError, ValueError):
        sidebar_width = SIDEBAR_WIDTH_DEFAULT
    sidebar_width = max(SIDEBAR_WIDTH_MIN, min(SIDEBAR_WIDTH_MAX, sidebar_width))
    return {
        "open_to": open_to,
        "show_hidden": bool(data.get("show_hidden", False)),
        "sidebar_width": sidebar_width,
    }


def save_options(opts: dict) -> None:
    _save_json(OPTS_FILE, opts)


def _mount_is_removable(mount) -> bool:
    try:
        volume = mount.get_volume()
        if volume is not None:
            drive = volume.get_drive()
            if drive is not None and drive.is_removable():
                return True
        drive = mount.get_drive()
        if drive is not None and drive.is_removable():
            return True
    except GLib.Error:
        pass
    return False


def list_drives() -> list[tuple[str, str, Path, str]]:
    """Return (name, icon, path, subtitle) for This PC — no Home folder."""
    rows: list[tuple[str, str, Path, str]] = []
    seen: set[str] = set()

    def add(name: str, icon_name: str, path: Path, subtitle: str = "") -> None:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key in seen or not path.exists():
            return
        seen.add(key)
        if not subtitle:
            try:
                usage = shutil.disk_usage(path)
                subtitle = f"{format_size(usage.used)} used of {format_size(usage.total)}"
            except OSError:
                subtitle = str(path)
        rows.append((name, icon_name, path, subtitle))

    add("FosOS (C:)", "drive-harddisk-symbolic", Path("/"))

    try:
        monitor = Gio.VolumeMonitor.get()
        for mount in monitor.get_mounts():
            root = mount.get_root()
            path_str = root.get_path() if root is not None else None
            if not path_str:
                continue
            path = Path(path_str)
            if path in (Path("/"), Path("/boot"), Path("/boot/efi"), Path("/home")):
                continue
            if path_str.startswith("/snap") or path_str.startswith("/run/user"):
                continue
            # Skip bind-style system mounts under /var, /usr, etc.
            if path_str in ("/var", "/usr", "/tmp", "/opt"):
                continue
            name = mount.get_name() or path.name or str(path)
            removable = _mount_is_removable(mount) or path_str.startswith("/media") or path_str.startswith("/run/media")
            icon_name = "drive-removable-media-symbolic" if removable else "drive-harddisk-symbolic"
            if removable and not name:
                name = path.name or "Removable Drive"
            add(name, icon_name, path)
    except GLib.Error:
        pass

    # Fallback: common removable / extra mount roots
    for candidate in (Path("/media"), Path("/mnt"), Path("/run/media")):
        if not candidate.is_dir():
            continue
        try:
            for child in candidate.iterdir():
                if not child.is_dir():
                    continue
                # /run/media/<user>/<label>
                if candidate == Path("/run/media"):
                    try:
                        for label in child.iterdir():
                            if label.is_dir():
                                add(label.name, "drive-removable-media-symbolic", label)
                    except OSError:
                        pass
                else:
                    add(child.name, "drive-removable-media-symbolic", child)
        except OSError:
            pass
    return rows


@dataclass
class Location:
    page: str
    path: Path | None = None

    def title(self) -> str:
        if self.page == PAGE_THIS_PC:
            return "This PC"
        if self.path is None:
            return "File Explorer"
        if is_trash_path(self.path) and self.path.resolve() == trash_dir().resolve():
            return "Recycle Bin"
        if self.path == Path("/"):
            return "FosOS (C:)"
        if self.path == Path.home():
            return "Home"
        return self.path.name or str(self.path)

    def folder_path(self) -> Path | None:
        if self.page == PAGE_FOLDER and self.path is not None:
            return self.path
        return None


def _build_tab_chip(
    title: str,
    *,
    on_focus: Callable[[], None],
    on_close: Callable[[], None],
) -> tuple[Gtk.Box, Gtk.Button, Gtk.Label]:
    chip = add_classes(Gtk.Box(spacing=0), "fos-files-tab-chip")
    focus_btn = button(variant="ghost", size="sm")
    add_classes(focus_btn, "fos-files-tab")
    tab_label = label(title, "fos-text", ellipsize=True)
    tab_label.set_width_chars(8)
    tab_label.set_max_width_chars(16)
    focus_btn.add(tab_label)
    focus_btn.set_can_focus(True)
    focus_btn.connect("clicked", lambda _b: on_focus())
    close = button(size="icon-xs", tooltip="Close tab")
    close.add(caption_image("close"))
    add_classes(close, "close", "fos-files-tab-close")
    close.connect("clicked", lambda _b: on_close())
    chip.pack_start(focus_btn, False, False, 0)
    chip.pack_start(close, False, False, 0)
    return chip, focus_btn, tab_label


class FilesTab:
    def __init__(self, window: "FilesWindow", start: Location) -> None:
        self.window = window
        self.history: list[Location] = [start]
        self.history_index = 0
        self.selected: set[Path] = set()
        self._anchor: Path | None = None
        self.view_mode = "details"
        self.sort_key = "name"
        self.sort_asc = True
        self.search_text = ""
        self.details_visible = False
        self._entries_cache: list[Path] = []
        self.tab_chip, self.tab_button, self.tab_label = _build_tab_chip(
            start.title(),
            on_focus=lambda: window.focus_tab(self),
            on_close=lambda: window.close_tab(self),
        )

    def location(self) -> Location:
        return self.history[self.history_index]

    def set_title(self) -> None:
        self.tab_label.set_text(self.location().title())


class FilesWindow(CardWindow):
    def __init__(self, app: "FilesApp", start: Path | None = None) -> None:
        super().__init__(
            app,
            title="File Explorer",
            icon_name="folder-symbolic",
            default_width=1100,
            default_height=700,
        )
        self.app = app
        self.tabs: list[FilesTab] = []
        self.active: FilesTab | None = None
        self._clipboard: list[Path] = []
        self._clipboard_cut = False
        self._address_mode = False
        self._nav_busy = False
        self._focus_region = 0
        self._item_widgets: dict[Path, Gtk.Widget] = {}
        self._click_path: Path | None = None
        self._click_time = 0
        # Set when a synthetic double-click already opened; skip the follow-up
        # _2BUTTON_PRESS so handlers (browser, Photos, …) are not launched twice.
        self._suppress_2button = False
        self.options = load_options()
        self.pins = load_pins()
        self._nav_buttons: dict[str, Gtk.Button] = {}
        self._view_btns: dict[str, Gtk.Button] = {}
        self._cmd: dict[str, Gtk.Button] = {}
        self._this_pc_expanded = True
        self._this_pc_children: Gtk.Box | None = None
        self._this_pc_chevron: Gtk.Button | None = None

        # Titlebar tabs
        self.tab_strip = add_classes(Gtk.Box(spacing=2), "fos-files-tabs")
        self.tab_strip.set_valign(Gtk.Align.CENTER)
        self.tab_strip.set_hexpand(True)
        self.add_tab_btn = button(icon_name="list-add-symbolic", size="icon-xs", tooltip="New tab", icon_size=14)
        self.add_tab_btn.connect("clicked", lambda _b: self.new_tab())
        self.set_header_center(self.tab_strip)

        # Nav row: Back Forward Up | breadcrumb/address | Search
        nav_row = add_classes(Gtk.Box(spacing=4), "fos-app-toolbar", "fos-files-navrow")
        self.back_btn = button(icon_name="go-previous-symbolic", size="icon-xs", tooltip="Back", icon_size=14)
        self.fwd_btn = button(icon_name="go-next-symbolic", size="icon-xs", tooltip="Forward", icon_size=14)
        self.up_btn = button(icon_name="go-up-symbolic", size="icon-xs", tooltip="Up", icon_size=14)
        self.back_btn.connect("clicked", lambda _b: self.go_back())
        self.fwd_btn.connect("clicked", lambda _b: self.go_forward())
        self.up_btn.connect("clicked", lambda _b: self.go_up())
        for btn in (self.back_btn, self.fwd_btn, self.up_btn):
            nav_row.pack_start(btn, False, False, 0)
        nav_row.pack_start(separator(length=22), False, False, 4)

        # One expand slot: breadcrumb XOR address (Gtk.Stack avoids dual-expand layout).
        self.location_stack = Gtk.Stack()
        self.location_stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.location_stack.set_hexpand(True)
        self.breadcrumb = add_classes(Gtk.Box(spacing=2), "fos-breadcrumb")
        self.breadcrumb.set_hexpand(True)
        self.crumb_hit = Gtk.EventBox()
        self.crumb_hit.set_visible_window(False)
        self.crumb_hit.add(self.breadcrumb)
        self.crumb_hit.connect("button-press-event", self._on_breadcrumb_press)
        self.location_stack.add_named(self.crumb_hit, "breadcrumb")

        self.address = add_classes(Gtk.Entry(), "fos-input")
        self.address.connect("activate", self._on_address_activate)
        self.address.connect("focus-out-event", lambda *_a: self._hide_address() or False)
        self.location_stack.add_named(self.address, "address")
        self.location_stack.set_visible_child_name("breadcrumb")
        nav_row.pack_start(self.location_stack, True, True, 0)

        self.search = add_classes(Gtk.Entry(), "fos-input")
        self.search.set_placeholder_text("Search")
        self.search.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "system-search-symbolic")
        self.search.set_width_chars(18)
        self.search.connect("changed", self._on_search_changed)
        self.search.connect("icon-press", self._on_search_icon)
        nav_row.pack_start(self.search, False, False, 0)
        self.body.pack_start(nav_row, False, False, 0)

        # Command bar
        cmd = add_classes(Gtk.Box(spacing=2), "fos-files-commandbar")
        self._cmd["new"] = button("New", icon_name="folder-new-symbolic", size="sm", icon_size=14, tooltip="New")
        self._cmd["cut"] = button(icon_name="edit-cut-symbolic", size="icon-xs", tooltip="Cut", icon_size=14)
        self._cmd["copy"] = button(icon_name="edit-copy-symbolic", size="icon-xs", tooltip="Copy", icon_size=14)
        self._cmd["paste"] = button(icon_name="edit-paste-symbolic", size="icon-xs", tooltip="Paste", icon_size=14)
        self._cmd["rename"] = button(icon_name="document-edit-symbolic", size="icon-xs", tooltip="Rename", icon_size=14)
        self._cmd["share"] = button(icon_name="edit-copy-symbolic", size="icon-xs", tooltip="Copy path", icon_size=14)
        self._cmd["delete"] = button(icon_name="user-trash-symbolic", size="icon-xs", tooltip="Delete", icon_size=14)
        self._cmd["sort"] = button("Sort", icon_name="view-sort-ascending-symbolic", size="sm", icon_size=14)
        self._cmd["view"] = button("View", icon_name="view-grid-symbolic", size="sm", icon_size=14)
        self._cmd["more"] = button(icon_name="view-more-symbolic", size="icon-xs", tooltip="See more", icon_size=14)
        self._cmd["details"] = button(icon_name="sidebar-show-symbolic", size="icon-xs", tooltip="Details pane", icon_size=14)

        self._cmd["new"].connect("clicked", lambda _b: self._popup_new_menu())
        self._cmd["cut"].connect("clicked", lambda _b: self._cmd_cut())
        self._cmd["copy"].connect("clicked", lambda _b: self._cmd_copy())
        self._cmd["paste"].connect("clicked", lambda _b: self._paste())
        self._cmd["rename"].connect("clicked", lambda _b: self._cmd_rename())
        self._cmd["share"].connect("clicked", lambda _b: self._cmd_share())
        self._cmd["delete"].connect("clicked", lambda _b: self._cmd_delete())
        self._cmd["sort"].connect("clicked", lambda _b: self._popup_sort_menu())
        self._cmd["view"].connect("clicked", lambda _b: self._popup_view_menu())
        self._cmd["more"].connect("clicked", lambda _b: self._popup_more_menu())
        self._cmd["details"].connect("clicked", lambda _b: self.toggle_details())

        for key in ("new", "cut", "copy", "paste", "rename", "share", "delete"):
            cmd.pack_start(self._cmd[key], False, False, 0)
        cmd.pack_start(separator(length=22), False, False, 6)
        cmd.pack_start(self._cmd["sort"], False, False, 0)
        cmd.pack_start(self._cmd["view"], False, False, 0)
        cmd.pack_end(self._cmd["details"], False, False, 0)
        cmd.pack_end(self._cmd["more"], False, False, 0)
        self.body.pack_start(cmd, False, False, 0)

        # Body: resizable sidenav | content (+ details)
        self.nav_paned = add_classes(
            Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL),
            "fos-files-paned",
        )
        self.nav_paned.set_wide_handle(True)
        self.nav_paned.set_hexpand(True)
        self.nav_paned.set_vexpand(True)
        self.body.pack_start(self.nav_paned, True, True, 0)

        self.sidebar = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2), "fos-files-sidebar")
        self.sidebar.set_vexpand(True)
        self.side_scroll = add_classes(Gtk.ScrolledWindow(), "fos-files-sidebar-scroll")
        self.side_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.side_scroll.set_size_request(SIDEBAR_WIDTH_MIN, -1)
        self.side_scroll.add(self.sidebar)
        self.nav_paned.pack1(self.side_scroll, False, False)
        self._rebuild_sidebar()

        right = Gtk.Box()
        right.set_hexpand(True)
        right.set_vexpand(True)
        self.nav_paned.pack2(right, True, False)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main.set_hexpand(True)
        main.set_vexpand(True)
        right.pack_start(main, True, True, 0)

        scroller = Gtk.ScrolledWindow()
        self.list_scroll = scroller
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        self.list_hit = Gtk.EventBox()
        self.list_hit.set_visible_window(True)
        self.list_hit.set_can_focus(True)
        add_classes(self.list_hit, "fos-files-hit")
        self.list_hit.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.list_hit.connect("button-press-event", self._on_list_bg_press)
        self.listing = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0), "fos-files-listing")
        self.listing.set_border_width(12)
        self.listing.set_valign(Gtk.Align.START)
        self.listing.drag_dest_set(Gtk.DestDefaults.ALL, URI_TARGET, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        self.listing.connect("drag-data-received", self._on_drag_data_received)
        self.list_hit.add(self.listing)
        scroller.add(self.list_hit)
        main.pack_start(scroller, True, True, 0)

        self.details_pane = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), "fos-files-details")
        self.details_pane.set_size_request(260, -1)
        self.details_pane.set_no_show_all(True)
        self.details_pane.set_can_focus(True)
        self.details_pane.set_border_width(12)
        right.pack_start(self.details_pane, False, False, 0)

        self._sidebar_width = int(self.options.get("sidebar_width", SIDEBAR_WIDTH_DEFAULT))
        self._sidebar_resize_save_id = 0
        self.nav_paned.connect("notify::position", self._on_sidebar_position)
        # Apply saved width after the paned has a real allocation.
        self.nav_paned.connect("realize", lambda *_a: GLib.idle_add(self._apply_sidebar_width))

        # Status bar
        self.footer = add_classes(Gtk.Box(spacing=8), "fos-app-footer", "fos-files-statusbar")
        self.status_left = label("", "fos-small", "fos-muted")
        self.status_left.set_hexpand(True)
        self.footer.pack_start(self.status_left, True, True, 0)
        view_cluster = add_classes(Gtk.Box(spacing=0), "fos-files-view-cluster")
        for mode, tip, glyph in (
            ("icons-xl", "Extra large icons", "view-grid-symbolic"),
            ("icons-l", "Large icons", "view-grid-symbolic"),
            ("icons-m", "Medium icons", "view-grid-symbolic"),
            ("icons-s", "Small icons", "view-grid-symbolic"),
            ("list", "List", "view-list-symbolic"),
            ("details", "Details", "view-list-symbolic"),
        ):
            btn = button(icon_name=glyph, size="icon-xs", tooltip=tip, icon_size=12)
            btn.connect("clicked", lambda _b, m=mode: self.set_view_mode(m))
            self._view_btns[mode] = btn
            view_cluster.pack_start(btn, False, False, 0)
        self.footer.pack_start(view_cluster, False, False, 0)
        self.body.pack_start(self.footer, False, False, 0)

        self.connect("key-press-event", self._on_key)

        initial = self._initial_location(start)
        self.new_tab(initial)

    # --- Tabs -----------------------------------------------------------------

    def _initial_location(self, start: Path | None) -> Location:
        if start is not None and start.exists():
            path = start if start.is_dir() else start.parent
            return Location(PAGE_FOLDER, path)
        if self.options.get("open_to") == "user":
            return Location(PAGE_FOLDER, Path.home())
        return Location(PAGE_THIS_PC)

    def new_tab(self, location: Location | None = None) -> FilesTab:
        loc = location or self._initial_location(None)
        tab = FilesTab(self, loc)
        self.tabs.append(tab)
        self._rebuild_tab_strip()
        self.focus_tab(tab)
        return tab

    def focus_tab(self, tab: FilesTab) -> None:
        if tab not in self.tabs:
            return
        self.active = tab
        for t in self.tabs:
            set_class(t.tab_chip, "secondary", t is tab)
            set_class(t.tab_button, "ghost", True)
        self.search.set_text(tab.search_text)
        self._address_mode = False
        self.refresh()

    def close_tab(self, tab: FilesTab) -> None:
        if tab not in self.tabs:
            return
        if len(self.tabs) == 1:
            self.close()
            return
        index = self.tabs.index(tab)
        self.tabs.remove(tab)
        tab.tab_chip.destroy()
        next_tab = self.tabs[min(index, len(self.tabs) - 1)]
        self._rebuild_tab_strip()
        self.focus_tab(next_tab)

    def _rebuild_tab_strip(self) -> None:
        clear(self.tab_strip)
        for tab in self.tabs:
            self.tab_strip.pack_start(tab.tab_chip, False, False, 0)
        self.tab_strip.pack_start(self.add_tab_btn, False, False, 0)
        self.tab_strip.show_all()

    # --- Navigation -----------------------------------------------------------

    def tab(self) -> FilesTab | None:
        return self.active

    def location(self) -> Location | None:
        return self.active.location() if self.active else None

    def current(self) -> Path | None:
        loc = self.location()
        return loc.folder_path() if loc else None

    def primary_selected(self) -> Path | None:
        tab = self.tab()
        if tab is None or not tab.selected:
            return None
        if tab._anchor is not None and tab._anchor in tab.selected:
            return tab._anchor
        return next(iter(tab.selected))

    def navigate_location(self, loc: Location, push: bool = False) -> None:
        tab = self.tab()
        if tab is None:
            return
        if loc.page == PAGE_FOLDER and loc.path is not None:
            try:
                path = loc.path.expanduser().resolve()
            except OSError:
                return
            if path == trash_dir().resolve():
                trash_dir()
            if not path.is_dir():
                return
            loc = Location(PAGE_FOLDER, path)
            push_recent(path)
        if push:
            tab.history = tab.history[: tab.history_index + 1]
            tab.history.append(loc)
            tab.history_index = len(tab.history) - 1
        elif tab.history_index >= 0:
            tab.history[tab.history_index] = loc
        else:
            tab.history = [loc]
            tab.history_index = 0
        tab.selected = set()
        tab._anchor = None
        self._hide_address()
        self.refresh()

    def navigate(self, path: Path, push: bool = False) -> None:
        self.navigate_location(Location(PAGE_FOLDER, path), push=push)

    def select_items(self, paths: list[Path]) -> None:
        """Highlight files in the current folder (browser “show in folder”)."""
        tab = self.tab()
        if tab is None or not paths:
            return
        if tab.search_text:
            tab.search_text = ""
            self.search.set_text("")
            self.refresh()
            tab = self.tab()
            if tab is None:
                return
        wanted: set[Path] = set()
        for path in paths:
            try:
                wanted.add(path.resolve())
            except OSError:
                wanted.add(path)
        matched: list[Path] = []
        for entry in tab._entries_cache:
            try:
                key = entry.resolve()
            except OSError:
                key = entry
            if key in wanted:
                matched.append(entry)
        if not matched:
            return
        tab.selected = set(matched)
        tab._anchor = matched[0]
        self._apply_selection_ui()
        GLib.idle_add(self._scroll_to_path, matched[0])

    def _scroll_to_path(self, path: Path, tries: int = 0) -> bool:
        widget = self._item_widgets.get(path)
        scroller = getattr(self, "list_scroll", None)
        if widget is None or scroller is None:
            return False
        if widget.get_allocation().height <= 1 and tries < 6:
            GLib.timeout_add(50, self._scroll_to_path, path, tries + 1)
            return False
        origin = widget.translate_coordinates(self.list_hit, 0, 0)
        if origin is None:
            return False
        adj = scroller.get_vadjustment()
        y = origin[1]
        page = adj.get_page_size()
        if y < adj.get_value() or y + widget.get_allocation().height > adj.get_value() + page:
            adj.set_value(max(0, min(max(0, adj.get_upper() - page), y - 48)))
        return False

    def go_back(self) -> None:
        tab = self.tab()
        if tab is None or tab.history_index <= 0:
            return
        tab.history_index -= 1
        tab.selected = set()
        tab._anchor = None
        self.refresh()

    def go_forward(self) -> None:
        tab = self.tab()
        if tab is None or tab.history_index + 1 >= len(tab.history):
            return
        tab.history_index += 1
        tab.selected = set()
        tab._anchor = None
        self.refresh()

    def go_up(self) -> None:
        loc = self.location()
        if loc is None:
            return
        if loc.page != PAGE_FOLDER or loc.path is None:
            return
        parent = loc.path.parent
        if parent != loc.path:
            self.navigate(parent, push=True)

    def set_view_mode(self, mode: str) -> None:
        tab = self.tab()
        if tab is None or mode not in VIEW_MODES:
            return
        tab.view_mode = mode
        self.refresh()

    def toggle_details(self) -> None:
        tab = self.tab()
        if tab is None:
            return
        tab.details_visible = not tab.details_visible
        self.refresh()

    # --- Search / address -----------------------------------------------------

    def _on_search_changed(self, _entry: Gtk.Entry) -> None:
        tab = self.tab()
        if tab is None:
            return
        tab.search_text = self.search.get_text()
        if tab.search_text:
            self.search.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "edit-clear-symbolic")
        else:
            self.search.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, None)
        self.refresh(keep_search_focus=True)

    def _on_search_icon(self, _entry: Gtk.Entry, position: Gtk.EntryIconPosition, _event) -> None:
        if position == Gtk.EntryIconPosition.SECONDARY:
            self.clear_search()

    def clear_search(self) -> None:
        if self.search.get_text():
            self.search.set_text("")
        else:
            self.refresh(keep_search_focus=True)

    def focus_search(self) -> None:
        self.search.grab_focus()
        self.search.select_region(0, -1)

    def _on_breadcrumb_press(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button == 1 and event.type == Gdk.EventType._2BUTTON_PRESS:
            self._show_address()
            return True
        return False

    def _show_address(self) -> None:
        loc = self.location()
        if loc is None:
            return
        self._address_mode = True
        text = str(loc.path) if loc.page == PAGE_FOLDER and loc.path else loc.title()
        self.address.set_text(text)
        self.location_stack.set_visible_child_name("address")
        self.address.grab_focus()
        self.address.select_region(0, -1)

    def _hide_address(self) -> None:
        if not self._address_mode:
            return
        self._address_mode = False
        self.location_stack.set_visible_child_name("breadcrumb")
        loc = self.location()
        if loc is not None:
            self._rebuild_breadcrumb(loc)
            self.breadcrumb.show_all()

    def _on_address_activate(self, entry: Gtk.Entry) -> None:
        text = entry.get_text().strip()
        self._hide_address()
        if not text:
            return
        lower = text.lower()
        if lower in ("this pc", "thispc"):
            self.navigate_location(Location(PAGE_THIS_PC), push=True)
            return
        if lower in ("home", "~"):
            self.navigate(Path.home(), push=True)
            return
        target = Path(text).expanduser()
        if target.is_dir():
            self.navigate(target, push=True)
        elif target.exists():
            self.navigate(target.parent, push=True)
            tab = self.tab()
            if tab is not None:
                tab.selected = {target.resolve()}
                tab._anchor = target.resolve()
                self.refresh()

    # --- Sidebar --------------------------------------------------------------

    def _rebuild_sidebar(self) -> None:
        clear(self.sidebar)
        self._nav_buttons = {}
        self._this_pc_children = None
        self._this_pc_chevron = None

        def section(title: str) -> None:
            self.sidebar.pack_start(label(title, "fos-small", "fos-muted", "fos-files-nav-section"), False, False, 4)

        def nav_row(
            name: str,
            icon_name: str,
            key: str,
            callback,
            *,
            pack_into: Gtk.Box | None = None,
            chevron_btn: Gtk.Button | None = None,
            indent: bool = False,
        ) -> Gtk.Button:
            """One nav line: fixed chevron gutter + full-width button (icons align)."""
            row = add_classes(Gtk.Box(spacing=0), "fos-files-nav-tree-row")
            if indent:
                add_classes(row, "fos-files-nav-child-row")
            if chevron_btn is not None:
                row.pack_start(chevron_btn, False, False, 0)
            else:
                gutter = Gtk.Box()
                add_classes(gutter, "fos-files-nav-gutter")
                gutter.set_size_request(22, 28)
                row.pack_start(gutter, False, False, 0)
            nav = button(name, icon_name=icon_name, variant="ghost", size="sm", icon_size=14)
            add_classes(nav, "fos-files-nav-item")
            nav.set_can_focus(True)
            child = nav.get_child()
            if child is not None:
                child.set_halign(Gtk.Align.START)
            nav.connect("clicked", lambda _b: callback())
            self._nav_buttons[key] = nav
            row.pack_start(nav, True, True, 0)
            parent = pack_into if pack_into is not None else self.sidebar
            parent.pack_start(row, False, False, 0)
            return nav

        # Home sits above Quick access (user profile folder, not under This PC).
        try:
            home_key = f"home:{Path.home().resolve()}"
        except OSError:
            home_key = f"home:{Path.home()}"
        nav_row("Home", "user-home-symbolic", home_key, lambda: self.navigate(Path.home(), push=True))

        cloud = existing_sync_dir()
        if cloud is not None:
            try:
                cloud_key = f"onedrive:{cloud.resolve()}"
            except OSError:
                cloud_key = f"onedrive:{cloud}"
            nav_row(
                "OneDrive",
                "folder-remote-symbolic",
                cloud_key,
                lambda p=cloud: self.navigate(p, push=True),
            )

        section("Quick access")
        for pin in self.pins:
            path = Path(pin.get("path", ""))
            name = pin.get("name") or path.name or str(path)
            icon_name = pin.get("icon") or "folder-symbolic"
            try:
                key = f"pin:{path.resolve()}"
            except OSError:
                key = f"pin:{path}"
            nav_row(name, icon_name, key, lambda p=path: self.navigate(p, push=True))

        # Horizontal rule between Quick access and This PC.
        rule = separator(vertical=False)
        add_classes(rule, "fos-files-nav-sep")
        rule.set_margin_top(8)
        rule.set_margin_bottom(8)
        rule.set_margin_start(10)
        rule.set_margin_end(10)
        self.sidebar.pack_start(rule, False, False, 0)

        chevron = button(
            icon_name="pan-down-symbolic" if self._this_pc_expanded else "pan-end-symbolic",
            size="icon-xs",
            tooltip="Collapse This PC" if self._this_pc_expanded else "Expand This PC",
            icon_size=12,
        )
        add_classes(chevron, "fos-files-nav-chevron")
        chevron.connect("clicked", lambda _b: self._toggle_this_pc_tree())
        self._this_pc_chevron = chevron
        nav_row(
            "This PC",
            "computer-symbolic",
            "page:this_pc",
            lambda: self.navigate_location(Location(PAGE_THIS_PC), push=True),
            chevron_btn=chevron,
        )

        children = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0), "fos-files-nav-children")
        self._this_pc_children = children
        for name, icon_name, path, _sub in list_drives():
            try:
                dkey = f"drive:{path.resolve()}"
            except OSError:
                dkey = f"drive:{path}"
            nav_row(
                name,
                icon_name,
                dkey,
                lambda p=path: self.navigate(p, push=True),
                pack_into=children,
                indent=True,
            )
        self.sidebar.pack_start(children, False, False, 0)
        children.set_no_show_all(True)

        try:
            trash_key = f"pin:{trash_dir().resolve()}"
        except OSError:
            trash_key = f"pin:{trash_dir()}"
        trash = nav_row("Recycle Bin", "user-trash-symbolic", trash_key, lambda: self.navigate(trash_dir(), push=True))
        trash.get_parent().set_margin_top(8)
        self.sidebar.show_all()
        self._apply_this_pc_tree_visibility()

    def _apply_sidebar_width(self) -> bool:
        width = max(SIDEBAR_WIDTH_MIN, min(SIDEBAR_WIDTH_MAX, int(self._sidebar_width)))
        self.nav_paned.set_position(width)
        return False

    def _on_sidebar_position(self, paned: Gtk.Paned, _pspec) -> None:
        pos = paned.get_position()
        if pos < SIDEBAR_WIDTH_MIN:
            paned.set_position(SIDEBAR_WIDTH_MIN)
            return
        if pos > SIDEBAR_WIDTH_MAX:
            paned.set_position(SIDEBAR_WIDTH_MAX)
            return
        self._sidebar_width = pos
        if self._sidebar_resize_save_id:
            GLib.source_remove(self._sidebar_resize_save_id)

        def _persist() -> bool:
            self._sidebar_resize_save_id = 0
            self.options["sidebar_width"] = self._sidebar_width
            save_options(self.options)
            return False

        self._sidebar_resize_save_id = GLib.timeout_add(400, _persist)

    def _toggle_this_pc_tree(self) -> None:
        self._this_pc_expanded = not self._this_pc_expanded
        self._apply_this_pc_tree_visibility()

    def _apply_this_pc_tree_visibility(self) -> None:
        children = self._this_pc_children
        chevron = self._this_pc_chevron
        if children is None:
            return
        if self._this_pc_expanded:
            children.set_no_show_all(False)
            children.show_all()
        else:
            children.set_no_show_all(True)
            children.hide()
        if chevron is not None:
            clear(chevron)
            glyph = "pan-down-symbolic" if self._this_pc_expanded else "pan-end-symbolic"
            chevron.add(icon(glyph, 12))
            chevron.show_all()
            chevron.set_tooltip_text("Collapse This PC" if self._this_pc_expanded else "Expand This PC")

    def _update_nav(self) -> None:
        loc = self.location()
        active_key = ""
        if loc is None:
            return
        if loc.page == PAGE_THIS_PC:
            active_key = "page:this_pc"
        elif loc.path is not None:
            try:
                key_path = str(loc.path.resolve())
            except OSError:
                key_path = str(loc.path)
            try:
                home_key = f"home:{Path.home().resolve()}"
            except OSError:
                home_key = f"home:{Path.home()}"
            # Prefer exact Home match over Quick access pins that share the path.
            if key_path == home_key[5:] and home_key in self._nav_buttons:
                active_key = home_key
            else:
                cloud_key = ""
                cloud_child = ""
                for key in self._nav_buttons:
                    if key.startswith("drive:") and key[6:] == key_path:
                        active_key = key
                        break
                    if key.startswith("pin:") and key[4:] == key_path:
                        active_key = key
                        break
                    if key.startswith("onedrive:"):
                        root = key[len("onedrive:") :]
                        if root == key_path:
                            cloud_key = key
                        elif not cloud_child:
                            try:
                                if Path(key_path).is_relative_to(root):
                                    cloud_child = key
                            except (OSError, ValueError):
                                pass
                if cloud_key:
                    active_key = cloud_key
                elif not active_key:
                    active_key = cloud_child
            if not active_key and is_trash_path(loc.path):
                try:
                    active_key = f"pin:{trash_dir().resolve()}"
                except OSError:
                    active_key = f"pin:{trash_dir()}"
            # Auto-expand This PC when browsing a drive child.
            if active_key.startswith("drive:") and not self._this_pc_expanded:
                self._this_pc_expanded = True
                self._apply_this_pc_tree_visibility()
        for key, nav in self._nav_buttons.items():
            on = key == active_key
            set_class(nav, "secondary", on)
            set_class(nav, "ghost", not on)
            set_class(nav, "fos-files-nav-active", on)

    # --- Refresh / listing ----------------------------------------------------

    def refresh(self, keep_search_focus: bool = False) -> None:
        tab = self.tab()
        if tab is None:
            return
        loc = tab.location()
        had_focus = keep_search_focus or self.search.has_focus()
        cursor = self.search.get_position() if had_focus else None
        tab.set_title()
        self.set_badge(loc.title())
        if not self._address_mode:
            self._rebuild_breadcrumb(loc)
        self._rebuild_listing(tab, loc)
        self._update_nav()
        self._update_command_bar()
        self._update_view_buttons()
        self._rebuild_details()
        self.back_btn.set_sensitive(tab.history_index > 0)
        self.fwd_btn.set_sensitive(tab.history_index + 1 < len(tab.history))
        folder = loc.folder_path()
        self.up_btn.set_sensitive(folder is not None and folder != folder.parent)
        self.show_all()
        if tab.details_visible:
            self.details_pane.show()
        else:
            self.details_pane.hide()
        self.location_stack.set_visible_child_name("address" if self._address_mode else "breadcrumb")
        self._apply_this_pc_tree_visibility()
        if had_focus:
            self.search.grab_focus()
            if cursor is not None:
                self.search.set_position(cursor)

    def _rebuild_breadcrumb(self, loc: Location) -> None:
        clear(self.breadcrumb)
        self.breadcrumb.show()

        def add_crumb(text: str, target: Location | None, strong: bool = False) -> None:
            crumb = button(text, variant="ghost", size="sm")
            if strong:
                add_classes(crumb, "fos-strong")
            if target is not None:
                crumb.connect("clicked", lambda _b, t=target: self.navigate_location(t, push=True))
            self.breadcrumb.pack_start(crumb, False, False, 0)

        def chev() -> None:
            mark = label("›", "fos-small", "fos-muted", xalign=0.5)
            mark.set_margin_start(2)
            mark.set_margin_end(2)
            self.breadcrumb.pack_start(mark, False, False, 0)

        if loc.page == PAGE_THIS_PC:
            add_crumb("This PC", None, strong=True)
        elif loc.path is not None:
            path = loc.path
            try:
                if is_trash_path(path) and path.resolve() == trash_dir().resolve():
                    parts = [(trash_dir(), "Recycle Bin")]
                else:
                    home = Path.home()
                    if path == Path("/"):
                        parts = [(Path("/"), "FosOS (C:)")]
                    elif path == home or path.is_relative_to(home):
                        parts = [(home, "Home")]
                        current = home
                        if path != home:
                            for part in path.relative_to(home).parts:
                                current = current / part
                                parts.append((current, part))
                    else:
                        parts = [(Path("/"), "FosOS (C:)")]
                        current = Path("/")
                        for part in path.parts[1:]:
                            current = current / part
                            parts.append((current, part))
            except (OSError, ValueError, AttributeError):
                parts = [(path, path.name or str(path))]
            for index, (target, name) in enumerate(parts):
                if index > 0:
                    chev()
                add_crumb(name, Location(PAGE_FOLDER, target), strong=index == len(parts) - 1)
        self.breadcrumb.show_all()

    def _entries(self, path: Path, tab: FilesTab) -> list[Path]:
        query = tab.search_text.strip().lower()
        show_hidden = self.options.get("show_hidden", False)
        try:
            entries = [p for p in path.iterdir() if show_hidden or not p.name.startswith(".")]
        except OSError:
            return []
        if query:
            entries = [p for p in entries if query in p.name.lower()]
        return self._sort_entries(entries, tab)

    def _sort_entries(self, entries: list[Path], tab: FilesTab) -> list[Path]:
        key = tab.sort_key
        reverse = not tab.sort_asc

        def sort_key(p: Path):
            try:
                st = p.stat()
            except OSError:
                st = None
            is_dir = p.is_dir()
            if key == "size":
                val = 0 if is_dir or st is None else st.st_size
            elif key == "modified":
                val = 0 if st is None else st.st_mtime
            elif key == "type":
                val = "" if is_dir else p.suffix.lower()
            else:
                val = p.name.lower()
            return (not is_dir, val)

        return sorted(entries, key=sort_key, reverse=reverse)

    def _set_listing_inset(self, mode: str | None) -> None:
        """Details/list sit flush; icon grids keep a small inset."""
        inset = 0 if mode in ("details", "list") else 12
        self.listing.set_border_width(inset)

    def _rebuild_listing(self, tab: FilesTab, loc: Location) -> None:
        clear(self.listing)
        self._item_widgets: dict[Path, Gtk.Widget] = {}
        tab._entries_cache = []
        # Drop removed virtual pages (Home / Gallery) from older sessions.
        if loc.page in ("home", "gallery"):
            loc = Location(PAGE_THIS_PC)
            tab.history[tab.history_index] = loc
        if loc.page == PAGE_THIS_PC:
            self._set_listing_inset("tiles")
            self._build_this_pc(tab)
            return
        path = loc.path
        if path is None:
            return
        entries = self._entries(path, tab)
        tab._entries_cache = entries
        tab.selected = {p for p in tab.selected if p in entries}
        if tab._anchor is not None and tab._anchor not in tab.selected:
            tab._anchor = next(iter(tab.selected), None)
        if not entries:
            self._set_listing_inset(tab.view_mode)
            empty = "Recycle Bin is empty." if is_trash_path(path) else (
                "This folder is empty." if not tab.search_text else "No matching items."
            )
            self.listing.pack_start(label(empty, "fos-text", "fos-muted"), False, False, 8)
            self.status_left.set_text("0 items")
            return
        self._render_entries(entries, tab)
        nsel = len(tab.selected)
        selected = f"  ·  {nsel} selected" if nsel else ""
        size_bit = ""
        if nsel == 1:
            only = next(iter(tab.selected))
            if only.is_file():
                try:
                    size_bit = f"  ·  {format_size(only.stat().st_size)}"
                except OSError:
                    pass
        self.status_left.set_text(f"{len(entries)} items{selected}{size_bit}")

    def _render_entries(self, entries: list[Path], tab: FilesTab) -> None:
        mode = tab.view_mode
        self._set_listing_inset(mode)
        if mode == "details":
            self._build_details_table(entries, tab)
        elif mode == "list":
            self._build_list_view(entries, tab)
        elif mode == "tiles":
            self._build_tiles(entries, tab)
        else:
            self._build_icon_grid(entries, tab, VIEW_ICON_PX.get(mode, 48))

    def _build_details_table(self, entries: list[Path], tab: FilesTab) -> None:
        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-files-table")
        header = add_classes(Gtk.Box(spacing=8), "fos-files-table-header")
        for title, key, width, expand in (
            ("Name", "name", -1, True),
            ("Modified", "modified", 100, False),
            ("Type", "type", 80, False),
            ("Size", "size", 72, False),
        ):
            btn = button(title, variant="ghost", size="sm")
            add_classes(btn, "fos-files-sort-header")
            if key == tab.sort_key:
                mark = " ▲" if tab.sort_asc else " ▼"
                child = btn.get_child()
                if isinstance(child, Gtk.Label):
                    child.set_text(title + mark)
            btn.connect("clicked", lambda _b, k=key: self._toggle_sort(k))
            if expand:
                header.pack_start(btn, True, True, 0)
            else:
                btn.set_size_request(width, -1)
                header.pack_start(btn, False, False, 0)
        frame.pack_start(header, False, False, 0)
        for entry in entries:
            frame.pack_start(self._list_row(entry, tab, details=True), False, False, 0)
        self.listing.pack_start(frame, False, False, 0)

    def _build_list_view(self, entries: list[Path], tab: FilesTab) -> None:
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for entry in entries:
            col.pack_start(self._list_row(entry, tab, details=False), False, False, 0)
        self.listing.pack_start(col, False, False, 0)

    def _list_row(self, path: Path, tab: FilesTab, details: bool) -> Gtk.Button:
        selected = path in tab.selected
        row = button(variant="ghost")
        add_classes(row, "fos-files-row")
        if selected:
            add_classes(row, "selected")
        box = Gtk.Box(spacing=8)
        # Pixbuf load (FORCE_REGULAR): theme sets -gtk-icon-style:symbolic and would
        # otherwise remap to Adwaita "plate" MIME glyphs.
        box.pack_start(full_icon(entry_icon(path, symbolic=False), 16), False, False, 0)
        name = label(entry_name(path), "fos-text", ellipsize=True)
        name.set_hexpand(True)
        box.pack_start(name, True, True, 0)
        if details:
            try:
                st = path.stat()
                mtime = format_mtime(st.st_mtime)
                size_text = "" if path.is_dir() else format_size(st.st_size)
                type_text = "File folder" if path.is_dir() else (path.suffix.upper().lstrip(".") or "File")
            except OSError:
                mtime, size_text, type_text = "—", "—", "—"
            modified = label(mtime, "fos-small", "fos-muted")
            modified.set_size_request(100, -1)
            typ = label(type_text, "fos-small", "fos-muted")
            typ.set_size_request(80, -1)
            size = label(size_text or "—", "fos-small", "fos-muted", xalign=1.0)
            size.set_size_request(72, -1)
            box.pack_start(modified, False, False, 0)
            box.pack_start(typ, False, False, 0)
            box.pack_start(size, False, False, 0)
        row.add(box)
        self._wire_item(row, path)
        return row

    def _listing_width(self) -> int:
        for widget in (self.list_hit, self.listing):
            width = widget.get_allocated_width()
            if width >= 64:
                return width
        return 640

    def _pack_icon_rows(
        self,
        cells: list[Gtk.Widget],
        *,
        cell_w: int,
        col_spacing: int = 2,
        row_spacing: int = 2,
    ) -> None:
        """Pack fixed-width cells left→right, wrap by rows (Win11 icon view)."""
        cols = max(1, (self._listing_width() + col_spacing) // (cell_w + col_spacing))
        self._icon_wrap_cols = cols
        wrap = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=row_spacing), "fos-files-flow")
        wrap.set_halign(Gtk.Align.FILL)
        wrap.set_valign(Gtk.Align.START)
        wrap.set_hexpand(True)
        wrap.set_vexpand(False)
        row: Gtk.Box | None = None
        for index, cell in enumerate(cells):
            if index % cols == 0:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=col_spacing)
                row.set_halign(Gtk.Align.START)
                row.set_hexpand(False)
                row.set_vexpand(False)
                wrap.pack_start(row, False, False, 0)
            assert row is not None
            cell.set_hexpand(False)
            cell.set_halign(Gtk.Align.START)
            row.pack_start(cell, False, False, 0)
        self.listing.pack_start(wrap, False, False, 0)
        self._ensure_icon_reflow_watch()

    def _ensure_icon_reflow_watch(self) -> None:
        if getattr(self, "_icon_reflow_connected", False):
            return
        self._icon_reflow_connected = True
        self._icon_wrap_cols = getattr(self, "_icon_wrap_cols", -1)
        self._icon_reflow_pending = False

        def on_allocate(_widget, allocation) -> None:
            tab = self.tab()
            if tab is None or tab.view_mode in ("details", "list"):
                return
            if tab.view_mode == "tiles":
                cell_w = 240
                spacing = 8
            elif tab.view_mode.startswith("icons-"):
                px = VIEW_ICON_PX.get(tab.view_mode, 48)
                cell_w = max(px + 32, 74)
                spacing = 2
            else:
                return
            cols = max(1, (max(allocation.width, 64) + spacing) // (cell_w + spacing))
            if cols == getattr(self, "_icon_wrap_cols", -1):
                return
            if self._icon_reflow_pending:
                return
            self._icon_reflow_pending = True

            def reflow() -> bool:
                self._icon_reflow_pending = False
                cur = self.tab()
                if cur is None or cur.view_mode in ("details", "list"):
                    return False
                self.refresh()
                return False

            GLib.idle_add(reflow)

        self.list_hit.connect("size-allocate", on_allocate)

    def _build_icon_grid(self, entries: list[Path], tab: FilesTab, px: int) -> None:
        cell_w = max(px + 32, 74)
        cell_h = px + 36
        cells: list[Gtk.Widget] = []
        for path in entries:
            tile_btn = button(variant="ghost")
            add_classes(tile_btn, "tile", "fos-files-tile")
            tile_btn.set_size_request(cell_w, cell_h)
            if path in tab.selected:
                add_classes(tile_btn, "selected")
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            col.set_halign(Gtk.Align.CENTER)
            col.set_valign(Gtk.Align.CENTER)
            thumb = self._entry_thumb(path, px)
            thumb.set_halign(Gtk.Align.CENTER)
            col.pack_start(thumb, False, False, 0)
            name = label(entry_name(path), "fos-small", xalign=0.5, ellipsize=True)
            name.set_width_chars(max(8, px // 7))
            name.set_max_width_chars(max(8, px // 7))
            name.set_halign(Gtk.Align.CENTER)
            col.pack_start(name, False, False, 0)
            tile_btn.add(col)
            self._wire_item(tile_btn, path)
            cells.append(tile_btn)
        self._pack_icon_rows(cells, cell_w=cell_w)

    def _build_tiles(self, entries: list[Path], tab: FilesTab) -> None:
        cell_w = 240
        cells: list[Gtk.Widget] = []
        for path in entries:
            tile_btn = button(variant="ghost")
            add_classes(tile_btn, "tile", "fos-files-tile")
            tile_btn.set_size_request(cell_w, 64)
            if path in tab.selected:
                add_classes(tile_btn, "selected")
            row = Gtk.Box(spacing=10)
            row.set_border_width(6)
            row.pack_start(self._entry_thumb(path, 40), False, False, 0)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            name = label(entry_name(path), "fos-text", ellipsize=True)
            name.set_max_width_chars(22)
            col.pack_start(name, False, False, 0)
            try:
                if path.is_dir():
                    sub = "File folder"
                elif path.suffix.lower() == ".desktop":
                    sub = "Shortcut"
                else:
                    st = path.stat()
                    sub = format_size(st.st_size)
            except OSError:
                sub = "—"
            col.pack_start(label(sub, "fos-small", "fos-muted", ellipsize=True), False, False, 0)
            row.pack_start(col, True, True, 0)
            tile_btn.add(row)
            self._wire_item(tile_btn, path)
            cells.append(tile_btn)
        self._pack_icon_rows(cells, cell_w=cell_w, col_spacing=8, row_spacing=8)

    def _entry_thumb(self, path: Path, px: int) -> Gtk.Widget:
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES and px >= 32:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), px, px, True)
                image = Gtk.Image.new_from_pixbuf(pixbuf)
                image.set_pixel_size(px)
                return image
            except GLib.Error:
                pass
        # Prefer FosOS icons via pixbuf (bypass theme symbolic remapping).
        return full_icon(entry_icon(path, symbolic=False), min(max(px, 16), 64))

    # --- Virtual pages --------------------------------------------------------

    def _build_this_pc(self, tab: FilesTab) -> None:
        self.listing.pack_start(label("Devices and drives", "fos-label"), False, False, 0)
        drives = list_drives()
        query = tab.search_text.strip().lower()
        if query:
            drives = [d for d in drives if query in d[0].lower() or query in str(d[2]).lower()]
        if not drives:
            self.listing.pack_start(label("No drives found.", "fos-text", "fos-muted"), False, False, 8)
            self.status_left.set_text("This PC")
            return
        cells: list[Gtk.Widget] = []
        for name, icon_name, path, subtitle in drives:
            btn = button(variant="ghost")
            add_classes(btn, "tile", "fos-files-drive")
            btn.set_size_request(280, -1)
            row = Gtk.Box(spacing=12)
            row.set_border_width(8)
            row.pack_start(full_icon(icon_name, 40), False, False, 0)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            title = label(name, "fos-text", ellipsize=True)
            title.set_max_width_chars(24)
            col.pack_start(title, False, False, 0)
            col.pack_start(label(subtitle, "fos-small", "fos-muted", ellipsize=True), False, False, 0)
            try:
                usage = shutil.disk_usage(path)
                bar = Gtk.ProgressBar()
                bar.set_fraction(usage.used / usage.total if usage.total else 0)
                bar.set_show_text(False)
                add_classes(bar, "fos-files-usage")
                col.pack_start(bar, False, False, 4)
            except OSError:
                pass
            row.pack_start(col, True, True, 0)
            btn.add(row)
            btn.connect("button-press-event", self._on_drive_press, path)
            cells.append(btn)
        self._pack_icon_rows(cells, cell_w=280, col_spacing=10, row_spacing=10)
        self.status_left.set_text(f"{len(drives)} drives")

    def _on_drive_press(self, _widget, event: Gdk.EventButton, path: Path) -> bool:
        if event.button == 1:
            self.navigate(path, push=True)
            return True
        if event.button == 3:
            menu = Gtk.Menu()
            open_item = Gtk.MenuItem(label="Open")
            open_item.connect("activate", lambda _i: self.navigate(path, push=True))
            menu.append(open_item)
            open_tab = Gtk.MenuItem(label="Open in new tab")
            open_tab.connect("activate", lambda _i: self.new_tab(Location(PAGE_FOLDER, path)))
            menu.append(open_tab)
            menu.append(Gtk.SeparatorMenuItem())
            props = Gtk.MenuItem(label="Properties")
            props.connect("activate", lambda _i: self._properties(path))
            menu.append(props)
            menu.show_all()
            menu.popup_at_pointer(event)
            return True
        return False

    # --- Details pane / command bar -------------------------------------------

    def _rebuild_details(self) -> None:
        clear(self.details_pane)
        tab = self.tab()
        if tab is None or not tab.details_visible:
            return
        path = self.primary_selected()
        if path is None:
            loc = tab.location()
            if loc and loc.folder_path() is not None:
                path = loc.folder_path()
            else:
                self.details_pane.pack_start(label("Select an item to see details", "fos-text", "fos-muted"), False, False, 0)
                self.details_pane.show_all()
                return
        assert path is not None
        self.details_pane.pack_start(self._entry_thumb(path, 96), False, False, 0)
        self.details_pane.pack_start(label(path.name, "fos-title", ellipsize=True), False, False, 0)
        try:
            st = path.stat()
            mime, _ = Gio.content_type_guess(str(path), None)
            rows = [
                ("Type", "File folder" if path.is_dir() else (mime or "File")),
                ("Size", "—" if path.is_dir() else format_size(st.st_size)),
                ("Modified", datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")),
                ("Location", str(path.parent)),
            ]
        except OSError:
            rows = [("Location", str(path.parent))]
        for key, value in rows:
            row = Gtk.Box(spacing=8)
            row.pack_start(label(key, "fos-small", "fos-muted"), False, False, 0)
            val = label(value, "fos-small", ellipsize=True)
            val.set_hexpand(True)
            val.set_xalign(1.0)
            row.pack_start(val, True, True, 0)
            self.details_pane.pack_start(row, False, False, 0)
        actions = Gtk.Box(spacing=4)
        open_btn = button("Open", variant="secondary", size="sm")
        open_btn.connect("clicked", lambda _b, p=path: self.open_path(p))
        copy_btn = button("Copy path", variant="ghost", size="sm")
        copy_btn.connect("clicked", lambda _b, p=path: self._copy_path_text([p]))
        props_btn = button("Properties", variant="ghost", size="sm")
        props_btn.connect("clicked", lambda _b, p=path: self._properties(p))
        for b in (open_btn, copy_btn, props_btn):
            actions.pack_start(b, False, False, 0)
        self.details_pane.pack_start(actions, False, False, 8)
        self.details_pane.show_all()

    def _update_command_bar(self) -> None:
        tab = self.tab()
        loc = self.location()
        folder = loc.folder_path() if loc else None
        in_trash = folder is not None and is_trash_path(folder)
        has_sel = bool(tab and tab.selected)
        folder_ok = folder is not None and not in_trash and loc is not None and loc.page == PAGE_FOLDER
        self._cmd["new"].set_sensitive(folder_ok)
        self._cmd["cut"].set_sensitive(has_sel and not in_trash)
        self._cmd["copy"].set_sensitive(has_sel)
        self._cmd["paste"].set_sensitive(bool(self._clipboard) and folder_ok)
        self._cmd["rename"].set_sensitive(has_sel and len(tab.selected) == 1 and folder_ok)  # type: ignore[union-attr]
        self._cmd["share"].set_sensitive(has_sel)
        self._cmd["delete"].set_sensitive(has_sel)
        set_class(self._cmd["details"], "secondary", bool(tab and tab.details_visible))
        set_class(self._cmd["details"], "ghost", not (tab and tab.details_visible))

    def _update_view_buttons(self) -> None:
        tab = self.tab()
        mode = tab.view_mode if tab else "details"
        for key, btn in self._view_btns.items():
            on = key == mode
            set_class(btn, "secondary", on)
            set_class(btn, "ghost", not on)

    def _toggle_sort(self, key: str) -> None:
        tab = self.tab()
        if tab is None:
            return
        if tab.sort_key == key:
            tab.sort_asc = not tab.sort_asc
        else:
            tab.sort_key = key
            tab.sort_asc = True
        self.refresh()

    # --- Menus ----------------------------------------------------------------

    def _popup_new_menu(self) -> None:
        menu = Gtk.Menu()
        folder = Gtk.MenuItem(label="Folder")
        folder.connect("activate", lambda _i: self._new_folder())
        menu.append(folder)
        empty = Gtk.MenuItem(label="Text Document")
        empty.connect("activate", lambda _i: self._new_file())
        menu.append(empty)
        menu.show_all()
        menu.popup_at_widget(self._cmd["new"], Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)

    def _popup_sort_menu(self) -> None:
        tab = self.tab()
        if tab is None:
            return
        menu = Gtk.Menu()
        for key, title in (("name", "Name"), ("modified", "Date modified"), ("type", "Type"), ("size", "Size")):
            item = Gtk.CheckMenuItem(label=title)
            item.set_active(tab.sort_key == key)
            item.connect("activate", lambda _i, k=key: self._toggle_sort(k) if tab.sort_key != k else None)
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        asc = Gtk.CheckMenuItem(label="Ascending")
        asc.set_active(tab.sort_asc)
        asc.connect("activate", lambda _i: setattr(tab, "sort_asc", True) or self.refresh())
        desc = Gtk.CheckMenuItem(label="Descending")
        desc.set_active(not tab.sort_asc)
        desc.connect("activate", lambda _i: setattr(tab, "sort_asc", False) or self.refresh())
        menu.append(asc)
        menu.append(desc)
        menu.show_all()
        menu.popup_at_widget(self._cmd["sort"], Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)

    def _popup_view_menu(self) -> None:
        tab = self.tab()
        if tab is None:
            return
        menu = Gtk.Menu()
        for mode in VIEW_MODES:
            item = Gtk.CheckMenuItem(label=VIEW_LABELS[mode])
            item.set_active(tab.view_mode == mode)
            item.connect("activate", lambda _i, m=mode: self.set_view_mode(m))
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        details = Gtk.CheckMenuItem(label="Details pane")
        details.set_active(tab.details_visible)
        details.connect("activate", lambda _i: self.toggle_details())
        menu.append(details)
        menu.show_all()
        menu.popup_at_widget(self._cmd["view"], Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)

    def _popup_more_menu(self) -> None:
        menu = Gtk.Menu()
        opts = Gtk.MenuItem(label="Options…")
        opts.connect("activate", lambda _i: self._show_options())
        menu.append(opts)
        hidden = Gtk.CheckMenuItem(label="Show hidden items")
        hidden.set_active(bool(self.options.get("show_hidden")))
        hidden.connect("activate", lambda _i: self._toggle_hidden())
        menu.append(hidden)
        menu.append(Gtk.SeparatorMenuItem())
        refresh = Gtk.MenuItem(label="Refresh")
        refresh.connect("activate", lambda _i: self.refresh())
        menu.append(refresh)
        loc = self.location()
        folder = loc.folder_path() if loc else None
        if folder is not None and not is_trash_path(folder):
            term = Gtk.MenuItem(label="Open Terminal here")
            term.connect("activate", lambda _i: self._open_terminal(folder))
            menu.append(term)
            props = Gtk.MenuItem(label="Properties")
            props.connect("activate", lambda _i: self._properties(folder))
            menu.append(props)
        menu.show_all()
        menu.popup_at_widget(self._cmd["more"], Gdk.Gravity.SOUTH_EAST, Gdk.Gravity.NORTH_EAST, None)

    def _show_options(self) -> None:
        dialog = FosDialog(self, title="Folder Options", width=420)
        dialog.add_body_text("Open File Explorer to", "fos-text")
        store = Gtk.ListStore(str, str)
        store.append(["This PC", "this_pc"])
        store.append(["User folder", "user"])
        combo = Gtk.ComboBox.new_with_model(store)
        renderer = Gtk.CellRendererText()
        combo.pack_start(renderer, True)
        combo.add_attribute(renderer, "text", 0)
        combo.set_active(1 if self.options.get("open_to") == "user" else 0)
        dialog.content.pack_start(combo, False, False, 0)
        dialog.add_action("Cancel", None, variant="ghost")

        def accept(_btn=None) -> None:
            active = combo.get_active_iter()
            if active is not None:
                self.options["open_to"] = store[active][1]
                save_options(self.options)
            dialog.respond(True)

        ok = button("OK", variant="default", size="sm")
        ok.connect("clicked", accept)
        dialog.footer.pack_start(ok, False, False, 0)
        dialog.run()

    def _toggle_hidden(self) -> None:
        self.options["show_hidden"] = not self.options.get("show_hidden", False)
        save_options(self.options)
        self.refresh()

    def _cmd_cut(self) -> None:
        tab = self.tab()
        if tab and tab.selected:
            self._clipboard_set(list(tab.selected), cut=True)

    def _cmd_copy(self) -> None:
        tab = self.tab()
        if tab and tab.selected:
            self._clipboard_set(list(tab.selected), cut=False)

    def _cmd_rename(self) -> None:
        path = self.primary_selected()
        if path is not None:
            self._rename(path)

    def _cmd_share(self) -> None:
        tab = self.tab()
        if tab and tab.selected:
            self._copy_path_text(list(tab.selected))

    def _cmd_delete(self) -> None:
        tab = self.tab()
        loc = self.location()
        if tab is None or not tab.selected:
            return
        folder = loc.folder_path() if loc else None
        if folder is not None and is_trash_path(folder):
            self._delete_permanent(list(tab.selected))
        else:
            self._trash_paths(list(tab.selected))

    # --- Item wiring / selection ----------------------------------------------

    def _wire_item(self, widget: Gtk.Widget, path: Path) -> None:
        self._item_widgets[path] = widget
        widget.connect("button-press-event", self._on_item_press, path)
        # Swallow Button "clicked" so a release after select doesn't fight dbl-click.
        if isinstance(widget, Gtk.Button):
            widget.connect("clicked", lambda *_a: None)
        widget.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, URI_TARGET, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        widget.connect("drag-data-get", self._on_drag_data_get)
        if path.is_dir():
            widget.drag_dest_set(Gtk.DestDefaults.ALL, URI_TARGET, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
            widget.connect("drag-data-received", self._on_drag_data_received_folder, path)

    def _apply_selection_ui(self) -> None:
        """Update selection chrome without rebuilding the listing (keeps dbl-click / menus alive)."""
        tab = self.tab()
        selected = tab.selected if tab else set()
        for path, widget in getattr(self, "_item_widgets", {}).items():
            on = path in selected
            set_class(widget, "selected", on)
            set_class(widget, "secondary", False)
        self._update_command_bar()
        if tab is None:
            return
        nsel = len(tab.selected)
        selected_bit = f"  ·  {nsel} selected" if nsel else ""
        size_bit = ""
        if nsel == 1:
            only = next(iter(tab.selected))
            if only.is_file():
                try:
                    size_bit = f"  ·  {format_size(only.stat().st_size)}"
                except OSError:
                    pass
        n_items = len(tab._entries_cache)
        self.status_left.set_text(f"{n_items} items{selected_bit}{size_bit}")
        self._rebuild_details()

    def _double_click_time_ms(self) -> int:
        try:
            return int(Gtk.Settings.get_default().get_property("gtk-double-click-time"))
        except (TypeError, AttributeError):
            return 400

    def _on_list_bg_press(self, _widget, event: Gdk.EventButton) -> bool:
        """Empty-space clicks — Win Explorer: clear selection; RMB = background menu."""
        tab = self.tab()
        if tab is None:
            return False
        if event.button == 1:
            self._click_path = None
            if tab.selected:
                tab.selected = set()
                tab._anchor = None
                self._apply_selection_ui()
            return False
        if event.button == 3:
            if tab.selected:
                tab.selected = set()
                tab._anchor = None
                self._apply_selection_ui()
            self._popup_background_menu(event)
            return True
        return False

    def _on_item_press(self, _widget, event: Gdk.EventButton, path: Path) -> bool:
        """Item clicks — select in place; dbl-click opens; RMB menu stays up."""
        tab = self.tab()
        if tab is None:
            return False
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        if event.button == 2:
            if path.is_dir():
                self.new_tab(Location(PAGE_FOLDER, path))
            return True
        if event.button == 3:
            if path not in tab.selected:
                tab.selected = {path}
                tab._anchor = path
                self._apply_selection_ui()
            self._popup_item_menu(path, event)
            return True
        if event.button != 1:
            return False

        # Double-click open (must not rebuild listing between the two clicks).
        # GTK delivers BUTTON_PRESS then _2BUTTON_PRESS; opening on both would
        # launch the default app twice (e.g. two browser tabs).
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self._click_path = None
            self._click_time = 0
            if self._suppress_2button:
                self._suppress_2button = False
                return True
            self.open_path(path)
            return True
        if self._click_path == path:
            delta = int(event.time) - int(self._click_time)
            if 0 <= delta <= self._double_click_time_ms():
                self._click_path = None
                self._click_time = 0
                self._suppress_2button = True
                self.open_path(path)
                return True

        self._suppress_2button = False
        self._click_path = path
        self._click_time = int(event.time)

        if shift and tab._anchor is not None and tab._entries_cache:
            try:
                start = tab._entries_cache.index(tab._anchor)
                end = tab._entries_cache.index(path)
            except ValueError:
                tab.selected = {path}
                tab._anchor = path
            else:
                lo, hi = sorted((start, end))
                tab.selected = set(tab._entries_cache[lo : hi + 1])
        elif ctrl:
            if path in tab.selected:
                tab.selected.remove(path)
            else:
                tab.selected.add(path)
            tab._anchor = path
        else:
            tab.selected = {path}
            tab._anchor = path
        self._apply_selection_ui()
        return True

    def open_path(self, path: Path) -> None:
        if path.is_dir():
            self.navigate(path, push=True)
            return
        push_recent(path)
        if path.suffix.lower() == ".desktop":
            try:
                info = Gio.DesktopAppInfo.new_from_filename(str(path))
            except GLib.Error:
                info = None
            if info is not None:
                try:
                    info.launch([], None)
                    return
                except GLib.Error:
                    pass
        if path.suffix.lower() == ".deb":
            if not appmod.spawn(["fosos-install-package", str(path.resolve())]):
                self._alert("Could not open package installer", "fosos-install-package is missing.")
            return
        context = Gdk.Display.get_default().get_app_launch_context()
        try:
            Gio.AppInfo.launch_default_for_uri(path.as_uri(), context)
        except GLib.Error:
            pass

    def _menu_add(self, menu: Gtk.Menu, label: str, callback, *, sensitive: bool = True) -> Gtk.MenuItem:
        item = Gtk.MenuItem(label=label)
        item.set_sensitive(sensitive)
        if callback is not None:
            item.connect("activate", lambda _i: callback())
        menu.append(item)
        return item

    def _menu_submenu(self, menu: Gtk.Menu, label: str) -> Gtk.Menu:
        item = Gtk.MenuItem(label=label)
        sub = Gtk.Menu()
        item.set_submenu(sub)
        menu.append(item)
        return sub

    def _append_view_submenu(self, menu: Gtk.Menu) -> None:
        tab = self.tab()
        if tab is None:
            return
        sub = self._menu_submenu(menu, "View")
        for mode in VIEW_MODES:
            item = Gtk.CheckMenuItem(label=VIEW_LABELS[mode])
            item.set_active(tab.view_mode == mode)
            item.connect("activate", lambda _i, m=mode: self.set_view_mode(m))
            sub.append(item)

    def _append_sort_submenu(self, menu: Gtk.Menu) -> None:
        tab = self.tab()
        if tab is None:
            return
        sub = self._menu_submenu(menu, "Sort by")
        for key, title in (("name", "Name"), ("modified", "Date modified"), ("type", "Type"), ("size", "Size")):
            item = Gtk.CheckMenuItem(label=title)
            item.set_active(tab.sort_key == key)
            item.connect("activate", lambda _i, k=key: self._toggle_sort(k) if tab.sort_key != k else None)
            sub.append(item)
        sub.append(Gtk.SeparatorMenuItem())
        asc = Gtk.CheckMenuItem(label="Ascending")
        asc.set_active(tab.sort_asc)
        asc.connect("activate", lambda _i: setattr(tab, "sort_asc", True) or self.refresh())
        desc = Gtk.CheckMenuItem(label="Descending")
        desc.set_active(not tab.sort_asc)
        desc.connect("activate", lambda _i: setattr(tab, "sort_asc", False) or self.refresh())
        sub.append(asc)
        sub.append(desc)

    def _append_new_submenu(self, menu: Gtk.Menu) -> None:
        sub = self._menu_submenu(menu, "New")
        self._menu_add(sub, "Folder", self._new_folder)
        self._menu_add(sub, "Text Document", self._new_file)

    def _popup_item_menu(self, path: Path, event: Gdk.EventButton) -> None:
        """Right-click on file/folder — Windows Explorer item menu shape."""
        tab = self.tab()
        if tab is None:
            return
        menu = Gtk.Menu()
        paths = list(tab.selected) if tab.selected else [path]
        in_trash = is_trash_path(path)
        current = self.current()
        can_edit = current is not None and not in_trash

        if len(paths) == 1:
            open_label = "Install" if path.is_file() and path.suffix.lower() == ".deb" else "Open"
            self._menu_add(menu, open_label, lambda p=path: self.open_path(p))
            if path.is_dir():
                self._menu_add(
                    menu,
                    "Open in new tab",
                    lambda p=path: self.new_tab(Location(PAGE_FOLDER, p)),
                )
            if path.is_file():
                self._menu_add(menu, "Open with…", lambda p=path: self._open_with(p))
        else:
            self._menu_add(menu, "Open", lambda ps=list(paths): [self.open_path(p) for p in ps])

        menu.append(Gtk.SeparatorMenuItem())
        self._menu_add(menu, "Cut", lambda: self._clipboard_set(paths, cut=True), sensitive=can_edit or in_trash)
        self._menu_add(menu, "Copy", lambda: self._clipboard_set(paths, cut=False))
        self._menu_add(
            menu,
            "Paste",
            self._paste,
            sensitive=bool(self._clipboard) and can_edit,
        )

        menu.append(Gtk.SeparatorMenuItem())
        if in_trash:
            self._menu_add(menu, "Restore", lambda: self._restore_paths(paths))
            self._menu_add(menu, "Delete permanently", lambda: self._delete_permanent(paths))
        else:
            self._menu_add(
                menu,
                "Rename",
                lambda: self._rename(path),
                sensitive=len(paths) == 1 and can_edit and path.parent == current,
            )
            self._menu_add(menu, "Delete", lambda: self._trash_paths(paths), sensitive=can_edit)

        menu.append(Gtk.SeparatorMenuItem())
        self._menu_add(menu, "Copy as path", lambda: self._copy_path_text(paths))
        if len(paths) == 1 and path.is_dir() and not in_trash:
            self._menu_add(menu, "Pin to Quick access", lambda p=path: self._pin(p))
        if len(paths) == 1:
            self._menu_add(menu, "Properties", lambda p=path: self._properties(p))

        self._show_context_menu(menu, event)

    def _popup_background_menu(self, event: Gdk.EventButton) -> None:
        """Right-click empty space — Windows Explorer background menu shape."""
        menu = Gtk.Menu()
        current = self.current()
        in_trash = current is not None and is_trash_path(current)
        can_edit = current is not None and not in_trash

        self._append_view_submenu(menu)
        self._append_sort_submenu(menu)
        menu.append(Gtk.SeparatorMenuItem())
        self._menu_add(menu, "Refresh", self.refresh)
        menu.append(Gtk.SeparatorMenuItem())

        if can_edit:
            self._append_new_submenu(menu)
            menu.append(Gtk.SeparatorMenuItem())

        self._menu_add(
            menu,
            "Paste",
            self._paste,
            sensitive=bool(self._clipboard) and can_edit,
        )
        self._menu_add(
            menu,
            "Select all",
            self._select_all,
            sensitive=bool(self.tab() and self.tab()._entries_cache),  # type: ignore[union-attr]
        )

        if can_edit:
            menu.append(Gtk.SeparatorMenuItem())
            self._menu_add(menu, "Open in Terminal", lambda: self._open_terminal(current))

        if current is not None:
            menu.append(Gtk.SeparatorMenuItem())
            self._menu_add(menu, "Properties", lambda: self._properties(current))

        self._show_context_menu(menu, event)

    def _show_context_menu(self, menu: Gtk.Menu, event: Gdk.EventButton) -> None:
        """Popup with the triggering event so GTK keeps the menu until a real choice/dismiss."""
        menu.attach_to_widget(self, None)
        menu.show_all()
        # Must run during button-press with the real event — idle popup is dismissed by release.
        menu.popup_at_pointer(event)

    def _select_all(self) -> None:
        tab = self.tab()
        if tab is None or not tab._entries_cache:
            return
        tab.selected = set(tab._entries_cache)
        self._apply_selection_ui()

    def _pin(self, path: Path) -> None:
        try:
            path = path.resolve()
        except OSError:
            return
        for pin in self.pins:
            if Path(pin.get("path", "")) == path:
                return
        self.pins.append({"name": path.name, "icon": "folder-symbolic", "path": str(path)})
        save_pins(self.pins)
        self._rebuild_sidebar()
        self._update_nav()

    def _unpin(self, path: Path) -> None:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)

        def pin_key(pin: dict) -> str:
            try:
                return str(Path(pin.get("path", "")).resolve())
            except OSError:
                return str(pin.get("path", ""))

        self.pins = [p for p in self.pins if pin_key(p) != key]
        save_pins(self.pins)
        self._rebuild_sidebar()
        self.refresh()

    # Clipboard / trash / transfer

    def _clipboard_set(self, paths: list[Path], cut: bool) -> None:
        self._clipboard = [p.resolve() for p in paths]
        self._clipboard_cut = cut
        self.status_left.set_text(f"{'Cut' if cut else 'Copied'} {len(paths)} item(s)")
        self._update_command_bar()

    def _copy_path_text(self, paths: list[Path]) -> None:
        text = "\n".join(str(p) for p in paths)
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        clipboard.store()
        self.status_left.set_text("Path copied")

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
        self._update_command_bar()

    def _trash_paths(self, paths: list[Path]) -> None:
        failed = []
        for path in paths:
            try:
                Gio.File.new_for_path(str(path)).trash(None)
            except GLib.Error:
                failed.append(path.name)
        tab = self.tab()
        if tab is not None:
            tab.selected = set()
            tab._anchor = None
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
        tab = self.tab()
        if tab is not None:
            tab.selected = set()
            tab._anchor = None
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
        tab = self.tab()
        if tab is not None:
            tab.selected = set()
            tab._anchor = None
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
            dialog = FosDialog(self, title="Copying…" if not move else "Moving…")
            dialog.add_body_text("Working with files…", "fos-text")
            bar = Gtk.ProgressBar()
            bar.set_show_text(True)
            dialog.content.pack_start(bar, False, False, 0)
            dialog.show_all()

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
            time.sleep(0)

        if dialog is not None:
            dialog.destroy()
        self.refresh()
        if errors:
            self._alert("Some items could not be transferred", "\n".join(errors[:8]))

    def _on_drag_data_get(self, _widget, _context, data, _info, _time) -> None:
        tab = self.tab()
        paths = list(tab.selected) if tab and tab.selected else []
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
        tab = self.tab()
        if tab is not None:
            tab.selected = {target}
            tab._anchor = target
        self.refresh()

    def _new_file(self) -> None:
        current = self.current()
        if current is None or is_trash_path(current):
            return
        name = self._ask_text("New Text Document", "File name", "New Text Document.txt")
        if not name:
            return
        target = unique_dest(current, name)
        try:
            target.write_text("", encoding="utf-8")
        except OSError:
            self._alert("Could not create file", name)
            return
        tab = self.tab()
        if tab is not None:
            tab.selected = {target}
            tab._anchor = target
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
        tab = self.tab()
        if tab is not None:
            tab.selected = {target}
            tab._anchor = target
        self.refresh()

    def _open_with(self, path: Path) -> None:
        mime, _ = Gio.content_type_guess(str(path), None)
        apps = list(Gio.AppInfo.get_all_for_type(mime)) if mime else []
        if not apps:
            self._alert("No apps available", f"Nothing is registered for {mime or 'this file'}.")
            return
        dialog = FosDialog(self, title="Open with")
        dialog.add_body_text(f"Open “{path.name}” with:", "fos-text")
        store = Gtk.ListStore(str, object)
        for app in apps:
            store.append([app.get_display_name(), app])
        combo = Gtk.ComboBox.new_with_model(store)
        renderer = Gtk.CellRendererText()
        combo.pack_start(renderer, True)
        combo.add_attribute(renderer, "text", 0)
        combo.set_active(0)
        dialog.content.pack_start(combo, False, False, 0)
        chosen: dict[str, object | None] = {"app": None}

        def accept(_btn=None) -> None:
            active = combo.get_active_iter()
            if active is not None:
                chosen["app"] = store[active][1]
            dialog.respond(True)

        dialog.add_action("Cancel", None, variant="ghost")
        ok_btn = button("Open", variant="default", size="sm")
        ok_btn.connect("clicked", accept)
        dialog.footer.pack_start(ok_btn, False, False, 0)
        if dialog.run() is not True or chosen["app"] is None:
            return
        try:
            chosen["app"].launch([Gio.File.new_for_path(str(path))], None)
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
            ("Name", path.name or str(path)),
            ("Type", "Folder" if path.is_dir() else (mime or "File")),
            ("Size", size),
            ("Modified", modified),
            ("Permissions", mode),
            ("Location", str(path.parent if path.name else path)),
        ]
        dialog = FosDialog(self, title="Properties", width=480)
        grid = Gtk.Grid(column_spacing=16, row_spacing=8)
        for index, (key, value) in enumerate(rows):
            grid.attach(label(key, "fos-text", "fos-muted"), 0, index, 1, 1)
            val = label(value, "fos-text", ellipsize=True)
            val.set_selectable(True)
            val.set_max_width_chars(48)
            grid.attach(val, 1, index, 1, 1)
        dialog.content.pack_start(grid, False, False, 0)
        dialog.add_action("Close", True, variant="default", default=True)
        dialog.run()

    def _open_terminal(self, path: Path) -> None:
        cwd = path if path.is_dir() else path.parent
        if not appmod.spawn(["fosos-terminal", str(cwd)]):
            appmod.spawn(["fosos-terminal"])

    def _ask_text(self, title: str, label_text: str, initial: str) -> str | None:
        return fos_prompt(self, title, label_text, initial)

    def _confirm(self, text: str) -> bool:
        return fos_confirm(self, text)

    def _alert(self, title: str, body: str) -> None:
        fos_alert(self, title, body)

    def _cycle_focus(self) -> None:
        """Approximate Win11 F6: tabs → nav → content → details."""
        self._focus_region = (self._focus_region + 1) % 4
        region = self._focus_region
        if region == 0 and self.tabs:
            self.tabs[0].tab_button.grab_focus()
        elif region == 1 and self._nav_buttons:
            next(iter(self._nav_buttons.values())).grab_focus()
        elif region == 2:
            self.list_hit.grab_focus()
        elif region == 3 and self.details_pane.get_visible():
            self.details_pane.grab_focus()
        else:
            self.list_hit.grab_focus()

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        key = Gdk.keyval_name(event.keyval) or ""
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        alt = bool(event.state & Gdk.ModifierType.MOD1_MASK)
        tab = self.tab()
        current = self.current()
        # Search / address entries need Backspace, Delete, arrows, Ctrl+A, etc.
        typing = self.search.has_focus() or self.address.has_focus()

        if key == "F6":
            self._cycle_focus()
            return True
        if key == "Escape":
            if self.search.has_focus() or self.search.get_text():
                self.search.set_text("")
                if self.search.has_focus():
                    self.list_hit.grab_focus()
                return True
            if self.address.has_focus():
                self._hide_address()
                return True
            if tab and tab.selected:
                tab.selected = set()
                tab._anchor = None
                self._apply_selection_ui()
                return True
            return False
        if key == "F3" or (ctrl and key.lower() == "f"):
            self.focus_search()
            return True
        if key == "F5":
            self.refresh()
            return True
        if ctrl and key.lower() == "l":
            self._show_address()
            return True
        if ctrl and key.lower() == "t":
            self.new_tab()
            return True
        if ctrl and key.lower() == "w":
            if tab is not None:
                self.close_tab(tab)
            return True
        if ctrl and key.lower() == "n":
            self.app._ensure_window(None, force_new=True)
            return True
        if typing:
            # Leave Backspace / Delete / editing chords to the Gtk.Entry.
            return False
        if ctrl and key == "Tab":
            if not self.tabs:
                return True
            idx = self.tabs.index(tab) if tab in self.tabs else 0
            nxt = (idx - 1 if shift else idx + 1) % len(self.tabs)
            self.focus_tab(self.tabs[nxt])
            return True
        if ctrl and key in ("1", "2", "3", "4", "5", "6", "7", "8", "9"):
            index = int(key) - 1
            if index < len(self.tabs):
                self.focus_tab(self.tabs[index])
            return True
        if alt and shift and key.lower() == "p":
            self.toggle_details()
            return True
        if key == "F2" and tab and len(tab.selected) == 1:
            self._rename(self.primary_selected())
            return True
        if key == "BackSpace" and not ctrl:
            self.go_up()
            return True
        if key in ("Return", "KP_Enter") and self.primary_selected() is not None:
            if alt:
                self._properties(self.primary_selected())
            else:
                self.open_path(self.primary_selected())
            return True
        if key == "Delete" and tab and tab.selected:
            if current is not None and is_trash_path(current):
                self._delete_permanent(list(tab.selected))
            elif shift:
                self._delete_permanent(list(tab.selected))
            else:
                self._trash_paths(list(tab.selected))
            return True
        if ctrl and key.lower() == "a" and tab and tab._entries_cache:
            tab.selected = set(tab._entries_cache)
            self._apply_selection_ui()
            return True
        if ctrl and key.lower() == "c" and tab and tab.selected:
            self._clipboard_set(list(tab.selected), cut=False)
            return True
        if ctrl and key.lower() == "x" and tab and tab.selected:
            self._clipboard_set(list(tab.selected), cut=True)
            return True
        if ctrl and key.lower() == "v":
            self._paste()
            return True
        if alt and key in ("Up", "KP_Up"):
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
        paths: list[Path] = []
        for gfile in files or []:
            local = gfile.get_path()
            if local:
                paths.append(Path(local))
        self._present_paths(paths)

    def do_command_line(self, command_line):
        argv = command_line.get_arguments()[1:]
        properties = "--properties" in argv
        cwd = command_line.get_cwd()
        paths: list[Path] = []
        for arg in argv:
            if not arg or arg.startswith("-"):
                continue
            path = self._coerce_path(arg, cwd)
            if path is not None:
                paths.append(path)
        self._present_paths(paths, properties=properties)
        return 0

    def _coerce_path(self, arg: str, cwd: str | None) -> Path | None:
        text = arg.strip()
        if "://" in text:
            local = Gio.File.new_for_uri(text).get_path()
            if not local:
                return None
            path = Path(local)
        else:
            path = Path(text).expanduser()
            if not path.is_absolute() and cwd:
                path = Path(cwd) / path
        if path.exists() or path.parent.exists():
            return path
        return None

    def _present_paths(self, paths: list[Path], *, properties: bool = False) -> None:
        """Open a folder, and select a file when the browser asked to reveal one."""
        usable = [path for path in paths if path.exists() or path.parent.exists()]
        if not usable:
            self._ensure_window(None)
            if self.window is not None:
                self.window.present()
            return
        files = [path for path in usable if path.is_file() or (not path.exists() and path.parent.exists())]
        folders = [path for path in usable if path.is_dir()]
        if files:
            parent = files[0].parent
            self._ensure_window(parent if parent.exists() else None)
            selectable = [path for path in files if path.exists()]
            if selectable and self.window is not None:
                self.window.select_items(selectable)
        else:
            self._ensure_window(folders[0])
            for extra in folders[1:]:
                if self.window is not None:
                    self.window.new_tab(Location(PAGE_FOLDER, extra))
        if self.window is None:
            return
        self.window.present()
        if properties:
            target = usable[0]
            GLib.idle_add(lambda p=target: (self.window._properties(p) if self.window else None) or False)

    def _ensure_window(self, path: Path | None, force_new: bool = False) -> None:
        if self.window is None or force_new:
            win = FilesWindow(self, start=path)
            win.connect("destroy", lambda w: self._on_window_destroy(w))
            if self.window is None:
                self.window = win
            win.show_all()
            win.present()
            return
        if path is not None:
            self.window.navigate(path, push=True)
        self.window.present()

    def _on_window_destroy(self, window: FilesWindow) -> None:
        if self.window is window:
            self.window = None


def main() -> int:
    return FilesApp().run(sys.argv)
