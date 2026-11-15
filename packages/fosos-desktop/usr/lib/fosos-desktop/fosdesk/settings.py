"""fosos-settings: one place for the system settings FosOS ships."""

import os
import platform
import shutil
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk

from . import VERSION
from . import apps as appmod
from .ui import add_classes, brand_title, button, clear, label, load_css, mark, tile

APP_ID = "org.fosos.Settings"

UPDATE_SCRIPT = (
    "fos update && fos upgrade; status=$?; echo; "
    "if [ $status -eq 0 ]; then echo 'Updates are installed.'; "
    "else echo 'Updates did not finish. Check the network and try again.'; fi; "
    "printf 'Press Enter to close. '; read _"
)

# (group, title, description, icon, command)
PANELS = [
    ("System", "Display", "Resolution, scaling and monitors", "video-display-symbolic", ["xfce4-display-settings"]),
    ("System", "Sound", "Output, input and volume", "audio-volume-high-symbolic", ["pavucontrol"]),
    ("System", "Network", "Wi-Fi, cable and VPN connections", "network-wireless-symbolic", ["nm-connection-editor"]),
    ("System", "Bluetooth", "Pair and manage devices", "bluetooth-active-symbolic", ["blueman-manager"]),
    ("Input", "Keyboard", "Layout, repeat and shortcuts", "input-keyboard-symbolic", ["xfce4-keyboard-settings"]),
    ("Input", "Mouse and touchpad", "Pointer speed and buttons", "input-mouse-symbolic", ["xfce4-mouse-settings"]),
    ("Apps", "Default apps", "Browser, mail and file types", "starred-symbolic", ["xfce4-mime-settings"]),
    (
        "FosOS",
        "Updates",
        "Install Debian and FosOS updates",
        "software-update-available-symbolic",
        ["xfce4-terminal", "--title=FosOS updates", "-x", "sh", "-c", UPDATE_SCRIPT],
    ),
    ("FosOS", "Welcome", "Open the FosOS welcome again", "help-about-symbolic", ["fosos-welcome", "--again"]),
]


def read_release() -> dict[str, str]:
    values = {}
    for path in ("/etc/fosos-release", "/etc/os-release"):
        try:
            for line in Path(path).read_text(encoding="utf-8").splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    values.setdefault(key.strip(), value.strip().strip('"'))
        except OSError:
            continue
    return values


def memory_text() -> str:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                kib = int(line.split()[1])
                return f"{kib / 1024 / 1024:.1f} GiB"
    except (OSError, ValueError):
        pass
    return "Unknown"


def cpu_text() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.machine()


def disk_text() -> str:
    try:
        usage = shutil.disk_usage("/")
    except OSError:
        return "Unknown"
    gib = 1024**3
    return f"{usage.free / gib:.0f} GiB free of {usage.total / gib:.0f} GiB"


class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Settings")
        self.set_default_size(860, 580)
        self.set_icon_name("preferences-system")
        add_classes(self, "fos-root", "fos-window")

        root = Gtk.Box()
        self.add(root)

        sidebar = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2), "fos-sidebar")
        sidebar.set_size_request(200, -1)
        sidebar.set_border_width(8)
        brand = Gtk.Box(spacing=10)
        brand.set_margin_start(8)
        brand.set_margin_top(8)
        brand.set_margin_bottom(16)
        brand.pack_start(mark("md", inverse=True), False, False, 0)
        brand.pack_start(brand_title(14), False, False, 0)
        sidebar.pack_start(brand, False, False, 0)
        sidebar.pack_start(label("SETTINGS", "fos-small", "fos-muted"), False, False, 4)

        self.pages: dict[str, Gtk.Button] = {}
        for name, icon_name in (("All settings", "view-app-grid-symbolic"), ("About", "help-about-symbolic")):
            nav = button(name, icon_name=icon_name, variant="ghost", size="sm")
            nav.get_child().set_halign(Gtk.Align.START)
            nav.connect("clicked", lambda _b, n=name: self.show_page(n))
            self.pages[name] = nav
            sidebar.pack_start(nav, False, False, 0)
        root.pack_start(sidebar, False, False, 0)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.pack_start(main, True, True, 0)

        top = add_classes(Gtk.Box(spacing=12), "fos-card-header")
        self.heading = label("All settings", "fos-title")
        top.pack_start(self.heading, True, True, 0)
        self.search = add_classes(Gtk.Entry(), "fos-input")
        self.search.set_placeholder_text("Search settings")
        self.search.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "system-search-symbolic")
        self.search.set_width_chars(28)
        self.search.connect("changed", lambda _e: self.show_page("All settings"))
        top.pack_end(self.search, False, False, 0)
        main.pack_start(top, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.content = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20), "fos-card-content")
        scroller.add(self.content)
        main.pack_start(scroller, True, True, 0)

        self.status = add_classes(Gtk.Box(spacing=8), "fos-card-footer")
        self.status_text = label(f"FosOS Desktop {VERSION} · experimental", "fos-small", "fos-muted")
        self.status.pack_start(self.status_text, True, True, 0)
        main.pack_start(self.status, False, False, 0)

        self.show_page("All settings")

    def show_page(self, name: str) -> None:
        for page, nav in self.pages.items():
            ctx = nav.get_style_context()
            if page == name:
                ctx.add_class("secondary")
                ctx.remove_class("ghost")
            else:
                ctx.add_class("ghost")
                ctx.remove_class("secondary")
        self.heading.set_text(name)
        clear(self.content)
        if name == "About":
            self._about()
        else:
            self._all_settings(self.search.get_text().strip().lower())
        self.content.show_all()

    def _all_settings(self, query: str) -> None:
        groups: dict[str, list] = {}
        for entry in PANELS:
            group, title, desc, _icon, command = entry
            if shutil.which(command[0]) is None:
                continue
            if query and query not in f"{group} {title} {desc}".lower():
                continue
            groups.setdefault(group, []).append(entry)
        if not groups:
            text = "No settings match your search." if query else "No settings tools are installed."
            self.content.pack_start(label(text, "fos-text", "fos-muted"), False, False, 0)
            return
        for group, entries in groups.items():
            section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            section.pack_start(label(group, "fos-label"), False, False, 0)
            grid = Gtk.Grid(column_spacing=8, row_spacing=8, column_homogeneous=True)
            for index, (_group, title, desc, icon_name, command) in enumerate(entries):
                grid.attach(self._panel_tile(title, desc, icon_name, command), index % 3, index // 3, 1, 1)
            section.pack_start(grid, False, False, 0)
            self.content.pack_start(section, False, False, 0)

    def _panel_tile(self, title: str, desc: str, icon_name: str, command: list[str]) -> Gtk.Button:
        widget = button(variant="outline")
        add_classes(widget, "row")
        row = Gtk.Box(spacing=12)
        row.pack_start(tile(icon_name, "primary"), False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        texts.set_valign(Gtk.Align.CENTER)
        texts.pack_start(label(title, "fos-text", "fos-strong", ellipsize=True), False, False, 0)
        texts.pack_start(label(desc, "fos-small", "fos-muted", ellipsize=True), False, False, 0)
        row.pack_start(texts, True, True, 0)
        widget.add(row)
        widget.set_tooltip_text(desc)
        widget.connect("clicked", lambda _b: self._run(title, command))
        return widget

    def _run(self, title: str, command: list[str]) -> None:
        if appmod.spawn(command):
            self.status_text.set_text(f"Opened {title}.")
        else:
            self.status_text.set_text(f"{title} is not available on this system.")

    def _about(self) -> None:
        release = read_release()
        header = Gtk.Box(spacing=12)
        header.pack_start(mark("md", inverse=True), False, False, 0)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        names.pack_start(brand_title(14), False, False, 0)
        based_on = release.get("PRETTY_NAME") or release.get("BASE", "Debian Stable")
        names.pack_start(label(f"Based on {based_on}", "fos-text", "fos-muted"), False, False, 0)
        header.pack_start(names, False, False, 0)
        self.content.pack_start(header, False, False, 0)

        try:
            debian = Path("/etc/debian_version").read_text(encoding="utf-8").strip()
        except OSError:
            debian = "Unknown"
        rows = [
            ("Edition", release.get("EDITION", "Unknown")),
            ("Debian", debian),
            ("Desktop", f"FosOS Desktop {VERSION} (experimental), XFCE fallback"),
            ("Session", "Live session" if appmod.is_live() else "Installed system"),
            ("Kernel", platform.release()),
            ("Processor", cpu_text()),
            ("Memory", memory_text()),
            ("Disk", disk_text()),
            ("Computer name", os.uname().nodename),
        ]
        table = add_classes(Gtk.Grid(column_spacing=24, row_spacing=0), "fos-card")
        for index, (key, value) in enumerate(rows):
            key_label = label(key, "fos-text", "fos-muted")
            value_label = label(value, "fos-text", ellipsize=True)
            value_label.set_selectable(True)
            for widget in (key_label, value_label):
                widget.set_margin_top(8)
                widget.set_margin_bottom(8)
            key_label.set_margin_start(12)
            value_label.set_margin_end(12)
            value_label.set_hexpand(True)
            table.attach(key_label, 0, index, 1, 1)
            table.attach(value_label, 1, index, 1, 1)
        self.content.pack_start(table, False, False, 0)


class SettingsApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window: SettingsWindow | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_prgname("fosos-settings")
        GLib.set_application_name("Settings")
        load_css()

    def do_activate(self) -> None:
        if self.window is None:
            self.window = SettingsWindow(self)
            self.window.show_all()
        self.window.present()


def main() -> int:
    return SettingsApp().run(sys.argv)
