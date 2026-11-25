"""SMB / UNC helpers for FosOS Files (GVFS only).

Parses Windows-style UNC and smb:// URIs, mounts via Gio + Gtk.MountOperation,
and tracks recent network locations. Browse uses gvfs-fuse paths under
/run/user/<uid>/gvfs once mounted — Files stays Path-centric.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable
from urllib.parse import quote, unquote, urlparse

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk

STATE_DIR = Path.home() / ".local/share/fosos-desktop"
LOCATIONS_FILE = STATE_DIR / "network-locations.json"
MAX_RECENT = 12

# \\host\share\path  or  //host/share/path  (optional trailing path)
_UNC_RE = re.compile(
    r"^[\\/]{2}"
    r"(?P<host>[^\\/]+)"
    r"(?:[\\/](?P<share>[^\\/]+)"
    r"(?P<rest>(?:[\\/][^\\/]+)*)?)?"
    r"[\\/]?$",
    re.IGNORECASE,
)


def parse_smb_location(text: str) -> str | None:
    """Normalize UNC / smb:// input to an smb:// URI, or None if not SMB."""
    raw = (text or "").strip()
    if not raw:
        return None
    lower = raw.lower()
    if lower.startswith("smb://"):
        parsed = urlparse(raw)
        if parsed.scheme.lower() != "smb" or not parsed.hostname:
            return None
        host = parsed.hostname
        # Keep userinfo if present (user@host or DOMAIN;user@host).
        netloc = parsed.netloc
        path = parsed.path or ""
        # Collapse duplicate slashes in path; keep leading /.
        parts = [p for p in path.split("/") if p]
        clean_path = "/" + "/".join(parts) if parts else ""
        return f"smb://{netloc}{clean_path}"

    # Other URI schemes are not SMB.
    if "://" in raw:
        return None

    # Windows / Unix UNC forms.
    match = _UNC_RE.match(raw.replace("\\", "/"))
    if match is None:
        # Also accept host/share without leading slashes when typed as path-like.
        # Require at least host\share to avoid treating local relative paths as UNC.
        return None
    host = match.group("host")
    share = match.group("share")
    rest = (match.group("rest") or "").replace("\\", "/")
    if not host:
        return None
    segments = [host]
    if share:
        segments.append(share)
    if rest:
        segments.extend(p for p in rest.split("/") if p)
    # Encode path segments; leave host unencoded (IDNA optional — keep as typed).
    if len(segments) == 1:
        return f"smb://{segments[0]}/"
    path = "/".join(quote(seg, safe="") for seg in segments[1:])
    return f"smb://{segments[0]}/{path}"


def unc_display_from_uri(uri: str) -> str:
    """smb://host/share/a/b → \\\\host\\share\\a\\b"""
    parsed = urlparse(uri)
    if parsed.scheme.lower() != "smb" or not parsed.hostname:
        return uri
    host = parsed.hostname
    parts = [unquote(p) for p in (parsed.path or "").split("/") if p]
    if not parts:
        return f"\\\\{host}"
    return "\\\\" + "\\".join([host, *parts])


def unc_display_for_path(path: Path) -> str | None:
    """If path is under a mounted SMB GVFS root, return a UNC-style display string."""
    info = find_smb_mount_for_path(path)
    if info is None:
        return None
    mount_path, uri = info
    try:
        rel = path.resolve().relative_to(Path(mount_path).resolve())
    except (OSError, ValueError):
        try:
            rel = path.relative_to(mount_path)
        except ValueError:
            return unc_display_from_uri(uri)
    base = unc_display_from_uri(uri).rstrip("\\")
    if not rel.parts:
        return base
    return base + "\\" + "\\".join(rel.parts)


def is_gvfs_smb_mount(mount: Gio.Mount) -> bool:
    root = mount.get_root()
    if root is None:
        return False
    uri = (root.get_uri() or "").lower()
    if uri.startswith("smb://"):
        return True
    path = root.get_path() or ""
    return "/gvfs/" in path and "smb-share:" in path


def list_smb_mounts() -> list[tuple[str, Path, str]]:
    """Return (display_name, local_path, smb_uri) for mounted SMB shares."""
    rows: list[tuple[str, Path, str]] = []
    try:
        monitor = Gio.VolumeMonitor.get()
    except GLib.Error:
        return rows
    for mount in monitor.get_mounts():
        if not is_gvfs_smb_mount(mount):
            continue
        root = mount.get_root()
        if root is None:
            continue
        path_str = root.get_path()
        if not path_str:
            continue
        uri = root.get_uri() or ""
        name = mount.get_name() or unc_display_from_uri(uri) or Path(path_str).name
        rows.append((name, Path(path_str), uri))
    return rows


def find_smb_mount_for_path(path: Path) -> tuple[Path, str] | None:
    """Return (mount_root, smb_uri) if path is on a mounted SMB share."""
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for _name, mount_path, uri in list_smb_mounts():
        try:
            root = mount_path.resolve()
        except OSError:
            root = mount_path
        try:
            if resolved == root or resolved.is_relative_to(root):
                return mount_path, uri
        except (ValueError, AttributeError):
            try:
                resolved.relative_to(root)
                return mount_path, uri
            except ValueError:
                continue
    return None


def find_mount_for_uri(uri: str) -> Path | None:
    """Local path of an already-mounted smb:// URI (exact or parent share)."""
    target = parse_smb_location(uri)
    if not target:
        return None
    target_parsed = urlparse(target)
    for _name, mount_path, mounted_uri in list_smb_mounts():
        mounted = parse_smb_location(mounted_uri) or mounted_uri
        # Exact match or target is under mounted URI.
        if target.rstrip("/") == mounted.rstrip("/"):
            return mount_path
        if target.startswith(mounted.rstrip("/") + "/"):
            # Append relative path segments onto the FUSE root.
            rel = target[len(mounted.rstrip("/")) :].lstrip("/")
            if not rel:
                return mount_path
            return mount_path / Path(*[unquote(p) for p in rel.split("/") if p])
        # Same host+share: compare first two path segments.
        m_parsed = urlparse(mounted)
        if (
            (target_parsed.hostname or "").lower() == (m_parsed.hostname or "").lower()
            and _share_name(target_parsed) == _share_name(m_parsed)
            and _share_name(m_parsed)
        ):
            rel_parts = [unquote(p) for p in (target_parsed.path or "").split("/") if p][1:]
            return mount_path.joinpath(*rel_parts) if rel_parts else mount_path
    return None


def _share_name(parsed) -> str:
    parts = [unquote(p) for p in (parsed.path or "").split("/") if p]
    return parts[0].lower() if parts else ""


def local_path_for_smb_uri(uri: str) -> Path | None:
    """Return a local Path if the URI is already mounted (possibly nested)."""
    return find_mount_for_uri(uri)


def mount_smb_async(
    uri: str,
    parent: Gtk.Window | None,
    on_done: Callable[[Path | None, str | None], None],
) -> None:
    """Mount smb:// via GVFS. on_done(path, error_message)."""
    normalized = parse_smb_location(uri)
    if not normalized:
        on_done(None, "Not a valid SMB or UNC path.")
        return

    existing = local_path_for_smb_uri(normalized)
    if existing is not None and existing.exists():
        remember_location(normalized)
        on_done(existing, None)
        return

    gfile = Gio.File.new_for_uri(normalized)
    # If the file is already reachable without an explicit mount, use it.
    try:
        path_now = gfile.get_path()
        if path_now and Path(path_now).exists():
            remember_location(normalized)
            on_done(Path(path_now), None)
            return
    except GLib.Error:
        pass

    operation = Gtk.MountOperation(parent=parent) if parent is not None else Gtk.MountOperation()

    def _finished(source: Gio.File, result: Gio.AsyncResult) -> None:
        try:
            source.mount_enclosing_volume_finish(result)
        except GLib.Error as exc:
            # Already mounted is success.
            if exc.matches(Gio.io_error_quark(), Gio.IOErrorEnum.ALREADY_MOUNTED):
                pass
            else:
                on_done(None, exc.message or str(exc))
                return
        # Prefer path from the mounted file; fall back to VolumeMonitor lookup.
        local = source.get_path()
        if local:
            remember_location(normalized)
            on_done(Path(local), None)
            return
        found = local_path_for_smb_uri(normalized)
        if found is not None:
            remember_location(normalized)
            on_done(found, None)
            return
        on_done(
            None,
            "Share mounted but no local path is available. Install gvfs-fuse and try again.",
        )

    try:
        gfile.mount_enclosing_volume(
            Gio.MountMountFlags.NONE,
            operation,
            None,
            _finished,
        )
    except GLib.Error as exc:
        on_done(None, exc.message or str(exc))


def unmount_path(path: Path, parent: Gtk.Window | None = None, on_done: Callable[[bool, str | None], None] | None = None) -> None:
    """Unmount the GVFS mount that contains path."""
    callback = on_done or (lambda _ok, _err: None)
    try:
        monitor = Gio.VolumeMonitor.get()
    except GLib.Error as exc:
        callback(False, str(exc))
        return
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    target: Gio.Mount | None = None
    for mount in monitor.get_mounts():
        root = mount.get_root()
        if root is None:
            continue
        root_path = root.get_path()
        if not root_path:
            continue
        try:
            root_resolved = Path(root_path).resolve()
        except OSError:
            root_resolved = Path(root_path)
        try:
            if resolved == root_resolved or resolved.is_relative_to(root_resolved):
                target = mount
                break
        except (ValueError, AttributeError):
            continue
    if target is None:
        callback(False, "No mounted share found for this location.")
        return

    operation = Gtk.MountOperation(parent=parent) if parent is not None else Gtk.MountOperation()

    def _finished(source: Gio.Mount, result: Gio.AsyncResult) -> None:
        try:
            source.unmount_with_operation_finish(result)
        except GLib.Error as exc:
            callback(False, exc.message or str(exc))
            return
        callback(True, None)

    try:
        target.unmount_with_operation(
            Gio.MountUnmountFlags.NONE,
            operation,
            None,
            _finished,
        )
    except GLib.Error as exc:
        callback(False, exc.message or str(exc))


def load_recent_locations() -> list[dict]:
    try:
        data = json.loads(LOCATIONS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for item in data:
        if isinstance(item, dict) and item.get("uri"):
            out.append(item)
    return out


def remember_location(uri: str, *, display_name: str | None = None) -> None:
    normalized = parse_smb_location(uri) or uri
    parsed = urlparse(normalized)
    host = parsed.hostname or ""
    share_parts = [unquote(p) for p in (parsed.path or "").split("/") if p]
    share = share_parts[0] if share_parts else ""
    entry = {
        "uri": normalized,
        "host": host,
        "share": share,
        "display_name": display_name or unc_display_from_uri(normalized),
    }
    recent = [e for e in load_recent_locations() if e.get("uri") != normalized]
    recent.insert(0, entry)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        LOCATIONS_FILE.write_text(json.dumps(recent[:MAX_RECENT], indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def connect_dialog(parent: Gtk.Window | None) -> str | None:
    """Prompt for \\\\server\\share. Returns smb:// URI or None if cancelled."""
    from .ui import FosDialog, add_classes, button, label

    dialog = FosDialog(parent, title="Connect to Server", width=440)
    dialog.add_body_text("Enter a Windows network path (\\\\server\\share).")
    entry = add_classes(Gtk.Entry(), "fos-input")
    entry.set_placeholder_text(r"\\server\share")
    entry.set_activates_default(True)
    # Prefill last recent location.
    recent = load_recent_locations()
    if recent:
        entry.set_text(recent[0].get("display_name") or recent[0].get("uri") or "")
        entry.select_region(0, -1)
    dialog.content.pack_start(label("Folder", "fos-small", "fos-muted"), False, False, 0)
    dialog.content.pack_start(entry, False, False, 0)

    if recent:
        recent_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        recent_box.pack_start(label("Recent", "fos-small", "fos-muted"), False, False, 0)
        for item in recent[:5]:
            text = item.get("display_name") or item.get("uri") or ""
            link = button(text, variant="ghost", size="sm")
            link.get_child().set_halign(Gtk.Align.START)
            link.connect("clicked", lambda _b, t=text: entry.set_text(t))
            recent_box.pack_start(link, False, False, 0)
        dialog.content.pack_start(recent_box, False, False, 0)

    held: dict[str, str | None] = {"uri": None}

    def _connect(_btn=None) -> None:
        text = entry.get_text().strip()
        if not text:
            dialog.respond(None)
            return
        uri = parse_smb_location(text)
        if uri is None:
            uri = parse_smb_location("\\\\" + text.lstrip("\\/"))
        held["uri"] = uri
        dialog.respond("connect" if uri else None)

    dialog.add_action("Cancel", None, variant="ghost")
    connect_btn = button("Connect", variant="default", size="sm")
    connect_btn.set_can_default(True)
    connect_btn.grab_default()
    connect_btn.connect("clicked", _connect)
    dialog.footer.pack_start(connect_btn, False, False, 0)
    entry.connect("activate", lambda _e: _connect())
    entry.grab_focus()
    response = dialog.run()
    if response != "connect":
        return None
    return held["uri"]
