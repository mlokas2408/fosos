"""FosOS Store: browse and install desktop apps from APT via AppStream."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass

import gi

gi.require_version("AppStream", "1.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import AppStream, Gio, GLib, Gtk

from . import apps as appmod
from .ui import (
    FosDialog,
    add_classes,
    button,
    clear,
    fos_alert,
    fos_confirm,
    icon,
    label,
    load_css,
    set_class,
)
from .windowchrome import CardWindow

APP_ID = "org.fosos.Store"
_PKG_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")

# Curated Home picks (Debian package names).
FEATURED_PACKAGES = (
    "firefox-esr",
    "libreoffice-writer",
    "gimp",
    "inkscape",
    "vlc",
    "thunderbird",
    "gedit",
    "transmission-gtk",
)

# (nav_key, title, AppStream category names or None for special pages)
NAV_ITEMS: tuple[tuple[str, str, tuple[str, ...] | None], ...] = (
    ("home", "Home", None),
    ("installed", "Installed", None),
    ("office", "Productivity", ("Office", "Publishing", "TextEditor")),
    ("graphics", "Graphics", ("Graphics", "Photography", "Scanning")),
    ("audio", "Music & video", ("AudioVideo", "Audio", "Video", "Player", "TV")),
    ("games", "Games", ("Game",)),
    ("internet", "Internet", ("Network", "WebBrowser", "Email", "Chat", "InstantMessaging")),
    ("development", "Development", ("Development", "IDE", "Debugger")),
    ("education", "Education", ("Education", "Science")),
    ("utilities", "Utilities", ("Utility", "System", "Settings", "Archiving")),
)


@dataclass
class StoreAppInfo:
    component_id: str
    name: str
    summary: str
    description: str
    package: str
    categories: tuple[str, ...]
    icon_name: str
    desktop_id: str | None


def _pkgname(component: AppStream.Component) -> str:
    name = (component.get_pkgname() or "").strip()
    if name and _PKG_RE.match(name):
        return name
    for candidate in component.get_pkgnames() or []:
        candidate = (candidate or "").strip()
        if candidate and _PKG_RE.match(candidate):
            return candidate
    return ""


def _icon_name(component: AppStream.Component) -> str:
    theme = Gtk.IconTheme.get_default()
    for entry in component.get_icons() or []:
        kind = entry.get_kind()
        name = (entry.get_name() or "").strip()
        if not name:
            continue
        if kind == AppStream.IconKind.STOCK and theme.has_icon(name):
            return name
        if kind == AppStream.IconKind.CACHED and theme.has_icon(name):
            return name
    for entry in component.get_icons() or []:
        name = (entry.get_name() or "").strip()
        if name and theme.has_icon(name):
            return name
    return "application-x-executable-symbolic"


def _desktop_id(component: AppStream.Component) -> str | None:
    for launchable in component.get_launchables() or []:
        if launchable.get_kind() != AppStream.LaunchableKind.DESKTOP_ID:
            continue
        for value in launchable.get_entries() or []:
            value = (value or "").strip()
            if value:
                return value if value.endswith(".desktop") else f"{value}.desktop"
    cid = (component.get_id() or "").strip()
    if cid.endswith(".desktop"):
        return cid
    return None


def _plain_description(markup: str) -> str:
    text = re.sub(r"<[^>]+>", " ", markup or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _wrap_component(component: AppStream.Component) -> StoreAppInfo | None:
    if component.get_kind() != AppStream.ComponentKind.DESKTOP_APP:
        return None
    package = _pkgname(component)
    if not package:
        return None
    name = (component.get_name() or package).strip()
    summary = (component.get_summary() or "").strip()
    description = _plain_description(component.get_description() or "")
    categories = tuple(sorted({c for c in (component.get_categories() or []) if c}))
    return StoreAppInfo(
        component_id=component.get_id() or package,
        name=name,
        summary=summary,
        description=description,
        package=package,
        categories=categories,
        icon_name=_icon_name(component),
        desktop_id=_desktop_id(component),
    )


def _read_installed_packages() -> set[str]:
    """One dpkg-query for the whole status database (avoids per-row freezes)."""
    installed: set[str] = set()
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Package}\t${db:Status-Status}\n"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return installed
    if result.returncode != 0:
        return installed
    for line in (result.stdout or "").splitlines():
        if "\t" not in line:
            continue
        name, status = line.split("\t", 1)
        if status.strip() == "installed" and _PKG_RE.match(name):
            installed.add(name)
    return installed


class StoreCatalog:
    """Lazy AppStream pool wrapper."""

    def __init__(self) -> None:
        self.pool: AppStream.Pool | None = None
        self._by_package: dict[str, StoreAppInfo] = {}
        self._apps: list[StoreAppInfo] = []
        self._installed: set[str] = set()
        self.error: str | None = None

    def load(self) -> None:
        self.error = None
        self._by_package.clear()
        self._apps.clear()
        self._installed.clear()
        try:
            pool = AppStream.Pool.new()
            pool.set_load_std_data_locations(True)
            pool.load()
            self.pool = pool
        except GLib.Error as exc:
            self.pool = None
            self.error = exc.message
            return

        box = pool.get_components_by_kind(AppStream.ComponentKind.DESKTOP_APP)
        seen: set[str] = set()
        for index in range(box.get_size()):
            info = _wrap_component(box.index_safe(index))
            if info is None or info.package in seen:
                continue
            seen.add(info.package)
            self._by_package[info.package] = info
            self._apps.append(info)
        self._apps.sort(key=lambda item: item.name.lower())
        self.refresh_installed()

    def refresh_installed(self) -> None:
        self._installed = _read_installed_packages()

    def package_installed(self, name: str) -> bool:
        return bool(name) and name in self._installed

    def package_can_uninstall(self, name: str) -> bool:
        return self.package_installed(name) and name not in appmod.PROTECTED_PACKAGES

    @property
    def ready(self) -> bool:
        return self.pool is not None and not self.error

    def all_apps(self) -> list[StoreAppInfo]:
        return list(self._apps)

    def featured(self) -> list[StoreAppInfo]:
        found: list[StoreAppInfo] = []
        for package in FEATURED_PACKAGES:
            info = self._by_package.get(package)
            if info is not None:
                found.append(info)
        return found

    def by_categories(self, categories: tuple[str, ...], *, limit: int = 150) -> list[StoreAppInfo]:
        wanted = {name.lower() for name in categories}
        found = [
            app
            for app in self._apps
            if any(category.lower() in wanted for category in app.categories)
        ]
        return found[:limit]

    def installed(self) -> list[StoreAppInfo]:
        return [app for app in self._apps if app.package in self._installed]

    def search(self, query: str) -> list[StoreAppInfo]:
        needle = query.strip().lower()
        if not needle or self.pool is None:
            return []
        box = self.pool.search(needle)
        results: list[StoreAppInfo] = []
        seen: set[str] = set()
        for index in range(box.get_size()):
            info = _wrap_component(box.index_safe(index))
            if info is None or info.package in seen:
                continue
            seen.add(info.package)
            results.append(info)
        results.sort(key=lambda item: item.name.lower())
        return results


class StoreWindow(CardWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(
            app,
            title="Store",
            icon_name="system-software-install-symbolic",
            default_width=1100,
            default_height=720,
        )
        self.set_icon_name("system-software-install")
        add_classes(self, "fos-store-shell")

        self.catalog = StoreCatalog()
        self._nav_key = "home"
        self._nav_buttons: dict[str, Gtk.Button] = {}
        self._selected: StoreAppInfo | None = None
        self._busy = False
        self._query = ""

        root = add_classes(Gtk.Box(), "fos-store-root")
        self.body.pack_start(root, True, True, 0)

        sidebar = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0), "fos-store-nav")
        sidebar.set_size_request(220, -1)
        nav_scroll = Gtk.ScrolledWindow()
        nav_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.nav_list = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2), "fos-store-nav-list")
        self.nav_list.set_margin_start(8)
        self.nav_list.set_margin_end(8)
        self.nav_list.set_margin_top(12)
        self.nav_list.set_margin_bottom(12)
        for key, title, _cats in NAV_ITEMS:
            nav = button(title, variant="ghost", size="sm")
            add_classes(nav, "fos-store-nav-item")
            child = nav.get_child()
            if child is not None:
                child.set_halign(Gtk.Align.START)
            nav.connect("clicked", lambda _b, k=key: self._show_nav(k))
            self._nav_buttons[key] = nav
            self.nav_list.pack_start(nav, False, False, 0)
        nav_scroll.add(self.nav_list)
        sidebar.pack_start(nav_scroll, True, True, 0)
        refresh = button("Get updates", variant="outline", size="sm")
        refresh.set_margin_start(8)
        refresh.set_margin_end(8)
        refresh.set_margin_bottom(12)
        refresh.set_tooltip_text("Refresh the package catalog (apt update)")
        refresh.connect("clicked", lambda _b: self._refresh_catalog())
        sidebar.pack_start(refresh, False, False, 0)
        root.pack_start(sidebar, False, False, 0)

        main = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-store-main")
        top = add_classes(Gtk.Box(spacing=12), "fos-store-toolbar")
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.heading = label("Home", "fos-title")
        self.subheading = label("Featured apps from Debian", "fos-small", "fos-muted")
        titles.pack_start(self.heading, False, False, 0)
        titles.pack_start(self.subheading, False, False, 0)
        top.pack_start(titles, True, True, 0)
        self.search = add_classes(Gtk.Entry(), "fos-input", "fos-store-search")
        self.search.set_placeholder_text("Search apps")
        self.search.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "system-search-symbolic")
        self.search.set_size_request(260, -1)
        self.search.connect("changed", self._on_search)
        top.pack_end(self.search, False, False, 0)
        main.pack_start(top, False, False, 0)

        body = Gtk.Box(spacing=0)
        list_scroll = Gtk.ScrolledWindow()
        list_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        list_scroll.set_hexpand(True)
        self.list_box = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0), "fos-store-list")
        list_scroll.add(self.list_box)
        body.pack_start(list_scroll, True, True, 0)

        detail_scroll = Gtk.ScrolledWindow()
        detail_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        detail_scroll.set_size_request(340, -1)
        self.detail = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "fos-store-detail")
        detail_scroll.add(self.detail)
        body.pack_start(detail_scroll, False, False, 0)
        main.pack_start(body, True, True, 0)

        self.status = add_classes(Gtk.Box(spacing=8), "fos-app-footer")
        self.status_text = label("Loading catalog…", "fos-small", "fos-muted")
        self.status.pack_start(self.status_text, True, True, 0)
        main.pack_start(self.status, False, False, 0)
        root.pack_start(main, True, True, 0)

        self.connect("map", self._on_map)
        self.show_all()
        GLib.idle_add(self._bootstrap)

    def _on_map(self, _widget) -> None:
        self.maximize()

    def _set_status(self, text: str) -> None:
        self.status_text.set_text(text)

    def _bootstrap(self) -> bool:
        self.catalog.load()
        if self.catalog.error:
            self._set_status(f"Catalog error: {self.catalog.error}")
        elif not self.catalog.all_apps():
            self._set_status("Catalog is empty. Click Get updates to download app metadata.")
        else:
            self._set_status(f"{len(self.catalog.all_apps())} apps available.")
        self._show_nav("home")
        return False

    def _highlight_nav(self, key: str) -> None:
        self._nav_key = key
        for name, nav in self._nav_buttons.items():
            set_class(nav, "secondary", name == key)
            set_class(nav, "ghost", name != key)

    def _on_search(self, _entry) -> None:
        self._query = self.search.get_text().strip()
        self._render_list()

    def _show_nav(self, key: str) -> None:
        self._highlight_nav(key)
        title = next((t for k, t, _ in NAV_ITEMS if k == key), key)
        self.heading.set_text(title)
        if key == "home":
            self.subheading.set_text("Featured apps from Debian")
        elif key == "installed":
            self.subheading.set_text("Apps installed from the Store catalog")
        else:
            self.subheading.set_text("Desktop apps you can install")
        self.set_header_title(f"{title} · Store")
        self._selected = None
        self._render_list()
        self._render_detail()

    def _current_apps(self) -> list[StoreAppInfo]:
        if self._query:
            return self.catalog.search(self._query)
        if self._nav_key == "home":
            featured = self.catalog.featured()
            return featured or self.catalog.all_apps()[:24]
        if self._nav_key == "installed":
            return self.catalog.installed()
        cats = next((c for k, _t, c in NAV_ITEMS if k == self._nav_key), None)
        if cats:
            return self.catalog.by_categories(cats)
        return self.catalog.all_apps()

    def _render_list(self) -> None:
        clear(self.list_box)
        if not self.catalog.ready and self.catalog.error:
            self.list_box.pack_start(
                label(f"Could not load the catalog.\n{self.catalog.error}", "fos-text", "fos-muted"),
                False,
                False,
                0,
            )
            self.list_box.show_all()
            return
        if not self.catalog.all_apps():
            empty = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "fos-store-empty")
            empty.pack_start(label("No apps in the catalog yet.", "fos-text", "fos-strong"), False, False, 0)
            empty.pack_start(
                label("Click Get updates to download Debian app metadata (apt update).", "fos-small", "fos-muted"),
                False,
                False,
                0,
            )
            self.list_box.pack_start(empty, False, False, 0)
            self.list_box.show_all()
            return

        apps = self._current_apps()
        if self._query:
            self.heading.set_text("Search results")
            self.subheading.set_text(f"{len(apps)} match{'es' if len(apps) != 1 else ''} for “{self._query}”")

        if not apps:
            msg = "No apps match your search." if self._query else "No apps in this category."
            self.list_box.pack_start(label(msg, "fos-text", "fos-muted"), False, False, 0)
            self.list_box.show_all()
            return

        card = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-settings-card", "fos-store-card")
        for index, app in enumerate(apps):
            row = self._app_row(app)
            card.pack_start(row, False, False, 0)
            if index < len(apps) - 1:
                card.pack_start(add_classes(Gtk.Box(), "fos-settings-row-sep"), False, False, 0)
        self.list_box.pack_start(card, False, False, 0)
        self.list_box.show_all()
        if self._selected is None and apps:
            self._select(apps[0])
        elif self._selected is not None:
            still = next((a for a in apps if a.package == self._selected.package), None)
            if still is None and apps:
                self._select(apps[0])
            elif still is not None:
                self._select(still)

    def _app_row(self, app: StoreAppInfo) -> Gtk.Button:
        widget = button(variant="ghost")
        add_classes(widget, "row", "fos-store-row")
        widget.store_package = app.package  # type: ignore[attr-defined]
        selected = self._selected is not None and self._selected.package == app.package
        set_class(widget, "secondary", selected)
        set_class(widget, "ghost", not selected)
        inner = Gtk.Box(spacing=12)
        inner.pack_start(icon(app.icon_name, 28), False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        texts.set_valign(Gtk.Align.CENTER)
        texts.set_hexpand(True)
        texts.pack_start(label(app.name, "fos-text", "fos-strong", ellipsize=True), False, False, 0)
        subtitle = app.summary or app.package
        texts.pack_start(label(subtitle, "fos-small", "fos-muted", ellipsize=True), False, False, 0)
        inner.pack_start(texts, True, True, 0)
        installed = self.catalog.package_installed(app.package)
        badge = label("Installed" if installed else app.package, "fos-small", "fos-muted")
        inner.pack_end(badge, False, False, 0)
        widget.add(inner)
        widget.connect("clicked", lambda _b, a=app: self._select(a))
        return widget

    def _select(self, app: StoreAppInfo) -> None:
        self._selected = app
        self._highlight_selected_rows()
        self._render_detail()

    def _highlight_selected_rows(self) -> None:
        selected_pkg = self._selected.package if self._selected else ""
        for child in self.list_box.get_children():
            if not isinstance(child, Gtk.Box):
                continue
            for row in child.get_children():
                if not isinstance(row, Gtk.Button):
                    continue
                pkg = getattr(row, "store_package", None)
                if pkg is None:
                    continue
                set_class(row, "secondary", pkg == selected_pkg)
                set_class(row, "ghost", pkg != selected_pkg)

    def _render_detail(self) -> None:
        clear(self.detail)
        app = self._selected
        if app is None:
            self.detail.pack_start(
                label("Select an app to see details.", "fos-small", "fos-muted"),
                False,
                False,
                0,
            )
            self.detail.show_all()
            return

        header = Gtk.Box(spacing=12)
        header.pack_start(icon(app.icon_name, 48), False, False, 0)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        titles.pack_start(label(app.name, "fos-title", ellipsize=True), False, False, 0)
        titles.pack_start(label(app.package, "fos-small", "fos-muted", ellipsize=True), False, False, 0)
        header.pack_start(titles, True, True, 0)
        self.detail.pack_start(header, False, False, 0)

        if app.summary:
            self.detail.pack_start(label(app.summary, "fos-text"), False, False, 0)

        installed = self.catalog.package_installed(app.package)
        version, size = appmod.package_details(app.package) if installed else ("", "")
        meta_bits = []
        if version:
            meta_bits.append(f"Version {version}")
        if size:
            meta_bits.append(size)
        if app.categories:
            meta_bits.append(", ".join(app.categories[:4]))
        if meta_bits:
            self.detail.pack_start(label(" · ".join(meta_bits), "fos-small", "fos-muted"), False, False, 0)

        if app.description:
            desc = label(app.description, "fos-small")
            desc.set_line_wrap(True)
            desc.set_xalign(0.0)
            desc.set_max_width_chars(42)
            self.detail.pack_start(desc, False, False, 0)

        actions = Gtk.Box(spacing=8)
        if installed:
            open_btn = button("Open", variant="default")
            open_btn.connect("clicked", lambda _b, a=app: self._open_app(a))
            actions.pack_start(open_btn, False, False, 0)
            if self.catalog.package_can_uninstall(app.package):
                remove_btn = button("Uninstall", variant="outline")
                add_classes(remove_btn, "destructive")
                remove_btn.connect("clicked", lambda _b, a=app: self._uninstall(a))
                actions.pack_start(remove_btn, False, False, 0)
            else:
                actions.pack_start(label("Required by FosOS", "fos-small", "fos-muted"), False, False, 0)
        else:
            install_btn = button("Install", variant="default")
            install_btn.connect("clicked", lambda _b, a=app: self._install(a))
            actions.pack_start(install_btn, False, False, 0)
        self.detail.pack_start(actions, False, False, 0)
        self.detail.show_all()

    def _open_app(self, app: StoreAppInfo) -> None:
        if app.desktop_id:
            desktop = appmod.load_app(app.desktop_id)
            if desktop and desktop.launch():
                self._set_status(f"Opened {app.name}.")
                return
        # Fall back: any desktop app owning this package name in its id/exec.
        for candidate in appmod.all_apps():
            path = appmod.desktop_file(candidate)
            if path is None:
                continue
            owner = appmod.owning_package(path)
            if owner == app.package and candidate.launch():
                self._set_status(f"Opened {app.name}.")
                return
        self._set_status(f"Could not open {app.name}.")

    def _install(self, app: StoreAppInfo) -> None:
        if self._busy:
            return
        if not fos_confirm(
            self,
            f"Install {app.name}?",
            f"Package “{app.package}” will be installed from APT.\n\n"
            "Administrator permission is required.",
            ok="Install",
        ):
            return
        self._run_apt(
            ["install", "--yes", "--", app.package],
            title=f"Installing {app.name}…",
            success=f"{app.name} is installed.",
            failure=f"{app.name} could not be installed.",
        )

    def _uninstall(self, app: StoreAppInfo) -> None:
        if self._busy:
            return
        if not self.catalog.package_can_uninstall(app.package):
            fos_alert(self, "Cannot uninstall", f"{app.name} is required by FosOS.")
            return
        if not fos_confirm(
            self,
            f"Uninstall {app.name}?",
            f"This removes the package “{app.package}”.\n\nAdministrator permission is required.",
            ok="Uninstall",
            destructive=True,
        ):
            return
        def after_remove() -> None:
            self._unpin_package(app)
            self._render_list()
            self._render_detail()

        self._run_apt(
            ["remove", "--yes", "--", app.package],
            title=f"Uninstalling {app.name}…",
            success=f"{app.name} was removed.",
            failure=f"{app.name} could not be uninstalled.",
            after_success=after_remove,
        )

    def _unpin_package(self, app: StoreAppInfo) -> None:
        if not app.desktop_id:
            return
        try:
            pins = appmod.Pinned()
            if pins.contains(app.desktop_id):
                pins.unpin(app.desktop_id)
        except OSError:
            pass

    def _refresh_catalog(self) -> None:
        if self._busy:
            return
        if not fos_confirm(
            self,
            "Refresh catalog?",
            "Downloads the latest package lists and app metadata (apt update).\n\n"
            "Administrator permission is required.",
            ok="Update",
        ):
            return

        def after() -> None:
            self.catalog.load()
            count = len(self.catalog.all_apps())
            self._set_status(f"Catalog refreshed · {count} apps.")
            self._render_list()
            self._render_detail()

        self._run_apt(
            ["update"],
            title="Refreshing catalog…",
            success="Package lists updated.",
            failure="Could not refresh the catalog.",
            after_success=after,
            allow_empty_packages=True,
        )

    def _run_apt(
        self,
        apt_args: list[str],
        *,
        title: str,
        success: str,
        failure: str,
        after_success=None,
        allow_empty_packages: bool = False,
    ) -> None:
        if self._busy:
            return
        if not allow_empty_packages:
            # Final package token must look like a package name.
            pkg = apt_args[-1] if apt_args else ""
            if not _PKG_RE.match(pkg):
                fos_alert(self, "Invalid package", f"Refusing to run apt for “{pkg}”.")
                return

        self._busy = True
        self._set_status(title)
        progress = FosDialog(self, title=title)
        progress.add_body_text("Approve the password prompt if asked, then wait.")
        progress.footer.set_no_show_all(True)
        progress.footer.hide()
        progress.show_all()

        argv = ["pkexec", "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", *apt_args]
        try:
            proc = Gio.Subprocess.new(
                argv,
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE,
            )
        except GLib.Error as error:
            progress.destroy()
            self._busy = False
            fos_alert(self, "Could not start", error.message)
            self._set_status("Action did not start.")
            return

        def finished(process, result) -> None:
            try:
                _ok, stdout, _stderr = process.communicate_utf8_finish(result)
            except GLib.Error as error:
                stdout = error.message
            progress.destroy()
            self._busy = False
            output = (stdout or "").strip()
            if len(output) > 1200:
                output = "…\n" + output[-1200:]
            if process.get_successful():
                body = success
                if output and apt_args[:1] != ["update"]:
                    body = f"{body}\n\n{output}"
                fos_alert(self, "Store", body)
                self._set_status(success)
                # Install/remove change dpkg status; refresh once before redraw.
                if apt_args[:1] != ["update"]:
                    self.catalog.refresh_installed()
                if after_success is not None:
                    after_success()
                else:
                    self._render_list()
                    self._render_detail()
            else:
                body = failure
                if output:
                    body = f"{body}\n\n{output}"
                fos_alert(self, "Store", body)
                self._set_status(failure)

        proc.communicate_utf8_async(None, None, finished)


class StoreApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window: StoreWindow | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_prgname("fosos-store")
        GLib.set_application_name("Store")
        load_css()

    def do_activate(self) -> None:
        if self.window is None:
            self.window = StoreWindow(self)
        self.window.present()


def main() -> int:
    return StoreApp().run(sys.argv)
