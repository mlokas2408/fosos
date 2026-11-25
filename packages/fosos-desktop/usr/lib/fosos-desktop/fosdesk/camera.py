"""FosOS Camera: CardWindow webcam preview and still capture via GStreamer."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gst", "1.0")
gi.require_version("GstVideo", "1.0")
from gi.repository import GdkPixbuf, Gio, GLib, Gst, GstVideo, Gtk

from .ui import add_classes, button, clear, label, load_css, set_class
from .windowchrome import CardWindow

APP_ID = "org.fosos.Camera"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "fosos-desktop"
CONFIG_FILE = CONFIG_DIR / "camera.conf"

# User-facing V4L2 int controls shown in Settings (when the device supports them).
IMAGE_CTRLS: tuple[tuple[str, str], ...] = (
    ("brightness", "Brightness"),
    ("contrast", "Contrast"),
    ("saturation", "Saturation"),
    ("hue", "Hue"),
    ("gamma", "Gamma"),
    ("sharpness", "Sharpness"),
    ("backlight_compensation", "Backlight"),
)

BOOL_CTRLS: tuple[tuple[str, str], ...] = (
    ("white_balance_automatic", "Auto white balance"),
)


@dataclass(frozen=True)
class RecordCodec:
    key: str
    label: str
    element: str
    fragment: str


@dataclass(frozen=True)
class RecordContainer:
    key: str
    label: str
    extension: str
    element: str
    codecs: tuple[str, ...]


# Video encoders offered for recording (filtered by Gst.ElementFactory at runtime).
RECORD_CODECS: tuple[RecordCodec, ...] = (
    RecordCodec("vp8", "VP8", "vp8enc", "vp8enc name=encoder deadline=1 cpu-used=8"),
    RecordCodec("vp9", "VP9", "vp9enc", "vp9enc name=encoder deadline=1 cpu-used=8"),
    RecordCodec(
        "h264",
        "H.264",
        "x264enc",
        # bframes=0 + constrained-baseline keeps MP4 playable without a long
        # GOP delay; h264parse (plugins-bad) is appended at pipeline build when present.
        "x264enc name=encoder tune=zerolatency speed-preset=ultrafast key-int-max=30 bframes=0",
    ),
    RecordCodec("mpeg4", "MPEG-4", "avenc_mpeg4", "avenc_mpeg4 name=encoder"),
    RecordCodec("theora", "Theora", "theoraenc", "theoraenc name=encoder"),
    RecordCodec("mjpeg", "MJPEG", "jpegenc", "jpegenc name=encoder quality=85"),
)

RECORD_CONTAINERS: tuple[RecordContainer, ...] = (
    RecordContainer("webm", "WebM", "webm", "webmmux", ("vp8", "vp9")),
    RecordContainer("mp4", "MP4", "mp4", "mp4mux", ("h264", "mpeg4")),
    RecordContainer("mkv", "Matroska (MKV)", "mkv", "matroskamux", ("vp8", "vp9", "h264", "mpeg4", "theora", "mjpeg")),
    RecordContainer("avi", "AVI", "avi", "avimux", ("mjpeg", "mpeg4")),
    RecordContainer("ogg", "Ogg", "ogv", "oggmux", ("theora",)),
)


def gst_element_available(name: str) -> bool:
    if not Gst.is_initialized():
        Gst.init(None)
    return Gst.ElementFactory.find(name) is not None


def available_record_containers() -> list[RecordContainer]:
    rows: list[RecordContainer] = []
    for container in RECORD_CONTAINERS:
        if not gst_element_available(container.element):
            continue
        if available_codecs_for(container):
            rows.append(container)
    return rows


def codec_by_key(key: str) -> RecordCodec | None:
    return next((c for c in RECORD_CODECS if c.key == key), None)


def container_by_key(key: str) -> RecordContainer | None:
    return next((c for c in RECORD_CONTAINERS if c.key == key), None)


def available_codecs_for(container: RecordContainer) -> list[RecordCodec]:
    codecs: list[RecordCodec] = []
    for key in container.codecs:
        codec = codec_by_key(key)
        if codec is not None and gst_element_available(codec.element):
            codecs.append(codec)
    return codecs


def pick_record_format(container_key: str, codec_key: str) -> tuple[RecordContainer, RecordCodec]:
    containers = available_record_containers()
    if not containers:
        # Hard fallback — plugins-good always ships these on FosOS.
        webm = container_by_key("webm") or RECORD_CONTAINERS[0]
        vp8 = codec_by_key("vp8") or RECORD_CODECS[0]
        return webm, vp8
    container = next((c for c in containers if c.key == container_key), containers[0])
    codecs = available_codecs_for(container)
    if not codecs:
        container = containers[0]
        codecs = available_codecs_for(container)
    codec = next((c for c in codecs if c.key == codec_key), codecs[0])
    return container, codec


@dataclass(frozen=True)
class CameraDevice:
    path: str
    name: str


@dataclass(frozen=True)
class CaptureMode:
    fourcc: str
    width: int
    height: int
    fps: float

    @property
    def key(self) -> str:
        return f"{self.fourcc}:{self.width}x{self.height}@{self.fps:g}"

    @property
    def label(self) -> str:
        fps = f"{self.fps:g}"
        return f"{self.width}×{self.height} · {fps} fps ({self.fourcc})"


@dataclass
class V4LControl:
    name: str
    kind: str  # int | bool | menu
    minimum: int
    maximum: int
    step: int
    default: int
    value: int
    inactive: bool = False


def pictures_dir() -> Path:
    pictures = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
    if pictures:
        return Path(pictures)
    return Path.home() / "Pictures"


def videos_dir() -> Path:
    videos = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS)
    if videos:
        return Path(videos)
    return Path.home() / "Videos"


def load_config() -> dict[str, str]:
    values: dict[str, str] = {}
    if not CONFIG_FILE.is_file():
        return values
    try:
        for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    except OSError:
        pass
    return values


def save_config(values: dict[str, str]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        "".join(f"{key}={value}\n" for key, value in values.items()),
        encoding="utf-8",
    )


def _run_v4l(argv: list[str], timeout: float = 4.0) -> str | None:
    if shutil.which("v4l2-ctl") is None:
        return None
    try:
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout or ""


def list_cameras() -> list[CameraDevice]:
    """Prefer GStreamer Video/Source devices; fall back to sysfs + v4l2-ctl."""
    if not Gst.is_initialized():
        Gst.init(None)
    devices: list[CameraDevice] = []
    seen: set[str] = set()
    try:
        monitor = Gst.DeviceMonitor.new()
        monitor.add_filter("Video/Source", None)
        monitor.start()
        try:
            for device in monitor.get_devices() or []:
                props = device.get_properties()
                path = props.get_string("device.path") if props is not None else None
                if not path or path in seen:
                    continue
                name = (device.get_display_name() or Path(path).name).strip()
                seen.add(path)
                devices.append(CameraDevice(path=path, name=name))
        finally:
            monitor.stop()
    except GLib.Error:
        pass

    if devices:
        return devices

    root = Path("/sys/class/video4linux")
    if not root.is_dir():
        return []
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        path = f"/dev/{entry.name}"
        if path in seen or not Path(path).exists():
            continue
        name_file = entry / "name"
        try:
            name = name_file.read_text(encoding="utf-8").strip() if name_file.is_file() else entry.name
        except OSError:
            name = entry.name
        out = _run_v4l(["v4l2-ctl", "-d", path, "--all"])
        if out is not None and "Video Capture" not in out:
            continue
        seen.add(path)
        devices.append(CameraDevice(path=path, name=name or entry.name))
    return devices


def list_capture_modes(device: str) -> list[CaptureMode]:
    out = _run_v4l(["v4l2-ctl", "-d", device, "--list-formats-ext"])
    if not out:
        return [CaptureMode("MJPG", 640, 480, 30.0)]
    modes: list[CaptureMode] = []
    fourcc = ""
    width = height = 0
    for line in out.splitlines():
        # e.g. [0]: 'MJPG' (Motion-JPEG, compressed)
        fmt = re.search(r"\[\d+\]:\s+'([A-Z0-9]{4})'", line)
        if fmt:
            fourcc = fmt.group(1)
            width = height = 0
            continue
        size = re.search(r"Size:\s+Discrete\s+(\d+)x(\d+)", line)
        if size and fourcc:
            width, height = int(size.group(1)), int(size.group(2))
            continue
        interval = re.search(r"Interval:\s+Discrete\s+[\d.]+s\s+\(([\d.]+)\s+fps\)", line)
        if interval and fourcc and width and height:
            modes.append(CaptureMode(fourcc, width, height, float(interval.group(1))))
    if not modes:
        return [CaptureMode("MJPG", 640, 480, 30.0)]
    # Prefer Motion-JPEG, then higher resolution / fps.
    modes.sort(key=lambda m: (0 if m.fourcc == "MJPG" else 1, -m.width * m.height, -m.fps))
    return modes


def list_v4l_controls(device: str) -> dict[str, V4LControl]:
    out = _run_v4l(["v4l2-ctl", "-d", device, "--list-ctrls"])
    controls: dict[str, V4LControl] = {}
    if not out:
        return controls
    pattern = re.compile(
        r"^\s*([a-z0-9_]+)\s+0x[0-9a-f]+\s+\((int|bool|menu)\)\s*:\s*(.*)$",
        re.IGNORECASE,
    )
    for line in out.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        name, kind, rest = match.group(1), match.group(2).lower(), match.group(3)
        fields = dict(re.findall(r"(min|max|step|default|value)=(-?\d+)", rest))
        if "value" not in fields:
            continue
        controls[name] = V4LControl(
            name=name,
            kind=kind,
            minimum=int(fields.get("min", 0)),
            maximum=int(fields.get("max", 1)),
            step=max(1, int(fields.get("step", 1))),
            default=int(fields.get("default", fields["value"])),
            value=int(fields["value"]),
            inactive="inactive" in rest,
        )
    return controls


def set_v4l_control(device: str, name: str, value: int) -> bool:
    out = _run_v4l(["v4l2-ctl", "-d", device, "-c", f"{name}={int(value)}"])
    return out is not None


def notify_saved(path: Path, *, title: str = "Photo saved", icon: str = "camera-web-symbolic") -> None:
    if not shutil.which("notify-send"):
        return
    subprocess.Popen(
        [
            "notify-send",
            "-a",
            "FosOS",
            "-i",
            icon,
            title,
            str(path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _gst_raw_format(fourcc: str) -> str:
    return {"YUYV": "YUY2", "YVYU": "YVYU", "UYVY": "UYVY"}.get(fourcc, fourcc)


class CameraWindow(CardWindow):
    def __init__(self, app: "CameraApp") -> None:
        super().__init__(
            app,
            title="Camera",
            icon_name="camera-web-symbolic",
            default_width=1100,
            default_height=720,
        )
        self.set_icon_name("camera-web")
        add_classes(self, "fos-camera-shell")
        self.app = app
        self.pipeline: Gst.Pipeline | None = None
        self._sink_widget: Gtk.Widget | None = None
        self._flip: Gst.Element | None = None
        self._appsink: Gst.Element | None = None
        self._bus: Gst.Bus | None = None
        self._bus_handler: int | None = None
        self._ctrl_scales: dict[str, Gtk.Scale] = {}
        self._ctrl_switches: dict[str, Gtk.Switch] = {}
        self._updating_ui = False
        self._modes: list[CaptureMode] = []
        self._mode: CaptureMode | None = None
        self._rec_valve: Gst.Element | None = None
        self._rec_file: Gst.Element | None = None
        self._rec_mux: Gst.Element | None = None
        self._rec_encoder: Gst.Element | None = None
        self._recording = False
        self._record_path: Path | None = None
        self._record_started = 0.0
        self._record_timer: int | None = None

        conf = load_config()
        self._mirror = conf.get("mirror", "0") in ("1", "true", "yes")
        # Default open so the side panel is obvious on first launch.
        self._settings_open = conf.get("settings_open", "1") not in ("0", "false", "no")
        self._record_container, self._record_codec = pick_record_format(
            conf.get("record_container", "webm"),
            conf.get("record_codec", "vp8"),
        )
        self._devices = list_cameras()
        saved_device = conf.get("device", "")
        if saved_device and any(d.path == saved_device for d in self._devices):
            self._device_path = saved_device
        else:
            self._device_path = self._devices[0].path if self._devices else ""

        toolbar = add_classes(Gtk.Box(spacing=8), "fos-app-toolbar", "fos-camera-toolbar")
        self.device_combo = add_classes(Gtk.ComboBoxText(), "fos-input")
        for device in self._devices:
            self.device_combo.append(device.path, f"{device.name} ({Path(device.path).name})")
        if self._device_path:
            self.device_combo.set_active_id(self._device_path)
        self.device_combo.set_sensitive(len(self._devices) > 1)
        self.device_combo.connect("changed", self._on_device_changed)
        toolbar.pack_start(self.device_combo, True, True, 0)

        self.settings_btn = button(
            "Settings",
            icon_name="preferences-system-symbolic",
            variant="outline",
            size="sm",
            tooltip="Camera settings",
        )
        self.settings_btn.connect("clicked", lambda _b: self.toggle_settings())
        toolbar.pack_start(self.settings_btn, False, False, 0)

        self.photo_btn = button(
            "Take photo",
            icon_name="camera-photo-symbolic",
            variant="default",
            size="sm",
            tooltip="Save a still to Pictures",
        )
        self.photo_btn.connect("clicked", lambda _b: self.take_photo())
        toolbar.pack_start(self.photo_btn, False, False, 0)

        self.record_btn = button(
            "Record",
            icon_name="media-record-symbolic",
            variant="outline",
            size="sm",
            tooltip="Record video to Videos (WebM)",
        )
        self.record_btn.connect("clicked", lambda _b: self.toggle_recording())
        toolbar.pack_start(self.record_btn, False, False, 0)
        self.body.pack_start(toolbar, False, False, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        content.set_hexpand(True)
        content.set_vexpand(True)

        self.preview_box = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-camera-preview")
        self.preview_box.set_hexpand(True)
        self.preview_box.set_vexpand(True)
        self.placeholder = label("No camera found.", "fos-text", "fos-muted", xalign=0.5)
        self.placeholder.set_valign(Gtk.Align.CENTER)
        self.placeholder.set_hexpand(True)
        self.placeholder.set_vexpand(True)
        self.preview_box.pack_start(self.placeholder, True, True, 0)
        content.pack_start(self.preview_box, True, True, 0)

        self.settings_panel = add_classes(
            Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0),
            "fos-camera-settings",
        )
        self.settings_panel.set_size_request(300, -1)
        # Keep hidden from window show_all until we open it. On this GTK,
        # show_all() on a no_show_all widget does not call show() — use
        # _set_settings_visible() which clears the flag before showing.
        self.settings_panel.set_no_show_all(True)
        settings_header = add_classes(Gtk.Box(spacing=8), "fos-camera-settings-header")
        settings_header.pack_start(label("Settings", "fos-label"), True, True, 0)
        content.pack_start(self.settings_panel, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        self.settings_box = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "fos-camera-settings-body")
        scroll.add(self.settings_box)
        self.settings_panel.pack_start(settings_header, False, False, 0)
        self.settings_panel.pack_start(scroll, True, True, 0)

        self.body.pack_start(content, True, True, 0)

        footer = add_classes(Gtk.Box(spacing=12), "fos-app-footer")
        self.status = label("", "fos-small", "fos-muted", ellipsize=True)
        footer.pack_start(self.status, True, True, 0)
        self.body.pack_start(footer, False, False, 0)

        self.connect("destroy", self._on_destroy)
        set_class(self.settings_btn, "active", self._settings_open)

        if self._devices:
            self._reload_modes(conf)
            self._rebuild_settings()
            self.start_pipeline(self._device_path)
            self._refresh_controls()
        else:
            self.status.set_text("No Video/Source device available.")
            self.photo_btn.set_sensitive(False)
            self.record_btn.set_sensitive(False)
            self.settings_btn.set_sensitive(False)
        self._set_settings_visible(self._settings_open)

    def _on_destroy(self, *_args) -> None:
        if self._recording:
            self.stop_recording(finalize_only=True)
        self._persist()
        self.stop_pipeline()

    def _persist(self) -> None:
        values = {
            "device": self._device_path,
            "mirror": "1" if self._mirror else "0",
            "settings_open": "1" if self._settings_open else "0",
            "record_container": self._record_container.key,
            "record_codec": self._record_codec.key,
        }
        if self._mode is not None:
            values["fourcc"] = self._mode.fourcc
            values["width"] = str(self._mode.width)
            values["height"] = str(self._mode.height)
            values["fps"] = f"{self._mode.fps:g}"
        save_config(values)

    def _set_settings_visible(self, visible: bool) -> None:
        """Show/hide the side panel. GTK skips show_all when no_show_all is set."""
        if visible:
            self.settings_panel.set_no_show_all(False)
            self.settings_panel.show_all()
            self._refresh_controls()
        else:
            self.settings_panel.hide()
            self.settings_panel.set_no_show_all(True)

    def toggle_settings(self) -> None:
        self._settings_open = not self._settings_open
        set_class(self.settings_btn, "active", self._settings_open)
        self._set_settings_visible(self._settings_open)
        self._persist()

    def _on_device_changed(self, combo: Gtk.ComboBoxText) -> None:
        path = combo.get_active_id() or ""
        if not path or path == self._device_path or self._updating_ui:
            return
        if self._recording:
            self.stop_recording()
        self._device_path = path
        self._reload_modes({})
        self._rebuild_settings()
        self.start_pipeline(path)
        self._refresh_controls()
        self._persist()

    def _reload_modes(self, conf: dict[str, str]) -> None:
        self._modes = list_capture_modes(self._device_path) if self._device_path else []
        self._mode = None
        if not self._modes:
            return
        want_fourcc = conf.get("fourcc", "")
        want_w = conf.get("width", "")
        want_h = conf.get("height", "")
        for mode in self._modes:
            if (
                want_fourcc
                and mode.fourcc == want_fourcc
                and str(mode.width) == want_w
                and str(mode.height) == want_h
            ):
                self._mode = mode
                break
        if self._mode is None:
            # Prefer 1280×720 MJPG when available, else first sorted mode.
            for mode in self._modes:
                if mode.fourcc == "MJPG" and mode.width == 1280 and mode.height == 720:
                    self._mode = mode
                    break
            if self._mode is None:
                self._mode = self._modes[0]

    def _rebuild_settings(self) -> None:
        clear(self.settings_box)
        self._ctrl_scales.clear()
        self._ctrl_switches.clear()

        self.settings_box.pack_start(label("Capture", "fos-small", "fos-muted"), False, False, 0)

        res_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        res_row.pack_start(label("Resolution", "fos-text"), False, False, 0)
        self.res_combo = add_classes(Gtk.ComboBoxText(), "fos-input")
        for mode in self._modes:
            self.res_combo.append(mode.key, mode.label)
        if self._mode is not None:
            self.res_combo.set_active_id(self._mode.key)
        self.res_combo.connect("changed", self._on_resolution_changed)
        res_row.pack_start(self.res_combo, False, False, 0)
        self.settings_box.pack_start(res_row, False, False, 0)

        mirror_row = add_classes(Gtk.Box(spacing=8), "fos-camera-setting-row")
        mirror_row.pack_start(label("Mirror preview", "fos-text"), True, True, 0)
        self.mirror_switch = add_classes(Gtk.Switch(), "fos-switch")
        self.mirror_switch.set_active(self._mirror)
        self.mirror_switch.set_valign(Gtk.Align.CENTER)
        self.mirror_switch.connect("notify::active", self._on_mirror_switch)
        mirror_row.pack_start(self.mirror_switch, False, False, 0)
        self.settings_box.pack_start(mirror_row, False, False, 0)

        self.settings_box.pack_start(label("Recording", "fos-small", "fos-muted"), False, False, 0)

        file_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        file_row.pack_start(label("File type", "fos-text"), False, False, 0)
        self.container_combo = add_classes(Gtk.ComboBoxText(), "fos-input")
        for container in available_record_containers():
            self.container_combo.append(container.key, f"{container.label} (.{container.extension})")
        self.container_combo.set_active_id(self._record_container.key)
        self.container_combo.connect("changed", self._on_container_changed)
        file_row.pack_start(self.container_combo, False, False, 0)
        self.settings_box.pack_start(file_row, False, False, 0)

        enc_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        enc_row.pack_start(label("Video encoder", "fos-text"), False, False, 0)
        self.codec_combo = add_classes(Gtk.ComboBoxText(), "fos-input")
        self._fill_codec_combo()
        self.codec_combo.connect("changed", self._on_codec_changed)
        enc_row.pack_start(self.codec_combo, False, False, 0)
        self.settings_box.pack_start(enc_row, False, False, 0)

        self.record_hint = label(
            f"Saves to Videos as Camera-*.{self._record_container.extension}",
            "fos-small",
            "fos-muted",
        )
        self.settings_box.pack_start(self.record_hint, False, False, 0)

        self.settings_box.pack_start(label("Image", "fos-small", "fos-muted"), False, False, 0)
        self._image_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.settings_box.pack_start(self._image_box, False, False, 0)

        reset = button("Reset image controls", variant="outline", size="sm")
        reset.connect("clicked", lambda _b: self.reset_image_controls())
        self.settings_box.pack_start(reset, False, False, 0)

        self.settings_box.show_all()

    def _on_resolution_changed(self, combo: Gtk.ComboBoxText) -> None:
        if self._updating_ui:
            return
        key = combo.get_active_id() or ""
        mode = next((m for m in self._modes if m.key == key), None)
        if mode is None or mode == self._mode:
            return
        if self._recording:
            self.stop_recording()
        self._mode = mode
        self.start_pipeline(self._device_path)
        self._refresh_controls()
        self._persist()

    def _fill_codec_combo(self) -> None:
        self._updating_ui = True
        self.codec_combo.remove_all()
        codecs = available_codecs_for(self._record_container)
        for codec in codecs:
            self.codec_combo.append(codec.key, codec.label)
        if self._record_codec.key not in {c.key for c in codecs} and codecs:
            self._record_codec = codecs[0]
        if codecs:
            self.codec_combo.set_active_id(self._record_codec.key)
        self.codec_combo.set_sensitive(len(codecs) > 1)
        self._updating_ui = False

    def _on_container_changed(self, combo: Gtk.ComboBoxText) -> None:
        if self._updating_ui:
            return
        key = combo.get_active_id() or ""
        container = container_by_key(key)
        if container is None or container.key == self._record_container.key:
            return
        if self._recording:
            self.stop_recording()
        codecs = available_codecs_for(container)
        if not codecs:
            self.status.set_text(f"No encoders available for {container.label}.")
            self._updating_ui = True
            self.container_combo.set_active_id(self._record_container.key)
            self._updating_ui = False
            return
        self._record_container = container
        if self._record_codec.key not in {c.key for c in codecs}:
            self._record_codec = codecs[0]
        self._fill_codec_combo()
        if hasattr(self, "record_hint"):
            self.record_hint.set_text(f"Saves to Videos as Camera-*.{container.extension}")
        self.start_pipeline(self._device_path)
        self._refresh_controls()
        self._persist()
        self._refresh_status()
        self._update_record_button()

    def _on_codec_changed(self, combo: Gtk.ComboBoxText) -> None:
        if self._updating_ui:
            return
        key = combo.get_active_id() or ""
        codec = codec_by_key(key)
        if codec is None or codec.key == self._record_codec.key:
            return
        if codec.key not in self._record_container.codecs:
            return
        if self._recording:
            self.stop_recording()
        self._record_codec = codec
        self.start_pipeline(self._device_path)
        self._persist()
        self._refresh_status()
        self._update_record_button()

    def _on_mirror_switch(self, switch: Gtk.Switch, _pspec) -> None:
        if self._updating_ui:
            return
        self._mirror = switch.get_active()
        if self._flip is not None:
            self._flip.set_property("method", "horizontal-flip" if self._mirror else "none")
        self._refresh_status()
        self._persist()

    def _refresh_controls(self) -> None:
        if not self._device_path or not hasattr(self, "_image_box"):
            return
        clear(self._image_box)
        self._ctrl_scales.clear()
        self._ctrl_switches.clear()
        controls = list_v4l_controls(self._device_path)

        for name, title in BOOL_CTRLS:
            ctrl = controls.get(name)
            if ctrl is None or ctrl.kind != "bool":
                continue
            row = add_classes(Gtk.Box(spacing=8), "fos-camera-setting-row")
            row.pack_start(label(title, "fos-text"), True, True, 0)
            switch = add_classes(Gtk.Switch(), "fos-switch")
            switch.set_active(bool(ctrl.value))
            switch.set_sensitive(not ctrl.inactive)
            switch.set_valign(Gtk.Align.CENTER)
            switch.connect("notify::active", self._on_bool_ctrl, name)
            row.pack_start(switch, False, False, 0)
            self._image_box.pack_start(row, False, False, 0)
            self._ctrl_switches[name] = switch

        for name, title in IMAGE_CTRLS:
            ctrl = controls.get(name)
            if ctrl is None or ctrl.kind != "int":
                continue
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            head = Gtk.Box(spacing=8)
            head.pack_start(label(title, "fos-text"), True, True, 0)
            value_lbl = label(str(ctrl.value), "fos-small", "fos-muted")
            head.pack_start(value_lbl, False, False, 0)
            col.pack_start(head, False, False, 0)
            scale = add_classes(
                Gtk.Scale.new_with_range(
                    Gtk.Orientation.HORIZONTAL,
                    ctrl.minimum,
                    ctrl.maximum,
                    ctrl.step,
                ),
                "fos-scale",
            )
            scale.set_draw_value(False)
            scale.set_value(ctrl.value)
            scale.set_sensitive(not ctrl.inactive)
            scale.connect("value-changed", self._on_int_ctrl, name, value_lbl)
            col.pack_start(scale, False, False, 0)
            self._image_box.pack_start(col, False, False, 0)
            self._ctrl_scales[name] = scale

        if not self._ctrl_scales and not self._ctrl_switches:
            self._image_box.pack_start(
                label("No image controls for this device.", "fos-small", "fos-muted"),
                False,
                False,
                0,
            )
        self._image_box.show_all()

    def _on_int_ctrl(self, scale: Gtk.Scale, name: str, value_lbl: Gtk.Label) -> None:
        if self._updating_ui or not self._device_path:
            return
        value = int(round(scale.get_value()))
        value_lbl.set_text(str(value))
        if not set_v4l_control(self._device_path, name, value):
            self.status.set_text(f"Could not set {name}.")

    def _on_bool_ctrl(self, switch: Gtk.Switch, _pspec, name: str) -> None:
        if self._updating_ui or not self._device_path:
            return
        if not set_v4l_control(self._device_path, name, 1 if switch.get_active() else 0):
            self.status.set_text(f"Could not set {name}.")
            return
        # Auto white balance toggles temperature activity — refresh sliders.
        GLib.timeout_add(150, self._deferred_refresh_controls)

    def _deferred_refresh_controls(self) -> bool:
        self._refresh_controls()
        return False

    def reset_image_controls(self) -> None:
        if not self._device_path:
            return
        controls = list_v4l_controls(self._device_path)
        for name, _title in (*BOOL_CTRLS, *IMAGE_CTRLS):
            ctrl = controls.get(name)
            if ctrl is None or ctrl.inactive:
                continue
            set_v4l_control(self._device_path, name, ctrl.default)
        self._refresh_controls()
        self.status.set_text("Image controls reset.")

    def stop_pipeline(self) -> None:
        if self._recording:
            self.stop_recording(finalize_only=True)
        self._stop_record_timer()
        if self._bus is not None:
            if self._bus_handler is not None:
                self._bus.disconnect(self._bus_handler)
                self._bus_handler = None
            self._bus.remove_signal_watch()
            self._bus = None
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
        self._flip = None
        self._appsink = None
        self._rec_valve = None
        self._rec_file = None
        self._rec_mux = None
        self._rec_encoder = None
        if self._sink_widget is not None:
            self.preview_box.remove(self._sink_widget)
            self._sink_widget = None

    def _caps_fragment(self) -> str:
        mode = self._mode or CaptureMode("MJPG", 640, 480, 30.0)
        fps = max(1, int(round(mode.fps)))
        if mode.fourcc == "MJPG":
            return f"image/jpeg,width={mode.width},height={mode.height},framerate={fps}/1 ! jpegdec"
        raw = _gst_raw_format(mode.fourcc)
        return (
            f"video/x-raw,format={raw},width={mode.width},height={mode.height},"
            f"framerate={fps}/1"
        )

    def _record_encode_fragment(self) -> str:
        """Encoder chain for the recording branch (may add parsers for MP4)."""
        fragment = self._record_codec.fragment
        if self._record_codec.key == "h264":
            fragment += " ! video/x-h264,profile=constrained-baseline"
            if gst_element_available("h264parse"):
                fragment += " ! h264parse"
        return fragment

    def _recording_looks_valid(self, path: Path) -> bool:
        if not path.is_file() or path.stat().st_size < 1000:
            return False
        # MP4 without a moov atom looks like a black / unplayable clip in players.
        if path.suffix.lower() == ".mp4":
            try:
                raw = path.read_bytes()
            except OSError:
                return False
            return b"moov" in raw and (b"avc1" in raw or b"mp4v" in raw)
        return True

    def start_pipeline(self, device: str) -> None:
        self.stop_pipeline()
        for child in list(self.preview_box.get_children()):
            self.preview_box.remove(child)

        flip_method = "horizontal-flip" if self._mirror else "none"
        caps = self._caps_fragment()
        placeholder = Path(f"/tmp/fosos-camera-placeholder.{self._record_container.extension}")
        encode = self._record_encode_fragment()
        mux = f"{self._record_container.element} name=recmux"
        # Flip once before the tee so preview, photos, and recordings match.
        desc = (
            f"v4l2src device={device} name=src ! {caps} ! "
            f"videoconvert ! videoflip name=flip method={flip_method} ! tee name=t "
            f"t. ! queue ! gtksink name=sink sync=false "
            f"t. ! queue max-size-buffers=2 leaky=downstream ! videoconvert ! "
            f"video/x-raw,format=RGB ! appsink name=snap max-buffers=1 drop=true sync=false "
            f"t. ! queue max-size-buffers=0 max-size-time=0 max-size-bytes=0 ! "
            f"valve name=recvalve drop=true ! videoconvert ! "
            f"{encode} ! {mux} ! "
            f"filesink name=recfile location={placeholder} sync=false async=false"
        )
        try:
            pipeline = Gst.parse_launch(desc)
        except GLib.Error as exc:
            self.placeholder = label(f"Could not open camera: {exc}", "fos-text", "fos-muted", xalign=0.5)
            self.placeholder.set_valign(Gtk.Align.CENTER)
            self.placeholder.set_hexpand(True)
            self.placeholder.set_vexpand(True)
            self.preview_box.pack_start(self.placeholder, True, True, 0)
            self.preview_box.show_all()
            self.status.set_text(str(exc))
            self.photo_btn.set_sensitive(False)
            self.record_btn.set_sensitive(False)
            return

        assert isinstance(pipeline, Gst.Pipeline)
        sink = pipeline.get_by_name("sink")
        flip = pipeline.get_by_name("flip")
        appsink = pipeline.get_by_name("snap")
        rec_valve = pipeline.get_by_name("recvalve")
        rec_file = pipeline.get_by_name("recfile")
        rec_mux = pipeline.get_by_name("recmux")
        rec_encoder = pipeline.get_by_name("encoder")
        if sink is None or appsink is None or rec_valve is None or rec_file is None or rec_mux is None:
            self.status.set_text("GStreamer camera elements missing.")
            self.photo_btn.set_sensitive(False)
            self.record_btn.set_sensitive(False)
            return

        widget = sink.get_property("widget")
        if widget is None:
            self.status.set_text("gtksink did not provide a widget.")
            self.photo_btn.set_sensitive(False)
            self.record_btn.set_sensitive(False)
            return

        widget.set_hexpand(True)
        widget.set_vexpand(True)
        self.preview_box.pack_start(widget, True, True, 0)
        self._sink_widget = widget
        self._flip = flip
        self._appsink = appsink
        self._rec_valve = rec_valve
        self._rec_file = rec_file
        self._rec_mux = rec_mux
        self._rec_encoder = rec_encoder
        self.pipeline = pipeline

        bus = pipeline.get_bus()
        bus.add_signal_watch()
        self._bus = bus
        self._bus_handler = bus.connect("message", self._on_bus_message)

        ret = pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            self.status.set_text(f"Failed to start {device}.")
            self.photo_btn.set_sensitive(False)
            self.record_btn.set_sensitive(False)
            self.stop_pipeline()
            self.placeholder = label("Camera failed to start.", "fos-text", "fos-muted", xalign=0.5)
            self.placeholder.set_valign(Gtk.Align.CENTER)
            self.preview_box.pack_start(self.placeholder, True, True, 0)
            self.preview_box.show_all()
            return

        self.photo_btn.set_sensitive(True)
        self.record_btn.set_sensitive(True)
        self.preview_box.show_all()
        self._refresh_status()

    def _on_bus_message(self, _bus: Gst.Bus, message: Gst.Message) -> None:
        if message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            text = err.message if err else "Camera error"
            self.status.set_text(text)
            if debug:
                print(f"fosos-camera: {text} ({debug})", file=sys.stderr)
            if self._recording:
                self.stop_recording(finalize_only=True)
        elif message.type == Gst.MessageType.EOS and not self._recording:
            self.status.set_text("Camera stream ended.")

    def _refresh_status(self) -> None:
        if self._recording and self._record_path is not None:
            elapsed = max(0, int(time.monotonic() - self._record_started))
            mins, secs = divmod(elapsed, 60)
            self.status.set_text(f"Recording {mins:02d}:{secs:02d} · {self._record_path.name}")
            return
        name = next((d.name for d in self._devices if d.path == self._device_path), self._device_path)
        bits = [name or "Camera"]
        if self._mode is not None:
            bits.append(f"{self._mode.width}×{self._mode.height}")
            bits.append(self._mode.fourcc)
        bits.append(f"{self._record_container.label}/{self._record_codec.label}")
        if self._mirror:
            bits.append("mirrored")
        self.status.set_text(" · ".join(b for b in bits if b))

    def _next_video_path(self) -> Path:
        dest_dir = videos_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        ext = self._record_container.extension
        path = dest_dir / f"Camera-{stamp}.{ext}"
        index = 1
        while path.exists():
            path = dest_dir / f"Camera-{stamp}-{index}.{ext}"
            index += 1
        return path

    def _update_record_button(self) -> None:
        set_class(self.record_btn, "destructive", self._recording)
        set_class(self.record_btn, "active", self._recording)
        icon_name = "media-playback-stop-symbolic" if self._recording else "media-record-symbolic"
        text = "Stop" if self._recording else "Record"
        child = self.record_btn.get_child()
        if isinstance(child, Gtk.Box):
            for widget in child.get_children():
                if isinstance(widget, Gtk.Image):
                    widget.set_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
                    widget.set_pixel_size(16)
                elif isinstance(widget, Gtk.Label):
                    widget.set_text(text)
        ext = self._record_container.extension
        self.record_btn.set_tooltip_text(
            "Stop recording"
            if self._recording
            else f"Record video to Videos (.{ext}, {self._record_codec.label})"
        )

    def _stop_record_timer(self) -> None:
        if self._record_timer is not None:
            GLib.source_remove(self._record_timer)
            self._record_timer = None

    def _on_record_tick(self) -> bool:
        if not self._recording:
            self._record_timer = None
            return False
        self._refresh_status()
        return True

    def toggle_recording(self) -> None:
        if self._recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self) -> None:
        if self._recording or self._rec_valve is None or self._rec_file is None or self._rec_mux is None:
            return
        if self.pipeline is None:
            self.status.set_text("Camera is not running.")
            return
        path = self._next_video_path()
        try:
            # Reset encoder + mux + sink so MP4 gets fresh SPS/PPS / moov headers.
            # Leaving x264enc running across a closed valve produced unplayable
            # (black) MP4 files with mdat but no moov/avc1.
            self._rec_valve.set_property("drop", True)
            self._rec_file.set_state(Gst.State.NULL)
            self._rec_mux.set_state(Gst.State.NULL)
            if self._rec_encoder is not None:
                self._rec_encoder.set_state(Gst.State.NULL)
            self._rec_file.set_property("location", str(path))
            if self._rec_encoder is not None:
                self._rec_encoder.sync_state_with_parent()
            self._rec_mux.sync_state_with_parent()
            self._rec_file.sync_state_with_parent()
            self._rec_valve.set_property("drop", False)
        except GLib.Error as exc:
            self.status.set_text(f"Could not start recording: {exc}")
            return

        self._recording = True
        self._record_path = path
        self._record_started = time.monotonic()
        self._update_record_button()
        self.device_combo.set_sensitive(False)
        if hasattr(self, "res_combo"):
            self.res_combo.set_sensitive(False)
        if hasattr(self, "container_combo"):
            self.container_combo.set_sensitive(False)
        if hasattr(self, "codec_combo"):
            self.codec_combo.set_sensitive(False)
        self._stop_record_timer()
        self._record_timer = GLib.timeout_add_seconds(1, self._on_record_tick)
        self._refresh_status()

    def _close_recording_branch(self) -> None:
        """EOS the record branch, then NULL encoder/mux/filesink (do not sync)."""
        if self._rec_valve is not None:
            self._rec_valve.set_property("drop", True)
            src = self._rec_valve.get_static_pad("src")
            peer = src.get_peer() if src is not None else None
            if peer is not None:
                peer.send_event(Gst.Event.new_eos())
        # Let mp4mux flush the moov atom. Do not timed_pop the shared bus
        # (signal watch is already attached for pipeline errors).
        time.sleep(0.25)
        if self._rec_file is not None:
            self._rec_file.set_state(Gst.State.NULL)
        if self._rec_mux is not None:
            self._rec_mux.set_state(Gst.State.NULL)
        if self._rec_encoder is not None:
            self._rec_encoder.set_state(Gst.State.NULL)

    def stop_recording(self, *, finalize_only: bool = False) -> None:
        if not self._recording:
            return
        path = self._record_path
        self._close_recording_branch()

        self._recording = False
        self._record_path = None
        self._stop_record_timer()
        self._update_record_button()
        self.device_combo.set_sensitive(len(self._devices) > 1)
        if hasattr(self, "res_combo"):
            self.res_combo.set_sensitive(True)
        if hasattr(self, "container_combo"):
            self.container_combo.set_sensitive(True)
        if hasattr(self, "codec_combo"):
            self.codec_combo.set_sensitive(len(available_codecs_for(self._record_container)) > 1)

        if path is not None and self._recording_looks_valid(path):
            if not finalize_only:
                notify_saved(path, title="Video saved", icon="camera-video-symbolic")
                self.status.set_text(f"Saved {path.name}")
            else:
                self._refresh_status()
        else:
            if path is not None and path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
            if not finalize_only:
                self.status.set_text("Recording failed — try WebM/VP8, or record a bit longer.")
            else:
                self._refresh_status()

    def take_photo(self) -> None:
        if self._appsink is None:
            self.status.set_text("Camera is not running.")
            return
        sample = self._appsink.emit("pull-sample")
        if sample is None:
            self.status.set_text("No frame ready yet — try again.")
            return
        path = self._save_sample(sample)
        if path is None:
            self.status.set_text("Could not save photo.")
            return
        notify_saved(path)
        self.status.set_text(f"Saved {path.name}")

    def _save_sample(self, sample: Gst.Sample) -> Path | None:
        buf = sample.get_buffer()
        caps = sample.get_caps()
        if buf is None or caps is None:
            return None
        try:
            info = GstVideo.VideoInfo.new_from_caps(caps)
        except (GLib.Error, TypeError, ValueError):
            return None
        width, height = int(info.width), int(info.height)
        if width <= 0 or height <= 0:
            return None
        success, mapinfo = buf.map(Gst.MapFlags.READ)
        if not success:
            return None
        try:
            data = bytes(mapinfo.data)
        finally:
            buf.unmap(mapinfo)

        rowstride = width * 3
        expected = rowstride * height
        if len(data) < expected:
            return None
        pixbuf = GdkPixbuf.Pixbuf.new_from_data(
            data,
            GdkPixbuf.Colorspace.RGB,
            False,
            8,
            width,
            height,
            rowstride,
            None,
            None,
        )
        pixbuf = pixbuf.copy()

        dest_dir = pictures_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = dest_dir / f"Camera-{stamp}.jpg"
        index = 1
        while path.exists():
            path = dest_dir / f"Camera-{stamp}-{index}.jpg"
            index += 1
        try:
            pixbuf.savev(str(path), "jpeg", ["quality"], ["92"])
        except GLib.Error as exc:
            print(f"fosos-camera: save failed: {exc}", file=sys.stderr)
            return None
        return path


class CameraApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window: CameraWindow | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_prgname("fosos-camera")
        GLib.set_application_name("Camera")
        Gst.init(None)
        load_css()

    def do_activate(self) -> None:
        if self.window is None:
            self.window = CameraWindow(self)
            self.window.show_all()
            # Re-apply after window show_all (respects no_show_all).
            self.window._set_settings_visible(self.window._settings_open)
        self.window.present()


def main() -> int:
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print("fosos-camera: no display available", file=sys.stderr)
        return 1
    return CameraApp().run(sys.argv)
