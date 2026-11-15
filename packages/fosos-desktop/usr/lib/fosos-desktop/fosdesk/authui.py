"""Two-column sign-in / unlock layout shared by the greeter and lock screen."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from .ui import BRAND, add_classes, brand_title, button, icon, label, mark
from .wallpaper import draw_wallpaper


@dataclass
class AuthWidgets:
    root: Gtk.Widget
    username: Gtk.Entry | None
    password: Gtk.Entry
    submit: Gtk.Button
    message: Gtk.Label
    session: Gtk.ComboBoxText | None
    brand_column: Gtk.Widget
    power_button: Gtk.MenuButton
    _power_list: Gtk.Box = field(repr=False)

    def set_power_actions(
        self,
        actions: list[tuple[str, str, Callable[[], None]]],
    ) -> None:
        """Populate the bottom-right power menu. Each action is (label, icon, callback)."""
        for child in list(self._power_list.get_children()):
            self._power_list.remove(child)
            child.destroy()
        for text, icon_name, callback in actions:
            item = button(text, icon_name=icon_name, variant="ghost", size="md")
            item.set_halign(Gtk.Align.FILL)
            item.set_hexpand(True)
            add_classes(item, "fos-login-power-item")
            item.connect("clicked", self._make_power_handler(callback))
            self._power_list.pack_start(item, False, False, 0)
        self._power_list.show_all()
        self.power_button.set_sensitive(bool(actions))
        self.power_button.set_visible(bool(actions))

    def _make_power_handler(self, callback: Callable[[], None]):
        def on_clicked(_button: Gtk.Button) -> None:
            popover = self.power_button.get_popover()
            if popover is not None:
                popover.popdown()
            callback()

        return on_clicked


def _field(name: str, entry: Gtk.Widget) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.pack_start(label(name, "fos-label"), False, False, 0)
    box.pack_start(entry, False, False, 0)
    return box


def _brand_column(live: bool) -> Gtk.Widget:
    overlay = Gtk.Overlay()
    add_classes(overlay, "fos-login-brand")
    canvas = Gtk.DrawingArea()
    canvas.connect("draw", _on_brand_draw)
    overlay.add(canvas)

    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    content.set_border_width(48)
    content.set_valign(Gtk.Align.FILL)
    content.set_halign(Gtk.Align.FILL)
    add_classes(content, "fos-login-brand-content")

    header = Gtk.Box(spacing=12)
    header.set_valign(Gtk.Align.START)
    header.pack_start(mark("md"), False, False, 0)
    live_text = BRAND["live_label"] if live else BRAND["name"]
    header.pack_start(
        label(live_text.upper(), "fos-small", "fos-login-kicker"),
        False,
        False,
        0,
    )
    content.pack_start(header, False, False, 0)

    hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    hero.set_valign(Gtk.Align.CENTER)
    hero.set_vexpand(True)
    hero.set_halign(Gtk.Align.START)
    title = brand_title(48)
    title.set_halign(Gtk.Align.START)
    hero.pack_start(title, False, False, 0)
    tagline = label(BRAND["tagline"].upper(), "fos-login-tagline", "fos-muted")
    tagline.set_margin_top(16)
    hero.pack_start(tagline, False, False, 0)
    motto = label(BRAND["motto"], "fos-text", "fos-muted")
    motto.set_margin_top(12)
    hero.pack_start(motto, False, False, 0)
    etymology = label(BRAND["etymology"], "fos-small", "fos-muted")
    etymology.set_margin_top(28)
    etymology.set_line_wrap(True)
    etymology.set_max_width_chars(42)
    hero.pack_start(etymology, False, False, 0)
    content.pack_start(hero, True, True, 0)

    footer = label(
        "Lightweight desktop for focus and delivery.",
        "fos-small",
        "fos-muted",
    )
    footer.set_valign(Gtk.Align.END)
    content.pack_start(footer, False, False, 0)

    overlay.add_overlay(content)
    return overlay


def _on_brand_draw(widget: Gtk.Widget, cr) -> bool:
    alloc = widget.get_allocation()
    area = Gdk.Rectangle()
    area.x = 0
    area.y = 0
    area.width = max(alloc.width, 1)
    area.height = max(alloc.height, 1)
    draw_wallpaper(cr, area)
    return False


def build_auth_ui(
    *,
    mode: str,
    username: str = "",
    live: bool = False,
    sessions: list[tuple[str, str]] | None = None,
    default_session: str | None = None,
    show_username: bool = True,
    username_editable: bool = True,
) -> AuthWidgets:
    """Build the mockup-style two-column auth layout.

    mode: "login" (Sign in) or "lock" (Unlock)
    sessions: optional list of (key, label) for the greeter session picker
    """
    root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    add_classes(root, "fos-root", "fos-login", f"fos-login-{mode}")

    brand = _brand_column(live)
    brand.set_hexpand(True)
    brand.set_size_request(420, -1)
    root.pack_start(brand, True, True, 0)

    form_shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    form_shell.set_size_request(440, -1)
    form_shell.set_hexpand(False)
    add_classes(form_shell, "fos-login-form")

    form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    form.set_valign(Gtk.Align.CENTER)
    form.set_vexpand(True)
    form.set_halign(Gtk.Align.CENTER)
    form.set_margin_start(48)
    form.set_margin_end(48)
    form.set_margin_top(48)
    form.set_margin_bottom(48)
    form.set_size_request(320, -1)
    add_classes(form, "fos-login-panel")

    mobile_brand = Gtk.Box(spacing=12)
    mobile_brand.set_margin_bottom(32)
    add_classes(mobile_brand, "fos-login-mobile-brand")
    mobile_brand.pack_start(mark("md"), False, False, 0)
    mobile_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    mobile_copy.pack_start(brand_title(18), False, False, 0)
    mobile_copy.pack_start(label(BRAND["tagline"].upper(), "fos-small", "fos-muted"), False, False, 0)
    mobile_brand.pack_start(mobile_copy, False, False, 0)
    form.pack_start(mobile_brand, False, False, 0)

    heading = "Sign in" if mode == "login" else "Unlock"
    form.pack_start(label(heading, "fos-login-heading"), False, False, 0)
    sub = label(
        "Continue to your FosOS session.",
        "fos-text",
        "fos-muted",
    )
    sub.set_margin_top(8)
    sub.set_margin_bottom(28)
    form.pack_start(sub, False, False, 0)

    username_entry: Gtk.Entry | None = None
    if show_username:
        username_entry = add_classes(Gtk.Entry(), "fos-input")
        username_entry.set_text(username)
        username_entry.set_placeholder_text("Username")
        username_entry.set_editable(username_editable)
        username_entry.set_sensitive(username_editable)
        if not username_editable:
            username_entry.set_can_focus(False)
        form.pack_start(_field("Username", username_entry), False, False, 0)

    password = add_classes(Gtk.Entry(), "fos-input")
    password.set_visibility(False)
    password.set_placeholder_text("Optional on live media" if live and mode == "login" else "Password")
    password.set_margin_top(16 if show_username else 0)
    form.pack_start(_field("Password", password), False, False, 0)

    session_combo: Gtk.ComboBoxText | None = None
    if sessions:
        session_combo = Gtk.ComboBoxText()
        add_classes(session_combo, "fos-login-session")
        active = 0
        for index, (key, text) in enumerate(sessions):
            session_combo.append(key, text)
            if default_session and key == default_session:
                active = index
        session_combo.set_active(active)
        session_combo.set_margin_top(16)
        form.pack_start(_field("Session", session_combo), False, False, 0)

    submit_label = "Sign in" if mode == "login" else "Unlock"
    submit = button(submit_label, variant="default", size="lg")
    submit.set_hexpand(True)
    submit.set_halign(Gtk.Align.FILL)
    submit.set_margin_top(24)
    add_classes(submit, "fos-login-submit")
    form.pack_start(submit, False, False, 0)

    message = label("", "fos-small", "fos-muted")
    message.set_margin_top(12)
    message.set_line_wrap(True)
    form.pack_start(message, False, False, 0)

    if live:
        foot = f"Live session · no account required · {BRAND['motto']}"
    else:
        foot = BRAND["motto"]
    footer = label(foot, "fos-small", "fos-muted")
    footer.set_margin_top(32)
    footer.set_line_wrap(True)
    form.pack_start(footer, False, False, 0)

    form_shell.pack_start(form, True, True, 0)
    root.pack_start(form_shell, False, False, 0)

    # Windows-style power control: bottom-right corner of the full screen.
    overlay = Gtk.Overlay()
    add_classes(overlay, "fos-login-overlay")
    overlay.add(root)

    power_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    power_list.set_border_width(6)
    add_classes(power_list, "fos-login-power-list")

    popover = Gtk.Popover()
    popover.set_position(Gtk.PositionType.TOP)
    popover.add(power_list)
    power_list.show_all()

    power_button = Gtk.MenuButton()
    power_button.set_relief(Gtk.ReliefStyle.NONE)
    power_button.set_can_focus(False)
    power_button.set_direction(Gtk.ArrowType.UP)
    power_button.set_popover(popover)
    power_button.set_tooltip_text("Power")
    power_button.add(icon("system-shutdown-symbolic", 20))
    add_classes(power_button, "fos-btn", "ghost", "fos-login-power")

    power_corner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    power_corner.set_halign(Gtk.Align.END)
    power_corner.set_valign(Gtk.Align.END)
    power_corner.set_margin_end(20)
    power_corner.set_margin_bottom(20)
    power_corner.pack_start(power_button, False, False, 0)
    add_classes(power_corner, "fos-login-power-corner")
    overlay.add_overlay(power_corner)
    power_corner.show_all()

    wide_state = {"value": None}

    def on_allocate(_widget, allocation: Gdk.Rectangle) -> None:
        wide = allocation.width >= 900
        if wide_state["value"] is wide:
            return
        wide_state["value"] = wide

        def apply() -> bool:
            brand.set_visible(wide)
            mobile_brand.set_visible(not wide)
            return False

        GLib.idle_add(apply)

    root.connect("size-allocate", on_allocate)
    brand.set_visible(True)
    mobile_brand.set_visible(False)

    return AuthWidgets(
        root=overlay,
        username=username_entry,
        password=password,
        submit=submit,
        message=message,
        session=session_combo,
        brand_column=brand,
        power_button=power_button,
        _power_list=power_list,
    )


def focus_first(widgets: AuthWidgets) -> None:
    if widgets.username is not None and widgets.username.get_sensitive() and widgets.username.get_editable():
        if not widgets.username.get_text():
            widgets.username.grab_focus()
            return
    widgets.password.grab_focus()
