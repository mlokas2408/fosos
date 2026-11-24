"""FosOS Notepad: Windows 11–aligned tabbed text / Markdown editor."""

from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from .settings_pages import load_kv, save_kv, truthy
from .ui import (
    add_classes,
    button,
    fos_choice,
    fos_custom,
    fos_file_chooser,
    fos_prompt,
    label,
    load_css,
    set_class,
)
from .windowchrome import CardWindow

APP_ID = "org.fosos.Notepad"
STATE_DIR = Path.home() / ".local/share/fosos-desktop"
SESSION_DIR = STATE_DIR / "notepad-session"
SESSION_FILE = SESSION_DIR / "session.json"
DRAFTS_DIR = SESSION_DIR / "drafts"

MARKDOWN_EXTS = {".md", ".markdown"}
PLAIN_EXTS = {".txt", ".log", ".csv", ".json", ".xml", ".yml", ".yaml", ".ini", ".cfg", ".conf"}

BASE_FONT_PT = 11
DEFAULT_PREFS = {
    "word_wrap": "1",
    "status_bar": "1",
    "font_family": "Liberation Mono",
    "font_size": "11",
    "default_zoom": "0",
}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_UL_RE = re.compile(r"^(\s*)([-*+])\s+", re.MULTILINE)
_OL_RE = re.compile(r"^(\s*)(\d+)\.\s+", re.MULTILINE)


def mode_for_path(path: Path | None, *, force_markdown: bool = False) -> str:
    if force_markdown:
        return "markdown"
    if path is None:
        return "plain"
    return "markdown" if path.suffix.lower() in MARKDOWN_EXTS else "plain"


def load_prefs() -> dict[str, str]:
    return load_kv("notepad", DEFAULT_PREFS)


def save_prefs(prefs: dict[str, str]) -> None:
    save_kv("notepad", prefs)


def _ensure_session_dirs() -> None:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)


def load_session() -> dict:
    _ensure_session_dirs()
    if not SESSION_FILE.is_file():
        return {"tabs": [], "active": 0}
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {"tabs": [], "active": 0}
    if not isinstance(data, dict):
        return {"tabs": [], "active": 0}
    tabs = data.get("tabs")
    if not isinstance(tabs, list):
        tabs = []
    try:
        active = int(data.get("active", 0))
    except (TypeError, ValueError):
        active = 0
    return {"tabs": tabs, "active": active}


def save_session(payload: dict) -> None:
    _ensure_session_dirs()
    try:
        SESSION_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def read_draft(tab_id: str) -> str | None:
    path = DRAFTS_DIR / f"{tab_id}.txt"
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def write_draft(tab_id: str, text: str) -> None:
    _ensure_session_dirs()
    try:
        (DRAFTS_DIR / f"{tab_id}.txt").write_text(text, encoding="utf-8")
    except OSError:
        pass


def remove_draft(tab_id: str) -> None:
    path = DRAFTS_DIR / f"{tab_id}.txt"
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _build_tab_chip(
    title: str,
    *,
    on_focus: Callable[[], None],
    on_close: Callable[[], None],
) -> tuple[Gtk.Box, Gtk.Button, Gtk.Label]:
    chip = add_classes(Gtk.Box(spacing=0), "fos-editor-tab-chip")
    focus_btn = button(variant="ghost", size="sm")
    add_classes(focus_btn, "fos-editor-tab")
    tab_label = label(title, "fos-text", ellipsize=True)
    tab_label.set_width_chars(8)
    tab_label.set_max_width_chars(18)
    focus_btn.add(tab_label)
    focus_btn.connect("clicked", lambda _b: on_focus())
    close = button(icon_name="window-close-symbolic", size="icon-xs", tooltip="Close tab", icon_size=12)
    add_classes(close, "close", "fos-editor-tab-close")
    close.connect("clicked", lambda _b: on_close())
    chip.pack_start(focus_btn, False, False, 0)
    chip.pack_start(close, False, False, 0)
    return chip, focus_btn, tab_label


def _menu_item(text: str, activate: Callable[[], None], *, accel: str | None = None) -> Gtk.MenuItem:
    item = Gtk.MenuItem(label=text)
    if accel:
        item.set_tooltip_text(accel)
    item.connect("activate", lambda _i: activate())
    return item


def _check_item(text: str, active: bool, toggled: Callable[[bool], None]) -> Gtk.CheckMenuItem:
    item = Gtk.CheckMenuItem(label=text)
    item.set_active(active)
    item.connect("toggled", lambda i: toggled(i.get_active()))
    return item


def _detect_eol(text: str) -> str:
    if "\r\n" in text:
        return "crlf"
    return "lf"


def _normalize_newlines(text: str) -> tuple[str, str]:
    eol = _detect_eol(text)
    return text.replace("\r\n", "\n").replace("\r", "\n"), eol


def _apply_eol(text: str, eol: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if eol == "crlf":
        return text.replace("\n", "\r\n")
    return text


def strip_markdown(text: str) -> str:
    text = _BOLD_RE.sub(lambda m: m.group(1) or m.group(2) or "", text)
    text = _ITALIC_RE.sub(lambda m: m.group(1) or m.group(2) or "", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _HEADING_RE.sub(r"\2", text)
    text = _UL_RE.sub(r"\1", text)
    text = _OL_RE.sub(r"\1", text)
    return text


class EditorTab:
    def __init__(
        self,
        window: "EditorWindow",
        *,
        tab_id: str | None = None,
        path: Path | None = None,
        mode: str | None = None,
        md_view: str = "formatted",
        text: str = "",
        eol: str = "lf",
        encoding: str = "UTF-8",
        dirty: bool = False,
    ) -> None:
        self.window = window
        self.tab_id = tab_id or uuid.uuid4().hex
        self.path = path
        self.mode = mode or mode_for_path(path)
        self.md_view = md_view if md_view in ("formatted", "syntax") else "formatted"
        self.eol = eol
        self.encoding = encoding
        self.dirty = dirty
        self._loading = False
        self._style_id: int | None = None
        self._draft_id: int | None = None
        self._undo: list[str] = []
        self._redo: list[str] = []
        self._undo_lock = False

        self.page = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-editor-page")
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        self.view = Gtk.TextView()
        self.view.set_left_margin(14)
        self.view.set_right_margin(14)
        self.view.set_top_margin(12)
        self.view.set_bottom_margin(12)
        self.view.set_accepts_tab(True)
        add_classes(self.view, "fos-editor-view")
        self.buffer = self.view.get_buffer()
        self._ensure_tags()
        self.buffer.connect("changed", self._on_changed)
        self.buffer.connect("mark-set", self._on_mark_set)
        scroller.add(self.view)
        self.page.pack_start(scroller, True, True, 0)

        title = path.name if path is not None else "Untitled"
        self.tab_chip, self.tab_button, self.tab_label = _build_tab_chip(
            title,
            on_focus=lambda: self.window.focus_tab(self),
            on_close=lambda: self.window.close_tab(self),
        )

        self._loading = True
        self.buffer.set_text(text)
        self._loading = False
        self._undo = [text]
        self.apply_wrap(window.word_wrap)
        self.apply_zoom(window.zoom)
        self.refresh_title()
        self.refresh_markdown_style()

    def _ensure_tags(self) -> None:
        table = self.buffer.get_tag_table()
        specs = {
            "md-marker": {"foreground": "#888888", "scale": 0.85},
            "md-h1": {"weight": Pango.Weight.BOLD, "scale": 1.55},
            "md-h2": {"weight": Pango.Weight.BOLD, "scale": 1.35},
            "md-h3": {"weight": Pango.Weight.BOLD, "scale": 1.2},
            "md-h4": {"weight": Pango.Weight.BOLD, "scale": 1.1},
            "md-bold": {"weight": Pango.Weight.BOLD},
            "md-italic": {"style": Pango.Style.ITALIC},
            "md-link": {"foreground": "#6cb6ff", "underline": Pango.Underline.SINGLE},
            "md-list": {"left_margin": 18},
        }
        for name, props in specs.items():
            if table.lookup(name) is None:
                self.buffer.create_tag(name, **props)

    def get_text(self) -> str:
        start, end = self.buffer.get_bounds()
        return self.buffer.get_text(start, end, True)

    def set_text(self, text: str, *, dirty: bool | None = None) -> None:
        self._loading = True
        self.buffer.set_text(text)
        self._loading = False
        if dirty is not None:
            self.dirty = dirty
        self.refresh_title()
        self.refresh_markdown_style()

    def refresh_title(self) -> None:
        name = self.path.name if self.path is not None else "Untitled"
        mark = "* " if self.dirty else ""
        self.tab_label.set_text(f"{mark}{name}")

    def apply_wrap(self, enabled: bool) -> None:
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR if enabled else Gtk.WrapMode.NONE)

    def apply_zoom(self, zoom: int) -> None:
        prefs = self.window.prefs
        family = prefs.get("font_family", DEFAULT_PREFS["font_family"])
        try:
            base = int(prefs.get("font_size", DEFAULT_PREFS["font_size"]))
        except ValueError:
            base = BASE_FONT_PT
        size = max(6, base + zoom)
        # Markdown formatted uses a proportional face; plain/syntax stay mono.
        if self.mode == "markdown" and self.md_view == "formatted":
            desc = Pango.FontDescription.from_string(f"Sans {size}")
        else:
            desc = Pango.FontDescription.from_string(f"{family} {size}")
        self.view.override_font(desc)

    def cursor_line_col(self) -> tuple[int, int]:
        mark = self.buffer.get_insert()
        it = self.buffer.get_iter_at_mark(mark)
        return it.get_line() + 1, it.get_line_offset() + 1

    def _on_changed(self, _buffer) -> None:
        if self._loading or self._undo_lock:
            return
        text = self.get_text()
        if not self._undo or self._undo[-1] != text:
            self._undo.append(text)
            if len(self._undo) > 80:
                self._undo = self._undo[-80:]
            self._redo.clear()
        if not self.dirty:
            self.dirty = True
            self.refresh_title()
            if self.window.active is self:
                self.window._update_chrome()
        self._schedule_style()
        self._schedule_draft()
        if self.window.active is self:
            self.window._update_status()

    def undo(self) -> None:
        if len(self._undo) < 2:
            return
        current = self._undo.pop()
        self._redo.append(current)
        self._undo_lock = True
        self._loading = True
        self.buffer.set_text(self._undo[-1])
        self._loading = False
        self._undo_lock = False
        self.dirty = True
        self.refresh_title()
        self.refresh_markdown_style()

    def redo(self) -> None:
        if not self._redo:
            return
        text = self._redo.pop()
        self._undo.append(text)
        self._undo_lock = True
        self._loading = True
        self.buffer.set_text(text)
        self._loading = False
        self._undo_lock = False
        self.dirty = True
        self.refresh_title()
        self.refresh_markdown_style()

    def _on_mark_set(self, _buffer, _iter, _mark) -> None:
        if self.window.active is self:
            self.window._update_status()

    def _schedule_style(self) -> None:
        if self._style_id is not None:
            GLib.source_remove(self._style_id)
        self._style_id = GLib.timeout_add(120, self._run_style)

    def _run_style(self) -> bool:
        self._style_id = None
        self.refresh_markdown_style()
        return False

    def _schedule_draft(self) -> None:
        if self._draft_id is not None:
            GLib.source_remove(self._draft_id)
        self._draft_id = GLib.timeout_add(400, self._run_draft)

    def _run_draft(self) -> bool:
        self._draft_id = None
        write_draft(self.tab_id, self.get_text())
        self.window.persist_session()
        return False

    def flush_draft(self) -> None:
        if self._draft_id is not None:
            GLib.source_remove(self._draft_id)
            self._draft_id = None
        write_draft(self.tab_id, self.get_text())

    def refresh_markdown_style(self) -> None:
        start, end = self.buffer.get_bounds()
        for name in (
            "md-marker",
            "md-h1",
            "md-h2",
            "md-h3",
            "md-h4",
            "md-bold",
            "md-italic",
            "md-link",
            "md-list",
        ):
            tag = self.buffer.get_tag_table().lookup(name)
            if tag is not None:
                self.buffer.remove_tag(tag, start, end)
        if self.mode != "markdown" or self.md_view != "formatted":
            return
        text = self.get_text()

        def apply_span(tag_name: str, a: int, b: int) -> None:
            if a >= b:
                return
            s = self.buffer.get_iter_at_offset(a)
            e = self.buffer.get_iter_at_offset(b)
            self.buffer.apply_tag_by_name(tag_name, s, e)

        for match in _HEADING_RE.finditer(text):
            hashes, _rest = match.group(1), match.group(2)
            level = min(len(hashes), 4)
            apply_span("md-marker", match.start(1), match.start(0) + len(hashes) + 1)
            apply_span(f"md-h{level}", match.start(2), match.end(2))
        for match in _BOLD_RE.finditer(text):
            apply_span("md-marker", match.start(), match.start() + 2)
            apply_span("md-marker", match.end() - 2, match.end())
            inner = match.group(1) or match.group(2) or ""
            if inner:
                apply_span("md-bold", match.start() + 2, match.end() - 2)
        for match in _ITALIC_RE.finditer(text):
            # Skip spans already claimed by bold (**...**)
            if text[match.start() : match.end()].startswith("**"):
                continue
            apply_span("md-marker", match.start(), match.start() + 1)
            apply_span("md-marker", match.end() - 1, match.end())
            apply_span("md-italic", match.start() + 1, match.end() - 1)
        for match in _LINK_RE.finditer(text):
            apply_span("md-marker", match.start(), match.start(1))
            apply_span("md-link", match.start(1), match.end(1))
            apply_span("md-marker", match.end(1), match.end())
        for match in _UL_RE.finditer(text):
            apply_span("md-marker", match.start(2), match.end(2))
            apply_span("md-list", match.start(), match.end())
        for match in _OL_RE.finditer(text):
            apply_span("md-marker", match.start(2), match.end())
            apply_span("md-list", match.start(), match.end())

    def session_entry(self) -> dict:
        return {
            "id": self.tab_id,
            "path": str(self.path) if self.path is not None else None,
            "mode": self.mode,
            "md_view": self.md_view,
            "eol": self.eol,
            "encoding": self.encoding,
            "dirty": self.dirty,
        }

    def destroy(self) -> None:
        if self._style_id is not None:
            GLib.source_remove(self._style_id)
            self._style_id = None
        if self._draft_id is not None:
            GLib.source_remove(self._draft_id)
            self._draft_id = None


class EditorWindow(CardWindow):
    def __init__(
        self,
        app: "EditorApp",
        *,
        restore: bool = True,
        open_paths: list[Path] | None = None,
    ) -> None:
        super().__init__(
            app,
            title="Notepad",
            icon_name="accessories-text-editor-symbolic",
            default_width=820,
            default_height=560,
        )
        self.app = app
        self.prefs = load_prefs()
        self.tabs: list[EditorTab] = []
        self.active: EditorTab | None = None
        self.word_wrap = truthy(self.prefs.get("word_wrap"), True)
        self.show_status = truthy(self.prefs.get("status_bar"), True)
        try:
            self.zoom = int(self.prefs.get("default_zoom", "0"))
        except ValueError:
            self.zoom = 0
        self._find_text = ""
        self._replace_text = ""
        self._persist_id: int | None = None
        self._md_menu_items: list[Gtk.MenuItem] = []
        self._wrap_item: Gtk.CheckMenuItem | None = None
        self._status_item: Gtk.CheckMenuItem | None = None

        # Titlebar tabs
        self.tab_strip = add_classes(Gtk.Box(spacing=2), "fos-editor-tabs")
        self.tab_strip.set_valign(Gtk.Align.CENTER)
        self.tab_strip.set_hexpand(True)
        self.add_tab_btn = button(
            icon_name="list-add-symbolic",
            size="icon-xs",
            tooltip="New tab (Ctrl+T)",
            icon_size=14,
        )
        self.add_tab_btn.connect("clicked", lambda _b: self.new_tab())
        self.set_header_center(self.tab_strip)

        # Menubar
        self.menubar = self._build_menubar()
        add_classes(self.menubar, "fos-editor-menubar")
        self.body.pack_start(self.menubar, False, False, 0)

        # Formatting toolbar (Markdown only)
        self.fmt_bar = add_classes(Gtk.Box(spacing=4), "fos-app-toolbar", "fos-editor-fmtbar")
        self._style_combo = Gtk.ComboBoxText()
        for key, title in (("text", "Text"), ("h1", "Heading 1"), ("h2", "Heading 2"), ("h3", "Heading 3")):
            self._style_combo.append(key, title)
        self._style_combo.set_active_id("text")
        self._style_combo.connect("changed", self._on_style_changed)
        add_classes(self._style_combo, "fos-editor-style")
        self.fmt_bar.pack_start(self._style_combo, False, False, 0)
        for text, handler, tip in (
            ("B", lambda: self.md_wrap("**"), "Bold (Ctrl+B)"),
            ("I", lambda: self.md_wrap("*"), "Italic (Ctrl+I)"),
            ("Link", self.md_link, "Insert link"),
            ("• List", lambda: self.md_list(False), "Bulleted list"),
            ("1. List", lambda: self.md_list(True), "Numbered list"),
            ("Clear", self.md_clear_formatting, "Clear formatting"),
        ):
            btn = button(text, variant="ghost", size="sm", tooltip=tip)
            btn.connect("clicked", lambda _b, h=handler: h())
            self.fmt_bar.pack_start(btn, False, False, 0)
        self.body.pack_start(self.fmt_bar, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        add_classes(self.stack, "fos-editor-body")
        self.body.pack_start(self.stack, True, True, 0)

        self.footer = add_classes(Gtk.Box(spacing=10), "fos-app-footer", "fos-editor-footer")
        self.status_pos = label("Ln 1, Col 1", "fos-small", "fos-muted")
        self.status_zoom = label("100%", "fos-small", "fos-muted")
        self.status_eol = label("Unix (LF)", "fos-small", "fos-muted")
        self.status_enc = label("UTF-8", "fos-small", "fos-muted")
        self.status_mode = button("Plain", variant="ghost", size="sm", tooltip="Toggle Markdown view")
        self.status_mode.connect("clicked", lambda _b: self.toggle_md_view())
        self.footer.pack_start(self.status_pos, False, False, 0)
        self.footer.pack_end(self.status_mode, False, False, 0)
        self.footer.pack_end(self.status_enc, False, False, 0)
        self.footer.pack_end(self.status_eol, False, False, 0)
        self.footer.pack_end(self.status_zoom, False, False, 0)
        self.body.pack_start(self.footer, False, False, 0)

        self.connect("key-press-event", self._on_key)
        self.connect("delete-event", self._on_delete)

        if restore:
            self._restore_session()
        focus_from_cli: EditorTab | None = None
        if open_paths:
            for path in open_paths:
                if path.is_file():
                    focus_from_cli = self.open_path(path, focus=False) or focus_from_cli
        if not self.tabs:
            self.new_tab()
        if focus_from_cli is not None:
            self.focus_tab(focus_from_cli)
        self._update_chrome()

    def _build_menubar(self) -> Gtk.MenuBar:
        bar = Gtk.MenuBar()

        file_menu = Gtk.Menu()
        file_root = Gtk.MenuItem(label="File")
        file_root.set_submenu(file_menu)
        for text, handler, accel in (
            ("New tab", self.new_tab, "Ctrl+T"),
            ("New Markdown tab", self.new_markdown_tab, "Ctrl+Shift+N"),
            ("New window", self.new_window, "Ctrl+Shift+T"),
            ("Open...", self.open_file, "Ctrl+O"),
            ("Save", lambda: self.save_file(), "Ctrl+S"),
            ("Save as...", lambda: self.save_file_as(), "Ctrl+Shift+S"),
            ("Close tab", lambda: self.close_tab(self.active) if self.active else None, "Ctrl+W"),
            ("Exit", self.close, "Alt+F4"),
        ):
            file_menu.append(_menu_item(text, handler, accel=accel))
            if text in ("New window", "Save as...", "Close tab"):
                file_menu.append(Gtk.SeparatorMenuItem())
        bar.append(file_root)

        edit_menu = Gtk.Menu()
        edit_root = Gtk.MenuItem(label="Edit")
        edit_root.set_submenu(edit_menu)
        for text, handler, accel in (
            ("Undo", self.undo, "Ctrl+Z"),
            ("Redo", self.redo, "Ctrl+Y"),
            ("Cut", self.cut, "Ctrl+X"),
            ("Copy", self.copy, "Ctrl+C"),
            ("Paste", self.paste, "Ctrl+V"),
            ("Find...", self.find, "Ctrl+F"),
            ("Replace...", self.replace, "Ctrl+H"),
            ("Go to line...", self.goto_line, "Ctrl+G"),
            ("Select all", self.select_all, "Ctrl+A"),
            ("Bold", lambda: self.md_wrap("**"), "Ctrl+B"),
            ("Italic", lambda: self.md_wrap("*"), "Ctrl+I"),
            ("Clear formatting", self.md_clear_formatting, None),
        ):
            item = _menu_item(text, handler, accel=accel)
            if text in ("Bold", "Italic", "Clear formatting"):
                self._md_menu_items.append(item)
            edit_menu.append(item)
            if text in ("Redo", "Paste", "Go to line...", "Select all"):
                edit_menu.append(Gtk.SeparatorMenuItem())
        bar.append(edit_root)

        view_menu = Gtk.Menu()
        view_root = Gtk.MenuItem(label="View")
        view_root.set_submenu(view_menu)
        view_menu.append(_menu_item("Zoom in", lambda: self.set_zoom(self.zoom + 1), accel="Ctrl++"))
        view_menu.append(_menu_item("Zoom out", lambda: self.set_zoom(self.zoom - 1), accel="Ctrl+-"))
        view_menu.append(_menu_item("Reset zoom", lambda: self.set_zoom(0), accel="Ctrl+0"))
        view_menu.append(Gtk.SeparatorMenuItem())
        self._wrap_item = _check_item("Word wrap", self.word_wrap, self.set_word_wrap)
        view_menu.append(self._wrap_item)
        self._status_item = _check_item("Status bar", self.show_status, self.set_status_visible)
        view_menu.append(self._status_item)
        view_menu.append(Gtk.SeparatorMenuItem())
        md_root = Gtk.MenuItem(label="Markdown")
        md_sub = Gtk.Menu()
        md_root.set_submenu(md_sub)
        for text, view in (("Formatted", "formatted"), ("Syntax", "syntax")):
            item = _menu_item(text, lambda v=view: self.set_md_view(v))
            self._md_menu_items.append(item)
            md_sub.append(item)
        self._md_menu_items.append(md_root)
        view_menu.append(md_root)
        bar.append(view_root)
        return bar

    # --- tabs ------------------------------------------------------------------

    def new_tab(self, *, mode: str = "plain", path: Path | None = None, text: str = "", **kwargs) -> EditorTab:
        tab = EditorTab(self, path=path, mode=mode, text=text, **kwargs)
        self.tabs.append(tab)
        tab.page.show_all()
        self.stack.add_named(tab.page, tab.tab_id)
        self._rebuild_tabs()
        self.focus_tab(tab)
        self.persist_session(debounce=True)
        return tab

    def new_markdown_tab(self) -> EditorTab:
        return self.new_tab(mode="markdown", md_view="formatted")

    def new_window(self) -> None:
        self.app.open_new_window(restore=False)

    def focus_tab(self, tab: EditorTab) -> None:
        if tab not in self.tabs:
            return
        self.active = tab
        tab.page.show_all()
        self.stack.set_visible_child(tab.page)
        for other in self.tabs:
            set_class(other.tab_button, "secondary", other is tab)
            set_class(other.tab_button, "ghost", other is not tab)
        tab.view.grab_focus()
        self._update_chrome()

    def close_tab(self, tab: EditorTab | None) -> None:
        if tab is None or tab not in self.tabs:
            return
        # Dirty file on disk: confirm. Untitled drafts drop silently (session).
        if tab.dirty and tab.path is not None:
            response = fos_choice(
                self,
                "Save changes?",
                f"Do you want to save changes to {tab.path.name}?",
                [
                    ("Cancel", "cancel", "ghost"),
                    ("Don't save", "discard", "ghost"),
                    ("Save", "save", "default"),
                ],
            )
            if response == "cancel" or response is None:
                return
            if response == "save" and not self.save_file(tab):
                return
        index = self.tabs.index(tab)
        self.tabs.remove(tab)
        self.stack.remove(tab.page)
        tab.flush_draft()
        remove_draft(tab.tab_id)
        tab.destroy()
        tab.page.destroy()
        if not self.tabs:
            self.persist_session()
            self.close()
            return
        next_tab = self.tabs[min(index, len(self.tabs) - 1)]
        self._rebuild_tabs()
        self.focus_tab(next_tab)
        self.persist_session()

    def _rebuild_tabs(self) -> None:
        for child in list(self.tab_strip.get_children()):
            self.tab_strip.remove(child)
        for tab in self.tabs:
            self.tab_strip.pack_start(tab.tab_chip, False, False, 0)
        self.tab_strip.pack_start(self.add_tab_btn, False, False, 0)
        filler = add_classes(Gtk.EventBox(), "fos-editor-drag")
        filler.set_hexpand(True)
        filler.set_visible_window(True)
        filler.set_above_child(False)
        filler.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.BUTTON1_MOTION_MASK
        )
        filler.connect("button-press-event", self._on_drag_filler_press)
        self.tab_strip.pack_start(filler, True, True, 0)
        self.tab_strip.show_all()

    def _on_drag_filler_press(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button == 3:
            self._popup_title_menu(event)
            return True
        return self.begin_titlebar_move(event)

    # --- open / save -----------------------------------------------------------

    def open_file(self) -> None:
        filt = Gtk.FileFilter()
        filt.set_name("Text files")
        filt.add_mime_type("text/plain")
        filt.add_pattern("*.txt")
        filt.add_pattern("*.md")
        filt.add_pattern("*.markdown")
        filt.add_pattern("*.log")
        filt.add_pattern("*.csv")
        all_filt = Gtk.FileFilter()
        all_filt.set_name("All files")
        all_filt.add_pattern("*")
        filename = fos_file_chooser(
            self,
            title="Open",
            action=Gtk.FileChooserAction.OPEN,
            ok_label="Open",
            filters=[filt, all_filt],
        )
        if filename:
            self.open_path(Path(filename), focus=True)

    def open_path(self, path: Path, *, focus: bool = True) -> EditorTab | None:
        path = path.expanduser().resolve()
        for tab in self.tabs:
            if tab.path is not None and tab.path.resolve() == path:
                if focus:
                    self.focus_tab(tab)
                return tab
        try:
            raw = path.read_bytes()
        except OSError as exc:
            if self.active:
                self.status_pos.set_text(f"Could not open: {exc}")
            return None
        text: str
        encoding = "UTF-8"
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
            encoding = "Latin-1"
        text, eol = _normalize_newlines(text)
        tab = self.new_tab(
            path=path,
            mode=mode_for_path(path),
            text=text,
            eol=eol,
            encoding=encoding,
            dirty=False,
            md_view="formatted",
        )
        tab.dirty = False
        tab.refresh_title()
        write_draft(tab.tab_id, text)
        if focus:
            self.focus_tab(tab)
        return tab

    def save_file(self, tab: EditorTab | None = None) -> bool:
        tab = tab or self.active
        if tab is None:
            return False
        if tab.path is None:
            return self.save_file_as(tab)
        return self._write_tab(tab, tab.path)

    def save_file_as(self, tab: EditorTab | None = None) -> bool:
        tab = tab or self.active
        if tab is None:
            return False
        default_name = "Untitled.md" if tab.mode == "markdown" else "Untitled.txt"
        filename = fos_file_chooser(
            self,
            title="Save as",
            action=Gtk.FileChooserAction.SAVE,
            ok_label="Save",
            filename=str(tab.path) if tab.path is not None else None,
            current_name=default_name if tab.path is None else None,
            overwrite_confirmation=True,
        )
        if not filename:
            return False
        return self._write_tab(tab, Path(filename))

    def _write_tab(self, tab: EditorTab, path: Path) -> bool:
        text = tab.get_text()
        new_mode = mode_for_path(path)
        if tab.mode == "markdown" and new_mode == "plain":
            response = fos_choice(
                self,
                "Save as plain text?",
                "Saving as a plain text file will clear Markdown formatting.",
                [
                    ("Cancel", "cancel", "ghost"),
                    ("Save plain", "plain", "default"),
                ],
            )
            if response != "plain":
                return False
            text = strip_markdown(text)
            tab.mode = "plain"
            tab.md_view = "syntax"
        elif new_mode == "markdown":
            tab.mode = "markdown"
            if tab.md_view not in ("formatted", "syntax"):
                tab.md_view = "formatted"
        try:
            path.write_bytes(_apply_eol(text, tab.eol).encode("utf-8"))
        except OSError as exc:
            self.status_pos.set_text(f"Could not save: {exc}")
            return False
        tab.path = path
        tab.encoding = "UTF-8"
        tab.dirty = False
        if tab.mode == "plain":
            tab.set_text(text, dirty=False)
        else:
            tab.refresh_title()
            tab.refresh_markdown_style()
            tab.apply_zoom(self.zoom)
        write_draft(tab.tab_id, tab.get_text())
        self._update_chrome()
        self.persist_session()
        return True

    # --- edit actions ----------------------------------------------------------

    def undo(self) -> None:
        if self.active:
            self.active.undo()
            self._update_chrome()

    def redo(self) -> None:
        if self.active:
            self.active.redo()
            self._update_chrome()

    def cut(self) -> None:
        if self.active:
            self.active.buffer.cut_clipboard(Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD), True)

    def copy(self) -> None:
        if self.active:
            self.active.buffer.copy_clipboard(Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD))

    def paste(self) -> None:
        if self.active:
            self.active.buffer.paste_clipboard(Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD), None, True)

    def select_all(self) -> None:
        if not self.active:
            return
        bounds = self.active.buffer.get_bounds()
        self.active.buffer.select_range(bounds[0], bounds[1])

    def find(self) -> None:
        self._find_replace_dialog(replace=False)

    def replace(self) -> None:
        self._find_replace_dialog(replace=True)

    def _find_replace_dialog(self, *, replace: bool) -> None:
        if self.active is None:
            return

        def build(dialog) -> None:
            dialog.content.pack_start(label("Find", "fos-text"), False, False, 0)
            find_entry = add_classes(Gtk.Entry(), "fos-input")
            find_entry.set_text(self._find_text)
            dialog.content.pack_start(find_entry, False, False, 0)
            replace_entry = None
            if replace:
                dialog.content.pack_start(label("Replace with", "fos-text"), False, False, 0)
                replace_entry = add_classes(Gtk.Entry(), "fos-input")
                replace_entry.set_text(self._replace_text)
                dialog.content.pack_start(replace_entry, False, False, 0)

            def do_find(_w=None) -> None:
                self._find_text = find_entry.get_text()
                if not self._find_next(self._find_text):
                    self.status_pos.set_text("Not found")

            def do_replace(_w=None) -> None:
                assert replace_entry is not None
                self._find_text = find_entry.get_text()
                self._replace_text = replace_entry.get_text()
                self._replace_selection(self._replace_text)
                self._find_next(self._find_text)

            def do_replace_all(_w=None) -> None:
                assert replace_entry is not None
                self._find_text = find_entry.get_text()
                self._replace_text = replace_entry.get_text()
                count = self._replace_all(self._find_text, self._replace_text)
                self.status_pos.set_text(f"Replaced {count}")
                dialog.respond(True)

            dialog.add_action("Close", False, variant="ghost")
            if replace:
                btn_all = button("Replace all", variant="ghost", size="sm")
                btn_all.connect("clicked", do_replace_all)
                dialog.footer.pack_start(btn_all, False, False, 0)
                btn_rep = button("Replace", variant="ghost", size="sm")
                btn_rep.connect("clicked", do_replace)
                dialog.footer.pack_start(btn_rep, False, False, 0)
            btn_find = button("Find next", variant="default", size="sm")
            btn_find.connect("clicked", do_find)
            dialog.footer.pack_start(btn_find, False, False, 0)
            find_entry.connect("activate", do_find)
            GLib.idle_add(find_entry.grab_focus)

        fos_custom(self, "Replace" if replace else "Find", build, width=420)

    def _find_next(self, needle: str) -> bool:
        if not self.active or not needle:
            return False
        buf = self.active.buffer
        insert = buf.get_iter_at_mark(buf.get_insert())
        found = insert.forward_search(needle, Gtk.TextSearchFlags.CASE_INSENSITIVE, None)
        if found is None:
            start = buf.get_start_iter()
            found = start.forward_search(needle, Gtk.TextSearchFlags.CASE_INSENSITIVE, None)
        if found is None:
            return False
        match_start, match_end = found
        buf.select_range(match_start, match_end)
        self.active.view.scroll_to_iter(match_start, 0.2, False, 0, 0)
        return True

    def _replace_selection(self, replacement: str) -> None:
        if not self.active:
            return
        buf = self.active.buffer
        bounds = buf.get_selection_bounds()
        if not bounds:
            return
        buf.delete(bounds[0], bounds[1])
        buf.insert_at_cursor(replacement)

    def _replace_all(self, needle: str, replacement: str) -> int:
        if not self.active or not needle:
            return 0
        text = self.active.get_text()
        count = text.count(needle)
        if count:
            self.active.set_text(text.replace(needle, replacement), dirty=True)
            self.active.dirty = True
            self.active.refresh_title()
        return count

    def goto_line(self) -> None:
        if self.active is None:
            return
        line_s = fos_prompt(self, "Go to line", "Line number", "1")
        if not line_s:
            return
        try:
            line = max(1, int(line_s))
        except ValueError:
            return
        buf = self.active.buffer
        it = buf.get_iter_at_line(min(line, buf.get_line_count()) - 1)
        buf.place_cursor(it)
        self.active.view.scroll_to_iter(it, 0.2, True, 0, 0.3)
        self._update_status()

    # --- markdown formatting ---------------------------------------------------

    def md_wrap(self, marker: str) -> None:
        tab = self.active
        if tab is None or tab.mode != "markdown":
            return
        buf = tab.buffer
        bounds = buf.get_selection_bounds()
        if bounds:
            start, end = bounds
            selected = buf.get_text(start, end, True)
            buf.delete(start, end)
            buf.insert_at_cursor(f"{marker}{selected}{marker}")
        else:
            insert = buf.get_iter_at_mark(buf.get_insert())
            pos = insert.get_offset()
            buf.insert_at_cursor(f"{marker}{marker}")
            new_it = buf.get_iter_at_offset(pos + len(marker))
            buf.place_cursor(new_it)
        tab.view.grab_focus()

    def md_link(self) -> None:
        tab = self.active
        if tab is None or tab.mode != "markdown":
            return
        url = fos_prompt(self, "Insert link", "URL", "https://")
        if not url:
            return
        buf = tab.buffer
        bounds = buf.get_selection_bounds()
        text = buf.get_text(bounds[0], bounds[1], True) if bounds else "link"
        if bounds:
            buf.delete(bounds[0], bounds[1])
        buf.insert_at_cursor(f"[{text}]({url})")

    def md_list(self, numbered: bool) -> None:
        tab = self.active
        if tab is None or tab.mode != "markdown":
            return
        buf = tab.buffer
        insert = buf.get_iter_at_mark(buf.get_insert())
        line_start = insert.copy()
        line_start.set_line_offset(0)
        prefix = "1. " if numbered else "- "
        buf.insert(line_start, prefix)

    def md_clear_formatting(self) -> None:
        tab = self.active
        if tab is None or tab.mode != "markdown":
            return
        buf = tab.buffer
        bounds = buf.get_selection_bounds()
        if bounds:
            start, end = bounds
            selected = buf.get_text(start, end, True)
            buf.delete(start, end)
            buf.insert_at_cursor(strip_markdown(selected))
        else:
            tab.set_text(strip_markdown(tab.get_text()), dirty=True)
            tab.dirty = True
            tab.refresh_title()

    def _on_style_changed(self, combo: Gtk.ComboBoxText) -> None:
        tab = self.active
        if tab is None or tab.mode != "markdown":
            return
        style = combo.get_active_id() or "text"
        buf = tab.buffer
        insert = buf.get_iter_at_mark(buf.get_insert())
        line_start = insert.copy()
        line_start.set_line_offset(0)
        line_end = insert.copy()
        if not line_end.ends_line():
            line_end.forward_to_line_end()
        line = buf.get_text(line_start, line_end, True)
        stripped = _HEADING_RE.sub(r"\2", line) if line.lstrip().startswith("#") else line
        if style == "h1":
            new = f"# {stripped.lstrip()}"
        elif style == "h2":
            new = f"## {stripped.lstrip()}"
        elif style == "h3":
            new = f"### {stripped.lstrip()}"
        else:
            new = stripped.lstrip() if stripped.lstrip().startswith("#") else stripped
            new = _HEADING_RE.sub(r"\2", line) if line.lstrip().startswith("#") else stripped
        buf.delete(line_start, line_end)
        buf.insert(line_start, new)

    def set_md_view(self, view: str) -> None:
        tab = self.active
        if tab is None or tab.mode != "markdown":
            return
        tab.md_view = view
        tab.apply_zoom(self.zoom)
        tab.refresh_markdown_style()
        self._update_chrome()
        self.persist_session(debounce=True)

    def toggle_md_view(self) -> None:
        tab = self.active
        if tab is None or tab.mode != "markdown":
            return
        self.set_md_view("syntax" if tab.md_view == "formatted" else "formatted")

    # --- view / prefs ----------------------------------------------------------

    def set_word_wrap(self, enabled: bool) -> None:
        self.word_wrap = enabled
        self.prefs["word_wrap"] = "1" if enabled else "0"
        save_prefs(self.prefs)
        for tab in self.tabs:
            tab.apply_wrap(enabled)
        if self._wrap_item is not None and self._wrap_item.get_active() != enabled:
            self._wrap_item.set_active(enabled)

    def set_status_visible(self, enabled: bool) -> None:
        self.show_status = enabled
        self.prefs["status_bar"] = "1" if enabled else "0"
        save_prefs(self.prefs)
        self.footer.set_visible(enabled)
        if self._status_item is not None and self._status_item.get_active() != enabled:
            self._status_item.set_active(enabled)

    def set_zoom(self, zoom: int) -> None:
        self.zoom = max(-6, min(12, zoom))
        self.prefs["default_zoom"] = str(self.zoom)
        save_prefs(self.prefs)
        for tab in self.tabs:
            tab.apply_zoom(self.zoom)
        self._update_status()

    def _update_chrome(self) -> None:
        tab = self.active
        if tab is None:
            self.set_header_title("Notepad")
            self.fmt_bar.hide()
            return
        name = tab.path.name if tab.path is not None else "Untitled"
        mark = "* " if tab.dirty else ""
        self.set_header_title(f"{mark}{name} - Notepad")
        self.set_badge(tab.path.parent.name if tab.path is not None else None)
        tab.refresh_title()
        is_md = tab.mode == "markdown"
        self.fmt_bar.set_visible(is_md)
        for item in self._md_menu_items:
            item.set_sensitive(is_md)
        self.status_mode.set_visible(is_md)
        self.footer.set_visible(self.show_status)
        self._update_status()

    def _update_status(self) -> None:
        tab = self.active
        if tab is None:
            return
        ln, col = tab.cursor_line_col()
        self.status_pos.set_text(f"Ln {ln}, Col {col}")
        self.status_zoom.set_text(f"{100 + self.zoom * 10}%")
        self.status_eol.set_text("Windows (CRLF)" if tab.eol == "crlf" else "Unix (LF)")
        self.status_enc.set_text(tab.encoding)
        if tab.mode == "markdown":
            # Refresh button label child
            for child in list(self.status_mode.get_children()):
                self.status_mode.remove(child)
                child.destroy()
            self.status_mode.add(
                label("Formatted" if tab.md_view == "formatted" else "Syntax", "fos-small")
            )
            self.status_mode.show_all()
        else:
            for child in list(self.status_mode.get_children()):
                self.status_mode.remove(child)
                child.destroy()
            self.status_mode.add(label("Plain", "fos-small"))
            self.status_mode.show_all()

    # --- session ---------------------------------------------------------------

    def persist_session(self, *, debounce: bool = False) -> None:
        if debounce:
            if self._persist_id is not None:
                GLib.source_remove(self._persist_id)
            self._persist_id = GLib.timeout_add(500, self._persist_now)
            return
        self._persist_now()

    def _persist_now(self) -> bool:
        self._persist_id = None
        # Only the primary window owns the shared session file.
        if self is not self.app.primary_window():
            return False
        tabs_payload = []
        active_index = 0
        for index, tab in enumerate(self.tabs):
            tab.flush_draft()
            tabs_payload.append(tab.session_entry())
            if tab is self.active:
                active_index = index
        save_session({"tabs": tabs_payload, "active": active_index})
        # Drop orphan drafts
        keep = {t.tab_id for t in self.tabs}
        if DRAFTS_DIR.is_dir():
            for path in DRAFTS_DIR.glob("*.txt"):
                if path.stem not in keep:
                    try:
                        path.unlink()
                    except OSError:
                        pass
        return False

    def _restore_session(self) -> None:
        data = load_session()
        tabs = data.get("tabs") or []
        active = int(data.get("active") or 0)
        restored: list[EditorTab] = []
        for entry in tabs:
            if not isinstance(entry, dict):
                continue
            tab_id = str(entry.get("id") or uuid.uuid4().hex)
            path_s = entry.get("path")
            path = Path(path_s) if path_s else None
            if path is not None and not path.is_file():
                # Keep path for title if draft exists; else drop missing files.
                if read_draft(tab_id) is None:
                    path = None
            draft = read_draft(tab_id)
            eol = str(entry.get("eol") or "lf")
            encoding = str(entry.get("encoding") or "UTF-8")
            dirty = bool(entry.get("dirty"))
            if draft is not None:
                text = draft
            elif path is not None and path.is_file():
                try:
                    raw = path.read_text(encoding="utf-8")
                    text, eol = _normalize_newlines(raw)
                    encoding = "UTF-8"
                    dirty = False
                except UnicodeDecodeError:
                    try:
                        raw = path.read_text(encoding="latin-1")
                        text, eol = _normalize_newlines(raw)
                        encoding = "Latin-1"
                        dirty = False
                    except OSError:
                        text = ""
                except OSError:
                    text = ""
            else:
                text = ""
            mode = mode_for_path(path, force_markdown=str(entry.get("mode")) == "markdown" and path is None)
            if path is not None:
                mode = mode_for_path(path)
            elif str(entry.get("mode")) == "markdown":
                mode = "markdown"
            tab = self.new_tab(
                tab_id=tab_id,
                path=path,
                mode=mode,
                md_view=str(entry.get("md_view") or "formatted"),
                text=text,
                eol=eol,
                encoding=encoding,
            )
            tab.dirty = dirty
            tab.refresh_title()
            restored.append(tab)
        if restored:
            index = max(0, min(active, len(restored) - 1))
            self.focus_tab(restored[index])

    def _on_delete(self, _window, _event) -> bool:
        for tab in self.tabs:
            tab.flush_draft()
        self.persist_session()
        return False

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        key = (Gdk.keyval_name(event.keyval) or "").lower()
        if ctrl and not shift and key == "t":
            self.new_tab()
            return True
        if ctrl and shift and key == "n":
            self.new_markdown_tab()
            return True
        if ctrl and shift and key == "t":
            self.new_window()
            return True
        if ctrl and not shift and key == "o":
            self.open_file()
            return True
        if ctrl and shift and key == "s":
            self.save_file_as()
            return True
        if ctrl and not shift and key == "s":
            self.save_file()
            return True
        if ctrl and not shift and key == "w":
            self.close_tab(self.active)
            return True
        if ctrl and not shift and key == "z":
            self.undo()
            return True
        if (ctrl and not shift and key == "y") or (ctrl and shift and key == "z"):
            self.redo()
            return True
        if ctrl and not shift and key == "f":
            self.find()
            return True
        if ctrl and not shift and key == "h":
            self.replace()
            return True
        if ctrl and not shift and key == "g":
            self.goto_line()
            return True
        if ctrl and not shift and key == "b":
            self.md_wrap("**")
            return True
        if ctrl and not shift and key == "i":
            self.md_wrap("*")
            return True
        if ctrl and (key in ("plus", "equal", "kp_add")):
            self.set_zoom(self.zoom + 1)
            return True
        if ctrl and (key in ("minus", "kp_subtract")):
            self.set_zoom(self.zoom - 1)
            return True
        if ctrl and key in ("0", "kp_0"):
            self.set_zoom(0)
            return True
        if ctrl and not shift and key == "tab":
            self._cycle_tab(1)
            return True
        if ctrl and shift and key == "tab":
            self._cycle_tab(-1)
            return True
        if ctrl and key.isdigit() and key != "0":
            index = int(key) - 1
            if 0 <= index < len(self.tabs):
                self.focus_tab(self.tabs[index])
                return True
        return False

    def _cycle_tab(self, delta: int) -> None:
        if not self.tabs or self.active is None:
            return
        index = self.tabs.index(self.active)
        self.focus_tab(self.tabs[(index + delta) % len(self.tabs)])


class EditorApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_OPEN | Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.windows: list[EditorWindow] = []
        self._pending_paths: list[Path] = []
        self._did_restore = False

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_prgname("fosos-notepad")
        GLib.set_application_name("Notepad")
        load_css()

    def do_activate(self) -> None:
        if not self.windows:
            paths = self._pending_paths
            self._pending_paths = []
            win = EditorWindow(self, restore=True, open_paths=paths or None)
            self.windows.append(win)
            win.connect("destroy", self._on_window_destroy)
            win.show_all()
            win._update_chrome()
            self._did_restore = True
        self.windows[0].present()

    def do_open(self, files, _n_files, _hint) -> None:
        paths = []
        for f in files:
            candidate = Path(f.get_path() or "")
            if candidate.is_file():
                paths.append(candidate)
        if not self.windows:
            self._pending_paths = paths
            self.do_activate()
            return
        win = self.windows[0]
        for path in paths:
            win.open_path(path, focus=True)
        win.present()

    def do_command_line(self, command_line):
        argv = command_line.get_arguments()[1:]
        paths = []
        for arg in argv:
            candidate = Path(arg).expanduser()
            if candidate.is_file():
                paths.append(candidate)
        if paths:
            if not self.windows:
                self._pending_paths = paths
                self.do_activate()
            else:
                for path in paths:
                    self.windows[0].open_path(path, focus=True)
                self.windows[0].present()
        else:
            self.do_activate()
        return 0

    def open_new_window(self, *, restore: bool = False) -> EditorWindow:
        win = EditorWindow(self, restore=restore)
        self.windows.append(win)
        win.connect("destroy", self._on_window_destroy)
        win.show_all()
        win._update_chrome()
        win.present()
        return win

    def primary_window(self) -> EditorWindow | None:
        return self.windows[0] if self.windows else None

    def _on_window_destroy(self, window: EditorWindow) -> None:
        if window in self.windows:
            self.windows.remove(window)


def main() -> int:
    return EditorApp().run(sys.argv)
