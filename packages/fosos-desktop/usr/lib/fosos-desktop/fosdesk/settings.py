"""fosos-settings: full-screen Settings shell (Windows 11–style navigation)."""

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

pages.register_extra_pages()

from .ui import add_classes, brand_title, button, clear, icon, label, load_css, mark, tile
from .windowchrome import CardWindow

APP_ID = "org.fosos.Settings"

# (group, title, description, icon, {"command": [...]} | {"page": "id"})
PANELS = [
    ("System", "Display", "Resolution, orientation and brightness", "video-display-symbolic", {"page": "display"}),
    ("System", "Sound", "Volume, output and input devices", "audio-volume-high-symbolic", {"page": "sound"}),
    (
        "System",
        "Network",
        "Wi-Fi, Ethernet and VPN connections",
        "network-wireless-symbolic",
        {"page": "network"},
    ),
    ("System", "Bluetooth", "Pair and manage devices", "bluetooth-active-symbolic", {"page": "bluetooth"}),
    (
        "System",
        "Remote Desktop",
        "Host RDP sessions and connect to other PCs",
        "network-server-symbolic",
        {"page": "remote"},
    ),
    (
        "System",
        "SSH",
        "Remote terminal access in and out",
        "utilities-terminal-symbolic",
        {"page": "ssh"},
    ),
    ("System", "Power", "Screen, lock, sleep and battery", "battery-good-symbolic", {"page": "power"}),
    ("System", "Storage", "Free space on disks", "drive-harddisk-symbolic", {"page": "storage"}),
    (
        "Personalization",
        "Wallpaper",
        "Drawn themes and image backgrounds",
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
        "Appearance",
        "Font size and cursor",
        "preferences-desktop-theme-symbolic",
        {"page": "appearance"},
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
        "Multitasking",
        "Virtual desktops",
        "view-grid-symbolic",
        {"page": "multitasking"},
    ),
    (
        "Personalization",
        "Notifications",
        "Focus assist, toasts, and per-app mutes",
        "preferences-system-notifications-symbolic",
        {"page": "notifications"},
    ),
    (
        "Personalization",
        "Night light",
        "Warmer colours at night",
        "weather-clear-night-symbolic",
        {"page": "nightlight"},
    ),
    ("Accounts", "Accounts", "Password, name and sign-in", "avatar-default-symbolic", {"page": "accounts"}),
    ("Input", "Keyboard", "Layout and key repeat", "input-keyboard-symbolic", {"page": "keyboard"}),
    (
        "Input",
        "Keyboard shortcuts",
        "Change desktop shortcuts",
        "preferences-desktop-keyboard-shortcuts-symbolic",
        {"page": "shortcuts"},
    ),
    ("Input", "Mouse and touchpad", "Pointer speed and tap-to-click", "input-mouse-symbolic", {"page": "mouse"}),
    (
        "Time & language",
        "Date & time",
        "Timezone and automatic clock sync",
        "preferences-system-time-symbolic",
        {"page": "datetime"},
    ),
    (
        "Time & language",
        "Region",
        "Formats for calendar, dates, time and numbers",
        "preferences-desktop-locale-symbolic",
        {"page": "region"},
    ),
    (
        "Apps",
        "Installed apps",
        "Uninstall programs on this PC",
        "system-software-install-symbolic",
        {"page": "apps"},
    ),
    ("Apps", "Default apps", "Browser, PDF, archives and more", "starred-symbolic", {"page": "defaults"}),
    ("Apps", "Startup", "Apps that launch when you sign in", "application-x-executable-symbolic", {"page": "startup"}),
    (
        "Accessibility",
        "Accessibility",
        "Larger text, sticky keys and reduce motion",
        "preferences-desktop-accessibility-symbolic",
        {"page": "accessibility"},
    ),
    (
        "Privacy",
        "Privacy",
        "Lock screen and clipboard",
        "security-high-symbolic",
        {"page": "privacy"},
    ),
    (
        "Privacy",
        "Firewall",
        "Block unexpected network connections",
        "network-wireless-encrypted-symbolic",
        {"page": "firewall"},
    ),
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
        # Built-in Display / Sound / Power no longer require external GUIs.
        if page_id == "network":
            return shutil.which("nmcli") is not None
        if page_id == "bluetooth":
            return shutil.which("bluetoothctl") is not None or shutil.which("blueman-manager") is not None
        return True
    command = action.get("command") or []
    return bool(command) and shutil.which(command[0]) is not None


class SettingsWindow(CardWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(
            app,
            title="Settings",
            icon_name="preferences-system-symbolic",
            default_width=1100,
            default_height=700,
        )
        self.set_icon_name("preferences-system")
        add_classes(self, "fos-settings-shell")
        self._nav_buttons: dict[str, Gtk.Button] = {}
        self._current_nav = "home"
        self._nav_entries: list[tuple[str, str, str, dict | None]] = []

        root = add_classes(Gtk.Box(), "fos-settings-root")
        self.body.pack_start(root, True, True, 0)

        # —— Left navigation (Windows Settings style) ——
        sidebar = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0), "fos-settings-nav")
        sidebar.set_size_request(280, -1)

        nav_head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        nav_head.set_margin_start(12)
        nav_head.set_margin_end(12)
        nav_head.set_margin_top(12)
        nav_head.set_margin_bottom(8)
        brand = Gtk.Box(spacing=10)
        brand.pack_start(mark("md"), False, False, 0)
        brand.pack_start(brand_title(14), False, False, 0)
        nav_head.pack_start(brand, False, False, 0)
        self.search = add_classes(Gtk.Entry(), "fos-input")
        self.search.set_placeholder_text("Find a setting")
        self.search.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "system-search-symbolic")
        self.search.connect("changed", self._on_search)
        nav_head.pack_start(self.search, False, False, 0)
        sidebar.pack_start(nav_head, False, False, 0)

        nav_scroll = Gtk.ScrolledWindow()
        nav_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.nav_list = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2), "fos-settings-nav-list")
        self.nav_list.set_margin_start(8)
        self.nav_list.set_margin_end(8)
        self.nav_list.set_margin_bottom(12)
        nav_scroll.add(self.nav_list)
        sidebar.pack_start(nav_scroll, True, True, 0)
        root.pack_start(sidebar, False, False, 0)

        # —— Main content ——
        main = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-settings-main")
        top = add_classes(Gtk.Box(spacing=12), "fos-settings-toolbar")
        self.back_btn = button(icon_name="go-previous-symbolic", size="icon-sm", tooltip="Back")
        self.back_btn.connect("clicked", lambda _b: self.show_home())
        self.back_btn.set_no_show_all(True)
        self.back_btn.hide()
        top.pack_start(self.back_btn, False, False, 0)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.heading = label("Home", "fos-title")
        self.subheading = label("System settings for FosOS", "fos-small", "fos-muted")
        titles.pack_start(self.heading, False, False, 0)
        titles.pack_start(self.subheading, False, False, 0)
        top.pack_start(titles, True, True, 0)
        main.pack_start(top, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.content = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20), "fos-settings-content")
        scroller.add(self.content)
        main.pack_start(scroller, True, True, 0)

        self.status = add_classes(Gtk.Box(spacing=8), "fos-app-footer")
        self.status_text = label(f"FosOS Desktop {VERSION}", "fos-small", "fos-muted")
        self.status.pack_start(self.status_text, True, True, 0)
        main.pack_start(self.status, False, False, 0)
        root.pack_start(main, True, True, 0)

        self._rebuild_nav()
        self.connect("map", self._on_map)
        self.show_home()

    def _on_map(self, _widget) -> None:
        self.maximize()

    def _rebuild_nav(self, query: str = "") -> None:
        clear(self.nav_list)
        self._nav_buttons.clear()
        self._nav_entries = []

        home = self._nav_button("home", "Home", "go-home-symbolic", None)
        self.nav_list.pack_start(home, False, False, 0)

        groups: dict[str, list] = {}
        for entry in PANELS:
            group, title, desc, icon_name, action = entry
            if not panel_available(action):
                continue
            if query and query not in f"{group} {title} {desc}".lower():
                continue
            groups.setdefault(group, []).append(entry)

        for group, entries in groups.items():
            header = label(group.upper(), "fos-small", "fos-muted")
            header.set_margin_top(10)
            header.set_margin_bottom(2)
            header.set_margin_start(8)
            self.nav_list.pack_start(header, False, False, 0)
            for _group, title, _desc, icon_name, action in entries:
                key = action.get("page") or f"cmd:{title}"
                nav = self._nav_button(key, title, icon_name, action)
                self.nav_list.pack_start(nav, False, False, 0)
                self._nav_entries.append((key, title, icon_name, action))

        about = self._nav_button("about", "About", "help-about-symbolic", None)
        self.nav_list.pack_start(about, False, False, 0)
        self.nav_list.show_all()
        self._highlight_nav(self._current_nav)

    def _nav_button(self, key: str, title: str, icon_name: str, action: dict | None) -> Gtk.Button:
        nav = button(title, icon_name=icon_name, variant="ghost", size="sm")
        add_classes(nav, "fos-settings-nav-item")
        child = nav.get_child()
        if child is not None:
            child.set_halign(Gtk.Align.START)
        nav.connect("clicked", lambda _b, k=key, a=action, t=title: self._on_nav(k, a, t))
        self._nav_buttons[key] = nav
        return nav

    def _on_nav(self, key: str, action: dict | None, title: str) -> None:
        self.search.set_text("")
        if key == "home":
            self.show_home()
            return
        if key == "about":
            self.show_about()
            return
        if action is None:
            return
        self._open(title, action)

    def _highlight_nav(self, key: str) -> None:
        self._current_nav = key
        for name, nav in self._nav_buttons.items():
            ctx = nav.get_style_context()
            if name == key:
                ctx.add_class("secondary")
                ctx.remove_class("ghost")
            else:
                ctx.add_class("ghost")
                ctx.remove_class("secondary")

    def _on_search(self, _entry) -> None:
        query = self.search.get_text().strip().lower()
        self._rebuild_nav(query)
        if self._current_nav == "home" or query:
            self.show_home(query)

    def _set_status(self, text: str) -> None:
        self.status_text.set_text(text)

    def show_home(self, query: str | None = None) -> None:
        needle = (query if query is not None else self.search.get_text()).strip().lower()
        self._highlight_nav("home")
        self.back_btn.hide()
        self.heading.set_text("Home")
        self.subheading.set_text("System settings for FosOS")
        self.set_header_title("Settings")
        clear(self.content)

        # System strip (Windows Settings home account / device card)
        release = read_release()
        hero = add_classes(Gtk.Box(spacing=16), "fos-settings-hero")
        hero.pack_start(mark("lg"), False, False, 0)
        hero_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        hero_text.pack_start(brand_title(18), False, False, 0)
        based_on = release.get("PRETTY_NAME") or release.get("BASE", "Debian")
        hero_text.pack_start(
            label(f"{os.uname().nodename} · {based_on}", "fos-text", "fos-muted", ellipsize=True),
            False,
            False,
            0,
        )
        hero_text.pack_start(
            label(f"{cpu_text()} · {memory_text()} · {disk_text()}", "fos-small", "fos-muted", ellipsize=True),
            False,
            False,
            0,
        )
        hero.pack_start(hero_text, True, True, 0)
        about_btn = button("About", variant="outline", size="sm")
        about_btn.connect("clicked", lambda _b: self.show_about())
        hero.pack_end(about_btn, False, False, 0)
        self.content.pack_start(hero, False, False, 0)

        groups: dict[str, list] = {}
        for entry in PANELS:
            group, title, desc, _icon, action = entry
            if not panel_available(action):
                continue
            if needle and needle not in f"{group} {title} {desc}".lower():
                continue
            groups.setdefault(group, []).append(entry)

        if not groups:
            text = "No settings match your search." if needle else "No settings tools are installed."
            self.content.pack_start(label(text, "fos-text", "fos-muted"), False, False, 0)
            self.content.show_all()
            return

        for group, entries in groups.items():
            section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            section.pack_start(label(group, "fos-label"), False, False, 0)
            grid = Gtk.Grid(column_spacing=8, row_spacing=8, column_homogeneous=True)
            for index, (_group, title, desc, icon_name, action) in enumerate(entries):
                grid.attach(self._panel_tile(title, desc, icon_name, action), index % 2, index // 2, 1, 1)
            section.pack_start(grid, False, False, 0)
            self.content.pack_start(section, False, False, 0)
        self.content.show_all()

    def show_about(self) -> None:
        self._highlight_nav("about")
        self.back_btn.show()
        self.heading.set_text("About")
        self.subheading.set_text("Device specifications and FosOS edition")
        self.set_header_title("About · Settings")
        clear(self.content)
        self._about()
        self.content.show_all()

    def show_builtin(self, page_id: str) -> None:
        entry = pages.PAGES.get(page_id)
        if entry is None:
            self.status_text.set_text("That settings page is not available.")
            return
        title, builder = entry
        self._highlight_nav(page_id)
        self.back_btn.show()
        self.heading.set_text(title)
        self.subheading.set_text("System")
        for group, panel_title, desc, _icon, action in PANELS:
            if action.get("page") == page_id:
                self.subheading.set_text(desc)
                break
        self.set_header_title(f"{title} · Settings")
        clear(self.content)
        self.content.pack_start(builder(self._set_status), False, False, 0)
        self.content.show_all()

    def _panel_tile(self, title: str, desc: str, icon_name: str, action: dict) -> Gtk.Button:
        widget = button(variant="ghost")
        add_classes(widget, "row", "fos-settings-tile")
        row = Gtk.Box(spacing=12)
        row.pack_start(tile(icon_name, "primary", size=28), False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        texts.set_valign(Gtk.Align.CENTER)
        texts.pack_start(label(title, "fos-text", "fos-strong", ellipsize=True), False, False, 0)
        texts.pack_start(label(desc, "fos-small", "fos-muted", ellipsize=True), False, False, 0)
        row.pack_start(texts, True, True, 0)
        row.pack_end(icon("go-next-symbolic", 14), False, False, 0)
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
        header = add_classes(Gtk.Box(spacing=12), "fos-settings-hero")
        header.pack_start(mark("md"), False, False, 0)
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
        table = add_classes(Gtk.Grid(column_spacing=24, row_spacing=0), "fos-settings-card")
        for index, (key, value) in enumerate(rows):
            key_label = label(key, "fos-text", "fos-muted")
            value_label = label(value, "fos-text", ellipsize=True)
            value_label.set_selectable(True)
            for widget in (key_label, value_label):
                widget.set_margin_top(10)
                widget.set_margin_bottom(10)
            key_label.set_margin_start(16)
            value_label.set_margin_end(16)
            value_label.set_hexpand(True)
            table.attach(key_label, 0, index, 1, 1)
            table.attach(value_label, 1, index, 1, 1)
        self.content.pack_start(table, False, False, 0)

        storage_heading = label("Storage", "fos-label")
        storage_heading.set_margin_top(8)
        self.content.pack_start(storage_heading, False, False, 0)
        storage = add_classes(Gtk.Grid(column_spacing=24, row_spacing=0), "fos-settings-card")
        for index, (mount, text) in enumerate(pages.storage_rows()):
            key_label = label(mount, "fos-text", "fos-muted")
            value_label = label(text, "fos-text", ellipsize=True)
            value_label.set_selectable(True)
            for widget in (key_label, value_label):
                widget.set_margin_top(10)
                widget.set_margin_bottom(10)
            key_label.set_margin_start(16)
            value_label.set_margin_end(16)
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
        # Do not force maximize — shell restores last size/position (Win11-like).
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
        self.window.show_home()


def main() -> int:
    return SettingsApp().run(sys.argv)
