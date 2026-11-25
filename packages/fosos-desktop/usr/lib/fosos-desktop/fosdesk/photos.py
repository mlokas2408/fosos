"""FosOS Photos: simple CardWindow image preview and basic edit."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
import cairo
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, PangoCairo

from .apps import user_dir
from .filechooser import ChooserFilter
from .ui import (
    add_classes,
    button,
    fos_choice,
    fos_confirm,
    fos_file_chooser,
    label,
    load_css,
    set_class,
)
from .windowchrome import CardWindow

APP_ID = "org.fosos.Photos"

IMAGE_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".ico",
    ".tga",
    ".webp",
}

IMAGE_FILTER = ChooserFilter(
    "Images",
    [
        (0, "*.jpg"),
        (0, "*.jpeg"),
        (0, "*.png"),
        (0, "*.gif"),
        (0, "*.bmp"),
        (0, "*.tif"),
        (0, "*.tiff"),
        (0, "*.ico"),
        (0, "*.webp"),
        (1, "image/*"),
    ],
)

SAVE_FILTER = ChooserFilter(
    "Images",
    [
        (0, "*.png"),
        (0, "*.jpg"),
        (0, "*.jpeg"),
        (0, "*.bmp"),
        (0, "*.tif"),
        (0, "*.tiff"),
    ],
)


def is_image_path(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTS


def list_siblings(path: Path) -> list[Path]:
    folder = path.parent
    try:
        items = [p for p in folder.iterdir() if is_image_path(p)]
    except OSError:
        return [path] if path.is_file() else []
    items.sort(key=lambda p: p.name.lower())
    return items


def save_format_for(path: Path) -> str | None:
    ext = path.suffix.lower()
    mapping = {
        ".png": "png",
        ".jpg": "jpeg",
        ".jpeg": "jpeg",
        ".bmp": "bmp",
        ".tif": "tiff",
        ".tiff": "tiff",
        ".ico": "ico",
        ".tga": "tga",
    }
    return mapping.get(ext)


def load_pixbuf(path: Path) -> GdkPixbuf.Pixbuf:
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
    oriented = pixbuf.apply_embedded_orientation()
    return oriented if oriented is not None else pixbuf


class PhotosWindow(CardWindow):
    def __init__(self, app: "PhotosApp", open_path: Path | None = None) -> None:
        super().__init__(
            app,
            title="Photos",
            icon_name="image-x-generic-symbolic",
            default_width=1000,
            default_height=700,
        )
        self.set_icon_name("image-x-generic")
        add_classes(self, "fos-photos-shell")
        self.app = app

        self.path: Path | None = None
        self.siblings: list[Path] = []
        self.pixbuf: GdkPixbuf.Pixbuf | None = None
        self._history: list[GdkPixbuf.Pixbuf] = []
        self._dirty = False
        self._fit = True
        self._zoom = 1.0
        self._cropping = False
        self._crop_origin: tuple[float, float] | None = None
        self._crop_current: tuple[float, float] | None = None
        self._img_rect: tuple[float, float, float, float] = (0, 0, 0, 0)
        self._redraw_queued = False

        toolbar = add_classes(Gtk.Box(spacing=4), "fos-app-toolbar", "fos-photos-toolbar")

        open_btn = button("Open", icon_name="document-open-symbolic", variant="outline", size="sm")
        open_btn.connect("clicked", lambda _b: self.choose_file())
        toolbar.pack_start(open_btn, False, False, 0)

        self.prev_btn = button(None, icon_name="go-previous-symbolic", variant="ghost", size="sm", tooltip="Previous (←)")
        self.prev_btn.connect("clicked", lambda _b: self.step(-1))
        toolbar.pack_start(self.prev_btn, False, False, 0)
        self.next_btn = button(None, icon_name="go-next-symbolic", variant="ghost", size="sm", tooltip="Next (→)")
        self.next_btn.connect("clicked", lambda _b: self.step(1))
        toolbar.pack_start(self.next_btn, False, False, 0)

        toolbar.pack_start(add_classes(Gtk.Separator.new(Gtk.Orientation.VERTICAL), "fos-photos-sep"), False, False, 4)

        zoom_out = button(None, icon_name="zoom-out-symbolic", variant="ghost", size="sm", tooltip="Zoom out")
        zoom_out.connect("clicked", lambda _b: self.zoom_by(1 / 1.25))
        toolbar.pack_start(zoom_out, False, False, 0)
        zoom_in = button(None, icon_name="zoom-in-symbolic", variant="ghost", size="sm", tooltip="Zoom in")
        zoom_in.connect("clicked", lambda _b: self.zoom_by(1.25))
        toolbar.pack_start(zoom_in, False, False, 0)
        self.fit_btn = button(None, icon_name="zoom-fit-best-symbolic", variant="ghost", size="sm", tooltip="Fit to window")
        self.fit_btn.connect("clicked", lambda _b: self.set_fit(True))
        toolbar.pack_start(self.fit_btn, False, False, 0)
        actual_btn = button(None, icon_name="zoom-original-symbolic", variant="ghost", size="sm", tooltip="Actual size (100%)")
        actual_btn.connect("clicked", lambda _b: self.set_actual())
        toolbar.pack_start(actual_btn, False, False, 0)

        toolbar.pack_start(add_classes(Gtk.Separator.new(Gtk.Orientation.VERTICAL), "fos-photos-sep"), False, False, 4)

        rot_l = button(None, icon_name="object-rotate-left-symbolic", variant="ghost", size="sm", tooltip="Rotate left")
        rot_l.connect("clicked", lambda _b: self.rotate(GdkPixbuf.PixbufRotation.COUNTERCLOCKWISE))
        toolbar.pack_start(rot_l, False, False, 0)
        rot_r = button(None, icon_name="object-rotate-right-symbolic", variant="ghost", size="sm", tooltip="Rotate right")
        rot_r.connect("clicked", lambda _b: self.rotate(GdkPixbuf.PixbufRotation.CLOCKWISE))
        toolbar.pack_start(rot_r, False, False, 0)
        flip_h = button(None, icon_name="object-flip-horizontal-symbolic", variant="ghost", size="sm", tooltip="Flip horizontal")
        flip_h.connect("clicked", lambda _b: self.flip(True))
        toolbar.pack_start(flip_h, False, False, 0)
        flip_v = button(None, icon_name="object-flip-vertical-symbolic", variant="ghost", size="sm", tooltip="Flip vertical")
        flip_v.connect("clicked", lambda _b: self.flip(False))
        toolbar.pack_start(flip_v, False, False, 0)

        self.crop_btn = button("Crop", icon_name="edit-cut-symbolic", variant="outline", size="sm", tooltip="Crop (drag a region)")
        self.crop_btn.connect("clicked", lambda _b: self.toggle_crop())
        toolbar.pack_start(self.crop_btn, False, False, 0)

        self.undo_btn = button("Undo", icon_name="edit-undo-symbolic", variant="ghost", size="sm", tooltip="Undo (Ctrl+Z)")
        self.undo_btn.connect("clicked", lambda _b: self.undo())
        toolbar.pack_start(self.undo_btn, False, False, 0)

        toolbar.pack_start(Gtk.Box(), True, True, 0)

        self.save_btn = button("Save", icon_name="document-save-symbolic", variant="default", size="sm", tooltip="Save (Ctrl+S)")
        self.save_btn.connect("clicked", lambda _b: self.save())
        toolbar.pack_start(self.save_btn, False, False, 0)
        save_as = button("Save as", icon_name="document-save-as-symbolic", variant="outline", size="sm")
        save_as.connect("clicked", lambda _b: self.save_as())
        toolbar.pack_start(save_as, False, False, 0)
        self.body.pack_start(toolbar, False, False, 0)

        self.stage = add_classes(Gtk.DrawingArea(), "fos-photos-stage")
        self.stage.set_hexpand(True)
        self.stage.set_vexpand(True)
        self.stage.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.SMOOTH_SCROLL_MASK
        )
        self.stage.connect("draw", self._on_draw)
        self.stage.connect("size-allocate", lambda *_a: self.queue_redraw())
        self.stage.connect("button-press-event", self._on_button_press)
        self.stage.connect("button-release-event", self._on_button_release)
        self.stage.connect("motion-notify-event", self._on_motion)
        self.stage.connect("scroll-event", self._on_scroll)
        self.body.pack_start(self.stage, True, True, 0)

        self.crop_bar = add_classes(Gtk.Box(spacing=8), "fos-photos-cropbar")
        self.crop_bar.set_no_show_all(True)
        self.crop_bar.hide()
        self.crop_bar.pack_start(
            label("Drag to select a region, then Apply.", "fos-small", "fos-muted"),
            True,
            True,
            0,
        )
        apply_crop = button("Apply crop", variant="default", size="sm")
        apply_crop.connect("clicked", lambda _b: self.apply_crop())
        cancel_crop = button("Cancel", variant="ghost", size="sm")
        cancel_crop.connect("clicked", lambda _b: self.set_cropping(False))
        self.crop_bar.pack_start(cancel_crop, False, False, 0)
        self.crop_bar.pack_start(apply_crop, False, False, 0)
        self.body.pack_start(self.crop_bar, False, False, 0)

        footer = add_classes(Gtk.Box(spacing=12), "fos-app-footer")
        self.status = label("Open an image to preview.", "fos-small", "fos-muted", ellipsize=True)
        footer.pack_start(self.status, True, True, 0)
        self.body.pack_start(footer, False, False, 0)

        self.connect("destroy", self._on_destroy)
        self.connect("key-press-event", self._on_key)
        self.connect("delete-event", self._on_delete_event)
        self._refresh_actions()

        if open_path is not None:
            GLib.idle_add(self.open_path, open_path)

    def _on_destroy(self, *_args) -> None:
        return

    def _on_delete_event(self, *_args) -> bool:
        if not self._ensure_can_leave():
            return True
        return False

    def _on_key(self, _w, event: Gdk.EventKey) -> bool:
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        key = event.keyval
        if ctrl and key in (Gdk.KEY_o, Gdk.KEY_O):
            self.choose_file()
            return True
        if ctrl and key in (Gdk.KEY_s, Gdk.KEY_S):
            self.save()
            return True
        if ctrl and key in (Gdk.KEY_z, Gdk.KEY_Z):
            self.undo()
            return True
        if key == Gdk.KEY_Escape:
            if self._cropping:
                self.set_cropping(False)
                return True
            return False
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and self._cropping:
            self.apply_crop()
            return True
        if key == Gdk.KEY_Left and not ctrl:
            self.step(-1)
            return True
        if key == Gdk.KEY_Right and not ctrl:
            self.step(1)
            return True
        if key in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            self.zoom_by(1.25)
            return True
        if key in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            self.zoom_by(1 / 1.25)
            return True
        if key in (Gdk.KEY_0, Gdk.KEY_KP_0):
            self.set_fit(True)
            return True
        if key in (Gdk.KEY_1, Gdk.KEY_KP_1):
            self.set_actual()
            return True
        if key in (Gdk.KEY_r, Gdk.KEY_R) and not ctrl:
            self.rotate(GdkPixbuf.PixbufRotation.CLOCKWISE)
            return True
        if key in (Gdk.KEY_l, Gdk.KEY_L) and not ctrl:
            self.rotate(GdkPixbuf.PixbufRotation.COUNTERCLOCKWISE)
            return True
        if key == Gdk.KEY_Delete and self.path is not None:
            self.delete_current()
            return True
        return False

    def _ensure_can_leave(self) -> bool:
        if not self._dirty:
            return True
        choice = fos_choice(
            self,
            "Save changes?",
            "This image has unsaved edits.",
            [
                ("Cancel", "cancel", "ghost"),
                ("Don't save", "discard", "outline"),
                ("Save", "save", "default"),
            ],
        )
        if choice == "save":
            return self.save()
        return choice == "discard"

    def choose_file(self) -> None:
        if not self._ensure_can_leave():
            return
        pictures = user_dir(GLib.UserDirectory.DIRECTORY_PICTURES, "Pictures")
        filename = fos_file_chooser(
            self,
            title="Open image",
            action=Gtk.FileChooserAction.OPEN,
            ok_label="Open",
            folder=pictures if self.path is None else self.path.parent,
            filters=[IMAGE_FILTER, ChooserFilter("All files", [(0, "*")])],
        )
        if filename:
            self.open_path(Path(filename))

    def open_path(self, path: Path) -> bool:
        path = path.expanduser()
        try:
            path = path.resolve()
        except OSError:
            pass
        if not path.is_file():
            self.status.set_text(f"File not found: {path}")
            return False
        try:
            pixbuf = load_pixbuf(path)
        except GLib.Error as exc:
            self.status.set_text(f"Could not open: {exc}")
            print(f"fosos-photos: open failed: {exc}", file=sys.stderr)
            return False

        self.path = path
        self.siblings = list_siblings(path)
        self.pixbuf = pixbuf
        self._history.clear()
        self._dirty = False
        self._fit = True
        self._zoom = 1.0
        self.set_cropping(False)
        self.set_header_title(path.name)
        self.queue_redraw()
        self._refresh_actions()
        self._refresh_status()
        return False  # for idle_add

    def step(self, delta: int) -> None:
        if self.path is None or not self.siblings:
            return
        if not self._ensure_can_leave():
            return
        try:
            index = self.siblings.index(self.path)
        except ValueError:
            self.siblings = list_siblings(self.path)
            try:
                index = self.siblings.index(self.path)
            except ValueError:
                return
        nxt = self.siblings[(index + delta) % len(self.siblings)]
        if nxt != self.path:
            self.open_path(nxt)

    def _push_history(self) -> None:
        if self.pixbuf is None:
            return
        self._history.append(self.pixbuf.copy())
        if len(self._history) > 30:
            self._history.pop(0)

    def _set_pixbuf(self, pixbuf: GdkPixbuf.Pixbuf, *, dirty: bool = True) -> None:
        self.pixbuf = pixbuf
        self._dirty = dirty
        self.queue_redraw()
        self._refresh_actions()
        self._refresh_status()

    def rotate(self, rotation: GdkPixbuf.PixbufRotation) -> None:
        if self.pixbuf is None:
            return
        self._push_history()
        rotated = self.pixbuf.rotate_simple(rotation)
        if rotated is not None:
            self._set_pixbuf(rotated)

    def flip(self, horizontal: bool) -> None:
        if self.pixbuf is None:
            return
        self._push_history()
        flipped = self.pixbuf.flip(horizontal)
        if flipped is not None:
            self._set_pixbuf(flipped)

    def undo(self) -> None:
        if not self._history:
            return
        self.pixbuf = self._history.pop()
        # Empty history means we are back to the loaded file.
        self._dirty = bool(self._history)
        self.queue_redraw()
        self._refresh_actions()
        self._refresh_status()

    def toggle_crop(self) -> None:
        if self.pixbuf is None:
            return
        self.set_cropping(not self._cropping)

    def set_cropping(self, enabled: bool) -> None:
        self._cropping = enabled and self.pixbuf is not None
        self._crop_origin = None
        self._crop_current = None
        set_class(self.crop_btn, "active", self._cropping)
        if self._cropping:
            self.crop_bar.set_no_show_all(False)
            self.crop_bar.show_all()
        else:
            self.crop_bar.hide()
            self.crop_bar.set_no_show_all(True)
        self.queue_redraw()

    def apply_crop(self) -> None:
        if self.pixbuf is None or not self._cropping:
            return
        rect = self._crop_image_rect()
        if rect is None:
            self.status.set_text("Drag a crop region first.")
            return
        x, y, w, h = rect
        if w < 2 or h < 2:
            self.status.set_text("Crop region is too small.")
            return
        self._push_history()
        cropped = self.pixbuf.new_subpixbuf(x, y, w, h)
        if cropped is None:
            return
        # Subpixbuf shares memory; copy so later edits are safe.
        self._set_pixbuf(cropped.copy())
        self.set_cropping(False)

    def zoom_by(self, factor: float) -> None:
        if self.pixbuf is None:
            return
        if self._fit:
            # Leave fit mode using current fitted scale as baseline.
            fitted = self._fitted_zoom()
            self._zoom = max(0.05, min(8.0, fitted * factor))
            self._fit = False
        else:
            self._zoom = max(0.05, min(8.0, self._zoom * factor))
        self.queue_redraw()
        self._refresh_status()

    def set_fit(self, enabled: bool = True) -> None:
        self._fit = enabled
        if enabled:
            self._zoom = 1.0
        self.queue_redraw()
        self._refresh_status()

    def set_actual(self) -> None:
        self._fit = False
        self._zoom = 1.0
        self.queue_redraw()
        self._refresh_status()

    def save(self) -> bool:
        if self.pixbuf is None or self.path is None:
            return False
        fmt = save_format_for(self.path)
        if fmt is None:
            return self.save_as()
        return self._write(self.path, fmt)

    def save_as(self) -> bool:
        if self.pixbuf is None:
            return False
        pictures = user_dir(GLib.UserDirectory.DIRECTORY_PICTURES, "Pictures")
        suggested = self.path.name if self.path is not None else "Photo.png"
        if self.path is not None and save_format_for(self.path) is None:
            suggested = self.path.with_suffix(".png").name
        filename = fos_file_chooser(
            self,
            title="Save image",
            action=Gtk.FileChooserAction.SAVE,
            ok_label="Save",
            folder=self.path.parent if self.path is not None else pictures,
            current_name=suggested,
            overwrite_confirmation=True,
            filters=[SAVE_FILTER, ChooserFilter("All files", [(0, "*")])],
        )
        if not filename:
            return False
        path = Path(filename)
        if path.suffix == "":
            path = path.with_suffix(".png")
        fmt = save_format_for(path)
        if fmt is None:
            path = path.with_suffix(".png")
            fmt = "png"
        if not self._write(path, fmt):
            return False
        self.path = path
        self.siblings = list_siblings(path)
        self.set_header_title(path.name)
        self._refresh_actions()
        self._refresh_status()
        return True

    def _write(self, path: Path, fmt: str) -> bool:
        if self.pixbuf is None:
            return False
        try:
            if fmt == "jpeg":
                self.pixbuf.savev(str(path), "jpeg", ["quality"], ["92"])
            else:
                self.pixbuf.savev(str(path), fmt, [], [])
        except GLib.Error as exc:
            self.status.set_text(f"Save failed: {exc}")
            print(f"fosos-photos: save failed: {exc}", file=sys.stderr)
            return False
        self.path = path
        self._dirty = False
        self._history.clear()
        self.status.set_text(f"Saved {path.name}")
        self._refresh_actions()
        return True

    def delete_current(self) -> None:
        if self.path is None:
            return
        if not fos_confirm(
            self,
            "Delete image?",
            f"Move {self.path.name} to trash?",
            ok="Delete",
            destructive=True,
        ):
            return
        trash_path = self.path
        try:
            old_index = self.siblings.index(trash_path)
        except ValueError:
            old_index = 0
        siblings = [p for p in self.siblings if p != trash_path]
        try:
            Gio.File.new_for_path(str(trash_path)).trash(None)
        except GLib.Error as exc:
            self.status.set_text(f"Delete failed: {exc}")
            return
        self._dirty = False
        self._history.clear()
        if siblings:
            nxt = siblings[min(old_index, len(siblings) - 1)]
            self.open_path(nxt)
        else:
            self.path = None
            self.siblings = []
            self.pixbuf = None
            self.set_header_title("Photos")
            self.queue_redraw()
            self._refresh_actions()
            self.status.set_text("Image deleted.")

    def _refresh_actions(self) -> None:
        has = self.pixbuf is not None
        self.prev_btn.set_sensitive(has and len(self.siblings) > 1)
        self.next_btn.set_sensitive(has and len(self.siblings) > 1)
        self.crop_btn.set_sensitive(has)
        self.undo_btn.set_sensitive(bool(self._history))
        self.save_btn.set_sensitive(has and self._dirty)

    def _fitted_zoom(self) -> float:
        if self.pixbuf is None:
            return 1.0
        alloc = self.stage.get_allocation()
        aw = max(1, alloc.width - 24)
        ah = max(1, alloc.height - 24)
        iw = self.pixbuf.get_width()
        ih = self.pixbuf.get_height()
        return min(aw / iw, ah / ih, 1.0)

    def _current_zoom(self) -> float:
        if self._fit:
            return self._fitted_zoom()
        return self._zoom

    def _refresh_status(self) -> None:
        if self.pixbuf is None or self.path is None:
            self.status.set_text("Open an image to preview.")
            return
        z = int(round(self._current_zoom() * 100))
        dirty = " · edited" if self._dirty else ""
        index = ""
        if self.siblings:
            try:
                index = f" · {self.siblings.index(self.path) + 1}/{len(self.siblings)}"
            except ValueError:
                index = ""
        self.status.set_text(
            f"{self.path.name} · {self.pixbuf.get_width()}×{self.pixbuf.get_height()} · {z}%{index}{dirty}"
        )

    def queue_redraw(self) -> None:
        if self._redraw_queued:
            return
        self._redraw_queued = True

        def _run() -> bool:
            self._redraw_queued = False
            self.stage.queue_draw()
            return False

        GLib.idle_add(_run)

    def _on_draw(self, _area: Gtk.DrawingArea, cr) -> bool:
        alloc = self.stage.get_allocation()
        cr.set_source_rgb(0.06, 0.06, 0.07)
        cr.rectangle(0, 0, alloc.width, alloc.height)
        cr.fill()

        if self.pixbuf is None:
            layout = self.stage.create_pango_layout("Open an image to preview.")
            _ink, logical = layout.get_pixel_extents()
            cr.set_source_rgba(1, 1, 1, 0.45)
            cr.move_to((alloc.width - logical.width) / 2, (alloc.height - logical.height) / 2)
            PangoCairo.show_layout(cr, layout)
            return False

        zoom = self._current_zoom()
        iw = self.pixbuf.get_width()
        ih = self.pixbuf.get_height()
        dw = max(1, int(round(iw * zoom)))
        dh = max(1, int(round(ih * zoom)))
        x = (alloc.width - dw) / 2
        y = (alloc.height - dh) / 2
        self._img_rect = (x, y, dw, dh)

        if zoom == 1.0:
            Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, x, y)
        else:
            scaled = self.pixbuf.scale_simple(dw, dh, GdkPixbuf.InterpType.BILINEAR)
            if scaled is None:
                return False
            Gdk.cairo_set_source_pixbuf(cr, scaled, x, y)
        cr.paint()

        if self._cropping:
            sel = self._crop_widget_rect()
            cr.set_source_rgba(0, 0, 0, 0.45)
            cr.rectangle(0, 0, alloc.width, alloc.height)
            if sel is not None:
                sx, sy, sw, sh = sel
                cr.rectangle(sx, sy, sw, sh)
                cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            cr.fill()
            if sel is not None:
                sx, sy, sw, sh = sel
                cr.set_source_rgba(1, 1, 1, 0.95)
                cr.set_line_width(1.5)
                cr.rectangle(sx + 0.5, sy + 0.5, max(0, sw - 1), max(0, sh - 1))
                cr.stroke()
        return False

    def _crop_widget_rect(self) -> tuple[float, float, float, float] | None:
        if self._crop_origin is None or self._crop_current is None:
            return None
        x0, y0 = self._crop_origin
        x1, y1 = self._crop_current
        ix, iy, iw, ih = self._img_rect
        left = max(ix, min(x0, x1))
        top = max(iy, min(y0, y1))
        right = min(ix + iw, max(x0, x1))
        bottom = min(iy + ih, max(y0, y1))
        if right - left < 1 or bottom - top < 1:
            return None
        return (left, top, right - left, bottom - top)

    def _crop_image_rect(self) -> tuple[int, int, int, int] | None:
        if self.pixbuf is None:
            return None
        sel = self._crop_widget_rect()
        if sel is None:
            return None
        sx, sy, sw, sh = sel
        ix, iy, iw, ih = self._img_rect
        if iw <= 0 or ih <= 0:
            return None
        pw = self.pixbuf.get_width()
        ph = self.pixbuf.get_height()
        x = int(round((sx - ix) / iw * pw))
        y = int(round((sy - iy) / ih * ph))
        w = int(round(sw / iw * pw))
        h = int(round(sh / ih * ph))
        x = max(0, min(pw - 1, x))
        y = max(0, min(ph - 1, y))
        w = max(1, min(pw - x, w))
        h = max(1, min(ph - y, h))
        return (x, y, w, h)

    def _on_button_press(self, _w, event: Gdk.EventButton) -> bool:
        if self.pixbuf is None:
            if event.button == 1:
                self.choose_file()
                return True
            return False
        if self._cropping and event.button == 1:
            self._crop_origin = (event.x, event.y)
            self._crop_current = (event.x, event.y)
            self.queue_redraw()
            return True
        return False

    def _on_button_release(self, _w, event: Gdk.EventButton) -> bool:
        if self._cropping and event.button == 1 and self._crop_origin is not None:
            self._crop_current = (event.x, event.y)
            self.queue_redraw()
            return True
        return False

    def _on_motion(self, _w, event: Gdk.EventMotion) -> bool:
        if self._cropping and self._crop_origin is not None and (event.state & Gdk.ModifierType.BUTTON1_MASK):
            self._crop_current = (event.x, event.y)
            self.queue_redraw()
            return True
        return False

    def _on_scroll(self, _w, event: Gdk.EventScroll) -> bool:
        if self.pixbuf is None:
            return False
        dy = 0.0
        if event.direction == Gdk.ScrollDirection.UP:
            dy = -1
        elif event.direction == Gdk.ScrollDirection.DOWN:
            dy = 1
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            dy = event.delta_y
        if abs(dy) < 0.01:
            return False
        self.zoom_by(1.25 if dy < 0 else 1 / 1.25)
        return True


class PhotosApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_OPEN | Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.window: PhotosWindow | None = None
        self._pending: Path | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_prgname("fosos-photos")
        GLib.set_application_name("Photos")
        load_css()

    def do_activate(self) -> None:
        if self.window is None:
            self.window = PhotosWindow(self, open_path=self._pending)
            self._pending = None
            self.window.show_all()
            if not self.window._cropping:
                self.window.crop_bar.hide()
        self.window.present()

    def do_open(self, files, _n_files, _hint) -> None:
        path: Path | None = None
        for f in files:
            candidate = Path(f.get_path() or "")
            if candidate.is_file():
                path = candidate
                break
        if path is None:
            self.do_activate()
            return
        if self.window is None:
            self._pending = path
            self.do_activate()
            return
        if not self.window._ensure_can_leave():
            self.window.present()
            return
        self.window.open_path(path)
        self.window.present()

    def do_command_line(self, command_line):
        argv = command_line.get_arguments()[1:]
        path: Path | None = None
        for arg in argv:
            candidate = Path(arg).expanduser()
            if candidate.is_file():
                path = candidate
                break
        if path is not None:
            if self.window is None:
                self._pending = path
                self.do_activate()
            else:
                if self.window._ensure_can_leave():
                    self.window.open_path(path)
                self.window.present()
        else:
            self.do_activate()
        return 0


def main() -> int:
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print("fosos-photos: no display available", file=sys.stderr)
        return 1
    return PhotosApp().run(sys.argv)
