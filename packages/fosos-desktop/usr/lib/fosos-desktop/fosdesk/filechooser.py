"""FosOS open/save dialog used by the browser download prompt."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gio", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from .apps import user_dir
from .files import entry_icon
from .onedrive import existing_sync_dir
from .ui import add_classes, button, fos_confirm, fos_prompt, full_icon, icon, label, load_css

PANEL_HEIGHT = 48
PLACES_WIDTH = 112


@dataclass
class ChooserFilter:
    name: str
    rules: list[tuple[int, str]] = field(default_factory=list)

    @property
    def accepts_all(self) -> bool:
        if not self.rules:
            return True
        for kind, pattern in self.rules:
            if kind == 0 and pattern in ("*", "*.*"):
                return True
        return False


def _places() -> list[tuple[str, str, Path]]:
    home = Path.home()
    rows = [
        ("Home", "user-home-symbolic", home),
    ]
    cloud = existing_sync_dir()
    if cloud is not None:
        rows.append(("OneDrive", "folder-remote-symbolic", cloud))
    rows.extend([
        ("Desktop", "user-desktop-symbolic", user_dir(GLib.UserDirectory.DIRECTORY_DESKTOP, "Desktop")),
        ("Downloads", "folder-download-symbolic", user_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD, "Downloads")),
        ("Documents", "folder-documents-symbolic", user_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS, "Documents")),
        ("Pictures", "folder-pictures-symbolic", user_dir(GLib.UserDirectory.DIRECTORY_PICTURES, "Pictures")),
        ("Music", "folder-music-symbolic", user_dir(GLib.UserDirectory.DIRECTORY_MUSIC, "Music")),
        ("Videos", "folder-videos-symbolic", user_dir(GLib.UserDirectory.DIRECTORY_VIDEOS, "Videos")),
    ])
    seen: set[Path] = set()
    places: list[tuple[str, str, Path]] = []
    for title, icon_name, path in rows:
        try:
            key = path.resolve()
        except OSError:
            key = path
        if key in seen:
            continue
        seen.add(key)
        places.append((title, icon_name, path))
    return places


def _downloads() -> Path:
    path = user_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD, "Downloads")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return Path.home()
    return path


def _matches(path: Path, spec: ChooserFilter | None) -> bool:
    if path.is_dir() or spec is None or spec.accepts_all:
        return True
    name = path.name.lower()
    guessed, _uncertain = Gio.content_type_guess(str(path), None)
    for kind, pattern in spec.rules:
        if kind == 0 and fnmatch.fnmatch(name, pattern.lower()):
            return True
        if kind == 1 and guessed and (guessed == pattern or fnmatch.fnmatch(guessed, pattern)):
            return True
    return False


def _row_icon(path: Path) -> Gtk.Image:
    return full_icon(entry_icon(path, symbolic=False), 16)


def _suffix_for(spec: ChooserFilter | None) -> str | None:
    """Single *.ext pattern, so Save can add the extension the browser asked for."""
    if spec is None or spec.accepts_all:
        return None
    globs = [pattern for kind, pattern in spec.rules if kind == 0]
    if len(globs) != 1 or not globs[0].startswith("*.") or globs[0] in ("*.*", "*"):
        return None
    suffix = globs[0][1:]
    return suffix if suffix.startswith(".") and "/" not in suffix else None


class SaveDialog(Gtk.Window):
    """Folder list plus a file name, centered over the desktop."""

    def __init__(
        self,
        *,
        title: str,
        mode: str,
        folder: Path | None,
        name: str,
        accept_label: str,
        filters: list[ChooserFilter] | None = None,
        multiple: bool = False,
        parent: Gtk.Window | None = None,
        confirm_overwrite: bool = True,
    ) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        load_css()
        self.mode = mode  # save, open, directory
        self.filters = list(filters or [])
        self.current_filter = self.filters[0] if self.filters else None
        self._paths: list[Path] | None = None
        self._loop: GLib.MainLoop | None = None
        self._places = _places()
        self._place_buttons: list[tuple[Path, Gtk.Button]] = []
        start = folder if folder is not None and folder.is_dir() else _downloads()
        self.folder = start
        self._suggested = name
        self._user_picked = False
        self._filling = False
        self._confirm_overwrite = confirm_overwrite

        self.set_title(title)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_decorated(False)
        self.set_resizable(True)
        self.set_modal(True)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        if parent is not None:
            self.set_transient_for(parent)
        add_classes(self, "fos-root", "fos-popup", "fos-dialog", "fos-chooser")
        self._placed = False
        self.connect("delete-event", self._on_delete)
        self.connect("key-press-event", self._on_key)
        self.connect("map", self._on_map)

        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)

        # Slim titlebar like CardWindow. Use begin_move_drag — Openbox ignores
        # plain ConfigureRequest moves on this undecorated dialog.
        header_shell = add_classes(Gtk.EventBox(), "fos-app-header", "fos-chooser-header")
        header_shell.set_visible_window(True)
        header_shell.set_size_request(-1, 30)
        header = add_classes(Gtk.Box(spacing=4), "fos-app-header-inner")
        header.set_valign(Gtk.Align.CENTER)
        header_shell.add(header)
        glyph = icon("document-save-symbolic" if mode == "save" else "folder-symbolic", 14)
        glyph.set_valign(Gtk.Align.CENTER)
        glyph.set_margin_end(8)
        header.pack_start(glyph, False, False, 0)
        title_label = label(title, "fos-title", ellipsize=True)
        title_label.set_valign(Gtk.Align.CENTER)
        title_label.set_hexpand(True)
        header.pack_start(title_label, True, True, 0)
        close = button(icon_name="window-close-symbolic", size="icon-xs", tooltip="Close")
        add_classes(close, "close")
        close.connect("clicked", lambda *_a: self.respond(None))
        captions = add_classes(Gtk.Box(spacing=0), "fos-caption-buttons")
        captions.pack_start(close, False, False, 0)
        header.pack_start(captions, False, False, 0)
        header_shell.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        header_shell.connect("button-press-event", self._on_header_press)
        frame.pack_start(header_shell, False, False, 0)

        body = add_classes(Gtk.Box(spacing=0), "fos-chooser-body")
        body.set_hexpand(True)
        body.set_vexpand(True)
        frame.pack_start(body, True, True, 0)

        places_shell = add_classes(Gtk.Box(), "fos-chooser-places-shell")
        places_shell.set_size_request(PLACES_WIDTH, -1)
        places_shell.set_hexpand(False)
        places_shell.set_vexpand(True)
        places = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0), "fos-chooser-places")
        places.set_hexpand(True)
        places.set_vexpand(True)
        places_shell.pack_start(places, True, True, 0)
        for title_text, icon_name, path in self._places:
            btn = button(title_text, icon_name=icon_name, variant="ghost", size="sm", icon_size=14)
            btn.set_halign(Gtk.Align.FILL)
            btn.set_hexpand(True)
            add_classes(btn, "fos-chooser-place")
            inner = btn.get_child()
            if isinstance(inner, Gtk.Box):
                inner.set_halign(Gtk.Align.START)
                inner.set_spacing(6)
                for child in inner.get_children():
                    if isinstance(child, Gtk.Label):
                        child.set_ellipsize(Pango.EllipsizeMode.END)
                        child.set_max_width_chars(10)
            btn.connect("clicked", lambda _b, target=path: self.go(target))
            places.pack_start(btn, False, False, 0)
            self._place_buttons.append((path, btn))
        body.pack_start(places_shell, False, False, 0)

        main = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0), "fos-chooser-main")
        main.set_hexpand(True)
        main.set_vexpand(True)
        body.pack_start(main, True, True, 0)

        nav = add_classes(Gtk.Box(spacing=4), "fos-chooser-nav")
        nav.set_hexpand(True)
        up = button(icon_name="go-up-symbolic", size="icon-xs", tooltip="Up")
        up.connect("clicked", lambda *_a: self.go_up())
        self.up_btn = up
        nav.pack_start(up, False, False, 0)
        self.path_label = label("", "fos-text", ellipsize=True)
        self.path_label.set_hexpand(True)
        self.path_label.set_halign(Gtk.Align.START)
        self.path_label.set_valign(Gtk.Align.CENTER)
        nav.pack_start(self.path_label, True, True, 0)
        if mode == "save":
            new_folder = button("New folder", icon_name="folder-new-symbolic", variant="outline", size="sm")
            new_folder.connect("clicked", self._new_folder)
            nav.pack_end(new_folder, False, False, 0)
        main.pack_start(nav, False, False, 0)

        scroller = add_classes(Gtk.ScrolledWindow(), "fos-chooser-scroll")
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        scroller.set_shadow_type(Gtk.ShadowType.NONE)
        scroller.set_min_content_height(200)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(
            Gtk.SelectionMode.MULTIPLE if mode == "open" and multiple else Gtk.SelectionMode.SINGLE
        )
        self.listbox.set_hexpand(True)
        self.listbox.set_vexpand(True)
        add_classes(self.listbox, "fos-chooser-list")
        self.listbox.connect("row-activated", self._on_row_activated)
        self.listbox.connect("row-selected", self._on_row_selected)
        self.listbox.connect("button-press-event", self._arm_pick)
        self.listbox.connect("key-press-event", self._arm_pick)
        scroller.add(self.listbox)
        main.pack_start(scroller, True, True, 0)
        self.empty = label("This folder is empty.", "fos-small", "fos-muted")
        self.empty.set_no_show_all(True)
        self.empty.set_margin_start(8)
        self.empty.set_margin_end(8)
        main.pack_start(self.empty, False, False, 0)

        if mode != "directory":
            name_row = add_classes(Gtk.Box(spacing=8), "fos-chooser-name")
            name_row.set_hexpand(True)
            name_lbl = label("File name", "fos-text")
            name_lbl.set_valign(Gtk.Align.CENTER)
            name_row.pack_start(name_lbl, False, False, 0)
            self.entry = add_classes(Gtk.Entry(), "fos-input")
            self.entry.set_hexpand(True)
            self.entry.set_text(name)
            self.entry.set_activates_default(True)
            self.entry.connect("activate", lambda *_a: self.accept())
            name_row.pack_start(self.entry, True, True, 0)
            main.pack_start(name_row, False, False, 0)
            self._select_basename(name)
        else:
            self.entry = None

        self.filter_box = Gtk.ComboBoxText()
        if self.filters and mode != "directory":
            type_row = add_classes(Gtk.Box(spacing=8), "fos-chooser-name")
            type_row.pack_start(label("Save as type" if mode == "save" else "Files of type", "fos-text"), False, False, 0)
            for spec in self.filters:
                self.filter_box.append_text(spec.name)
            self.filter_box.set_active(0)
            self.filter_box.connect("changed", lambda *_a: self._on_filter())
            self.filter_box.set_hexpand(True)
            type_row.pack_start(self.filter_box, True, True, 0)
            main.pack_start(type_row, False, False, 0)

        footer = add_classes(Gtk.Box(spacing=8), "fos-chooser-footer")
        footer.set_halign(Gtk.Align.END)
        frame.pack_start(footer, False, False, 0)
        cancel = button("Cancel", variant="ghost", size="sm")
        cancel.set_can_focus(True)
        cancel.connect("clicked", lambda *_a: self.respond(None))
        footer.pack_start(cancel, False, False, 0)
        save = button(accept_label, variant="default", size="sm")
        save.set_can_focus(True)
        save.set_can_default(True)
        save.connect("clicked", lambda *_a: self.accept())
        footer.pack_start(save, False, False, 0)
        self.save_btn = save

        self.go(self.folder)

    def _on_map(self, *_args) -> None:
        if not self._placed:
            self._place()
            self._placed = True

    def _on_header_press(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button != 1 or event.type != Gdk.EventType.BUTTON_PRESS:
            return False
        window = self.get_window()
        if window is None:
            return False
        Gdk.Window.begin_move_drag(
            window,
            int(event.button),
            int(event.x_root),
            int(event.y_root),
            int(event.time),
        )
        return True

    def _select_basename(self, name: str) -> None:
        if self.entry is None or not name:
            return
        if "." in name and not name.startswith("."):
            self.entry.select_region(0, name.rfind("."))
        else:
            self.entry.select_region(0, -1)

    def _place(self) -> None:
        display = Gdk.Display.get_default()
        if display is None:
            return
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        if monitor is None:
            return
        area = monitor.get_geometry()
        width = min(720, max(560, area.width - 80))
        height = min(480, max(400, area.height - PANEL_HEIGHT - 80))
        self.resize(width, height)
        self.move(
            area.x + max(0, (area.width - width) // 2),
            area.y + max(0, (area.height - PANEL_HEIGHT - height) // 2),
        )

    def go(self, folder: Path) -> None:
        try:
            folder = folder.expanduser().resolve()
        except OSError:
            return
        if not folder.is_dir():
            return
        self.folder = folder
        self.path_label.set_text(str(folder))
        self.up_btn.set_sensitive(folder.parent != folder)
        self._sync_places()
        self._fill()

    def go_up(self) -> None:
        parent = self.folder.parent
        if parent != self.folder:
            self.go(parent)

    def _sync_places(self) -> None:
        try:
            current = self.folder.resolve()
        except OSError:
            current = self.folder
        for path, btn in self._place_buttons:
            try:
                same = path.resolve() == current
            except OSError:
                same = False
            ctx = btn.get_style_context()
            if same:
                ctx.remove_class("ghost")
                ctx.add_class("secondary")
            else:
                ctx.remove_class("secondary")
                ctx.add_class("ghost")

    def _on_filter(self) -> None:
        index = self.filter_box.get_active()
        if 0 <= index < len(self.filters):
            self.current_filter = self.filters[index]
        self._fill()

    def _fill(self) -> None:
        for child in self.listbox.get_children():
            self.listbox.remove(child)
        try:
            entries = [path for path in self.folder.iterdir() if not path.name.startswith(".")]
        except OSError:
            entries = []
        entries = [path for path in entries if _matches(path, self.current_filter)]
        entries.sort(key=lambda path: (not path.is_dir(), path.name.lower()))
        self.empty.set_visible(not entries)
        self._filling = True
        for path in entries:
            row = Gtk.ListBoxRow()
            row.set_hexpand(True)
            box = Gtk.Box(spacing=8)
            box.set_hexpand(True)
            box.set_margin_start(8)
            box.set_margin_end(8)
            box.set_margin_top(3)
            box.set_margin_bottom(3)
            box.pack_start(_row_icon(path), False, False, 0)
            text = label(path.name, "fos-text", ellipsize=True)
            text.set_hexpand(True)
            text.set_halign(Gtk.Align.START)
            box.pack_start(text, True, True, 0)
            row.add(box)
            row.path = path  # type: ignore[attr-defined]
            self.listbox.add(row)
        self.listbox.show_all()
        self.listbox.unselect_all()
        self._filling = False

    def _arm_pick(self, *_args) -> bool:
        self._user_picked = True
        return False

    def _keep_suggested(self) -> bool:
        """List focus selects the first file; that must not replace the download name."""
        if self.entry is None or self._user_picked:
            return False
        self._filling = True
        self.listbox.unselect_all()
        self._filling = False
        if self.entry.get_text() != self._suggested:
            self.entry.set_text(self._suggested)
            self._select_basename(self._suggested)
        return False

    def _on_row_selected(self, _box, row) -> None:
        if self._filling:
            return
        if not self._user_picked:
            if row is not None:
                self._filling = True
                self.listbox.unselect_all()
                self._filling = False
                self._keep_suggested()
            return
        if row is None or self.entry is None or self.mode == "directory":
            return
        path = row.path
        if path.is_file():
            self.entry.set_text(path.name)
            self._select_basename(path.name)

    def _on_row_activated(self, _box, row) -> None:
        path = row.path
        if path.is_dir():
            self.go(path)
            return
        if self.entry is not None:
            self._user_picked = True
            self.entry.set_text(path.name)
        if self.mode in ("open", "save"):
            self.accept()

    def _new_folder(self, *_args) -> None:
        name = fos_prompt(self, "New folder", "Folder name")
        if not name or "/" in name or name in (".", ".."):
            return
        target = self.folder / name
        try:
            target.mkdir(exist_ok=False)
        except OSError:
            return
        self.go(target)

    def _selected_paths(self) -> list[Path]:
        rows = self.listbox.get_selected_rows()
        return [row.path for row in rows]

    def accept(self) -> None:
        if self.mode == "directory":
            selected = [path for path in self._selected_paths() if path.is_dir()]
            self.respond([selected[0]] if selected else [self.folder])
            return
        assert self.entry is not None
        name = self.entry.get_text().strip()
        if not name or "/" in name or name in (".", ".."):
            return
        if self.mode == "save":
            suffix = _suffix_for(self.current_filter)
            if suffix and "." not in Path(name).name:
                name = f"{name}{suffix}"
                self.entry.set_text(name)
        path = self.folder / name
        if path.is_dir():
            self.go(path)
            return
        if self.mode == "open":
            chosen = [item for item in self._selected_paths() if item.is_file()]
            if not chosen and path.is_file():
                chosen = [path]
            if not chosen:
                return
            self.respond(chosen)
            return
        if (
            path.exists()
            and self._confirm_overwrite
            and not fos_confirm(
                self,
                "Replace file?",
                f"“{path.name}” already exists. Replace it?",
                ok="Replace",
                destructive=True,
            )
        ):
            return
        self.respond([path])

    def respond(self, paths: list[Path] | None) -> None:
        self._paths = paths
        self.hide()
        if self._loop is not None and self._loop.is_running():
            self._loop.quit()

    def run(self) -> list[Path] | None:
        self.show_all()
        self.empty.set_visible(not self.listbox.get_children())
        self._place()
        self.present()
        self.save_btn.grab_default()
        if self.entry is not None:
            self.entry.set_text(self._suggested)
            self._select_basename(self._suggested)
            self.entry.grab_focus()
        GLib.idle_add(self._keep_suggested)
        GLib.timeout_add(80, self._keep_suggested)
        self._loop = GLib.MainLoop()
        self._loop.run()
        self._loop = None
        paths = self._paths
        self.destroy()
        return paths

    def _on_delete(self, *_args) -> bool:
        self.respond(None)
        return True

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.respond(None)
            return True
        if event.keyval in (Gdk.KEY_BackSpace, Gdk.KEY_Back) and event.state & Gdk.ModifierType.MOD1_MASK:
            self.go_up()
            return True
        return False


def run_chooser(
    *,
    title: str,
    mode: str,
    folder: Path | None = None,
    name: str = "",
    accept_label: str = "",
    filters: list[ChooserFilter] | None = None,
) -> list[Path] | None:
    if not accept_label:
        accept_label = {"save": "Save", "directory": "Select"}.get(mode, "Open")
    dialog = SaveDialog(
        title=title or ("Save as" if mode == "save" else "Open"),
        mode=mode,
        folder=folder,
        name=name,
        accept_label=accept_label,
        filters=filters,
    )
    return dialog.run()
