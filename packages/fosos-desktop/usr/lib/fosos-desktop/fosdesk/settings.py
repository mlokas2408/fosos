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
from . import settings_pages as pages
from .ui import add_classes, brand_title, button, clear, label, load_css, mark, tile

APP_ID = "org.fosos.Settings"

# External tools or built-in page ids.
# (group, title, description, icon, {"command": [...]} | {"page": "id"})
PANELS = [
    ("System", "Display", "Resolution, scaling and monitors", "video-display-symbolic", {"page": "display"}),
    ("System", "Sound", "Output, input and volume", "audio-volume-high-symbolic", {"page": "sound"}),
    (
        "System",
        "Network",
        "Wi-Fi, cable and VPN connections",
        "network-wireless-symbolic",
        {"page": "network"},
    ),
    ("System", "Bluetooth", "Pair and manage devices", "bluetooth-active-symbolic", {"page": "bluetooth"}),
    ("System", "Power", "Idle blanking and suspend", "battery-good-symbolic", {"page": "power"}),
    ("System", "Storage", "Free space on disks", "drive-harddisk-symbolic", {"page": "storage"}),
    (
        "Personalization",
        "Wallpaper",
        "Dawn Aperture and other drawn backgrounds",
        "preferences-desktop-wallpaper-symbolic",
        {"page": "wallpaper"},
    ),
    (
        "Personalization",
        "Personalize",
        "Desktop icons and click behavior",
        "user-desktop-symbolic",
        {"page": "desktop"},
    ),
    (
        "Personalization",
        "Taskbar",
        "Desktop switcher, clock and notification bell",
        "view-continuous-symbolic",
        {"page": "taskbar"},
    ),
    (
        "Personalization",
        "Notifications",
        "Toasts, Do not disturb and duration",
        "preferences-system-notifications-symbolic",
        {"page": "notifications"},
    ),
    ("Input", "Keyboard", "Layout, repeat and shortcuts", "input-keyboard-symbolic", {"page": "keyboard"}),
    ("Input", "Mouse and touchpad", "Pointer speed and buttons", "input-mouse-symbolic", {"page": "mouse"}),
    ("Apps", "Default apps", "Browser, PDF, archives and more", "starred-symbolic", {"page": "defaults"}),
    (
        "FosOS",
        "Updates",
        "Check status and install Debian / FosOS updates",
        "software-update-available-symbolic",
        {"page": "updates"},
    ),
    ("FosOS", "Welcome", "Open the FosOS welcome again", "help-about-symbolic", {"command": ["fosos-welcome", "--again"]}),
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


def panel_available(action: dict) -> bool:
    if "page" in action:
        page_id = action["page"]
        if page_id not in pages.PAGES:
            return False
        # Tool wrappers need their binary present.
        commands = {
            "display": "arandr",
            "sound": "pavucontrol",
            "network": "nm-connection-editor",
            "bluetooth": "blueman-manager",
        }
        binary = commands.get(page_id)
        if binary is not None and shutil.which(binary) is None:
            return False
        return True
    command = action.get("command") or []
    return bool(command) and shutil.which(command[0]) is not None


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
        self.status_text = label(f"FosOS Desktop {VERSION}", "fos-small", "fos-muted")
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

    def show_builtin(self, page_id: str) -> None:
        entry = pages.PAGES.get(page_id)
        if entry is None:
            self.status_text.set_text("That settings page is not available.")
            return
        title, builder = entry
        for page, nav in self.pages.items():
            ctx = nav.get_style_context()
            ctx.add_class("ghost")
            ctx.remove_class("secondary")
        self.heading.set_text(title)
        clear(self.content)
        back = button("Back to all settings", variant="ghost", size="sm")
        back.connect("clicked", lambda _b: self.show_page("All settings"))
        self.content.pack_start(back, False, False, 0)
        self.content.pack_start(builder(self._set_status), False, False, 0)
        self.content.show_all()

    def _set_status(self, text: str) -> None:
        self.status_text.set_text(text)

    def _all_settings(self, query: str) -> None:
        groups: dict[str, list] = {}
        for entry in PANELS:
            group, title, desc, _icon, action = entry
            if not panel_available(action):
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
            for index, (_group, title, desc, icon_name, action) in enumerate(entries):
                grid.attach(self._panel_tile(title, desc, icon_name, action), index % 3, index // 3, 1, 1)
            section.pack_start(grid, False, False, 0)
            self.content.pack_start(section, False, False, 0)

    def _panel_tile(self, title: str, desc: str, icon_name: str, action: dict) -> Gtk.Button:
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
        widget.connect("clicked", lambda _b: self._open(title, action))
        return widget

    def _open(self, title: str, action: dict) -> None:
        if "page" in action:
            self.show_builtin(action["page"])
            return
        command = action.get("command") or []
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
            ("Desktop", f"FosOS Desktop {VERSION}; recovery session available"),
            ("Session", "Live session" if appmod.is_live() else "Installed system"),
            ("Kernel", platform.release()),
            ("Processor", cpu_text()),
            ("Memory", memory_text()),
            ("Computer name", os.uname().nodename),
        ]
        if pages.reboot_required():
            rows.append(("Updates", "Restart required to finish some updates"))
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

        storage_heading = label("Storage", "fos-label")
        storage_heading.set_margin_top(8)
        self.content.pack_start(storage_heading, False, False, 0)
        storage = add_classes(Gtk.Grid(column_spacing=24, row_spacing=0), "fos-card")
        for index, (mount, text) in enumerate(pages.storage_rows()):
            key_label = label(mount, "fos-text", "fos-muted")
            value_label = label(text, "fos-text", ellipsize=True)
            value_label.set_selectable(True)
            for widget in (key_label, value_label):
                widget.set_margin_top(8)
                widget.set_margin_bottom(8)
            key_label.set_margin_start(12)
            value_label.set_margin_end(12)
            value_label.set_hexpand(True)
            storage.attach(key_label, 0, index, 1, 1)
            storage.attach(value_label, 1, index, 1, 1)
        self.content.pack_start(storage, False, False, 0)

        actions = Gtk.Box(spacing=8)
        actions.set_margin_top(8)
        open_storage = button("Storage details", variant="outline", size="sm")
        open_storage.connect("clicked", lambda _b: self.show_builtin("storage"))
        actions.pack_start(open_storage, False, False, 0)
        open_updates = button("Updates", variant="outline", size="sm")
        open_updates.connect("clicked", lambda _b: self.show_builtin("updates"))
        actions.pack_start(open_updates, False, False, 0)
        self.content.pack_start(actions, False, False, 0)


class SettingsApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window: SettingsWindow | None = None
        self._pending_builtin: str | None = None
        self._pending_open: str | None = None

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
        if self._pending_builtin:
            self.window.show_builtin(self._pending_builtin)
            self._pending_builtin = None
        elif self._pending_open:
            self._open_named(self._pending_open)
            self._pending_open = None

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        args = command_line.get_arguments()[1:]
        if "--builtin" in args:
            index = args.index("--builtin")
            self._pending_builtin = args[index + 1] if index + 1 < len(args) else None
            self._pending_open = None
        elif "--open" in args:
            index = args.index("--open")
            self._pending_open = args[index + 1] if index + 1 < len(args) else None
            self._pending_builtin = None
        self.activate()
        return 0

    def _open_named(self, title: str) -> None:
        if self.window is None:
            return
        needle = title.strip().lower()
        for _group, panel_title, _desc, _icon, action in PANELS:
            if panel_title.lower() != needle:
                continue
            self.window._open(panel_title, action)
            return
        self.window.show_page("All settings")


def main() -> int:
    return SettingsApp().run(sys.argv)
