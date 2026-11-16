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
    "fosos-files.desktop": ("Files", "folder-symbolic"),
    "fosos-terminal.desktop": ("Terminal", "utilities-terminal-symbolic"),
    "fosos-notepad.desktop": ("Notepad", "accessories-text-editor-symbolic"),
    "thunar.desktop": ("Thunar", "folder-symbolic"),
    "xfce4-terminal.desktop": ("XFCE Terminal", "utilities-terminal-symbolic"),
    "firefox-esr.desktop": ("Firefox", "web-browser-symbolic"),
    "fosos-settings.desktop": ("Settings", "preferences-system-symbolic"),
    "fosos-remote.desktop": ("Remote Desktop", "network-server-symbolic"),
    "org.xfce.mousepad.desktop": ("Mousepad", "accessories-text-editor-symbolic"),
    "calamares-install-fosos.desktop": ("Install FosOS", "system-software-install-symbolic"),
    "fosos-welcome.desktop": ("Welcome", "help-about-symbolic"),
    "org.pulseaudio.pavucontrol.desktop": ("Sound", "audio-volume-high-symbolic"),
    "xfce4-screenshooter.desktop": ("Screenshot", "camera-photo-symbolic"),
    "fosos-screenshot.desktop": ("Screenshot", "camera-photo-symbolic"),
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


def user_dir(kind, fallback: str) -> Path:
    path = GLib.get_user_special_dir(kind)
    return Path(path) if path else Path.home() / fallback


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


def recent_paths(limit: int = 8) -> list[Path]:
    """Recent local files and folders for Start Recommended / search."""
    seen: set[str] = set()
    found: list[tuple[float, Path]] = []

    def add(path: Path, mtime: float | None = None) -> None:
        try:
            path = path.expanduser().resolve()
        except OSError:
            return
        key = str(path)
        if key in seen or not path.exists():
            return
        seen.add(key)
        try:
            stamp = mtime if mtime is not None else path.stat().st_mtime
        except OSError:
            return
        found.append((stamp, path))

    try:
        manager = Gtk.RecentManager.get_default()
        for item in manager.get_items():
            if item.get_private_hint() or not item.exists():
                continue
            uri = item.get_uri()
            if not uri.startswith("file://"):
                continue
            try:
                path = Path(GLib.filename_from_uri(uri)[0])
            except (GLib.Error, TypeError, ValueError):
                continue
            add(path, item.get_modified())
    except GLib.Error:
        pass

    for kind, fallback in (
        (GLib.UserDirectory.DIRECTORY_DOWNLOAD, "Downloads"),
        (GLib.UserDirectory.DIRECTORY_DOCUMENTS, "Documents"),
        (GLib.UserDirectory.DIRECTORY_DESKTOP, "Desktop"),
    ):
        folder = user_dir(kind, fallback)
        add(folder)
        try:
            children = [p for p in folder.iterdir() if not p.name.startswith(".")]
        except OSError:
            continue
        children.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        for child in children[:6]:
            add(child)

    found.sort(key=lambda item: item[0], reverse=True)
    return [path for _mtime, path in found[:limit]]


def search_paths(query: str, limit: int = 8) -> list[Path]:
    query = query.strip().lower()
    if not query:
        return []
    matches = []
    for path in recent_paths(24):
        name = path.name.lower()
        if query in name or query in str(path).lower():
            matches.append(path)
        if len(matches) >= limit:
            break
    return matches


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
            ids = [
                "fosos-files.desktop",
                "fosos-terminal.desktop",
                "fosos-notepad.desktop",
                "firefox-esr.desktop",
            ]
        self.ids = [app_id for app_id in ids if load_app(app_id) is not None]

    def apps(self) -> list[App]:
        return [app for app in (load_app(app_id) for app_id in self.ids) if app]

    def contains(self, app_id: str) -> bool:
        return app_id in self.ids

    def _notify(self) -> None:
        self.save()
        for listener in self.listeners:
            listener()

    def toggle(self, app_id: str) -> None:
        if app_id in self.ids:
            self.ids.remove(app_id)
        else:
            self.ids.append(app_id)
        self._notify()

    def pin(self, app_id: str) -> None:
        if not app_id or app_id in self.ids:
            return
        self.ids.append(app_id)
        self._notify()

    def unpin(self, app_id: str) -> None:
        if app_id not in self.ids:
            return
        self.ids.remove(app_id)
        self._notify()

    def move(self, app_id: str, new_index: int) -> None:
        if app_id not in self.ids:
            return
        ids = [item for item in self.ids if item != app_id]
        new_index = max(0, min(new_index, len(ids)))
        ids.insert(new_index, app_id)
        if ids == self.ids:
            return
        self.ids = ids
        self._notify()

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
        if path.is_dir():
            return spawn(["fosos-files", str(path)])
        return False
