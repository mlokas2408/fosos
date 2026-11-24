"""Night light via xrandr display gamma (no extra dependencies)."""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime

from .settings_pages import load_kv, save_kv, truthy

KV_NAME = "night-light"

DEFAULTS: dict[str, str] = {
    "enabled": "0",
    "temperature": "4500",
    "schedule": "0",
    "start_hour": "20",
    "end_hour": "7",
}


def load_night_light() -> dict[str, str]:
    return load_kv(KV_NAME, dict(DEFAULTS))


def save_night_light(values: dict[str, str]) -> None:
    merged = dict(DEFAULTS)
    for key, value in values.items():
        if key in merged:
            merged[key] = value.strip()
    save_kv(KV_NAME, merged)


def temp_to_gamma(kelvin: int) -> tuple[float, float, float]:
    """Approximate RGB gamma multipliers for a color temperature (1000–6500 K)."""
    k = max(1000, min(6500, int(kelvin)))
    if k >= 6500:
        return (1.0, 1.0, 1.0)
    t = (6500 - k) / 5500.0
    red = 1.0
    green = max(0.55, 1.0 - 0.22 * t)
    blue = max(0.35, 1.0 - 0.65 * t)
    return (red, green, blue)


def list_outputs() -> list[str]:
    if shutil.which("xrandr") is None:
        return []
    try:
        result = subprocess.run(
            ["xrandr", "--query"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    outputs: list[str] = []
    for line in result.stdout.splitlines():
        match = re.match(r"^(\S+)\s+connected\b", line)
        if match:
            outputs.append(match.group(1))
    return outputs


def apply_gamma(red: float, green: float, blue: float) -> bool:
    if shutil.which("xrandr") is None:
        return False
    outputs = list_outputs()
    if not outputs:
        return False
    ok = True
    spec = f"{red:g}:{green:g}:{blue:g}"
    for name in outputs:
        code = subprocess.run(
            ["xrandr", "--output", name, "--gamma", spec],
            check=False,
        ).returncode
        if code != 0:
            ok = False
    return ok


def _schedule_active(start_hour: int, end_hour: int, hour: int) -> bool:
    start_hour = start_hour % 24
    end_hour = end_hour % 24
    if start_hour == end_hour:
        return True
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def _parse_int(value: str | None, default: int, lo: int, hi: int) -> int:
    try:
        number = int((value or "").strip())
    except ValueError:
        return default
    return max(lo, min(hi, number))


def apply_night_light() -> bool:
    prefs = load_night_light()
    if not truthy(prefs.get("enabled"), default=False):
        return apply_gamma(1.0, 1.0, 1.0)

    if truthy(prefs.get("schedule"), default=False):
        start = _parse_int(prefs.get("start_hour"), 20, 0, 23)
        end = _parse_int(prefs.get("end_hour"), 7, 0, 23)
        hour = datetime.now().hour
        if not _schedule_active(start, end, hour):
            return apply_gamma(1.0, 1.0, 1.0)

    temp = _parse_int(prefs.get("temperature"), 4500, 1000, 6500)
    red, green, blue = temp_to_gamma(temp)
    return apply_gamma(red, green, blue)


def restore_session_night_light() -> bool:
    return apply_night_light()