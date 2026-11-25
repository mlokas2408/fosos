"""org.freedesktop.portal.Desktop — Save As and “show in folder”.

FileChooser drives the FosOS download Save As dialog. OpenURI.OpenDirectory
is what Chrome calls for “Show in folder” once this portal name is on the bus;
without it Chrome opens the folder as a page in the browser instead.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk

from .filechooser import ChooserFilter, SaveDialog
from .filemanager import _open as reveal_paths

BUS_NAME = "org.freedesktop.portal.Desktop"
OBJECT_PATH = "/org/freedesktop/portal/desktop"
FILE_CHOOSER_VERSION = 4
OPEN_URI_VERSION = 5
_TOKEN = re.compile(r"[A-Za-z0-9_]+")

PORTAL_XML = """
<node>
  <interface name="org.freedesktop.portal.FileChooser">
    <method name="OpenFile">
      <arg type="s" name="parent_window" direction="in"/>
      <arg type="s" name="title" direction="in"/>
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="o" name="handle" direction="out"/>
    </method>
    <method name="SaveFile">
      <arg type="s" name="parent_window" direction="in"/>
      <arg type="s" name="title" direction="in"/>
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="o" name="handle" direction="out"/>
    </method>
    <method name="SaveFiles">
      <arg type="s" name="parent_window" direction="in"/>
      <arg type="s" name="title" direction="in"/>
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="o" name="handle" direction="out"/>
    </method>
    <property name="version" type="u" access="read"/>
  </interface>
  <interface name="org.freedesktop.portal.OpenURI">
    <method name="OpenURI">
      <arg type="s" name="parent_window" direction="in"/>
      <arg type="s" name="uri" direction="in"/>
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="o" name="handle" direction="out"/>
    </method>
    <method name="OpenFile">
      <arg type="s" name="parent_window" direction="in"/>
      <arg type="h" name="fd" direction="in"/>
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="o" name="handle" direction="out"/>
    </method>
    <method name="OpenDirectory">
      <arg type="s" name="parent_window" direction="in"/>
      <arg type="h" name="fd" direction="in"/>
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="o" name="handle" direction="out"/>
    </method>
    <property name="version" type="u" access="read"/>
  </interface>
</node>
"""

REQUEST_XML = """
<node>
  <interface name="org.freedesktop.portal.Request">
    <method name="Close"/>
    <signal name="Response">
      <arg type="u" name="response"/>
      <arg type="a{sv}" name="results"/>
    </signal>
  </interface>
</node>
"""


def _option(options: dict, key: str):
    value = options.get(key)
    if isinstance(value, GLib.Variant):
        return value.unpack()
    return value


def _options(raw) -> dict:
    if isinstance(raw, GLib.Variant):
        raw = raw.unpack()
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items()}


def _path_bytes(value) -> Path | None:
    if isinstance(value, GLib.Variant):
        value = value.unpack()
    if isinstance(value, str):
        data = os.fsencode(value)
    elif isinstance(value, (bytes, bytearray)):
        data = bytes(value)
    elif isinstance(value, (list, tuple)):
        data = bytes(int(item) & 0xFF for item in value)
    else:
        return None
    data = data.split(b"\x00", 1)[0]
    if not data:
        return None
    return Path(os.fsdecode(data)).expanduser()


def _filters(value) -> list[ChooserFilter]:
    if isinstance(value, GLib.Variant):
        value = value.unpack()
    found: list[ChooserFilter] = []
    if not isinstance(value, (list, tuple)):
        return found
    for item in value:
        if isinstance(item, GLib.Variant):
            item = item.unpack()
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        name = str(item[0])
        rules_raw = item[1]
        if isinstance(rules_raw, GLib.Variant):
            rules_raw = rules_raw.unpack()
        rules: list[tuple[int, str]] = []
        for rule in rules_raw or []:
            if isinstance(rule, GLib.Variant):
                rule = rule.unpack()
            if isinstance(rule, (list, tuple)) and len(rule) >= 2:
                rules.append((int(rule[0]), str(rule[1])))
        found.append(ChooserFilter(name=name, rules=rules))
    return found


def _sender_token(sender: str) -> str:
    return sender.replace(":", "_").replace(".", "_")


def _fd_path(invocation, handle_index: int) -> Path | None:
    """Resolve a D-Bus unix fd handle to a filesystem path."""
    message = invocation.get_message()
    fd_list = message.get_unix_fd_list() if message is not None else None
    if fd_list is None:
        return None
    try:
        fd = fd_list.get(int(handle_index))
    except (TypeError, ValueError, GLib.Error):
        return None
    try:
        return Path(os.readlink(f"/proc/self/fd/{fd}"))
    except OSError:
        return None
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


class Portal:
    def __init__(self) -> None:
        self.connection: Gio.DBusConnection | None = None
        self._serial = 0
        self._requests: dict[str, dict] = {}
        self._request_iface = Gio.DBusNodeInfo.new_for_xml(REQUEST_XML).interfaces[0]

    def start(self) -> None:
        acquired = {"ok": False}

        def on_bus(connection, _name) -> None:
            self.connection = connection
            node = Gio.DBusNodeInfo.new_for_xml(PORTAL_XML)
            for iface in node.interfaces:
                connection.register_object(
                    OBJECT_PATH,
                    iface,
                    self._on_method,
                    self._on_get_property,
                    None,
                )

        def on_acquired(*_args) -> None:
            acquired["ok"] = True

        def on_lost(*_args) -> None:
            if not acquired["ok"]:
                print("fosos-file-chooser: portal name is already taken", flush=True)
            Gtk.main_quit()

        Gio.bus_own_name(
            Gio.BusType.SESSION,
            BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            on_bus,
            on_acquired,
            on_lost,
        )

    def _on_get_property(self, _conn, _sender, _path, iface, prop):
        if prop != "version":
            return None
        if iface == "org.freedesktop.portal.OpenURI":
            return GLib.Variant("u", OPEN_URI_VERSION)
        return GLib.Variant("u", FILE_CHOOSER_VERSION)

    def _on_method(self, _conn, sender, _path, iface, method, params, invocation) -> None:
        if iface == "org.freedesktop.portal.OpenURI":
            self._on_open_uri(sender, method, params, invocation)
            return
        try:
            _parent, title, raw_options = params.unpack()
        except Exception:  # noqa: BLE001
            invocation.return_dbus_error("org.freedesktop.DBus.Error.InvalidArgs", "Expected title and options")
            return
        options = _options(raw_options)
        if method == "OpenFile":
            mode = "directory" if _option(options, "directory") else "open"
        elif method == "SaveFile":
            mode = "save"
        elif method == "SaveFiles":
            mode = "directory"
        else:
            invocation.return_dbus_error("org.freedesktop.DBus.Error.UnknownMethod", method)
            return
        handle = self._request_path(sender or "", str(_option(options, "handle_token") or ""))
        state = {"mode": mode, "title": title or "", "options": options, "dialog": None, "reg": 0, "done": False}
        self._requests[handle] = state
        assert self.connection is not None
        state["reg"] = self.connection.register_object(handle, self._request_iface, self._on_request, None, None)
        invocation.return_value(GLib.Variant("(o)", (handle,)))
        GLib.idle_add(self._show, handle)

    def _on_open_uri(self, sender: str, method: str, params, invocation) -> None:
        options: dict = {}
        path: Path | None = None
        action = "reveal"
        try:
            if method == "OpenURI":
                _parent, uri, raw_options = params.unpack()
                options = _options(raw_options)
                text = str(uri or "").strip()
                if not text.startswith("file:"):
                    invocation.return_dbus_error(
                        "org.freedesktop.portal.Error.NotAllowed",
                        "Only file:// URIs are handled by the FosOS portal",
                    )
                    return
                local = Gio.File.new_for_uri(text).get_path()
                path = Path(local) if local else None
                action = "reveal" if path is not None and path.is_dir() else "launch"
            elif method == "OpenDirectory":
                _parent, handle_index, raw_options = params.unpack()
                options = _options(raw_options)
                path = _fd_path(invocation, handle_index)
                action = "reveal"
            elif method == "OpenFile":
                _parent, handle_index, raw_options = params.unpack()
                options = _options(raw_options)
                path = _fd_path(invocation, handle_index)
                action = "launch"
            else:
                invocation.return_dbus_error("org.freedesktop.DBus.Error.UnknownMethod", method)
                return
        except Exception:  # noqa: BLE001
            invocation.return_dbus_error("org.freedesktop.DBus.Error.InvalidArgs", "Bad OpenURI arguments")
            return

        handle = self._request_path(sender or "", str(_option(options, "handle_token") or ""))
        state = {
            "mode": "reveal",
            "dialog": None,
            "reg": 0,
            "done": False,
            "path": path,
            "action": action,
        }
        self._requests[handle] = state
        assert self.connection is not None
        state["reg"] = self.connection.register_object(handle, self._request_iface, self._on_request, None, None)
        invocation.return_value(GLib.Variant("(o)", (handle,)))
        GLib.idle_add(self._open_uri_finish, handle)

    def _open_uri_finish(self, handle: str) -> bool:
        state = self._requests.get(handle)
        if state is None or state["done"] or state.get("cancelled"):
            return False
        path = state.get("path")
        ok = False
        if isinstance(path, Path) and (path.exists() or path.parent.exists()):
            if state.get("action") == "launch" and path.is_file():
                try:
                    ok = bool(Gio.AppInfo.launch_default_for_uri(path.as_uri(), None))
                except GLib.Error:
                    ok = False
            else:
                target = path if path.is_dir() else path.parent
                if target.exists():
                    reveal_paths([path if path.exists() else target])
                    ok = True
        self._finish(handle, 0 if ok else 1, [])
        return False

    def _request_path(self, sender: str, token: str) -> str:
        if not _TOKEN.fullmatch(token or ""):
            self._serial += 1
            token = f"fosos{self._serial}"
        who = _sender_token(sender) or "unknown"
        return f"/org/freedesktop/portal/desktop/request/{who}/{token}"

    def _on_request(self, _conn, _sender, path, _iface, method, _params, invocation) -> None:
        if method == "Close":
            self._cancel(path)
        invocation.return_value(None)

    def _cancel(self, handle: str) -> None:
        state = self._requests.get(handle)
        if state is None:
            return
        state["cancelled"] = True
        dialog = state.get("dialog")
        if dialog is not None:
            dialog.respond(None)
        else:
            self._finish(handle, 1, [])

    def _show(self, handle: str) -> bool:
        state = self._requests.get(handle)
        if state is None or state["done"] or state.get("cancelled"):
            return False
        options = state["options"]
        mode = state["mode"]
        folder = _path_bytes(_option(options, "current_folder"))
        if folder is not None and not folder.is_dir():
            folder = folder.parent if folder.parent.is_dir() else None
        name = str(_option(options, "current_name") or "")
        multiple = bool(_option(options, "multiple"))
        if mode == "directory":
            files = _option(options, "files") or []
            state["save_names"] = [Path(str(item)).name for item in files if str(item).strip()]
            name = ""
        else:
            state["save_names"] = []
            name = Path(name).name
        label = str(_option(options, "accept_label") or "")
        dialog = SaveDialog(
            title=state["title"] or ("Save as" if mode == "save" else "Open"),
            mode=mode,
            folder=folder,
            name=name,
            accept_label=label or {"save": "Save", "directory": "Select"}.get(mode, "Open"),
            filters=_filters(_option(options, "filters")),
            multiple=multiple,
        )
        if state.get("cancelled") or state.get("done"):
            dialog.destroy()
            return False
        state["dialog"] = dialog
        paths = dialog.run()
        if state.get("done"):
            return False
        if mode == "directory" and paths and state["save_names"]:
            folder_path = paths[0]
            paths = [folder_path / item for item in state["save_names"]]
        uris = []
        if paths:
            for path in paths:
                uris.append(Gio.File.new_for_path(str(path)).get_uri())
        self._finish(handle, 0 if uris else 1, uris)
        return False

    def _finish(self, handle: str, response: int, uris: list[str]) -> None:
        state = self._requests.pop(handle, None)
        if state is None or state["done"] or self.connection is None:
            return
        state["done"] = True
        results: dict[str, GLib.Variant] = {}
        if response == 0 and uris:
            results["uris"] = GLib.Variant("as", uris)
        self.connection.emit_signal(
            None,
            handle,
            "org.freedesktop.portal.Request",
            "Response",
            GLib.Variant("(ua{sv})", (response, results)),
        )
        reg = state.get("reg") or 0
        if reg:
            try:
                self.connection.unregister_object(reg)
            except Exception:  # noqa: BLE001 - object may already be gone
                pass


def main() -> int:
    Gtk.init([])
    portal = Portal()
    portal.start()
    Gtk.main()
    return 0
