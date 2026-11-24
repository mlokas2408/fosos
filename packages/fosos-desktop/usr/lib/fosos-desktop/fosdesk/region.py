"""Regional locale helpers for clock, calendar and numbers."""

from __future__ import annotations

import locale
import os
import subprocess
from datetime import datetime
from pathlib import Path

# Friendly labels for common UTF-8 locales (shown when installed).
LOCALE_LABELS: dict[str, str] = {
    "en_US.UTF-8": "English (United States)",
    "en_GB.UTF-8": "English (United Kingdom)",
    "hr_HR.UTF-8": "Croatian (Croatia)",
    "pl_PL.UTF-8": "Polish (Poland)",
    "de_DE.UTF-8": "German (Germany)",
    "fr_FR.UTF-8": "French (France)",
    "es_ES.UTF-8": "Spanish (Spain)",
    "it_IT.UTF-8": "Italian (Italy)",
    "pt_BR.UTF-8": "Portuguese (Brazil)",
    "pt_PT.UTF-8": "Portuguese (Portugal)",
    "nl_NL.UTF-8": "Dutch (Netherlands)",
    "sv_SE.UTF-8": "Swedish (Sweden)",
    "nb_NO.UTF-8": "Norwegian (Bokmål)",
    "da_DK.UTF-8": "Danish (Denmark)",
    "fi_FI.UTF-8": "Finnish (Finland)",
    "cs_CZ.UTF-8": "Czech (Czechia)",
    "sk_SK.UTF-8": "Slovak (Slovakia)",
    "hu_HU.UTF-8": "Hungarian (Hungary)",
    "ro_RO.UTF-8": "Romanian (Romania)",
    "uk_UA.UTF-8": "Ukrainian (Ukraine)",
    "ru_RU.UTF-8": "Russian (Russia)",
    "ja_JP.UTF-8": "Japanese (Japan)",
    "ko_KR.UTF-8": "Korean (Korea)",
    "zh_CN.UTF-8": "Chinese (Simplified)",
    "zh_TW.UTF-8": "Chinese (Traditional)",
}


def _normalize_name(name: str) -> str:
    raw = name.strip()
    if not raw:
        return ""
    if raw.lower() in ("c", "posix"):
        return "C"
    # locale -a often prints en_US.utf8; prefer .UTF-8 form.
    if raw.endswith(".utf8"):
        return raw[: -len(".utf8")] + ".UTF-8"
    if raw.endswith(".utf-8"):
        return raw[: -len(".utf-8")] + ".UTF-8"
    return raw


def installed_locales() -> list[str]:
    """Return generated locale names (UTF-8 preferred), sorted."""
    names: set[str] = set()
    try:
        result = subprocess.run(
            ["locale", "-a"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if result.returncode == 0 and result.stdout:
            for line in result.stdout.splitlines():
                normalized = _normalize_name(line)
                if normalized and ("UTF-8" in normalized or normalized == "C"):
                    names.add(normalized)
    except (OSError, subprocess.TimeoutExpired):
        pass
    # Always allow current LANG if set.
    for key in ("LC_ALL", "LANG"):
        value = os.environ.get(key, "").strip()
        if value:
            names.add(_normalize_name(value))
    return sorted(names)


def locale_choices() -> list[tuple[str, str]]:
    """(code, label) pairs for Settings — known labels first, then the rest."""
    available = installed_locales()
    available_set = set(available)
    choices: list[tuple[str, str]] = []
    for code, label in LOCALE_LABELS.items():
        if code in available_set:
            choices.append((code, f"{label} — {code}"))
    for code in available:
        if code not in LOCALE_LABELS and code != "C":
            choices.append((code, code))
    if not choices:
        current = current_locale()
        choices.append((current, current))
    return choices


def current_locale() -> str:
    for key in ("LC_ALL", "LANG"):
        value = os.environ.get(key, "").strip()
        if value:
            return _normalize_name(value)
    try:
        language, encoding = locale.getlocale()
        if language:
            if encoding:
                return _normalize_name(f"{language}.{encoding}")
            return language
    except (TypeError, ValueError):
        pass
    return "en_US.UTF-8"


def apply_locale(name: str) -> bool:
    """Set process locale and environment. Returns False if the locale is missing."""
    name = _normalize_name(name)
    if not name:
        return False
    candidates = [name]
    if name.endswith(".UTF-8"):
        candidates.append(name[: -len(".UTF-8")] + ".utf8")
    ok = False
    for candidate in candidates:
        try:
            locale.setlocale(locale.LC_ALL, candidate)
            ok = True
            break
        except locale.Error:
            continue
    if not ok:
        return False
    for key in (
        "LANG",
        "LC_TIME",
        "LC_NUMERIC",
        "LC_MONETARY",
        "LC_MEASUREMENT",
        "LC_PAPER",
        "LC_NAME",
        "LC_ADDRESS",
        "LC_TELEPHONE",
        "LC_IDENTIFICATION",
    ):
        os.environ[key] = name
    os.environ.pop("LC_ALL", None)
    return True


def write_user_locale_conf(name: str) -> None:
    """Persist LANG for next login (systemd user / pam_env style)."""
    name = _normalize_name(name)
    path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "locale.conf"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"LANG={name}\n", encoding="utf-8")
    except OSError:
        pass


def _uses_am_pm() -> bool:
    try:
        ampm = locale.nl_langinfo(locale.T_FMT_AMPM)
        return bool(ampm and str(ampm).strip())
    except (AttributeError, ValueError, locale.Error):
        return False


def format_time(now: datetime | None = None) -> str:
    stamp = now or datetime.now()
    if _uses_am_pm():
        text = stamp.strftime("%I:%M %p")
        return text.lstrip("0") if text.startswith("0") else text
    return stamp.strftime("%H:%M")


def format_date_short(now: datetime | None = None) -> str:
    stamp = now or datetime.now()
    return stamp.strftime("%a, %b %-d")


def format_weekday(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%A")


def format_date_full(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%-d %B %Y")


def format_number(value: float, digits: int = 2) -> str:
    try:
        return locale.format_string(f"%.{digits}f", value, grouping=True)
    except (ValueError, locale.Error):
        return f"{value:.{digits}f}"
