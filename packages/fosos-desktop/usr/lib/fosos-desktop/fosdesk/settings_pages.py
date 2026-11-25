"""Built-in settings panels that replace xfce4-* dialogs."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk

from .ui import add_classes, button, label

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "fosos-desktop"
MIMEAPPS = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "mimeapps.list"

COMMON_LAYOUTS = [
    ("us", "English (US)"),
    ("gb", "English (UK)"),
    ("de", "German"),
    ("fr", "French"),
    ("es", "Spanish"),
    ("it", "Italian"),
    ("pl", "Polish"),
    ("pt", "Portuguese"),
    ("nl", "Dutch"),
    ("se", "Swedish"),
    ("no", "Norwegian"),
    ("dk", "Danish"),
    ("fi", "Finnish"),
    ("cz", "Czech"),
    ("sk", "Slovak"),
    ("hu", "Hungarian"),
    ("ro", "Romanian"),
    ("tr", "Turkish"),
    ("ru", "Russian"),
    ("ua", "Ukrainian"),
    ("gr", "Greek"),
    ("il", "Hebrew"),
    ("ara", "Arabic"),
    ("jp", "Japanese"),
    ("kr", "Korean"),
    ("cn", "Chinese"),
]

DEFAULT_TYPES = [
    ("Web browser", "x-scheme-handler/http"),
    ("File manager", "inode/directory"),
    ("Terminal", "application/x-terminal"),
    ("Text editor", "text/plain"),
    ("PDF", "application/pdf"),
    ("Archives", "application/zip"),
    ("Images", "image/jpeg"),
    ("Mail", "x-scheme-handler/mailto"),
]

# Extra MIME types set alongside the primary default above.
DEFAULT_MIME_ALIASES = {
    "x-scheme-handler/http": ("x-scheme-handler/https",),
    "application/zip": (
        "application/x-tar",
        "application/gzip",
        "application/x-compressed-tar",
        "application/x-7z-compressed",
        "application/x-rar-compressed",
        "application/vnd.rar",
    ),
    "image/jpeg": ("image/png", "image/webp", "image/gif", "image/bmp"),
}


def load_kv(name: str, defaults: dict[str, str] | None = None) -> dict[str, str]:
    values = dict(defaults or {})
    path = CONFIG / name
    if not path.is_file():
        return values
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    except OSError:
        pass
    return values


def save_kv(name: str, values: dict[str, str]) -> None:
    CONFIG.mkdir(parents=True, exist_ok=True)
    (CONFIG / name).write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")


def truthy(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


def run(argv: list[str], timeout: float = 3.0) -> str | None:
    if shutil.which(argv[0]) is None:
        return None
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def current_layout() -> str:
    output = run(["setxkbmap", "-query"]) or ""
    for line in output.splitlines():
        if line.startswith("layout:"):
            return line.split(":", 1)[1].strip().split(",")[0]
    return "us"


def apply_layout(layout: str) -> bool:
    return subprocess.run(["setxkbmap", layout], check=False).returncode == 0


def layout_display_code(code: str | None = None) -> str:
    """Short taskbar label for a layout (US, PL, ARA, …)."""
    raw = (code if code is not None else current_layout()) or "us"
    return raw.strip().split(",")[0].upper()[:3] or "US"


def panel_layout_choices() -> list[tuple[str, str]]:
    """Layouts offered from the taskbar selector (saved + a few commons)."""
    current = current_layout()
    prefs = load_kv("keyboard", {})
    codes: list[str] = []
    listed = prefs.get("layouts", "")
    if listed.strip():
        codes = [part.strip() for part in listed.split(",") if part.strip()]
    saved = prefs.get("layout", "").strip()
    if saved and saved not in codes:
        codes.insert(0, saved)
    if current and current not in codes:
        codes.insert(0, current)
    for code, _name in COMMON_LAYOUTS[:8]:
        if code not in codes:
            codes.append(code)
    names = dict(COMMON_LAYOUTS)
    return [(code, names.get(code, code)) for code in codes]


def persist_layout(layout: str) -> bool:
    """Apply a layout and remember it in ~/.config/fosos-desktop/keyboard."""
    if not apply_layout(layout):
        return False
    prefs = load_kv("keyboard", {"layout": "us", "delay": "600", "rate": "25"})
    prefs["layout"] = layout
    listed = [part.strip() for part in prefs.get("layouts", "").split(",") if part.strip()]
    if layout not in listed:
        listed.insert(0, layout)
        prefs["layouts"] = ",".join(listed)
    save_kv("keyboard", prefs)
    return True


def current_repeat() -> tuple[int, int]:
    output = run(["xset", "q"]) or ""
    match = re.search(r"repeat delay:\s*(\d+)\s*repeat rate:\s*(\d+)", output)
    if match:
        return int(match.group(1)), int(match.group(2))
    return 600, 25


def apply_repeat(delay_ms: int, rate: int) -> None:
    subprocess.run(["xset", "r", "rate", str(delay_ms), str(rate)], check=False)


def current_accel() -> tuple[int, int]:
    output = run(["xset", "q"]) or ""
    match = re.search(r"acceleration:\s*([0-9.]+)\s*threshold:\s*(\d+)", output)
    if match:
        numer = max(1, int(round(float(match.group(1)) * 10)))
        return numer, int(match.group(2))
    return 20, 10


def apply_accel(numer: int, denom: int, threshold: int) -> None:
    subprocess.run(["xset", "m", f"{numer}/{denom}", str(threshold)], check=False)


_TAPPING_PROP = "libinput Tapping Enabled"
_NATURAL_PROP = "libinput Natural Scrolling Enabled"


def _pointer_device_ids() -> list[str]:
    output = run(["xinput", "list"]) or ""
    return re.findall(r"id=(\d+)\s+\[slave\s+pointer", output)


def _libinput_prop_state(prop: str) -> bool | None:
    for device_id in _pointer_device_ids():
        props = run(["xinput", "list-props", device_id]) or ""
        match = re.search(rf"{re.escape(prop)}\s*\(\d+\):\s*(\d+)", props)
        if match:
            return match.group(1) == "1"
    return None


def _apply_libinput_prop(prop: str, enabled: bool) -> bool:
    value = "1" if enabled else "0"
    applied = False
    for device_id in _pointer_device_ids():
        props = run(["xinput", "list-props", device_id]) or ""
        if prop not in props:
            continue
        result = subprocess.run(
            ["xinput", "set-prop", device_id, prop, value],
            check=False,
        )
        if result.returncode == 0:
            applied = True
    return applied


def current_tapping() -> bool | None:
    """Return live tap-to-click state, or None if no libinput touchpad."""
    return _libinput_prop_state(_TAPPING_PROP)


def apply_tapping(enabled: bool) -> bool:
    return _apply_libinput_prop(_TAPPING_PROP, enabled)


def current_natural_scrolling() -> bool | None:
    return _libinput_prop_state(_NATURAL_PROP)


def apply_natural_scrolling(enabled: bool) -> bool:
    return _apply_libinput_prop(_NATURAL_PROP, enabled)


def idle_timeout_seconds() -> int:
    output = run(["xset", "q"]) or ""
    match = re.search(r"timeout:\s*(\d+)", output)
    if match:
        return int(match.group(1))
    return 300


def apply_idle_timeout(seconds: int) -> None:
    if seconds <= 0:
        subprocess.run(["xset", "s", "off"], check=False)
    else:
        subprocess.run(["xset", "s", str(seconds), "5"], check=False)


def apps_for_type(mime: str) -> list[Gio.AppInfo]:
    try:
        return list(Gio.AppInfo.get_all_for_type(mime))
    except GLib.Error:
        return []


def default_for_type(mime: str) -> Gio.AppInfo | None:
    return Gio.AppInfo.get_default_for_type(mime, False)


def set_default_for_type(app: Gio.AppInfo, mime: str) -> bool:
    try:
        return bool(app.set_as_default_for_type(mime))
    except GLib.Error:
        return False


def pack_header(title: str, subtitle: str) -> Gtk.Box:
    """Kept for call-site compatibility; the Settings toolbar already shows title/subtitle."""
    del title, subtitle
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    box.set_no_show_all(True)
    box.hide()
    return box


def build_keyboard(status_cb) -> Gtk.Box:
    from .settings_helpers import settings_row, settings_section

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(pack_header("Keyboard", "Layouts and key repeat for this session."), False, False, 0)

    prefs = load_kv("keyboard", {"layout": "us", "delay": "600", "rate": "25", "layouts": ""})
    current = current_layout()
    listed = [part.strip() for part in prefs.get("layouts", "").split(",") if part.strip()]
    if prefs.get("layout") and prefs["layout"] not in listed:
        listed.insert(0, prefs["layout"])
    if current and current not in listed:
        listed.insert(0, current)
    if not listed:
        listed = ["us"]
    names = dict(COMMON_LAYOUTS)

    layout_store = Gtk.ListStore(str, str)
    for code in listed:
        layout_store.append([code, f"{names.get(code, code)} ({code})"])
    layout_tree = Gtk.TreeView(model=layout_store)
    layout_tree.append_column(Gtk.TreeViewColumn("Installed layouts", Gtk.CellRendererText(), text=1))
    layout_tree.set_headers_visible(False)
    layout_tree.set_size_request(-1, 120)
    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.add(layout_tree)

    combo = Gtk.ComboBoxText()
    seen: set[str] = set()
    for code, name in COMMON_LAYOUTS:
        combo.append(code, f"{name} ({code})")
        seen.add(code)
    for code in listed:
        if code not in seen:
            combo.append(code, code)
            seen.add(code)
    combo.set_active_id(current if current in seen else listed[0])

    def refresh_store() -> None:
        layout_store.clear()
        for code in listed:
            layout_store.append([code, f"{names.get(code, code)} ({code})"])

    def add_layout(_button=None) -> None:
        code = combo.get_active_id()
        if not code:
            return
        if code in listed:
            status_cb(f"{code} is already in the list.")
            return
        listed.append(code)
        refresh_store()
        status_cb(f"Added {names.get(code, code)}.")

    def remove_layout(_button=None) -> None:
        model, row = layout_tree.get_selection().get_selected()
        if row is None:
            status_cb("Select a layout to remove.")
            return
        if len(listed) <= 1:
            status_cb("Keep at least one layout.")
            return
        code = model[row][0]
        listed.remove(code)
        refresh_store()
        if combo.get_active_id() == code:
            combo.set_active_id(listed[0])
        status_cb(f"Removed {code}.")

    add_btn = button("Add", variant="outline", size="sm")
    add_btn.connect("clicked", add_layout)
    remove_btn = button("Remove", variant="outline", size="sm")
    remove_btn.connect("clicked", remove_layout)
    layout_actions = Gtk.Box(spacing=8)
    layout_actions.pack_start(combo, True, True, 0)
    layout_actions.pack_start(add_btn, False, False, 0)
    layout_actions.pack_start(remove_btn, False, False, 0)

    delay, rate = current_repeat()
    delay_scale = add_classes(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 100, 1000, 10), "fos-scale")
    delay_scale.set_value(delay)
    delay_scale.set_draw_value(True)
    delay_scale.set_size_request(160, -1)
    rate_scale = add_classes(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1), "fos-scale")
    rate_scale.set_value(rate)
    rate_scale.set_draw_value(True)
    rate_scale.set_size_request(160, -1)

    def apply(_button=None) -> None:
        code = combo.get_active_id() or listed[0]
        if code not in listed:
            listed.insert(0, code)
        apply_repeat(int(delay_scale.get_value()), int(rate_scale.get_value()))
        values = {
            "layout": code,
            "delay": str(int(delay_scale.get_value())),
            "rate": str(int(rate_scale.get_value())),
            "layouts": ",".join(listed),
        }
        save_kv("keyboard", values)
        apply_layout(code)
        _request_shell_reload()
        status_cb("Keyboard settings applied for this session.")

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(
        settings_section(
            "Layouts",
            settings_row("Primary and extras", "Taskbar layout picker uses this list", trailing=None),
        ),
        False,
        False,
        0,
    )
    root.pack_start(scroller, False, False, 0)
    root.pack_start(layout_actions, False, False, 0)
    root.pack_start(
        settings_section(
            "Key repeat",
            settings_row("Repeat delay", "Milliseconds before repeat starts", trailing=delay_scale),
            settings_row("Repeat rate", "Characters per second", trailing=rate_scale),
            settings_row("Save", "Apply layout and repeat", trailing=apply_btn),
        ),
        False,
        False,
        0,
    )
    tip = label(
        "Change desktop shortcuts under Input → Keyboard shortcuts.",
        "fos-small",
        "fos-muted",
    )
    tip.set_line_wrap(True)
    root.pack_start(tip, False, False, 0)
    return root


def build_region(status_cb) -> Gtk.Box:
    from . import apps as appmod
    from .region import (
        apply_locale,
        current_locale,
        format_date_full,
        format_date_short,
        format_number,
        format_time,
        locale_choices,
        write_user_locale_conf,
    )

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header(
            "Region",
            "Formats for the calendar, clock, dates and numbers. Uses locales already "
            "generated on this system (sudo dpkg-reconfigure locales to add more).",
        ),
        False,
        False,
        0,
    )

    prefs = load_kv("region", {})
    selected = prefs.get("locale", "").strip() or current_locale()
    choices = locale_choices()
    codes = [code for code, _label in choices]
    if selected not in codes:
        choices.insert(0, (selected, selected))
        codes.insert(0, selected)

    row = Gtk.Box(spacing=12)
    row.pack_start(label("Regional format", "fos-text", "fos-strong"), False, False, 0)
    combo = Gtk.ComboBoxText()
    for code, text in choices:
        combo.append(code, text)
    combo.set_active_id(selected)
    combo.set_hexpand(True)
    row.pack_start(combo, True, True, 0)
    root.pack_start(row, False, False, 0)

    preview = label("", "fos-text", "fos-muted")
    preview.set_line_wrap(True)
    root.pack_start(preview, False, False, 0)

    def refresh_preview(_combo=None) -> None:
        code = combo.get_active_id() or selected
        # Preview without permanently switching until Apply.
        previous = current_locale()
        if apply_locale(code):
            preview.set_text(
                f"Preview: {format_time()} · {format_date_short()} · {format_date_full()} · "
                f"1 234,56 → {format_number(1234.56)}"
            )
            apply_locale(previous)
        else:
            preview.set_text(f"Locale {code} is not available on this system.")

    combo.connect("changed", refresh_preview)
    refresh_preview()

    def apply(_button=None) -> None:
        code = combo.get_active_id()
        if not code:
            status_cb("Choose a regional format.")
            return
        if not apply_locale(code):
            status_cb(f"Could not apply {code}. Generate it with: sudo dpkg-reconfigure locales")
            return
        save_kv("region", {"locale": code})
        write_user_locale_conf(code)
        appmod.spawn(["fosos-shell", "--reload-ui"])
        refresh_preview()
        status_cb(f"Region set to {code}. Clock and calendar updated.")

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)
    tip = label(
        "New apps pick up the format after you sign out and back in.",
        "fos-small",
        "fos-muted",
    )
    tip.set_line_wrap(True)
    root.pack_start(tip, False, False, 0)
    return root


def build_mouse(status_cb) -> Gtk.Box:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("Mouse and touchpad", "Pointer speed and tap-to-click for this session."),
        False,
        False,
        0,
    )
    prefs = load_kv(
        "mouse",
        {"accel": "2.0", "threshold": "10", "tapping": "1", "natural": "0"},
    )
    numer, threshold = current_accel()
    accel = numer / 10.0

    row = Gtk.Box(spacing=12)
    row.pack_start(label("Acceleration", "fos-text"), False, False, 0)
    scale = add_classes(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.5, 5.0, 0.1), "fos-scale")
    scale.set_value(accel)
    scale.set_hexpand(True)
    scale.set_draw_value(True)
    row.pack_start(scale, True, True, 0)
    root.pack_start(row, False, False, 0)

    thr_row = Gtk.Box(spacing=12)
    thr_row.pack_start(label("Threshold", "fos-text"), False, False, 0)
    thr = add_classes(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 20, 1), "fos-scale")
    thr.set_value(threshold)
    thr.set_hexpand(True)
    thr.set_draw_value(True)
    thr_row.pack_start(thr, True, True, 0)
    root.pack_start(thr_row, False, False, 0)

    live_tap = current_tapping()
    tapping = Gtk.CheckButton(label="Tap to click (touchpad)")
    if live_tap is None:
        tapping.set_active(truthy(prefs.get("tapping"), True))
        tapping.set_sensitive(False)
        note = label(
            "No libinput touchpad detected in this session.",
            "fos-small",
            "fos-muted",
        )
        note.set_line_wrap(True)
        root.pack_start(tapping, False, False, 0)
        root.pack_start(note, False, False, 0)
    else:
        tapping.set_active(live_tap)
        root.pack_start(tapping, False, False, 0)

    live_natural = current_natural_scrolling()
    natural = Gtk.CheckButton(label="Natural scrolling")
    if live_natural is None:
        natural.set_active(truthy(prefs.get("natural"), False))
        natural.set_sensitive(False)
    else:
        natural.set_active(live_natural)
    root.pack_start(natural, False, False, 0)

    def apply(_button=None) -> None:
        value = scale.get_value()
        numer_v = max(1, int(round(value * 10)))
        thr_v = int(thr.get_value())
        apply_accel(numer_v, 10, thr_v)
        tap_on = tapping.get_active()
        if tapping.get_sensitive():
            apply_tapping(tap_on)
        natural_on = natural.get_active()
        if natural.get_sensitive():
            apply_natural_scrolling(natural_on)
        save_kv(
            "mouse",
            {
                "accel": str(value),
                "threshold": str(thr_v),
                "tapping": "1" if tap_on else "0",
                "natural": "1" if natural_on else "0",
            },
        )
        status_cb("Mouse and touchpad settings applied for this session.")

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)
    return root


def build_defaults(status_cb) -> Gtk.Box:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("Default apps", "Choose which app opens common file types and links."),
        False,
        False,
        0,
    )
    combos: list[tuple[str, Gtk.ComboBoxText, list[Gio.AppInfo]]] = []

    for title, mime in DEFAULT_TYPES:
        row = Gtk.Box(spacing=12)
        row.pack_start(label(title, "fos-text", "fos-strong"), False, False, 0)
        combo = Gtk.ComboBoxText()
        apps = apps_for_type(mime)
        if mime == "application/x-terminal":
            for app_id in ("fosos-terminal.desktop",):
                info = Gio.DesktopAppInfo.new(app_id)
                if info is not None and all(a.get_id() != info.get_id() for a in apps):
                    apps.insert(0, info)
        default = default_for_type(mime)
        active = 0
        for index, app in enumerate(apps):
            combo.append_text(app.get_display_name() or app.get_id() or "App")
            if default is not None and app.get_id() == default.get_id():
                active = index
        if not apps:
            combo.append_text("No apps found")
            combo.set_sensitive(False)
        else:
            combo.set_active(active)
        combo.set_hexpand(True)
        row.pack_start(combo, True, True, 0)
        root.pack_start(row, False, False, 0)
        combos.append((mime, combo, apps))

    def apply(_button=None) -> None:
        changed = 0
        for mime, combo, apps in combos:
            if not apps or not combo.get_sensitive():
                continue
            index = combo.get_active()
            if index < 0 or index >= len(apps):
                continue
            if set_default_for_type(apps[index], mime):
                changed += 1
            for alias in DEFAULT_MIME_ALIASES.get(mime, ()):
                set_default_for_type(apps[index], alias)
        status_cb(f"Updated {changed} default app{'s' if changed != 1 else ''}.")

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)
    note = label(
        f"Choices are stored for your account ({MIMEAPPS}). "
        "Downloaded .deb packages open with Install Package.",
        "fos-small",
        "fos-muted",
    )
    note.set_line_wrap(True)
    root.pack_start(note, False, False, 0)
    return root


def _request_shell_reload() -> None:
    from . import apps as appmod

    appmod.spawn(["fosos-shell", "--reload-ui"])


def build_wallpaper(status_cb) -> Gtk.Box:
    from .desktop import load_desktop_prefs, save_desktop_prefs
    from .ui import fos_file_chooser
    from .wallpaper import THEMES

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header(
            "Wallpaper",
            "Drawn themes or a picture. Login and lock screens stay on Dawn Aperture.",
        ),
        False,
        False,
        0,
    )
    prefs = load_desktop_prefs()
    current = prefs.get("wallpaper", "dawn")
    image_path = prefs.get("wallpaper_image", "")
    use_image = current == "image" and bool(image_path)
    group = None
    radios: dict[str, Gtk.RadioButton] = {}
    for theme_id, title in THEMES:
        radio = Gtk.RadioButton.new_with_label_from_widget(group, title)
        if group is None:
            group = radio
        if theme_id == current and not use_image:
            radio.set_active(True)
        radios[theme_id] = radio
        root.pack_start(radio, False, False, 0)

    image_radio = Gtk.RadioButton.new_with_label_from_widget(group, "Picture…")
    if use_image:
        image_radio.set_active(True)
    root.pack_start(image_radio, False, False, 0)
    image_label = label(image_path or "No picture selected", "fos-small", "fos-muted")
    image_label.set_line_wrap(True)
    root.pack_start(image_label, False, False, 0)
    chosen_image = {"path": image_path}

    def pick_image(_button=None) -> None:
        from .apps import user_dir
        from .filechooser import ChooserFilter

        pictures = user_dir(GLib.UserDirectory.DIRECTORY_PICTURES, "Pictures")
        path = fos_file_chooser(
            None,
            title="Choose wallpaper",
            action=Gtk.FileChooserAction.OPEN,
            ok_label="Choose",
            folder=pictures,
            filters=[
                ChooserFilter(
                    "Images",
                    [
                        (0, "*.png"),
                        (0, "*.jpg"),
                        (0, "*.jpeg"),
                        (0, "*.webp"),
                        (0, "*.bmp"),
                    ],
                ),
            ],
        )
        if not path:
            return
        dest_dir = CONFIG / "wallpapers"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / Path(path).name
        try:
            shutil.copy2(path, dest)
        except OSError:
            status_cb("Could not copy the picture.")
            return
        chosen_image["path"] = str(dest)
        image_label.set_text(str(dest))
        image_radio.set_active(True)
        status_cb("Picture ready — press Apply.")

    pick_btn = button("Browse…", variant="outline", size="sm")
    pick_btn.connect("clicked", pick_image)
    root.pack_start(pick_btn, False, False, 0)

    def apply(_button=None) -> None:
        values = load_desktop_prefs()
        if image_radio.get_active():
            if not chosen_image["path"]:
                status_cb("Choose a picture first.")
                return
            values["wallpaper"] = "image"
            values["wallpaper_image"] = chosen_image["path"]
            msg = "Picture wallpaper applied. Desktop refreshes shortly."
        else:
            chosen = "dawn"
            for theme_id, radio in radios.items():
                if radio.get_active():
                    chosen = theme_id
                    break
            values["wallpaper"] = chosen
            msg = f"Wallpaper set to {dict(THEMES).get(chosen, chosen)}. Desktop refreshes shortly."
        save_desktop_prefs(values)
        _request_shell_reload()
        status_cb(msg)

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)
    return root


def build_desktop(status_cb) -> Gtk.Box:
    from . import apps as appmod
    from .desktop import load_desktop_prefs, save_desktop_prefs, save_icon_positions

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("Personalize", "Desktop icons and how they open."),
        False,
        False,
        0,
    )

    prefs = load_desktop_prefs()
    click_mode = prefs.get("click", "double")
    if click_mode not in ("single", "double"):
        click_mode = "double"

    click_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    click_box.pack_start(label("Open desktop icons", "fos-text", "fos-strong"), False, False, 0)
    group = Gtk.RadioButton.new_with_label_from_widget(None, "Double-click")
    single = Gtk.RadioButton.new_with_label_from_widget(group, "Single-click")
    if click_mode == "single":
        single.set_active(True)
    else:
        group.set_active(True)
    click_box.pack_start(group, False, False, 0)
    click_box.pack_start(single, False, False, 0)
    root.pack_start(click_box, False, False, 0)

    def apply(_button=None) -> None:
        values = load_desktop_prefs()
        values["click"] = "single" if single.get_active() else "double"
        save_desktop_prefs(values)
        status_cb("Desktop preferences saved. Changes apply on the next click.")

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)

    def reset_positions(_button=None) -> None:
        save_icon_positions({})
        status_cb("Icon positions reset. Press F5 or Refresh on the desktop to re-stack.")

    reset = button("Reset icon positions", variant="outline")
    reset.connect("clicked", reset_positions)
    root.pack_start(reset, False, False, 0)

    wallpaper = button("Wallpaper…", variant="outline", icon_name="preferences-desktop-wallpaper-symbolic")
    wallpaper.connect("clicked", lambda _b: appmod.spawn(["fosos-settings", "--builtin", "wallpaper"]))
    root.pack_start(wallpaper, False, False, 0)

    def open_display(_button=None) -> None:
        if appmod.spawn(["arandr"]):
            status_cb("Opened Display settings.")
        else:
            status_cb("Display settings are not available.")

    display = button("Open Display settings", variant="outline", icon_name="video-display-symbolic")
    display.connect("clicked", open_display)
    root.pack_start(display, False, False, 0)
    return root


def build_taskbar(status_cb) -> Gtk.Box:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("Taskbar", "What the FosOS panel shows on the primary display."),
        False,
        False,
        0,
    )
    prefs = load_kv(
        "taskbar",
        {
            "task_view": "1",
            "clock_date": "1",
            "bell": "1",
            "search": "1",
            "align": "left",
            "auto_hide": "0",
        },
    )

    task_view = Gtk.CheckButton(label="Show Task View button")
    task_view.set_active(truthy(prefs.get("task_view"), True))
    root.pack_start(task_view, False, False, 0)

    search = Gtk.CheckButton(label="Show Search button")
    search.set_active(truthy(prefs.get("search"), True))
    root.pack_start(search, False, False, 0)

    clock_date = Gtk.CheckButton(label="Show date under the clock")
    clock_date.set_active(truthy(prefs.get("clock_date"), True))
    root.pack_start(clock_date, False, False, 0)

    bell = Gtk.CheckButton(label="Show notification bell")
    bell.set_active(truthy(prefs.get("bell"), True))
    root.pack_start(bell, False, False, 0)

    auto_hide = Gtk.CheckButton(label="Automatically hide the taskbar")
    auto_hide.set_active(truthy(prefs.get("auto_hide"), False))
    root.pack_start(auto_hide, False, False, 0)

    align_row = Gtk.Box(spacing=12)
    align_row.pack_start(label("Taskbar alignment", "fos-text"), False, False, 0)
    align_left = Gtk.RadioButton.new_with_label_from_widget(None, "Left")
    align_center = Gtk.RadioButton.new_with_label_from_widget(align_left, "Center")
    if (prefs.get("align") or "left").strip().lower() == "center":
        align_center.set_active(True)
    else:
        align_left.set_active(True)
    align_row.pack_start(align_left, False, False, 0)
    align_row.pack_start(align_center, False, False, 0)
    root.pack_start(align_row, False, False, 0)

    def apply(_button=None) -> None:
        save_kv(
            "taskbar",
            {
                "task_view": "1" if task_view.get_active() else "0",
                "search": "1" if search.get_active() else "0",
                "clock_date": "1" if clock_date.get_active() else "0",
                "bell": "1" if bell.get_active() else "0",
                "auto_hide": "1" if auto_hide.get_active() else "0",
                "align": "center" if align_center.get_active() else "left",
            },
        )
        _request_shell_reload()
        status_cb("Taskbar preferences saved.")

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)
    tip = label(
        "Pinned apps: right-click for jump list, drag to reorder, Win+1…9 to launch. "
        "Desktops: Ctrl+Win+1–4.",
        "fos-small",
        "fos-muted",
    )
    tip.set_line_wrap(True)
    root.pack_start(tip, False, False, 0)
    return root


def build_notifications(status_cb) -> Gtk.Box:
    from .notifications import muted_app_names

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("Notifications", "Focus assist, toasts, and per-app mutes."),
        False,
        False,
        0,
    )
    prefs = load_kv(
        "notifications",
        {"dnd": "0", "toasts": "1", "timeout": "5000", "muted_apps": ""},
    )

    focus = Gtk.CheckButton(label="Focus assist (hide toast popups)")
    focus.set_active(truthy(prefs.get("dnd"), False))
    root.pack_start(focus, False, False, 0)

    toasts = Gtk.CheckButton(label="Show toast popups for new notifications")
    toasts.set_active(truthy(prefs.get("toasts"), True))
    root.pack_start(toasts, False, False, 0)

    row = Gtk.Box(spacing=12)
    row.pack_start(label("Toast duration", "fos-text"), False, False, 0)
    try:
        timeout_ms = max(1000, int(prefs.get("timeout", "5000")))
    except ValueError:
        timeout_ms = 5000
    scale = add_classes(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 2, 20, 1), "fos-scale")
    scale.set_value(timeout_ms / 1000)
    scale.set_hexpand(True)
    scale.set_draw_value(True)
    scale.connect("format-value", lambda _s, v: f"{int(v)} s")
    row.pack_start(scale, True, True, 0)
    root.pack_start(row, False, False, 0)

    root.pack_start(label("Apps", "fos-label"), False, False, 0)
    apps_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    muted = muted_app_names(prefs)
    app_names: set[str] = set(muted)
    recent_path = CONFIG / "notification-apps"
    if recent_path.is_file():
        try:
            for line in recent_path.read_text(encoding="utf-8").splitlines():
                name = line.strip()
                if name:
                    app_names.add(name)
        except OSError:
            pass

    app_checks: list[tuple[str, Gtk.CheckButton]] = []
    if not app_names:
        apps_box.pack_start(
            label(
                "Apps that send notifications will appear here. You can also mute from Notification Center.",
                "fos-small",
                "fos-muted",
            ),
            False,
            False,
            0,
        )
    else:
        for name in sorted(app_names, key=str.lower):
            check = Gtk.CheckButton(label=f"Mute toasts from {name}")
            check.set_active(any(name.lower() == m.lower() for m in muted))
            apps_box.pack_start(check, False, False, 0)
            app_checks.append((name, check))
    root.pack_start(apps_box, False, False, 0)

    def apply(_button=None) -> None:
        if app_checks:
            muted_list = [name for name, check in app_checks if check.get_active()]
            muted_value = "|".join(sorted(muted_list, key=str.lower))
        else:
            muted_value = prefs.get("muted_apps", "")
        save_kv(
            "notifications",
            {
                "dnd": "1" if focus.get_active() else "0",
                "toasts": "1" if toasts.get_active() else "0",
                "timeout": str(int(scale.get_value() * 1000)),
                "muted_apps": muted_value,
            },
        )
        _request_shell_reload()
        status_cb("Notification preferences saved.")

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)

    tip = label(
        "History still appears in Notification Center (Win+N) while Focus assist is on. "
        "Per-app mute hides that app’s toast popups only.",
        "fos-small",
        "fos-muted",
    )
    tip.set_line_wrap(True)
    root.pack_start(tip, False, False, 0)
    return root


def build_tool_page(title: str, subtitle: str, command: list[str], button_label: str, status_cb) -> Gtk.Box:
    from . import apps as appmod

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(pack_header(title, subtitle), False, False, 0)
    tip = label(
        "FosOS opens the system tool below so you stay in one Settings shell.",
        "fos-small",
        "fos-muted",
    )
    tip.set_line_wrap(True)
    root.pack_start(tip, False, False, 0)

    def open_tool(_button=None) -> None:
        if appmod.spawn(command):
            status_cb(f"Opened {title}.")
        else:
            status_cb(f"{title} is not available on this system.")

    open_btn = button(button_label, variant="default")
    open_btn.connect("clicked", open_tool)
    root.pack_start(open_btn, False, False, 0)
    return root


def build_display(status_cb) -> Gtk.Box:
    from . import apps as appmod
    from .indicators import brightness_available, read_brightness, set_brightness
    from .settings_helpers import (
        list_displays,
        set_display_mode,
        set_display_primary,
        set_display_rotation,
        settings_row,
        settings_section,
    )

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("Display", "Brightness, resolution and orientation for connected monitors."),
        False,
        False,
        0,
    )

    if brightness_available():
        bright_scale = add_classes(
            Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1),
            "fos-scale",
        )
        bright_scale.set_draw_value(True)
        bright_scale.set_size_request(180, -1)
        level = read_brightness()
        if level is not None:
            bright_scale.set_value(level)

        def on_bright(scale: Gtk.Scale) -> None:
            set_brightness(int(scale.get_value()))
            status_cb(f"Brightness {int(scale.get_value())}%")

        bright_scale.connect("value-changed", on_bright)
        root.pack_start(
            settings_section(
                "Brightness & color",
                settings_row(
                    "Brightness",
                    "Built-in display backlight",
                    trailing=bright_scale,
                    icon_name="display-brightness-symbolic",
                ),
            ),
            False,
            False,
            0,
        )

    displays = [d for d in list_displays() if d.connected]
    if not displays:
        root.pack_start(
            label("No connected displays were reported by xrandr.", "fos-text", "fos-muted"),
            False,
            False,
            0,
        )
    for display in displays:
        title = display.name + (" (primary)" if display.primary else "")
        rows: list[Gtk.Widget] = []
        guard = {"ready": False}

        mode_combo = Gtk.ComboBoxText()
        modes = display.modes or ([display.current] if display.current else [])
        for mode in modes:
            mode_combo.append(mode, mode)
        if display.current:
            mode_combo.set_active_id(display.current)
        elif modes:
            mode_combo.set_active(0)

        def on_mode(_combo, name=display.name, combo=mode_combo, g=guard) -> None:
            if not g["ready"]:
                return
            mode = combo.get_active_id()
            if mode and set_display_mode(name, mode):
                status_cb(f"{name} → {mode}")
            else:
                status_cb(f"Could not set resolution on {name}.")

        mode_combo.connect("changed", on_mode)
        rows.append(
            settings_row(
                "Display resolution",
                "Recommended modes for this monitor",
                trailing=mode_combo,
            )
        )

        rot_combo = Gtk.ComboBoxText()
        for code, text in (
            ("normal", "Landscape"),
            ("left", "Portrait (left)"),
            ("right", "Portrait (right)"),
            ("inverted", "Landscape (flipped)"),
        ):
            rot_combo.append(code, text)
        rot_combo.set_active_id(display.rotation if display.rotation in ("normal", "left", "right", "inverted") else "normal")

        def on_rot(_combo, name=display.name, combo=rot_combo, g=guard) -> None:
            if not g["ready"]:
                return
            rot = combo.get_active_id()
            if rot and set_display_rotation(name, rot):
                status_cb(f"{name} orientation updated.")
            else:
                status_cb(f"Could not rotate {name}.")

        rot_combo.connect("changed", on_rot)
        rows.append(settings_row("Display orientation", "Rotate this monitor", trailing=rot_combo))
        guard["ready"] = True

        if not display.primary:
            make_primary = button("Set as main display", variant="outline", size="sm")

            def on_primary(_b, name=display.name) -> None:
                if set_display_primary(name):
                    status_cb(f"{name} is now the main display. Reopen Display to refresh.")
                else:
                    status_cb(f"Could not set {name} as primary.")

            make_primary.connect("clicked", on_primary)
            rows.append(settings_row("Multiple displays", "Use this monitor as the main display", trailing=make_primary))

        root.pack_start(settings_section(title, *rows), False, False, 0)

    primary = next((d for d in displays if d.primary), displays[0] if displays else None)
    others = [d for d in displays if primary and d.name != primary.name]
    if primary and others:
        from .settings_helpers import set_display_beside

        arrange_rows: list[Gtk.Widget] = []
        for other in others:
            box = Gtk.Box(spacing=8)
            left_btn = button("Left of main", variant="outline", size="sm")
            right_btn = button("Right of main", variant="outline", size="sm")

            def on_left(_b, name=other.name, base=primary.name) -> None:
                if set_display_beside(name, base, "left"):
                    status_cb(f"{name} placed left of {base}.")
                else:
                    status_cb(f"Could not move {name}.")

            def on_right(_b, name=other.name, base=primary.name) -> None:
                if set_display_beside(name, base, "right"):
                    status_cb(f"{name} placed right of {base}.")
                else:
                    status_cb(f"Could not move {name}.")

            left_btn.connect("clicked", on_left)
            right_btn.connect("clicked", on_right)
            box.pack_start(left_btn, False, False, 0)
            box.pack_start(right_btn, False, False, 0)
            arrange_rows.append(settings_row(other.name, "Quick arrange relative to the main display", trailing=box))
        root.pack_start(settings_section("Arrange displays", *arrange_rows), False, False, 0)

    advanced = Gtk.Box(spacing=8)
    if shutil.which("arandr"):
        layout_btn = button("Advanced layout…", variant="outline", size="sm")
        layout_btn.connect(
            "clicked",
            lambda _b: status_cb("Opened display layout.")
            if appmod.spawn(["arandr"])
            else status_cb("Display layout tool is not available."),
        )
        advanced.pack_start(layout_btn, False, False, 0)
    tip = label(
        "Quick arrange covers two-monitor left/right. Use Advanced layout for complex setups.",
        "fos-small",
        "fos-muted",
    )
    tip.set_line_wrap(True)
    root.pack_start(advanced, False, False, 0)
    root.pack_start(tip, False, False, 0)
    return root


def build_sound(status_cb) -> Gtk.Box:
    from . import apps as appmod
    from .indicators import read_volume, set_volume, toggle_mute, volume_icon
    from .settings_helpers import list_audio_nodes, set_default_audio, settings_row, settings_section

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("Sound", "Output volume, mute and default devices."),
        False,
        False,
        0,
    )

    vol_box = add_classes(Gtk.Box(spacing=10), "fos-volume-row")
    mute_btn = button(icon_name="audio-volume-high-symbolic", size="icon-sm", tooltip="Mute")
    add_classes(mute_btn, "fos-volume-mute")
    vol_scale = add_classes(
        Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1),
        "fos-scale",
        "fos-volume-scale",
    )
    vol_scale.set_draw_value(False)
    vol_scale.set_size_request(220, -1)
    vol_box.pack_start(mute_btn, False, False, 0)
    vol_box.pack_start(vol_scale, True, True, 0)
    updating = {"on": False}

    def refresh_volume() -> None:
        state = read_volume()
        updating["on"] = True
        if state is None:
            vol_scale.set_sensitive(False)
            mute_btn.set_sensitive(False)
            status_cb("Sound is not available.")
        else:
            level, muted = state
            vol_scale.set_sensitive(True)
            mute_btn.set_sensitive(True)
            vol_scale.set_value(min(level, 100))
            child = mute_btn.get_child()
            if isinstance(child, Gtk.Image):
                child.set_from_icon_name(volume_icon(level, muted), Gtk.IconSize.MENU)
            mute_btn.set_tooltip_text("Unmute" if muted else "Mute")
        updating["on"] = False

    def on_vol(scale: Gtk.Scale) -> None:
        if updating["on"]:
            return
        level = int(scale.get_value())
        if set_volume(level):
            status_cb(f"Volume {level}%")
        else:
            status_cb("Could not change volume.")
        refresh_volume()

    def on_mute(_b) -> None:
        if toggle_mute():
            status_cb("Mute toggled.")
        else:
            status_cb("Could not toggle mute.")
        refresh_volume()

    vol_scale.connect("value-changed", on_vol)
    mute_btn.connect("clicked", on_mute)
    refresh_volume()
    root.pack_start(
        settings_section(
            "Output",
            settings_row("Volume", "Master output level", trailing=vol_box, icon_name="audio-volume-high-symbolic"),
        ),
        False,
        False,
        0,
    )

    sinks = list_audio_nodes("Sinks")
    if sinks:
        sink_combo = Gtk.ComboBoxText()
        for node in sinks:
            sink_combo.append(node.id, node.name)
            if node.default:
                sink_combo.set_active_id(node.id)
        if sink_combo.get_active_id() is None and sinks:
            sink_combo.set_active(0)

        def on_sink(_combo) -> None:
            node_id = sink_combo.get_active_id()
            if node_id and set_default_audio(node_id):
                status_cb("Output device updated.")
                refresh_volume()
            else:
                status_cb("Could not change output device.")

        sink_combo.connect("changed", on_sink)
        root.pack_start(
            settings_section(
                "Choose your output device",
                settings_row("Output device", "Speakers or headphones", trailing=sink_combo),
            ),
            False,
            False,
            0,
        )

    sources = list_audio_nodes("Sources")
    if sources:
        source_combo = Gtk.ComboBoxText()
        for node in sources:
            source_combo.append(node.id, node.name)
            if node.default:
                source_combo.set_active_id(node.id)
        if source_combo.get_active_id() is None and sources:
            source_combo.set_active(0)

        def on_source(_combo) -> None:
            node_id = source_combo.get_active_id()
            if node_id and set_default_audio(node_id):
                status_cb("Input device updated.")
            else:
                status_cb("Could not change input device.")

        source_combo.connect("changed", on_source)
        root.pack_start(
            settings_section(
                "Input",
                settings_row("Input device", "Microphone", trailing=source_combo, icon_name="audio-input-microphone-symbolic"),
            ),
            False,
            False,
            0,
        )

    if shutil.which("pavucontrol"):
        more = button("More sound settings", variant="outline", size="sm")
        more.connect(
            "clicked",
            lambda _b: status_cb("Opened volume control.")
            if appmod.spawn(["pavucontrol"])
            else status_cb("Volume control is not available."),
        )
        root.pack_start(more, False, False, 0)
    return root


def build_network(status_cb) -> Gtk.Box:
    from . import apps as appmod
    from .indicators import WifiPicker
    from .settings_helpers import settings_row, settings_section

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("Network", "Wi-Fi, Ethernet status, and VPN connections."),
        False,
        False,
        0,
    )
    card = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10), "fos-card")
    card.set_border_width(12)
    picker = WifiPicker(
        on_changed=lambda: status_cb("Network status updated."),
        show_switch=True,
    )
    picker.set_dialog_parent(root)
    card.pack_start(picker, False, False, 0)
    root.pack_start(card, False, False, 0)

    eth_lines: list[str] = []
    vpn_rows: list[Gtk.Widget] = []
    nm_out = run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"]) or ""
    for line in nm_out.splitlines():
        parts = line.split(":")
        if len(parts) < 4:
            continue
        device, dtype, state, conn = parts[0], parts[1], parts[2], parts[3]
        if dtype == "ethernet":
            eth_lines.append(f"{device}: {state}" + (f" — {conn}" if conn else ""))
    if eth_lines:
        root.pack_start(
            settings_section(
                "Ethernet",
                settings_row("Wired", "\n".join(eth_lines)),
            ),
            False,
            False,
            0,
        )

    vpn_out = run(["nmcli", "-t", "-f", "NAME,TYPE,ACTIVE", "connection"]) or ""
    for line in vpn_out.splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        name, ctype, active = parts[0], parts[1], parts[2]
        if "vpn" not in ctype.lower() and "wireguard" not in ctype.lower():
            continue
        is_on = active in ("yes", "true", "1")
        toggle = button("Disconnect" if is_on else "Connect", variant="outline", size="sm")

        def on_vpn(_b, vpn_name=name, connected=is_on) -> None:
            action = "down" if connected else "up"
            code = subprocess.run(["nmcli", "connection", action, vpn_name], check=False).returncode
            if code == 0:
                status_cb(f"VPN {vpn_name} {'disconnected' if connected else 'connected'}. Reopen Network to refresh.")
            else:
                status_cb(f"Could not change VPN {vpn_name}.")

        toggle.connect("clicked", on_vpn)
        vpn_rows.append(settings_row(name, ctype, trailing=toggle))
    if vpn_rows:
        root.pack_start(settings_section("VPN", *vpn_rows), False, False, 0)

    def open_advanced(_button=None) -> None:
        if appmod.spawn(["nm-connection-editor"]):
            status_cb("Opened advanced network connections.")
        else:
            status_cb("nm-connection-editor is not available.")

    advanced = button("Advanced connections…", variant="outline", size="sm")
    advanced.connect("clicked", open_advanced)
    root.pack_start(advanced, False, False, 0)
    tip = label(
        "Use Advanced for bridges and editing profiles. Everyday Wi-Fi is above.",
        "fos-small",
        "fos-muted",
    )
    tip.set_line_wrap(True)
    root.pack_start(tip, False, False, 0)
    picker.refresh(rescan=False)

    def soft_rescan() -> bool:
        picker.refresh(rescan=True)
        return False

    GLib.timeout_add(250, soft_rescan)
    status_cb("Network settings.")
    return root


def build_bluetooth(status_cb) -> Gtk.Box:
    from .settings_more import build_bluetooth_full

    return build_bluetooth_full(status_cb)


def reboot_required() -> bool:
    for path in (Path("/run/reboot-required"), Path("/var/run/reboot-required")):
        if path.is_file():
            return True
    return False


def last_update_text() -> str:
    stamps = [
        Path("/var/lib/apt/periodic/update-success-stamp"),
        Path("/var/cache/apt/pkgcache.bin"),
    ]
    latest = 0.0
    for path in stamps:
        try:
            latest = max(latest, path.stat().st_mtime)
        except OSError:
            continue
    if not latest:
        return "Unknown"
    try:
        from datetime import datetime

        return datetime.fromtimestamp(latest).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return "Unknown"


def upgradable_estimate() -> str:
    try:
        result = subprocess.run(
            ["apt", "list", "--upgradable"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "Could not query (try Check for updates)."
    lines = [
        line
        for line in (result.stdout or "").splitlines()
        if "/" in line and not line.startswith("Listing")
    ]
    count = len(lines)
    if count == 0:
        return "No upgrades listed (refresh package lists if this looks stale)."
    return f"{count} package{'s' if count != 1 else ''} listed as upgradable."


def build_updates(status_cb) -> Gtk.Box:
    from . import apps as appmod

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("Updates", "Debian and FosOS packages through fos / APT."),
        False,
        False,
        0,
    )

    card = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), "fos-card", "fos-card-content")
    last_label = label(f"Last package list refresh: {last_update_text()}", "fos-text")
    card.pack_start(last_label, False, False, 0)
    reboot_label = label(
        "A restart is required to finish some updates." if reboot_required() else "No reboot required right now.",
        "fos-text",
        "fos-strong" if reboot_required() else "fos-muted",
    )
    card.pack_start(reboot_label, False, False, 0)
    summary = label(upgradable_estimate(), "fos-small", "fos-muted")
    summary.set_line_wrap(True)
    card.pack_start(summary, False, False, 0)
    root.pack_start(card, False, False, 0)

    def refresh_labels() -> None:
        last_label.set_text(f"Last package list refresh: {last_update_text()}")
        needed = reboot_required()
        reboot_label.set_text(
            "A restart is required to finish some updates." if needed else "No reboot required right now."
        )
        ctx = reboot_label.get_style_context()
        if needed:
            ctx.add_class("fos-strong")
            ctx.remove_class("fos-muted")
        else:
            ctx.add_class("fos-muted")
            ctx.remove_class("fos-strong")
        summary.set_text(upgradable_estimate())

    def check(_button=None) -> None:
        status_cb("Refreshing package lists…")
        script = (
            "fos update; status=$?; echo; "
            "if [ $status -eq 0 ]; then echo 'Package lists refreshed.'; "
            "else echo 'Refresh failed. Check the network.'; fi; "
            "printf 'Press Enter to close. '; read _"
        )
        if appmod.spawn(["fosos-terminal", "-e", "sh", "-c", script]):
            save_kv("updates", {**load_kv("updates"), "last_check": str(int(__import__("time").time()))})
            GLib.timeout_add_seconds(2, lambda: (refresh_labels(), False)[1])
        else:
            status_cb("Terminal is not available.")

    def upgrade(_button=None) -> None:
        script = (
            "fos update && fos upgrade; status=$?; echo; "
            "if [ $status -eq 0 ]; then echo 'Updates are installed.'; "
            "else echo 'Updates did not finish. Check the network and try again.'; fi; "
            "printf 'Press Enter to close. '; read _"
        )
        if appmod.spawn(["fosos-terminal", "-e", "sh", "-c", script]):
            status_cb("Opened update terminal.")
            GLib.timeout_add_seconds(3, lambda: (refresh_labels(), False)[1])
        else:
            status_cb("Terminal is not available.")

    def reboot(_button=None) -> None:
        status_cb("Restarting…")
        subprocess.Popen(["systemctl", "reboot"])

    actions = Gtk.Box(spacing=8)
    check_btn = button("Check for updates", variant="outline")
    check_btn.connect("clicked", check)
    actions.pack_start(check_btn, False, False, 0)
    upgrade_btn = button("Install updates", variant="default")
    upgrade_btn.connect("clicked", upgrade)
    actions.pack_start(upgrade_btn, False, False, 0)
    if reboot_required():
        reboot_btn = button("Restart now", variant="outline")
        reboot_btn.connect("clicked", reboot)
        actions.pack_start(reboot_btn, False, False, 0)
    root.pack_start(actions, False, False, 0)

    tip = label(
        "Install updates runs `fos update && fos upgrade` (no password for sudo users).",
        "fos-small",
        "fos-muted",
    )
    tip.set_line_wrap(True)
    root.pack_start(tip, False, False, 0)
    return root


def storage_rows() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    gib = 1024**3
    try:
        usage = shutil.disk_usage("/")
        rows.append(("/", f"{usage.free / gib:.1f} GiB free of {usage.total / gib:.1f} GiB"))
    except OSError:
        rows.append(("/", "Unknown"))
    home = Path.home()
    try:
        usage = shutil.disk_usage(str(home))
        if str(home) != "/":
            rows.append((str(home), f"{usage.free / gib:.1f} GiB free of {usage.total / gib:.1f} GiB"))
    except OSError:
        pass
    # Extra mounts from /proc/mounts (common user-visible ones).
    seen = {path for path, _ in rows}
    try:
        for line in Path("/proc/mounts").read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            mount, fstype = parts[1], parts[2]
            if fstype not in ("ext4", "xfs", "btrfs", "vfat", "ntfs", "exfat"):
                continue
            if mount in seen or mount.startswith("/snap") or mount.startswith("/boot/efi"):
                continue
            if mount.count("/") > 2 and mount not in ("/home", "/var", "/usr"):
                continue
            try:
                usage = shutil.disk_usage(mount)
            except OSError:
                continue
            rows.append((mount, f"{usage.free / gib:.1f} GiB free of {usage.total / gib:.1f} GiB"))
            seen.add(mount)
            if len(rows) >= 6:
                break
    except OSError:
        pass
    return rows


def build_storage(status_cb) -> Gtk.Box:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(pack_header("Storage", "Free space on mounted disks."), False, False, 0)
    table = add_classes(Gtk.Grid(column_spacing=24, row_spacing=0), "fos-card")
    for index, (mount, text) in enumerate(storage_rows()):
        key_label = label(mount, "fos-text", "fos-muted")
        value_label = label(text, "fos-text", ellipsize=True)
        value_label.set_selectable(True)
        for widget in (key_label, value_label):
            widget.set_margin_top(8)
            widget.set_margin_bottom(8)
        key_label.set_margin_start(12)
        value_label.set_margin_end(12)
        value_label.set_hexpand(True)
        table.attach(key_label, 0, index, 1, 1)
        table.attach(value_label, 1, index, 1, 1)
    root.pack_start(table, False, False, 0)
    status_cb("Storage summary loaded.")
    return root


REMOTE_HOST = Path("/usr/libexec/fosos-remote-host")
REMOTE_PORT = 3389
REMOTE_INFO = Path("/run/fosos/rdp-host-info")


def remote_host_active() -> bool:
    """True when xrdp is listening for Remote Desktop sessions."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "xrdp.service"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and (result.stdout or "").strip() == "active"


def remote_host_installed() -> bool:
    return any(
        Path(path).is_file()
        for path in (
            "/usr/sbin/xrdp",
            "/usr/bin/xrdp",
            "/lib/systemd/system/xrdp.service",
            "/usr/lib/systemd/system/xrdp.service",
            "/usr/libexec/fosos-remote-host",
        )
    )


def remote_host_addresses() -> list[str]:
    addrs: list[str] = []
    try:
        result = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        result = None
    if result is not None and result.returncode == 0:
        for token in (result.stdout or "").split():
            if token and token not in addrs:
                addrs.append(token)
    try:
        host = subprocess.check_output(["hostname", "-f"], text=True, timeout=5).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        host = ""
    if host and host not in addrs:
        addrs.insert(0, host)
    return addrs


def remote_host_info() -> dict[str, str]:
    data: dict[str, str] = {}
    if not REMOTE_INFO.is_file():
        return data
    try:
        for line in REMOTE_INFO.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
    except OSError:
        return {}
    return data


def remote_display_geometry() -> str:
    info = remote_host_info()
    if info.get("geometry"):
        return info["geometry"]
    try:
        result = subprocess.run(
            ["xrandr", "--current"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    for line in (result.stdout or "").splitlines():
        if " connected" not in line:
            continue
        for token in line.split():
            if "x" in token and token[0].isdigit():
                return token.split("+")[0]
    return ""


def set_remote_host_enabled_async(enabled: bool, done_cb) -> None:
    """Toggle xrdp Remote Desktop via pkexec without blocking the GTK main loop.

    A synchronous pkexec + capture_output freezes Settings (mouse still moves).
    """
    if not REMOTE_HOST.is_file():
        done_cb(False, "Remote Desktop host helper is missing.")
        return
    action = "enable" if enabled else "disable"
    argv = ["pkexec", str(REMOTE_HOST), action]
    try:
        # Do not capture stdio: polkit agent dialogs need a live TTY/display path.
        proc = Gio.Subprocess.new(argv, Gio.SubprocessFlags.NONE)
    except GLib.Error as exc:
        done_cb(False, exc.message)
        return

    def finished(process, result) -> None:
        try:
            process.wait_finish(result)
        except GLib.Error as error:
            done_cb(False, error.message)
            return
        if process.get_exit_status() != 0:
            done_cb(False, "Request cancelled or failed.")
            return
        done_cb(True, "enabled" if enabled else "disabled")

    proc.wait_async(None, finished)


def build_remote_desktop(status_cb) -> Gtk.Box:
    from . import apps as appmod

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header(
            "Remote Desktop",
            "Allow remote sign-in to a FosOS Desktop session, or connect out to other PCs.",
        ),
        False,
        False,
        0,
    )

    if not remote_host_installed():
        tip = label(
            "Install xrdp and xorgxrdp to host Remote Desktop. "
            "The FosOS Remote Desktop app still connects out with FreeRDP.",
            "fos-text",
            "fos-muted",
        )
        tip.set_line_wrap(True)
        root.pack_start(tip, False, False, 0)
    else:
        card = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "fos-card", "fos-card-content")
        row = Gtk.Box(spacing=12)
        row.pack_start(label("Enable Remote Desktop", "fos-text", "fos-strong"), True, True, 0)
        switch = add_classes(Gtk.Switch(), "fos-switch")
        switch.set_active(remote_host_active())
        switch.set_valign(Gtk.Align.CENTER)
        row.pack_end(switch, False, False, 0)
        card.pack_start(row, False, False, 0)

        status_line = label("", "fos-text")
        status_line.set_selectable(True)
        status_line.set_line_wrap(True)
        card.pack_start(status_line, False, False, 0)

        how_line = label("", "fos-small", "fos-muted")
        how_line.set_line_wrap(True)
        how_line.set_selectable(True)
        card.pack_start(how_line, False, False, 0)

        help_line = label(
            "Starts a separate FosOS Desktop session for the account you sign in with "
            "(any local user). Works even when nobody is signed in on this PC. "
            "mstsc will ask you to accept the certificate once, then ask for username "
            "and password. Live image: user / live. A FosOS-Remote-Desktop.rdp helper "
            "is written to the Desktop when you enable. Enabling opens TCP 3389 in the "
            "firewall; turn Remote Desktop off when finished.",
            "fos-small",
            "fos-muted",
        )
        help_line.set_line_wrap(True)
        card.pack_start(help_line, False, False, 0)
        root.pack_start(card, False, False, 0)

        toggling = {"busy": False}

        def refresh_status() -> None:
            active = remote_host_active()
            toggling["busy"] = True
            switch.set_active(active)
            toggling["busy"] = False
            if active:
                targets = remote_host_addresses() or ["(no address yet)"]
                primary = targets[0]
                lines = [
                    f"Listening on port {REMOTE_PORT} · separate session (xrdp)",
                    "Sign in as any local FosOS user",
                ]
                for item in targets:
                    lines.append(f"{item}:{REMOTE_PORT}")
                status_line.set_text("\n".join(lines))
                how_line.set_text(
                    f"On Windows: open mstsc → Computer “{primary}:{REMOTE_PORT}” "
                    f"→ accept the certificate → sign in with a local username and password. "
                    f"Or copy Desktop/FosOS-Remote-Desktop.rdp to Windows and open it."
                )
            else:
                status_line.set_text("Remote Desktop is off.")
                how_line.set_text(
                    "Turn on to listen for Windows Remote Desktop (mstsc) on port 3389."
                )

        def on_toggle(widget: Gtk.Switch, _gparam) -> None:
            if toggling["busy"]:
                return
            want = widget.get_active()
            if want == remote_host_active():
                return
            toggling["busy"] = True
            widget.set_sensitive(False)
            status_cb("Authenticating to change Remote Desktop…")

            def done(ok: bool, message: str) -> None:
                toggling["busy"] = False
                widget.set_sensitive(True)
                if not ok:
                    toggling["busy"] = True
                    widget.set_active(not want)
                    toggling["busy"] = False
                    status_cb(message)
                    refresh_status()
                    return
                status_cb(f"Remote Desktop {message}.")

                def refresh_later() -> bool:
                    refresh_status()
                    return False

                # Status / .rdp file appear shortly after the unit starts.
                GLib.timeout_add(600, refresh_later)
                refresh_status()

            set_remote_host_enabled_async(want, done)

        switch.connect("notify::active", on_toggle)
        refresh_status()

        actions = Gtk.Box(spacing=8)
        open_btn = button("Open Remote Desktop", variant="default")
        open_btn.connect(
            "clicked",
            lambda _b: status_cb("Opened Remote Desktop.")
            if appmod.spawn(["fosos-remote"])
            else status_cb("Remote Desktop app is not available."),
        )
        actions.pack_start(open_btn, False, False, 0)
        refresh = button("Refresh status", variant="outline", size="sm")
        refresh.connect(
            "clicked",
            lambda _b: (refresh_status(), status_cb("Status refreshed.")),
        )
        actions.pack_start(refresh, False, False, 0)
        root.pack_start(actions, False, False, 0)
        status_cb("Remote Desktop settings.")
        return root

    tip_actions = Gtk.Box(spacing=8)
    open_btn = button("Open Remote Desktop", variant="default")
    open_btn.connect(
        "clicked",
        lambda _b: status_cb("Opened Remote Desktop.")
        if appmod.spawn(["fosos-remote"])
        else status_cb("Remote Desktop app is not available."),
    )
    tip_actions.pack_start(open_btn, False, False, 0)
    root.pack_start(tip_actions, False, False, 0)
    status_cb("Remote Desktop settings.")
    return root


def build_power(status_cb) -> Gtk.Box:
    from .indicators import (
        battery_present,
        battery_state,
        brightness_available,
        read_brightness,
        set_brightness,
    )
    from .settings_helpers import hibernate_available, settings_row, settings_section

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("Power", "Screen, sleep, battery and power actions."),
        False,
        False,
        0,
    )

    if battery_present():
        batt = battery_state()
        tip = batt[1] if batt else "Battery"
        capacity = f"{batt[2]}%" if batt else "—"
        root.pack_start(
            settings_section(
                "Battery",
                settings_row(
                    "Battery status",
                    tip,
                    trailing=label(capacity, "fos-text", "fos-strong"),
                    icon_name="battery-good-symbolic",
                ),
            ),
            False,
            False,
            0,
        )

    if brightness_available():
        bright_scale = add_classes(
            Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1),
            "fos-scale",
        )
        bright_scale.set_draw_value(True)
        bright_scale.set_size_request(160, -1)
        level = read_brightness()
        if level is not None:
            bright_scale.set_value(level)

        def on_bright(scale: Gtk.Scale) -> None:
            set_brightness(int(scale.get_value()))

        bright_scale.connect("value-changed", on_bright)
        root.pack_start(
            settings_section(
                "Brightness",
                settings_row("Screen brightness", "Also available on the taskbar", trailing=bright_scale),
            ),
            False,
            False,
            0,
        )

    power_prefs = load_kv("power", {"blank": "300", "sleep": "0", "lock": "300", "lid": "suspend"})
    timeout = idle_timeout_seconds()
    blank_combo = Gtk.ComboBoxText()
    blank_choices = [
        (0, "Never"),
        (60, "1 minute"),
        (120, "2 minutes"),
        (300, "5 minutes"),
        (600, "10 minutes"),
        (900, "15 minutes"),
        (1800, "30 minutes"),
    ]
    for value, text in blank_choices:
        blank_combo.append(str(value), text)
    try:
        blank_saved = int(power_prefs.get("blank", str(timeout)))
    except ValueError:
        blank_saved = timeout
    nearest = min(blank_choices, key=lambda item: abs(item[0] - blank_saved))[0]
    blank_combo.set_active_id(str(nearest))

    lock_combo = Gtk.ComboBoxText()
    for value, text in blank_choices:
        lock_combo.append(str(value), text)
    try:
        lock_saved = int(power_prefs.get("lock", "300"))
    except ValueError:
        lock_saved = 300
    lock_nearest = min(blank_choices, key=lambda item: abs(item[0] - lock_saved))[0]
    lock_combo.set_active_id(str(lock_nearest))

    sleep_combo = Gtk.ComboBoxText()
    sleep_choices = [
        (0, "Never"),
        (900, "15 minutes"),
        (1800, "30 minutes"),
        (3600, "1 hour"),
        (7200, "2 hours"),
    ]
    for value, text in sleep_choices:
        sleep_combo.append(str(value), text)
    try:
        sleep_saved = int(power_prefs.get("sleep", "0"))
    except ValueError:
        sleep_saved = 0
    sleep_nearest = min(sleep_choices, key=lambda item: abs(item[0] - sleep_saved))[0]
    sleep_combo.set_active_id(str(sleep_nearest))

    lid_combo = Gtk.ComboBoxText()
    for code, text in (
        ("suspend", "Suspend"),
        ("hibernate", "Hibernate"),
        ("lock", "Lock"),
        ("ignore", "Do nothing"),
        ("poweroff", "Shut down"),
    ):
        lid_combo.append(code, text)
    lid_combo.set_active_id(power_prefs.get("lid", "suspend") if power_prefs.get("lid") in (
        "suspend", "hibernate", "lock", "ignore", "poweroff"
    ) else "suspend")

    def apply_power(_button=None) -> None:
        try:
            blank = int(blank_combo.get_active_id() or "0")
        except ValueError:
            blank = 0
        try:
            lock = int(lock_combo.get_active_id() or "0")
        except ValueError:
            lock = 0
        try:
            sleep = int(sleep_combo.get_active_id() or "0")
        except ValueError:
            sleep = 0
        # Screensaver timeout drives xss-lock; blank uses the same when lock is Never.
        apply_idle_timeout(lock if lock > 0 else blank)
        if sleep <= 0:
            subprocess.run(["xset", "dpms", "0", "0", "0"], check=False)
        else:
            subprocess.run(["xset", "dpms", str(sleep), str(sleep), str(sleep)], check=False)
        lid = lid_combo.get_active_id() or "suspend"
        save_kv(
            "power",
            {
                "blank": str(blank),
                "lock": str(lock),
                "sleep": str(sleep),
                "lid": lid,
            },
        )
        policy = Path("/usr/libexec/fosos-settings-policy")
        if shutil.which("pkexec") and policy.is_file():
            subprocess.Popen(["pkexec", str(policy), "set-lid", lid])
        status_cb("Power settings saved for this session.")

    apply_btn = button("Apply", variant="default", size="sm")
    apply_btn.connect("clicked", apply_power)
    root.pack_start(
        settings_section(
            "Screen, lock and sleep",
            settings_row(
                "Turn off my screen after",
                "Idle blanking preference (paired with lock below)",
                trailing=blank_combo,
            ),
            settings_row(
                "Lock screen after",
                "xss-lock idle timer (Super+L still locks immediately)",
                trailing=lock_combo,
            ),
            settings_row(
                "Make my device sleep after",
                "Display power management (DPMS). Full system sleep uses Suspend.",
                trailing=sleep_combo,
            ),
            settings_row(
                "Lid close",
                "System-wide logind policy (needs authentication)",
                trailing=lid_combo,
            ),
            settings_row("Save power settings", "Apply timers and lid policy", trailing=apply_btn),
        ),
        False,
        False,
        0,
    )

    actions_box = Gtk.Box(spacing=8)
    suspend_btn = button("Suspend", variant="outline", size="sm")
    suspend_btn.connect(
        "clicked",
        lambda _b: (status_cb("Suspending…"), subprocess.Popen(["systemctl", "suspend"])),
    )
    actions_box.pack_start(suspend_btn, False, False, 0)
    if hibernate_available():
        hibernate_btn = button("Hibernate", variant="outline", size="sm")
        hibernate_btn.connect(
            "clicked",
            lambda _b: (status_cb("Hibernating…"), subprocess.Popen(["systemctl", "hibernate"])),
        )
        actions_box.pack_start(hibernate_btn, False, False, 0)
    root.pack_start(
        settings_section(
            "Power actions",
            settings_row("Suspend or hibernate now", "Uses systemd", trailing=actions_box),
        ),
        False,
        False,
        0,
    )
    return root


PAGES = {
    "keyboard": ("Keyboard", build_keyboard),
    "mouse": ("Mouse and touchpad", build_mouse),
    "region": ("Region", build_region),
    "defaults": ("Default apps", build_defaults),
    "power": ("Power", build_power),
    "desktop": ("Personalize", build_desktop),
    "wallpaper": ("Wallpaper", build_wallpaper),
    "taskbar": ("Taskbar", build_taskbar),
    "notifications": ("Notifications", build_notifications),
    "display": ("Display", build_display),
    "sound": ("Sound", build_sound),
    "network": ("Network", build_network),
    "bluetooth": ("Bluetooth", build_bluetooth),
    "remote": ("Remote Desktop", build_remote_desktop),
    "updates": ("Updates", build_updates),
    "storage": ("Storage", build_storage),
}


def register_extra_pages() -> None:
    """Attach pages from settings_more (call after both modules are imported)."""
    from . import settings_more as more

    PAGES.update(
        {
            "datetime": ("Date & time", more.build_datetime),
            "accounts": ("Accounts", more.build_accounts),
            "appearance": ("Appearance", more.build_appearance),
            "shortcuts": ("Keyboard shortcuts", more.build_shortcuts),
            "startup": ("Startup", more.build_startup),
            "apps": ("Installed apps", more.build_installed_apps),
            "accessibility": ("Accessibility", more.build_accessibility),
            "privacy": ("Privacy", more.build_privacy),
            "firewall": ("Firewall", more.build_firewall),
            "ssh": ("SSH", more.build_ssh),
            "multitasking": ("Multitasking", more.build_multitasking),
            "nightlight": ("Night light", more.build_nightlight),
            "bluetooth": ("Bluetooth", more.build_bluetooth_full),
        }
    )


def restore_session_region() -> None:
    """Apply saved regional locale into this process environment."""
    from .region import apply_locale, write_user_locale_conf

    prefs = load_kv("region", {})
    code = prefs.get("locale", "").strip()
    if not code:
        return
    if apply_locale(code):
        write_user_locale_conf(code)


def restore_session_input() -> None:
    """Apply saved keyboard/mouse/power prefs at session start."""
    restore_session_region()
    keyboard = CONFIG / "keyboard"
    if keyboard.is_file():
        values = dict(
            line.split("=", 1) for line in keyboard.read_text(encoding="utf-8").splitlines() if "=" in line
        )
        if "layout" in values:
            apply_layout(values["layout"])
        if "delay" in values and "rate" in values:
            try:
                apply_repeat(int(values["delay"]), int(values["rate"]))
            except ValueError:
                pass
    mouse = CONFIG / "mouse"
    if mouse.is_file():
        values = dict(line.split("=", 1) for line in mouse.read_text(encoding="utf-8").splitlines() if "=" in line)
        try:
            accel = float(values.get("accel", "2.0"))
            thr = int(values.get("threshold", "10"))
            apply_accel(max(1, int(round(accel * 10))), 10, thr)
        except ValueError:
            pass
        apply_tapping(truthy(values.get("tapping"), True))
        apply_natural_scrolling(truthy(values.get("natural"), False))
    else:
        # Match system Xorg default when the user has never opened Mouse settings.
        apply_tapping(True)
    power = CONFIG / "power"
    if power.is_file():
        values = dict(line.split("=", 1) for line in power.read_text(encoding="utf-8").splitlines() if "=" in line)
        try:
            lock = int(values.get("lock", values.get("blank", "300")))
        except ValueError:
            lock = 300
        try:
            blank = int(values.get("blank", "300"))
        except ValueError:
            blank = 300
        # xss-lock watches the X screensaver; prefer explicit lock timeout.
        apply_idle_timeout(lock if lock > 0 else blank)
        try:
            sleep = int(values.get("sleep", "0"))
        except ValueError:
            sleep = 0
        if sleep <= 0:
            subprocess.run(["xset", "dpms", "0", "0", "0"], check=False)
        else:
            subprocess.run(["xset", "dpms", str(sleep), str(sleep), str(sleep)], check=False)
    try:
        from .nightlight import restore_session_night_light

        restore_session_night_light()
    except Exception:
        pass
    try:
        from .settings_more import restore_session_accessibility

        restore_session_accessibility()
    except Exception:
        pass
