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
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.pack_start(label(title, "fos-title"), False, False, 0)
    box.pack_start(label(subtitle, "fos-small", "fos-muted"), False, False, 0)
    return box


def build_keyboard(status_cb) -> Gtk.Box:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(pack_header("Keyboard", "Layout and key repeat for this session."), False, False, 0)

    layout_row = Gtk.Box(spacing=12)
    layout_row.pack_start(label("Layout", "fos-text", "fos-strong"), False, False, 0)
    combo = Gtk.ComboBoxText()
    current = current_layout()
    seen = set()
    for code, name in COMMON_LAYOUTS:
        combo.append(code, f"{name} ({code})")
        seen.add(code)
    if current not in seen:
        combo.append(current, current)
    combo.set_active_id(current)
    combo.set_hexpand(True)
    layout_row.pack_start(combo, True, True, 0)
    root.pack_start(layout_row, False, False, 0)

    delay, rate = current_repeat()
    delay_row = Gtk.Box(spacing=12)
    delay_row.pack_start(label("Repeat delay", "fos-text"), False, False, 0)
    delay_scale = add_classes(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 100, 1000, 10), "fos-scale")
    delay_scale.set_value(delay)
    delay_scale.set_hexpand(True)
    delay_scale.set_draw_value(True)
    delay_row.pack_start(delay_scale, True, True, 0)
    root.pack_start(delay_row, False, False, 0)

    rate_row = Gtk.Box(spacing=12)
    rate_row.pack_start(label("Repeat rate", "fos-text"), False, False, 0)
    rate_scale = add_classes(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1), "fos-scale")
    rate_scale.set_value(rate)
    rate_scale.set_hexpand(True)
    rate_scale.set_draw_value(True)
    rate_row.pack_start(rate_scale, True, True, 0)
    root.pack_start(rate_row, False, False, 0)

    def apply(_button=None) -> None:
        code = combo.get_active_id() or "us"
        apply_layout(code)
        apply_repeat(int(delay_scale.get_value()), int(rate_scale.get_value()))
        CONFIG.mkdir(parents=True, exist_ok=True)
        (CONFIG / "keyboard").write_text(
            f"layout={code}\ndelay={int(delay_scale.get_value())}\nrate={int(rate_scale.get_value())}\n",
            encoding="utf-8",
        )
        status_cb("Keyboard settings applied for this session.")

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)
    return root


def build_mouse(status_cb) -> Gtk.Box:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(pack_header("Mouse and touchpad", "Pointer acceleration for this session."), False, False, 0)
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

    def apply(_button=None) -> None:
        value = scale.get_value()
        numer_v = max(1, int(round(value * 10)))
        thr_v = int(thr.get_value())
        apply_accel(numer_v, 10, thr_v)
        CONFIG.mkdir(parents=True, exist_ok=True)
        (CONFIG / "mouse").write_text(f"accel={value}\nthreshold={thr_v}\n", encoding="utf-8")
        status_cb("Mouse settings applied for this session.")

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
    from .wallpaper import THEMES

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("Wallpaper", "Drawn FosOS backgrounds. Login and lock screens stay on Dawn Aperture."),
        False,
        False,
        0,
    )
    prefs = load_desktop_prefs()
    current = prefs.get("wallpaper", "dawn")
    group = None
    radios: dict[str, Gtk.RadioButton] = {}
    for theme_id, title in THEMES:
        radio = Gtk.RadioButton.new_with_label_from_widget(group, title)
        if group is None:
            group = radio
        if theme_id == current:
            radio.set_active(True)
        radios[theme_id] = radio
        root.pack_start(radio, False, False, 0)

    def apply(_button=None) -> None:
        values = load_desktop_prefs()
        chosen = "dawn"
        for theme_id, radio in radios.items():
            if radio.get_active():
                chosen = theme_id
                break
        values["wallpaper"] = chosen
        save_desktop_prefs(values)
        _request_shell_reload()
        status_cb(f"Wallpaper set to {dict(THEMES).get(chosen, chosen)}. Desktop refreshes shortly.")

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)
    tip = label(
        "Image file wallpapers are not supported yet — keep the branded drawn look.",
        "fos-small",
        "fos-muted",
    )
    tip.set_line_wrap(True)
    root.pack_start(tip, False, False, 0)
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
    prefs = load_kv("taskbar", {"workspaces": "1", "clock_date": "1", "bell": "1"})

    workspaces = Gtk.CheckButton(label="Show desktop switcher (1–4)")
    workspaces.set_active(truthy(prefs.get("workspaces"), True))
    root.pack_start(workspaces, False, False, 0)

    clock_date = Gtk.CheckButton(label="Show date under the clock")
    clock_date.set_active(truthy(prefs.get("clock_date"), True))
    root.pack_start(clock_date, False, False, 0)

    bell = Gtk.CheckButton(label="Show notification bell")
    bell.set_active(truthy(prefs.get("bell"), True))
    root.pack_start(bell, False, False, 0)

    def apply(_button=None) -> None:
        save_kv(
            "taskbar",
            {
                "workspaces": "1" if workspaces.get_active() else "0",
                "clock_date": "1" if clock_date.get_active() else "0",
                "bell": "1" if bell.get_active() else "0",
            },
        )
        _request_shell_reload()
        status_cb("Taskbar preferences saved.")

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)
    tip = label("Pinned apps are managed from the taskbar (right-click → Pin).", "fos-small", "fos-muted")
    tip.set_line_wrap(True)
    root.pack_start(tip, False, False, 0)
    return root


def build_notifications(status_cb) -> Gtk.Box:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("Notifications", "Toasts, quiet hours, and Notification Center history."),
        False,
        False,
        0,
    )
    prefs = load_kv("notifications", {"dnd": "0", "toasts": "1", "timeout": "5000"})

    dnd = Gtk.CheckButton(label="Do not disturb (hide toast popups)")
    dnd.set_active(truthy(prefs.get("dnd"), False))
    root.pack_start(dnd, False, False, 0)

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

    def apply(_button=None) -> None:
        save_kv(
            "notifications",
            {
                "dnd": "1" if dnd.get_active() else "0",
                "toasts": "1" if toasts.get_active() else "0",
                "timeout": str(int(scale.get_value() * 1000)),
            },
        )
        _request_shell_reload()
        status_cb("Notification preferences saved.")

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)

    tip = label(
        "History still appears in Notification Center (Win+N) while Do not disturb is on.",
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
    return build_tool_page(
        "Display",
        "Arrange monitors, set resolution and orientation.",
        ["arandr"],
        "Open display layout",
        status_cb,
    )


def build_sound(status_cb) -> Gtk.Box:
    return build_tool_page(
        "Sound",
        "Choose output and input devices and levels.",
        ["pavucontrol"],
        "Open volume control",
        status_cb,
    )


def build_network(status_cb) -> Gtk.Box:
    return build_tool_page(
        "Network",
        "Wi-Fi, wired, and VPN connections via NetworkManager.",
        ["nm-connection-editor"],
        "Open network connections",
        status_cb,
    )


def build_bluetooth(status_cb) -> Gtk.Box:
    return build_tool_page(
        "Bluetooth",
        "Pair and manage Bluetooth devices.",
        ["blueman-manager"],
        "Open Bluetooth manager",
        status_cb,
    )


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

    card = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), "fos-card")
    card.set_border_width(12)
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
        "Install updates runs `fos update && fos upgrade` with your password when needed.",
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


def build_power(status_cb) -> Gtk.Box:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("Power", "Idle blanking for this session. Lid actions follow systemd-logind."),
        False,
        False,
        0,
    )

    timeout = idle_timeout_seconds()
    row = Gtk.Box(spacing=12)
    row.pack_start(label("Blank screen after", "fos-text"), False, False, 0)
    scale = add_classes(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1800, 60), "fos-scale")
    scale.set_value(timeout)
    scale.set_hexpand(True)
    scale.set_draw_value(True)
    scale.connect("format-value", lambda _s, v: "Off" if int(v) == 0 else f"{int(v)} s")
    row.pack_start(scale, True, True, 0)
    root.pack_start(row, False, False, 0)

    def apply(_button=None) -> None:
        seconds = int(scale.get_value())
        apply_idle_timeout(seconds)
        CONFIG.mkdir(parents=True, exist_ok=True)
        (CONFIG / "power").write_text(f"blank={seconds}\n", encoding="utf-8")
        status_cb("Idle blanking updated. Screen lock still uses Super+L / xss-lock.")

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)

    def suspend(_button=None) -> None:
        status_cb("Suspending…")
        subprocess.Popen(["systemctl", "suspend"])

    actions = Gtk.Box(spacing=8)
    suspend_btn = button("Suspend now", variant="outline")
    suspend_btn.connect("clicked", suspend)
    actions.pack_start(suspend_btn, False, False, 0)
    root.pack_start(actions, False, False, 0)

    tip = label(
        "Brightness is on the taskbar when a backlight is present.",
        "fos-small",
        "fos-muted",
    )
    tip.set_line_wrap(True)
    root.pack_start(tip, False, False, 0)
    return root


PAGES = {
    "keyboard": ("Keyboard", build_keyboard),
    "mouse": ("Mouse and touchpad", build_mouse),
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
    "updates": ("Updates", build_updates),
    "storage": ("Storage", build_storage),
}


def restore_session_input() -> None:
    """Apply saved keyboard/mouse/power prefs at session start."""
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
    power = CONFIG / "power"
    if power.is_file():
        values = dict(line.split("=", 1) for line in power.read_text(encoding="utf-8").splitlines() if "=" in line)
        try:
            apply_idle_timeout(int(values.get("blank", "300")))
        except ValueError:
            pass
