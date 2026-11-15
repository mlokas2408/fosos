"""Widgets and styling shared by the shell and the settings window."""

import sys
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango

def _resolve_data_dir() -> Path:
    here = Path(__file__).resolve().parent
    candidates = (
        here.parents[2] / "share" / "fosos-desktop",  # /usr/lib/fosos-desktop/fosdesk → /usr/share/...
        Path("/usr/share/fosos-desktop"),
    )
    for path in candidates:
        if (path / "fosos-desktop.css").is_file():
            return path
    return candidates[0]


DATA_DIR = _resolve_data_dir()

BRAND = {
    "name": "FosOS",
    "tagline": "φως · light",
    "motto": "Focus. Own. Ship.",
    "live_label": "FosOS · live",
    "etymology": "From Greek φως (fos), light.",
}

_css_loaded = False


def load_css() -> None:
    global _css_loaded
    if _css_loaded:
        return
    css_path = DATA_DIR / "fosos-desktop.css"
    settings = Gtk.Settings.get_default()
    if settings is not None:
        settings.set_property("gtk-application-prefer-dark-theme", True)
    if not css_path.is_file():
        print(f"fosos-desktop: CSS missing at {css_path}", file=sys.stderr)
        _css_loaded = True
        return
    try:
        provider = Gtk.CssProvider()
        provider.load_from_path(str(css_path))
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
    except GLib.Error as exc:
        # Never kill the shell over a stylesheet problem.
        print(f"fosos-desktop: CSS load failed: {exc}", file=sys.stderr)
    _css_loaded = True


def add_classes(widget: Gtk.Widget, *names: str) -> Gtk.Widget:
    context = widget.get_style_context()
    for name in names:
        if name:
            context.add_class(name)
    return widget


def set_class(widget: Gtk.Widget, name: str, enabled: bool) -> None:
    context = widget.get_style_context()
    if enabled:
        context.add_class(name)
    else:
        context.remove_class(name)


def icon(name: str, size: int = 16) -> Gtk.Image:
    image = Gtk.Image.new_from_icon_name(name, Gtk.IconSize.MENU)
    image.set_pixel_size(size)
    return image


def label(text: str = "", *classes: str, xalign: float = 0.0, ellipsize: bool = False) -> Gtk.Label:
    widget = Gtk.Label(label=text)
    widget.set_xalign(xalign)
    if ellipsize:
        widget.set_ellipsize(Pango.EllipsizeMode.END)
    add_classes(widget, *classes)
    return widget


def button(
    text: str | None = None,
    icon_name: str | None = None,
    variant: str = "ghost",
    size: str = "",
    tooltip: str | None = None,
    icon_size: int = 16,
) -> Gtk.Button:
    widget = Gtk.Button()
    widget.set_relief(Gtk.ReliefStyle.NONE)
    widget.set_can_focus(False)
    add_classes(widget, "fos-btn", variant, f"size-{size}" if size else "")
    if icon_name and text:
        box = Gtk.Box(spacing=8)
        box.pack_start(icon(icon_name, icon_size), False, False, 0)
        box.pack_start(label(text), False, False, 0)
        widget.add(box)
    elif icon_name:
        widget.add(icon(icon_name, icon_size))
    elif text:
        widget.add(label(text, xalign=0.5))
    if tooltip:
        widget.set_tooltip_text(tooltip)
    return widget


_MARK_PX = {"sm": 18, "md": 24, "lg": 48, "xl": 64}


def mark(size: str = "md", inverse: bool = False) -> Gtk.Widget:
    """Dawn Aperture logo mark (φως / light). inverse=True uses the black-tile logo."""
    px = _MARK_PX.get(size, 24)
    # Full tile (black + white) on light chrome; white-only mark on dark UI.
    filename = "fosos-dawn-aperture.svg" if inverse else "fosos-dawn-aperture-mark.svg"
    path = DATA_DIR / "logo" / filename
    image = Gtk.Image()
    image.set_halign(Gtk.Align.CENTER)
    image.set_valign(Gtk.Align.CENTER)
    if path.is_file():
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(path), px, px)
            image.set_from_pixbuf(pixbuf)
        except GLib.Error:
            image.set_from_icon_name("image-missing", Gtk.IconSize.BUTTON)
    else:
        image.set_from_icon_name("image-missing", Gtk.IconSize.BUTTON)
    add_classes(image, "fos-mark", f"size-{size}", "inverse" if inverse else "")
    image.set_size_request(px, px)
    return image


def start_icon() -> Gtk.Grid:
    """Four-pane mark, like the Windows Start button."""
    grid = Gtk.Grid()
    grid.set_row_spacing(2)
    grid.set_column_spacing(2)
    grid.set_row_homogeneous(True)
    grid.set_column_homogeneous(True)
    grid.set_halign(Gtk.Align.CENTER)
    grid.set_valign(Gtk.Align.CENTER)
    for index in range(4):
        cell = Gtk.Box()
        cell.set_size_request(6, 6)
        add_classes(cell, "fos-start-cell")
        grid.attach(cell, index % 2, index // 2, 1, 1)
    add_classes(grid, "fos-start-icon")
    return grid


def brand_title(size_px: int = 14) -> Gtk.Label:
    widget = Gtk.Label()
    widget.set_markup(
        f"<span size='{size_px * 1024}' weight='500'>Fos</span>"
        f"<span size='{size_px * 1024}' weight='normal' alpha='80%'>OS</span>"
    )
    widget.set_xalign(0)
    return widget


def separator(vertical: bool = True, length: int = 28) -> Gtk.Box:
    widget = Gtk.Box()
    if vertical:
        widget.set_size_request(1, length)
        widget.set_valign(Gtk.Align.CENTER)
    else:
        widget.set_size_request(-1, 1)
    add_classes(widget, "fos-sep")
    return widget


def badge(text: str, variant: str = "outline") -> Gtk.Label:
    widget = label(text, "fos-badge", variant, xalign=0.5)
    widget.set_valign(Gtk.Align.CENTER)
    return widget


def kbd(text: str) -> Gtk.Label:
    widget = label(text, "fos-kbd", xalign=0.5)
    widget.set_valign(Gtk.Align.CENTER)
    return widget


def tile(icon_name: str, kind: str = "primary", size: int = 16, small: bool = False) -> Gtk.Box:
    box = Gtk.Box()
    box.set_halign(Gtk.Align.CENTER)
    box.set_valign(Gtk.Align.CENTER)
    box.pack_start(icon(icon_name, size), True, True, 0)
    add_classes(box, "fos-tile", kind, "small" if small else "")
    return box


def card() -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    add_classes(box, "fos-card")
    return box


def clear(container: Gtk.Container) -> None:
    for child in container.get_children():
        container.remove(child)
        child.destroy()


def idle(func, *args) -> None:
    def run():
        func(*args)
        return False

    GLib.idle_add(run)
