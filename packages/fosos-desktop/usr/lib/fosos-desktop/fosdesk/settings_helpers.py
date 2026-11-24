"""Shared Settings UI helpers (Win11-style rows) and display/audio probes."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from .ui import add_classes, button, label


def settings_card(*children: Gtk.Widget, spacing: int = 0) -> Gtk.Box:
    card = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing), "fos-settings-card")
    for child in children:
        card.pack_start(child, False, False, 0)
    return card


def settings_row(
    title: str,
    subtitle: str = "",
    *,
    trailing: Gtk.Widget | None = None,
    icon_name: str | None = None,
) -> Gtk.Box:
    """One settings line: title/subtitle left, control right (Windows Settings style)."""
    row = add_classes(Gtk.Box(spacing=12), "fos-settings-row")
    if icon_name:
        from .ui import icon

        row.pack_start(icon(icon_name, 18), False, False, 0)
    texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    texts.set_valign(Gtk.Align.CENTER)
    texts.set_hexpand(True)
    texts.pack_start(label(title, "fos-text", "fos-strong", ellipsize=True), False, False, 0)
    if subtitle:
        texts.pack_start(label(subtitle, "fos-small", "fos-muted", ellipsize=True), False, False, 0)
    row.pack_start(texts, True, True, 0)
    if trailing is not None:
        trailing.set_valign(Gtk.Align.CENTER)
        row.pack_end(trailing, False, False, 0)
    return row


def settings_section(title: str, *rows: Gtk.Widget) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    if title:
        box.pack_start(label(title, "fos-label"), False, False, 0)
    card = settings_card()
    for index, row in enumerate(rows):
        card.pack_start(row, False, False, 0)
        if index < len(rows) - 1:
            card.pack_start(add_classes(Gtk.Box(), "fos-settings-row-sep"), False, False, 0)
    box.pack_start(card, False, False, 0)
    return box


def run(argv: list[str], timeout: float = 3.0) -> str | None:
    if shutil.which(argv[0]) is None:
        return None
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


@dataclass
class DisplayOutput:
    name: str
    connected: bool
    primary: bool
    current: str | None = None
    modes: list[str] = field(default_factory=list)
    rotation: str = "normal"


def list_displays() -> list[DisplayOutput]:
    output = run(["xrandr", "--query"]) or ""
    displays: list[DisplayOutput] = []
    current: DisplayOutput | None = None
    for line in output.splitlines():
        match = re.match(r"^(\S+)\s+(connected|disconnected)(.*)$", line)
        if match:
            name, state, rest = match.groups()
            current = DisplayOutput(
                name=name,
                connected=state == "connected",
                primary="primary" in rest,
                rotation="normal",
            )
            for rot in ("left", "right", "inverted", "normal"):
                if f" {rot} " in f" {rest} ":
                    # xrandr prints orientation in parentheses block; keep default.
                    pass
            geom = re.search(r"(\d+)x(\d+)\+\d+\+\d+", rest)
            if geom:
                current.current = f"{geom.group(1)}x{geom.group(2)}"
            # Orientation tokens after geometry in connected line.
            orient = re.search(r"\)\s+(\w+)\s+\(", rest)
            if orient and orient.group(1) in ("normal", "left", "right", "inverted"):
                current.rotation = orient.group(1)
            displays.append(current)
            continue
        if current is None or not line.startswith("   "):
            continue
        parts = line.split()
        if not parts:
            continue
        mode = parts[0]
        if "x" not in mode:
            continue
        try:
            width = int(mode.split("x", 1)[0])
        except ValueError:
            continue
        if width < 800:
            continue
        if mode not in current.modes:
            current.modes.append(mode)
        if "*" in line:
            current.current = mode
    return displays


def set_display_mode(output: str, mode: str) -> bool:
    return subprocess.run(["xrandr", "--output", output, "--mode", mode], check=False).returncode == 0


def set_display_rotation(output: str, rotation: str) -> bool:
    if rotation not in ("normal", "left", "right", "inverted"):
        return False
    return subprocess.run(["xrandr", "--output", output, "--rotate", rotation], check=False).returncode == 0


def set_display_primary(output: str) -> bool:
    return subprocess.run(["xrandr", "--output", output, "--primary"], check=False).returncode == 0


@dataclass
class AudioNode:
    id: str
    name: str
    default: bool = False


def list_audio_nodes(section: str) -> list[AudioNode]:
    """Parse wpctl status for Sinks or Sources."""
    output = run(["wpctl", "status"]) or ""
    nodes: list[AudioNode] = []
    in_section = False
    # Sections look like " ├─ Sinks:" / " ├─ Sources:"
    header = section.lower()
    for line in output.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if lower.startswith("├─") or lower.startswith("└─") or lower.endswith(":"):
            label_text = stripped.lstrip("├─└─ ").rstrip(":").lower()
            in_section = label_text == header
            continue
        if not in_section:
            continue
        if "Video" in stripped or "Settings" in stripped:
            break
        match = re.search(r"(\*?)\s*(\d+)\.\s+(.+)", stripped)
        if not match:
            continue
        default = match.group(1) == "*"
        node_id = match.group(2)
        name = match.group(3).strip()
        name = re.sub(r"\s*\[vol:.*$", "", name).strip()
        nodes.append(AudioNode(id=node_id, name=name, default=default))
    return nodes


def set_default_audio(node_id: str) -> bool:
    return subprocess.run(["wpctl", "set-default", node_id], check=False).returncode == 0


def hibernate_available() -> bool:
    path = "/sys/power/disk"
    try:
        text = open(path, encoding="utf-8").read().strip().lower()
    except OSError:
        return False
    return "disk" in text or "[disk]" in text or "platform" in text or "shutdown" in text
