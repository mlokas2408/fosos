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


_NOTIF_DEFAULTS = {
    "dnd": "0",
    "toasts": "1",
    "timeout": str(DEFAULT_TIMEOUT_MS),
    "muted_apps": "",
}


def _notification_prefs() -> dict[str, str]:
    from .settings_pages import load_kv

    return load_kv("notifications", dict(_NOTIF_DEFAULTS))


def _pref_true(prefs: dict[str, str], key: str, default: bool) -> bool:
    from .settings_pages import truthy

    return truthy(prefs.get(key), default)


def muted_app_names(prefs: dict[str, str] | None = None) -> set[str]:
    prefs = prefs or _notification_prefs()
    raw = prefs.get("muted_apps", "") or ""
    return {part.strip() for part in raw.split("|") if part.strip()}


def is_app_muted(app_name: str, prefs: dict[str, str] | None = None) -> bool:
    name = (app_name or "").strip()
    if not name:
        return False
    muted = muted_app_names(prefs)
    return name in muted or name.lower() in {m.lower() for m in muted}


def set_app_muted(app_name: str, muted: bool) -> None:
    from .settings_pages import save_kv

    name = (app_name or "").strip()
    if not name:
        return
    prefs = _notification_prefs()
    current = muted_app_names(prefs)
    # Normalize case-insensitive membership.
    current = {m for m in current if m.lower() != name.lower()}
    if muted:
        current.add(name)
    prefs["muted_apps"] = "|".join(sorted(current, key=str.lower))
    save_kv("notifications", prefs)


def remember_notification_app(app_name: str) -> None:
    """Track apps that have notified so Settings can offer per-app mutes."""
    from .settings_pages import CONFIG

    name = (app_name or "").strip()
    if not name:
        return
    path = CONFIG / "notification-apps"
    try:
        CONFIG.mkdir(parents=True, exist_ok=True)
        existing: list[str] = []
        if path.is_file():
            existing = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        lower = {item.lower() for item in existing}
        if name.lower() not in lower:
            existing.append(name)
            path.write_text("\n".join(existing[-40:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def toast_timeout_ms(note_timeout: int, urgency: int) -> int:
    prefs = _notification_prefs()
    try:
        configured = max(1000, int(prefs.get("timeout", str(DEFAULT_TIMEOUT_MS))))
    except ValueError:
        configured = DEFAULT_TIMEOUT_MS
    if note_timeout < 0:
        return 0 if urgency >= 2 else configured
    if note_timeout == 0:
        return 0
    return note_timeout

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


def notification_card(
    note: Notification,
    on_close=None,
    on_action=None,
    on_click=None,
    on_mute=None,
    compact=False,
) -> Gtk.Widget:
    card = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6), "fos-card", "fos-notification")
    if note.urgency >= 2:
        add_classes(card, "critical")
    head = Gtk.Box(spacing=8)
    head.pack_start(notification_icon(note.app_icon, note.hints), False, False, 0)
    head.pack_start(label(note.app_name, "fos-small", "fos-muted", ellipsize=True), True, True, 0)
    head.pack_start(label(note.time.format("%H:%M"), "fos-small", "fos-muted"), False, False, 0)
    if on_mute is not None:
        muted = is_app_muted(note.app_name)
        mute_btn = button(
            "Unmute" if muted else "Mute",
            variant="ghost",
            size="sm",
            tooltip="Show toasts from this app again" if muted else "Hide toast popups from this app",
        )
        mute_btn.connect("clicked", lambda _b: on_mute(not muted))
        head.pack_start(mute_btn, False, False, 0)
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
    if on_click is None:
        return card
    events = Gtk.EventBox()
    events.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
    events.add(card)

    def pressed(_widget, event: Gdk.EventButton) -> bool:
        if event.button != 1:
            return False
        # Ignore clicks on action/close buttons inside the card.
        widget = Gtk.get_event_widget(event)
        while widget is not None and widget is not events:
            if isinstance(widget, Gtk.Button):
                return False
            widget = widget.get_parent()
        on_click()
        return True

    events.connect("button-press-event", pressed)
    return events


class NotificationPopup(Gtk.Window):
    def __init__(self, server: "NotificationServer", note: Notification) -> None:
        super().__init__(type=Gtk.WindowType.POPUP)
        self.server = server
        self.note = note
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self.set_size_request(POPUP_WIDTH, -1)
        add_classes(self, "fos-root", "fos-popup")
        events = Gtk.EventBox()
        events.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        events.connect("button-press-event", self._on_press)
        events.connect("enter-notify-event", self._on_enter)
        events.connect("leave-notify-event", self._on_leave)
        events.add(
            notification_card(
                note,
                on_close=lambda: server.close(note.id, DISMISSED),
                on_action=lambda key: server.invoke(note.id, key),
            )
        )
        self.add(events)
        self.timer = 0
        self._timeout_ms = 0
        self._paused = False
        self._stack_idle = 0
        self.connect("size-allocate", self._on_size_allocate)

    def start_timer(self) -> None:
        self._timeout_ms = toast_timeout_ms(self.note.timeout, self.note.urgency)
        self._arm_timer()

    def stop_timer(self) -> None:
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0

    def _arm_timer(self) -> None:
        self.stop_timer()
        if self._paused or self._timeout_ms <= 0:
            return
        self.timer = GLib.timeout_add(self._timeout_ms, self._expire)

    def _expire(self) -> bool:
        self.timer = 0
        self.server.close(self.note.id, EXPIRED)
        return False

    def _on_enter(self, _widget, event: Gdk.EventCrossing) -> bool:
        if event.detail == Gdk.NotifyType.INFERIOR:
            return False
        self._paused = True
        self.stop_timer()
        return False

    def _on_leave(self, _widget, event: Gdk.EventCrossing) -> bool:
        if event.detail == Gdk.NotifyType.INFERIOR:
            return False
        self._paused = False
        self._arm_timer()
        return False

    def _on_size_allocate(self, _widget, _allocation) -> None:
        if self._stack_idle:
            return
        self._stack_idle = GLib.idle_add(self._restack_idle)

    def _restack_idle(self) -> bool:
        self._stack_idle = 0
        self.server.stack()
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
    """Standalone notifications list (kept for compatibility)."""

    def __init__(self, server: "NotificationServer") -> None:
        super().__init__(width=POPUP_WIDTH + 32)
        self.server = server
        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)
        header = add_classes(Gtk.Box(spacing=8), "fos-card-header")
        header.pack_start(label("Notifications", "fos-title"), True, True, 0)
        clear_all = button("Clear all", variant="ghost", size="sm")
        clear_all.connect("clicked", lambda _b: server.clear_all())
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
        _fill_notification_items(self.items, self.server, on_activate=None, on_forget=self._forget)
        self.items.show_all()
        self.relayout()

    def _forget(self, note: Notification) -> None:
        if note in self.server.history:
            self.server.history.remove(note)
        self.refresh()


class NotificationCenter(Popup):
    """Clock / Win+N hub: calendar plus notification history."""

    def __init__(self, shell) -> None:
        super().__init__(width=POPUP_WIDTH + 40)
        self.shell = shell
        self.server = shell.notifications
        frame = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-card")
        self.add(frame)

        header = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2), "fos-card-header")
        self.day = label("", "fos-text", "fos-muted")
        self.date = label("", "fos-title")
        header.pack_start(self.day, False, False, 0)
        header.pack_start(self.date, False, False, 0)
        frame.pack_start(header, False, False, 0)

        body = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "fos-card-content")
        frame.pack_start(body, True, True, 0)
        self.calendar = add_classes(Gtk.Calendar(), "fos-calendar")
        body.pack_start(self.calendar, False, False, 0)

        notif_head = Gtk.Box(spacing=8)
        notif_head.pack_start(label("Notifications", "fos-label"), True, True, 0)
        clear_all = button("Clear all", variant="ghost", size="sm")
        clear_all.connect("clicked", lambda _b: self._clear())
        notif_head.pack_end(clear_all, False, False, 0)
        body.pack_start(notif_head, False, False, 0)

        self.items = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_propagate_natural_height(True)
        scroller.set_min_content_height(160)
        scroller.set_max_content_height(280)
        scroller.add(self.items)
        body.pack_start(scroller, True, True, 0)

    def refresh(self) -> None:
        now = GLib.DateTime.new_now_local()
        self.day.set_text(now.format("%A"))
        self.date.set_text(now.format("%-d %B %Y"))
        self.calendar.select_month(now.get_month() - 1, now.get_year())
        self.calendar.select_day(now.get_day_of_month())
        clear(self.items)
        _fill_notification_items(
            self.items,
            self.server,
            on_activate=self._activate,
            on_forget=self._forget,
            on_mute=self._mute_app,
        )
        self.items.show_all()
        self.relayout()

    def _forget(self, note: Notification) -> None:
        if note in self.server.history:
            self.server.history.remove(note)
        self.refresh()

    def _mute_app(self, note: Notification, muted: bool) -> None:
        set_app_muted(note.app_name, muted)
        self.refresh()

    def _clear(self) -> None:
        self.server.clear_all()
        self.refresh()

    def _activate(self, note: Notification) -> None:
        self.dismiss()
        self.server.activate_note(note)


def _fill_notification_items(
    container: Gtk.Box,
    server: "NotificationServer",
    on_activate,
    on_forget,
    on_mute=None,
) -> None:
    if not server.history:
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        empty.set_margin_top(12)
        empty.set_margin_bottom(12)
        empty.pack_start(icon("preferences-system-notifications-symbolic", 24), False, False, 0)
        empty.pack_start(label("No notifications", "fos-text", "fos-muted", xalign=0.5), False, False, 0)
        container.pack_start(empty, False, False, 0)
        return
    for note in reversed(server.history):
        container.pack_start(
            notification_card(
                note,
                on_close=(lambda n=note: on_forget(n)) if on_forget else None,
                on_action=(lambda key, n=note: server.invoke(n.id, key)),
                on_click=(lambda n=note: on_activate(n)) if on_activate else None,
                on_mute=(lambda muted, n=note: on_mute(n, muted)) if on_mute else None,
                compact=True,
            ),
            False,
            False,
            0,
        )


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
        remember_notification_app(note.app_name)
        if not hints.get("transient"):
            self.history = [n for n in self.history if n.id != nid]
            self.history.append(note)
            del self.history[:-HISTORY_LIMIT]
            self.unread = True
            if self.shell.panel is not None:
                self.shell.panel.set_unread(True)
        prefs = _notification_prefs()
        show_toast = (
            _pref_true(prefs, "toasts", True)
            and not _pref_true(prefs, "dnd", False)
            and not is_app_muted(note.app_name, prefs)
        )
        if show_toast:
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

    def clear_all(self) -> None:
        for nid in list(self.popups):
            self.close(nid, DISMISSED)
        self.history.clear()
        self.mark_read()
        center = self.shell.popups.get("clock")
        if center is not None and center.get_visible() and hasattr(center, "refresh"):
            center.refresh()
        notes = self.shell.popups.get("notifications")
        if notes is not None and notes.get_visible() and hasattr(notes, "refresh"):
            notes.refresh()

    def activate_note(self, note: Notification) -> None:
        """Click-to-focus: default action and/or raise a matching window."""
        if any(key == "default" for key, _text in note.actions):
            self.invoke(note.id, "default")
        else:
            self._remove_popup(note.id)
            self.stack()
        self._focus_app(note.app_name)
        if note in self.history:
            self.history.remove(note)
        self.mark_read()

    def _focus_app(self, app_name: str) -> None:
        if not app_name:
            return
        try:
            gi.require_version("Wnck", "3.0")
            from gi.repository import Wnck

            from .panel import x_timestamp
        except Exception:
            return
        needle = app_name.lower()
        screen = Wnck.Screen.get_default()
        screen.force_update()
        stamp = x_timestamp(self.shell.panel) if self.shell.panel is not None else int(GLib.get_monotonic_time() / 1000)
        for window in reversed(screen.get_windows_stacked()):
            name = (window.get_name() or "").lower()
            group = (window.get_class_group_name() or "").lower()
            if needle in name or needle in group or name in needle or group in needle:
                workspace = window.get_workspace()
                if workspace is not None:
                    workspace.activate(stamp)
                window.activate(stamp)
                return
