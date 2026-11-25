"""Additional built-in Settings panels (accounts, appearance, shortcuts, …)."""

from __future__ import annotations

import getpass
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from . import apps as appmod
from .onedrive import accounts_section
from .settings_helpers import settings_row, settings_section
from .settings_pages import CONFIG, load_kv, pack_header, run, save_kv, truthy
from .settings_pages import _request_shell_reload  # noqa: PLC2701 — shared shell reload
from .ui import FosDialog, add_classes, button, clear, fos_alert, fos_confirm, label

POLICY = Path("/usr/libexec/fosos-settings-policy")
AUTOLOGIN_CONF = Path("/etc/lightdm/lightdm.conf.d/95-fosos-autologin.conf")
XSETTINGS_TEMPLATE = Path("/usr/share/fosos-desktop/xsettingsd.conf")
USER_XSETTINGS = CONFIG / "xsettingsd.conf"
DEFAULT_FONT_SIZE = 11
FONT_SCALE_MIN = 0.85
FONT_SCALE_MAX = 1.4

_OPENBOX_KEY_ALIASES = {
    " ": "space",
    "space": "space",
}


def _run(argv: list[str], timeout: float = 8.0) -> tuple[int, str]:
    if not argv or shutil.which(argv[0]) is None:
        return 127, ""
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""
    out = (result.stdout or "") + (result.stderr or "")
    return result.returncode, out.strip()


def pkexec_policy(*args: str) -> bool:
    if shutil.which("pkexec") is None or not POLICY.is_file():
        return False
    code, _out = _run(["pkexec", str(POLICY), *args], timeout=120)
    return code == 0


def pkexec_policy_stdin(*args: str, stdin_text: str) -> bool:
    if shutil.which("pkexec") is None or not POLICY.is_file():
        return False
    try:
        result = subprocess.run(
            ["pkexec", str(POLICY), *args],
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def list_timezones() -> list[str]:
    output = run(["timedatectl", "list-timezones"])
    if output:
        zones = [line.strip() for line in output.splitlines() if line.strip() and "/" in line]
        if zones:
            return zones
    zoneinfo = Path("/usr/share/zoneinfo")
    if not zoneinfo.is_dir():
        return ["UTC"]
    names: list[str] = []
    for path in zoneinfo.rglob("*"):
        if not path.is_file() or path.name in ("UTC", "localtime", "posixrules", "Factory"):
            continue
        try:
            rel = path.relative_to(zoneinfo)
        except ValueError:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        names.append("/".join(rel.parts))
    return sorted(set(names)) or ["UTC"]


def current_timezone() -> str:
    value = run(["timedatectl", "show", "-p", "Timezone", "--value"])
    if value:
        return value.strip()
    try:
        link = Path("/etc/localtime").resolve()
        parts = link.parts
        if "zoneinfo" in parts:
            index = parts.index("zoneinfo")
            return "/".join(parts[index + 1 :])
    except OSError:
        pass
    return "UTC"


def current_ntp() -> bool | None:
    value = run(["timedatectl", "show", "-p", "NTP", "--value"])
    if value is None:
        return None
    return value.strip().lower() in ("yes", "1", "true")


def write_xsettings(
    *,
    font_size: int | None = None,
    cursor_size: int | None = None,
    dpi: int | None = None,
) -> bool:
    template_path = XSETTINGS_TEMPLATE
    if not template_path.is_file():
        template_path = appmod.DATA_DIR / "xsettingsd.conf"
    try:
        text = template_path.read_text(encoding="utf-8")
    except OSError:
        return False

    size = font_size if font_size is not None else DEFAULT_FONT_SIZE
    if re.search(r'^Gtk/FontName\s+"', text, flags=re.MULTILINE):
        text = re.sub(
            r'^Gtk/FontName\s+"[^"]*"',
            f'Gtk/FontName "Inter {size}"',
            text,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        text += f'\nGtk/FontName "Inter {size}"\n'

    if cursor_size is not None:
        if re.search(r"^Xcursor/size\s+", text, flags=re.MULTILINE):
            text = re.sub(r"^Xcursor/size\s+\S+", f"Xcursor/size {cursor_size}", text, count=1, flags=re.MULTILINE)
        else:
            text += f"\nXcursor/size {cursor_size}\n"

    if dpi is not None:
        if re.search(r"^Xft/DPI\s+", text, flags=re.MULTILINE):
            text = re.sub(r"^Xft/DPI\s+\S+", f"Xft/DPI {dpi}", text, count=1, flags=re.MULTILINE)
        else:
            text += f"\nXft/DPI {dpi}\n"

    USER_XSETTINGS.parent.mkdir(parents=True, exist_ok=True)
    try:
        USER_XSETTINGS.write_text(text, encoding="utf-8")
    except OSError:
        return False

    uid = os.getuid()
    subprocess.run(["pkill", "-u", str(uid), "-x", "xsettingsd"], check=False)
    if shutil.which("xsettingsd"):
        try:
            subprocess.Popen(
                ["xsettingsd", "-c", str(USER_XSETTINGS)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            return False
    return True


def restart_xsettings_from_prefs() -> bool:
    appearance = load_kv("appearance", {"font_size": str(DEFAULT_FONT_SIZE), "cursor_size": "24"})
    try:
        font_size = max(8, min(24, int(appearance.get("font_size", str(DEFAULT_FONT_SIZE)))))
    except ValueError:
        font_size = DEFAULT_FONT_SIZE
    try:
        cursor_size = max(12, min(48, int(appearance.get("cursor_size", "24"))))
    except ValueError:
        cursor_size = 24
    return write_xsettings(font_size=font_size, cursor_size=cursor_size)


def _read_autologin_user() -> str | None:
    if not AUTOLOGIN_CONF.is_file():
        return None
    try:
        text = AUTOLOGIN_CONF.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("autologin-user="):
            user = stripped.split("=", 1)[1].strip()
            return user or None
    return None


def _gdk_key_to_openbox(event: Gdk.EventKey) -> str | None:
    name = Gdk.keyval_name(event.keyval) or ""
    if not name or name.endswith("_L") or name.endswith("_R"):
        if name in (
            "Shift_L",
            "Shift_R",
            "Control_L",
            "Control_R",
            "Alt_L",
            "Alt_R",
            "Super_L",
            "Super_R",
            "Meta_L",
            "Meta_R",
            "ISO_Level3_Shift",
            "Num_Lock",
            "Caps_Lock",
        ):
            return None
    mods: list[str] = []
    state = event.state
    if state & Gdk.ModifierType.SUPER_MASK:
        mods.append("W")
    if state & Gdk.ModifierType.CONTROL_MASK:
        mods.append("C")
    if state & Gdk.ModifierType.MOD1_MASK:
        mods.append("A")
    if state & Gdk.ModifierType.SHIFT_MASK:
        mods.append("S")

    key = _OPENBOX_KEY_ALIASES.get(name, name)
    if len(key) == 1:
        key = key.lower()
    elif key.startswith("F") and key[1:].isdigit():
        pass
    elif key == "Return":
        key = "Return"
    elif key in ("Left", "Right", "Up", "Down", "Tab", "Escape", "Print", "Delete", "BackSpace"):
        pass
    else:
        key = key.replace("_", "-")

    if not key:
        return None
    if mods:
        return "-".join(mods) + "-" + key
    return key


class _KeyCaptureDialog(Gtk.Window):
    def __init__(self, parent: Gtk.Widget, on_capture) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self._on_capture = on_capture
        self.set_title("Capture shortcut")
        self.set_modal(True)
        self.set_transient_for(parent.get_toplevel() if hasattr(parent, "get_toplevel") else None)
        self.set_decorated(True)
        self.set_default_size(320, 120)
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("key-press-event", self._on_key)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=16)
        self.add(box)
        box.pack_start(label("Press the key combination you want to use.", "fos-text"), False, False, 0)
        cancel = button("Cancel", variant="ghost", size="sm")
        cancel.connect("clicked", lambda _b: self.destroy())
        box.pack_start(cancel, False, False, 0)

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        combo = _gdk_key_to_openbox(event)
        if combo:
            self._on_capture(combo)
            self.destroy()
            return True
        return False


def build_datetime(status_cb) -> Gtk.Box:
    from .region import format_date_full, format_time

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("Date & time", "Timezone and automatic time sync (NTP)."),
        False,
        False,
        0,
    )

    zones = list_timezones()
    current_tz = current_timezone()
    tz_combo = Gtk.ComboBoxText()
    if current_tz not in zones:
        tz_combo.append(current_tz, current_tz)
    for zone in zones:
        tz_combo.append(zone, zone)
    tz_combo.set_active_id(current_tz)

    ntp_switch = Gtk.Switch()
    ntp_val = current_ntp()
    if ntp_val is not None:
        ntp_switch.set_active(ntp_val)
        ntp_switch.set_sensitive(True)
    else:
        ntp_switch.set_sensitive(False)

    clock = label("", "fos-text", "fos-strong")
    clock.set_line_wrap(True)

    def refresh_clock() -> bool:
        try:
            clock.set_text(f"{format_time()} · {format_date_full()}")
        except OSError:
            clock.set_text(datetime.now().strftime("%H:%M · %A, %-d %B %Y"))
        return True

    tick_id = GLib.timeout_add_seconds(1, refresh_clock)
    root.connect("destroy", lambda *_a: GLib.source_remove(tick_id) if tick_id else None)
    refresh_clock()

    def apply(_button=None) -> None:
        tz = tz_combo.get_active_id() or current_tz
        ok_tz = pkexec_policy("set-timezone", tz)
        if ok_tz:
            status_cb(f"Timezone set to {tz}.")
        elif shutil.which("timedatectl"):
            code, _ = _run(["pkexec", "timedatectl", "set-timezone", tz], timeout=60)
            if code == 0:
                status_cb(f"Timezone set to {tz}.")
            else:
                status_cb("Could not set timezone (policy helper or pkexec unavailable).")
        else:
            status_cb("timedatectl is not available.")

        if ntp_switch.get_sensitive():
            desired = "1" if ntp_switch.get_active() else "0"
            if pkexec_policy("set-ntp", desired):
                status_cb("Automatic time " + ("enabled." if desired == "1" else "disabled."))
            else:
                code, _ = _run(["pkexec", "timedatectl", "set-ntp", desired], timeout=60)
                if code == 0:
                    status_cb("Automatic time " + ("enabled." if desired == "1" else "disabled."))
                else:
                    status_cb("Could not change NTP setting.")

    root.pack_start(
        settings_section(
            "",
            settings_row("Time zone", current_tz, trailing=tz_combo),
            settings_row("Set time automatically (NTP)", "", trailing=ntp_switch),
            settings_row("Preview", "", trailing=clock),
        ),
        False,
        False,
        0,
    )

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)
    tip = label(
        "The clock preview updates every second. Some changes need the fosos-settings-policy helper.",
        "fos-small",
        "fos-muted",
    )
    tip.set_line_wrap(True)
    root.pack_start(tip, False, False, 0)
    return root


def build_accounts(status_cb) -> Gtk.Box:
    username = getpass.getuser()
    display = appmod.user_display_name()

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(pack_header("Your account", "Name, password, and sign-in options."), False, False, 0)

    name_entry = Gtk.Entry()
    name_entry.set_text(display)
    name_entry.set_hexpand(True)

    current_pw = Gtk.Entry()
    current_pw.set_visibility(False)
    new_pw = Gtk.Entry()
    new_pw.set_visibility(False)
    confirm_pw = Gtk.Entry()
    confirm_pw.set_visibility(False)

    autologin = Gtk.Switch()
    live = appmod.is_live()
    autologin_user = _read_autologin_user()
    autologin.set_active(bool(autologin_user) and autologin_user.lower() not in ("off", "none"))
    if live:
        autologin.set_sensitive(False)

    root.pack_start(
        settings_section(
            "Profile",
            settings_row("User name", username),
            settings_row("Display name", "Shown on the sign-in screen and Start menu", trailing=name_entry),
        ),
        False,
        False,
        0,
    )

    root.pack_start(
        settings_section(
            "Password",
            settings_row("Current password", "", trailing=current_pw),
            settings_row("New password", "", trailing=new_pw),
            settings_row("Confirm password", "", trailing=confirm_pw),
        ),
        False,
        False,
        0,
    )

    autologin_sub = (
        "Not available on the live image."
        if live
        else "Sign in without a password on this PC."
    )
    root.pack_start(
        settings_section(
            "Sign-in",
            settings_row("Automatic sign-in", autologin_sub, trailing=autologin),
        ),
        False,
        False,
        0,
    )

    root.pack_start(accounts_section(status_cb), False, False, 0)

    def apply(_button=None) -> None:
        new_name = name_entry.get_text().strip()
        if new_name and new_name != display:
            if pkexec_policy("set-gecos", username, new_name):
                status_cb("Display name updated.")
            elif shutil.which("chfn"):
                code, _ = _run(["chfn", "-f", new_name, username])
                if code == 0:
                    status_cb("Display name updated.")
                else:
                    code2, _ = _run(["pkexec", "chfn", "-f", new_name, username])
                    if code2 == 0:
                        status_cb("Display name updated.")
                    else:
                        status_cb("Could not change display name.")
            else:
                status_cb("chfn is not available.")

        cur = current_pw.get_text()
        new = new_pw.get_text()
        conf = confirm_pw.get_text()
        if cur or new or conf:
            if not cur or not new:
                status_cb("Enter current and new password.")
                return
            if new != conf:
                status_cb("New passwords do not match.")
                return
            try:
                import pamela  # type: ignore
            except ImportError:
                status_cb("python3-pamela is not installed.")
                return
            try:
                pamela.authenticate(username, cur, service="fosos-lock")
            except pamela.PAMError:
                status_cb("Current password is incorrect.")
                return
            if pkexec_policy_stdin("set-password", username, stdin_text=new + "\n"):
                status_cb("Password changed.")
                current_pw.set_text("")
                new_pw.set_text("")
                confirm_pw.set_text("")
            else:
                status_cb("Could not change password (policy helper missing or denied).")

        if not live:
            if autologin.get_active():
                if not pkexec_policy("set-autologin", username):
                    status_cb("Could not enable automatic sign-in.")
            elif autologin_user:
                if not pkexec_policy("set-autologin", "off"):
                    status_cb("Could not disable automatic sign-in.")

    def lock_screen(_button=None) -> None:
        if appmod.spawn(["fosos-lock"]):
            status_cb("Locked.")
        else:
            status_cb("fosos-lock is not available.")

    def sign_out(_button=None) -> None:
        if shutil.which("openbox"):
            subprocess.Popen(["openbox", "--exit"], start_new_session=True)
            status_cb("Signing out…")
        elif shutil.which("loginctl"):
            subprocess.Popen(["loginctl", "terminate-user", username], start_new_session=True)
            status_cb("Signing out…")
        else:
            status_cb("Could not sign out.")

    btn_row = Gtk.Box(spacing=8)
    lock_btn = button("Lock", variant="outline", size="sm")
    lock_btn.connect("clicked", lock_screen)
    sign_btn = button("Sign out", variant="outline", size="sm")
    sign_btn.connect("clicked", sign_out)
    btn_row.pack_start(lock_btn, False, False, 0)
    btn_row.pack_start(sign_btn, False, False, 0)
    root.pack_start(btn_row, False, False, 0)

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)

    note = label("Lock always requires your password to unlock.", "fos-small", "fos-muted")
    note.set_line_wrap(True)
    root.pack_start(note, False, False, 0)
    return root


def build_appearance(status_cb) -> Gtk.Box:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(pack_header("Appearance", "Text size, pointer, and motion."), False, False, 0)

    appearance = load_kv("appearance", {"font_size": str(DEFAULT_FONT_SIZE), "cursor_size": "24"})
    access = load_kv("accessibility", {"reduce_motion": "0"})
    try:
        font_size = int(appearance.get("font_size", str(DEFAULT_FONT_SIZE)))
    except ValueError:
        font_size = DEFAULT_FONT_SIZE
    try:
        cursor_size = int(appearance.get("cursor_size", "24"))
    except ValueError:
        cursor_size = 24
    scale = font_size / DEFAULT_FONT_SIZE

    scale_w = add_classes(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, FONT_SCALE_MIN, FONT_SCALE_MAX, 0.05), "fos-scale")
    scale_w.set_value(max(FONT_SCALE_MIN, min(FONT_SCALE_MAX, scale)))
    scale_w.set_hexpand(True)
    scale_w.set_draw_value(True)
    scale_w.connect("format-value", lambda _s, v: f"{v:.2f}×")

    cursor_spin = Gtk.SpinButton.new_with_range(12, 48, 1)
    cursor_spin.set_value(cursor_size)

    motion_sw = Gtk.Switch()
    motion_sw.set_active(truthy(access.get("reduce_motion"), False))

    def apply(_button=None) -> None:
        new_font = max(8, min(24, round(DEFAULT_FONT_SIZE * scale_w.get_value())))
        new_cursor = int(cursor_spin.get_value())
        appearance["font_size"] = str(new_font)
        appearance["cursor_size"] = str(new_cursor)
        save_kv("appearance", appearance)
        access["reduce_motion"] = "1" if motion_sw.get_active() else "0"
        save_kv("accessibility", access)
        if write_xsettings(font_size=new_font, cursor_size=new_cursor):
            status_cb("Appearance applied.")
        else:
            status_cb("Could not write xsettingsd configuration.")
        _request_shell_reload()

    root.pack_start(
        settings_section(
            "",
            settings_row("Text size", "Inter font scale", trailing=scale_w),
            settings_row("Cursor size", "Pointer size in pixels", trailing=cursor_spin),
            settings_row("Reduce motion", "Fewer animations in the shell", trailing=motion_sw),
        ),
        False,
        False,
        0,
    )

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)
    return root


def build_shortcuts(status_cb) -> Gtk.Box:
    from .shortcuts import (
        SHORTCUT_ACTIONS,
        apply_shortcuts,
        default_map,
        find_conflicts,
        load_shortcuts,
        save_shortcuts,
    )

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(pack_header("Keyboard shortcuts", "Global shortcuts handled by Openbox."), False, False, 0)

    values = load_shortcuts()
    rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    entries: dict[str, Gtk.Entry] = {}

    for action_id, title, default_key, _kind, _payload in SHORTCUT_ACTIONS:
        entry = Gtk.Entry()
        entry.set_text(values.get(action_id, default_key))
        entry.set_width_chars(16)

        def make_capture(ent: Gtk.Entry):
            def open_capture(_button=None) -> None:
                _KeyCaptureDialog(ent, lambda key: (ent.set_text(key), status_cb(f"Captured {key}.")))

            return open_capture

        cap_btn = button("Capture", variant="ghost", size="sm")
        cap_btn.connect("clicked", make_capture(entry))

        trail = Gtk.Box(spacing=6)
        trail.pack_start(entry, False, False, 0)
        trail.pack_start(cap_btn, False, False, 0)
        rows_box.pack_start(settings_row(title, default_key, trailing=trail), False, False, 0)
        entries[action_id] = entry

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_min_content_height(280)
    scroll.add(rows_box)
    root.pack_start(scroll, True, True, 0)

    def collect() -> dict[str, str]:
        return {action_id: ent.get_text().strip() for action_id, ent in entries.items()}

    def apply(_button=None) -> None:
        merged = collect()
        conflicts = find_conflicts(merged)
        if conflicts:
            parts = [f"{key} ({', '.join(ids)})" for key, ids in conflicts]
            status_cb("Conflicts: " + "; ".join(parts))
            return
        save_shortcuts(merged)
        if apply_shortcuts(merged):
            status_cb("Shortcuts saved and applied.")
        else:
            status_cb("Saved preferences but could not update Openbox configuration.")

    def reset(_button=None) -> None:
        defaults = default_map()
        for action_id, ent in entries.items():
            ent.set_text(defaults.get(action_id, ""))
        status_cb("Reset to defaults — choose Apply to save.")

    btn_row = Gtk.Box(spacing=8)
    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    reset_btn = button("Reset to defaults", variant="outline", size="sm")
    reset_btn.connect("clicked", reset)
    btn_row.pack_start(apply_btn, False, False, 0)
    btn_row.pack_start(reset_btn, False, False, 0)
    root.pack_start(btn_row, False, False, 0)
    return root


def _app_subtitle(app: appmod.App, kind: str, package: str | None) -> str:
    if kind == "local":
        return "Local app · not from APT"
    if package:
        version, size = appmod.package_details(package)
        bits = [package]
        if version:
            bits.append(version)
        if size:
            bits.append(size)
        if kind == "required":
            bits.append("required by FosOS")
        return " · ".join(bits)
    return app.description or "System component"


def build_installed_apps(status_cb) -> Gtk.Box:
    """Windows-style Installed apps: searchable list with Uninstall."""
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("Installed apps", "Uninstall programs on this PC."),
        False,
        False,
        0,
    )

    store_row = Gtk.Box(spacing=8)
    store_row.pack_start(
        label("Get more apps from the FosOS Store.", "fos-text", "fos-muted"),
        True,
        True,
        0,
    )
    open_store = button("Get apps", variant="default", size="sm")
    open_store.connect(
        "clicked",
        lambda _b: status_cb("Opened Store.") if appmod.spawn(["fosos-store"]) else status_cb("Store is not available."),
    )
    store_row.pack_end(open_store, False, False, 0)
    root.pack_start(store_row, False, False, 0)

    filter_entry = add_classes(Gtk.Entry(), "fos-input", "fos-settings-apps-filter")
    filter_entry.set_placeholder_text("Filter apps")
    filter_entry.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "system-search-symbolic")
    root.pack_start(filter_entry, False, False, 0)

    summary = label("", "fos-small", "fos-muted")
    root.pack_start(summary, False, False, 0)

    list_host = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    root.pack_start(list_host, False, False, 0)

    busy = {"value": False}

    def rebuild(_entry=None) -> None:
        clear(list_host)
        needle = filter_entry.get_text().strip().lower()
        apps = appmod.all_apps()
        if needle:
            apps = [app for app in apps if needle in app.search_text()]

        card = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-settings-card")
        if not apps:
            empty = add_classes(Gtk.Box(), "fos-settings-row")
            empty.pack_start(
                label("No apps match your filter." if needle else "No apps found.", "fos-small", "fos-muted"),
                False,
                False,
                0,
            )
            card.pack_start(empty, False, False, 0)
            summary.set_text("0 apps")
        else:
            summary.set_text(f"{len(apps)} app{'s' if len(apps) != 1 else ''}")
            for index, app in enumerate(apps):
                kind, package = appmod.app_install_kind(app)
                if kind == "uninstallable" and package:
                    uninstall_btn = button("Uninstall", variant="outline", size="sm")
                    uninstall_btn.connect(
                        "clicked",
                        lambda _b, a=app, p=package: _uninstall_app(a, p, status_cb, rebuild, busy),
                    )
                    trailing: Gtk.Widget = uninstall_btn
                elif kind == "local":
                    trailing = label("Local", "fos-small", "fos-muted")
                else:
                    trailing = label("Required", "fos-small", "fos-muted")
                card.pack_start(
                    settings_row(
                        app.name,
                        _app_subtitle(app, kind, package),
                        trailing=trailing,
                        icon_name=app.icon_name(),
                    ),
                    False,
                    False,
                    0,
                )
                if index < len(apps) - 1:
                    card.pack_start(add_classes(Gtk.Box(), "fos-settings-row-sep"), False, False, 0)

        list_host.pack_start(card, False, False, 0)
        list_host.show_all()

    filter_entry.connect("changed", rebuild)
    rebuild()
    status_cb("Choose an app to uninstall.")
    return root


def _uninstall_app(
    app: appmod.App,
    package: str,
    status_cb,
    rebuild,
    busy: dict[str, bool],
) -> None:
    if busy["value"]:
        return
    if not fos_confirm(
        None,
        f"Uninstall {app.name}?",
        f"This removes the package “{package}” and may remove related components.\n\n"
        "Administrator permission is required.",
        ok="Uninstall",
        destructive=True,
    ):
        return

    busy["value"] = True
    status_cb(f"Uninstalling {app.name}…")
    progress = FosDialog(None, title=f"Uninstalling {app.name}…")
    progress.add_body_text("Approve the password prompt if asked, then wait.")
    progress.footer.set_no_show_all(True)
    progress.footer.hide()
    progress.show_all()

    argv = [
        "pkexec",
        "env",
        "DEBIAN_FRONTEND=noninteractive",
        "apt-get",
        "remove",
        "--yes",
        "--",
        package,
    ]
    try:
        proc = Gio.Subprocess.new(
            argv,
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE,
        )
    except GLib.Error as error:
        progress.destroy()
        busy["value"] = False
        fos_alert(None, "Could not start uninstall", error.message)
        status_cb("Uninstall did not start.")
        return

    def finished(process, result) -> None:
        try:
            _ok, stdout, _stderr = process.communicate_utf8_finish(result)
        except GLib.Error as error:
            stdout = error.message
        progress.destroy()
        busy["value"] = False
        output = (stdout or "").strip()
        if len(output) > 1200:
            output = "…\n" + output[-1200:]
        if process.get_successful():
            # Drop Start / taskbar pins for this launcher if present.
            try:
                pins = appmod.Pinned()
                if pins.contains(app.id):
                    pins.unpin(app.id)
            except OSError:
                pass
            body = f"{app.name} ({package}) was removed."
            if output:
                body = f"{body}\n\n{output}"
            fos_alert(None, "App uninstalled", body)
            status_cb(f"Uninstalled {app.name}.")
            rebuild()
        else:
            body = f"{app.name} could not be uninstalled."
            if output:
                body = f"{body}\n\n{output}"
            fos_alert(None, "Uninstall failed", body)
            status_cb("Uninstall failed.")

    proc.communicate_utf8_async(None, None, finished)


def build_startup(status_cb) -> Gtk.Box:
    from .taskmgr import list_startup_apps, set_startup_enabled

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(pack_header("Startup apps", "Programs that run when you sign in."), False, False, 0)

    apps = list_startup_apps()
    switches: list[tuple[str, Gtk.Switch]] = []
    rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    card = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-settings-card")

    for index, app in enumerate(apps):
        sw = Gtk.Switch()
        sw.set_active(app.enabled)
        switches.append((app.id, sw))
        card.pack_start(settings_row(app.name, app.description or app.exec_line, trailing=sw), False, False, 0)
        if index < len(apps) - 1:
            card.pack_start(add_classes(Gtk.Box(), "fos-settings-row-sep"), False, False, 0)

    if not apps:
        card.pack_start(
            label("No startup applications found.", "fos-small", "fos-muted"),
            False,
            False,
            0,
        )

    rows.pack_start(card, False, False, 0)
    root.pack_start(rows, False, False, 0)

    def apply(_button=None) -> None:
        changed = 0
        for desktop_id, switch in switches:
            desired = switch.get_active()
            current = next((a for a in apps if a.id == desktop_id), None)
            if current is None or current.enabled == desired:
                continue
            if set_startup_enabled(desktop_id, desired):
                changed += 1
        status_cb(f"Updated {changed} startup item{'s' if changed != 1 else ''}. Changes apply at next sign-in.")

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)
    return root


def build_accessibility(status_cb) -> Gtk.Box:
    from .settings_pages import current_layout

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(pack_header("Accessibility", "Vision and keyboard assistance."), False, False, 0)

    appearance = load_kv("appearance", {"font_size": str(DEFAULT_FONT_SIZE)})
    access = load_kv("accessibility", {"reduce_motion": "0", "sticky_keys": "0", "slow_keys": "0"})
    try:
        font_size = int(appearance.get("font_size", str(DEFAULT_FONT_SIZE)))
    except ValueError:
        font_size = DEFAULT_FONT_SIZE

    large_text = Gtk.Switch()
    large_text.set_active(font_size >= 14)

    reduce_motion = Gtk.Switch()
    reduce_motion.set_active(truthy(access.get("reduce_motion"), False))

    sticky = Gtk.Switch()
    sticky.set_active(truthy(access.get("sticky_keys"), False))
    slow = Gtk.Switch()
    slow.set_active(truthy(access.get("slow_keys"), False))

    def apply(_button=None) -> None:
        new_font = 14 if large_text.get_active() else DEFAULT_FONT_SIZE
        cursor = appearance.get("cursor_size", "24")
        appearance["font_size"] = str(new_font)
        appearance["cursor_size"] = cursor
        save_kv("appearance", appearance)
        access["reduce_motion"] = "1" if reduce_motion.get_active() else "0"
        access["sticky_keys"] = "1" if sticky.get_active() else "0"
        access["slow_keys"] = "1" if slow.get_active() else "0"
        save_kv("accessibility", access)
        try:
            cursor_int = int(cursor)
        except ValueError:
            cursor_int = None
        write_xsettings(font_size=new_font, cursor_size=cursor_int)

        options: list[str] = []
        if sticky.get_active():
            options.append("stickykeys")
        if slow.get_active():
            options.append("slowkeys")
        layout = current_layout()
        argv = ["setxkbmap", "-layout", layout]
        if options:
            argv.extend(["-option", ",".join(options)])
        else:
            argv.extend(["-option", ""])
        subprocess.run(argv, check=False)

        _request_shell_reload()
        status_cb("Accessibility settings saved.")

    root.pack_start(
        settings_section(
            "",
            settings_row("Large text", "Uses 14 pt Inter instead of 11 pt", trailing=large_text),
            settings_row("Reduce motion", "Fewer animations in the shell", trailing=reduce_motion),
            settings_row("Sticky keys", "Press modifiers one at a time", trailing=sticky),
            settings_row("Slow keys", "Short delay before keys register", trailing=slow),
        ),
        False,
        False,
        0,
    )

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)
    return root


def build_privacy(status_cb) -> Gtk.Box:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(pack_header("Privacy & security", "Clipboard and notifications."), False, False, 0)

    prefs = load_kv("privacy", {"clear_clipboard_on_lock": "0"})
    clear_sw = Gtk.Switch()
    clear_sw.set_active(truthy(prefs.get("clear_clipboard_on_lock"), False))

    def apply(_button=None) -> None:
        save_kv("privacy", {"clear_clipboard_on_lock": "1" if clear_sw.get_active() else "0"})
        status_cb("Privacy preferences saved.")

    def open_notifications(_button=None) -> None:
        if appmod.spawn(["fosos-settings", "--builtin", "notifications"]):
            status_cb("Opened Notifications settings.")
        else:
            status_cb("Could not open Notifications settings.")

    root.pack_start(
        settings_section(
            "",
            settings_row("Clear clipboard on lock", "Remove copied text when the screen locks", trailing=clear_sw),
        ),
        False,
        False,
        0,
    )

    notif_btn = button("Notification settings…", variant="outline", size="sm")
    notif_btn.connect("clicked", open_notifications)
    root.pack_start(notif_btn, False, False, 0)

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)

    note = label("Lock always requires your password to unlock.", "fos-small", "fos-muted")
    note.set_line_wrap(True)
    root.pack_start(note, False, False, 0)
    return root


def _ufw_bin() -> str | None:
    path = shutil.which("ufw")
    if path:
        return path
    for candidate in ("/usr/sbin/ufw", "/sbin/ufw"):
        if Path(candidate).is_file():
            return candidate
    return None


def firewall_installed() -> bool:
    return _ufw_bin() is not None


def firewall_active_from_conf() -> bool | None:
    """Read ENABLED from ufw.conf without privileges. None if unknown."""
    path = Path("/etc/ufw/ufw.conf")
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.upper().startswith("ENABLED="):
                return line.split("=", 1)[1].strip().lower() in ("yes", "true", "1")
    except OSError:
        return None
    return None


def firewall_status() -> dict[str, object]:
    """Query firewall state without pkexec (conf + optional unprivileged ufw status)."""
    info: dict[str, object] = {
        "installed": firewall_installed(),
        "active": False,
        "incoming": "deny",
        "outgoing": "allow",
        "rules": [],
    }
    if not info["installed"]:
        return info
    conf_active = firewall_active_from_conf()
    if conf_active is not None:
        info["active"] = conf_active
    try:
        defaults = Path("/etc/default/ufw").read_text(encoding="utf-8")
    except OSError:
        defaults = ""
    for line in defaults.splitlines():
        if line.startswith("DEFAULT_INPUT_POLICY="):
            info["incoming"] = line.split("=", 1)[1].strip().strip('"').lower()
        elif line.startswith("DEFAULT_OUTPUT_POLICY="):
            info["outgoing"] = line.split("=", 1)[1].strip().strip('"').lower()
    # ufw status is often readable without root on Debian; never call pkexec here.
    ufw = _ufw_bin()
    if ufw is None:
        return info
    code, out = _run([ufw, "status", "numbered"], timeout=5)
    if code != 0 or not out:
        return info
    rules: list[str] = []
    for line in out.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if lower.startswith("status:"):
            info["active"] = "inactive" not in lower
            continue
        match = re.match(r"^\[\s*(\d+)\]\s+(.*)$", stripped)
        if match:
            rules.append(match.group(2).strip())
    info["rules"] = rules
    return info


def set_firewall_enabled_async(enabled: bool, done_cb) -> None:
    """Toggle UFW via pkexec without blocking the GTK main loop."""
    if not firewall_installed() or not POLICY.is_file() or shutil.which("pkexec") is None:
        done_cb(False, "Firewall helper is not available.")
        return
    argv = ["pkexec", str(POLICY), "set-firewall", "on" if enabled else "off"]
    try:
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


def build_firewall(status_cb) -> Gtk.Box:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("Firewall", "Block unexpected inbound connections."),
        False,
        False,
        0,
    )

    if not firewall_installed():
        root.pack_start(
            label(
                "The firewall package (ufw) is not installed. Install it from the Store or with fos install ufw.",
                "fos-text",
                "fos-muted",
            ),
            False,
            False,
            0,
        )
        return root

    # Avoid pkexec on first paint — use conf for the switch, refresh details after.
    active = firewall_active_from_conf()
    if active is None:
        active = False

    switch = Gtk.Switch()
    switch.set_active(bool(active))
    state_label = label("", "fos-text")
    defaults_label = label("", "fos-small", "fos-muted")
    defaults_label.set_line_wrap(True)
    rules_card = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-settings-card")

    def paint(info: dict[str, object] | None = None) -> None:
        data = info if info is not None else {
            "active": firewall_active_from_conf() or False,
            "incoming": "deny",
            "outgoing": "allow",
            "rules": [],
        }
        is_on = bool(data.get("active"))
        toggling["busy"] = True
        switch.set_active(is_on)
        toggling["busy"] = False
        state_label.set_text("Firewall is on" if is_on else "Firewall is off")
        incoming = str(data.get("incoming") or "deny")
        outgoing = str(data.get("outgoing") or "allow")
        defaults_label.set_text(
            f"Default: inbound {incoming}, outbound {outgoing}. "
            "SSH opens TCP 22 and Remote Desktop opens TCP 3389 when those services are on."
        )
        clear(rules_card)
        rules = list(data.get("rules") or [])
        if not is_on:
            empty = add_classes(Gtk.Box(), "fos-settings-row")
            empty.pack_start(label("Turn the firewall on to enforce rules.", "fos-small", "fos-muted"), False, False, 0)
            rules_card.pack_start(empty, False, False, 0)
        elif not rules:
            empty = add_classes(Gtk.Box(), "fos-settings-row")
            empty.pack_start(
                label("No extra allow rules. Inbound traffic is blocked by default.", "fos-small", "fos-muted"),
                False,
                False,
                0,
            )
            rules_card.pack_start(empty, False, False, 0)
        else:
            for index, rule in enumerate(rules[:40]):
                rules_card.pack_start(
                    settings_row(rule, ""),
                    False,
                    False,
                    0,
                )
                if index < min(len(rules), 40) - 1:
                    rules_card.pack_start(add_classes(Gtk.Box(), "fos-settings-row-sep"), False, False, 0)
        rules_card.show_all()

    toggling = {"busy": False}

    def refresh_details() -> None:
        # Detailed rule list needs privileges; run off the click path via idle.
        def load() -> bool:
            info = firewall_status()
            paint(info)
            status_cb("Firewall is on." if info.get("active") else "Firewall is off.")
            return False

        status_cb("Reading firewall status…")
        GLib.idle_add(load)

    def on_toggle(widget: Gtk.Switch, _gparam) -> None:
        if toggling["busy"]:
            return
        want = widget.get_active()
        current = bool(firewall_active_from_conf())
        if want == current:
            return
        toggling["busy"] = True
        widget.set_sensitive(False)
        status_cb("Authenticating to change the firewall…")

        def done(ok: bool, message: str) -> None:
            toggling["busy"] = False
            widget.set_sensitive(True)
            if not ok:
                # Revert switch.
                toggling["busy"] = True
                widget.set_active(not want)
                toggling["busy"] = False
                status_cb(message or "Firewall change failed.")
                return
            status_cb(f"Firewall {message}.")
            refresh_details()

        set_firewall_enabled_async(want, done)

    switch.connect("notify::active", on_toggle)

    root.pack_start(
        settings_section(
            "",
            settings_row("Firewall", "Block unexpected inbound connections", trailing=switch),
        ),
        False,
        False,
        0,
    )
    root.pack_start(state_label, False, False, 0)
    root.pack_start(defaults_label, False, False, 0)

    rules_heading = label("Allowed inbound", "fos-label")
    rules_heading.set_margin_top(4)
    root.pack_start(rules_heading, False, False, 0)
    root.pack_start(rules_card, False, False, 0)

    paint({"active": active, "incoming": "deny", "outgoing": "allow", "rules": []})
    GLib.idle_add(lambda: refresh_details() or False)
    return root


def ssh_server_installed() -> bool:
    return shutil.which("sshd") is not None or Path("/usr/sbin/sshd").is_file()


def ssh_client_installed() -> bool:
    return shutil.which("ssh") is not None or Path("/usr/bin/ssh").is_file()


def ssh_server_active() -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "ssh.service"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and (result.stdout or "").strip() == "active"


def ssh_host_addresses() -> list[str]:
    try:
        result = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [part for part in (result.stdout or "").split() if part]


def set_ssh_enabled_async(enabled: bool, done_cb) -> None:
    """Toggle OpenSSH server via pkexec without blocking the GTK main loop."""
    if not ssh_server_installed() or not POLICY.is_file() or shutil.which("pkexec") is None:
        done_cb(False, "SSH helper is not available.")
        return
    argv = ["pkexec", str(POLICY), "set-ssh", "on" if enabled else "off"]
    try:
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


def build_ssh(status_cb) -> Gtk.Box:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("SSH", "Remote terminal access in and out."),
        False,
        False,
        0,
    )

    if not ssh_server_installed():
        root.pack_start(
            label(
                "OpenSSH server is not installed. Install openssh-server from the Store or with fos install openssh-server.",
                "fos-text",
                "fos-muted",
            ),
            False,
            False,
            0,
        )
        return root

    active = ssh_server_active()
    switch = Gtk.Switch()
    switch.set_active(active)
    state_label = label("", "fos-text")
    how_label = label("", "fos-small", "fos-muted")
    how_label.set_line_wrap(True)
    how_label.set_selectable(True)
    client_label = label(
        "SSH client is ready — use Terminal: ssh user@host"
        if ssh_client_installed()
        else "SSH client (openssh-client) is missing.",
        "fos-small",
        "fos-muted",
    )
    client_label.set_line_wrap(True)

    toggling = {"busy": False}

    def paint() -> None:
        is_on = ssh_server_active()
        toggling["busy"] = True
        switch.set_active(is_on)
        toggling["busy"] = False
        if is_on:
            addrs = ssh_host_addresses() or ["(no address yet)"]
            primary = addrs[0]
            lines = [f"Listening on port 22 · {item}" for item in addrs]
            state_label.set_text("SSH server is on\n" + "\n".join(lines))
            user = getpass.getuser()
            how_label.set_text(
                f"From another PC: ssh {user}@{primary}\n"
                "Sign in with the same username and password as on this FosOS account. "
                "The firewall opens TCP 22 while SSH is on."
            )
        else:
            state_label.set_text("SSH server is off.")
            how_label.set_text("Turn on to allow remote terminal access to this PC on port 22.")

    def on_toggle(widget: Gtk.Switch, _gparam) -> None:
        if toggling["busy"]:
            return
        want = widget.get_active()
        if want == ssh_server_active():
            return
        toggling["busy"] = True
        widget.set_sensitive(False)
        status_cb("Authenticating to change SSH…")

        def done(ok: bool, message: str) -> None:
            toggling["busy"] = False
            widget.set_sensitive(True)
            if not ok:
                toggling["busy"] = True
                widget.set_active(not want)
                toggling["busy"] = False
                status_cb(message or "SSH change failed.")
                return
            status_cb(f"SSH server {message}.")
            paint()

        set_ssh_enabled_async(want, done)

    switch.connect("notify::active", on_toggle)
    root.pack_start(
        settings_section(
            "",
            settings_row("SSH server", "Allow others to connect to this PC", trailing=switch),
        ),
        False,
        False,
        0,
    )
    root.pack_start(state_label, False, False, 0)
    root.pack_start(how_label, False, False, 0)
    root.pack_start(client_label, False, False, 0)
    paint()
    status_cb("SSH server is on." if active else "SSH server is off.")
    return root


def _ensure_user_openbox_rc() -> str | None:
    from .shortcuts import SYSTEM_RC, USER_RC

    if USER_RC.is_file():
        try:
            return USER_RC.read_text(encoding="utf-8")
        except OSError:
            return None
    if not SYSTEM_RC.is_file():
        return None
    try:
        text = SYSTEM_RC.read_text(encoding="utf-8")
        USER_RC.parent.mkdir(parents=True, exist_ok=True)
        USER_RC.write_text(text, encoding="utf-8")
        return text
    except OSError:
        return None


def _patch_desktop_count(text: str, count: int) -> str:
    count = max(1, min(4, count))
    text = re.sub(r"(<desktops>\s*<number>)\d+(</number>)", rf"\g<1>{count}\g<2>", text, count=1)
    names = "\n".join(f"      <name>Desktop {n}</name>" for n in range(1, count + 1))
    text = re.sub(
        r"<names>[\s\S]*?</names>",
        f"<names>\n{names}\n    </names>",
        text,
        count=1,
    )
    return text


def build_multitasking(status_cb) -> Gtk.Box:
    from .shortcuts import USER_RC, reconfigure_openbox

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(pack_header("Multitasking", "Virtual desktops and window switching."), False, False, 0)

    prefs = load_kv("multitasking", {"desktop_count": "4"})
    try:
        current_count = max(1, min(4, int(prefs.get("desktop_count", "4"))))
    except ValueError:
        current_count = 4

    combo = Gtk.ComboBoxText()
    for n in range(1, 5):
        combo.append(str(n), str(n))
    combo.set_active_id(str(current_count))

    def apply(_button=None) -> None:
        try:
            count = int(combo.get_active_id() or "4")
        except ValueError:
            count = 4
        count = max(1, min(4, count))
        save_kv("multitasking", {"desktop_count": str(count)})
        text = _ensure_user_openbox_rc()
        if text is None:
            status_cb("Openbox configuration not found.")
            return
        patched = _patch_desktop_count(text, count)
        try:
            USER_RC.write_text(patched, encoding="utf-8")
        except OSError:
            status_cb("Could not write Openbox configuration.")
            return
        if reconfigure_openbox():
            status_cb(f"Using {count} virtual desktop{'s' if count != 1 else ''}.")
        else:
            status_cb("Saved desktop count; sign out and back in if desks do not update.")

    root.pack_start(
        settings_section(
            "",
            settings_row("Virtual desktops", "How many desks Openbox exposes", trailing=combo),
        ),
        False,
        False,
        0,
    )

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)
    tip = label("Ctrl+Win+1–4 still switch desks; unused numbers are ignored when count is lower.", "fos-small", "fos-muted")
    tip.set_line_wrap(True)
    root.pack_start(tip, False, False, 0)
    return root


def build_nightlight(status_cb) -> Gtk.Box:
    from .nightlight import apply_night_light, load_night_light, save_night_light

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(
        pack_header("Night light", "Warmer display colours in the evening."),
        False,
        False,
        0,
    )

    prefs = load_night_light()
    try:
        temperature = int(prefs.get("temperature", "4500"))
    except ValueError:
        temperature = 4500
    temperature = max(1000, min(6500, temperature))
    try:
        start_hour = int(prefs.get("start_hour", "20"))
    except ValueError:
        start_hour = 20
    start_hour = max(0, min(23, start_hour))
    try:
        end_hour = int(prefs.get("end_hour", "7"))
    except ValueError:
        end_hour = 7
    end_hour = max(0, min(23, end_hour))

    enable_sw = Gtk.Switch()
    enable_sw.set_active(truthy(prefs.get("enabled"), False))

    temp_scale = add_classes(
        Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1000, 6500, 100),
        "fos-scale",
    )
    temp_scale.set_value(temperature)
    temp_scale.set_hexpand(True)
    temp_scale.set_draw_value(True)
    temp_scale.connect("format-value", lambda _s, v: f"{int(v)} K")

    schedule_sw = Gtk.Switch()
    schedule_sw.set_active(truthy(prefs.get("schedule"), False))

    start_spin = Gtk.SpinButton.new_with_range(0, 23, 1)
    start_spin.set_value(start_hour)
    end_spin = Gtk.SpinButton.new_with_range(0, 23, 1)
    end_spin.set_value(end_hour)

    def sync_schedule_sensitivity() -> None:
        active = schedule_sw.get_active()
        start_spin.set_sensitive(active)
        end_spin.set_sensitive(active)

    schedule_sw.connect("toggled", lambda _sw: sync_schedule_sensitivity())
    sync_schedule_sensitivity()

    def collect() -> dict[str, str]:
        return {
            "enabled": "1" if enable_sw.get_active() else "0",
            "temperature": str(int(temp_scale.get_value())),
            "schedule": "1" if schedule_sw.get_active() else "0",
            "start_hour": str(int(start_spin.get_value())),
            "end_hour": str(int(end_spin.get_value())),
        }

    def apply(_button=None) -> None:
        save_night_light(collect())
        if apply_night_light():
            status_cb("Night light applied.")
        else:
            status_cb("Saved preferences but could not adjust display gamma (is xrandr available?).")

    def on_temp_live(_scale: Gtk.Scale) -> None:
        if not enable_sw.get_active():
            return
        values = collect()
        save_night_light(values)
        apply_night_light()

    temp_scale.connect("value-changed", on_temp_live)

    root.pack_start(
        settings_section(
            "",
            settings_row("Night light", "Tint the screen warmer at night", trailing=enable_sw),
            settings_row(
                "Colour temperature",
                "Lower is warmer (1000–6500 K)",
                trailing=temp_scale,
            ),
            settings_row("Use schedule", "Only apply between chosen hours", trailing=schedule_sw),
            settings_row("Start hour", "When night light turns on (0–23)", trailing=start_spin),
            settings_row("End hour", "When night light turns off (0–23)", trailing=end_spin),
        ),
        False,
        False,
        0,
    )

    apply_btn = button("Apply", variant="default")
    apply_btn.connect("clicked", apply)
    root.pack_start(apply_btn, False, False, 0)

    tip = label(
        "Uses xrandr gamma on connected displays. Schedule spans midnight when start is after end.",
        "fos-small",
        "fos-muted",
    )
    tip.set_line_wrap(True)
    root.pack_start(tip, False, False, 0)
    return root


def build_bluetooth_full(status_cb) -> Gtk.Box:
    from .indicators import BluetoothPicker, bluetooth_available

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.pack_start(pack_header("Bluetooth", "Pair and connect devices."), False, False, 0)

    if not bluetooth_available():
        root.pack_start(
            label("bluetoothctl is not available on this system.", "fos-text", "fos-muted"),
            False,
            False,
            0,
        )
        return root

    card = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0), "fos-card")
    body = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0), "fos-card-content")
    card.pack_start(body, True, True, 0)

    def on_changed() -> None:
        status_cb("Bluetooth updated.")

    picker = BluetoothPicker(on_changed=on_changed, show_switch=True)
    body.pack_start(picker, False, False, 0)
    root.pack_start(card, False, False, 0)
    picker.refresh()

    tip = label(
        "Click a device to connect or disconnect. Use Scan to discover new hardware.",
        "fos-small",
        "fos-muted",
    )
    tip.set_line_wrap(True)
    root.pack_start(tip, False, False, 0)
    return root


def restore_session_accessibility() -> None:
    """Re-apply sticky/slow keys and xsettings font from saved prefs."""
    from .settings_pages import current_layout

    appearance = load_kv("appearance", {})
    access = load_kv("accessibility", {"sticky_keys": "0", "slow_keys": "0"})
    try:
        font_size = int(appearance.get("font_size", str(DEFAULT_FONT_SIZE)))
    except ValueError:
        font_size = DEFAULT_FONT_SIZE
    try:
        cursor_size = int(appearance.get("cursor_size", "24"))
    except ValueError:
        cursor_size = 24
    if appearance:
        write_xsettings(font_size=font_size, cursor_size=cursor_size)
    options: list[str] = []
    if truthy(access.get("sticky_keys"), False):
        options.append("stickykeys")
    if truthy(access.get("slow_keys"), False):
        options.append("slowkeys")
    if options:
        layout = current_layout()
        subprocess.run(
            ["setxkbmap", "-layout", layout, "-option", ",".join(options)],
            check=False,
        )


__all__ = [
    "build_accessibility",
    "build_accounts",
    "build_appearance",
    "build_bluetooth_full",
    "build_datetime",
    "build_firewall",
    "build_installed_apps",
    "build_multitasking",
    "build_nightlight",
    "build_privacy",
    "build_shortcuts",
    "build_ssh",
    "build_startup",
    "restore_session_accessibility",
    "write_xsettings",
]