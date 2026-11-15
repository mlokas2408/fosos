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
from .ui import add_classes, button, clear, icon, label

SINK = "@DEFAULT_AUDIO_SINK@"
POWER_SUPPLY = Path("/sys/class/power_supply")
BACKLIGHT = Path("/sys/class/backlight")


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
        super().__init__(width=300)
        self.shell = shell
        self._updating = False
        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)
        frame.pack_start(popup_header("Volume"), False, False, 0)
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
        run(["wpctl", "set-volume", "-l", "1.0", SINK, f"{level / 100:.2f}"])
        self.shell.update_status()

    def _toggle_mute(self) -> None:
        run(["wpctl", "set-mute", SINK, "toggle"])
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
            if len(fields) >= 3 and fields[0] == kind and fields[1] == "connected":
                if kind == "wifi":
                    return "network-wireless-symbolic", f"Connected to {fields[2]}"
                return "network-wired-symbolic", "Connected by cable"
    return "network-offline-symbolic", "Not connected"


def wifi_networks() -> list[dict]:
    output = run(["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "no"])
    if not output:
        return []
    networks: dict[str, dict] = {}
    for line in output.splitlines():
        fields = split_terse(line)
        if len(fields) < 4 or not fields[1]:
            continue
        ssid = fields[1]
        entry = {
            "ssid": ssid,
            "active": fields[0] == "*",
            "signal": int(fields[2]) if fields[2].isdigit() else 0,
            "secure": fields[3] not in ("", "--"),
        }
        known = networks.get(ssid)
        if known is None or entry["active"] or entry["signal"] > known["signal"]:
            networks[ssid] = entry
    return sorted(networks.values(), key=lambda n: (not n["active"], -n["signal"]))[:8]


def wifi_enabled() -> bool | None:
    output = run(["nmcli", "radio", "wifi"])
    if output is None:
        return None
    return output.strip() == "enabled"


class NetworkPopup(Popup):
    def __init__(self, shell) -> None:
        super().__init__(width=320)
        self.shell = shell
        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)
        header = popup_header("Network")
        self.wifi_switch = add_classes(Gtk.Switch(), "fos-switch")
        self.wifi_switch.set_valign(Gtk.Align.CENTER)
        self.wifi_switch.set_tooltip_text("Wi-Fi")
        self.wifi_switch.connect("state-set", self._on_wifi_toggled)
        header.pack_end(self.wifi_switch, False, False, 0)
        header.pack_end(label("Wi-Fi", "fos-small", "fos-muted"), False, False, 0)
        frame.pack_start(header, False, False, 0)
        body = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10), "fos-card-content")
        frame.pack_start(body, True, True, 0)
        self.status = label("", "fos-text", "fos-strong")
        body.pack_start(self.status, False, False, 0)
        self.message = label("", "fos-small", "fos-muted")
        self.message.set_line_wrap(True)
        self.message.set_no_show_all(True)
        body.pack_start(self.message, False, False, 0)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        body.pack_start(self.list, False, False, 0)
        footer = add_classes(Gtk.Box(), "fos-card-footer")
        settings = button("Network settings", variant="ghost", size="sm")
        settings.connect("clicked", lambda _b: self._open_settings())
        footer.pack_start(settings, False, False, 0)
        frame.pack_start(footer, False, False, 0)
        self._updating = False

    def refresh(self) -> None:
        _icon, text = network_state()
        self.status.set_text(text)
        enabled = wifi_enabled()
        self._updating = True
        self.wifi_switch.set_sensitive(enabled is not None)
        self.wifi_switch.set_active(bool(enabled))
        self._updating = False
        clear(self.list)
        if enabled:
            networks = wifi_networks()
            if not networks:
                self.list.pack_start(label("No Wi-Fi networks found.", "fos-small", "fos-muted"), False, False, 0)
            for network in networks:
                self.list.pack_start(self._network_row(network), False, False, 0)
        self.list.show_all()
        self.shell.update_status()
        self.relayout()

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
            widget.connect("clicked", lambda _b: self._connect(network["ssid"]))
        return widget

    def _connect(self, ssid: str) -> None:
        self._show_message(f"Connecting to {ssid}…")

        def done(ok: bool, output: str) -> None:
            if ok:
                self._show_message(f"Connected to {ssid}.")
            else:
                detail = output.strip().splitlines()[-1] if output.strip() else "The connection failed."
                self._show_message(detail)
            self.refresh()

        run_async(["nmcli", "device", "wifi", "connect", ssid], done)

    def _show_message(self, text: str) -> None:
        self.message.set_text(text)
        self.message.show()
        self.relayout()

    def _on_wifi_toggled(self, _switch, state: bool) -> bool:
        if self._updating:
            return False
        run_async(["nmcli", "radio", "wifi", "on" if state else "off"], lambda _ok, _out: self.refresh())
        return False

    def _open_settings(self) -> None:
        self.dismiss()
        appmod.spawn(["nm-connection-editor"])


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
        now = GLib.DateTime.new_now_local()
        self.day.set_text(now.format("%A"))
        self.date.set_text(now.format("%-d %B %Y"))
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


def battery_state() -> tuple[str, str] | None:
    """Return (icon, tooltip) for the first battery, or None if none."""
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
        return icon_name, tip
    return None


class BatteryPopup(Popup):
    def __init__(self, shell) -> None:
        super().__init__(width=260)
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

    def refresh(self) -> None:
        state = battery_state()
        if state is None:
            self.status.set_text("No battery")
            self.detail.set_text("This machine has no battery, or it is not reported.")
        else:
            _icon, tip = state
            self.status.set_text(tip)
            self.detail.set_text("Power settings follow the system power manager.")
        self.shell.update_status()


# Brightness


def backlight_device() -> Path | None:
    if not BACKLIGHT.is_dir():
        return None
    devices = sorted(p for p in BACKLIGHT.iterdir() if (p / "brightness").is_file())
    return devices[0] if devices else None


def brightness_available() -> bool:
    return backlight_device() is not None or shutil.which("brightnessctl") is not None


def read_brightness() -> int | None:
    """Return brightness as 0–100, or None if unavailable."""
    if shutil.which("brightnessctl"):
        output = run(["brightnessctl", "-m", "info"])
        if output:
            # brightnessctl -m: device,type,class,current,percent,max
            fields = output.strip().split(",")
            if len(fields) >= 5:
                percent = fields[4].rstrip("%")
                if percent.isdigit():
                    return max(0, min(100, int(percent)))
    device = backlight_device()
    if device is None:
        return None
    current = _read_int(device / "brightness")
    maximum = _read_int(device / "max_brightness")
    if current is None or not maximum:
        return None
    return max(0, min(100, round(100 * current / maximum)))


def set_brightness(percent: int) -> None:
    percent = max(1, min(100, int(percent)))
    if shutil.which("brightnessctl"):
        run(["brightnessctl", "set", f"{percent}%"])
        return
    device = backlight_device()
    if device is None:
        return
    maximum = _read_int(device / "max_brightness")
    if not maximum:
        return
    value = max(1, min(maximum, round(maximum * percent / 100)))
    try:
        (device / "brightness").write_text(str(value), encoding="utf-8")
    except OSError:
        pass


def brightness_icon(_level: int) -> str:
    return "display-brightness-symbolic"


class BrightnessPopup(Popup):
    def __init__(self, shell) -> None:
        super().__init__(width=300)
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
        set_brightness(level)
        self.icon_button.get_child().set_from_icon_name(brightness_icon(level), Gtk.IconSize.MENU)
        self.shell.update_status()

    def _open_settings(self) -> None:
        self.dismiss()
        appmod.spawn(["arandr"])
