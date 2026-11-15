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
    ("Mail", "x-scheme-handler/mailto"),
]


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
            if mime == "x-scheme-handler/http":
                set_default_for_type(apps[index], "x-scheme-handler/https")
        status_cb(f"Updated {changed} default app{'s' if changed != 1 else ''}.")

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)
    note = label(
        f"Choices are stored for your account ({MIMEAPPS}).",
        "fos-small",
        "fos-muted",
    )
    note.set_line_wrap(True)
    root.pack_start(note, False, False, 0)
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
