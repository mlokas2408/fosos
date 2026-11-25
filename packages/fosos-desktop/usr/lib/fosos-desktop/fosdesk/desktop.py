"""The desktop: drawn wallpaper, the faint FosOS brand and desktop icons."""

from __future__ import annotations

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
from .panel import HEIGHT as PANEL_HEIGHT
from .ui import BRAND, DATA_DIR, add_classes, full_icon, label, set_class

try:
    from .wallpaper import draw_wallpaper
except ImportError:  # pragma: no cover - packaging fault; keep shell alive
    def draw_wallpaper(cr, area: Gdk.Rectangle, theme: str = "dawn", image_path: str | None = None) -> None:
        cr.set_source_rgb(10 / 255, 10 / 255, 10 / 255)
        cr.rectangle(area.x, area.y, area.width, area.height)
        cr.fill()

# Re-export for callers that still import draw_wallpaper from desktop.
__all__ = ["Desktop", "DesktopIcon", "draw_brand", "draw_wallpaper", "desktop_dir", "load_desktop_prefs", "save_desktop_prefs"]

ICON_W = 96
ICON_H = 104
ICON_GAP = 8
ICON_PX = 48
DEFAULT_MARGIN = 16
POSITIONS_FILE = "desktop-icons"
PREFS_FILE = "desktop"


def cell_metrics() -> tuple[int, int]:
    return ICON_W + ICON_GAP, ICON_H + ICON_GAP


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
    values: dict[str, str] = {"click": "double", "wallpaper": "dawn"}
    if not path.is_file():
        return values
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    except OSError:
        pass
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
    if path.is_dir():
        return "folder"
    if path.suffix.lower() == ".desktop":
        try:
            info = Gio.DesktopAppInfo.new_from_filename(str(path))
        except GLib.Error:
            info = None
        if info is not None:
            gicon = info.get_icon()
            if isinstance(gicon, Gio.ThemedIcon):
                names = gicon.get_names()
                if names:
                    return names[0]
        return "application-x-executable"
    mime, _ = Gio.content_type_guess(str(path), None)
    if mime:
        themed = Gio.content_type_get_icon(mime)
        if isinstance(themed, Gio.ThemedIcon):
            names = themed.get_names()
            if names:
                return names[0]
    return "text-x-generic"


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
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.box.set_size_request(ICON_W - 8, -1)
        add_classes(self.box, "fos-desktop-icon")
        # Full-size icon on the wallpaper — no bordered tile (Windows-like).
        image = full_icon(icon_name, ICON_PX)
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
        self.set_size_request(ICON_W, ICON_H)
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

    def reload_icons(self) -> None:
        """Rebuild icons from ~/Desktop so File Explorer and the wallpaper match."""
        selected_id = self.selected.icon_id if self.selected is not None else None
        for item in list(self.icons):
            self.fixed.remove(item)
            item.destroy()
        self.icons = []
        self.icon_by_id = {}
        self.selected = None

        folder = desktop_dir()
        try:
            entries = sorted(
                (p for p in folder.iterdir() if not p.name.startswith(".")),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except OSError:
            entries = []

        for path in entries:
            icon_id = path.name
            title = desktop_entry_title(path)
            icon_name = desktop_entry_icon(path)
            self._add_icon(icon_id, title, icon_name, lambda p=path: self._activate_path(p))

        if selected_id and selected_id in self.icon_by_id:
            self.select(self.icon_by_id[selected_id])
        self.place()
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
        max_x = primary.x + max(0, primary.width - ICON_W)
        max_y = primary.y + max(0, primary.height - PANEL_HEIGHT - ICON_H)
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

    def _build_context_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()

        refresh = Gtk.MenuItem(label="Refresh")
        refresh.connect("activate", lambda _i: self.refresh())
        menu.append(refresh)

        arrange = Gtk.MenuItem(label="Auto arrange icons")
        arrange.connect("activate", lambda _i: self.auto_arrange())
        menu.append(arrange)

        menu.append(Gtk.SeparatorMenuItem())

        display = Gtk.MenuItem(label="Display settings")
        display.connect("activate", lambda _i: appmod.spawn(["arandr"]))
        menu.append(display)

        personalize = Gtk.MenuItem(label="Personalize")
        personalize.connect("activate", lambda _i: appmod.spawn(["fosos-settings", "--builtin", "desktop"]))
        menu.append(personalize)

        menu.append(Gtk.SeparatorMenuItem())

        new_folder = Gtk.MenuItem(label="New folder")
        new_folder.connect("activate", lambda _i: self._new_folder())
        menu.append(new_folder)

        menu.append(Gtk.SeparatorMenuItem())

        files_here = Gtk.MenuItem(label="Open Files here")
        files_here.connect("activate", lambda _i: self._open_folder(desktop_dir()))
        menu.append(files_here)

        terminal = Gtk.MenuItem(label="Open Terminal here")
        terminal.connect("activate", lambda _i: appmod.spawn(["fosos-terminal", str(desktop_dir())]))
        menu.append(terminal)
        return menu

    def _show_context_menu(self, event: Gdk.EventButton) -> None:
        menu = self._build_context_menu()
        menu.show_all()
        menu.popup_at_pointer(event)

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
        return False
