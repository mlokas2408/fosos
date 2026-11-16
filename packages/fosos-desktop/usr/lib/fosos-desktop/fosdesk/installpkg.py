"""Install a local .deb package with a confirm dialog and pkexec."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk

from .ui import load_css

APP_ID = "org.fosos.InstallPackage"
DEB_MAGIC = b"!<arch>\n"


def is_deb_file(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() != ".deb":
        return False
    try:
        with path.open("rb") as handle:
            return handle.read(len(DEB_MAGIC)) == DEB_MAGIC
    except OSError:
        return False


def deb_field(path: Path, field: str) -> str | None:
    try:
        result = subprocess.run(
            ["dpkg-deb", "-f", str(path), field],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    value = (result.stdout or "").strip()
    return value or None


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024**2:
        return f"{size / 1024:.0f} KB"
    if size < 1024**3:
        return f"{size / 1024**2:.1f} MB"
    return f"{size / 1024**3:.1f} GB"


def message(parent: Gtk.Window | None, kind: Gtk.MessageType, title: str, body: str) -> None:
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=kind,
        buttons=Gtk.ButtonsType.OK,
        text=title,
    )
    dialog.format_secondary_text(body)
    dialog.run()
    dialog.destroy()


class InstallApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_OPEN | Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self._busy = False

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_prgname("fosos-install-package")
        GLib.set_application_name("Install Package")
        load_css()

    def do_activate(self) -> None:
        message(None, Gtk.MessageType.INFO, "Install Package", "Open a .deb file to install it.")
        self.quit()

    def do_open(self, files, _n_files, _hint) -> None:
        if not files:
            self.quit()
            return
        path = Path(files[0].get_path() or "")
        self._install(path)

    def do_command_line(self, command_line):
        argv = command_line.get_arguments()[1:]
        if not argv:
            self.activate()
            return 0
        self._install(Path(argv[0]).expanduser())
        return 0

    def _install(self, path: Path) -> None:
        if self._busy:
            return
        path = path.resolve()
        if not is_deb_file(path):
            message(
                None,
                Gtk.MessageType.ERROR,
                "Not a package",
                f"“{path.name}” is not a valid Debian package (.deb).",
            )
            self.quit()
            return

        name = deb_field(path, "Package") or path.stem
        version = deb_field(path, "Version") or "unknown"
        try:
            size = format_size(path.stat().st_size)
        except OSError:
            size = "unknown"

        dialog = Gtk.MessageDialog(
            transient_for=None,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.CANCEL,
            text=f"Install {name}?",
        )
        dialog.format_secondary_text(
            f"Version {version} · {size}\n\n"
            f"{path.name}\n\n"
            "Administrator permission is required."
        )
        dialog.add_button("Install", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            self.quit()
            return

        self._busy = True
        self.hold()
        progress = Gtk.MessageDialog(
            transient_for=None,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.NONE,
            text=f"Installing {name}…",
        )
        progress.format_secondary_text("Approve the password prompt if asked, then wait.")
        progress.show_all()

        argv = [
            "pkexec",
            "env",
            "DEBIAN_FRONTEND=noninteractive",
            "apt-get",
            "install",
            "--yes",
            "--allow-downgrades",
            str(path),
        ]
        try:
            proc = Gio.Subprocess.new(
                argv,
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE,
            )
        except GLib.Error as error:
            progress.destroy()
            self._busy = False
            self.release()
            message(None, Gtk.MessageType.ERROR, "Could not start installer", error.message)
            self.quit()
            return

        def finished(process, result):
            try:
                _ok, stdout, _stderr = process.communicate_utf8_finish(result)
            except GLib.Error as error:
                stdout = error.message
            progress.destroy()
            self._busy = False
            output = (stdout or "").strip()
            if len(output) > 1200:
                output = "…\n" + output[-1200:]
            if process.get_successful():
                body = f"{name} ({version}) is installed."
                if output:
                    body = f"{body}\n\n{output}"
                message(None, Gtk.MessageType.INFO, "Package installed", body)
            else:
                body = "The package could not be installed."
                if output:
                    body = f"{body}\n\n{output}"
                message(None, Gtk.MessageType.ERROR, "Install failed", body)
            self.release()
            self.quit()

        proc.communicate_utf8_async(None, None, finished)


def main() -> int:
    return InstallApp().run(sys.argv)
