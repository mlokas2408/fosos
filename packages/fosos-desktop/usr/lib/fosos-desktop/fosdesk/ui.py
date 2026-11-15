"""Widgets and styling shared by the shell and the settings window."""

from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango

DATA_DIR = Path(__file__).resolve().parents[3] / "share" / "fosos-desktop"

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
    provider = Gtk.CssProvider()
    provider.load_from_path(str(DATA_DIR / "fosos-desktop.css"))
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    settings = Gtk.Settings.get_default()
    if settings is not None:
        settings.set_property("gtk-application-prefer-dark-theme", True)
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


def mark(size: str = "md", inverse: bool = False) -> Gtk.Label:
    widget = Gtk.Label(label="F")
    widget.set_xalign(0.5)
    widget.set_yalign(0.5)
    widget.set_halign(Gtk.Align.CENTER)
    widget.set_valign(Gtk.Align.CENTER)
    add_classes(widget, "fos-mark", f"size-{size}", "inverse" if inverse else "")
    return widget


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
