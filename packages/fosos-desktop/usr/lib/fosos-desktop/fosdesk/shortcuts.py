"""Keyboard shortcut catalog and Openbox rc.xml merge."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from .settings_pages import load_kv, save_kv

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "fosos-desktop"
SYSTEM_RC = Path("/usr/share/fosos-desktop/openbox/rc.xml")
USER_RC = CONFIG / "openbox" / "rc.xml"
KV_NAME = "shortcuts"

BEGIN_MARKER = "<!-- FOSOS-SHORTCUTS-BEGIN -->"
END_MARKER = "<!-- FOSOS-SHORTCUTS-END -->"

ShortcutAction = tuple[str, str, str, str, str]

SHORTCUT_ACTIONS: list[ShortcutAction] = [
    ("start", "Start menu", "W-space", "execute", "fosos-shell --toggle-start"),
    ("files", "Files", "W-e", "execute", "fosos-files"),
    ("terminal", "Terminal", "C-A-t", "execute", "fosos-terminal"),
    ("taskmgr", "Task Manager", "C-S-Escape", "execute", "fosos-taskmgr"),
    ("settings", "Settings", "W-i", "execute", "fosos-settings"),
    ("lock", "Lock", "W-l", "execute", "fosos-lock"),
    ("run", "Run", "W-r", "execute", "fosos-shell --run"),
    ("quick_links", "Quick links", "W-x", "execute", "fosos-shell --quick-links"),
    ("quick_settings", "Quick settings", "W-a", "execute", "fosos-shell --quick-settings"),
    ("notification_center", "Notification center", "W-n", "execute", "fosos-shell --notification-center"),
    ("clipboard", "Clipboard history", "W-v", "execute", "fosos-shell --clipboard-history"),
    ("screenshot_full", "Screenshot (full screen)", "Print", "execute", "fosos-screenshot -f"),
    ("screenshot_region", "Screenshot (region)", "W-S-s", "execute", "fosos-screenshot -r"),
    ("task_view", "Task view", "W-Tab", "execute", "fosos-shell --task-view"),
    ("snap_layouts", "Snap layouts", "W-z", "execute", "fosos-shell --snap-layouts"),
    ("show_desktop", "Show desktop", "W-d", "ob", '<action name="ToggleShowDesktop"/>'),
    ("snap_max", "Snap maximize", "W-Up", "execute", "fosos-shell --snap-maximize"),
    ("snap_down", "Snap down", "W-Down", "execute", "fosos-shell --snap-down"),
    ("snap_left", "Snap left", "W-Left", "execute", "fosos-shell --snap-left"),
    ("snap_right", "Snap right", "W-Right", "execute", "fosos-shell --snap-right"),
    ("close_window", "Close window", "A-F4", "ob", '<action name="Close"/>'),
]

# Pinned apps, desktops, and Alt+Tab — inside the shortcuts region but not user-configurable.
_STATIC_KEYBINDS_XML = """
    <!-- Win+1…9 launch/cycle pinned apps (Windows 11). Desktops: Ctrl+Win+1–4. -->
    <keybind key="W-1">
      <action name="Execute"><command>fosos-shell --pin-activate 1</command></action>
    </keybind>
    <keybind key="W-2">
      <action name="Execute"><command>fosos-shell --pin-activate 2</command></action>
    </keybind>
    <keybind key="W-3">
      <action name="Execute"><command>fosos-shell --pin-activate 3</command></action>
    </keybind>
    <keybind key="W-4">
      <action name="Execute"><command>fosos-shell --pin-activate 4</command></action>
    </keybind>
    <keybind key="W-5">
      <action name="Execute"><command>fosos-shell --pin-activate 5</command></action>
    </keybind>
    <keybind key="W-6">
      <action name="Execute"><command>fosos-shell --pin-activate 6</command></action>
    </keybind>
    <keybind key="W-7">
      <action name="Execute"><command>fosos-shell --pin-activate 7</command></action>
    </keybind>
    <keybind key="W-8">
      <action name="Execute"><command>fosos-shell --pin-activate 8</command></action>
    </keybind>
    <keybind key="W-9">
      <action name="Execute"><command>fosos-shell --pin-activate 9</command></action>
    </keybind>
    <keybind key="C-W-1">
      <action name="GoToDesktop"><to>1</to></action>
    </keybind>
    <keybind key="C-W-2">
      <action name="GoToDesktop"><to>2</to></action>
    </keybind>
    <keybind key="C-W-3">
      <action name="GoToDesktop"><to>3</to></action>
    </keybind>
    <keybind key="C-W-4">
      <action name="GoToDesktop"><to>4</to></action>
    </keybind>
    <keybind key="C-A-Left">
      <action name="GoToDesktop"><to>left</to><wrap>no</wrap></action>
    </keybind>
    <keybind key="C-A-Right">
      <action name="GoToDesktop"><to>right</to><wrap>no</wrap></action>
    </keybind>
    <keybind key="C-W-Left">
      <action name="GoToDesktop"><to>left</to><wrap>no</wrap></action>
    </keybind>
    <keybind key="C-W-Right">
      <action name="GoToDesktop"><to>right</to><wrap>no</wrap></action>
    </keybind>
    <keybind key="W-S-Left">
      <action name="SendToDesktop"><to>left</to><wrap>no</wrap></action>
    </keybind>
    <keybind key="W-S-Right">
      <action name="SendToDesktop"><to>right</to><wrap>no</wrap></action>
    </keybind>
    <keybind key="W-S-1">
      <action name="SendToDesktop"><to>1</to></action>
    </keybind>
    <keybind key="W-S-2">
      <action name="SendToDesktop"><to>2</to></action>
    </keybind>
    <keybind key="W-S-3">
      <action name="SendToDesktop"><to>3</to></action>
    </keybind>
    <keybind key="W-S-4">
      <action name="SendToDesktop"><to>4</to></action>
    </keybind>

    <keybind key="A-Tab">
      <action name="Execute"><command>fosos-shell --alt-tab next</command></action>
    </keybind>
    <keybind key="A-S-Tab">
      <action name="Execute"><command>fosos-shell --alt-tab prev</command></action>
    </keybind>
"""

_CLIENT_MENU_KEYBIND = """
    <keybind key="A-space">
      <action name="ShowMenu"><menu>client-menu</menu></action>
    </keybind>
"""

_SCREENSHOT_PRINT_KEYBIND = """
    <keybind key="S-Print">
      <action name="Execute"><command>fosos-screenshot -r</command></action>
    </keybind>
"""

_ACTION_BY_ID = {row[0]: row for row in SHORTCUT_ACTIONS}


def default_map() -> dict[str, str]:
    return {action_id: default_key for action_id, _, default_key, _, _ in SHORTCUT_ACTIONS}


def load_shortcuts() -> dict[str, str]:
    return load_kv(KV_NAME, default_map())


def save_shortcuts(values: dict[str, str]) -> None:
    merged = default_map()
    for action_id, key in values.items():
        if action_id in merged and key.strip():
            merged[action_id] = key.strip()
    save_kv(KV_NAME, merged)


def find_conflicts(values: dict[str, str]) -> list[tuple[str, list[str]]]:
    by_key: dict[str, list[str]] = {}
    for action_id, key in values.items():
        if action_id not in _ACTION_BY_ID:
            continue
        key = (key or "").strip()
        if not key:
            continue
        by_key.setdefault(key, []).append(action_id)
    # A-F1 is a fixed alias for start; ignore it for conflict detection.
    return sorted((key, ids) for key, ids in by_key.items() if len(ids) > 1)


def reconfigure_openbox() -> bool:
    if shutil.which("openbox") is None:
        return False
    return subprocess.run(["openbox", "--reconfigure"], check=False).returncode == 0


def _keybind_xml(key: str, kind: str, payload: str) -> str:
    if kind == "execute":
        return (
            f'    <keybind key="{key}">\n'
            f"      <action name=\"Execute\"><command>{payload}</command></action>\n"
            f"    </keybind>"
        )
    body = payload.strip()
    if not body.startswith("<action"):
        body = f'<action name="{body}"/>'
    return f'    <keybind key="{key}">\n      {body}\n    </keybind>'


def _action_key(values: dict[str, str], action_id: str) -> str:
    default = _ACTION_BY_ID[action_id][2]
    return (values.get(action_id) or default).strip() or default


def _render_shortcuts_block(values: dict[str, str]) -> str:
    lines: list[str] = []
    lines.append("    <!-- Start: Super alone via xcape → Alt+F1; Super+Space remains an alias. -->")
    start_id, _, _, start_kind, start_payload = _ACTION_BY_ID["start"]
    start_key = _action_key(values, start_id)
    lines.append(_keybind_xml(start_key, start_kind, start_payload))
    lines.append(_keybind_xml("A-F1", start_kind, start_payload))

    pre_static = (
        "files",
        "terminal",
        "taskmgr",
        "settings",
        "lock",
        "run",
        "quick_links",
        "quick_settings",
        "notification_center",
        "clipboard",
        "screenshot_full",
    )
    for action_id in pre_static:
        _, _, _, kind, payload = _ACTION_BY_ID[action_id]
        lines.append(_keybind_xml(_action_key(values, action_id), kind, payload))

    lines.append(_SCREENSHOT_PRINT_KEYBIND.strip())
    _, _, _, kind, payload = _ACTION_BY_ID["screenshot_region"]
    lines.append(_keybind_xml(_action_key(values, "screenshot_region"), kind, payload))

    lines.append(_STATIC_KEYBINDS_XML.strip())

    post_static = (
        "task_view",
        "snap_layouts",
        "close_window",
        "show_desktop",
        "snap_max",
        "snap_down",
        "snap_left",
        "snap_right",
    )
    for action_id in post_static:
        _, _, _, kind, payload = _ACTION_BY_ID[action_id]
        lines.append(_keybind_xml(_action_key(values, action_id), kind, payload))

    lines.append(_CLIENT_MENU_KEYBIND.strip())
    return "\n\n".join(lines)


def _read_system_rc() -> str:
    path = SYSTEM_RC if SYSTEM_RC.is_file() else USER_RC
    return path.read_text(encoding="utf-8")


def _merge_user_rc(system_text: str, block: str) -> str | None:
    if BEGIN_MARKER in system_text and END_MARKER in system_text:
        pattern = re.compile(re.escape(BEGIN_MARKER) + r"[\s\S]*?" + re.escape(END_MARKER), re.MULTILINE)
        replacement = f"{BEGIN_MARKER}\n{block}\n    {END_MARKER}"
        return pattern.sub(replacement, system_text, count=1)

    match = re.search(r"(<chainQuitKey>[^<]+</chainQuitKey>\s*)", system_text)
    if not match:
        return None
    start = match.end()
    end_match = re.search(r"\s*</keyboard>", system_text[start:])
    if not end_match:
        return None
    end = start + end_match.start()
    wrapped = f"{BEGIN_MARKER}\n{block}\n    {END_MARKER}"
    return system_text[:start] + wrapped + system_text[end:]


def apply_shortcuts(values: dict[str, str] | None = None) -> bool:
    merged = default_map()
    if values:
        for action_id, key in values.items():
            if action_id in merged and (key or "").strip():
                merged[action_id] = key.strip()
    else:
        merged.update({k: v for k, v in load_shortcuts().items() if k in merged})

    if find_conflicts(merged):
        return False

    try:
        system_text = _read_system_rc()
    except OSError:
        return False

    block = _render_shortcuts_block(merged)
    merged_text = _merge_user_rc(system_text, block)
    if merged_text is None:
        return False

    try:
        USER_RC.parent.mkdir(parents=True, exist_ok=True)
        USER_RC.write_text(merged_text, encoding="utf-8")
    except OSError:
        return False

    reconfigure_openbox()
    return True