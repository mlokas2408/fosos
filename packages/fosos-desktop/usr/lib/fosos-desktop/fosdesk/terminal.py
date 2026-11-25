"""FosOS Terminal: Windows Terminal–style tabbed VTE with settings."""

from __future__ import annotations

import os
import pwd
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango, Vte

from .settings_helpers import settings_row, settings_section
from .settings_pages import load_kv, save_kv, truthy
from .ui import FosDialog, add_classes, button, icon, label, load_css, set_class
from .windowchrome import CardWindow, caption_image

APP_ID = "org.fosos.Terminal"
CONFIG_NAME = "terminal"

DEFAULTS = {
    "font_family": "Liberation Mono",
    "font_size": "11",
    "scheme": "fos-dark",
    "cursor_blink": "1",
    "scrollback": "10000",
    "copy_on_select": "0",
    "audible_bell": "1",
    "cursor_shape": "block",
    "default_profile": "default",
}


def _rgba(r: float, g: float, b: float, a: float = 1.0) -> Gdk.RGBA:
    return Gdk.RGBA(red=r, green=g, blue=b, alpha=a)


def _palette(*colors: tuple[float, float, float]) -> list[Gdk.RGBA]:
    return [_rgba(*c) for c in colors]


SCHEMES: dict[str, dict] = {
    "fos-dark": {
        "label": "Fos Dark",
        "fg": _rgba(0.98, 0.98, 0.98),
        "bg": _rgba(0.09, 0.09, 0.09),
        "palette": _palette(
            (0.10, 0.10, 0.10),
            (1.00, 0.39, 0.40),
            (0.29, 0.87, 0.50),
            (0.96, 0.77, 0.26),
            (0.55, 0.70, 1.00),
            (0.85, 0.55, 1.00),
            (0.40, 0.90, 0.90),
            (0.98, 0.98, 0.98),
            (0.40, 0.40, 0.40),
            (1.00, 0.50, 0.52),
            (0.40, 0.95, 0.60),
            (1.00, 0.85, 0.40),
            (0.65, 0.78, 1.00),
            (0.92, 0.65, 1.00),
            (0.50, 0.95, 0.95),
            (1.00, 1.00, 1.00),
        ),
    },
    "campbell": {
        "label": "Campbell",
        "fg": _rgba(0.80, 0.80, 0.80),
        "bg": _rgba(0.05, 0.05, 0.05),
        "palette": _palette(
            (0.05, 0.05, 0.05),
            (0.77, 0.13, 0.16),
            (0.07, 0.58, 0.19),
            (0.76, 0.55, 0.05),
            (0.00, 0.33, 0.71),
            (0.53, 0.13, 0.54),
            (0.18, 0.62, 0.64),
            (0.80, 0.80, 0.80),
            (0.46, 0.46, 0.46),
            (0.91, 0.28, 0.28),
            (0.09, 0.78, 0.26),
            (0.98, 0.73, 0.20),
            (0.23, 0.51, 0.96),
            (0.71, 0.27, 0.73),
            (0.30, 0.85, 0.87),
            (0.95, 0.95, 0.95),
        ),
    },
    "one-half-dark": {
        "label": "One Half Dark",
        "fg": _rgba(0.86, 0.87, 0.88),
        "bg": _rgba(0.16, 0.18, 0.20),
        "palette": _palette(
            (0.16, 0.18, 0.20),
            (0.88, 0.42, 0.46),
            (0.60, 0.76, 0.45),
            (0.90, 0.75, 0.45),
            (0.42, 0.62, 0.84),
            (0.78, 0.47, 0.75),
            (0.38, 0.71, 0.73),
            (0.86, 0.87, 0.88),
            (0.36, 0.39, 0.42),
            (0.88, 0.42, 0.46),
            (0.60, 0.76, 0.45),
            (0.90, 0.75, 0.45),
            (0.42, 0.62, 0.84),
            (0.78, 0.47, 0.75),
            (0.38, 0.71, 0.73),
            (0.86, 0.87, 0.88),
        ),
    },
    "solarized-dark": {
        "label": "Solarized Dark",
        "fg": _rgba(0.51, 0.58, 0.59),
        "bg": _rgba(0.00, 0.17, 0.21),
        "palette": _palette(
            (0.03, 0.21, 0.26),
            (0.86, 0.20, 0.18),
            (0.52, 0.60, 0.00),
            (0.71, 0.54, 0.00),
            (0.15, 0.55, 0.82),
            (0.83, 0.21, 0.51),
            (0.16, 0.63, 0.60),
            (0.93, 0.91, 0.84),
            (0.00, 0.17, 0.21),
            (0.80, 0.29, 0.09),
            (0.35, 0.43, 0.47),
            (0.40, 0.48, 0.51),
            (0.51, 0.58, 0.59),
            (0.42, 0.44, 0.77),
            (0.58, 0.63, 0.63),
            (0.99, 0.96, 0.89),
        ),
    },
    "tango-dark": {
        "label": "Tango Dark",
        "fg": _rgba(0.82, 0.84, 0.81),
        "bg": _rgba(0.12, 0.12, 0.12),
        "palette": _palette(
            (0.18, 0.20, 0.21),
            (0.80, 0.00, 0.00),
            (0.31, 0.60, 0.02),
            (0.77, 0.63, 0.00),
            (0.20, 0.40, 0.64),
            (0.46, 0.31, 0.48),
            (0.02, 0.60, 0.60),
            (0.83, 0.84, 0.82),
            (0.33, 0.34, 0.33),
            (0.94, 0.16, 0.16),
            (0.54, 0.89, 0.20),
            (0.99, 0.91, 0.31),
            (0.45, 0.62, 0.81),
            (0.68, 0.50, 0.66),
            (0.20, 0.91, 0.89),
            (0.93, 0.93, 0.93),
        ),
    },
    "light": {
        "label": "Light",
        "fg": _rgba(0.14, 0.14, 0.14),
        "bg": _rgba(0.98, 0.98, 0.98),
        "palette": _palette(
            (0.14, 0.14, 0.14),
            (0.80, 0.14, 0.16),
            (0.10, 0.55, 0.22),
            (0.72, 0.53, 0.04),
            (0.15, 0.35, 0.75),
            (0.55, 0.20, 0.65),
            (0.10, 0.55, 0.58),
            (0.85, 0.85, 0.85),
            (0.40, 0.40, 0.40),
            (0.90, 0.25, 0.28),
            (0.20, 0.70, 0.35),
            (0.90, 0.70, 0.15),
            (0.30, 0.50, 0.90),
            (0.70, 0.35, 0.80),
            (0.20, 0.75, 0.78),
            (0.10, 0.10, 0.10),
        ),
    },
}

CURSOR_SHAPES = {
    "block": Vte.CursorShape.BLOCK,
    "ibeam": Vte.CursorShape.IBEAM,
    "underline": Vte.CursorShape.UNDERLINE,
}


def default_shell() -> str:
    shell = os.environ.get("SHELL")
    if shell and Path(shell).exists():
        return shell
    try:
        return pwd.getpwuid(os.getuid()).pw_shell or "/bin/bash"
    except KeyError:
        return "/bin/bash"


@dataclass(frozen=True)
class ShellProfile:
    """An installed shell profile shown in the header dropdown (Windows Terminal style)."""

    id: str
    name: str
    argv: tuple[str, ...]
    path: str


_SHELL_LABELS = {
    "bash": "Bash",
    "zsh": "Zsh",
    "fish": "Fish",
    "dash": "Dash",
    "sh": "sh",
    "pwsh": "PowerShell",
    "powershell": "PowerShell",
    "nu": "Nushell",
    "elvish": "Elvish",
    "xonsh": "Xonsh",
}


def _shell_label(path: str) -> str:
    name = Path(path).name.lower()
    return _SHELL_LABELS.get(name, Path(path).name)


def _resolve_executable(path: str) -> str | None:
    candidate = Path(path)
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        return None
    try:
        return str(candidate.resolve())
    except OSError:
        return str(candidate)


def _find_powershell() -> str | None:
    for name in ("pwsh", "powershell"):
        found = shutil.which(name)
        if found:
            resolved = _resolve_executable(found)
            if resolved:
                return resolved
    root = Path("/opt/microsoft/powershell")
    if root.is_dir():
        for candidate in sorted(root.glob("*/pwsh"), reverse=True):
            resolved = _resolve_executable(str(candidate))
            if resolved:
                return resolved
    return None


def discover_profiles() -> list[ShellProfile]:
    """Detect installed shells for the profile dropdown (re-scanned when the menu opens)."""
    profiles: list[ShellProfile] = []
    seen: set[str] = set()

    login = default_shell()
    login_resolved = _resolve_executable(login) or login
    profiles.append(
        ShellProfile(
            id="default",
            name=_shell_label(login),
            argv=(login,),
            path=login_resolved,
        )
    )
    seen.add(login_resolved)

    extras: list[tuple[str, str, Callable[[], str | None]]] = [
        ("powershell", "PowerShell", _find_powershell),
        ("bash", "Bash", lambda: shutil.which("bash")),
        ("zsh", "Zsh", lambda: shutil.which("zsh")),
        ("fish", "Fish", lambda: shutil.which("fish")),
        ("nu", "Nushell", lambda: shutil.which("nu")),
        ("dash", "Dash", lambda: shutil.which("dash")),
        ("sh", "sh", lambda: shutil.which("sh")),
    ]
    for profile_id, name, finder in extras:
        found = finder()
        if not found:
            continue
        resolved = _resolve_executable(found) or found
        if resolved in seen:
            continue
        profiles.append(ShellProfile(id=profile_id, name=name, argv=(found,), path=resolved))
        seen.add(resolved)
    return profiles


def load_prefs() -> dict[str, str]:
    return load_kv(CONFIG_NAME, dict(DEFAULTS))


def save_prefs(prefs: dict[str, str]) -> None:
    save_kv(CONFIG_NAME, prefs)


def package_version() -> str:
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Version}", "fosos-desktop"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    version = (result.stdout or "").strip()
    return version or "unknown"


@dataclass(frozen=True)
class PaletteCommand:
    title: str
    action: Callable[[], None]
    shortcut: str = ""
    keywords: str = ""


def _build_tab_chip(
    title: str,
    *,
    on_focus: Callable[[], None],
    on_close: Callable[[], None],
) -> tuple[Gtk.Box, Gtk.Button, Gtk.Label]:
    """Tab chrome with a focus button and a sibling close button.

    GTK does not support nesting a Button inside another Button; that broke
    both tab switching and close clicks.
    """
    chip = add_classes(Gtk.Box(spacing=0), "fos-term-tab-chip")
    focus_btn = button(variant="ghost", size="sm")
    add_classes(focus_btn, "fos-term-tab")
    tab_label = label(title, "fos-text", ellipsize=True)
    tab_label.set_width_chars(8)
    tab_label.set_max_width_chars(16)
    focus_btn.add(tab_label)
    focus_btn.connect("clicked", lambda _b: on_focus())
    close = button(size="icon-xs", tooltip="Close tab")
    close.add(caption_image("close"))
    add_classes(close, "close", "fos-term-tab-close")
    close.connect("clicked", lambda _b: on_close())
    chip.pack_start(focus_btn, False, False, 0)
    chip.pack_start(close, False, False, 0)
    return chip, focus_btn, tab_label


class TerminalTab:
    def __init__(
        self,
        window: "TerminalWindow",
        cwd: Path,
        argv: list[str] | None = None,
        *,
        profile_name: str = "Terminal",
    ) -> None:
        self.window = window
        self.profile_name = profile_name
        self.terminal = Vte.Terminal()
        self.terminal.set_mouse_autohide(True)
        self.terminal.connect("child-exited", self._on_exited)
        self.terminal.connect("window-title-changed", self._on_title)
        self.terminal.connect("button-press-event", self._on_button)
        self.terminal.connect("selection-changed", self._on_selection)
        # Intercept before VTE feeds the key to the PTY (window handlers are too late).
        self.terminal.connect("key-press-event", self._on_key)

        # VTE ignores CSS padding; inset via a padded page that shares the
        # scheme background so the gap matches the terminal chrome.
        self.page = add_classes(Gtk.Box(), "fos-term-page")
        self._page_css = Gtk.CssProvider()
        self.page.get_style_context().add_provider(
            self._page_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.page.pack_start(self.terminal, True, True, 0)

        self.tab_chip, self.tab_button, self.tab_label = _build_tab_chip(
            profile_name,
            on_focus=lambda: self.window.focus_tab(self),
            on_close=lambda: self.window.close_tab(self),
        )

        self.apply_prefs(window.prefs, window.font_zoom)
        self.spawn(cwd, argv)

    def apply_prefs(self, prefs: dict[str, str], font_zoom: int = 0) -> None:
        scheme = SCHEMES.get(prefs.get("scheme", "fos-dark"), SCHEMES["fos-dark"])
        self.terminal.set_colors(scheme["fg"], scheme["bg"], scheme["palette"])
        bg = scheme["bg"]
        self._page_css.load_from_data(
            f".fos-term-page {{ background-color: rgba({int(bg.red * 255)},"
            f"{int(bg.green * 255)},{int(bg.blue * 255)},{bg.alpha}); }}".encode()
        )
        family = prefs.get("font_family", DEFAULTS["font_family"]) or DEFAULTS["font_family"]
        try:
            size = max(6, int(prefs.get("font_size", "11")) + font_zoom)
        except ValueError:
            size = 11 + font_zoom
        self.terminal.set_font(Pango.FontDescription.from_string(f"{family} {size}"))
        try:
            scrollback = max(100, int(prefs.get("scrollback", "10000")))
        except ValueError:
            scrollback = 10000
        self.terminal.set_scrollback_lines(scrollback)
        blink = Vte.CursorBlinkMode.ON if truthy(prefs.get("cursor_blink"), True) else Vte.CursorBlinkMode.OFF
        self.terminal.set_cursor_blink_mode(blink)
        shape = CURSOR_SHAPES.get(prefs.get("cursor_shape", "block"), Vte.CursorShape.BLOCK)
        self.terminal.set_cursor_shape(shape)
        self.terminal.set_audible_bell(truthy(prefs.get("audible_bell"), True))

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

    def _on_selection(self, terminal) -> None:
        if not truthy(self.window.prefs.get("copy_on_select"), False):
            return
        if terminal.get_has_selection():
            terminal.copy_clipboard_format(Vte.Format.TEXT)

    def _popup_context_menu(self, event: Gdk.EventButton) -> None:
        menu = Gtk.Menu()
        for name, handler in (
            ("Copy", self.window.copy),
            ("Paste", self.window.paste),
            ("New tab", self.window.new_tab),
            ("Command palette…", self.window.open_command_palette),
            ("Settings…", self.window.open_settings),
        ):
            item = Gtk.MenuItem(label=name)
            item.connect("activate", lambda _i, h=handler: h())
            menu.append(item)
        menu.show_all()
        menu.popup_at_pointer(event)

    def _on_button(self, terminal, event: Gdk.EventButton) -> bool:
        if event.button != 3:
            return False
        # Shift+right-click keeps the context menu (Windows Terminal escape hatch).
        if event.state & Gdk.ModifierType.SHIFT_MASK:
            self._popup_context_menu(event)
            return True
        # Windows console / Terminal: selection → copy; otherwise paste.
        if terminal.get_has_selection():
            terminal.copy_clipboard_format(Vte.Format.TEXT)
            try:
                terminal.unselect_all()
            except (AttributeError, TypeError):
                pass
        else:
            terminal.paste_clipboard()
        return True

    def _on_key(self, _terminal, event: Gdk.EventKey) -> bool:
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        key = (Gdk.keyval_name(event.keyval) or "").lower()
        # Windows Terminal: Ctrl+V pastes (Ctrl+Shift+V still works too).
        if ctrl and key == "v":
            self.window.paste()
            return True
        # Windows Terminal: Ctrl+C copies when there is a selection; else SIGINT.
        if ctrl and not shift and key == "c" and _terminal.get_has_selection():
            self.window.copy()
            try:
                _terminal.unselect_all()
            except (AttributeError, TypeError):
                pass
            return True
        if ctrl and shift and key == "p":
            self.window.open_command_palette()
            return True
        if ctrl and not shift and key in ("comma", "commaaccent"):
            self.window.open_settings()
            return True
        return False


class SettingsTab:
    """Settings page hosted as a tab inside the Terminal window (Windows Terminal style)."""

    def __init__(self, window: "TerminalWindow") -> None:
        self.window = window
        prefs = dict(window.prefs)

        self.tab_chip, self.tab_button, self.tab_label = _build_tab_chip(
            "Settings",
            on_focus=lambda: self.window.focus_settings(),
            on_close=lambda: self.window.close_settings(),
        )

        self.page = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-term-settings")
        header = add_classes(Gtk.Box(spacing=8), "fos-term-settings-header")
        header.pack_start(label("Settings", "fos-title"), False, False, 0)
        header.pack_start(
            label("Changes apply immediately to all tabs", "fos-small", "fos-muted"),
            False,
            False,
            0,
        )
        self.page.pack_start(header, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        scroller.add(body)
        self.page.pack_start(scroller, True, True, 0)

        scheme_store = Gtk.ListStore(str, str)
        self._scheme_ids = list(SCHEMES.keys())
        for key, meta in SCHEMES.items():
            scheme_store.append([key, meta["label"]])
        self.scheme_combo = Gtk.ComboBox.new_with_model(scheme_store)
        scheme_renderer = Gtk.CellRendererText()
        self.scheme_combo.pack_start(scheme_renderer, True)
        self.scheme_combo.add_attribute(scheme_renderer, "text", 1)
        current_scheme = prefs.get("scheme", "fos-dark")
        self.scheme_combo.set_active(
            self._scheme_ids.index(current_scheme) if current_scheme in self._scheme_ids else 0
        )
        self.scheme_combo.connect("changed", lambda _c: self._apply())

        self._fonts = ("Liberation Mono", "DejaVu Sans Mono", "Monospace", "Courier New", "Noto Sans Mono")
        font_store = Gtk.ListStore(str)
        for name in self._fonts:
            font_store.append([name])
        self.font_combo = Gtk.ComboBox.new_with_model(font_store)
        font_renderer = Gtk.CellRendererText()
        self.font_combo.pack_start(font_renderer, True)
        self.font_combo.add_attribute(font_renderer, "text", 0)
        family = prefs.get("font_family", DEFAULTS["font_family"])
        self.font_combo.set_active(self._fonts.index(family) if family in self._fonts else 0)
        self.font_combo.connect("changed", lambda _c: self._apply())

        size_adj = Gtk.Adjustment(
            value=float(prefs.get("font_size", "11") or 11),
            lower=6,
            upper=36,
            step_increment=1,
            page_increment=2,
        )
        self.size_spin = Gtk.SpinButton(adjustment=size_adj, climb_rate=1, digits=0)
        self.size_spin.connect("value-changed", lambda _s: self._apply())

        shape_store = Gtk.ListStore(str, str)
        self._shapes = (("block", "Block"), ("ibeam", "Bar"), ("underline", "Underline"))
        for key, text in self._shapes:
            shape_store.append([key, text])
        self.shape_combo = Gtk.ComboBox.new_with_model(shape_store)
        shape_renderer = Gtk.CellRendererText()
        self.shape_combo.pack_start(shape_renderer, True)
        self.shape_combo.add_attribute(shape_renderer, "text", 1)
        shape_keys = [s[0] for s in self._shapes]
        shape = prefs.get("cursor_shape", "block")
        self.shape_combo.set_active(shape_keys.index(shape) if shape in shape_keys else 0)
        self.shape_combo.connect("changed", lambda _c: self._apply())

        self.blink_switch = Gtk.Switch()
        self.blink_switch.set_active(truthy(prefs.get("cursor_blink"), True))
        self.blink_switch.set_valign(Gtk.Align.CENTER)
        self.blink_switch.connect("notify::active", lambda *_a: self._apply())

        body.pack_start(
            settings_section(
                "Appearance",
                settings_row("Color scheme", "Palette used by the shell", trailing=self.scheme_combo),
                settings_row("Font", "Monospace face for all tabs", trailing=self.font_combo),
                settings_row("Font size", "Base size before zoom", trailing=self.size_spin),
                settings_row("Cursor shape", "Block, bar, or underline", trailing=self.shape_combo),
                settings_row("Cursor blink", "Blink the text cursor", trailing=self.blink_switch),
            ),
            False,
            False,
            0,
        )

        scroll_adj = Gtk.Adjustment(
            value=float(prefs.get("scrollback", "10000") or 10000),
            lower=100,
            upper=100000,
            step_increment=500,
            page_increment=1000,
        )
        self.scroll_spin = Gtk.SpinButton(adjustment=scroll_adj, climb_rate=500, digits=0)
        self.scroll_spin.connect("value-changed", lambda _s: self._apply())

        self.copy_switch = Gtk.Switch()
        self.copy_switch.set_active(truthy(prefs.get("copy_on_select"), False))
        self.copy_switch.set_valign(Gtk.Align.CENTER)
        self.copy_switch.connect("notify::active", lambda *_a: self._apply())

        self.bell_switch = Gtk.Switch()
        self.bell_switch.set_active(truthy(prefs.get("audible_bell"), True))
        self.bell_switch.set_valign(Gtk.Align.CENTER)
        self.bell_switch.connect("notify::active", lambda *_a: self._apply())

        profiles = discover_profiles()
        profile_store = Gtk.ListStore(str, str)
        profile_ids = [p.id for p in profiles]
        for profile in profiles:
            profile_store.append([profile.id, f"{profile.name}  ·  {profile.path}"])
        self.profile_combo = Gtk.ComboBox.new_with_model(profile_store)
        profile_renderer = Gtk.CellRendererText()
        self.profile_combo.pack_start(profile_renderer, True)
        self.profile_combo.add_attribute(profile_renderer, "text", 1)
        current_profile = prefs.get("default_profile", "default")
        self.profile_combo.set_active(
            profile_ids.index(current_profile) if current_profile in profile_ids else 0
        )
        self.profile_combo.connect("changed", lambda _c: self._apply())

        body.pack_start(
            settings_section(
                "Interaction",
                settings_row("Scrollback", "Lines kept above the viewport", trailing=self.scroll_spin),
                settings_row("Copy on select", "Copy text as soon as it is selected", trailing=self.copy_switch),
                settings_row("Audible bell", "Play a sound for BEL", trailing=self.bell_switch),
                settings_row(
                    "Default profile",
                    "Shell used by + and Ctrl+Shift+T (dropdown lists all installed)",
                    trailing=self.profile_combo,
                ),
            ),
            False,
            False,
            0,
        )

        about_btn = button("About…", variant="outline", size="sm")
        about_btn.connect("clicked", lambda _b: self.window.show_about())
        palette_btn = button("Open command palette", variant="outline", size="sm")
        palette_btn.connect("clicked", lambda _b: self.window.open_command_palette())
        about_actions = Gtk.Box(spacing=8)
        about_actions.pack_start(about_btn, False, False, 0)
        about_actions.pack_start(palette_btn, False, False, 0)
        body.pack_start(
            settings_section(
                "About",
                settings_row(
                    "FosOS Terminal",
                    f"Version {package_version()} · Ctrl+Shift+P for command palette",
                    trailing=about_actions,
                ),
            ),
            False,
            False,
            0,
        )

        tips = label(
            "Shortcuts: Ctrl+Shift+T new tab · Ctrl+, settings · Ctrl+Shift+P command palette · "
            "Ctrl++ / Ctrl+- zoom · right-click copies selection or pastes · Shift+right-click opens the menu",
            "fos-small",
            "fos-muted",
        )
        tips.set_line_wrap(True)
        body.pack_start(tips, False, False, 0)
        self.page.show_all()

    def _collect(self) -> dict[str, str]:
        scheme_iter = self.scheme_combo.get_active_iter()
        font_iter = self.font_combo.get_active_iter()
        shape_iter = self.shape_combo.get_active_iter()
        profile_iter = self.profile_combo.get_active_iter()
        scheme_model = self.scheme_combo.get_model()
        font_model = self.font_combo.get_model()
        shape_model = self.shape_combo.get_model()
        profile_model = self.profile_combo.get_model()
        return {
            "scheme": scheme_model.get_value(scheme_iter, 0) if scheme_iter else "fos-dark",
            "font_family": font_model.get_value(font_iter, 0) if font_iter else DEFAULTS["font_family"],
            "font_size": str(int(self.size_spin.get_value())),
            "cursor_shape": shape_model.get_value(shape_iter, 0) if shape_iter else "block",
            "cursor_blink": "1" if self.blink_switch.get_active() else "0",
            "scrollback": str(int(self.scroll_spin.get_value())),
            "copy_on_select": "1" if self.copy_switch.get_active() else "0",
            "audible_bell": "1" if self.bell_switch.get_active() else "0",
            "default_profile": profile_model.get_value(profile_iter, 0) if profile_iter else "default",
        }

    def _apply(self) -> None:
        prefs = self._collect()
        if prefs.get("font_size") != self.window.prefs.get("font_size"):
            self.window.font_zoom = 0
        self.window.apply_prefs(prefs)


class CommandPalette(Gtk.Window):
    """Windows Terminal–style searchable command palette (Ctrl+Shift+P)."""

    def __init__(self, terminal: "TerminalWindow") -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.terminal = terminal
        self.set_transient_for(terminal)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_decorated(False)
        self.set_modal(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_resizable(False)
        add_classes(self, "fos-root", "fos-popup", "fos-term-palette")
        self.set_default_size(520, -1)
        self._commands: list[PaletteCommand] = []
        self._filtered: list[PaletteCommand] = []
        self._rows: list[Gtk.ListBoxRow] = []

        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)
        body = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), "fos-card-content")
        frame.pack_start(body, True, True, 0)

        self.entry = add_classes(Gtk.Entry(), "fos-input")
        self.entry.set_placeholder_text("Type a command…")
        self.entry.connect("changed", lambda _e: self._refilter())
        self.entry.connect("activate", lambda _e: self._run_selected())
        body.pack_start(self.entry, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(220)
        scroller.set_max_content_height(320)
        scroller.set_propagate_natural_height(True)
        self.listbox = add_classes(Gtk.ListBox(), "fos-term-palette-list")
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_activate_on_single_click(True)
        self.listbox.connect("row-activated", self._on_row_activated)
        scroller.add(self.listbox)
        body.pack_start(scroller, True, True, 0)

        hint = label("↑↓ to move · Enter to run · Esc to close", "fos-small", "fos-muted")
        body.pack_start(hint, False, False, 0)

        self.connect("key-press-event", self._on_key)
        self.connect("delete-event", lambda *_a: self.hide() or True)

    def open_palette(self) -> None:
        self._commands = self.terminal._palette_commands()
        self.entry.set_text("")
        self._refilter()
        self.show_all()
        self._position()
        self.present()
        GLib.idle_add(self.entry.grab_focus)

    def _position(self) -> None:
        parent = self.terminal.get_window()
        if parent is None:
            return
        _ok, px, py = parent.get_origin()
        pw = parent.get_width()
        self.resize(520, 1)
        _minimum, natural = self.get_preferred_size()
        width = max(480, min(560, natural.width))
        height = natural.height
        self.resize(width, height)
        self.move(px + max(0, (pw - width) // 2), py + 48)

    def _refilter(self) -> None:
        query = self.entry.get_text().strip().lower()
        for child in list(self.listbox.get_children()):
            self.listbox.remove(child)
        self._rows = []
        self._filtered = []
        for cmd in self._commands:
            hay = f"{cmd.title} {cmd.shortcut} {cmd.keywords}".lower()
            if query and query not in hay:
                continue
            self._filtered.append(cmd)
            row = Gtk.ListBoxRow()
            add_classes(row, "fos-term-palette-row")
            box = Gtk.Box(spacing=12)
            box.set_margin_start(8)
            box.set_margin_end(8)
            box.set_margin_top(6)
            box.set_margin_bottom(6)
            title = label(cmd.title, "fos-text", ellipsize=True)
            title.set_hexpand(True)
            box.pack_start(title, True, True, 0)
            if cmd.shortcut:
                box.pack_start(label(cmd.shortcut, "fos-small", "fos-muted"), False, False, 0)
            row.add(box)
            self.listbox.add(row)
            self._rows.append(row)
        self.listbox.show_all()
        if self._rows:
            self.listbox.select_row(self._rows[0])

    def _selected_command(self) -> PaletteCommand | None:
        row = self.listbox.get_selected_row()
        if row is None or row not in self._rows:
            return self._filtered[0] if self._filtered else None
        return self._filtered[self._rows.index(row)]

    def _run_selected(self) -> None:
        cmd = self._selected_command()
        self.hide()
        if cmd is not None:
            GLib.idle_add(lambda: cmd.action() or False)

    def _on_row_activated(self, _listbox, _row) -> None:
        self._run_selected()

    def _move_selection(self, delta: int) -> None:
        if not self._rows:
            return
        row = self.listbox.get_selected_row()
        index = self._rows.index(row) if row in self._rows else 0
        nxt = self._rows[(index + delta) % len(self._rows)]
        self.listbox.select_row(nxt)
        nxt.grab_focus()
        self.entry.grab_focus_without_selecting()

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        key = Gdk.keyval_name(event.keyval) or ""
        if key == "Escape":
            self.hide()
            return True
        if key == "Up":
            self._move_selection(-1)
            return True
        if key == "Down":
            self._move_selection(1)
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
        self.settings_tab: SettingsTab | None = None
        self.active: TerminalTab | None = None
        self.settings_active = False
        self.start_cwd = cwd or Path.home()
        self.prefs = load_prefs()
        self.font_zoom = 0
        self._palette: CommandPalette | None = None

        # Windows-style: tabs live in the title bar, not below it.
        self.tab_strip = add_classes(Gtk.Box(spacing=2), "fos-term-tabs")
        self.tab_strip.set_valign(Gtk.Align.CENTER)
        self.tab_strip.set_hexpand(True)
        self.add_tab_btn = button(icon_name="list-add-symbolic", size="icon-xs", tooltip="New tab", icon_size=14)
        self.add_tab_btn.connect("clicked", lambda _b: self.new_tab())
        self.menu_btn = button(
            icon_name="pan-down-symbolic",
            size="icon-xs",
            tooltip="Terminal menu",
            icon_size=14,
        )
        self.menu_btn.connect("clicked", self._on_menu_clicked)
        self.settings_btn = button(
            icon_name="emblem-system-symbolic",
            size="icon-xs",
            tooltip="Settings (Ctrl+,)",
            icon_size=14,
        )
        self.settings_btn.connect("clicked", lambda _b: self.open_settings())
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

    def profiles(self) -> list[ShellProfile]:
        return discover_profiles()

    def profile_by_id(self, profile_id: str | None) -> ShellProfile:
        profiles = self.profiles()
        if not profiles:
            shell = default_shell()
            return ShellProfile("default", _shell_label(shell), (shell,), shell)
        if profile_id:
            for profile in profiles:
                if profile.id == profile_id:
                    return profile
        preferred = self.prefs.get("default_profile", "default")
        for profile in profiles:
            if profile.id == preferred:
                return profile
        return profiles[0]

    def new_tab(
        self,
        cwd: Path | None = None,
        argv: list[str] | None = None,
        profile: ShellProfile | None = None,
    ) -> None:
        if argv is None:
            profile = profile or self.profile_by_id(None)
            argv = list(profile.argv)
        elif profile is None:
            profile = ShellProfile("custom", "Terminal", tuple(argv), argv[0] if argv else "")
        tab = TerminalTab(
            self,
            cwd or self.start_cwd,
            argv=argv,
            profile_name=profile.name if profile is not None else "Terminal",
        )
        self.tabs.append(tab)
        # Stack children must be shown explicitly; show_all on the window only
        # covers widgets that exist at first map.
        tab.page.show_all()
        self.stack.add_named(tab.page, str(id(tab)))
        self._rebuild_tabs()
        self.focus_tab(tab)

    def focus_tab(self, tab: TerminalTab) -> None:
        if tab not in self.tabs:
            return
        self.active = tab
        self.settings_active = False
        tab.page.show_all()
        self.stack.set_visible_child(tab.page)
        for other in self.tabs:
            set_class(other.tab_chip, "secondary", other is tab)
            set_class(other.tab_button, "ghost", True)
        if self.settings_tab is not None:
            set_class(self.settings_tab.tab_chip, "secondary", False)
            set_class(self.settings_tab.tab_button, "ghost", True)
        tab.terminal.grab_focus()
        title = tab.tab_label.get_text() or "Terminal"
        self.set_title(title)

    def focus_settings(self) -> None:
        if self.settings_tab is None:
            return
        self.active = None
        self.settings_active = True
        self.settings_tab.page.show_all()
        self.stack.set_visible_child(self.settings_tab.page)
        for other in self.tabs:
            set_class(other.tab_chip, "secondary", False)
            set_class(other.tab_button, "ghost", True)
        set_class(self.settings_tab.tab_chip, "secondary", True)
        set_class(self.settings_tab.tab_button, "ghost", True)
        self.set_title("Settings")

    def close_tab(self, tab: TerminalTab) -> None:
        if tab not in self.tabs:
            return
        index = self.tabs.index(tab)
        self.tabs.remove(tab)
        self.stack.remove(tab.page)
        tab.page.destroy()
        if not self.tabs:
            if self.settings_tab is not None:
                self._rebuild_tabs()
                self.focus_settings()
                return
            self.close()
            return
        next_tab = self.tabs[min(index, len(self.tabs) - 1)]
        self._rebuild_tabs()
        self.focus_tab(next_tab)

    def close_settings(self) -> None:
        if self.settings_tab is None:
            return
        self.stack.remove(self.settings_tab.page)
        self.settings_tab.page.destroy()
        self.settings_tab = None
        self.settings_active = False
        if self.tabs:
            self._rebuild_tabs()
            self.focus_tab(self.tabs[-1])
            return
        self.close()

    def _rebuild_tabs(self) -> None:
        for child in list(self.tab_strip.get_children()):
            self.tab_strip.remove(child)
        for tab in self.tabs:
            self.tab_strip.pack_start(tab.tab_chip, False, False, 0)
        if self.settings_tab is not None:
            self.tab_strip.pack_start(self.settings_tab.tab_chip, False, False, 0)
        self.tab_strip.pack_start(self.add_tab_btn, False, False, 0)
        self.tab_strip.pack_start(self.menu_btn, False, False, 0)
        # Explicit drag handle: empty titlebar space to the right of tabs.
        filler = add_classes(Gtk.EventBox(), "fos-term-drag")
        filler.set_hexpand(True)
        filler.set_visible_window(True)
        filler.set_above_child(False)
        filler.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.BUTTON1_MOTION_MASK
        )
        filler.connect("button-press-event", self._on_drag_filler_press)
        self.tab_strip.pack_start(filler, True, True, 0)
        self.tab_strip.pack_start(self.settings_btn, False, False, 0)
        self.tab_strip.show_all()

    def _on_drag_filler_press(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button == 3:
            self._popup_title_menu(event)
            return True
        return self.begin_titlebar_move(event)

    def _on_menu_clicked(self, btn: Gtk.Button) -> None:
        menu = Gtk.Menu()
        # Windows Terminal style: installed profiles first, then app actions.
        default_id = self.prefs.get("default_profile", "default")
        for profile in self.profiles():
            mark = "  ★" if profile.id == default_id else ""
            item = Gtk.MenuItem(label=f"{profile.name}{mark}")
            item.connect(
                "activate",
                lambda _i, p=profile: self.new_tab(profile=p),
            )
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        for name, handler in (
            ("Command palette…", self.open_command_palette),
            ("Settings…", self.open_settings),
            ("About Terminal", self.show_about),
        ):
            item = Gtk.MenuItem(label=name)
            item.connect("activate", lambda _i, h=handler: h())
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        zoom_in = Gtk.MenuItem(label="Zoom in")
        zoom_in.connect("activate", lambda _i: self._zoom(1))
        menu.append(zoom_in)
        zoom_out = Gtk.MenuItem(label="Zoom out")
        zoom_out.connect("activate", lambda _i: self._zoom(-1))
        menu.append(zoom_out)
        zoom_reset = Gtk.MenuItem(label="Reset zoom")
        zoom_reset.connect("activate", lambda _i: self._zoom(0, reset=True))
        menu.append(zoom_reset)
        menu.show_all()
        menu.popup_at_widget(btn, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)

    def apply_prefs(self, prefs: dict[str, str]) -> None:
        self.prefs = prefs
        save_prefs(prefs)
        for tab in self.tabs:
            tab.apply_prefs(prefs, self.font_zoom)

    def open_settings(self) -> None:
        if self.settings_tab is None:
            self.settings_tab = SettingsTab(self)
            self.stack.add_named(self.settings_tab.page, "settings")
            self._rebuild_tabs()
        self.focus_settings()

    def show_about(self) -> None:
        version = package_version()
        try:
            vte_ver = f"{Vte.get_major_version()}.{Vte.get_minor_version()}.{Vte.get_micro_version()}"
        except AttributeError:
            vte_ver = "2.91"
        dialog = FosDialog(self, title="About Terminal", width=420)
        head = Gtk.Box(spacing=12)
        head.pack_start(icon("utilities-terminal-symbolic", 48), False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        texts.pack_start(label("FosOS Terminal", "fos-title"), False, False, 0)
        texts.pack_start(label(f"Version {version}", "fos-text", "fos-muted"), False, False, 0)
        head.pack_start(texts, True, True, 0)
        dialog.content.pack_start(head, False, False, 0)
        profile_lines = "\n".join(f"· {p.name}: {p.path}" for p in self.profiles()) or f"· {default_shell()}"
        dialog.add_body_text(
            f"Tabbed terminal for FosOS Desktop.\n"
            f"Default shell: {default_shell()}\n"
            f"VTE {vte_ver}\n\n"
            f"Profiles:\n{profile_lines}\n\n"
            "Ctrl+Shift+P opens the command palette."
        )
        dialog.add_action("Close", True, variant="default", default=True)
        dialog.run()

    def open_command_palette(self) -> None:
        if self._palette is None:
            self._palette = CommandPalette(self)
        self._palette.open_palette()

    def _palette_commands(self) -> list[PaletteCommand]:
        commands = [
            PaletteCommand("New tab", self.new_tab, "Ctrl+Shift+T", "open shell default profile"),
        ]
        for profile in self.profiles():
            commands.append(
                PaletteCommand(
                    f"New tab: {profile.name}",
                    lambda p=profile: self.new_tab(profile=p),
                    "",
                    f"profile shell {profile.path}",
                )
            )
        commands.extend(
            [
                PaletteCommand(
                    "Close tab",
                    lambda: self.close_settings()
                    if self.settings_active
                    else self.close_tab(self.active)
                    if self.active is not None
                    else None,
                    "Ctrl+Shift+W",
                    "close",
                ),
                PaletteCommand("Next tab", lambda: self._cycle(1), "Ctrl+Tab", "cycle"),
                PaletteCommand("Previous tab", lambda: self._cycle(-1), "Ctrl+Shift+Tab", "cycle"),
                PaletteCommand("Settings", self.open_settings, "Ctrl+,", "preferences options"),
                PaletteCommand("Command palette", self.open_command_palette, "Ctrl+Shift+P", "actions"),
                PaletteCommand("Copy", self.copy, "Ctrl+Shift+C", "clipboard"),
                PaletteCommand("Paste", self.paste, "Ctrl+V", "clipboard"),
                PaletteCommand("Zoom in", lambda: self._zoom(1), "Ctrl++", "font larger"),
                PaletteCommand("Zoom out", lambda: self._zoom(-1), "Ctrl+-", "font smaller"),
                PaletteCommand("Reset zoom", lambda: self._zoom(0, reset=True), "Ctrl+0", "font"),
                PaletteCommand("About Terminal", self.show_about, "", "version info"),
            ]
        )
        return commands

    def copy(self) -> None:
        if self.active is not None:
            self.active.terminal.copy_clipboard_format(Vte.Format.TEXT)

    def paste(self) -> None:
        if self.active is not None:
            self.active.terminal.paste_clipboard()

    def _cycle(self, delta: int) -> None:
        pages: list[object] = list(self.tabs)
        if self.settings_tab is not None:
            pages.append(self.settings_tab)
        if not pages:
            return
        if self.settings_active and self.settings_tab is not None:
            current: object = self.settings_tab
        elif self.active is not None:
            current = self.active
        else:
            current = pages[0]
        index = pages.index(current) if current in pages else 0
        nxt = pages[(index + delta) % len(pages)]
        if isinstance(nxt, SettingsTab):
            self.focus_settings()
        else:
            self.focus_tab(nxt)  # type: ignore[arg-type]

    def _zoom(self, delta: int, *, reset: bool = False) -> None:
        if reset:
            self.font_zoom = 0
        else:
            self.font_zoom = max(-8, min(24, self.font_zoom + delta))
        for tab in self.tabs:
            tab.apply_prefs(self.prefs, self.font_zoom)

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        key = Gdk.keyval_name(event.keyval) or ""
        if ctrl and not shift and key in ("comma", "commaaccent"):
            self.open_settings()
            return True
        if ctrl and shift and key.lower() == "p":
            self.open_command_palette()
            return True
        if ctrl and shift and key.lower() == "t":
            self.new_tab()
            return True
        if ctrl and shift and key.lower() == "w":
            if self.settings_active:
                self.close_settings()
            elif self.active is not None:
                self.close_tab(self.active)
            return True
        if ctrl and shift and key.lower() == "c":
            self.copy()
            return True
        if ctrl and key.lower() == "v":
            self.paste()
            return True
        if ctrl and not shift and key == "Tab":
            self._cycle(1)
            return True
        if ctrl and shift and key in ("Tab", "ISO_Left_Tab"):
            self._cycle(-1)
            return True
        if ctrl and not shift and key in ("plus", "equal", "KP_Add"):
            self._zoom(1)
            return True
        if ctrl and shift and key in ("plus", "equal", "KP_Add"):
            self._zoom(1)
            return True
        if ctrl and key in ("minus", "KP_Subtract"):
            self._zoom(-1)
            return True
        if ctrl and not shift and key in ("0", "KP_0"):
            self._zoom(0, reset=True)
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
