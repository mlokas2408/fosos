"""org.freedesktop.Notifications server, popups and the notification list."""

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from . import VERSION
from .popup import Popup
from .ui import add_classes, button, clear, icon, label

BUS_NAME = "org.freedesktop.Notifications"
OBJECT_PATH = "/org/freedesktop/Notifications"
INTERFACE_XML = """
<node>
  <interface name="org.freedesktop.Notifications">
    <method name="GetCapabilities">
      <arg type="as" name="capabilities" direction="out"/>
    </method>
    <method name="Notify">
      <arg type="s" name="app_name" direction="in"/>
      <arg type="u" name="replaces_id" direction="in"/>
      <arg type="s" name="app_icon" direction="in"/>
      <arg type="s" name="summary" direction="in"/>
      <arg type="s" name="body" direction="in"/>
      <arg type="as" name="actions" direction="in"/>
      <arg type="a{sv}" name="hints" direction="in"/>
      <arg type="i" name="expire_timeout" direction="in"/>
      <arg type="u" name="id" direction="out"/>
    </method>
    <method name="CloseNotification">
      <arg type="u" name="id" direction="in"/>
    </method>
    <method name="GetServerInformation">
      <arg type="s" name="name" direction="out"/>
      <arg type="s" name="vendor" direction="out"/>
      <arg type="s" name="version" direction="out"/>
      <arg type="s" name="spec_version" direction="out"/>
    </method>
    <signal name="NotificationClosed">
      <arg type="u" name="id"/>
      <arg type="u" name="reason"/>
    </signal>
    <signal name="ActionInvoked">
      <arg type="u" name="id"/>
      <arg type="s" name="action_key"/>
    </signal>
  </interface>
</node>
"""

DEFAULT_TIMEOUT_MS = 6000
POPUP_WIDTH = 360
MAX_POPUPS = 4
HISTORY_LIMIT = 50

EXPIRED, DISMISSED, CLOSED_BY_CALL = 1, 2, 3


def safe_markup(text: str) -> str:
    try:
        Pango.parse_markup(text, -1, "\0")
    except GLib.Error:
        return GLib.markup_escape_text(text)
    return text


def notification_icon(app_icon: str, hints: dict) -> Gtk.Image:
    path = hints.get("image-path") or hints.get("image_path") or app_icon
    if path.startswith("file://"):
        path = GLib.filename_from_uri(path)[0]
    if path.startswith("/"):
        try:
            image = Gtk.Image.new_from_icon_name("dialog-information-symbolic", Gtk.IconSize.MENU)
            from gi.repository import GdkPixbuf

            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 16, 16, True)
            image.set_from_pixbuf(pixbuf)
            return image
        except GLib.Error:
            pass
    return icon(path or "dialog-information-symbolic", 16)


class Notification:
    def __init__(self, nid, app_name, app_icon, summary, body, actions, hints, timeout) -> None:
        self.id = nid
        self.app_name = app_name or "FosOS"
        self.app_icon = app_icon
        self.summary = summary
        self.body = body
        self.actions = list(zip(actions[0::2], actions[1::2]))
        self.hints = hints
        self.urgency = int(hints.get("urgency", 1))
        self.timeout = timeout
        self.time = GLib.DateTime.new_now_local()


def notification_card(note: Notification, on_close=None, on_action=None, compact=False) -> Gtk.Box:
    card = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6), "fos-card", "fos-notification")
    if note.urgency >= 2:
        add_classes(card, "critical")
    head = Gtk.Box(spacing=8)
    head.pack_start(notification_icon(note.app_icon, note.hints), False, False, 0)
    head.pack_start(label(note.app_name, "fos-small", "fos-muted", ellipsize=True), True, True, 0)
    head.pack_start(label(note.time.format("%H:%M"), "fos-small", "fos-muted"), False, False, 0)
    if on_close is not None:
        close = button(icon_name="window-close-symbolic", size="icon-xs", tooltip="Dismiss")
        add_classes(close, "close")
        close.connect("clicked", lambda _b: on_close())
        head.pack_start(close, False, False, 0)
    card.pack_start(head, False, False, 0)
    if note.summary:
        summary = label("", "fos-text", "fos-strong", ellipsize=True)
        summary.set_markup(safe_markup(note.summary))
        card.pack_start(summary, False, False, 0)
    if note.body:
        body = label("", "fos-text", "fos-muted")
        body.set_markup(safe_markup(note.body))
        body.set_line_wrap(True)
        body.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        body.set_max_width_chars(44)
        if compact:
            body.set_lines(2)
            body.set_ellipsize(Pango.EllipsizeMode.END)
        card.pack_start(body, False, False, 0)
    buttons = [(key, text) for key, text in note.actions if key != "default"]
    if buttons and on_action is not None:
        row = Gtk.Box(spacing=6)
        for key, text in buttons:
            action = button(text, variant="outline", size="sm")
            action.connect("clicked", lambda _b, k=key: on_action(k))
            row.pack_start(action, False, False, 0)
        card.pack_start(row, False, False, 4)
    return card


class NotificationPopup(Gtk.Window):
    def __init__(self, server: "NotificationServer", note: Notification) -> None:
        super().__init__(type=Gtk.WindowType.POPUP)
        self.server = server
        self.note = note
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self.set_size_request(POPUP_WIDTH, -1)
        add_classes(self, "fos-root", "fos-popup")
        events = Gtk.EventBox()
        events.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        events.connect("button-press-event", self._on_press)
        events.add(
            notification_card(
                note,
                on_close=lambda: server.close(note.id, DISMISSED),
                on_action=lambda key: server.invoke(note.id, key),
            )
        )
        self.add(events)
        self.timer = 0

    def start_timer(self) -> None:
        timeout = self.note.timeout
        if timeout < 0:
            timeout = 0 if self.note.urgency >= 2 else DEFAULT_TIMEOUT_MS
        if timeout > 0:
            self.timer = GLib.timeout_add(timeout, self._expire)

    def stop_timer(self) -> None:
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0

    def _expire(self) -> bool:
        self.timer = 0
        self.server.close(self.note.id, EXPIRED)
        return False

    def _on_press(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button != 1:
            return False
        if any(key == "default" for key, _text in self.note.actions):
            self.server.invoke(self.note.id, "default")
        else:
            self.server.close(self.note.id, DISMISSED)
        return True


class NotificationList(Popup):
    """The bell menu: recent notifications and Clear all."""

    def __init__(self, server: "NotificationServer") -> None:
        super().__init__(width=POPUP_WIDTH + 32)
        self.server = server
        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)
        header = add_classes(Gtk.Box(spacing=8), "fos-card-header")
        header.pack_start(label("Notifications", "fos-title"), True, True, 0)
        clear_all = button("Clear all", variant="ghost", size="sm")
        clear_all.connect("clicked", lambda _b: self._clear())
        header.pack_end(clear_all, False, False, 0)
        frame.pack_start(header, False, False, 0)
        self.items = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_propagate_natural_height(True)
        scroller.set_max_content_height(420)
        scroller.add(self.items)
        body = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card-content")
        body.pack_start(scroller, True, True, 0)
        frame.pack_start(body, True, True, 0)

    def refresh(self) -> None:
        clear(self.items)
        if not self.server.history:
            empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            empty.set_margin_top(16)
            empty.set_margin_bottom(16)
            empty.pack_start(icon("preferences-system-notifications-symbolic", 24), False, False, 0)
            empty.pack_start(label("No notifications", "fos-text", "fos-muted", xalign=0.5), False, False, 0)
            self.items.pack_start(empty, False, False, 0)
        for note in reversed(self.server.history):
            self.items.pack_start(
                notification_card(note, on_close=lambda n=note: self._forget(n), compact=True), False, False, 0
            )
        self.items.show_all()
        self.relayout()

    def _forget(self, note: Notification) -> None:
        if note in self.server.history:
            self.server.history.remove(note)
        self.refresh()

    def _clear(self) -> None:
        self.server.history.clear()
        self.refresh()


class NotificationServer:
    def __init__(self, shell) -> None:
        self.shell = shell
        self.next_id = 1
        self.popups: dict[int, NotificationPopup] = {}
        self.history: list[Notification] = []
        self.unread = False
        self.connection: Gio.DBusConnection | None = None
        node = Gio.DBusNodeInfo.new_for_xml(INTERFACE_XML)
        self.interface = node.interfaces[0]
        self.owner_id = Gio.bus_own_name(
            Gio.BusType.SESSION,
            BUS_NAME,
            Gio.BusNameOwnerFlags.REPLACE | Gio.BusNameOwnerFlags.ALLOW_REPLACEMENT,
            self._on_bus_acquired,
            None,
            self._on_name_lost,
        )

    def _on_bus_acquired(self, connection: Gio.DBusConnection, _name: str) -> None:
        self.connection = connection
        connection.register_object(OBJECT_PATH, self.interface, self._on_call, None, None)

    def _on_name_lost(self, _connection, _name) -> None:
        print("fosos-shell: another notification daemon owns org.freedesktop.Notifications")

    def _on_call(self, _conn, _sender, _path, _iface, method, params, invocation) -> None:
        args = params.unpack()
        if method == "GetCapabilities":
            invocation.return_value(GLib.Variant("(as)", (["body", "body-markup", "actions", "persistence"],)))
        elif method == "GetServerInformation":
            invocation.return_value(GLib.Variant("(ssss)", ("FosOS Desktop", "FosOS", VERSION, "1.2")))
        elif method == "CloseNotification":
            self.close(args[0], CLOSED_BY_CALL)
            invocation.return_value(None)
        elif method == "Notify":
            nid = self.notify(*args)
            invocation.return_value(GLib.Variant("(u)", (nid,)))
        else:
            invocation.return_dbus_error("org.freedesktop.DBus.Error.UnknownMethod", method)

    def notify(self, app_name, replaces_id, app_icon, summary, body, actions, hints, timeout) -> int:
        if replaces_id and replaces_id in self.popups:
            nid = replaces_id
            self._remove_popup(nid)
        else:
            nid = replaces_id or self.next_id
            if not replaces_id:
                self.next_id += 1
        note = Notification(nid, app_name, app_icon, summary, body, actions, hints, timeout)
        if not hints.get("transient"):
            self.history = [n for n in self.history if n.id != nid]
            self.history.append(note)
            del self.history[:-HISTORY_LIMIT]
            self.unread = True
            if self.shell.panel is not None:
                self.shell.panel.set_unread(True)
        popup = NotificationPopup(self, note)
        self.popups[nid] = popup
        while len(self.popups) > MAX_POPUPS:
            oldest = next(iter(self.popups))
            self.close(oldest, EXPIRED)
        popup.show_all()
        popup.start_timer()
        self.stack()
        return nid

    def stack(self) -> None:
        panel = self.shell.panel
        if panel is None:
            return
        area = panel.area()
        bottom = panel.top() - 8
        for popup in reversed(list(self.popups.values())):
            _minimum, natural = popup.get_preferred_size()
            x = area.x + area.width - POPUP_WIDTH - 8
            y = bottom - natural.height
            popup.resize(POPUP_WIDTH, natural.height)
            popup.move(x, y)
            bottom = y - 8

    def _remove_popup(self, nid: int) -> bool:
        popup = self.popups.pop(nid, None)
        if popup is None:
            return False
        popup.stop_timer()
        popup.destroy()
        return True

    def close(self, nid: int, reason: int) -> None:
        if self._remove_popup(nid):
            self.stack()
        self._emit("NotificationClosed", GLib.Variant("(uu)", (nid, reason)))

    def invoke(self, nid: int, key: str) -> None:
        self._emit("ActionInvoked", GLib.Variant("(us)", (nid, key)))
        self.close(nid, DISMISSED)

    def _emit(self, signal: str, params: GLib.Variant) -> None:
        if self.connection is None:
            return
        try:
            self.connection.emit_signal(None, OBJECT_PATH, BUS_NAME, signal, params)
        except GLib.Error:
            pass

    def mark_read(self) -> None:
        self.unread = False
        if self.shell.panel is not None:
            self.shell.panel.set_unread(False)
