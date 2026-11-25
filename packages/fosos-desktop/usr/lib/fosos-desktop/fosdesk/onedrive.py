"""Local OneDrive folder via Debian's onedrive sync client.

The client has no GUI. Sign-in uses ``onedrive --auth-files``: it writes a
Microsoft login URL, then waits until we store the blank-page redirect.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from . import apps as appmod
from .settings_helpers import settings_row, settings_section
from .ui import FosDialog, add_classes, button, clear, fos_alert, fos_confirm, label

CONFIG_DIR = Path.home() / ".config" / "onedrive"
CONFIG_FILE = CONFIG_DIR / "config"
TOKEN_FILE = CONFIG_DIR / "refresh_token"
SERVICE = "onedrive.service"
_ACTIVE = {"active", "activating"}


def _run(argv: list[str], timeout: float = 20) -> tuple[int, str]:
    if not argv or shutil.which(argv[0]) is None:
        return 127, ""
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return result.returncode, ((result.stdout or "") + (result.stderr or "")).strip()


def client_installed() -> bool:
    return shutil.which("onedrive") is not None


def _read_config() -> str:
    try:
        return CONFIG_FILE.read_text(encoding="utf-8")
    except OSError:
        return ""


def config_value(key: str) -> str | None:
    for line in _read_config().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue
        if "=" not in stripped:
            continue
        name, raw = stripped.split("=", 1)
        if name.strip() != key:
            continue
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        return value
    return None


def _upsert(text: str, key: str, value: str) -> str:
    line_out = f'{key} = "{value}"'
    found = False
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        name = ""
        if stripped and not stripped.startswith("#") and not stripped.startswith(";") and "=" in stripped:
            name = stripped.split("=", 1)[0].strip()
        if name == key:
            out.append(line_out)
            found = True
        else:
            out.append(line)
    if not found:
        if out and out[-1].strip():
            out.append("")
        out.append(line_out)
    body = "\n".join(out)
    if not body.endswith("\n"):
        body += "\n"
    return body


def ensure_config() -> None:
    """Create the client config. Leave an existing sync folder alone."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, 0o700)
    text = _read_config()
    if config_value("sync_dir") is None:
        text = _upsert(text, "sync_dir", "~/OneDrive")
    text = _upsert(text, "notify_file_actions", "false")
    CONFIG_FILE.write_text(text, encoding="utf-8")
    os.chmod(CONFIG_FILE, 0o600)


def configured_sync_dir() -> Path:
    raw = config_value("sync_dir") or "~/OneDrive"
    return Path(os.path.expanduser(raw))


def existing_sync_dir() -> Path | None:
    path = configured_sync_dir()
    try:
        return path if path.is_dir() else None
    except OSError:
        return None


def display_sync_dir() -> str:
    path = configured_sync_dir()
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def has_token() -> bool:
    try:
        return TOKEN_FILE.is_file() and TOKEN_FILE.stat().st_size > 0
    except OSError:
        return False


def service_state() -> str:
    """active, activating, inactive, failed, or unavailable."""
    code, out = _run(["systemctl", "--user", "is-active", SERVICE], timeout=8)
    if code == 127 or not out:
        return "unavailable"
    word = out.splitlines()[0].strip()
    if word in {"active", "activating", "inactive", "failed", "deactivating"}:
        return word
    return "unavailable"


def _systemctl(*args: str, timeout: float = 30) -> tuple[bool, str]:
    code, out = _run(["systemctl", "--user", *args], timeout=timeout)
    return code == 0, out


def stop_service() -> None:
    _systemctl("stop", SERVICE)


def start_service() -> tuple[bool, str]:
    """Enable the user service and start it.

    The Debian unit sleeps 15 seconds before the client runs. ``--no-block``
    returns as soon as systemd accepts the start, then we wait until the unit
    is activating so Settings does not sit frozen for that sleep.
    """
    try:
        configured_sync_dir().mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, str(exc)
    ok, out = _systemctl("enable", SERVICE)
    if not ok:
        return False, out
    ok, out = _systemctl("start", "--no-block", SERVICE)
    if not ok:
        return False, out
    for _ in range(20):
        state = service_state()
        if state == "failed":
            _code, detail = _run(["systemctl", "--user", "status", "--no-pager", SERVICE], timeout=8)
            return False, detail or out
        if state in _ACTIVE:
            return True, out
        time.sleep(0.25)
    return True, out


def disable_service() -> tuple[bool, str]:
    return _systemctl("disable", "--now", SERVICE)


def logout_client() -> tuple[bool, str]:
    code, out = _run(["onedrive", "--logout"], timeout=60)
    if code == 0 or not has_token():
        return True, out
    if "already running" in out.lower():
        stop_service()
        code, out = _run(["onedrive", "--logout"], timeout=60)
        if code == 0 or not has_token():
            return True, out
    return False, out


def _open_browser(url: str) -> bool:
    for argv in (["firefox-esr", url], ["xdg-open", url], ["gio", "open", url]):
        if appmod.spawn(argv):
            return True
    return False


def _tail(text: str, limit: int = 1200) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def _parent_window(widget: Gtk.Widget) -> Gtk.Window | None:
    top = widget.get_toplevel()
    return top if isinstance(top, Gtk.Window) else None


def _explanation() -> str:
    text = (
        f"Signing in downloads your whole OneDrive into {display_sync_dir()} and keeps it updated. "
        "Files stay on this PC when you are offline."
    )
    if appmod.is_live():
        text += " On this live session that copy lasts until you reboot."
    return text


def _sign_in(parent: Gtk.Window | None) -> tuple[bool, str]:
    """Run the browser sign-in. Returns (signed_in, service_error)."""
    if not client_installed():
        fos_alert(parent, "OneDrive", "The onedrive package is not installed.")
        return False, ""
    try:
        ensure_config()
    except OSError as exc:
        fos_alert(parent, "OneDrive", f"Could not write the OneDrive config.\n\n{exc}")
        return False, ""
    stop_service()

    auth_path = CONFIG_DIR / "fosos-auth-url"
    response_path = CONFIG_DIR / "fosos-auth-response"
    log_path = CONFIG_DIR / "fosos-auth.log"
    for path in (auth_path, response_path):
        path.unlink(missing_ok=True)

    log = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 - closed in cleanup
    proc = subprocess.Popen(  # noqa: S603 - fixed client argv
        ["onedrive", "--auth-files", f"{auth_path}:{response_path}"],
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    state = {
        "closed": False,
        "poll": 0,
        "opened": False,
        "submitted": False,
        "ok": False,
        "service_error": "",
    }

    dialog = FosDialog(parent, title="Sign in to OneDrive", width=480)
    dialog.add_body_text(
        "Firefox opens a Microsoft sign-in page. After you approve access, the browser shows a blank page. "
        "Copy the full address from the address bar and paste it here. "
        "Some work or school accounts need an administrator to approve the OneDrive client first."
    )
    status = label("Waiting for the sign-in link…", "fos-small", "fos-muted")
    status.set_line_wrap(True)
    status.set_max_width_chars(52)
    status.set_xalign(0)
    dialog.content.pack_start(status, False, False, 0)
    link = label("", "fos-small")
    link.set_line_wrap(True)
    link.set_max_width_chars(52)
    link.set_selectable(True)
    link.set_xalign(0)
    link.set_no_show_all(True)
    dialog.content.pack_start(link, False, False, 0)
    entry = add_classes(Gtk.Entry(), "fos-input")
    entry.set_placeholder_text("Paste the browser address")
    entry.set_hexpand(True)
    dialog.content.pack_start(entry, False, False, 0)

    def read_log() -> str:
        log.flush()
        try:
            return log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def show_client_error(prefix: str) -> None:
        detail = _tail(read_log())
        status.set_text(prefix if not detail else f"{prefix}\n\n{detail}")

    def finish_submit() -> bool:
        if proc.poll() is None:
            return True
        state["poll"] = 0
        if has_token() or "Sync Engine Initialised" in read_log():
            ok, err = start_service()
            state["ok"] = True
            state["service_error"] = "" if ok else (err or "Could not start sync.")
            dialog.respond(True)
            return False
        entry.set_sensitive(True)
        continue_btn.set_sensitive(True)
        state["submitted"] = False
        show_client_error("Microsoft did not accept that address. Close this and try Sign in again.")
        return False

    def poll() -> bool:
        if state["closed"]:
            state["poll"] = 0
            return False
        if state["submitted"]:
            return finish_submit()
        if proc.poll() is not None:
            state["poll"] = 0
            show_client_error("Sign-in stopped before the browser opened.")
            return False
        if auth_path.is_file() and not state["opened"]:
            url = auth_path.read_text(encoding="utf-8", errors="replace").strip().strip('"')
            if url.startswith("http"):
                state["opened"] = True
                state["poll"] = 0
                if _open_browser(url):
                    status.set_text("After the blank page appears, paste its address here.")
                else:
                    status.set_text("Open this address in a browser. After the blank page, paste that address here.")
                link.set_text(url)
                link.show()
                return False
        return True

    def stop_poll() -> None:
        source = state["poll"]
        state["poll"] = 0
        if source:
            GLib.source_remove(source)

    def start_poll() -> None:
        stop_poll()
        state["poll"] = GLib.timeout_add(250, poll)

    def on_continue(_widget=None) -> None:
        text = entry.get_text().strip()
        if not text.startswith("http"):
            status.set_text("Paste the full address from the browser, starting with https://")
            return
        if proc.poll() is not None:
            show_client_error("The sign-in client already exited. Close this and try again.")
            return
        part = response_path.with_name(response_path.name + ".part")
        part.write_text(text + "\n", encoding="utf-8")
        os.chmod(part, 0o600)
        part.replace(response_path)
        state["submitted"] = True
        entry.set_sensitive(False)
        continue_btn.set_sensitive(False)
        status.set_text("Signing in…")
        link.hide()
        start_poll()

    continue_btn = button("Continue", variant="default", size="sm")
    continue_btn.set_can_focus(True)
    continue_btn.connect("clicked", on_continue)
    entry.connect("activate", on_continue)
    dialog.add_action("Cancel", None, variant="ghost")
    dialog.footer.pack_start(continue_btn, False, False, 0)

    original_respond = dialog.respond

    def respond(value) -> None:
        if value is None:
            state["closed"] = True
            stop_poll()
            if proc.poll() is None:
                proc.terminate()
        original_respond(value)

    dialog.respond = respond  # type: ignore[method-assign]
    start_poll()
    try:
        dialog.run()
    finally:
        state["closed"] = True
        stop_poll()
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        log.close()
        for path in (auth_path, response_path, log_path, response_path.with_name(response_path.name + ".part")):
            path.unlink(missing_ok=True)
    return state["ok"], state["service_error"]


def accounts_section(status_cb) -> Gtk.Box:
    """OneDrive block for Settings → Accounts. Rebuilds itself after each action."""
    host = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

    def refresh() -> None:
        clear(host)
        if not client_installed():
            subtitle = "The OneDrive client is not installed."
        elif not has_token():
            subtitle = "Not signed in"
        elif service_state() in _ACTIVE:
            subtitle = f"Syncing {display_sync_dir()}"
        elif service_state() == "failed":
            subtitle = "Signed in. Sync stopped because of an error."
        else:
            subtitle = "Sync is paused. It starts again the next time you sign in to this PC."

        host.pack_start(
            settings_section("OneDrive", settings_row("Status", subtitle, icon_name="folder-remote-symbolic")),
            False,
            False,
            0,
        )
        actions = Gtk.Box(spacing=8)
        if not has_token():
            sign = button("Sign in", variant="default", size="sm")
            sign.connect("clicked", lambda btn: _on_sign_in(btn))
            actions.pack_start(sign, False, False, 0)
        else:
            open_btn = button("Open folder", variant="outline", size="sm")
            open_btn.connect("clicked", lambda _b: _on_open())
            actions.pack_start(open_btn, False, False, 0)
            if service_state() in _ACTIVE:
                pause = button("Pause", variant="outline", size="sm")
                pause.connect("clicked", lambda _b: _on_pause())
                actions.pack_start(pause, False, False, 0)
            else:
                resume = button("Resume", variant="default", size="sm")
                resume.connect("clicked", lambda _b: _on_resume())
                actions.pack_start(resume, False, False, 0)
            sign_out = button("Sign out", variant="outline", size="sm")
            sign_out.connect("clicked", lambda btn: _on_sign_out(btn))
            actions.pack_start(sign_out, False, False, 0)
        host.pack_start(actions, False, False, 0)
        note = label(_explanation(), "fos-small", "fos-muted")
        note.set_line_wrap(True)
        note.set_xalign(0)
        note.set_max_width_chars(72)
        host.pack_start(note, False, False, 0)
        host.show_all()

    def _on_sign_in(button_widget: Gtk.Button) -> None:
        parent = _parent_window(button_widget)
        ok, service_error = _sign_in(parent)
        if not ok:
            return
        status_cb("Signed in to OneDrive.")
        if service_error:
            fos_alert(parent, "OneDrive", "Signed in, but sync did not start.\n\n" + _tail(service_error))
        refresh()

    def _on_open() -> None:
        folder = existing_sync_dir() or configured_sync_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            status_cb("Could not open the OneDrive folder.")
            return
        if not appmod.spawn(["fosos-files", str(folder)]):
            status_cb("Could not open the OneDrive folder.")

    def _on_pause() -> None:
        stop_service()
        status_cb("OneDrive sync is paused.")
        refresh()

    def _on_resume() -> None:
        ok, err = start_service()
        if ok:
            status_cb("OneDrive sync started.")
        else:
            status_cb("Could not start OneDrive sync.")
            fos_alert(None, "OneDrive", _tail(err) or "Could not start sync.")
        refresh()

    def _on_sign_out(button_widget: Gtk.Button) -> None:
        parent = _parent_window(button_widget)
        if not fos_confirm(
            parent,
            "Sign out of OneDrive?",
            "Files already in your OneDrive folder stay on this PC.",
            ok="Sign out",
            destructive=True,
        ):
            return
        disable_service()
        ok, err = logout_client()
        if ok:
            status_cb("Signed out of OneDrive. Files stay in the folder.")
        else:
            status_cb("Could not sign out of OneDrive.")
            fos_alert(parent, "OneDrive", _tail(err) or "Could not sign out.")
        refresh()

    refresh()
    return host
