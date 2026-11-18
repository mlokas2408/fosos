"""Win+V clipboard history: watch text copies and paste from a FosOS popup."""

from __future__ import annotations

import json
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from .popup import Popup
from .ui import add_classes, button, clear, label

HISTORY_LIMIT = 25
HISTORY_FILE = Path(GLib.get_user_config_dir()) / "fosos-desktop" / "clipboard-history"
PREVIEW_CHARS = 96


def _send_ctrl_v() -> bool:
    """Synthesize Ctrl+V into the focused X client."""
    try:
        from Xlib import XK, X, display
        from Xlib.ext import xtest
    except Exception:
        return False
    try:
        dpy = display.Display()
        ctrl = dpy.keysym_to_keycode(XK.string_to_keysym("Control_L"))
        key_v = dpy.keysym_to_keycode(XK.string_to_keysym("v"))
        if not ctrl or not key_v:
            return False
        xtest.fake_input(dpy, X.KeyPress, ctrl)
        xtest.fake_input(dpy, X.KeyPress, key_v)
        xtest.fake_input(dpy, X.KeyRelease, key_v)
        xtest.fake_input(dpy, X.KeyRelease, ctrl)
        dpy.sync()
        return True
    except Exception:
        return False


class ClipboardHistory:
    """In-memory + on-disk text clipboard history."""

    def __init__(self) -> None:
        self.items: list[str] = []
        self._load()
        self._clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self._clip.connect("owner-change", self._on_owner_change)
        # Catch the first value if something was already copied.
        GLib.idle_add(self._poll_once)

    def _poll_once(self) -> bool:
        self._clip.request_text(self._on_text, None)
        return False

    def _on_owner_change(self, _clipboard, _event) -> None:
        self._clip.request_text(self._on_text, None)

    def _on_text(self, _clipboard, text, _data) -> None:
        if not text or not text.strip():
            return
        # Ignore our own paste-selection writes that match the newest item.
        if self.items and self.items[0] == text:
            return
        self.items = [t for t in self.items if t != text]
        self.items.insert(0, text)
        del self.items[HISTORY_LIMIT:]
        self._save()

    def clear(self) -> None:
        self.items = []
        self._save()

    def _load(self) -> None:
        if not HISTORY_FILE.is_file():
            return
        try:
            raw = HISTORY_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, list):
                self.items = [str(item) for item in data if str(item).strip()][:HISTORY_LIMIT]
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            self.items = []

    def _save(self) -> None:
        try:
            HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            HISTORY_FILE.write_text(json.dumps(self.items, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


class ClipboardPopup(Popup):
    def __init__(self, shell) -> None:
        super().__init__(width=420)
        self.shell = shell
        self._nav: list[str] = []
        self._nav_index = -1

        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)

        header = add_classes(Gtk.Box(spacing=8), "fos-card-header")
        header.pack_start(label("Clipboard", "fos-title"), True, True, 0)
        clear_btn = button("Clear all", variant="ghost", size="sm")
        clear_btn.connect("clicked", lambda _b: self._clear_all())
        header.pack_end(clear_btn, False, False, 0)
        frame.pack_start(header, False, False, 0)

        body = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), "fos-card-content")
        frame.pack_start(body, True, True, 0)
        tip = label("Super+V · pick an item to paste", "fos-small", "fos-muted")
        body.pack_start(tip, False, False, 0)

        self.items_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(200)
        scroller.set_max_content_height(360)
        scroller.set_propagate_natural_height(True)
        scroller.add(self.items_box)
        body.pack_start(scroller, True, True, 0)

    def open_near_panel(self) -> None:
        panel = self.shell.panel
        if panel is None:
            return
        if self.get_visible():
            self.dismiss()
            return
        self.shell.close_popups(keep="clipboard")
        self.refresh()
        area = panel.area()
        # Anchor toward the right status area (near clock).
        x = area.x + area.width - self.width - 12
        self.show_at(x, panel.top(), area)

    def refresh(self) -> None:
        clear(self.items_box)
        self._nav = []
        self._nav_index = -1
        history = self.shell.clipboard_history
        if not history.items:
            empty = label("Clipboard history is empty.", "fos-text", "fos-muted")
            empty.set_margin_top(12)
            empty.set_margin_bottom(12)
            self.items_box.pack_start(empty, False, False, 0)
        else:
            for text in history.items:
                self._nav.append(text)
                row = button(variant="ghost")
                add_classes(row, "row")
                preview = text.replace("\n", " ").strip()
                if len(preview) > PREVIEW_CHARS:
                    preview = preview[: PREVIEW_CHARS - 1] + "…"
                row_label = label(preview, "fos-text", ellipsize=True)
                row_label.set_xalign(0.0)
                row.add(row_label)
                row.set_tooltip_text(text if len(text) <= 500 else text[:500] + "…")
                row.connect("clicked", lambda _b, t=text: self._paste(t))
                self.items_box.pack_start(row, False, False, 0)
        self.items_box.show_all()
        self.relayout()

    def _clear_all(self) -> None:
        self.shell.clipboard_history.clear()
        self.refresh()

    def _paste(self, text: str) -> None:
        self.dismiss()
        clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clip.set_text(text, -1)
        clip.store()
        # Let the popup grab release, then paste into the previously focused client.
        GLib.timeout_add(50, self._do_paste)

    def _do_paste(self) -> bool:
        _send_ctrl_v()
        return False

    def _on_key_press(self, _widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.dismiss()
            return True
        if event.keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            if self._nav:
                self._nav_index = min(self._nav_index + 1, len(self._nav) - 1)
                if self._nav_index < 0:
                    self._nav_index = 0
                self._highlight()
            return True
        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            if self._nav:
                self._nav_index = max(self._nav_index - 1, 0)
                self._highlight()
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if 0 <= self._nav_index < len(self._nav):
                self._paste(self._nav[self._nav_index])
                return True
        return False

    def _highlight(self) -> None:
        from .ui import set_class

        children = self.items_box.get_children()
        for index, child in enumerate(children):
            if isinstance(child, Gtk.Button):
                set_class(child, "fos-start-selected", index == self._nav_index)
