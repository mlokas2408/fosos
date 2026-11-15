"""The desktop: drawn wallpaper, the faint FosOS brand and desktop icons."""

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo

from . import apps as appmod
from .panel import HEIGHT as PANEL_HEIGHT
from .ui import BRAND, add_classes, icon, label, set_class

try:
    from .wallpaper import draw_wallpaper
except ImportError:  # pragma: no cover - packaging fault; keep shell alive
    def draw_wallpaper(cr, area: Gdk.Rectangle) -> None:
        cr.set_source_rgb(10 / 255, 10 / 255, 10 / 255)
        cr.rectangle(area.x, area.y, area.width, area.height)
        cr.fill()

# Re-export for callers that still import draw_wallpaper from desktop.
__all__ = ["Desktop", "DesktopIcon", "draw_brand", "draw_wallpaper"]


def draw_brand(cr, widget: Gtk.Widget, area: Gdk.Rectangle) -> None:
    """The centred mark, name, tagline and motto at 14% opacity."""
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
    mark = 48
    gap = 12
    total = mark + gap + sizes[0][1] + 4 + sizes[1][1] + 8 + sizes[2][1]
    top = area.y + (usable_h - total) / 2

    cr.save()
    cr.push_group()
    cr.set_source_rgb(0.98, 0.98, 0.98)
    cr.set_line_width(1)
    cr.rectangle(round(cx - mark / 2) + 0.5, round(top) + 0.5, mark - 1, mark - 1)
    cr.stroke()
    f_layout = PangoCairo.create_layout(cr)
    f_layout.set_font_description(Pango.FontDescription("Inter Medium 20px"))
    f_layout.set_text("F", -1)
    fw, fh = f_layout.get_pixel_size()
    cr.move_to(cx - fw / 2, top + (mark - fh) / 2)
    PangoCairo.show_layout(cr, f_layout)

    y = top + mark + gap
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
    def __init__(self, desktop: "Desktop", title: str, icon_name: str, activate) -> None:
        super().__init__()
        self.desktop = desktop
        self.activate_cb = activate
        self.set_visible_window(False)
        self.set_above_child(True)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.box.set_size_request(76, -1)
        add_classes(self.box, "fos-desktop-icon")
        tile = Gtk.Box()
        tile.set_halign(Gtk.Align.CENTER)
        tile.pack_start(icon(icon_name, 18), True, True, 0)
        add_classes(tile, "fos-desktop-tile")
        self.box.pack_start(tile, False, False, 0)
        text = label(title, "fos-desktop-label", xalign=0.5)
        text.set_justify(Gtk.Justification.CENTER)
        text.set_line_wrap(True)
        text.set_lines(2)
        text.set_ellipsize(Pango.EllipsizeMode.END)
        text.set_max_width_chars(10)
        self.box.pack_start(text, False, False, 0)
        self.add(self.box)
        self.connect("button-press-event", self._on_press)

    def set_selected(self, selected: bool) -> None:
        set_class(self.box, "selected", selected)

    def _on_press(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button != 1:
            return False
        self.desktop.shell.close_popups()
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self.desktop.select(None)
            self.activate_cb()
        else:
            self.desktop.select(self)
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
        self.icons_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.icons: list[DesktopIcon] = []
        self.selected: DesktopIcon | None = None
        self._add_icon("Files", "folder-symbolic", lambda: self._launch("fosos-files.desktop"))
        if appmod.is_live() and appmod.load_app("calamares-install-fosos.desktop"):
            self._add_icon(
                "Install FosOS", "system-software-install-symbolic", lambda: self._launch("calamares-install-fosos.desktop")
            )
        self.fixed.put(self.icons_box, 0, 0)

        screen = Gdk.Screen.get_default()
        screen.connect("monitors-changed", lambda _s: self.place())
        screen.connect("size-changed", lambda _s: self.place())
        self.place()

    def _add_icon(self, title: str, icon_name: str, activate) -> None:
        item = DesktopIcon(self, title, icon_name, activate)
        self.icons.append(item)
        self.icons_box.pack_start(item, False, False, 0)

    def _launch(self, app_id: str) -> None:
        app = appmod.load_app(app_id)
        if app is not None:
            app.launch()

    def place(self) -> None:
        screen = Gdk.Screen.get_default()
        width, height = screen.get_width(), screen.get_height()
        self.move(0, 0)
        self.set_size_request(width, height)
        self.resize(width, height)
        primary = self._primary()
        self.fixed.move(self.icons_box, primary.x + 16, primary.y + 16)
        self.queue_draw()

    def _primary(self) -> Gdk.Rectangle:
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        return monitor.get_geometry()

    def _on_draw(self, _widget, cr) -> bool:
        display = Gdk.Display.get_default()
        primary = self._primary()
        for index in range(display.get_n_monitors()):
            area = display.get_monitor(index).get_geometry()
            draw_wallpaper(cr, area)
        draw_brand(cr, self, primary)
        return False

    def select(self, item: DesktopIcon | None) -> None:
        self.selected = item
        for other in self.icons:
            other.set_selected(other is item)

    def _on_press(self, _widget, event: Gdk.EventButton) -> bool:
        self.shell.close_popups()
        self.select(None)
        if event.button == 3:
            self.shell.show_desktop_menu(int(event.x_root), int(event.y_root))
            return True
        return False

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.select(None)
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and self.selected is not None:
            item = self.selected
            self.select(None)
            item.activate_cb()
            return True
        return False
