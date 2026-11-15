"""Applications, pinned apps and launching."""

import os
import pwd
import shutil
import subprocess
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from .ui import DATA_DIR

CONFIG_DIR = Path(GLib.get_user_config_dir()) / "fosos-desktop"
PINNED_FILE = CONFIG_DIR / "pinned"
DEFAULT_PINNED_FILE = DATA_DIR / "pinned"

# Short names and monochrome icons for the apps FosOS ships.
KNOWN_APPS = {
    "thunar.desktop": ("Files", "folder-symbolic"),
    "xfce4-terminal.desktop": ("Terminal", "utilities-terminal-symbolic"),
    "firefox-esr.desktop": ("Firefox", "web-browser-symbolic"),
    "fosos-settings.desktop": ("Settings", "preferences-system-symbolic"),
    "org.xfce.mousepad.desktop": ("Text Editor", "accessories-text-editor-symbolic"),
    "calamares-install-fosos.desktop": ("Install FosOS", "system-software-install-symbolic"),
    "fosos-welcome.desktop": ("Welcome", "help-about-symbolic"),
    "org.pulseaudio.pavucontrol.desktop": ("Sound", "audio-volume-high-symbolic"),
    "xfce4-screenshooter.desktop": ("Screenshot", "camera-photo-symbolic"),
}


def is_live() -> bool:
    try:
        return "boot=live" in Path("/proc/cmdline").read_text(encoding="utf-8")
    except OSError:
        return False


def user_display_name() -> str:
    try:
        entry = pwd.getpwuid(os.getuid())
    except KeyError:
        return GLib.get_user_name()
    gecos = entry.pw_gecos.split(",")[0].strip()
    return gecos or entry.pw_name


class App:
    """One launchable desktop entry."""

    def __init__(self, info: Gio.DesktopAppInfo) -> None:
        self.info = info
        self.id = info.get_id() or ""
        known = KNOWN_APPS.get(self.id)
        self.name = known[0] if known else (info.get_name() or self.id)
        self.symbolic = known[1] if known else None
        self.description = info.get_description() or info.get_generic_name() or ""

    def icon_name(self, symbolic: bool = True) -> str:
        if symbolic and self.symbolic:
            return self.symbolic
        gicon = self.info.get_icon()
        if isinstance(gicon, Gio.ThemedIcon):
            names = gicon.get_names()
            if names:
                theme = Gtk.IconTheme.get_default()
                if symbolic and theme.has_icon(f"{names[0]}-symbolic"):
                    return f"{names[0]}-symbolic"
                return names[0]
        return "application-x-executable-symbolic"

    def gicon(self) -> Gio.Icon | None:
        return self.info.get_icon()

    def search_text(self) -> str:
        parts = [
            self.name,
            self.info.get_name() or "",
            self.info.get_generic_name() or "",
            self.description,
            self.info.get_executable() or "",
            " ".join(self.info.get_keywords() or []),
            self.id,
        ]
        return " ".join(parts).lower()

    def window_classes(self) -> set[str]:
        names = set()
        wm_class = self.info.get_startup_wm_class()
        if wm_class:
            names.add(wm_class.lower())
        names.add(self.id.removesuffix(".desktop").lower())
        names.add(self.id.removesuffix(".desktop").split(".")[-1].lower())
        executable = self.info.get_executable()
        if executable:
            names.add(os.path.basename(executable).lower())
        return names

    def launch(self, uris: list[str] | None = None) -> bool:
        context = Gdk.Display.get_default().get_app_launch_context()
        try:
            if uris:
                return self.info.launch_uris(uris, context)
            return self.info.launch([], context)
        except GLib.Error:
            return False


def load_app(app_id: str) -> App | None:
    try:
        info = Gio.DesktopAppInfo.new(app_id)
    except TypeError:
        return None
    if info is None:
        return None
    return App(info)


def all_apps() -> list[App]:
    apps = []
    seen = set()
    for info in Gio.AppInfo.get_all():
        if not isinstance(info, Gio.DesktopAppInfo) or not info.should_show():
            continue
        app = App(info)
        if app.id in seen:
            continue
        seen.add(app.id)
        apps.append(app)
    apps.sort(key=lambda a: a.name.lower())
    return apps


def search_apps(query: str, apps: list[App]) -> list[App]:
    query = query.strip().lower()
    if not query:
        return []
    scored = []
    for app in apps:
        name = app.name.lower()
        if name.startswith(query):
            score = 0
        elif query in name:
            score = 1
        elif query in app.search_text():
            score = 2
        else:
            continue
        scored.append((score, name, app))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in scored]


class Pinned:
    """Pinned app ids, shared by the taskbar and the Start menu."""

    def __init__(self) -> None:
        self.ids: list[str] = []
        self.listeners = []
        self.load()

    def load(self) -> None:
        source = PINNED_FILE if PINNED_FILE.exists() else DEFAULT_PINNED_FILE
        ids = []
        try:
            for line in source.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and line not in ids:
                    ids.append(line)
        except OSError:
            ids = ["thunar.desktop", "xfce4-terminal.desktop", "firefox-esr.desktop"]
        self.ids = [app_id for app_id in ids if load_app(app_id) is not None]

    def apps(self) -> list[App]:
        return [app for app in (load_app(app_id) for app_id in self.ids) if app]

    def contains(self, app_id: str) -> bool:
        return app_id in self.ids

    def toggle(self, app_id: str) -> None:
        if app_id in self.ids:
            self.ids.remove(app_id)
        else:
            self.ids.append(app_id)
        self.save()
        for listener in self.listeners:
            listener()

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        PINNED_FILE.write_text("".join(f"{app_id}\n" for app_id in self.ids), encoding="utf-8")


def spawn(argv: list[str]) -> bool:
    if not argv or shutil.which(argv[0]) is None:
        return False
    try:
        subprocess.Popen(argv, start_new_session=True)
    except OSError:
        return False
    return True


def open_path(path: Path) -> bool:
    context = Gdk.Display.get_default().get_app_launch_context()
    try:
        return Gio.AppInfo.launch_default_for_uri(path.as_uri(), context)
    except GLib.Error:
        return spawn(["thunar", str(path)])


def user_dir(kind, fallback: str) -> Path:
    path = GLib.get_user_special_dir(kind)
    return Path(path) if path else Path.home() / fallback
