"""Status Notifier (SNI) watcher and panel tray strip."""

from __future__ import annotations

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk

from .ui import add_classes, button

WATCHER_NAME = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
ITEM_IFACE = "org.kde.StatusNotifierItem"

WATCHER_XML = """
<node>
  <interface name="org.kde.StatusNotifierWatcher">
    <method name="RegisterStatusNotifierItem">
      <arg name="service" type="s" direction="in"/>
    </method>
    <method name="RegisterStatusNotifierHost">
      <arg name="service" type="s" direction="in"/>
    </method>
    <property name="RegisteredStatusNotifierItems" type="as" access="read"/>
    <property name="IsStatusNotifierHostRegistered" type="b" access="read"/>
    <property name="ProtocolVersion" type="i" access="read"/>
    <signal name="StatusNotifierItemRegistered">
      <arg name="service" type="s"/>
    </signal>
    <signal name="StatusNotifierItemUnregistered">
      <arg name="service" type="s"/>
    </signal>
    <signal name="StatusNotifierHostRegistered"/>
  </interface>
</node>
"""


def _variant_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, GLib.Variant):
        try:
            return str(value.unpack())
        except Exception:
            return ""
    return str(value)


class TrayItem:
    def __init__(self, service: str, bus_name: str, object_path: str) -> None:
        self.id = service
        self.bus_name = bus_name
        self.object_path = object_path
        self.proxy: Gio.DBusProxy | None = None
        self.icon_name = "application-x-executable-symbolic"
        self.tooltip = ""
        self.pixbuf: GdkPixbuf.Pixbuf | None = None
        self.button: Gtk.Button | None = None

    def connect(self) -> None:
        self.proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.GET_INVALIDATED_PROPERTIES,
            None,
            self.bus_name,
            self.object_path,
            ITEM_IFACE,
            None,
        )
        self.proxy.connect("g-properties-changed", lambda *_a: self.refresh())
        self.proxy.connect("g-signal", self._on_signal)
        self.refresh()

    def _on_signal(self, _proxy, _sender, signal, _params) -> None:
        if signal in ("NewIcon", "NewAttentionIcon", "NewToolTip", "NewStatus", "NewTitle"):
            self.refresh()

    def _prop(self, name: str):
        if self.proxy is None:
            return None
        try:
            cached = self.proxy.get_cached_property(name)
            if cached is not None:
                return cached.unpack()
        except Exception:
            pass
        try:
            conn = self.proxy.get_connection()
            result = conn.call_sync(
                self.bus_name,
                self.object_path,
                "org.freedesktop.DBus.Properties",
                "Get",
                GLib.Variant("(ss)", (ITEM_IFACE, name)),
                GLib.VariantType("(v)"),
                Gio.DBusCallFlags.NONE,
                1000,
                None,
            )
            return result.unpack()[0]
        except GLib.Error:
            return None

    def refresh(self) -> None:
        if self.proxy is None:
            return
        name = self._prop("IconName")
        if isinstance(name, str) and name:
            self.icon_name = name
        tip = self._prop("ToolTip")
        if isinstance(tip, (list, tuple)) and len(tip) >= 3:
            title = tip[2] or (tip[3] if len(tip) > 3 else "")
            self.tooltip = str(title or "")
        title_prop = self._prop("Title")
        if isinstance(title_prop, str) and title_prop and not self.tooltip:
            self.tooltip = title_prop
        pix = self._prop("IconPixmap")
        try:
            self.pixbuf = _pixmap_to_pixbuf(pix) if pix else None
        except Exception:
            self.pixbuf = None
        self._apply_button()

    def _apply_button(self) -> None:
        if self.button is None:
            return
        child = self.button.get_child()
        if self.pixbuf is not None:
            scaled = self.pixbuf.scale_simple(16, 16, GdkPixbuf.InterpType.BILINEAR)
            image = Gtk.Image.new_from_pixbuf(scaled)
            if child is not None:
                self.button.remove(child)
            self.button.add(image)
            image.show()
        elif isinstance(child, Gtk.Image):
            child.set_from_icon_name(self.icon_name, Gtk.IconSize.MENU)
            child.set_pixel_size(16)
        else:
            if child is not None:
                self.button.remove(child)
            image = Gtk.Image.new_from_icon_name(self.icon_name, Gtk.IconSize.MENU)
            image.set_pixel_size(16)
            self.button.add(image)
            image.show()
        self.button.set_tooltip_text(self.tooltip or self.icon_name)

    def activate(self, x: int, y: int) -> None:
        self._call("Activate", GLib.Variant("(ii)", (x, y)))

    def secondary_activate(self, x: int, y: int) -> None:
        self._call("SecondaryActivate", GLib.Variant("(ii)", (x, y)))

    def context_menu(self, x: int, y: int) -> None:
        self._call("ContextMenu", GLib.Variant("(ii)", (x, y)))

    def _call(self, method: str, params: GLib.Variant) -> None:
        if self.proxy is None:
            return
        try:
            self.proxy.call(method, params, Gio.DBusCallFlags.NONE, -1, None, None, None)
        except GLib.Error:
            pass


def _pixmap_to_pixbuf(data) -> GdkPixbuf.Pixbuf | None:
    """IconPixmap is a(iiay): width, height, ARGB32 bytes."""
    if not data:
        return None
    # Prefer largest pixmap.
    best = None
    best_area = -1
    for entry in data:
        if not isinstance(entry, (list, tuple)) or len(entry) < 3:
            continue
        width, height, raw = entry[0], entry[1], entry[2]
        if width * height > best_area and raw:
            best = (int(width), int(height), bytes(raw))
            best_area = width * height
    if best is None:
        return None
    width, height, raw = best
    # ARGB32 network byte order → RGBA for GdkPixbuf
    if len(raw) < width * height * 4:
        return None
    rgba = bytearray(width * height * 4)
    for i in range(width * height):
        o = i * 4
        a, r, g, b = raw[o], raw[o + 1], raw[o + 2], raw[o + 3]
        rgba[o] = r
        rgba[o + 1] = g
        rgba[o + 2] = b
        rgba[o + 3] = a
    return GdkPixbuf.Pixbuf.new_from_data(
        bytes(rgba),
        GdkPixbuf.Colorspace.RGB,
        True,
        8,
        width,
        height,
        width * 4,
        None,
        None,
    )


class StatusNotifierWatcher:
    """Owns org.kde.StatusNotifierWatcher and drives the panel tray strip."""

    def __init__(self, shell) -> None:
        self.shell = shell
        self.items: dict[str, TrayItem] = {}
        self._hosts: list[str] = []
        self.connection: Gio.DBusConnection | None = None
        self._owner_id = Gio.bus_own_name(
            Gio.BusType.SESSION,
            WATCHER_NAME,
            Gio.BusNameOwnerFlags.NONE,
            self._on_bus_acquired,
            self._on_name_acquired,
            self._on_name_lost,
        )

    def _on_bus_acquired(self, connection: Gio.DBusConnection, _name: str) -> None:
        self.connection = connection
        node = Gio.DBusNodeInfo.new_for_xml(WATCHER_XML)
        connection.register_object(
            WATCHER_PATH,
            node.interfaces[0],
            self._on_method,
            self._on_get_property,
            None,
        )
        connection.signal_subscribe(
            "org.freedesktop.DBus",
            "org.freedesktop.DBus",
            "NameOwnerChanged",
            "/org/freedesktop/DBus",
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_name_owner_changed,
            None,
        )

    def _on_name_acquired(self, _connection, _name) -> None:
        # We are also the host.
        self._hosts.append("fosos-shell")
        self._emit("StatusNotifierHostRegistered", None)

    def _on_name_lost(self, _connection, _name) -> None:
        print("fosos-shell: StatusNotifierWatcher name lost")

    def _on_get_property(self, _conn, _sender, _path, _iface, name):
        if name == "RegisteredStatusNotifierItems":
            return GLib.Variant("as", (list(self.items.keys()),))
        if name == "IsStatusNotifierHostRegistered":
            return GLib.Variant("b", (True,))
        if name == "ProtocolVersion":
            return GLib.Variant("i", (0,))
        return None

    def _on_method(self, connection, sender, _path, _iface, method, params, invocation) -> None:
        args = params.unpack()
        if method == "RegisterStatusNotifierItem":
            service = args[0]
            self._register_item(sender, service)
            invocation.return_value(None)
        elif method == "RegisterStatusNotifierHost":
            host = args[0]
            if host not in self._hosts:
                self._hosts.append(host)
            self._emit("StatusNotifierHostRegistered", None)
            invocation.return_value(None)
        else:
            invocation.return_dbus_error("org.freedesktop.DBus.Error.UnknownMethod", method)

    def _register_item(self, sender: str, service: str) -> None:
        # service may be "bus.name" or "/path" or "bus.name/path"
        if service.startswith("/"):
            bus_name = sender
            object_path = service
            key = f"{bus_name}{object_path}"
        elif "/" in service:
            bus_name, object_path = service.split("/", 1)
            object_path = "/" + object_path
            key = service if service.startswith(bus_name) else f"{bus_name}{object_path}"
            # Canonicalize key used by clients
            key = f"{bus_name}{object_path}"
        else:
            bus_name = service
            object_path = "/StatusNotifierItem"
            key = f"{bus_name}{object_path}"

        if key in self.items:
            self.items[key].refresh()
            self._refresh_panels()
            return

        item = TrayItem(key, bus_name, object_path)
        try:
            item.connect()
        except GLib.Error as exc:
            print(f"fosos-shell: tray item failed ({key}): {exc}")
            return
        self.items[key] = item
        self._emit("StatusNotifierItemRegistered", GLib.Variant("(s)", (key,)))
        self._refresh_panels()

    def _unregister(self, key: str) -> None:
        item = self.items.pop(key, None)
        if item is None:
            return
        self._emit("StatusNotifierItemUnregistered", GLib.Variant("(s)", (key,)))
        self._refresh_panels()

    def _on_name_owner_changed(self, _conn, _sender, _path, _iface, _signal, params, _data) -> None:
        name, _old, new = params.unpack()
        if new:
            return
        for key in list(self.items):
            if self.items[key].bus_name == name:
                self._unregister(key)

    def _emit(self, signal: str, params: GLib.Variant | None) -> None:
        if self.connection is None:
            return
        try:
            self.connection.emit_signal(None, WATCHER_PATH, WATCHER_NAME, signal, params)
        except GLib.Error:
            pass

    def _refresh_panels(self) -> None:
        for panel in self.shell.panels:
            if hasattr(panel, "rebuild_tray"):
                panel.rebuild_tray()


def build_tray_button(item: TrayItem) -> Gtk.Button:
    widget = button(variant="ghost", size="icon-sm", tooltip=item.tooltip or "Tray")
    add_classes(widget, "fos-tray-icon")
    image = Gtk.Image.new_from_icon_name(item.icon_name, Gtk.IconSize.MENU)
    image.set_pixel_size(16)
    widget.add(image)
    item.button = widget
    item._apply_button()

    def on_press(_btn, event: Gdk.EventButton) -> bool:
        x = int(event.x_root)
        y = int(event.y_root)
        if event.button == 1:
            item.activate(x, y)
            return True
        if event.button == 2:
            item.secondary_activate(x, y)
            return True
        if event.button == 3:
            item.context_menu(x, y)
            return True
        return False

    widget.connect("button-press-event", on_press)
    return widget
