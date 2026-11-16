"""Widgets and styling shared by the shell and the settings window."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

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


class FosDialog(Gtk.Window):
    """Undecorated modal dialog with fos-card chrome (Start-menu style)."""

    def __init__(
        self,
        parent: Gtk.Window | None,
        *,
        title: str,
        width: int = 420,
    ) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_title(title)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_modal(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        if parent is not None:
            self.set_transient_for(parent)
        add_classes(self, "fos-root", "fos-popup", "fos-dialog")
        self.set_default_size(width, -1)
        self._response: Any = None
        self._loop: GLib.MainLoop | None = None
        self.connect("delete-event", self._on_delete)
        self.connect("key-press-event", self._on_key)

        self.frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(self.frame)

        header = add_classes(Gtk.Box(spacing=8), "fos-card-header")
        header.pack_start(label(title, "fos-title"), True, True, 0)
        self.frame.pack_start(header, False, False, 0)

        self.content = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "fos-card-content")
        self.frame.pack_start(self.content, True, True, 0)

        self.footer = add_classes(Gtk.Box(spacing=8), "fos-card-footer")
        self.footer.set_halign(Gtk.Align.END)
        self.frame.pack_start(self.footer, False, False, 0)

    def add_body_text(self, text: str, *classes: str) -> Gtk.Label:
        widget = label(text, *(classes or ("fos-text", "fos-muted")))
        widget.set_line_wrap(True)
        widget.set_max_width_chars(52)
        self.content.pack_start(widget, False, False, 0)
        return widget

    def add_action(
        self,
        text: str,
        response: Any,
        *,
        variant: str = "ghost",
        default: bool = False,
    ) -> Gtk.Button:
        btn = button(text, variant=variant, size="sm")
        btn.set_can_focus(True)
        btn.connect("clicked", lambda _b: self.respond(response))
        self.footer.pack_start(btn, False, False, 0)
        if default:
            btn.set_can_default(True)
            btn.grab_default()
        return btn

    def respond(self, value: Any) -> None:
        self._response = value
        self.hide()
        if self._loop is not None and self._loop.is_running():
            self._loop.quit()

    def run(self) -> Any:
        self.show_all()
        self.present()
        self._response = None
        self._loop = GLib.MainLoop()
        self._loop.run()
        self._loop = None
        self.destroy()
        return self._response

    def _on_delete(self, *_args) -> bool:
        self.respond(None)
        return True

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.respond(None)
            return True
        return False


def fos_alert(parent: Gtk.Window | None, title: str, body: str = "") -> None:
    dialog = FosDialog(parent, title=title)
    if body:
        dialog.add_body_text(body)
    dialog.add_action("OK", True, variant="default", default=True)
    dialog.run()


def fos_confirm(
    parent: Gtk.Window | None,
    title: str,
    body: str = "",
    *,
    ok: str = "OK",
    cancel: str = "Cancel",
    destructive: bool = False,
) -> bool:
    dialog = FosDialog(parent, title=title)
    if body:
        dialog.add_body_text(body)
    dialog.add_action(cancel, False, variant="ghost")
    dialog.add_action(ok, True, variant="destructive" if destructive else "default", default=True)
    return bool(dialog.run())


def fos_prompt(
    parent: Gtk.Window | None,
    title: str,
    field_label: str,
    initial: str = "",
) -> str | None:
    dialog = FosDialog(parent, title=title)
    dialog.content.pack_start(label(field_label, "fos-text"), False, False, 0)
    entry = add_classes(Gtk.Entry(), "fos-input")
    entry.set_text(initial)
    entry.set_activates_default(True)
    dialog.content.pack_start(entry, False, False, 0)
    result: dict[str, str | None] = {"text": None}

    def accept(_widget=None) -> None:
        result["text"] = entry.get_text().strip() or None
        dialog.respond(True)

    dialog.add_action("Cancel", None, variant="ghost")
    ok_btn = button("OK", variant="default", size="sm")
    ok_btn.set_can_focus(True)
    ok_btn.set_can_default(True)
    ok_btn.connect("clicked", accept)
    dialog.footer.pack_start(ok_btn, False, False, 0)
    entry.connect("activate", accept)
    GLib.idle_add(entry.grab_focus)
    if dialog.run() is not True:
        return None
    return result["text"]


def fos_choice(
    parent: Gtk.Window | None,
    title: str,
    body: str,
    buttons: list[tuple[str, Any, str]],
) -> Any:
    """Show a dialog with custom buttons: (label, response_value, variant)."""
    dialog = FosDialog(parent, title=title)
    if body:
        dialog.add_body_text(body)
    for index, (text, value, variant) in enumerate(buttons):
        default = index == len(buttons) - 1
        dialog.add_action(text, value, variant=variant, default=default)
    return dialog.run()


def fos_custom(
    parent: Gtk.Window | None,
    title: str,
    build: Callable[[FosDialog], None],
    *,
    width: int = 420,
) -> Any:
    """Build a themed dialog, then run it. Call dialog.respond(value) from actions."""
    dialog = FosDialog(parent, title=title, width=width)
    build(dialog)
    return dialog.run()


def fos_file_chooser(
    parent: Gtk.Window | None,
    *,
    title: str,
    action: Gtk.FileChooserAction,
    ok_label: str = "OK",
    filters: list[Gtk.FileFilter] | None = None,
    current_name: str | None = None,
    filename: str | None = None,
    overwrite_confirmation: bool = False,
) -> str | None:
    """Themed file open/save dialog. Returns a filesystem path or None."""
    dialog = FosDialog(parent, title=title, width=640)
    dialog.set_resizable(True)
    dialog.set_default_size(640, 420)

    chooser = Gtk.FileChooserWidget(action=action)
    add_classes(chooser, "fos-file-chooser")
    if filters:
        for filt in filters:
            chooser.add_filter(filt)
    if filename:
        chooser.set_filename(filename)
    elif current_name and action == Gtk.FileChooserAction.SAVE:
        chooser.set_current_name(current_name)
    dialog.content.pack_start(chooser, True, True, 0)

    chosen: dict[str, str | None] = {"path": None}

    def accept(_widget=None) -> None:
        path = chooser.get_filename()
        if not path:
            dialog.respond(None)
            return
        if (
            overwrite_confirmation
            and action == Gtk.FileChooserAction.SAVE
            and Path(path).exists()
            and not fos_confirm(
                dialog,
                "Replace file?",
                f"“{Path(path).name}” already exists. Replace it?",
                ok="Replace",
                destructive=True,
            )
        ):
            return
        chosen["path"] = path
        dialog.respond(True)

    dialog.add_action("Cancel", None, variant="ghost")
    ok_btn = button(ok_label, variant="default", size="sm")
    ok_btn.set_can_focus(True)
    ok_btn.set_can_default(True)
    ok_btn.connect("clicked", accept)
    dialog.footer.pack_start(ok_btn, False, False, 0)
    chooser.connect("file-activated", accept)

    if dialog.run() is not True:
        return None
    return chosen["path"]
