"""The desktop: drawn wallpaper, the faint FosOS brand and desktop icons."""

from __future__ import annotations

import datetime
import shutil
from functools import lru_cache
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango, PangoCairo

from . import apps as appmod
from .files import entry_icon, format_size
from .panel import HEIGHT as PANEL_HEIGHT
from .ui import (
    BRAND,
    DATA_DIR,
    FosDialog,
    add_classes,
    fos_alert,
    fos_prompt,
    full_icon,
    label,
    set_class,
)

try:
    from .wallpaper import draw_wallpaper
except ImportError:  # pragma: no cover - packaging fault; keep shell alive
    def draw_wallpaper(cr, area: Gdk.Rectangle, theme: str = "dawn", image_path: str | None = None) -> None:
        cr.set_source_rgb(10 / 255, 10 / 255, 10 / 255)
        cr.rectangle(area.x, area.y, area.width, area.height)
        cr.fill()

# Re-export for callers that still import draw_wallpaper from desktop.
__all__ = ["Desktop", "DesktopIcon", "draw_brand", "draw_wallpaper", "desktop_dir", "load_desktop_prefs", "save_desktop_prefs"]

# glyph px, cell width, cell height — Windows View → Large / Medium / Small.
ICON_SIZES = {
    "large": (64, 112, 120),
    "medium": (48, 96, 104),
    "small": (32, 72, 80),
}
ICON_GAP = 8
DEFAULT_MARGIN = 16
POSITIONS_FILE = "desktop-icons"
PREFS_FILE = "desktop"

# Module-level clipboard so Paste works across desktop RMB sessions.
_desk_clipboard: list[Path] = []
_desk_clipboard_cut = False


def icon_metrics() -> tuple[int, int, int]:
    """Return (glyph_px, icon_w, icon_h) from desktop prefs."""
    prefs = load_desktop_prefs()
    size = prefs.get("icon_size", "medium")
    return ICON_SIZES.get(size, ICON_SIZES["medium"])


def cell_metrics() -> tuple[int, int]:
    _px, icon_w, icon_h = icon_metrics()
    return icon_w + ICON_GAP, icon_h + ICON_GAP


def grid_bounds(primary: Gdk.Rectangle) -> tuple[int, int, int, int]:
    """Return origin_x, origin_y, columns, rows for the usable desktop grid."""
    cell_w, cell_h = cell_metrics()
    ox = primary.x + DEFAULT_MARGIN
    oy = primary.y + DEFAULT_MARGIN
    usable_w = max(cell_w, primary.width - 2 * DEFAULT_MARGIN)
    usable_h = max(cell_h, primary.height - PANEL_HEIGHT - 2 * DEFAULT_MARGIN)
    cols = max(1, usable_w // cell_w)
    rows = max(1, usable_h // cell_h)
    return ox, oy, cols, rows


def pixel_to_cell(x: int, y: int, primary: Gdk.Rectangle) -> tuple[int, int]:
    ox, oy, cols, rows = grid_bounds(primary)
    cell_w, cell_h = cell_metrics()
    col = int(round((x - ox) / cell_w))
    row = int(round((y - oy) / cell_h))
    return max(0, min(col, cols - 1)), max(0, min(row, rows - 1))


def cell_to_pixel(col: int, row: int, primary: Gdk.Rectangle) -> tuple[int, int]:
    ox, oy, _, _ = grid_bounds(primary)
    cell_w, cell_h = cell_metrics()
    return ox + col * cell_w, oy + row * cell_h


def nearest_free_cell(
    col: int,
    row: int,
    occupied: set[tuple[int, int]],
    cols: int,
    rows: int,
) -> tuple[int, int]:
    if (col, row) not in occupied:
        return col, row
    best: tuple[int, int] | None = None
    best_dist: int | None = None
    for r in range(rows):
        for c in range(cols):
            if (c, r) in occupied:
                continue
            dist = abs(c - col) + abs(r - row)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best = (c, r)
    if best is not None:
        return best
    # Grid full — keep the requested cell rather than stacking off-grid.
    return col, row


def default_cell(index: int, primary: Gdk.Rectangle) -> tuple[int, int]:
    """Column-major packing: fill top-to-bottom, then next column (Windows-like)."""
    _, _, cols, rows = grid_bounds(primary)
    row = index % rows
    col = min(index // rows, cols - 1)
    return col, row


def desktop_dir() -> Path:
    path = appmod.user_dir(GLib.UserDirectory.DIRECTORY_DESKTOP, "Desktop")
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    return Path(GLib.get_user_config_dir()) / "fosos-desktop"


def load_desktop_prefs() -> dict[str, str]:
    path = config_dir() / PREFS_FILE
    values: dict[str, str] = {
        "click": "double",
        "wallpaper": "dawn",
        "icon_size": "medium",
        "show_icons": "1",
        "auto_arrange": "0",
        "sort": "name",
    }
    if not path.is_file():
        return values
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    except OSError:
        pass
    if values.get("icon_size") not in ICON_SIZES:
        values["icon_size"] = "medium"
    if values.get("sort") not in ("name", "size", "type", "date"):
        values["sort"] = "name"
    return values


def wallpaper_theme() -> str:
    theme = load_desktop_prefs().get("wallpaper", "dawn")
    from .wallpaper import THEMES

    if theme == "image":
        return "image"
    ids = {tid for tid, _name in THEMES}
    return theme if theme in ids else "dawn"


def wallpaper_image_path() -> str | None:
    prefs = load_desktop_prefs()
    if prefs.get("wallpaper") != "image":
        return None
    path = prefs.get("wallpaper_image", "").strip()
    return path or None


def save_desktop_prefs(values: dict[str, str]) -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={value}\n" for key, value in values.items()]
    (config_dir() / PREFS_FILE).write_text("".join(lines), encoding="utf-8")


# Retired defaults kept out of the active set (1.13.14 dropped Home).
RETIRED_ICON_IDS = frozenset({"home"})

# Pre-1.13.23 virtual icon ids → real Desktop launcher filenames.
POSITION_ALIASES = {
    "computer": "Computer.desktop",
    "files": "Files.desktop",
    "trash": "Recycle Bin.desktop",
    "install": "Install FosOS.desktop",
}

DEFAULTS_DIR = DATA_DIR / "desktop-defaults"
DEFAULTS_LIVE_DIR = DATA_DIR / "desktop-defaults-live"


def ensure_default_desktop_entries() -> None:
    """Seed ~/Desktop with Computer / Files / Recycle Bin (and Install on live)."""
    folder = desktop_dir()
    sources = [DEFAULTS_DIR]
    if appmod.is_live():
        sources.append(DEFAULTS_LIVE_DIR)
    for src_dir in sources:
        if not src_dir.is_dir():
            continue
        try:
            entries = list(src_dir.iterdir())
        except OSError:
            continue
        for src in entries:
            if not src.is_file() or src.name.startswith("."):
                continue
            dest = folder / src.name
            if dest.exists():
                continue
            try:
                shutil.copy2(src, dest)
            except OSError:
                pass


def desktop_entry_icon(path: Path) -> str:
    """Same glyph Files uses, skipping MIME names the theme does not ship."""
    return entry_icon(path, symbolic=False)


def desktop_entry_title(path: Path) -> str:
    if path.suffix.lower() == ".desktop":
        try:
            info = Gio.DesktopAppInfo.new_from_filename(str(path))
        except GLib.Error:
            info = None
        if info is not None and info.get_name():
            return info.get_name()
        return path.stem
    return path.name


def load_icon_positions() -> dict[str, tuple[int, int]]:
    path = config_dir() / POSITIONS_FILE
    positions: dict[str, tuple[int, int]] = {}
    if not path.is_file():
        return positions
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            icon_id = key.strip()
            if icon_id in RETIRED_ICON_IDS:
                continue
            parts = value.split(",")
            if len(parts) != 2:
                continue
            positions[icon_id] = (int(parts[0]), int(parts[1]))
    except (OSError, ValueError):
        pass
    # Migrate virtual shell icon ids to Desktop launcher filenames.
    for old, new in POSITION_ALIASES.items():
        if old in positions and new not in positions:
            positions[new] = positions.pop(old)
        elif old in positions:
            del positions[old]
    return positions


def save_icon_positions(positions: dict[str, tuple[int, int]]) -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    active = {
        key: value
        for key, value in positions.items()
        if key not in RETIRED_ICON_IDS and key not in POSITION_ALIASES
    }
    text = "".join(f"{key}={x},{y}\n" for key, (x, y) in sorted(active.items()))
    (config_dir() / POSITIONS_FILE).write_text(text, encoding="utf-8")


@lru_cache(maxsize=1)
def _brand_logo_pixbuf(size: int = 64):
    path = DATA_DIR / "logo" / "fosos-dawn-aperture-mark.svg"
    if not path.is_file():
        return None
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_size(str(path), size, size)
    except GLib.Error:
        return None


def draw_brand(cr, widget: Gtk.Widget, area: Gdk.Rectangle) -> None:
    """The centred Dawn Aperture mark, name, tagline and motto at 14% opacity."""
    usable_h = area.height - PANEL_HEIGHT
    cx = area.x + area.width / 2
    layouts = []
    for markup, size, spacing in (
        (f"<span weight='500'>Fos</span><span weight='normal'>OS</span>", 24, 0),
        (GLib.markup_escape_text(BRAND["tagline"].upper()), 12, 2.2),
        (GLib.markup_escape_text(BRAND["motto"]), 11, 0.4),
    ):
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription(f"Inter {size}px"))
        layout.set_markup(markup, -1)
        if spacing:
            attrs = layout.get_attributes() or Pango.AttrList()
            attrs.insert(Pango.attr_letter_spacing_new(int(spacing * Pango.SCALE)))
            layout.set_attributes(attrs)
        layouts.append(layout)

    sizes = [layout.get_pixel_size() for layout in layouts]
    mark = 64
    gap = 12
    total = mark + gap + sizes[0][1] + 4 + sizes[1][1] + 8 + sizes[2][1]
    top = area.y + (usable_h - total) / 2

    cr.save()
    cr.push_group()
    logo = _brand_logo_pixbuf(mark)
    if logo is not None:
        Gdk.cairo_set_source_pixbuf(cr, logo, cx - mark / 2, top)
        cr.paint()
    else:
        cr.set_source_rgb(0.98, 0.98, 0.98)
        cr.set_line_width(1)
        cr.rectangle(round(cx - mark / 2) + 0.5, round(top) + 0.5, mark - 1, mark - 1)
        cr.stroke()

    y = top + mark + gap
    cr.set_source_rgb(0.98, 0.98, 0.98)
    for index, (layout, (lw, lh)) in enumerate(zip(layouts, sizes)):
        if index == 2:
            cr.set_source_rgb(0.63, 0.63, 0.63)
        cr.move_to(cx - lw / 2, y)
        PangoCairo.show_layout(cr, layout)
        y += lh + (4 if index == 0 else 8)
    cr.pop_group_to_source()
    cr.paint_with_alpha(0.14)
    cr.restore()


class DesktopIcon(Gtk.EventBox):
    def __init__(self, desktop: "Desktop", icon_id: str, title: str, icon_name: str, activate) -> None:
        super().__init__()
        self.desktop = desktop
        self.icon_id = icon_id
        self.activate_cb = activate
        self.set_visible_window(False)
        self.set_above_child(True)
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.BUTTON1_MOTION_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        glyph_px, icon_w, icon_h = icon_metrics()
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.box.set_size_request(icon_w - 8, -1)
        add_classes(self.box, "fos-desktop-icon")
        # Full-size icon on the wallpaper — no bordered tile (Windows-like).
        image = full_icon(icon_name, glyph_px)
        image.set_halign(Gtk.Align.CENTER)
        add_classes(image, "fos-desktop-glyph")
        self.box.pack_start(image, False, False, 0)
        text = label(title, "fos-desktop-label", xalign=0.5)
        text.set_justify(Gtk.Justification.CENTER)
        text.set_line_wrap(True)
        text.set_lines(2)
        text.set_ellipsize(Pango.EllipsizeMode.END)
        text.set_max_width_chars(12)
        self.box.pack_start(text, False, False, 0)
        self.set_size_request(icon_w, icon_h)
        self.add(self.box)
        self.connect("button-press-event", self._on_press)
        self.connect("button-release-event", self._on_release)
        self.connect("motion-notify-event", self._on_motion)
        self._drag_origin: tuple[int, int] | None = None
        self._drag_start: tuple[float, float] | None = None
        self._dragging = False
        self._double = getattr(Gdk.EventType, "DOUBLE_BUTTON_PRESS", Gdk.EventType._2BUTTON_PRESS)

    def set_selected(self, selected: bool) -> None:
        set_class(self.box, "selected", selected)

    def _on_press(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button == 3:
            self.desktop.shell.close_popups()
            self.desktop.select(self)
            self.desktop._show_icon_menu(self, event)
            return True
        if event.button != 1:
            return False
        self.desktop.shell.close_popups()
        self.desktop.select(self)
        self._drag_origin = self.desktop.icon_pos(self.icon_id)
        self._drag_start = (event.x_root, event.y_root)
        self._dragging = False
        single = self.desktop.click_mode() == "single"
        if single and event.type == Gdk.EventType.BUTTON_PRESS:
            # Activate on release unless the user dragged.
            return True
        if event.type == self._double and not single:
            self.desktop.select(None)
            self.activate_cb()
            self._drag_start = None
            return True
        return True

    def _on_motion(self, _widget, event: Gdk.EventMotion) -> bool:
        if self._drag_start is None or self._drag_origin is None:
            return False
        if not (event.state & Gdk.ModifierType.BUTTON1_MASK):
            return False
        dx = int(event.x_root - self._drag_start[0])
        dy = int(event.y_root - self._drag_start[1])
        if not self._dragging and abs(dx) < 4 and abs(dy) < 4:
            return False
        self._dragging = True
        x = self._drag_origin[0] + dx
        y = self._drag_origin[1] + dy
        self.desktop.move_icon(self, x, y, persist=False)
        return True

    def _on_release(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button != 1:
            return False
        single = self.desktop.click_mode() == "single"
        if self._dragging:
            pos = self.desktop.icon_pos(self.icon_id)
            self.desktop.move_icon(self, pos[0], pos[1], persist=True)
        elif single and self._drag_start is not None:
            self.desktop.select(None)
            self.activate_cb()
        self._drag_start = None
        self._drag_origin = None
        self._dragging = False
        return True


class Desktop(Gtk.Window):
    def __init__(self, shell) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.shell = shell
        self.set_title("FosOS Desktop")
        self.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_below(True)
        self.stick()
        self.set_app_paintable(True)
        add_classes(self, "fos-root")
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("draw", self._on_draw)
        self.connect("button-press-event", self._on_press)
        self.connect("key-press-event", self._on_key)

        self.fixed = Gtk.Fixed()
        self.add(self.fixed)
        self.icons: list[DesktopIcon] = []
        self.icon_by_id: dict[str, DesktopIcon] = {}
        self.positions = load_icon_positions()
        self.selected: DesktopIcon | None = None
        self._prefs = load_desktop_prefs()
        self._monitor: Gio.FileMonitor | None = None
        self._reload_pending = False

        # Icons come from ~/Desktop (real files). Seed Computer / Files / Recycle Bin.
        ensure_default_desktop_entries()
        self.reload_icons()
        self._watch_desktop()

        screen = Gdk.Screen.get_default()
        screen.connect("monitors-changed", lambda _s: self.place())
        screen.connect("size-changed", lambda _s: self.place())
        self.place()

    def click_mode(self) -> str:
        self._prefs = load_desktop_prefs()
        mode = self._prefs.get("click", "double")
        return mode if mode in ("single", "double") else "double"

    def reload_prefs(self) -> None:
        self._prefs = load_desktop_prefs()

    def show_menu_at(self, x: int, y: int) -> None:
        """Show the desktop context menu at a root coordinate (no Gdk event)."""
        menu = self._build_context_menu()
        menu.show_all()
        try:
            # Gdk.Rectangle(x, y, w, h) ignores its arguments.
            anchor = Gdk.Rectangle()
            anchor.x = int(x)
            anchor.y = int(y)
            anchor.width = 1
            anchor.height = 1
            menu.popup_at_rect(
                self.get_window(),
                anchor,
                Gdk.Gravity.NORTH_WEST,
                Gdk.Gravity.NORTH_WEST,
                None,
            )
        except (TypeError, AttributeError):
            menu.popup(None, None, None, None, 0, Gtk.get_current_event_time())

    def _add_icon(self, icon_id: str, title: str, icon_name: str, activate) -> None:
        item = DesktopIcon(self, icon_id, title, icon_name, activate)
        self.icons.append(item)
        self.icon_by_id[icon_id] = item
        self.fixed.put(item, 0, 0)

    def show_icons_enabled(self) -> bool:
        self._prefs = load_desktop_prefs()
        return self._prefs.get("show_icons", "1") != "0"

    def _sort_entries(self, entries: list[Path]) -> list[Path]:
        sort_key = load_desktop_prefs().get("sort", "name")

        def name_key(path: Path) -> tuple:
            return (not path.is_dir(), path.name.lower())

        def size_key(path: Path) -> tuple:
            try:
                size = 0 if path.is_dir() else path.stat().st_size
            except OSError:
                size = 0
            return (not path.is_dir(), size, path.name.lower())

        def type_key(path: Path) -> tuple:
            if path.is_dir():
                kind = ""
            else:
                kind = path.suffix.lower() or path.name.lower()
            return (not path.is_dir(), kind, path.name.lower())

        def date_key(path: Path) -> tuple:
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            return (not path.is_dir(), -mtime, path.name.lower())

        keys = {"name": name_key, "size": size_key, "type": type_key, "date": date_key}
        return sorted(entries, key=keys.get(sort_key, name_key))

    def reload_icons(self) -> None:
        """Rebuild icons from ~/Desktop so File Explorer and the wallpaper match."""
        selected_id = self.selected.icon_id if self.selected is not None else None
        for item in list(self.icons):
            self.fixed.remove(item)
            item.destroy()
        self.icons = []
        self.icon_by_id = {}
        self.selected = None

        if not self.show_icons_enabled():
            self.place()
            self.show_all()
            return

        folder = desktop_dir()
        try:
            entries = [p for p in folder.iterdir() if not p.name.startswith(".")]
        except OSError:
            entries = []
        entries = self._sort_entries(entries)

        for path in entries:
            icon_id = path.name
            title = desktop_entry_title(path)
            icon_name = desktop_entry_icon(path)
            self._add_icon(icon_id, title, icon_name, lambda p=path: self._activate_path(p))

        if selected_id and selected_id in self.icon_by_id:
            self.select(self.icon_by_id[selected_id])
        self.place()
        if load_desktop_prefs().get("auto_arrange", "0") == "1":
            # Pack column-major after grid snap when Auto arrange is on.
            self.auto_arrange()
        self.show_all()

    def _watch_desktop(self) -> None:
        folder = desktop_dir()
        if self._monitor is not None:
            self._monitor.cancel()
            self._monitor = None
        try:
            self._monitor = Gio.File.new_for_path(str(folder)).monitor_directory(
                Gio.FileMonitorFlags.NONE, None
            )
        except GLib.Error:
            self._monitor = None
            return
        self._monitor.connect("changed", self._on_desktop_changed)

    def _on_desktop_changed(self, _monitor, _file, _other, _event) -> None:
        if self._reload_pending:
            return
        self._reload_pending = True

        def _run() -> bool:
            self._reload_pending = False
            self.reload_icons()
            return False

        GLib.timeout_add(200, _run)

    def _activate_path(self, path: Path) -> None:
        if not path.exists():
            self.reload_icons()
            return
        if path.is_dir():
            self._open_folder(path)
            return
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
            return
        context = Gdk.Display.get_default().get_app_launch_context()
        try:
            Gio.AppInfo.launch_default_for_uri(path.as_uri(), context)
        except GLib.Error:
            pass

    def icon_pos(self, icon_id: str) -> tuple[int, int]:
        if icon_id in self.positions:
            return self.positions[icon_id]
        index = list(self.icon_by_id).index(icon_id) if icon_id in self.icon_by_id else 0
        primary = self._primary()
        return cell_to_pixel(*default_cell(index, primary), primary)

    def move_icon(self, item: DesktopIcon, x: int, y: int, persist: bool = True) -> None:
        primary = self._primary()
        _px, icon_w, icon_h = icon_metrics()
        max_x = primary.x + max(0, primary.width - icon_w)
        max_y = primary.y + max(0, primary.height - PANEL_HEIGHT - icon_h)
        x = max(primary.x, min(x, max_x))
        y = max(primary.y, min(y, max_y))
        if persist:
            col, row = pixel_to_cell(x, y, primary)
            _, _, cols, rows = grid_bounds(primary)
            occupied = self._occupied_cells(exclude=item.icon_id)
            col, row = nearest_free_cell(col, row, occupied, cols, rows)
            x, y = cell_to_pixel(col, row, primary)
        self.fixed.move(item, x, y)
        self.positions[item.icon_id] = (x, y)
        if persist:
            save_icon_positions(self.positions)

    def _prune_orphan_positions(self) -> None:
        """Drop retired/unknown icon ids so ghosts cannot block cells or overlap."""
        known = set(self.icon_by_id)
        for icon_id in list(self.positions):
            if icon_id not in known or icon_id in RETIRED_ICON_IDS:
                del self.positions[icon_id]

    def _occupied_cells(self, exclude: str | None = None) -> set[tuple[int, int]]:
        primary = self._primary()
        occupied: set[tuple[int, int]] = set()
        for icon_id, (px, py) in self.positions.items():
            if icon_id == exclude or icon_id not in self.icon_by_id:
                continue
            occupied.add(pixel_to_cell(px, py, primary))
        return occupied

    def _snap_all_to_grid(self, persist: bool = True) -> None:
        """Snap saved/free positions onto the grid and resolve collisions."""
        self._prune_orphan_positions()
        primary = self._primary()
        _, _, cols, rows = grid_bounds(primary)
        occupied: set[tuple[int, int]] = set()
        for item in self.icons:
            x, y = self.positions.get(item.icon_id, self.icon_pos(item.icon_id))
            col, row = pixel_to_cell(x, y, primary)
            col, row = nearest_free_cell(col, row, occupied, cols, rows)
            occupied.add((col, row))
            px, py = cell_to_pixel(col, row, primary)
            self.positions[item.icon_id] = (px, py)
            self.fixed.move(item, px, py)
        if persist:
            save_icon_positions(self.positions)

    def auto_arrange(self) -> None:
        """Pack icons into the default column/flow and persist."""
        self._prune_orphan_positions()
        primary = self._primary()
        for index, item in enumerate(self.icons):
            px, py = cell_to_pixel(*default_cell(index, primary), primary)
            self.positions[item.icon_id] = (px, py)
            self.fixed.move(item, px, py)
        save_icon_positions(self.positions)
        self.queue_draw()

    def _open_folder(self, path: Path) -> None:
        appmod.spawn(["fosos-files", str(path)])

    def place(self) -> None:
        screen = Gdk.Screen.get_default()
        width, height = screen.get_width(), screen.get_height()
        self.move(0, 0)
        self.set_size_request(width, height)
        self.resize(width, height)
        for item in self.icons:
            if item.icon_id not in self.positions:
                index = list(self.icon_by_id).index(item.icon_id)
                self.positions[item.icon_id] = cell_to_pixel(
                    *default_cell(index, self._primary()), self._primary()
                )
        self._snap_all_to_grid(persist=True)
        self.queue_draw()

    def refresh(self) -> None:
        self.reload_prefs()
        # Re-read positions so a Settings "Reset icon positions" takes effect.
        self.positions = load_icon_positions()
        ensure_default_desktop_entries()
        self.reload_icons()
        self.queue_draw()

    def _primary(self) -> Gdk.Rectangle:
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        return monitor.get_geometry()

    def _on_draw(self, _widget, cr) -> bool:
        display = Gdk.Display.get_default()
        primary = self._primary()
        theme = wallpaper_theme()
        image = wallpaper_image_path()
        for index in range(display.get_n_monitors()):
            area = display.get_monitor(index).get_geometry()
            draw_wallpaper(cr, area, theme, image_path=image)
        draw_brand(cr, self, primary)
        return False

    def select(self, item: DesktopIcon | None) -> None:
        self.selected = item
        for other in self.icons:
            other.set_selected(other is item)

    def _on_press(self, _widget, event: Gdk.EventButton) -> bool:
        self.shell.close_popups()
        # Clicks on icons are handled by DesktopIcon; empty desktop clears selection.
        if event.window != self.get_window():
            return False
        self.select(None)
        if event.button == 3:
            self._show_context_menu(event)
            return True
        return False

    def _menu_add(self, menu: Gtk.Menu, title: str, callback, *, sensitive: bool = True) -> Gtk.MenuItem:
        item = Gtk.MenuItem(label=title)
        item.set_sensitive(sensitive)
        item.connect("activate", lambda _i: callback())
        menu.append(item)
        return item

    def _menu_submenu(self, menu: Gtk.Menu, title: str) -> Gtk.Menu:
        item = Gtk.MenuItem(label=title)
        sub = Gtk.Menu()
        item.set_submenu(sub)
        menu.append(item)
        return sub

    def _set_pref(self, key: str, value: str) -> None:
        values = load_desktop_prefs()
        values[key] = value
        save_desktop_prefs(values)
        self._prefs = values

    def _build_context_menu(self) -> Gtk.Menu:
        """Windows-shaped desktop background menu: View / Sort by / New / …"""
        menu = Gtk.Menu()
        prefs = load_desktop_prefs()

        view = self._menu_submenu(menu, "View")
        size_group: Gtk.RadioMenuItem | None = None
        current_size = prefs.get("icon_size", "medium")
        for size_id, title in (("large", "Large icons"), ("medium", "Medium icons"), ("small", "Small icons")):
            item = Gtk.RadioMenuItem.new_with_label_from_widget(size_group, title)
            if size_group is None:
                size_group = item
            item.set_active(current_size == size_id)
            item.connect("activate", lambda _i, s=size_id: self._set_icon_size(s) if _i.get_active() else None)
            view.append(item)
        view.append(Gtk.SeparatorMenuItem())
        auto = Gtk.CheckMenuItem(label="Auto arrange icons")
        auto.set_active(prefs.get("auto_arrange", "0") == "1")
        auto.connect("toggled", lambda i: self._set_auto_arrange(i.get_active()))
        view.append(auto)
        align = Gtk.MenuItem(label="Align icons to grid")
        align.connect("activate", lambda _i: self._snap_all_to_grid(persist=True))
        view.append(align)
        view.append(Gtk.SeparatorMenuItem())
        show = Gtk.CheckMenuItem(label="Show desktop icons")
        show.set_active(prefs.get("show_icons", "1") != "0")
        show.connect("toggled", lambda i: self._set_show_icons(i.get_active()))
        view.append(show)

        sort_menu = self._menu_submenu(menu, "Sort by")
        sort_group: Gtk.RadioMenuItem | None = None
        current_sort = prefs.get("sort", "name")
        for key, title in (("name", "Name"), ("size", "Size"), ("type", "Item type"), ("date", "Date modified")):
            item = Gtk.RadioMenuItem.new_with_label_from_widget(sort_group, title)
            if sort_group is None:
                sort_group = item
            item.set_active(current_sort == key)
            item.connect("activate", lambda _i, k=key: self._sort_by(k) if _i.get_active() else None)
            sort_menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())
        self._menu_add(menu, "Refresh", self.refresh)

        menu.append(Gtk.SeparatorMenuItem())
        new_menu = self._menu_submenu(menu, "New")
        self._menu_add(new_menu, "Folder", self._new_folder)
        self._menu_add(new_menu, "Text Document", self._new_text_document)

        menu.append(Gtk.SeparatorMenuItem())
        self._menu_add(menu, "Paste", self._paste, sensitive=self._can_paste())

        menu.append(Gtk.SeparatorMenuItem())
        self._menu_add(menu, "Display settings", lambda: appmod.spawn(["arandr"]))
        self._menu_add(
            menu,
            "Personalize",
            lambda: appmod.spawn(["fosos-settings", "--builtin", "desktop"]),
        )

        menu.append(Gtk.SeparatorMenuItem())
        self._menu_add(menu, "Open in Terminal", lambda: appmod.spawn(["fosos-terminal", str(desktop_dir())]))
        self._menu_add(menu, "Open in Files", lambda: self._open_folder(desktop_dir()))
        return menu

    def _show_context_menu(self, event: Gdk.EventButton) -> None:
        menu = self._build_context_menu()
        menu.attach_to_widget(self, None)
        menu.show_all()
        menu.popup_at_pointer(event)

    def _show_icon_menu(self, item: DesktopIcon, event: Gdk.EventButton) -> None:
        """Windows-shaped item menu for a desktop icon."""
        path = desktop_dir() / item.icon_id
        menu = Gtk.Menu()
        open_label = "Install" if path.is_file() and path.suffix.lower() == ".deb" else "Open"
        self._menu_add(menu, open_label, item.activate_cb)
        menu.append(Gtk.SeparatorMenuItem())
        self._menu_add(menu, "Cut", lambda: self._clipboard_set([path], cut=True))
        self._menu_add(menu, "Copy", lambda: self._clipboard_set([path], cut=False))
        self._menu_add(menu, "Paste", self._paste, sensitive=self._can_paste())
        menu.append(Gtk.SeparatorMenuItem())
        self._menu_add(menu, "Delete", lambda: self._trash_paths([path]))
        self._menu_add(menu, "Rename", lambda: self._rename_path(path))
        menu.append(Gtk.SeparatorMenuItem())
        self._menu_add(menu, "Properties", lambda: self._properties(path))
        menu.attach_to_widget(self, None)
        menu.show_all()
        menu.popup_at_pointer(event)

    def _set_icon_size(self, size_id: str) -> None:
        if size_id not in ICON_SIZES:
            return
        self._set_pref("icon_size", size_id)
        self.reload_icons()

    def _set_auto_arrange(self, enabled: bool) -> None:
        self._set_pref("auto_arrange", "1" if enabled else "0")
        if enabled:
            self.auto_arrange()

    def _set_show_icons(self, show: bool) -> None:
        self._set_pref("show_icons", "1" if show else "0")
        self.reload_icons()

    def _sort_by(self, key: str) -> None:
        self._set_pref("sort", key)
        self.reload_icons()
        self.auto_arrange()

    def _can_paste(self) -> bool:
        global _desk_clipboard
        if _desk_clipboard:
            return True
        return bool(self._clipboard_uris())

    def _clipboard_set(self, paths: list[Path], cut: bool) -> None:
        global _desk_clipboard, _desk_clipboard_cut
        _desk_clipboard = [p.resolve() for p in paths]
        _desk_clipboard_cut = cut
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        uris = "\n".join(p.as_uri() for p in _desk_clipboard)
        clipboard.set_text(uris, -1)
        clipboard.store()

    def _clipboard_uris(self) -> list[Path]:
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        text = clipboard.wait_for_text()
        if not text:
            return []
        paths: list[Path] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("file:"):
                try:
                    paths.append(Path(GLib.filename_from_uri(line)[0]))
                except (TypeError, ValueError, GLib.Error):
                    continue
            else:
                candidate = Path(line)
                if candidate.exists():
                    paths.append(candidate)
        return paths

    def _paste(self) -> None:
        global _desk_clipboard, _desk_clipboard_cut
        sources = list(_desk_clipboard) if _desk_clipboard else self._clipboard_uris()
        if not sources:
            return
        cut = _desk_clipboard_cut if _desk_clipboard else False
        dest_dir = desktop_dir()
        for src in sources:
            if not src.exists():
                continue
            target = dest_dir / src.name
            index = 1
            while target.exists():
                stem, suffix = src.stem, src.suffix
                if src.is_dir():
                    target = dest_dir / f"{src.name} ({index})"
                else:
                    target = dest_dir / f"{stem} ({index}){suffix}"
                index += 1
            try:
                if cut:
                    shutil.move(str(src), str(target))
                elif src.is_dir():
                    shutil.copytree(src, target)
                else:
                    shutil.copy2(src, target)
            except OSError:
                continue
        if cut and _desk_clipboard:
            _desk_clipboard = []
            _desk_clipboard_cut = False
        self.reload_icons()

    def _trash_paths(self, paths: list[Path]) -> None:
        for path in paths:
            try:
                Gio.File.new_for_path(str(path)).trash(None)
            except GLib.Error:
                pass
        self.select(None)
        self.reload_icons()

    def _rename_path(self, path: Path) -> None:
        name = fos_prompt(self, "Rename", "New name", path.name)
        if not name or name == path.name:
            return
        target = path.with_name(name)
        if target.exists():
            fos_alert(self, "Could not rename", f"“{name}” already exists.")
            return
        try:
            path.rename(target)
        except OSError as exc:
            fos_alert(self, "Could not rename", str(exc))
            return
        # Preserve layout cell under the new id when possible.
        if path.name in self.positions:
            self.positions[target.name] = self.positions.pop(path.name)
            save_icon_positions(self.positions)
        self.reload_icons()

    def _properties(self, path: Path) -> None:
        try:
            st = path.stat()
        except OSError as exc:
            fos_alert(self, "Properties unavailable", str(exc))
            return
        mime, _ = Gio.content_type_guess(str(path), None)
        if path.is_dir():
            try:
                size = f"{sum(1 for _ in path.iterdir())} items"
            except OSError:
                size = "Folder"
            kind = "Folder"
        else:
            size = format_size(st.st_size)
            kind = mime or "File"
        modified = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
        rows = [
            ("Name", path.name),
            ("Type", kind),
            ("Size", size),
            ("Modified", modified),
            ("Location", str(path.parent)),
        ]
        dialog = FosDialog(self, title="Properties", width=480)
        grid = Gtk.Grid(column_spacing=16, row_spacing=8)
        for index, (key, value) in enumerate(rows):
            grid.attach(label(key, "fos-text", "fos-muted"), 0, index, 1, 1)
            val = label(value, "fos-text")
            val.set_selectable(True)
            val.set_max_width_chars(48)
            grid.attach(val, 1, index, 1, 1)
        dialog.content.pack_start(grid, False, False, 0)
        dialog.add_action("Close", True, variant="default", default=True)
        dialog.run()

    def _new_folder(self) -> None:
        folder = desktop_dir()
        base = "New folder"
        target = folder / base
        index = 1
        while target.exists():
            target = folder / f"{base} ({index})"
            index += 1
        try:
            target.mkdir(exist_ok=False)
        except OSError:
            return
        self.reload_icons()

    def _new_text_document(self) -> None:
        folder = desktop_dir()
        base = "New Text Document.txt"
        target = folder / base
        index = 1
        while target.exists():
            target = folder / f"New Text Document ({index}).txt"
            index += 1
        try:
            target.write_text("", encoding="utf-8")
        except OSError:
            return
        self.reload_icons()

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.select(None)
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and self.selected is not None:
            item = self.selected
            self.select(None)
            item.activate_cb()
            return True
        if event.keyval == Gdk.KEY_F5:
            self.refresh()
            return True
        if event.keyval == Gdk.KEY_F2 and self.selected is not None:
            self._rename_path(desktop_dir() / self.selected.icon_id)
            return True
        if event.keyval in (Gdk.KEY_Delete, Gdk.KEY_KP_Delete) and self.selected is not None:
            path = desktop_dir() / self.selected.icon_id
            self._trash_paths([path])
            return True
        # Ctrl+C / Ctrl+X / Ctrl+V
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        if ctrl and self.selected is not None and event.keyval in (Gdk.KEY_c, Gdk.KEY_C):
            self._clipboard_set([desktop_dir() / self.selected.icon_id], cut=False)
            return True
        if ctrl and self.selected is not None and event.keyval in (Gdk.KEY_x, Gdk.KEY_X):
            self._clipboard_set([desktop_dir() / self.selected.icon_id], cut=True)
            return True
        if ctrl and event.keyval in (Gdk.KEY_v, Gdk.KEY_V):
            self._paste()
            return True
        return False
