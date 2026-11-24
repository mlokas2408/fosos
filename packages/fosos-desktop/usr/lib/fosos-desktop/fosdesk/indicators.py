"""Volume, network, battery, brightness and clock: panel status and their popups."""

import re
import shutil
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk

from . import apps as appmod
from .popup import Popup
from .ui import FosDialog, add_classes, button, clear, icon, label

SINK = "@DEFAULT_AUDIO_SINK@"
POWER_SUPPLY = Path("/sys/class/power_supply")
BACKLIGHT = Path("/sys/class/backlight")
VOLUME_CHANGE_SOUND = Path("/usr/share/sounds/freedesktop/stereo/audio-volume-change.oga")
_volume_sound_timer: int | None = None


def run(argv: list[str], timeout: float = 2.0) -> str | None:
    if shutil.which(argv[0]) is None:
        return None
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def run_ok(argv: list[str], timeout: float = 2.0) -> bool:
    """Like run(), but success is returncode 0 (stdout may be empty)."""
    if shutil.which(argv[0]) is None:
        return False
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def run_async(argv: list[str], done=None) -> None:
    """Run without blocking the shell. `done(ok, output)` runs on completion."""
    if shutil.which(argv[0]) is None:
        if done:
            done(False, f"{argv[0]} is not installed.")
        return
    proc = Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE)

    def finished(process, result):
        try:
            _ok, stdout, _stderr = process.communicate_utf8_finish(result)
        except GLib.Error as error:
            stdout = error.message
        if done:
            done(process.get_successful(), stdout or "")

    proc.communicate_utf8_async(None, None, finished)


def play_volume_feedback() -> None:
    """Play the freedesktop volume-change click (Windows-like OSD ding)."""
    if not VOLUME_CHANGE_SOUND.is_file():
        return
    path = str(VOLUME_CHANGE_SOUND)
    if shutil.which("pw-play"):
        run_async(["pw-play", path])
    elif shutil.which("paplay"):
        run_async(["paplay", path])


def schedule_volume_feedback(delay_ms: int = 120) -> None:
    """Debounce feedback so slider drags play one click after the last change."""
    global _volume_sound_timer
    if _volume_sound_timer is not None:
        GLib.source_remove(_volume_sound_timer)
        _volume_sound_timer = None

    def _fire() -> bool:
        global _volume_sound_timer
        _volume_sound_timer = None
        play_volume_feedback()
        return False

    _volume_sound_timer = GLib.timeout_add(delay_ms, _fire)


def set_volume(level: int, *, feedback: bool = True) -> bool:
    """Set default sink volume 0–100%. wpctl global options must precede the command."""
    level = max(0, min(100, int(level)))
    # WirePlumber: `wpctl [OPTION] set-volume ID VOL` — `-l` before the verb.
    ok = run_ok(["wpctl", "-l", "1.0", "set-volume", SINK, f"{level}%"])
    if not ok:
        ok = run_ok(["wpctl", "set-volume", SINK, f"{level}%"])
    if not ok:
        return False
    # Windows-like: moving the slider unmutes so the new level is audible.
    run_ok(["wpctl", "set-mute", SINK, "0"])
    if feedback and level > 0:
        schedule_volume_feedback()
    return True


def toggle_mute(*, feedback: bool = True) -> bool:
    before = read_volume()
    if not run_ok(["wpctl", "set-mute", SINK, "toggle"]):
        return False
    # Click when unmuting so silence → sound is obvious.
    if feedback and before is not None and before[1]:
        schedule_volume_feedback()
    return True


def popup_header(title: str) -> Gtk.Box:
    header = add_classes(Gtk.Box(spacing=8), "fos-card-header")
    header.pack_start(label(title, "fos-title"), True, True, 0)
    return header


# Volume


def read_volume() -> tuple[int, bool] | None:
    output = run(["wpctl", "get-volume", SINK])
    if not output:
        return None
    match = re.search(r"Volume:\s*([0-9.]+)", output)
    if not match:
        return None
    return round(float(match.group(1)) * 100), "[MUTED]" in output


def volume_icon(level: int, muted: bool) -> str:
    if muted or level == 0:
        return "audio-volume-muted-symbolic"
    if level < 34:
        return "audio-volume-low-symbolic"
    if level < 67:
        return "audio-volume-medium-symbolic"
    return "audio-volume-high-symbolic"


class VolumePopup(Popup):
    def __init__(self, shell) -> None:
        super().__init__(width=360)
        self.shell = shell
        self._updating = False
        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)
        frame.pack_start(popup_header("Sound"), False, False, 0)
        body = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "fos-card-content")
        frame.pack_start(body, True, True, 0)
        row = Gtk.Box(spacing=8)
        self.mute = button(icon_name="audio-volume-high-symbolic", size="icon-sm", tooltip="Mute")
        self.mute.connect("clicked", lambda _b: self._toggle_mute())
        row.pack_start(self.mute, False, False, 0)
        self.scale = add_classes(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1), "fos-scale")
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        self.scale.connect("value-changed", self._on_value)
        row.pack_start(self.scale, True, True, 0)
        self.percent = label("", "fos-text", "fos-muted", xalign=1.0)
        self.percent.set_width_chars(4)
        row.pack_start(self.percent, False, False, 0)
        body.pack_start(row, False, False, 0)
        self.status = label("", "fos-small", "fos-muted")
        body.pack_start(self.status, False, False, 0)
        footer = add_classes(Gtk.Box(), "fos-card-footer")
        settings = button("Sound settings", variant="ghost", size="sm")
        settings.connect("clicked", lambda _b: self._open_settings())
        footer.pack_start(settings, False, False, 0)
        frame.pack_start(footer, False, False, 0)

    def refresh(self) -> None:
        state = read_volume()
        self._updating = True
        if state is None:
            self.scale.set_sensitive(False)
            self.mute.set_sensitive(False)
            self.percent.set_text("")
            self.status.set_text("Sound is not available.")
        else:
            level, muted = state
            self.scale.set_sensitive(True)
            self.mute.set_sensitive(True)
            self.scale.set_value(min(level, 100))
            self.percent.set_text(f"{level}%")
            self.status.set_text("Muted" if muted else "Output: default device")
            self.mute.get_child().set_from_icon_name(volume_icon(level, muted), Gtk.IconSize.MENU)
        self._updating = False
        self.shell.update_status()

    def _on_value(self, scale: Gtk.Scale) -> None:
        if self._updating:
            return
        level = int(scale.get_value())
        self.percent.set_text(f"{level}%")
        if not set_volume(level):
            self.status.set_text("Could not change volume.")
        else:
            self.status.set_text("Output: default device")
            child = self.mute.get_child()
            if isinstance(child, Gtk.Image):
                child.set_from_icon_name(volume_icon(level, False), Gtk.IconSize.MENU)
        self.shell.update_status()

    def _toggle_mute(self) -> None:
        if not toggle_mute():
            self.status.set_text("Could not toggle mute.")
        self.refresh()

    def _open_settings(self) -> None:
        self.dismiss()
        appmod.spawn(["pavucontrol"])


# Network


def split_terse(line: str) -> list[str]:
    fields = re.split(r"(?<!\\):", line)
    return [field.replace("\\:", ":").replace("\\\\", "\\") for field in fields]


def network_state() -> tuple[str, str]:
    """Return (icon, description) for the current connection."""
    output = run(["nmcli", "-t", "-f", "TYPE,STATE,CONNECTION", "device"])
    if output is None:
        return "network-offline-symbolic", "Network status is unavailable"
    for kind in ("ethernet", "wifi"):
        for line in output.splitlines():
            fields = split_terse(line)
            if len(fields) < 2 or fields[0] != kind:
                continue
            # nmcli may report "connected (externally)" etc.
            if not fields[1].startswith("connected"):
                continue
            name = fields[2] if len(fields) >= 3 and fields[2] else kind
            if kind == "wifi":
                return "network-wireless-symbolic", f"Connected to {name}"
            return "network-wired-symbolic", "Connected by cable"
    return "network-offline-symbolic", "Not connected"


def parse_wifi_list(output: str | None, *, limit: int = 12) -> list[dict]:
    """Parse nmcli terse Wi-Fi list output into unique SSIDs sorted by signal."""
    if not output:
        return []
    networks: dict[str, dict] = {}
    for line in output.splitlines():
        fields = split_terse(line)
        if len(fields) < 4 or not fields[1]:
            continue
        ssid = fields[1]
        security = fields[3]
        entry = {
            "ssid": ssid,
            "active": fields[0] == "*",
            "signal": int(fields[2]) if fields[2].isdigit() else 0,
            "secure": security not in ("", "--"),
            "security": security,
        }
        known = networks.get(ssid)
        if known is None or entry["active"] or entry["signal"] > known["signal"]:
            networks[ssid] = entry
    return sorted(networks.values(), key=lambda n: (not n["active"], -n["signal"]))[:limit]


def _wifi_list_argv(*, rescan: bool = False) -> list[str]:
    mode = "yes" if rescan else "no"
    return ["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", mode]


def wifi_networks(*, rescan: bool = False, limit: int = 12) -> list[dict]:
    """List nearby Wi-Fi networks (blocking). Prefer wifi_networks_async in the UI."""
    # Rescan can take a few seconds on real hardware — avoid calling with
    # rescan=True on the GTK main thread.
    output = run(_wifi_list_argv(rescan=rescan), timeout=12.0 if rescan else 2.0)
    return parse_wifi_list(output, limit=limit)


def wifi_networks_async(*, rescan: bool = False, limit: int = 12, done=None) -> None:
    """List nearby Wi-Fi networks without blocking the shell."""

    def finished(ok: bool, output: str) -> None:
        networks = parse_wifi_list(output if ok else None, limit=limit)
        if done:
            done(networks)

    run_async(_wifi_list_argv(rescan=rescan), finished)


def wifi_enabled() -> bool | None:
    output = run(["nmcli", "radio", "wifi"])
    if output is None:
        return None
    return output.strip() == "enabled"


def wifi_ask_password(parent: Gtk.Widget | None, ssid: str) -> str | None:
    """Password prompt for a secured SSID. Returns None if cancelled.

    Uses FosDialog (nested main loop) and holds the parent Popup's seat grab
    so the network flyout is not dismissed mid-prompt.
    """
    toplevel: Gtk.Window | None = None
    popup: Popup | None = None
    if parent is not None:
        top = parent.get_toplevel()
        if isinstance(top, Popup):
            popup = top
            toplevel = top
        elif isinstance(top, Gtk.Window):
            toplevel = top

    if popup is not None:
        popup._hold_grab = True

    try:
        dialog = FosDialog(toplevel, title=f"Connect to {ssid}", width=360)
        dialog.add_body_text(f"Password for “{ssid}”")
        entry = add_classes(Gtk.Entry(), "fos-input")
        entry.set_visibility(False)
        entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        entry.set_activates_default(True)
        dialog.content.pack_start(entry, False, False, 0)
        result: dict[str, str | None] = {"password": None}

        def accept(_widget=None) -> None:
            result["password"] = entry.get_text()
            dialog.respond(True)

        dialog.add_action("Cancel", None, variant="ghost")
        connect_btn = button("Connect", variant="default", size="sm")
        connect_btn.set_can_focus(True)
        connect_btn.set_can_default(True)
        connect_btn.connect("clicked", accept)
        dialog.footer.pack_start(connect_btn, False, False, 0)
        entry.connect("activate", accept)
        GLib.idle_add(entry.grab_focus)
        if dialog.run() is not True:
            return None
        return result["password"]
    finally:
        if popup is not None:
            popup._hold_grab = False
            if popup.get_visible():
                GLib.idle_add(popup._grab)


def wifi_connect(ssid: str, *, secure: bool = False, parent: Gtk.Widget | None = None, done=None) -> None:
    """Connect to SSID; prompt for password when the network looks secured."""
    argv = ["nmcli", "device", "wifi", "connect", ssid]
    if secure:
        password = wifi_ask_password(parent, ssid)
        if password is None:
            if done:
                done(False, "Cancelled.")
            return
        if password:
            argv.extend(["password", password])
    run_async(argv, done)


class WifiPicker(Gtk.Box):
    """Reusable Wi-Fi radio switch + scanned network list (popup and Settings)."""

    def __init__(self, *, on_changed=None, show_switch: bool = True) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.on_changed = on_changed
        self._updating = False
        self._parent_for_dialogs = self
        self._list_gen = 0

        if show_switch:
            switch_row = Gtk.Box(spacing=10)
            switch_row.pack_start(label("Wi-Fi", "fos-text", "fos-strong"), True, True, 0)
            self.wifi_switch = add_classes(Gtk.Switch(), "fos-switch")
            self.wifi_switch.set_valign(Gtk.Align.CENTER)
            self.wifi_switch.connect("state-set", self._on_wifi_toggled)
            switch_row.pack_end(self.wifi_switch, False, False, 0)
            self.pack_start(switch_row, False, False, 0)
        else:
            self.wifi_switch = None

        self.status = label("", "fos-text", "fos-strong")
        self.pack_start(self.status, False, False, 0)
        self.message = label("", "fos-small", "fos-muted")
        self.message.set_line_wrap(True)
        self.message.set_no_show_all(True)
        self.pack_start(self.message, False, False, 0)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.pack_start(self.list, False, False, 0)
        actions = Gtk.Box(spacing=8)
        refresh_btn = button("Refresh", variant="outline", size="sm")
        refresh_btn.connect("clicked", lambda _b: self.refresh(rescan=True))
        actions.pack_start(refresh_btn, False, False, 0)
        self.pack_start(actions, False, False, 0)

    def set_dialog_parent(self, widget: Gtk.Widget) -> None:
        self._parent_for_dialogs = widget

    def refresh(self, *, rescan: bool = False) -> None:
        """Update radio state immediately; load the SSID list asynchronously."""
        _icon, text = network_state()
        self.status.set_text(text)
        enabled = wifi_enabled()
        if self.wifi_switch is not None:
            self._updating = True
            self.wifi_switch.set_sensitive(enabled is not None)
            self.wifi_switch.set_active(bool(enabled))
            self._updating = False

        self._list_gen += 1
        gen = self._list_gen

        if enabled is None:
            clear(self.list)
            self.list.pack_start(
                label("Wi-Fi is not available (NetworkManager / nmcli).", "fos-small", "fos-muted"),
                False,
                False,
                0,
            )
            self.list.show_all()
            if self.on_changed:
                self.on_changed()
            return

        if not enabled:
            clear(self.list)
            self.list.pack_start(label("Wi-Fi is off.", "fos-small", "fos-muted"), False, False, 0)
            self.list.show_all()
            if self.on_changed:
                self.on_changed()
            return

        # Keep status messages like "Connecting…" visible during a background scan.
        scanning_note = False
        if rescan:
            existing = self.message.get_text() if self.message.get_visible() else ""
            if not existing or existing == "Scanning…":
                self._show_message("Scanning…")
                scanning_note = True
        elif not self.list.get_children():
            self.list.pack_start(
                label("Looking for networks…", "fos-small", "fos-muted"),
                False,
                False,
                0,
            )
            self.list.show_all()

        def apply_networks(networks: list[dict]) -> bool:
            if gen != self._list_gen:
                return False
            clear(self.list)
            if not networks:
                self.list.pack_start(
                    label("No Wi-Fi networks found. Try Refresh.", "fos-small", "fos-muted"),
                    False,
                    False,
                    0,
                )
            for network in networks:
                self.list.pack_start(self._network_row(network), False, False, 0)
            self.list.show_all()
            if scanning_note and self.message.get_text() == "Scanning…":
                self.message.hide()
            if self.on_changed:
                self.on_changed()
            return False

        wifi_networks_async(
            rescan=rescan,
            done=lambda networks: GLib.idle_add(apply_networks, networks),
        )

    def _network_row(self, network: dict) -> Gtk.Button:
        widget = button(variant="secondary" if network["active"] else "ghost")
        add_classes(widget, "row")
        row = Gtk.Box(spacing=10)
        strength = "good" if network["signal"] >= 60 else "ok" if network["signal"] >= 35 else "weak"
        row.pack_start(icon(f"network-wireless-signal-{strength}-symbolic", 16), False, False, 0)
        row.pack_start(label(network["ssid"], "fos-text", ellipsize=True), True, True, 0)
        if network["active"]:
            row.pack_end(label("Connected", "fos-small", "fos-muted"), False, False, 0)
        if network["secure"]:
            row.pack_end(icon("network-wireless-encrypted-symbolic", 12), False, False, 0)
        widget.add(row)
        if not network["active"]:
            widget.connect("clicked", lambda _b, n=network: self._connect(n))
        return widget

    def _connect(self, network: dict) -> None:
        ssid = network["ssid"]
        self._show_message(f"Connecting to {ssid}…")

        def done(ok: bool, output: str) -> None:
            def apply() -> bool:
                if ok:
                    self._show_message(f"Connected to {ssid}.")
                else:
                    detail = output.strip().splitlines()[-1] if output.strip() else "The connection failed."
                    self._show_message(detail)
                self.refresh(rescan=False)
                return False

            GLib.idle_add(apply)

        wifi_connect(
            ssid,
            secure=bool(network.get("secure")),
            parent=self._parent_for_dialogs,
            done=done,
        )

    def _show_message(self, text: str) -> None:
        self.message.set_text(text)
        self.message.show()

    def _on_wifi_toggled(self, _switch, state: bool) -> bool:
        if self._updating:
            return False

        def after(_ok: bool, _out: str) -> None:
            def run() -> bool:
                self.refresh(rescan=bool(state))
                return False

            GLib.idle_add(run)

        run_async(["nmcli", "radio", "wifi", "on" if state else "off"], after)
        return False


def bluetooth_available() -> bool:
    return shutil.which("bluetoothctl") is not None


def bluetooth_powered() -> bool | None:
    if not bluetooth_available():
        return None
    output = run(["bluetoothctl", "show"])
    if output is None:
        return None
    for line in output.splitlines():
        if line.strip().startswith("Powered:"):
            return line.strip().endswith("yes")
    return False


class NetworkPopup(Popup):
    """Network + Bluetooth flyout (taskbar network icon)."""

    def __init__(self, shell) -> None:
        super().__init__(width=360)
        self.shell = shell
        self._bt_updating = False
        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)
        frame.pack_start(popup_header("Network & Bluetooth"), False, False, 0)
        body = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14), "fos-card-content")
        frame.pack_start(body, True, True, 0)
        self.picker = WifiPicker(on_changed=self._on_picker_changed, show_switch=True)
        self.picker.set_dialog_parent(self)
        body.pack_start(self.picker, False, False, 0)

        self.bt_block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.bt_block.set_no_show_all(True)
        bt_row = Gtk.Box(spacing=10)
        bt_row.pack_start(label("Bluetooth", "fos-text", "fos-strong"), True, True, 0)
        self.bt_switch = add_classes(Gtk.Switch(), "fos-switch")
        self.bt_switch.set_valign(Gtk.Align.CENTER)
        self.bt_switch.connect("state-set", self._on_bt_toggled)
        bt_row.pack_end(self.bt_switch, False, False, 0)
        self.bt_block.pack_start(bt_row, False, False, 0)
        self.bt_status = label("", "fos-small", "fos-muted")
        self.bt_status.set_line_wrap(True)
        self.bt_block.pack_start(self.bt_status, False, False, 0)
        body.pack_start(self.bt_block, False, False, 0)

        footer = add_classes(Gtk.Box(spacing=8), "fos-card-footer")
        net_settings = button("Network…", variant="ghost", size="sm")
        net_settings.connect("clicked", lambda _b: self._open_network_settings())
        footer.pack_start(net_settings, False, False, 0)
        self.bt_settings = button("Bluetooth…", variant="ghost", size="sm")
        self.bt_settings.connect("clicked", lambda _b: self._open_bluetooth_settings())
        footer.pack_end(self.bt_settings, False, False, 0)
        frame.pack_start(footer, False, False, 0)

    def refresh(self) -> None:
        # Cached list first (non-blocking). Soft-rescan after the flyout is up
        # so opening the taskbar icon never stalls the desktop.
        self.picker.refresh(rescan=False)
        avail = bluetooth_available()
        self.bt_block.set_visible(avail)
        self.bt_settings.set_visible(avail)
        if avail:
            powered = bluetooth_powered()
            self._bt_updating = True
            self.bt_switch.set_sensitive(powered is not None)
            if powered is not None:
                self.bt_switch.set_active(powered)
                self.bt_status.set_text("On — pair devices in Bluetooth settings" if powered else "Off")
            else:
                self.bt_switch.set_active(False)
                self.bt_status.set_text("Bluetooth status unavailable")
            self._bt_updating = False
            self.bt_block.show_all()
        self.relayout()
        GLib.timeout_add(250, self._soft_rescan)

    def _soft_rescan(self) -> bool:
        if self.get_visible():
            self.picker.refresh(rescan=True)
        return False

    def _on_picker_changed(self) -> None:
        self.shell.update_status()
        self.relayout()

    def _on_bt_toggled(self, switch: Gtk.Switch, state: bool) -> bool:
        if self._bt_updating:
            return False
        run_async(
            ["bluetoothctl", "power", "on" if state else "off"],
            lambda _ok, _out: GLib.idle_add(self.refresh),
        )
        return False

    def _open_network_settings(self) -> None:
        self.dismiss()
        self.shell.open_settings("network")

    def _open_bluetooth_settings(self) -> None:
        self.dismiss()
        if shutil.which("blueman-manager"):
            appmod.spawn(["blueman-manager"])
        else:
            self.shell.open_settings("bluetooth")


# Clock


class ClockPopup(Popup):
    def __init__(self, shell) -> None:
        super().__init__(width=280)
        self.shell = shell
        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)
        header = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2), "fos-card-header")
        self.day = label("", "fos-text", "fos-muted")
        self.date = label("", "fos-title")
        header.pack_start(self.day, False, False, 0)
        header.pack_start(self.date, False, False, 0)
        frame.pack_start(header, False, False, 0)
        body = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card-content")
        self.calendar = add_classes(Gtk.Calendar(), "fos-calendar")
        body.pack_start(self.calendar, False, False, 0)
        frame.pack_start(body, True, True, 0)

    def refresh(self) -> None:
        from .region import format_date_full, format_weekday

        now = GLib.DateTime.new_now_local()
        self.day.set_text(format_weekday())
        self.date.set_text(format_date_full())
        self.calendar.select_month(now.get_month() - 1, now.get_year())
        self.calendar.select_day(now.get_day_of_month())


# Battery


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def battery_present() -> bool:
    if not POWER_SUPPLY.is_dir():
        return False
    for path in POWER_SUPPLY.iterdir():
        if _read_text(path / "type") == "Battery":
            return True
    return False


def battery_state() -> tuple[str, str, int] | None:
    """Return (icon, tooltip, capacity%) for the first battery, or None if none."""
    if not POWER_SUPPLY.is_dir():
        return None
    for path in sorted(POWER_SUPPLY.iterdir()):
        if _read_text(path / "type") != "Battery":
            continue
        status = (_read_text(path / "status") or "Unknown").lower()
        capacity = _read_int(path / "capacity")
        if capacity is None:
            now = _read_int(path / "energy_now") or _read_int(path / "charge_now")
            full = _read_int(path / "energy_full") or _read_int(path / "charge_full")
            if now is not None and full:
                capacity = max(0, min(100, round(100 * now / full)))
        if capacity is None:
            continue
        charging = status in ("charging", "full")
        if capacity >= 90:
            icon_name = "battery-full-charging-symbolic" if charging else "battery-full-symbolic"
        elif capacity >= 70:
            icon_name = "battery-good-charging-symbolic" if charging else "battery-good-symbolic"
        elif capacity >= 40:
            icon_name = "battery-low-charging-symbolic" if charging else "battery-low-symbolic"
        elif capacity >= 15:
            icon_name = "battery-caution-charging-symbolic" if charging else "battery-caution-symbolic"
        else:
            icon_name = "battery-empty-charging-symbolic" if charging else "battery-empty-symbolic"
        if status == "charging":
            tip = f"Charging · {capacity}%"
        elif status == "full":
            tip = f"Full · {capacity}%"
        elif status == "discharging":
            tip = f"Battery · {capacity}%"
        else:
            tip = f"Battery · {capacity}%"
        return icon_name, tip, int(capacity)
    return None


class BatteryPopup(Popup):
    def __init__(self, shell) -> None:
        super().__init__(width=360)
        self.shell = shell
        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)
        frame.pack_start(popup_header("Battery"), False, False, 0)
        body = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), "fos-card-content")
        frame.pack_start(body, True, True, 0)
        self.status = label("", "fos-text", "fos-strong")
        body.pack_start(self.status, False, False, 0)
        self.detail = label("", "fos-small", "fos-muted")
        self.detail.set_line_wrap(True)
        body.pack_start(self.detail, False, False, 0)
        footer = add_classes(Gtk.Box(), "fos-card-footer")
        settings = button("Power settings", variant="ghost", size="sm")
        settings.connect("clicked", lambda _b: self._open_settings())
        footer.pack_start(settings, False, False, 0)
        frame.pack_start(footer, False, False, 0)

    def refresh(self) -> None:
        state = battery_state()
        if state is None:
            self.status.set_text("No battery")
            self.detail.set_text("This machine has no battery, or it is not reported.")
        else:
            _icon, tip, _capacity = state
            self.status.set_text(tip)
            self.detail.set_text("Screen blank and suspend are under Power settings.")
        self.shell.update_status()

    def _open_settings(self) -> None:
        self.dismiss()
        self.shell.open_settings("power")


# Brightness


def backlight_device() -> Path | None:
    if not BACKLIGHT.is_dir():
        return None
    devices = sorted(p for p in BACKLIGHT.iterdir() if (p / "brightness").is_file())
    return devices[0] if devices else None


def brightness_available() -> bool:
    return backlight_device() is not None or shutil.which("brightnessctl") is not None


def _parse_brightnessctl_percent(output: str) -> int | None:
    """Parse `brightnessctl -m info`. Debian 0.5.x is device,class,current,percent,max."""
    fields = output.strip().split(",")
    # Prefer the field that ends with '%'.
    for field in fields:
        if field.endswith("%"):
            raw = field[:-1]
            if raw.isdigit():
                return max(0, min(100, int(raw)))
    # Legacy 6-field layout: …,current,percent,max
    if len(fields) >= 6:
        percent = fields[4].rstrip("%")
        if percent.isdigit():
            return max(0, min(100, int(percent)))
    return None


def read_brightness() -> int | None:
    """Return brightness as 0–100, or None if unavailable."""
    # Prefer sysfs when present — reliable percent without CLI format drift.
    device = backlight_device()
    if device is not None:
        current = _read_int(device / "brightness")
        maximum = _read_int(device / "max_brightness")
        if current is not None and maximum:
            return max(0, min(100, round(100 * current / maximum)))
    if shutil.which("brightnessctl"):
        output = run(["brightnessctl", "-m", "info"])
        if output:
            parsed = _parse_brightnessctl_percent(output)
            if parsed is not None:
                return parsed
    return None


def set_brightness(percent: int) -> bool:
    percent = max(1, min(100, int(percent)))
    if shutil.which("brightnessctl") and run_ok(["brightnessctl", "set", f"{percent}%"]):
        return True
    device = backlight_device()
    if device is None:
        return False
    maximum = _read_int(device / "max_brightness")
    if not maximum:
        return False
    value = max(1, min(maximum, round(maximum * percent / 100)))
    try:
        (device / "brightness").write_text(str(value), encoding="utf-8")
        return True
    except OSError:
        return False


def brightness_icon(_level: int) -> str:
    return "display-brightness-symbolic"


class BrightnessPopup(Popup):
    def __init__(self, shell) -> None:
        super().__init__(width=360)
        self.shell = shell
        self._updating = False
        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)
        frame.pack_start(popup_header("Brightness"), False, False, 0)
        body = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "fos-card-content")
        frame.pack_start(body, True, True, 0)
        row = Gtk.Box(spacing=8)
        self.icon_button = button(icon_name="display-brightness-symbolic", size="icon-sm", tooltip="Brightness")
        row.pack_start(self.icon_button, False, False, 0)
        self.scale = add_classes(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1), "fos-scale")
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        self.scale.connect("value-changed", self._on_value)
        row.pack_start(self.scale, True, True, 0)
        self.percent = label("", "fos-text", "fos-muted", xalign=1.0)
        self.percent.set_width_chars(4)
        row.pack_start(self.percent, False, False, 0)
        body.pack_start(row, False, False, 0)
        self.status = label("", "fos-small", "fos-muted")
        body.pack_start(self.status, False, False, 0)
        footer = add_classes(Gtk.Box(), "fos-card-footer")
        settings = button("Display settings", variant="ghost", size="sm")
        settings.connect("clicked", lambda _b: self._open_settings())
        footer.pack_start(settings, False, False, 0)
        frame.pack_start(footer, False, False, 0)

    def refresh(self) -> None:
        level = read_brightness()
        self._updating = True
        if level is None:
            self.scale.set_sensitive(False)
            self.percent.set_text("")
            self.status.set_text("Brightness control is not available.")
        else:
            self.scale.set_sensitive(True)
            self.scale.set_value(level)
            self.percent.set_text(f"{level}%")
            self.status.set_text("Built-in display")
            self.icon_button.get_child().set_from_icon_name(brightness_icon(level), Gtk.IconSize.MENU)
        self._updating = False
        self.shell.update_status()

    def _on_value(self, scale: Gtk.Scale) -> None:
        if self._updating:
            return
        level = int(scale.get_value())
        self.percent.set_text(f"{level}%")
        if not set_brightness(level):
            self.status.set_text("Could not change brightness.")
        child = self.icon_button.get_child()
        if isinstance(child, Gtk.Image):
            child.set_from_icon_name(brightness_icon(level), Gtk.IconSize.MENU)
        self.shell.update_status()

    def _open_settings(self) -> None:
        self.dismiss()
        self.shell.open_settings("display")
