"""Windows 11-like open placement: restore last size/position, else cascade."""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gdk, GLib, Wnck

from .panel import SKIP_TYPES
from .snaplayouts import (
    is_snapped,
    normal_geometry,
    remember_normal_geometry,
    work_area_for_point,
    work_area_for_window,
)

STORE_NAME = "window-geometry"
CASCADE_STEP = 28
_ORIGIN_TOLERANCE = 12
_TINY_WIDTH = 160
_TINY_HEIGHT = 120

# Next cascade origin per monitor index (session only).
_cascade_next: dict[int, tuple[int, int]] = {}
# XIDs already given a startup placement this map.
_placed_xids: set[int] = set()
# Live cache for save-on-close: xid -> record.
_live: dict[int, dict] = {}


def _config_dir() -> Path:
    return Path(GLib.get_user_config_dir()) / "fosos-desktop"


def _store_path() -> Path:
    return _config_dir() / STORE_NAME


def window_class_key(window: Wnck.Window) -> str:
    """Stable per-app key (WM class group, else instance name)."""
    try:
        group = (window.get_class_group_name() or "").strip()
    except Exception:
        group = ""
    if group:
        return group.lower()
    try:
        instance = (window.get_class_instance_name() or "").strip()
    except Exception:
        instance = ""
    return instance.lower()


def _load_store() -> dict[str, dict]:
    path = _store_path()
    values: dict[str, dict] = {}
    if not path.is_file():
        return values
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, raw = line.split("=", 1)
            key = key.strip().lower()
            parts = [p.strip() for p in raw.split(",")]
            if len(parts) < 5:
                continue
            try:
                values[key] = {
                    "x": int(parts[0]),
                    "y": int(parts[1]),
                    "w": int(parts[2]),
                    "h": int(parts[3]),
                    "maximized": parts[4] in ("1", "true", "yes"),
                }
            except ValueError:
                continue
    except OSError:
        pass
    return values


def _save_store(values: dict[str, dict]) -> None:
    _config_dir().mkdir(parents=True, exist_ok=True)
    lines = ["# class=x,y,w,h,maximized\n"]
    for key in sorted(values):
        rec = values[key]
        lines.append(
            f"{key}={int(rec['x'])},{int(rec['y'])},{int(rec['w'])},{int(rec['h'])},"
            f"{1 if rec.get('maximized') else 0}\n"
        )
    try:
        _store_path().write_text("".join(lines), encoding="utf-8")
    except OSError:
        pass


def _clamp_rect(x: int, y: int, w: int, h: int, area: Gdk.Rectangle) -> tuple[int, int, int, int]:
    w = max(200, min(w, area.width))
    h = max(160, min(h, area.height))
    x = max(area.x, min(x, area.x + area.width - w))
    y = max(area.y, min(y, area.y + area.height - h))
    return x, y, w, h


def _monitor_index_for_point(root_x: int, root_y: int) -> int:
    display = Gdk.Display.get_default()
    if display is None:
        return 0
    monitor = display.get_monitor_at_point(root_x, root_y)
    if monitor is None:
        return 0
    for index in range(display.get_n_monitors()):
        if display.get_monitor(index) == monitor:
            return index
    return 0


def _default_size(area: Gdk.Rectangle) -> tuple[int, int]:
    # ~55% of work area, with Windows-like minimums.
    w = min(area.width, max(720, int(area.width * 0.55)))
    h = min(area.height, max(480, int(area.height * 0.55)))
    return w, h


def cascade_position(area: Gdk.Rectangle, w: int, h: int) -> tuple[int, int]:
    """Next cascade origin on this monitor (Win11-like offset stack)."""
    display = Gdk.Display.get_default()
    index = 0
    if display is not None:
        monitor = display.get_monitor_at_point(area.x + area.width // 2, area.y + area.height // 2)
        if monitor is not None:
            for i in range(display.get_n_monitors()):
                if display.get_monitor(i) == monitor:
                    index = i
                    break
    origin = _cascade_next.get(index)
    if origin is None:
        # Start slightly inset from top-left of the work area (not dead center).
        origin = (area.x + max(48, area.width // 8), area.y + max(48, area.height // 10))
    x, y = origin
    x, y, w, h = _clamp_rect(x, y, w, h, area)
    next_x = x + CASCADE_STEP
    next_y = y + CASCADE_STEP
    # Wrap when the next cascade would leave too little room.
    if next_x + w > area.x + area.width - 32 or next_y + h > area.y + area.height - 32:
        next_x = area.x + max(48, area.width // 8)
        next_y = area.y + max(48, area.height // 10)
    _cascade_next[index] = (next_x, next_y)
    return x, y


def _set_geometry(window: Wnck.Window, x: int, y: int, w: int, h: int) -> None:
    if window.is_maximized():
        window.unmaximize()
    gravity = Wnck.WindowGravity.STATIC
    mask = (
        Wnck.WindowMoveResizeMask.X
        | Wnck.WindowMoveResizeMask.Y
        | Wnck.WindowMoveResizeMask.WIDTH
        | Wnck.WindowMoveResizeMask.HEIGHT
    )
    window.set_geometry(gravity, mask, x, y, w, h)


def _same_class_count(key: str, exclude_xid: int) -> int:
    if not key:
        return 0
    screen = Wnck.Screen.get_default()
    screen.force_update()
    count = 0
    for window in screen.get_windows():
        if window.get_xid() == exclude_xid:
            continue
        if window.is_skip_tasklist() or window.get_window_type() in SKIP_TYPES:
            continue
        if window.get_window_type() != Wnck.WindowType.NORMAL:
            continue
        if window.is_minimized():
            continue
        if window_class_key(window) == key:
            count += 1
    return count


def _needs_placement(window: Wnck.Window, area: Gdk.Rectangle) -> tuple[bool, bool]:
    """Return (needs_move_or_resize, is_stub)."""
    x, y, w, h = window.get_geometry()
    too_small = (w < _TINY_WIDTH and h < _TINY_HEIGHT) or min(w, h) < 64
    at_origin = abs(x - area.x) <= _ORIGIN_TOLERANCE and abs(y - area.y) <= _ORIGIN_TOLERANCE
    # GTK/Electron often map at 0,0 with a real size; treat as needing placement.
    return (too_small or at_origin, too_small)


def track_window(window: Wnck.Window) -> None:
    """Keep a live geometry cache for save-on-close (call from shell hooks)."""
    if window.get_window_type() != Wnck.WindowType.NORMAL:
        return
    if window.is_skip_tasklist() or window.get_window_type() in SKIP_TYPES:
        return
    try:
        xid = window.get_xid()
    except Exception:
        return
    key = window_class_key(window)
    if not key:
        return
    rec = _live.get(xid, {"key": key, "x": 0, "y": 0, "w": 800, "h": 600, "maximized": False})
    rec["key"] = key
    try:
        maximized = window.is_maximized()
    except Exception:
        return
    if maximized:
        rec["maximized"] = True
        # Prefer snaplayouts pre-max floating size when present.
        geom = normal_geometry(xid)
        if geom is not None:
            rec["x"], rec["y"], rec["w"], rec["h"] = geom
    elif is_snapped(window):
        rec["maximized"] = False
        geom = normal_geometry(xid)
        if geom is not None:
            rec["x"], rec["y"], rec["w"], rec["h"] = geom
        # else keep last floating
    else:
        try:
            x, y, w, h = window.get_geometry()
        except Exception:
            return
        rec["x"], rec["y"], rec["w"], rec["h"] = x, y, w, h
        rec["maximized"] = False
        remember_normal_geometry(window)
    _live[xid] = rec


def forget_window(xid: int) -> None:
    _placed_xids.discard(xid)
    _live.pop(xid, None)


def persist_closed(xid: int) -> None:
    """Flush cached geometry for a just-closed window."""
    rec = _live.pop(xid, None)
    _placed_xids.discard(xid)
    if rec is None:
        return
    key = rec.get("key") or ""
    if not key:
        return
    w = int(rec.get("w", 0))
    h = int(rec.get("h", 0))
    if w < 100 or h < 80:
        return
    store = _load_store()
    store[key] = {
        "x": int(rec["x"]),
        "y": int(rec["y"]),
        "w": w,
        "h": h,
        "maximized": bool(rec.get("maximized")),
    }
    _save_store(store)


def place_startup_window(window: Wnck.Window) -> bool:
    """Apply Win11-like open placement. Returns True if geometry changed."""
    if window.get_window_type() != Wnck.WindowType.NORMAL:
        return False
    if window.is_skip_tasklist() or window.get_window_type() in SKIP_TYPES:
        return False
    if window.is_fullscreen() or window.is_minimized():
        return False
    try:
        xid = window.get_xid()
    except Exception:
        return False

    area = work_area_for_window(window)
    if area.width < 64 or area.height < 64:
        return False
    if is_snapped(window, area):
        _placed_xids.add(xid)
        return False

    # Already maximized (app or WM restored) — remember and leave.
    if window.is_maximized():
        _placed_xids.add(xid)
        track_window(window)
        return False

    needs, is_stub = _needs_placement(window, area)
    # Second pass after we already placed: only fight stubs that snap back.
    if xid in _placed_xids and not is_stub:
        return False
    if not needs and xid in _placed_xids:
        return False
    if not needs:
        # App chose a real non-origin position — keep it, just track.
        track_window(window)
        _placed_xids.add(xid)
        return False

    key = window_class_key(window)
    store = _load_store()
    saved = store.get(key) if key else None
    others = _same_class_count(key, xid) if key else 0

    x0, y0, w0, h0 = window.get_geometry()
    if is_stub:
        if saved is not None:
            w = int(saved["w"])
            h = int(saved["h"])
        else:
            w, h = _default_size(area)
    else:
        w, h = w0, h0
        if saved is not None and (w < 200 or h < 160):
            w, h = int(saved["w"]), int(saved["h"])

    applied = False
    if saved is not None and others == 0:
        # First visible instance: restore last size/position (and maximize).
        x, y, w, h = _clamp_rect(int(saved["x"]), int(saved["y"]), w, h, area)
        # If saved monitor is gone / off-screen, fall back to cascade on primary.
        primary = work_area_for_point(area.x + 8, area.y + 8)
        if x + w <= area.x or y + h <= area.y:
            x, y = cascade_position(primary, w, h)
            x, y, w, h = _clamp_rect(x, y, w, h, primary)
        _set_geometry(window, x, y, w, h)
        applied = True
        if saved.get("maximized"):
            remember_normal_geometry(window)
            # Defer maximize so size settles first.
            GLib.timeout_add(80, lambda: _deferred_maximize(xid))
    else:
        # New instance or no history: cascade with size (saved size if any).
        if saved is not None:
            w, h = int(saved["w"]), int(saved["h"])
        x, y = cascade_position(area, w, h)
        x, y, w, h = _clamp_rect(x, y, w, h, area)
        _set_geometry(window, x, y, w, h)
        applied = True

    _placed_xids.add(xid)
    track_window(window)
    return applied


def _deferred_maximize(xid: int) -> bool:
    screen = Wnck.Screen.get_default()
    screen.force_update()
    window = next((w for w in screen.get_windows() if w.get_xid() == xid), None)
    if window is None or window.is_maximized():
        return False
    remember_normal_geometry(window)
    window.maximize()
    track_window(window)
    return False


# Back-compat name used by older shell hooks / docs.
def repair_startup_geometry(window: Wnck.Window) -> bool:
    return place_startup_window(window)
