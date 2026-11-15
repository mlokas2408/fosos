"""FosOS Notepad: a simple plain-text editor."""

from __future__ import annotations

import sys
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from .ui import add_classes, button, label, load_css, separator
from .windowchrome import CardWindow

APP_ID = "org.fosos.Notepad"


class EditorWindow(CardWindow):
    def __init__(self, app: "EditorApp", path: Path | None = None) -> None:
        super().__init__(
            app,
            title="Untitled - Notepad",
            icon_name="accessories-text-editor-symbolic",
            default_width=720,
            default_height=520,
        )
        self.app = app
        self.path: Path | None = None
        self._dirty = False
        self._loading = False

        toolbar = add_classes(Gtk.Box(spacing=4), "fos-app-toolbar")
        for text, handler, tip in (
            ("New", self.new_file, "New (Ctrl+N)"),
            ("Open", self.open_file, "Open (Ctrl+O)"),
            ("Save", self.save_file, "Save (Ctrl+S)"),
            ("Save as", self.save_file_as, "Save as (Ctrl+Shift+S)"),
        ):
            btn = button(text, variant="ghost", size="sm", tooltip=tip)
            btn.connect("clicked", lambda _b, h=handler: h())
            toolbar.pack_start(btn, False, False, 0)
        toolbar.pack_start(separator(length=22), False, False, 4)
        self.wrap_btn = button("Wrap", variant="ghost", size="sm", tooltip="Toggle word wrap")
        self.wrap_btn.connect("clicked", lambda _b: self.toggle_wrap())
        toolbar.pack_start(self.wrap_btn, False, False, 0)
        self.body.pack_start(toolbar, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        self.view = Gtk.TextView()
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_left_margin(12)
        self.view.set_right_margin(12)
        self.view.set_top_margin(10)
        self.view.set_bottom_margin(10)
        self.view.override_font(Pango.FontDescription.from_string("Liberation Mono 11"))
        add_classes(self.view, "fos-editor-view")
        self.buffer = self.view.get_buffer()
        self.buffer.connect("changed", self._on_changed)
        scroller.add(self.view)
        self.body.pack_start(scroller, True, True, 0)

        self.footer = add_classes(Gtk.Box(spacing=12), "fos-app-footer")
        self.status = label("Ready", "fos-small", "fos-muted")
        self.footer.pack_start(self.status, True, True, 0)
        self.body.pack_start(self.footer, False, False, 0)

        self.connect("key-press-event", self._on_key)
        self.connect("delete-event", self._on_delete)
        if path is not None and path.is_file():
            self.load_path(path)
        else:
            self._update_title()

    def _update_title(self) -> None:
        name = self.path.name if self.path is not None else "Untitled"
        mark = "* " if self._dirty else ""
        self.set_header_title(f"{mark}{name} - Notepad")
        self.set_badge(self.path.parent.name if self.path is not None else None)

    def _on_changed(self, _buffer) -> None:
        if self._loading:
            return
        if not self._dirty:
            self._dirty = True
            self._update_title()
        start, end = self.buffer.get_bounds()
        text = self.buffer.get_text(start, end, True)
        lines = text.count("\n") + (1 if text else 0)
        self.status.set_text(f"{lines} lines · {len(text)} characters")

    def toggle_wrap(self) -> None:
        if self.view.get_wrap_mode() == Gtk.WrapMode.NONE:
            self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            self.status.set_text("Word wrap on")
        else:
            self.view.set_wrap_mode(Gtk.WrapMode.NONE)
            self.status.set_text("Word wrap off")

    def new_file(self) -> None:
        if not self._confirm_discard():
            return
        self.path = None
        self._loading = True
        self.buffer.set_text("")
        self._loading = False
        self._dirty = False
        self._update_title()
        self.status.set_text("New document")

    def open_file(self) -> None:
        if not self._confirm_discard():
            return
        dialog = Gtk.FileChooserDialog(
            title="Open",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Open", Gtk.ResponseType.OK)
        filt = Gtk.FileFilter()
        filt.set_name("Text files")
        filt.add_mime_type("text/plain")
        filt.add_pattern("*.txt")
        filt.add_pattern("*.md")
        filt.add_pattern("*.log")
        filt.add_pattern("*.csv")
        dialog.add_filter(filt)
        all_filt = Gtk.FileFilter()
        all_filt.set_name("All files")
        all_filt.add_pattern("*")
        dialog.add_filter(all_filt)
        response = dialog.run()
        filename = dialog.get_filename()
        dialog.destroy()
        if response == Gtk.ResponseType.OK and filename:
            self.load_path(Path(filename))

    def load_path(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = path.read_text(encoding="latin-1")
            except OSError as exc:
                self.status.set_text(f"Could not open: {exc}")
                return
        except OSError as exc:
            self.status.set_text(f"Could not open: {exc}")
            return
        self.path = path
        self._loading = True
        self.buffer.set_text(text)
        self._loading = False
        self._dirty = False
        self._update_title()
        self.status.set_text(str(path))

    def save_file(self) -> bool:
        if self.path is None:
            return self.save_file_as()
        return self._write(self.path)

    def save_file_as(self) -> bool:
        dialog = Gtk.FileChooserDialog(
            title="Save as",
            transient_for=self,
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Save", Gtk.ResponseType.OK)
        dialog.set_do_overwrite_confirmation(True)
        if self.path is not None:
            dialog.set_filename(str(self.path))
        else:
            dialog.set_current_name("Untitled.txt")
        response = dialog.run()
        filename = dialog.get_filename()
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not filename:
            return False
        return self._write(Path(filename))

    def _write(self, path: Path) -> bool:
        start, end = self.buffer.get_bounds()
        text = self.buffer.get_text(start, end, True)
        try:
            path.write_text(text, encoding="utf-8")
        except OSError as exc:
            self.status.set_text(f"Could not save: {exc}")
            return False
        self.path = path
        self._dirty = False
        self._update_title()
        self.status.set_text(f"Saved {path}")
        return True

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text="Save changes?",
        )
        dialog.format_secondary_text("Your document has unsaved changes.")
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Don't save", Gtk.ResponseType.REJECT)
        dialog.add_button("Save", Gtk.ResponseType.ACCEPT)
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.CANCEL:
            return False
        if response == Gtk.ResponseType.ACCEPT:
            return self.save_file()
        return True

    def _on_delete(self, _window, _event) -> bool:
        if self._confirm_discard():
            return False
        return True

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        key = (Gdk.keyval_name(event.keyval) or "").lower()
        if ctrl and not shift and key == "n":
            self.new_file()
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
        return False


class EditorApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_OPEN | Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.window: EditorWindow | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_prgname("fosos-notepad")
        GLib.set_application_name("Notepad")
        load_css()

    def do_activate(self) -> None:
        self._ensure_window(None)
        self.window.present()

    def do_open(self, files, _n_files, _hint) -> None:
        path = None
        if files:
            candidate = Path(files[0].get_path() or "")
            if candidate.is_file():
                path = candidate
        self._ensure_window(path)
        self.window.present()

    def do_command_line(self, command_line):
        argv = command_line.get_arguments()[1:]
        path = None
        if argv:
            candidate = Path(argv[0]).expanduser()
            if candidate.is_file():
                path = candidate
        self._ensure_window(path)
        self.window.present()
        return 0

    def _ensure_window(self, path: Path | None) -> None:
        if self.window is None:
            self.window = EditorWindow(self, path=path)
            self.window.show_all()
        elif path is not None:
            if self.window._confirm_discard():
                self.window.load_path(path)


def main() -> int:
    return EditorApp().run(sys.argv)
