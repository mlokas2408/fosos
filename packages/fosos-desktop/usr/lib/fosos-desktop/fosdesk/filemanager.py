"""org.freedesktop.FileManager1 for the download “show in folder” button.

Chrome and Firefox ask this D-Bus name to reveal a downloaded file. With no
answer they open the folder path as a page in the browser.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

BUS_NAME = "org.freedesktop.FileManager1"
OBJECT_PATH = "/org/freedesktop/FileManager1"
IFACE_XML = """
<node>
  <interface name="org.freedesktop.FileManager1">
    <method name="ShowFolders">
      <arg type="as" name="URIs" direction="in"/>
      <arg type="s" name="StartupId" direction="in"/>
    </method>
    <method name="ShowItems">
      <arg type="as" name="URIs" direction="in"/>
      <arg type="s" name="StartupId" direction="in"/>
    </method>
    <method name="ShowItemProperties">
      <arg type="as" name="URIs" direction="in"/>
      <arg type="s" name="StartupId" direction="in"/>
    </method>
  </interface>
</node>
"""


def _paths(uris: list[str]) -> list[Path | str]:
    """Resolve to local Paths, or leave smb:// / UNC strings for Files to mount."""
    from . import smb as smbmod

    found: list[Path | str] = []
    for uri in uris:
        text = (uri or "").strip()
        if not text:
            continue
        smb = smbmod.parse_smb_location(text)
        if smb is None and ("\\" in text or text.startswith("//")):
            smb = smbmod.parse_smb_location("\\\\" + text.lstrip("\\/"))
        if smb is not None:
            local = smbmod.local_path_for_smb_uri(smb)
            if local is not None and (local.exists() or local.parent.exists()):
                found.append(local)
            else:
                gpath = Gio.File.new_for_uri(smb).get_path()
                if gpath and Path(gpath).exists():
                    found.append(Path(gpath))
                else:
                    found.append(smb)
            continue
        if "://" in text:
            local = Gio.File.new_for_uri(text).get_path()
            if not local:
                continue
            path = Path(local)
        else:
            path = Path(text).expanduser()
        if path.exists() or path.parent.exists():
            found.append(path)
    return found


def _open(paths: list[Path | str], *, properties: bool = False) -> None:
    if not paths:
        return
    argv = ["fosos-files", *(str(path) for path in paths)]
    if properties:
        argv.append("--properties")
    proc = subprocess.Popen(  # noqa: S603 - fixed launcher, paths come from the browser
        argv,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Reap the explorer when it exits so the service does not keep zombies.
    GLib.child_watch_add(proc.pid, lambda *_status: None)


def _on_method(_conn, _sender, _path, _iface, method: str, params, invocation) -> None:
    try:
        uris, _startup = params.unpack()
    except Exception:  # noqa: BLE001 - bad callers should get a D-Bus error
        invocation.return_dbus_error("org.freedesktop.DBus.Error.InvalidArgs", "Expected URIs and a startup id")
        return
    paths = _paths(list(uris))
    if method == "ShowFolders":
        folders: list[Path | str] = []
        for path in paths:
            if isinstance(path, str):
                folders.append(path)
            else:
                folders.append(path if path.is_dir() else path.parent)
        _open([folder for folder in folders if isinstance(folder, str) or folder.exists()])
    elif method == "ShowItemProperties":
        _open(paths, properties=True)
    else:
        # ShowItems: pass the file so Files opens its folder and selects it.
        _open(paths)
    invocation.return_value(None)


def serve() -> int:
    """Own the file-manager name until the session bus drops it."""
    loop = GLib.MainLoop()
    node = Gio.DBusNodeInfo.new_for_xml(IFACE_XML)
    iface = node.interfaces[0]
    acquired = {"ok": False}

    def on_bus(connection, _name) -> None:
        connection.register_object(OBJECT_PATH, iface, _on_method)

    def on_acquired(*_args) -> None:
        acquired["ok"] = True

    def on_lost(*_args) -> None:
        if not acquired["ok"]:
            print("fosos-files: FileManager1 name is already taken", file=sys.stderr)
        loop.quit()

    Gio.bus_own_name(
        Gio.BusType.SESSION,
        BUS_NAME,
        Gio.BusNameOwnerFlags.NONE,
        on_bus,
        on_acquired,
        on_lost,
    )
    loop.run()
    return 0
