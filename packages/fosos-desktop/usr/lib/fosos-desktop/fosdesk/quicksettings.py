"""Win+A style Quick Settings: volume, brightness, Wi-Fi, Bluetooth, power."""

from __future__ import annotations

import shutil

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from . import apps as appmod
from .indicators import (
    battery_present,
    battery_state,
    brightness_available,
    brightness_icon,
    network_state,
    popup_header,
    read_brightness,
    read_volume,
    run,
    run_async,
    set_brightness,
    volume_icon,
    wifi_enabled,
)
from .popup import Popup
from .ui import add_classes, button, label, set_class, tile


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


def _focus_assist_on() -> bool:
    from .settings_pages import load_kv, truthy

    prefs = load_kv("notifications", {"dnd": "0"})
    return truthy(prefs.get("dnd"), False)


def _set_focus_assist(enabled: bool) -> None:
    from .settings_pages import load_kv, save_kv

    prefs = load_kv(
        "notifications",
        {"dnd": "0", "toasts": "1", "timeout": "6000", "muted_apps": ""},
    )
    prefs["dnd"] = "1" if enabled else "0"
    save_kv("notifications", prefs)


class QuickSettings(Popup):
    def __init__(self, shell) -> None:
        super().__init__(width=360)
        self.shell = shell
        self._updating = False

        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)
        frame.pack_start(popup_header("Quick settings"), False, False, 0)

        body = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16), "fos-card-content")
        frame.pack_start(body, True, True, 0)

        # 2×2 tile grid: Wi-Fi | Bluetooth / Focus assist | Mute
        self.tiles = Gtk.Grid()
        self.tiles.set_column_homogeneous(True)
        self.tiles.set_row_homogeneous(True)
        self.tiles.set_column_spacing(8)
        self.tiles.set_row_spacing(8)
        body.pack_start(self.tiles, False, False, 0)

        self.wifi_tile = self._toggle_tile("network-wireless-symbolic", "Wi-Fi")
        self.wifi_tile.connect("clicked", lambda _b: self._toggle_wifi())
        self.tiles.attach(self.wifi_tile, 0, 0, 1, 1)

        self.bt_tile = self._toggle_tile("bluetooth-active-symbolic", "Bluetooth")
        self.bt_tile.connect("clicked", lambda _b: self._toggle_bluetooth())
        self.tiles.attach(self.bt_tile, 1, 0, 1, 1)

        self.focus_tile = self._toggle_tile("preferences-system-notifications-symbolic", "Focus assist")
        self.focus_tile.set_tooltip_text("Focus assist — hide toast popups")
        self.focus_tile.connect("clicked", lambda _b: self._toggle_focus())
        self.tiles.attach(self.focus_tile, 0, 1, 1, 1)

        self.mute_tile = self._toggle_tile("audio-volume-high-symbolic", "Mute")
        self.mute_tile.connect("clicked", lambda _b: self._toggle_mute())
        self.tiles.attach(self.mute_tile, 1, 1, 1, 1)

        # Volume
        vol_block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vol_block.pack_start(label("Volume", "fos-small", "fos-muted"), False, False, 0)
        vol_row = Gtk.Box(spacing=8)
        self.vol_icon = button(icon_name="audio-volume-high-symbolic", size="icon-sm", tooltip="Mute")
        self.vol_icon.connect("clicked", lambda _b: self._toggle_mute())
        vol_row.pack_start(self.vol_icon, False, False, 0)
        self.vol_scale = add_classes(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1), "fos-scale")
        self.vol_scale.set_draw_value(False)
        self.vol_scale.set_hexpand(True)
        self.vol_scale.connect("value-changed", self._on_volume)
        vol_row.pack_start(self.vol_scale, True, True, 0)
        self.vol_percent = label("", "fos-text", "fos-muted", xalign=1.0)
        self.vol_percent.set_width_chars(4)
        vol_row.pack_start(self.vol_percent, False, False, 0)
        vol_block.pack_start(vol_row, False, False, 0)
        body.pack_start(vol_block, False, False, 0)

        # Brightness
        self.bright_block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.bright_block.pack_start(label("Brightness", "fos-small", "fos-muted"), False, False, 0)
        bright_row = Gtk.Box(spacing=8)
        self.bright_icon = button(icon_name="display-brightness-symbolic", size="icon-sm", tooltip="Brightness")
        bright_row.pack_start(self.bright_icon, False, False, 0)
        self.bright_scale = add_classes(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1), "fos-scale")
        self.bright_scale.set_draw_value(False)
        self.bright_scale.set_hexpand(True)
        self.bright_scale.connect("value-changed", self._on_brightness)
        bright_row.pack_start(self.bright_scale, True, True, 0)
        self.bright_percent = label("", "fos-text", "fos-muted", xalign=1.0)
        self.bright_percent.set_width_chars(4)
        bright_row.pack_start(self.bright_percent, False, False, 0)
        self.bright_block.pack_start(bright_row, False, False, 0)
        body.pack_start(self.bright_block, False, False, 0)

        self.battery_label = label("", "fos-text")
        self.battery_label.set_line_wrap(True)
        body.pack_start(self.battery_label, False, False, 0)

        self.network_label = label("", "fos-small", "fos-muted")
        self.network_label.set_line_wrap(True)
        body.pack_start(self.network_label, False, False, 0)

        power = Gtk.Box(spacing=8)
        for text, icon_name, action in (
            ("Lock", "system-lock-screen-symbolic", "lock"),
            ("Suspend", "system-suspend-symbolic", "suspend"),
        ):
            btn = button(text, icon_name=icon_name, variant="outline", size="sm")
            btn.connect("clicked", lambda _b, a=action: self._power(a))
            power.pack_start(btn, True, True, 0)
        body.pack_start(power, False, False, 0)

        footer = add_classes(Gtk.Box(spacing=8), "fos-card-footer")
        settings = button("Settings", variant="ghost", size="sm")
        settings.connect("clicked", lambda _b: self._open_settings())
        footer.pack_start(settings, False, False, 0)
        more = button("Network…", variant="ghost", size="sm")
        more.connect("clicked", lambda _b: self._open_network())
        footer.pack_end(more, False, False, 0)
        sound = button("Sound…", variant="ghost", size="sm")
        sound.connect("clicked", lambda _b: self._open_sound())
        footer.pack_end(sound, False, False, 0)
        frame.pack_start(footer, False, False, 0)

    def _toggle_tile(self, icon_name: str, caption: str) -> Gtk.Button:
        widget = button(variant="outline")
        add_classes(widget, "fos-qs-tile")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_halign(Gtk.Align.CENTER)
        box.pack_start(tile(icon_name, "muted", small=True), False, False, 0)
        box.pack_start(label(caption, "fos-small", xalign=0.5), False, False, 0)
        widget.add(box)
        widget.set_tooltip_text(caption)
        return widget

    def _set_tile_active(self, widget: Gtk.Button, active: bool, sensitive: bool = True) -> None:
        widget.set_sensitive(sensitive)
        set_class(widget, "secondary", active and sensitive)
        set_class(widget, "outline", not (active and sensitive))

    def refresh(self) -> None:
        self._updating = True

        wifi = wifi_enabled()
        self._set_tile_active(self.wifi_tile, bool(wifi), wifi is not None)

        bt_avail = bluetooth_available()
        self.bt_tile.set_visible(bt_avail)
        if bt_avail:
            bt = bluetooth_powered()
            self._set_tile_active(self.bt_tile, bool(bt), bt is not None)
        else:
            self._set_tile_active(self.bt_tile, False, False)

        focus_on = _focus_assist_on()
        self._set_tile_active(self.focus_tile, focus_on, True)
        self.focus_tile.set_tooltip_text(
            "Focus assist on — toast popups hidden" if focus_on else "Focus assist — hide toast popups"
        )

        state = read_volume()
        if state is None:
            self.vol_scale.set_sensitive(False)
            self.vol_icon.set_sensitive(False)
            self.mute_tile.set_sensitive(False)
            self.vol_percent.set_text("")
            self._set_tile_active(self.mute_tile, False, False)
        else:
            level, muted = state
            self.vol_scale.set_sensitive(True)
            self.vol_icon.set_sensitive(True)
            self.mute_tile.set_sensitive(True)
            self.vol_scale.set_value(min(level, 100))
            self.vol_percent.set_text(f"{level}%")
            icon_name = volume_icon(level, muted)
            self.vol_icon.get_child().set_from_icon_name(icon_name, Gtk.IconSize.MENU)
            self._set_tile_active(self.mute_tile, muted, True)
            self.mute_tile.set_tooltip_text("Unmute" if muted else "Mute")

        level = read_brightness()
        if level is None or not brightness_available():
            self.bright_block.hide()
        else:
            self.bright_block.show()
            self.bright_scale.set_sensitive(True)
            self.bright_scale.set_value(level)
            self.bright_percent.set_text(f"{level}%")
            self.bright_icon.get_child().set_from_icon_name(brightness_icon(level), Gtk.IconSize.MENU)

        if battery_present():
            batt = battery_state()
            self.battery_label.set_text(batt[1] if batt else "Battery")
            self.battery_label.show()
        else:
            self.battery_label.hide()

        _icon, net_text = network_state()
        self.network_label.set_text(net_text)

        self._updating = False
        self.shell.update_status()
        self.relayout()

    def _on_volume(self, scale: Gtk.Scale) -> None:
        if self._updating:
            return
        level = int(scale.get_value())
        self.vol_percent.set_text(f"{level}%")
        run(["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", f"{level / 100:.2f}"])
        self.shell.update_status()

    def _on_brightness(self, scale: Gtk.Scale) -> None:
        if self._updating:
            return
        level = int(scale.get_value())
        self.bright_percent.set_text(f"{level}%")
        set_brightness(level)
        self.shell.update_status()

    def _toggle_mute(self) -> None:
        run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"])
        self.refresh()

    def _toggle_focus(self) -> None:
        _set_focus_assist(not _focus_assist_on())
        self.refresh()

    def _open_network_popup(self) -> None:
        self.dismiss()
        for panel in self.shell.panels:
            anchor = panel.network_button or panel.volume_button or panel.clock_button
            if anchor is not None:
                self.shell.toggle_popup("network", anchor, panel)
                return

    def _toggle_wifi(self) -> None:
        # Open the network flyout (list + switch). Radio toggle lives there.
        self._open_network_popup()

    def _toggle_bluetooth(self) -> None:
        powered = bluetooth_powered()
        if powered is None:
            return
        run_async(
            ["bluetoothctl", "power", "off" if powered else "on"],
            lambda _ok, _out: self.refresh(),
        )

    def _power(self, action: str) -> None:
        self.dismiss()
        self.shell.end_session(action)

    def _open_settings(self) -> None:
        self.dismiss()
        self.shell.open_settings()

    def _open_network(self) -> None:
        self._open_network_popup()

    def _open_sound(self) -> None:
        self.dismiss()
        appmod.spawn(["pavucontrol"])
