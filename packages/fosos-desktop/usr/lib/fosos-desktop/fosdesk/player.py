"""FosOS Videos: simple CardWindow video player via GStreamer playbin."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gst", "1.0")
gi.require_version("GstVideo", "1.0")
from gi.repository import Gdk, Gio, GLib, Gst, Gtk

from .apps import user_dir
from .filechooser import ChooserFilter
from .ui import add_classes, button, fos_file_chooser, label, load_css, set_class
from .windowchrome import CardWindow

APP_ID = "org.fosos.Videos"

VIDEO_FILTER = ChooserFilter(
    "Videos",
    [
        (0, "*.mp4"),
        (0, "*.mkv"),
        (0, "*.webm"),
        (0, "*.avi"),
        (0, "*.mov"),
        (0, "*.m4v"),
        (0, "*.ogv"),
        (0, "*.mpeg"),
        (0, "*.mpg"),
        (1, "video/*"),
    ],
)


def format_clock(ns: int) -> str:
    if ns < 0:
        ns = 0
    total = int(ns // Gst.SECOND)
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


class VideosWindow(CardWindow):
    def __init__(self, app: "VideosApp", open_path: Path | None = None) -> None:
        super().__init__(
            app,
            title="Videos",
            icon_name="multimedia-player-symbolic",
            default_width=960,
            default_height=640,
        )
        self.set_icon_name("multimedia-player")
        add_classes(self, "fos-videos-shell")
        self.app = app
        self.path: Path | None = None
        self.playbin: Gst.Element | None = None
        self._sink: Gst.Element | None = None
        self._sink_widget: Gtk.Widget | None = None
        self._bus: Gst.Bus | None = None
        self._bus_handler: int | None = None
        self._tick: int | None = None
        self._seeking = False
        self._duration_ns = 0
        self._playing = False
        self._muted = False
        self._volume = 0.8

        toolbar = add_classes(Gtk.Box(spacing=8), "fos-app-toolbar", "fos-videos-toolbar")
        open_btn = button(
            "Open",
            icon_name="document-open-symbolic",
            variant="outline",
            size="sm",
            tooltip="Open a video file",
        )
        open_btn.connect("clicked", lambda _b: self.choose_file())
        toolbar.pack_start(open_btn, False, False, 0)

        self.play_btn = button(
            None,
            icon_name="media-playback-start-symbolic",
            variant="default",
            size="sm",
            tooltip="Play / Pause (Space)",
        )
        self.play_btn.connect("clicked", lambda _b: self.toggle_play())
        toolbar.pack_start(self.play_btn, False, False, 0)

        stop_btn = button(
            None,
            icon_name="media-playback-stop-symbolic",
            variant="ghost",
            size="sm",
            tooltip="Stop",
        )
        stop_btn.connect("clicked", lambda _b: self.stop())
        toolbar.pack_start(stop_btn, False, False, 0)

        toolbar.pack_start(Gtk.Box(), True, True, 0)

        self.mute_btn = button(
            None,
            icon_name="audio-volume-high-symbolic",
            variant="ghost",
            size="sm",
            tooltip="Mute",
        )
        self.mute_btn.connect("clicked", lambda _b: self.toggle_mute())
        toolbar.pack_start(self.mute_btn, False, False, 0)

        self.volume = add_classes(
            Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.01),
            "fos-scale",
            "fos-videos-volume",
        )
        self.volume.set_draw_value(False)
        self.volume.set_value(self._volume)
        self.volume.set_size_request(100, -1)
        self.volume.set_valign(Gtk.Align.CENTER)
        self.volume.connect("value-changed", self._on_volume)
        toolbar.pack_start(self.volume, False, False, 0)
        self.body.pack_start(toolbar, False, False, 0)

        self.stage = add_classes(Gtk.EventBox(), "fos-videos-stage")
        self.stage.set_visible_window(True)
        self.stage.set_hexpand(True)
        self.stage.set_vexpand(True)
        self.stage.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.stage.connect("button-press-event", self._on_stage_click)

        self.preview = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-videos-preview")
        self.preview.set_hexpand(True)
        self.preview.set_vexpand(True)
        self.placeholder = label("Open a video to play.", "fos-text", "fos-muted", xalign=0.5)
        self.placeholder.set_valign(Gtk.Align.CENTER)
        self.placeholder.set_hexpand(True)
        self.placeholder.set_vexpand(True)
        self.preview.pack_start(self.placeholder, True, True, 0)
        self.stage.add(self.preview)
        self.body.pack_start(self.stage, True, True, 0)

        controls = add_classes(Gtk.Box(spacing=10), "fos-videos-controls")
        self.time_label = label("0:00", "fos-small", "fos-muted")
        self.time_label.set_width_chars(5)
        controls.pack_start(self.time_label, False, False, 0)

        self.seek = add_classes(
            Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.001),
            "fos-scale",
            "fos-videos-seek",
        )
        self.seek.set_draw_value(False)
        self.seek.set_hexpand(True)
        self.seek.set_sensitive(False)
        self.seek.connect("button-press-event", self._on_seek_press)
        self.seek.connect("button-release-event", self._on_seek_release)
        self.seek.connect("value-changed", self._on_seek_changed)
        controls.pack_start(self.seek, True, True, 0)

        self.dur_label = label("0:00", "fos-small", "fos-muted")
        self.dur_label.set_width_chars(5)
        self.dur_label.set_xalign(1.0)
        controls.pack_start(self.dur_label, False, False, 0)
        self.body.pack_start(controls, False, False, 0)

        footer = add_classes(Gtk.Box(spacing=12), "fos-app-footer")
        self.status = label("Ready", "fos-small", "fos-muted", ellipsize=True)
        footer.pack_start(self.status, True, True, 0)
        self.body.pack_start(footer, False, False, 0)

        self.connect("destroy", self._on_destroy)
        self.connect("key-press-event", self._on_key)
        self._set_transport_sensitive(False)

        if open_path is not None:
            GLib.idle_add(self.open_path, open_path)

    def _on_destroy(self, *_args) -> None:
        self._teardown()

    def _on_key(self, _w, event: Gdk.EventKey) -> bool:
        key = event.keyval
        if key in (Gdk.KEY_space, Gdk.KEY_k, Gdk.KEY_K):
            self.toggle_play()
            return True
        if key in (Gdk.KEY_o, Gdk.KEY_O) and (event.state & Gdk.ModifierType.CONTROL_MASK):
            self.choose_file()
            return True
        if key in (Gdk.KEY_m, Gdk.KEY_M):
            self.toggle_mute()
            return True
        if key == Gdk.KEY_Left:
            self._nudge(-5 * Gst.SECOND)
            return True
        if key == Gdk.KEY_Right:
            self._nudge(5 * Gst.SECOND)
            return True
        if key in (Gdk.KEY_Escape,) and self._playing:
            self.pause()
            return True
        return False

    def _on_stage_click(self, _w, event: Gdk.EventButton) -> bool:
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 1:
            if self.path is not None:
                self.toggle_play()
                return True
            self.choose_file()
            return True
        return False

    def choose_file(self) -> None:
        videos = user_dir(GLib.UserDirectory.DIRECTORY_VIDEOS, "Videos")
        filename = fos_file_chooser(
            self,
            title="Open video",
            action=Gtk.FileChooserAction.OPEN,
            ok_label="Open",
            folder=videos if self.path is None else self.path.parent,
            filters=[VIDEO_FILTER, ChooserFilter("All files", [(0, "*")])],
        )
        if filename:
            self.open_path(Path(filename))

    def _make_video_sink(self) -> tuple[Gst.Element | None, Gtk.Widget | None]:
        """playbin sink that always paints opaque frames.

        gtksink maps BGRA to a cairo surface with alpha. On this uncomposited
        X11 session those frames do not replace the window pixels, so the
        player ghosts into Files and names look double-drawn (bold).
        """
        sink = Gst.ElementFactory.make("gtksink", "gtksink")
        convert = Gst.ElementFactory.make("videoconvert", "vconv")
        capsfilter = Gst.ElementFactory.make("capsfilter", "vcaps")
        if sink is None or convert is None or capsfilter is None:
            return None, None
        try:
            sink.set_property("force-aspect-ratio", True)
            sink.set_property("ignore-alpha", True)
        except Exception:
            pass
        capsfilter.set_property("caps", Gst.Caps.from_string("video/x-raw,format=BGRx"))
        bin_ = Gst.Bin.new("videosink")
        if bin_ is None:
            return None, None
        for element in (convert, capsfilter, sink):
            bin_.add(element)
        if not convert.link(capsfilter) or not capsfilter.link(sink):
            return None, None
        sinkpad = convert.get_static_pad("sink")
        ghost = Gst.GhostPad.new("sink", sinkpad) if sinkpad is not None else None
        if ghost is None or not bin_.add_pad(ghost):
            return None, None
        widget = sink.get_property("widget")
        if widget is None:
            return None, None
        return bin_, widget

    def open_path(self, path: Path) -> bool:
        path = path.expanduser()
        try:
            path = path.resolve()
        except OSError:
            pass
        if not path.is_file():
            self.status.set_text(f"File not found: {path}")
            return False
        self._teardown()
        self.path = path
        self.set_header_title(path.name)
        self.status.set_text(str(path))
        self._duration_ns = 0
        self.seek.set_value(0)
        self.time_label.set_text("0:00")
        self.dur_label.set_text("0:00")

        for child in list(self.preview.get_children()):
            self.preview.remove(child)

        playbin = Gst.ElementFactory.make("playbin", "playbin")
        sink, widget = self._make_video_sink()
        if playbin is None or sink is None or widget is None:
            self._show_placeholder("GStreamer playbin/gtksink unavailable.")
            self.status.set_text("GStreamer video elements missing.")
            return False

        uri = Gio.File.new_for_path(str(path)).get_uri()
        playbin.set_property("uri", uri)
        playbin.set_property("video-sink", sink)
        playbin.set_property("volume", 0.0 if self._muted else self._volume)
        widget.set_hexpand(True)
        widget.set_vexpand(True)
        self.preview.pack_start(widget, True, True, 0)
        self._sink_widget = widget
        self._sink = sink
        self.playbin = playbin

        bus = playbin.get_bus()
        bus.add_signal_watch()
        self._bus = bus
        self._bus_handler = bus.connect("message", self._on_bus_message)

        ret = playbin.set_state(Gst.State.PAUSED)
        if ret == Gst.StateChangeReturn.FAILURE:
            self._teardown()
            self._show_placeholder("Could not open this video.")
            self.status.set_text(f"Failed to open {path.name}")
            return False

        self.preview.show_all()
        self._set_transport_sensitive(True)
        self._start_tick()
        # Autoplay once the pipeline is ready (async state change).
        GLib.timeout_add(120, self._try_autoplay)
        return False  # for idle_add

    def _try_autoplay(self) -> bool:
        if self.playbin is None:
            return False
        self.play()
        return False

    def _show_placeholder(self, text: str) -> None:
        for child in list(self.preview.get_children()):
            self.preview.remove(child)
        self.placeholder = label(text, "fos-text", "fos-muted", xalign=0.5)
        self.placeholder.set_valign(Gtk.Align.CENTER)
        self.placeholder.set_hexpand(True)
        self.placeholder.set_vexpand(True)
        self.preview.pack_start(self.placeholder, True, True, 0)
        self.preview.show_all()
        self._set_transport_sensitive(False)

    def _teardown(self) -> None:
        self._stop_tick()
        if self._bus is not None and self._bus_handler is not None:
            try:
                self._bus.disconnect(self._bus_handler)
                self._bus.remove_signal_watch()
            except Exception:
                pass
        self._bus = None
        self._bus_handler = None
        if self.playbin is not None:
            self.playbin.set_state(Gst.State.NULL)
        self.playbin = None
        self._sink = None
        if self._sink_widget is not None and self._sink_widget.get_parent() is self.preview:
            self.preview.remove(self._sink_widget)
        self._sink_widget = None
        self._playing = False
        self._update_play_icon()

    def _set_transport_sensitive(self, enabled: bool) -> None:
        self.play_btn.set_sensitive(enabled)
        self.seek.set_sensitive(enabled)

    def _update_play_icon(self) -> None:
        name = "media-playback-pause-symbolic" if self._playing else "media-playback-start-symbolic"
        tip = "Pause (Space)" if self._playing else "Play (Space)"
        child = self.play_btn.get_child()
        if isinstance(child, Gtk.Image):
            child.set_from_icon_name(name, Gtk.IconSize.MENU)
            child.set_pixel_size(16)
        else:
            for c in list(self.play_btn.get_children()):
                self.play_btn.remove(c)
            image = Gtk.Image.new_from_icon_name(name, Gtk.IconSize.MENU)
            image.set_pixel_size(16)
            self.play_btn.add(image)
            self.play_btn.show_all()
        self.play_btn.set_tooltip_text(tip)

    def _update_mute_icon(self) -> None:
        if self._muted or self._volume <= 0.001:
            name = "audio-volume-muted-symbolic"
        elif self._volume < 0.34:
            name = "audio-volume-low-symbolic"
        elif self._volume < 0.67:
            name = "audio-volume-medium-symbolic"
        else:
            name = "audio-volume-high-symbolic"
        child = self.mute_btn.get_child()
        if isinstance(child, Gtk.Image):
            child.set_from_icon_name(name, Gtk.IconSize.MENU)
            child.set_pixel_size(16)
        set_class(self.mute_btn, "active", self._muted)
        self.mute_btn.set_tooltip_text("Unmute" if self._muted else "Mute")

    def play(self) -> None:
        if self.playbin is None:
            return
        self.playbin.set_state(Gst.State.PLAYING)
        self._playing = True
        self._update_play_icon()
        self._start_tick()

    def pause(self) -> None:
        if self.playbin is None:
            return
        self.playbin.set_state(Gst.State.PAUSED)
        self._playing = False
        self._update_play_icon()

    def toggle_play(self) -> None:
        if self.playbin is None:
            self.choose_file()
            return
        if self._playing:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        if self.playbin is None:
            return
        self.pause()
        self._seek_to(0)
        self.seek.set_value(0)
        self.time_label.set_text("0:00")

    def toggle_mute(self) -> None:
        self._muted = not self._muted
        if self.playbin is not None:
            self.playbin.set_property("volume", 0.0 if self._muted else self._volume)
        self._update_mute_icon()

    def _on_volume(self, scale: Gtk.Scale) -> None:
        self._volume = float(scale.get_value())
        if self._volume > 0.001 and self._muted:
            self._muted = False
        if self.playbin is not None:
            self.playbin.set_property("volume", 0.0 if self._muted else self._volume)
        self._update_mute_icon()

    def _on_seek_press(self, _w, _event) -> bool:
        self._seeking = True
        return False

    def _on_seek_release(self, _w, _event) -> bool:
        if self._seeking:
            self._seeking = False
            self._seek_fraction(float(self.seek.get_value()))
        return False

    def _on_seek_changed(self, scale: Gtk.Scale) -> None:
        if not self._seeking or self._duration_ns <= 0:
            return
        pos = int(float(scale.get_value()) * self._duration_ns)
        self.time_label.set_text(format_clock(pos))

    def _seek_fraction(self, fraction: float) -> None:
        if self._duration_ns <= 0:
            return
        fraction = max(0.0, min(1.0, fraction))
        self._seek_to(int(fraction * self._duration_ns))

    def _seek_to(self, position_ns: int) -> None:
        if self.playbin is None:
            return
        position_ns = max(0, position_ns)
        if self._duration_ns > 0:
            position_ns = min(position_ns, max(0, self._duration_ns - Gst.MSECOND))
        self.playbin.seek_simple(
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
            position_ns,
        )

    def _nudge(self, delta_ns: int) -> None:
        if self.playbin is None:
            return
        ok, pos = self.playbin.query_position(Gst.Format.TIME)
        if not ok:
            return
        self._seek_to(pos + delta_ns)

    def _start_tick(self) -> None:
        if self._tick is None:
            self._tick = GLib.timeout_add(250, self._on_tick)

    def _stop_tick(self) -> None:
        if self._tick is not None:
            GLib.source_remove(self._tick)
            self._tick = None

    def _on_tick(self) -> bool:
        if self.playbin is None:
            self._tick = None
            return False
        if self._duration_ns <= 0:
            ok, dur = self.playbin.query_duration(Gst.Format.TIME)
            if ok and dur > 0:
                self._duration_ns = dur
                self.dur_label.set_text(format_clock(dur))
        if not self._seeking:
            ok, pos = self.playbin.query_position(Gst.Format.TIME)
            if ok:
                self.time_label.set_text(format_clock(pos))
                if self._duration_ns > 0:
                    self.seek.set_value(pos / self._duration_ns)
        return True

    def _on_bus_message(self, _bus: Gst.Bus, message: Gst.Message) -> None:
        if message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            text = err.message if err else "Playback error"
            self.status.set_text(text)
            if debug:
                print(f"fosos-videos: {text} ({debug})", file=sys.stderr)
            self.pause()
        elif message.type == Gst.MessageType.EOS:
            self.pause()
            self._seek_to(0)
            self.seek.set_value(0)
            self.time_label.set_text("0:00")
            self.status.set_text("End of video")
        elif message.type == Gst.MessageType.DURATION_CHANGED:
            self._duration_ns = 0
        elif message.type == Gst.MessageType.STATE_CHANGED and message.src == self.playbin:
            _old, new, _pending = message.parse_state_changed()
            self._playing = new == Gst.State.PLAYING
            self._update_play_icon()


class VideosApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_OPEN | Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.window: VideosWindow | None = None
        self._pending: Path | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_prgname("fosos-videos")
        GLib.set_application_name("Videos")
        Gst.init(None)
        load_css()

    def do_activate(self) -> None:
        if self.window is None:
            self.window = VideosWindow(self, open_path=self._pending)
            self._pending = None
            self.window.show_all()
            self.window._update_mute_icon()
        self.window.present()

    def do_open(self, files, _n_files, _hint) -> None:
        path: Path | None = None
        for f in files:
            candidate = Path(f.get_path() or "")
            if candidate.is_file():
                path = candidate
                break
        if path is None:
            self.do_activate()
            return
        if self.window is None:
            self._pending = path
            self.do_activate()
            return
        self.window.open_path(path)
        self.window.present()

    def do_command_line(self, command_line):
        argv = command_line.get_arguments()[1:]
        path: Path | None = None
        for arg in argv:
            candidate = Path(arg).expanduser()
            if candidate.is_file():
                path = candidate
                break
        if path is not None:
            if self.window is None:
                self._pending = path
                self.do_activate()
            else:
                self.window.open_path(path)
                self.window.present()
        else:
            self.do_activate()
        return 0


def main() -> int:
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print("fosos-videos: no display available", file=sys.stderr)
        return 1
    return VideosApp().run(sys.argv)
