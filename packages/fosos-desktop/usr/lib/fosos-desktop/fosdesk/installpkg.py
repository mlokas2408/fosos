"""Install a local .deb package with a Windows Setup–style wizard and pkexec."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from .ui import add_classes, button, fos_alert, label, load_css, mark, set_class

APP_ID = "org.fosos.InstallPackage"
DEB_MAGIC = b"!<arch>\n"

STEPS = (
    ("welcome", "Welcome"),
    ("info", "Package info"),
    ("ready", "Ready to install"),
    ("installing", "Installing"),
    ("completed", "Completed"),
)


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


def _wrapped(text: str, *classes: str, chars: int = 52) -> Gtk.Label:
    widget = label(text, *classes)
    widget.set_line_wrap(True)
    widget.set_max_width_chars(chars)
    widget.set_xalign(0.0)
    return widget


def _meta_row(key: str, value: str) -> Gtk.Box:
    row = Gtk.Box(spacing=12)
    key_label = label(key, "fos-label", "fos-muted")
    key_label.set_size_request(100, -1)
    key_label.set_xalign(0.0)
    row.pack_start(key_label, False, False, 0)
    val = label(value, "fos-text", ellipsize=True)
    val.set_hexpand(True)
    val.set_xalign(0.0)
    row.pack_start(val, True, True, 0)
    return row


class SetupWizard(Gtk.Window):
    """Single-window Setup Wizard for a local .deb."""

    def __init__(
        self,
        app: InstallApp,
        path: Path,
        *,
        name: str,
        version: str,
        architecture: str,
        description: str,
        size: str,
    ) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL, application=app)
        self._app = app
        self._path = path
        self._name = name
        self._version = version
        self._architecture = architecture
        self._description = description
        self._size = size
        self._step = 0
        self._busy = False
        self._success = False
        self._log = ""
        self._step_labels: list[Gtk.Label] = []

        self.set_title(f"{name} Setup")
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_modal(True)
        self.set_default_size(700, 480)
        add_classes(self, "fos-root", "fos-popup", "fos-dialog")
        self.connect("delete-event", self._on_delete)
        self.connect("key-press-event", self._on_key)

        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)

        header = add_classes(Gtk.Box(spacing=8), "fos-card-header")
        self._title = label(f"{name} Setup", "fos-title")
        header.pack_start(self._title, True, True, 0)
        frame.pack_start(header, False, False, 0)
        header.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        header.connect("button-press-event", self._on_header_press)

        body = add_classes(Gtk.Box(spacing=0), "fos-setup-body")
        body.set_hexpand(True)
        body.set_vexpand(True)
        frame.pack_start(body, True, True, 0)

        body.pack_start(self._build_sidebar(), False, False, 0)

        right = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0), "fos-setup-main")
        right.set_hexpand(True)
        right.set_vexpand(True)
        body.pack_start(right, True, True, 0)

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self._stack.set_hexpand(True)
        self._stack.set_vexpand(True)
        right.pack_start(self._stack, True, True, 0)

        self._stack.add_named(self._page_welcome(), "welcome")
        self._stack.add_named(self._page_info(), "info")
        self._stack.add_named(self._page_ready(), "ready")
        self._stack.add_named(self._page_installing(), "installing")
        self._stack.add_named(self._page_completed(), "completed")

        footer = add_classes(Gtk.Box(spacing=8), "fos-card-footer", "fos-setup-footer")
        frame.pack_start(footer, False, False, 0)

        self._cancel = button("Cancel", variant="ghost", size="sm")
        self._cancel.connect("clicked", lambda _b: self._close())
        footer.pack_start(self._cancel, False, False, 0)

        actions = Gtk.Box(spacing=8)
        actions.set_halign(Gtk.Align.END)
        actions.set_hexpand(True)
        footer.pack_end(actions, True, True, 0)

        self._back = button("Back", variant="ghost", size="sm")
        self._back.connect("clicked", lambda _b: self._go(-1))
        actions.pack_start(self._back, False, False, 0)

        self._next = button("Next", variant="default", size="sm")
        self._next.set_can_focus(True)
        self._next.set_can_default(True)
        self._next.connect("clicked", self._on_primary)
        actions.pack_start(self._next, False, False, 0)

        self._sync_ui()

    def _build_sidebar(self) -> Gtk.Widget:
        side = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16), "fos-setup-sidebar")
        side.set_size_request(220, -1)

        brand = Gtk.Box(spacing=10)
        brand.pack_start(mark("md"), False, False, 0)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        titles.pack_start(label("Setup Wizard", "fos-small", "fos-muted"), False, False, 0)
        pkg = label(self._name, "fos-title", ellipsize=True)
        titles.pack_start(pkg, False, False, 0)
        brand.pack_start(titles, True, True, 0)
        side.pack_start(brand, False, False, 0)

        steps = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for _key, title in STEPS:
            step = label(title, "fos-setup-step", "fos-text")
            step.set_xalign(0.0)
            steps.pack_start(step, False, False, 0)
            self._step_labels.append(step)
        side.pack_start(steps, False, False, 0)
        return side

    def _page_welcome(self) -> Gtk.Widget:
        box = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "fos-setup-page")
        box.pack_start(
            _wrapped(f"Welcome to the {self._name} Setup Wizard", "fos-setup-heading"),
            False,
            False,
            0,
        )
        box.pack_start(
            _wrapped(
                f"This wizard will install {self._name} on your computer. "
                "The package will be available for all users.",
                "fos-text",
            ),
            False,
            False,
            0,
        )
        box.pack_start(
            _wrapped("Click Next to continue.", "fos-text", "fos-muted"),
            False,
            False,
            0,
        )
        return box

    def _page_info(self) -> Gtk.Widget:
        box = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "fos-setup-page")
        box.pack_start(_wrapped("Package information", "fos-setup-heading"), False, False, 0)

        meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        meta.pack_start(_meta_row("Package", self._name), False, False, 0)
        meta.pack_start(_meta_row("Version", self._version), False, False, 0)
        meta.pack_start(_meta_row("Architecture", self._architecture), False, False, 0)
        meta.pack_start(_meta_row("Size", self._size), False, False, 0)
        meta.pack_start(_meta_row("File", self._path.name), False, False, 0)
        box.pack_start(meta, False, False, 0)

        if self._description:
            box.pack_start(label("Description", "fos-label", "fos-muted"), False, False, 0)
            desc = _wrapped(self._description, "fos-text")
            box.pack_start(desc, False, False, 0)
        return box

    def _page_ready(self) -> Gtk.Widget:
        box = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "fos-setup-page")
        box.pack_start(_wrapped("Ready to install", "fos-setup-heading"), False, False, 0)
        box.pack_start(
            _wrapped(
                f"Setup is ready to install {self._name} ({self._version}).",
                "fos-text",
            ),
            False,
            False,
            0,
        )
        box.pack_start(
            _wrapped(
                "Administrator permission is required. Click Install to continue.",
                "fos-text",
                "fos-muted",
            ),
            False,
            False,
            0,
        )
        return box

    def _page_installing(self) -> Gtk.Widget:
        box = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "fos-setup-page")
        box.pack_start(_wrapped("Installing", "fos-setup-heading"), False, False, 0)
        self._status = _wrapped(
            "Approve the password prompt if asked, then wait.",
            "fos-text",
            "fos-muted",
        )
        box.pack_start(self._status, False, False, 0)
        self._progress = Gtk.ProgressBar()
        self._progress.set_show_text(False)
        self._progress.set_pulse_step(0.05)
        box.pack_start(self._progress, False, False, 0)
        return box

    def _page_completed(self) -> Gtk.Widget:
        box = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "fos-setup-page")
        self._done_heading = _wrapped("Installation complete", "fos-setup-heading")
        box.pack_start(self._done_heading, False, False, 0)
        self._done_body = _wrapped("", "fos-text")
        box.pack_start(self._done_body, False, False, 0)
        self._done_log = Gtk.Label(label="")
        self._done_log.set_xalign(0.0)
        self._done_log.set_line_wrap(True)
        self._done_log.set_max_width_chars(52)
        self._done_log.set_selectable(True)
        self._done_log.set_ellipsize(Pango.EllipsizeMode.END)
        add_classes(self._done_log, "fos-text", "fos-muted", "fos-setup-log")
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(120)
        scrolled.set_shadow_type(Gtk.ShadowType.NONE)
        scrolled.add(self._done_log)
        box.pack_start(scrolled, True, True, 0)
        return box

    def _sync_ui(self) -> None:
        key, title = STEPS[self._step]
        self._stack.set_visible_child_name(key)
        self._title.set_text(f"{self._name} Setup — {title}")
        for index, widget in enumerate(self._step_labels):
            set_class(widget, "active", index == self._step)
            set_class(widget, "done", index < self._step)

        installing = key == "installing"
        completed = key == "completed"
        self._back.set_sensitive(self._step > 0 and not installing and not completed)
        self._back.set_visible(not completed)
        self._cancel.set_sensitive(not installing and not completed)
        self._cancel.set_visible(not completed)

        if completed:
            self._set_button_label(self._next, "Finish")
            self._next.set_sensitive(True)
        elif key == "ready":
            self._set_button_label(self._next, "Install")
            self._next.set_sensitive(True)
        elif installing:
            self._set_button_label(self._next, "Next")
            self._next.set_sensitive(False)
        else:
            self._set_button_label(self._next, "Next")
            self._next.set_sensitive(True)

    @staticmethod
    def _set_button_label(btn: Gtk.Button, text: str) -> None:
        child = btn.get_child()
        if isinstance(child, Gtk.Label):
            child.set_text(text)
        else:
            btn.set_label(text)

    def _go(self, delta: int) -> None:
        if self._busy:
            return
        nxt = self._step + delta
        if nxt < 0 or nxt >= len(STEPS):
            return
        # Do not enter installing/completed via Back/Next alone.
        if STEPS[nxt][0] in ("installing", "completed") and delta > 0:
            return
        if STEPS[self._step][0] in ("installing", "completed"):
            return
        self._step = nxt
        self._sync_ui()

    def _on_primary(self, _button: Gtk.Button) -> None:
        key = STEPS[self._step][0]
        if key == "completed":
            self._close()
            return
        if key == "ready":
            self._start_install()
            return
        if key in ("welcome", "info"):
            self._go(1)

    def _start_install(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._step = next(i for i, (k, _) in enumerate(STEPS) if k == "installing")
        self._sync_ui()
        self._status.set_text("Approve the password prompt if asked, then wait.")
        self._progress.pulse()
        GLib.timeout_add(100, self._pulse)

        argv = [
            "pkexec",
            "env",
            "DEBIAN_FRONTEND=noninteractive",
            "apt-get",
            "install",
            "--yes",
            "--allow-downgrades",
            str(self._path),
        ]
        try:
            proc = Gio.Subprocess.new(
                argv,
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE,
            )
        except GLib.Error as error:
            self._busy = False
            self._finish(False, error.message)
            return

        self._status.set_text("Installing…")

        def finished(process, result):
            try:
                _ok, stdout, _stderr = process.communicate_utf8_finish(result)
            except GLib.Error as error:
                stdout = error.message
            output = (stdout or "").strip()
            if len(output) > 1200:
                output = "…\n" + output[-1200:]
            self._busy = False
            self._finish(process.get_successful(), output)

        proc.communicate_utf8_async(None, None, finished)

    def _pulse(self) -> bool:
        if not self._busy:
            return False
        self._progress.pulse()
        return True

    def _finish(self, success: bool, output: str) -> None:
        self._success = success
        self._log = output
        self._step = next(i for i, (k, _) in enumerate(STEPS) if k == "completed")
        if success:
            self._done_heading.set_text("Installation complete")
            self._done_body.set_text(f"{self._name} ({self._version}) is installed.")
        else:
            self._done_heading.set_text("Installation failed")
            self._done_body.set_text("The package could not be installed.")
        self._done_log.set_text(output)
        self._done_log.set_visible(bool(output))
        self._sync_ui()

    def _close(self) -> None:
        if self._busy:
            return
        self.destroy()
        self._app.release()
        self._app.quit()

    def _on_delete(self, *_args) -> bool:
        if self._busy:
            return True
        self._close()
        return True

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            if not self._busy and STEPS[self._step][0] != "completed":
                self._close()
            return True
        return False

    def _on_header_press(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button != 1:
            return False
        window = self.get_window()
        if window is not None:
            Gdk.Window.begin_move_drag(
                window,
                int(event.button),
                int(event.x_root),
                int(event.y_root),
                int(event.time),
            )
            return True
        return False


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
        fos_alert(None, "Install Package", "Open a .deb file to install it.")
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
            fos_alert(
                None,
                "Not a package",
                f"“{path.name}” is not a valid Debian package (.deb).",
            )
            self.quit()
            return

        name = deb_field(path, "Package") or path.stem
        version = deb_field(path, "Version") or "unknown"
        architecture = deb_field(path, "Architecture") or "unknown"
        description = deb_field(path, "Description") or ""
        try:
            size = format_size(path.stat().st_size)
        except OSError:
            size = "unknown"

        self._busy = True
        self.hold()
        wizard = SetupWizard(
            self,
            path,
            name=name,
            version=version,
            architecture=architecture,
            description=description,
            size=size,
        )
        wizard.show_all()
        wizard.present()
        wizard._next.grab_default()


def main() -> int:
    return InstallApp().run(sys.argv)
