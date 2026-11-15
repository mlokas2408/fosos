"""FosOS Terminal: simple Windows-style tabbed VTE terminal."""

from __future__ import annotations

import os
import pwd
import sys
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango, Vte

from .ui import add_classes, button, label, load_css, set_class
from .windowchrome import CardWindow

APP_ID = "org.fosos.Terminal"

PALETTE = [
    Gdk.RGBA(red=0.10, green=0.10, blue=0.10, alpha=1),
    Gdk.RGBA(red=1.00, green=0.39, blue=0.40, alpha=1),
    Gdk.RGBA(red=0.29, green=0.87, blue=0.50, alpha=1),
    Gdk.RGBA(red=0.96, green=0.77, blue=0.26, alpha=1),
    Gdk.RGBA(red=0.55, green=0.70, blue=1.00, alpha=1),
    Gdk.RGBA(red=0.85, green=0.55, blue=1.00, alpha=1),
    Gdk.RGBA(red=0.40, green=0.90, blue=0.90, alpha=1),
    Gdk.RGBA(red=0.98, green=0.98, blue=0.98, alpha=1),
    Gdk.RGBA(red=0.40, green=0.40, blue=0.40, alpha=1),
    Gdk.RGBA(red=1.00, green=0.50, blue=0.52, alpha=1),
    Gdk.RGBA(red=0.40, green=0.95, blue=0.60, alpha=1),
    Gdk.RGBA(red=1.00, green=0.85, blue=0.40, alpha=1),
    Gdk.RGBA(red=0.65, green=0.78, blue=1.00, alpha=1),
    Gdk.RGBA(red=0.92, green=0.65, blue=1.00, alpha=1),
    Gdk.RGBA(red=0.50, green=0.95, blue=0.95, alpha=1),
    Gdk.RGBA(red=1.00, green=1.00, blue=1.00, alpha=1),
]
FG = Gdk.RGBA(red=0.98, green=0.98, blue=0.98, alpha=1)
BG = Gdk.RGBA(red=0.09, green=0.09, blue=0.09, alpha=1)


def default_shell() -> str:
    shell = os.environ.get("SHELL")
    if shell and Path(shell).exists():
        return shell
    try:
        return pwd.getpwuid(os.getuid()).pw_shell or "/bin/bash"
    except KeyError:
        return "/bin/bash"


class TerminalTab:
    def __init__(self, window: "TerminalWindow", cwd: Path, argv: list[str] | None = None) -> None:
        self.window = window
        self.terminal = Vte.Terminal()
        self.terminal.set_cursor_blink_mode(Vte.CursorBlinkMode.ON)
        self.terminal.set_scrollback_lines(10000)
        self.terminal.set_mouse_autohide(True)
        self.terminal.set_colors(FG, BG, PALETTE)
        font = Pango.FontDescription.from_string("Liberation Mono 11")
        self.terminal.set_font(font)
        self.terminal.connect("child-exited", self._on_exited)
        self.terminal.connect("window-title-changed", self._on_title)
        self.terminal.connect("button-press-event", self._on_button)

        self.page = Gtk.Box()
        self.page.pack_start(self.terminal, True, True, 0)

        self.tab_button = button(variant="ghost", size="sm")
        add_classes(self.tab_button, "fos-term-tab")
        tab_row = Gtk.Box(spacing=4)
        self.tab_label = label("Terminal", "fos-text", ellipsize=True)
        self.tab_label.set_width_chars(8)
        self.tab_label.set_max_width_chars(16)
        tab_row.pack_start(self.tab_label, True, True, 0)
        close = button(icon_name="window-close-symbolic", size="icon-xs", tooltip="Close tab", icon_size=12)
        add_classes(close, "close")
        close.connect("clicked", lambda _b: self.window.close_tab(self))
        tab_row.pack_start(close, False, False, 0)
        self.tab_button.add(tab_row)
        self.tab_button.connect("clicked", lambda _b: self.window.focus_tab(self))

        self.spawn(cwd, argv)

    def spawn(self, cwd: Path, argv: list[str] | None = None) -> None:
        command = argv if argv else [default_shell()]

        def _spawned(_terminal, _pid, _error, _data=None) -> None:
            return

        try:
            self.terminal.spawn_async(
                Vte.PtyFlags.DEFAULT,
                str(cwd),
                command,
                None,
                GLib.SpawnFlags.DEFAULT,
                None,
                None,
                -1,
                None,
                _spawned,
                None,
            )
        except (TypeError, AttributeError, GLib.Error):
            try:
                self.terminal.spawn_sync(
                    Vte.PtyFlags.DEFAULT,
                    str(cwd),
                    command,
                    [],
                    GLib.SpawnFlags.DEFAULT,
                    None,
                    None,
                )
            except (TypeError, AttributeError, GLib.Error):
                pass

    def _on_exited(self, _terminal, _status) -> None:
        self.window.close_tab(self)

    def _on_title(self, terminal) -> None:
        title = terminal.get_window_title() or "Terminal"
        short = title[-20:] if len(title) > 20 else title
        self.tab_label.set_text(short)
        if self.window.active is self:
            self.window.set_title(short)

    def _on_button(self, _terminal, event: Gdk.EventButton) -> bool:
        if event.button == 3:
            menu = Gtk.Menu()
            for name, handler in (
                ("Copy", self.window.copy),
                ("Paste", self.window.paste),
                ("New tab", self.window.new_tab),
            ):
                item = Gtk.MenuItem(label=name)
                item.connect("activate", lambda _i, h=handler: h())
                menu.append(item)
            menu.show_all()
            menu.popup_at_pointer(event)
            return True
        return False


class TerminalWindow(CardWindow):
    def __init__(self, app: "TerminalApp", cwd: Path | None = None) -> None:
        super().__init__(
            app,
            title="Terminal",
            icon_name="utilities-terminal-symbolic",
            default_width=900,
            default_height=560,
        )
        self.app = app
        self.tabs: list[TerminalTab] = []
        self.active: TerminalTab | None = None
        self.start_cwd = cwd or Path.home()

        # Windows-style: tabs live in the title bar, not below it.
        self.tab_strip = add_classes(Gtk.Box(spacing=2), "fos-term-tabs")
        self.tab_strip.set_valign(Gtk.Align.CENTER)
        self.tab_strip.set_hexpand(True)
        self.add_tab_btn = button(icon_name="list-add-symbolic", size="icon-xs", tooltip="New tab", icon_size=14)
        self.add_tab_btn.connect("clicked", lambda _b: self.new_tab())
        self.set_header_center(self.tab_strip)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        add_classes(self.stack, "fos-term-body")
        self.body.pack_start(self.stack, True, True, 0)

        self.connect("key-press-event", self._on_key)
        initial_argv = getattr(app, "_initial_argv", None)
        if hasattr(app, "_initial_argv"):
            app._initial_argv = None
        self.new_tab(self.start_cwd, initial_argv)

    def new_tab(self, cwd: Path | None = None, argv: list[str] | None = None) -> None:
        tab = TerminalTab(self, cwd or self.start_cwd, argv=argv)
        self.tabs.append(tab)
        self.stack.add_named(tab.page, str(id(tab)))
        self._rebuild_tabs()
        self.focus_tab(tab)

    def focus_tab(self, tab: TerminalTab) -> None:
        if tab not in self.tabs:
            return
        self.active = tab
        self.stack.set_visible_child(tab.page)
        for other in self.tabs:
            set_class(other.tab_button, "secondary", other is tab)
            set_class(other.tab_button, "ghost", other is not tab)
        tab.terminal.grab_focus()
        title = tab.tab_label.get_text() or "Terminal"
        self.set_title(title)

    def close_tab(self, tab: TerminalTab) -> None:
        if tab not in self.tabs:
            return
        index = self.tabs.index(tab)
        self.tabs.remove(tab)
        self.stack.remove(tab.page)
        tab.page.destroy()
        if not self.tabs:
            self.close()
            return
        next_tab = self.tabs[min(index, len(self.tabs) - 1)]
        self._rebuild_tabs()
        self.focus_tab(next_tab)

    def _rebuild_tabs(self) -> None:
        for child in list(self.tab_strip.get_children()):
            self.tab_strip.remove(child)
        for tab in self.tabs:
            self.tab_strip.pack_start(tab.tab_button, False, False, 0)
        self.tab_strip.pack_start(self.add_tab_btn, False, False, 0)
        # Fill remaining header space so dragging still works to the right of tabs.
        filler = Gtk.Box()
        filler.set_hexpand(True)
        self.tab_strip.pack_start(filler, True, True, 0)
        self.tab_strip.show_all()

    def copy(self) -> None:
        if self.active is not None:
            self.active.terminal.copy_clipboard_format(Vte.Format.TEXT)

    def paste(self) -> None:
        if self.active is not None:
            self.active.terminal.paste_clipboard()

    def _cycle(self, delta: int) -> None:
        if not self.tabs or self.active is None:
            return
        index = self.tabs.index(self.active)
        self.focus_tab(self.tabs[(index + delta) % len(self.tabs)])

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        key = Gdk.keyval_name(event.keyval) or ""
        if ctrl and shift and key.lower() == "t":
            self.new_tab()
            return True
        if ctrl and shift and key.lower() == "w":
            if self.active is not None:
                self.close_tab(self.active)
            return True
        if ctrl and shift and key.lower() == "c":
            self.copy()
            return True
        if ctrl and shift and key.lower() == "v":
            self.paste()
            return True
        if ctrl and not shift and key == "Tab":
            self._cycle(1)
            return True
        if ctrl and shift and key in ("Tab", "ISO_Left_Tab"):
            self._cycle(-1)
            return True
        return False


class TerminalApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE | Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self.window: TerminalWindow | None = None
        self._initial_argv: list[str] | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_prgname("fosos-terminal")
        GLib.set_application_name("Terminal")
        load_css()

    def do_activate(self) -> None:
        self._ensure_window(None)
        self.window.present()

    def do_open(self, files, _n_files, _hint) -> None:
        path = Path.home()
        if files:
            candidate = Path(files[0].get_path() or "")
            if candidate.is_dir():
                path = candidate
            elif candidate.parent.is_dir():
                path = candidate.parent
        self._ensure_window(path)
        self.window.present()

    def do_command_line(self, command_line):
        argv = command_line.get_arguments()[1:]
        path = Path.home()
        run_argv = None
        if "-e" in argv:
            index = argv.index("-e")
            run_argv = argv[index + 1 :]
            argv = argv[:index]
        if argv:
            candidate = Path(argv[0]).expanduser()
            if candidate.is_dir():
                path = candidate
        self._initial_argv = run_argv
        self._ensure_window(path)
        self.window.present()
        return 0

    def _ensure_window(self, cwd: Path | None) -> None:
        if self.window is None:
            self.window = TerminalWindow(self, cwd=cwd)
            self.window.show_all()
        elif cwd is not None:
            self.window.new_tab(cwd, self._initial_argv)
            self._initial_argv = None


def main() -> int:
    return TerminalApp().run(sys.argv)
