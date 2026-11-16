"""FosOS Remote Desktop: FreeRDP client with card chrome."""

from __future__ import annotations

import configparser
import os
import shutil
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk

from .ui import FosDialog, add_classes, button, clear, label, load_css, set_class
from .windowchrome import CardWindow

APP_ID = "org.fosos.RemoteDesktop"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "fosos-desktop"
CONNECTIONS_FILE = CONFIG_DIR / "remote-connections.ini"
LAST_LOG = CONFIG_DIR / "remote-last.log"


def freerdp_bin() -> str | None:
    for name in ("xfreerdp3", "xfreerdp", "wlfreerdp3", "wlfreerdp"):
        path = shutil.which(name)
        if path:
            return path
    # Absolute fallbacks when PATH is thin (some .desktop launches).
    for path in ("/usr/bin/xfreerdp3", "/usr/bin/xfreerdp"):
        if Path(path).is_file():
            return path
    return None


def load_connections() -> list[dict[str, str]]:
    parser = configparser.ConfigParser()
    if CONNECTIONS_FILE.is_file():
        try:
            parser.read(CONNECTIONS_FILE, encoding="utf-8")
        except configparser.Error:
            return []
    rows: list[dict[str, str]] = []
    for section in parser.sections():
        rows.append(
            {
                "id": section,
                "name": parser.get(section, "name", fallback=section),
                "host": parser.get(section, "host", fallback=""),
                "port": parser.get(section, "port", fallback="3389"),
                "user": parser.get(section, "user", fallback=""),
                "domain": parser.get(section, "domain", fallback=""),
                "gateway": parser.get(section, "gateway", fallback=""),
                "fullscreen": parser.get(section, "fullscreen", fallback="0"),
                "clipboard": parser.get(section, "clipboard", fallback="1"),
                "audio": parser.get(section, "audio", fallback="0"),
                "gfx": parser.get(section, "gfx", fallback="0"),
            }
        )
    rows.sort(key=lambda row: row["name"].lower())
    return rows


def save_connections(rows: list[dict[str, str]]) -> None:
    parser = configparser.ConfigParser()
    for index, row in enumerate(rows):
        section = row.get("id") or f"conn{index + 1}"
        parser[section] = {
            "name": row.get("name") or row.get("host") or section,
            "host": row.get("host") or "",
            "port": row.get("port") or "3389",
            "user": row.get("user") or "",
            "domain": row.get("domain") or "",
            "gateway": row.get("gateway") or "",
            "fullscreen": row.get("fullscreen") or "0",
            "clipboard": row.get("clipboard") or "1",
            "audio": row.get("audio") or "0",
            "gfx": row.get("gfx") or "0",
        }
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with CONNECTIONS_FILE.open("w", encoding="utf-8") as handle:
        parser.write(handle)


def build_argv(row: dict[str, str], password: str | None = None) -> list[str] | None:
    """Build xfreerdp3 argv. FreeRDP 3 needs /u: and /p: for NLA or it exits with no window."""
    binary = freerdp_bin()
    if binary is None:
        return None
    host = (row.get("host") or "").strip()
    if not host:
        return None
    port = (row.get("port") or "3389").strip() or "3389"
    # Keep the base argv conservative: exotic flags are what make FreeRDP exit
    # before mapping a window (false "started" with nothing on screen).
    argv = [
        binary,
        f"/v:{host}",
        f"/port:{port}",
        "/cert:ignore",
        "/t:FosOS Remote Desktop",
        "/wm-class:fosos-remote",
    ]
    user = (row.get("user") or "").strip()
    if user:
        argv.append(f"/u:{user}")
    domain = (row.get("domain") or "").strip()
    if domain:
        argv.append(f"/d:{domain}")
    # Always pass /p: when we have a password string (including empty) so NLA
    # does not wait on a TTY that we do not attach.
    if password is not None:
        argv.append(f"/p:{password}")
    gateway = (row.get("gateway") or "").strip()
    if gateway:
        argv.append(f"/gateway:g:{gateway}")
    if row.get("fullscreen", "0") == "1":
        argv.append("/f")
    else:
        argv.append("/size:1280x800")
    if row.get("clipboard", "1") == "1":
        argv.append("+clipboard")
    if row.get("audio", "1") == "1":
        argv.append("/sound")
    if row.get("gfx", "1") == "1":
        argv.append("/gfx")
    return argv


def ask_password(parent: Gtk.Window | None, user: str, host: str) -> str | None:
    """Modal password prompt. Returns password string, or None if cancelled."""
    dialog = FosDialog(parent, title="Sign in", width=420)
    who = f"{user}@{host}" if user else host
    dialog.add_body_text(f"Password for {who}", "fos-text", "fos-muted")
    entry = add_classes(Gtk.Entry(), "fos-input")
    entry.set_visibility(False)
    entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
    entry.set_activates_default(True)
    dialog.content.pack_start(entry, False, False, 0)
    tip = label("Required for most Windows and Ubuntu hosts (NLA). Leave empty only for servers that show their own login screen.", "fos-small", "fos-muted")
    tip.set_line_wrap(True)
    dialog.content.pack_start(tip, False, False, 0)

    result: dict[str, str | None] = {"value": None}

    def accept(_w=None) -> None:
        result["value"] = entry.get_text()
        dialog.respond(True)

    def cancel(_w=None) -> None:
        result["value"] = None
        dialog.respond(False)

    cancel_btn = button("Cancel", variant="ghost", size="sm")
    cancel_btn.connect("clicked", cancel)
    ok_btn = button("Connect", variant="default", size="sm")
    ok_btn.set_can_default(True)
    ok_btn.connect("clicked", accept)
    dialog.footer.pack_start(cancel_btn, False, False, 0)
    dialog.footer.pack_start(ok_btn, False, False, 0)
    entry.connect("activate", accept)
    GLib.idle_add(entry.grab_focus)
    if dialog.run() is not True:
        return None
    return result["value"]


class RemoteWindow(CardWindow):
    def __init__(self, app: "RemoteApp") -> None:
        super().__init__(
            app,
            title="Remote Desktop",
            icon_name="network-server-symbolic",
            default_width=740,
            default_height=540,
        )
        self.app = app
        self.rows = load_connections()
        self._selected: str | None = None
        self._session: subprocess.Popen | None = None
        self._log_handle = None
        self._announced = False

        toolbar = add_classes(Gtk.Box(spacing=4), "fos-app-toolbar")
        self.connect_btn = button("Connect", variant="default", size="sm")
        self.connect_btn.connect("clicked", lambda _b: self.connect_selected())
        toolbar.pack_start(self.connect_btn, False, False, 0)
        add_btn = button("Add", variant="ghost", size="sm")
        add_btn.connect("clicked", lambda _b: self.edit_connection(None))
        toolbar.pack_start(add_btn, False, False, 0)
        self.edit_btn = button("Edit", variant="ghost", size="sm")
        self.edit_btn.connect("clicked", lambda _b: self.edit_connection(self._selected))
        toolbar.pack_start(self.edit_btn, False, False, 0)
        self.remove_btn = button("Remove", variant="ghost", size="sm")
        self.remove_btn.connect("clicked", lambda _b: self.remove_selected())
        toolbar.pack_start(self.remove_btn, False, False, 0)
        self.body.pack_start(toolbar, False, False, 0)

        split = Gtk.Box(spacing=0)
        self.body.pack_start(split, True, True, 0)

        side = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4), "fos-sidebar")
        side.set_size_request(220, -1)
        side.set_border_width(8)
        side.pack_start(label("Connections", "fos-small", "fos-muted"), False, False, 4)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        scroller.add(self.list_box)
        side.pack_start(scroller, True, True, 0)
        split.pack_start(side, False, False, 0)

        form = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "fos-card-content")
        form.set_hexpand(True)
        split.pack_start(form, True, True, 0)

        self.name_entry = self._field(form, "Name")
        self.host_entry = self._field(form, "PC name / address")
        self.port_entry = self._field(form, "Port", "3389")
        self.user_entry = self._field(form, "User name")
        self.domain_entry = self._field(form, "Domain (optional)")
        self.gateway_entry = self._field(form, "Gateway (optional)")

        toggles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.full_switch = self._toggle(toggles, "Fullscreen", False)
        self.clip_switch = self._toggle(toggles, "Clipboard", True)
        self.audio_switch = self._toggle(toggles, "Audio", False)
        self.gfx_switch = self._toggle(toggles, "GFX / GPU path", False)
        form.pack_start(toggles, False, False, 0)

        tip = label(
            "Passwords are not stored. You will be asked when you connect. "
            "Works with Windows, Ubuntu Remote Desktop, and other RDP hosts.",
            "fos-small",
            "fos-muted",
        )
        tip.set_line_wrap(True)
        form.pack_start(tip, False, False, 0)

        save_row = Gtk.Box(spacing=8)
        save_btn = button("Save", variant="outline", size="sm")
        save_btn.connect("clicked", lambda _b: self.save_form())
        save_row.pack_start(save_btn, False, False, 0)
        form.pack_start(save_row, False, False, 0)

        self.footer = add_classes(Gtk.Box(spacing=12), "fos-app-footer")
        binary = freerdp_bin() or "FreeRDP not installed"
        self.status = label(f"Ready · {binary}", "fos-small", "fos-muted")
        self.footer.pack_start(self.status, True, True, 0)
        self.body.pack_start(self.footer, False, False, 0)

        self.rebuild_list()
        if self.rows:
            self.select_row(self.rows[0]["id"])
        else:
            self.edit_connection(None)

    def _field(self, parent: Gtk.Box, caption: str, initial: str = "") -> Gtk.Entry:
        parent.pack_start(label(caption, "fos-label"), False, False, 0)
        entry = add_classes(Gtk.Entry(), "fos-input")
        entry.set_text(initial)
        parent.pack_start(entry, False, False, 0)
        return entry

    def _toggle(self, parent: Gtk.Box, caption: str, active: bool) -> Gtk.Switch:
        row = Gtk.Box(spacing=12)
        row.pack_start(label(caption, "fos-text"), True, True, 0)
        switch = add_classes(Gtk.Switch(), "fos-switch")
        switch.set_active(active)
        switch.set_valign(Gtk.Align.CENTER)
        row.pack_end(switch, False, False, 0)
        parent.pack_start(row, False, False, 0)
        return switch

    def rebuild_list(self) -> None:
        clear(self.list_box)
        for row in self.rows:
            btn = button(row["name"] or row["host"] or row["id"], variant="ghost", size="sm")
            btn.get_child().set_halign(Gtk.Align.START)
            set_class(btn, "secondary", row["id"] == self._selected)
            set_class(btn, "ghost", row["id"] != self._selected)
            btn.connect("clicked", lambda _b, rid=row["id"]: self.select_row(rid))
            self.list_box.pack_start(btn, False, False, 0)
        self.list_box.show_all()

    def select_row(self, row_id: str) -> None:
        row = next((item for item in self.rows if item["id"] == row_id), None)
        if row is None:
            return
        self._selected = row_id
        self.name_entry.set_text(row.get("name") or "")
        self.host_entry.set_text(row.get("host") or "")
        self.port_entry.set_text(row.get("port") or "3389")
        self.user_entry.set_text(row.get("user") or "")
        self.domain_entry.set_text(row.get("domain") or "")
        self.gateway_entry.set_text(row.get("gateway") or "")
        self.full_switch.set_active(row.get("fullscreen", "0") == "1")
        self.clip_switch.set_active(row.get("clipboard", "1") == "1")
        self.audio_switch.set_active(row.get("audio", "0") == "1")
        self.gfx_switch.set_active(row.get("gfx", "0") == "1")
        self.rebuild_list()
        self.status.set_text(f"Selected {row.get('name') or row.get('host')}")

    def edit_connection(self, row_id: str | None) -> None:
        if row_id is None:
            new_id = f"conn{len(self.rows) + 1}"
            while any(row["id"] == new_id for row in self.rows):
                new_id = f"conn{len(self.rows) + 1}_{len(self.rows)}"
            self.rows.append(
                {
                    "id": new_id,
                    "name": "New connection",
                    "host": "",
                    "port": "3389",
                    "user": "",
                    "domain": "",
                    "gateway": "",
                    "fullscreen": "0",
                    "clipboard": "1",
                    "audio": "0",
                    "gfx": "0",
                }
            )
            save_connections(self.rows)
            self.select_row(new_id)
            self.status.set_text("New connection — fill in the address and Save.")
            return
        self.select_row(row_id)

    def form_to_row(self) -> dict[str, str]:
        row_id = self._selected or f"conn{len(self.rows) + 1}"
        return {
            "id": row_id,
            "name": self.name_entry.get_text().strip() or self.host_entry.get_text().strip() or row_id,
            "host": self.host_entry.get_text().strip(),
            "port": self.port_entry.get_text().strip() or "3389",
            "user": self.user_entry.get_text().strip(),
            "domain": self.domain_entry.get_text().strip(),
            "gateway": self.gateway_entry.get_text().strip(),
            "fullscreen": "1" if self.full_switch.get_active() else "0",
            "clipboard": "1" if self.clip_switch.get_active() else "0",
            "audio": "1" if self.audio_switch.get_active() else "0",
            "gfx": "1" if self.gfx_switch.get_active() else "0",
        }

    def save_form(self) -> None:
        row = self.form_to_row()
        if not row["host"]:
            self.status.set_text("Enter a PC name or address before saving.")
            return
        updated = False
        for index, existing in enumerate(self.rows):
            if existing["id"] == row["id"]:
                self.rows[index] = row
                updated = True
                break
        if not updated:
            self.rows.append(row)
        self._selected = row["id"]
        save_connections(self.rows)
        self.rebuild_list()
        self.status.set_text(f"Saved {row['name']}.")

    def remove_selected(self) -> None:
        if self._selected is None:
            return
        self.rows = [row for row in self.rows if row["id"] != self._selected]
        save_connections(self.rows)
        self._selected = None
        self.rebuild_list()
        if self.rows:
            self.select_row(self.rows[0]["id"])
        else:
            self.name_entry.set_text("")
            self.host_entry.set_text("")
            self.port_entry.set_text("3389")
            self.user_entry.set_text("")
            self.domain_entry.set_text("")
            self.gateway_entry.set_text("")
        self.status.set_text("Connection removed.")

    def connect_selected(self) -> None:
        row = self.form_to_row()
        if not row["host"]:
            self.status.set_text("Enter a PC name or address.")
            return
        # Persist before connect so a failed attempt still keeps the form.
        self.save_form()
        row = self.form_to_row()
        if freerdp_bin() is None:
            self.status.set_text("FreeRDP is not installed (package freerdp3-x11).")
            return
        if not row.get("user"):
            self.status.set_text("Enter a user name (required for NLA).")
            return
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            self.status.set_text("No display available for FreeRDP.")
            return

        if self._session is not None and self._session.poll() is None:
            self.status.set_text("A session is already running — close it first.")
            return

        password = ask_password(self, row.get("user") or "", row["host"])
        if password is None:
            self.status.set_text("Connect cancelled.")
            return

        # Always pass a string so /p: is set; stdin is closed and FreeRDP cannot prompt.
        argv = build_argv(row, password=password)
        if argv is None:
            self.status.set_text("Could not build FreeRDP command.")
            return

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            if self._log_handle is not None:
                try:
                    self._log_handle.close()
                except OSError:
                    pass
            self._log_handle = LAST_LOG.open("w", encoding="utf-8")
            self._log_handle.write(" ".join(_redact_argv(argv)) + "\n")
            self._log_handle.flush()
            env = os.environ.copy()
            self._session = subprocess.Popen(
                argv,
                start_new_session=True,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
            )
        except OSError as exc:
            self.status.set_text(f"Could not start FreeRDP: {exc}")
            self._session = None
            return

        self._announced = False
        self._poll_ticks = 0
        self.status.set_text(f"Connecting to {row['host']}…")
        self.connect_btn.set_sensitive(False)
        # Poll quickly so a bad argv/NLA failure is not mistaken for success.
        GLib.timeout_add(250, self._poll_session)

    def _poll_session(self) -> bool:
        proc = self._session
        if proc is None:
            self.connect_btn.set_sensitive(True)
            return False
        code = proc.poll()
        if code is None:
            self._poll_ticks = getattr(self, "_poll_ticks", 0) + 1
            # ~1.5s alive before calling it connected (auth failures exit faster).
            if not self._announced and self._poll_ticks >= 6:
                self._announced = True
                self.status.set_text("Connected — use the FreeRDP window.")
            return True

        self.connect_btn.set_sensitive(True)
        self._announced = False
        self._session = None
        detail = _tail_log(LAST_LOG)
        if code == 0:
            self.status.set_text("Session closed.")
        else:
            msg = detail or f"exit {code}"
            if len(msg) > 180:
                msg = msg[-180:]
            self.status.set_text(f"Connection failed: {msg}")
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except OSError:
                pass
            self._log_handle = None
        return False


def _redact_argv(argv: list[str]) -> list[str]:
    out = []
    for arg in argv:
        if arg.startswith("/p:"):
            out.append("/p:***")
        else:
            out.append(arg)
    return out


def _tail_log(path: Path, limit: int = 12) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    useful = [line.strip() for line in lines if line.strip() and not line.startswith("/")]
    if not useful:
        useful = [line.strip() for line in lines if line.strip()]
    return " | ".join(useful[-limit:])


class RemoteApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window: RemoteWindow | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_prgname("fosos-remote")
        GLib.set_application_name("Remote Desktop")
        load_css()

    def do_activate(self) -> None:
        if self.window is None:
            self.window = RemoteWindow(self)
            self.window.show_all()
        self.window.present()


def main() -> int:
    return RemoteApp().run(sys.argv)
