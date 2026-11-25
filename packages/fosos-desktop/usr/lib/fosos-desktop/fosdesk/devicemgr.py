"""FosOS Device Manager: Windows-style hardware tree from sysfs."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk, Pango

from .ui import add_classes, button, label, load_css
from .windowchrome import CardWindow

APP_ID = "org.fosos.DeviceManager"
SYS = Path("/sys")

# TreeStore columns
C_NAME = 0
C_KIND = 1  # "category" | "device"
C_ICON = 2
C_DETAIL = 3  # multiline properties text
C_SEARCH = 4


@dataclass
class DeviceNode:
    name: str
    category: str
    icon: str
    props: dict[str, str] = field(default_factory=dict)

    def detail_text(self) -> str:
        lines = [f"{key}: {value}" for key, value in self.props.items() if value]
        return "\n".join(lines) if lines else "No extra properties."


def _read(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default


def _pci_name(vendor: str, device: str) -> str | None:
    """Resolve PCI ids from pci.ids when available."""
    ids_path = Path("/usr/share/misc/pci.ids")
    if not ids_path.is_file():
        return None
    vendor = vendor.lower().removeprefix("0x")
    device = device.lower().removeprefix("0x")
    try:
        text = ids_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    vendor_name = ""
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        if not line.startswith("\t") and len(line) >= 6:
            if line[:4].lower() == vendor:
                vendor_name = line[4:].strip()
            elif vendor_name:
                break
            continue
        if vendor_name and line.startswith("\t") and not line.startswith("\t\t"):
            if line[1:5].lower() == device:
                return f"{line[5:].strip()} ({vendor_name})"
    return vendor_name or None


def _collect_processors() -> list[DeviceNode]:
    names: list[str] = []
    seen: set[str] = set()
    try:
        text = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    model = "Processor"
    cores = 0
    for line in text.splitlines():
        if line.startswith("model name"):
            model = line.split(":", 1)[1].strip()
            cores += 1
            if model not in seen:
                seen.add(model)
                names.append(model)
        elif line.startswith("processor"):
            if not names:
                cores += 1
    if not names:
        names = [f"CPU ({cores} logical processors)" if cores else "CPU"]
    nodes = []
    for name in names:
        nodes.append(
            DeviceNode(
                name=name,
                category="Processors",
                icon="cpu-symbolic",
                props={"Type": "Processor", "Logical processors": str(cores) if cores else ""},
            )
        )
    return nodes


def _collect_disks() -> list[DeviceNode]:
    block = SYS / "block"
    if not block.is_dir():
        return []
    nodes: list[DeviceNode] = []
    for entry in sorted(block.iterdir()):
        name = entry.name
        if name.startswith(("loop", "ram", "dm-", "zram", "sr")):
            continue
        model = _read(entry / "device" / "model") or _read(entry / "device" / "name") or name
        size_sectors = _read(entry / "size")
        size_text = ""
        if size_sectors.isdigit():
            gib = int(size_sectors) * 512 / (1024**3)
            size_text = f"{gib:.1f} GB" if gib >= 1 else f"{gib * 1024:.0f} MB"
        vendor = _read(entry / "device" / "vendor")
        nodes.append(
            DeviceNode(
                name=model.strip() or name,
                category="Disk drives",
                icon="drive-harddisk-symbolic",
                props={
                    "Device": f"/dev/{name}",
                    "Size": size_text,
                    "Vendor": vendor,
                    "Type": "Disk drive",
                },
            )
        )
    return nodes


def _collect_display() -> list[DeviceNode]:
    nodes: list[DeviceNode] = []
    drm = SYS / "class" / "drm"
    if not drm.is_dir():
        return nodes
    for entry in sorted(drm.iterdir()):
        if not entry.name.startswith("card") or "-" in entry.name:
            continue
        vendor = _read(entry / "device" / "vendor")
        device = _read(entry / "device" / "device")
        pretty = _pci_name(vendor, device) if vendor and device else None
        name = pretty or f"Display adapter ({entry.name})"
        driver = ""
        driver_link = entry / "device" / "driver"
        if driver_link.is_symlink():
            try:
                driver = driver_link.resolve().name
            except OSError:
                driver = ""
        nodes.append(
            DeviceNode(
                name=name,
                category="Display adapters",
                icon="video-display-symbolic",
                props={
                    "Adapter": entry.name,
                    "Vendor ID": vendor,
                    "Device ID": device,
                    "Driver": driver,
                    "Type": "Display adapter",
                },
            )
        )
    for entry in sorted(drm.iterdir()):
        if "-" not in entry.name:
            continue
        status = _read(entry / "status")
        if status != "connected":
            continue
        nodes.append(
            DeviceNode(
                name=entry.name.split("-", 1)[-1].replace("-", " "),
                category="Monitors",
                icon="video-display-symbolic",
                props={"Connector": entry.name, "Status": status, "Type": "Monitor"},
            )
        )
    return nodes


def _collect_network() -> list[DeviceNode]:
    net = SYS / "class" / "net"
    if not net.is_dir():
        return []
    nodes: list[DeviceNode] = []
    for entry in sorted(net.iterdir()):
        if entry.name == "lo":
            continue
        oper = _read(entry / "operstate")
        address = _read(entry / "address")
        typ = "Network adapter"
        icon = "network-wired-symbolic"
        if (entry / "wireless").is_dir() or Path(f"/sys/class/net/{entry.name}/phy80211").exists():
            typ = "Wi-Fi adapter"
            icon = "network-wireless-symbolic"
        elif entry.name.startswith("docker") or entry.name.startswith("br-"):
            typ = "Virtual network adapter"
        nodes.append(
            DeviceNode(
                name=entry.name,
                category="Network adapters",
                icon=icon,
                props={
                    "Interface": entry.name,
                    "MAC address": address,
                    "State": oper,
                    "Type": typ,
                },
            )
        )
    return nodes


def _collect_input() -> list[DeviceNode]:
    input_dir = SYS / "class" / "input"
    if not input_dir.is_dir():
        return []
    keyboards: list[DeviceNode] = []
    mice: list[DeviceNode] = []
    other: list[DeviceNode] = []
    seen: set[str] = set()
    for entry in sorted(input_dir.glob("event*")):
        name = _read(entry / "device" / "name")
        if not name or name in seen:
            continue
        seen.add(name)
        lower = name.lower()
        props = {"Name": name, "Sysfs": str(entry)}
        if any(token in lower for token in ("keyboard", "atkbd", "set 2 keyboard")):
            props["Type"] = "Keyboard"
            keyboards.append(DeviceNode(name, "Keyboards", "input-keyboard-symbolic", props))
        elif any(token in lower for token in ("mouse", "touchpad", "trackpoint", "trackball", "pointer")):
            props["Type"] = "Mouse / pointing device"
            mice.append(DeviceNode(name, "Mice and other pointing devices", "input-mouse-symbolic", props))
        elif any(token in lower for token in ("button", "lid", "power", "sleep", "video bus", "speaker", "hdmi", "mic", "headphone")):
            continue
        else:
            props["Type"] = "Input device"
            other.append(DeviceNode(name, "Human Interface Devices", "input-gaming-symbolic", props))
    return keyboards + mice + other


def _collect_sound() -> list[DeviceNode]:
    sound = SYS / "class" / "sound"
    if not sound.is_dir():
        return []
    nodes: list[DeviceNode] = []
    for entry in sorted(sound.glob("card*")):
        card_id = _read(entry / "id") or entry.name
        nodes.append(
            DeviceNode(
                name=card_id,
                category="Sound, video and game controllers",
                icon="audio-card-symbolic",
                props={"Card": entry.name, "Id": card_id, "Type": "Audio device"},
            )
        )
    return nodes


def _collect_batteries() -> list[DeviceNode]:
    power = SYS / "class" / "power_supply"
    if not power.is_dir():
        return []
    nodes: list[DeviceNode] = []
    for entry in sorted(power.iterdir()):
        typ = _read(entry / "type")
        if typ.upper() not in ("BATTERY", "MAINS", "USB"):
            # Still show named batteries / AC
            if not entry.name.upper().startswith(("BAT", "AC", "ADP")):
                continue
        name = _read(entry / "model_name") or entry.name
        status = _read(entry / "status") or _read(entry / "online")
        capacity = _read(entry / "capacity")
        props = {
            "Device": entry.name,
            "Type": typ or "Power",
            "Status": status,
            "Capacity": f"{capacity}%" if capacity else "",
        }
        icon = "battery-symbolic" if (typ or "").upper() == "BATTERY" or entry.name.upper().startswith("BAT") else "ac-adapter-symbolic"
        nodes.append(DeviceNode(name, "Batteries", icon, props))
    return nodes


def _collect_usb() -> list[DeviceNode]:
    usb = SYS / "bus" / "usb" / "devices"
    if not usb.is_dir():
        return []
    nodes: list[DeviceNode] = []
    for entry in sorted(usb.iterdir()):
        # Skip root hubs naming like usb1; keep real devices with product
        product = _read(entry / "product")
        manufacturer = _read(entry / "manufacturer")
        if not product and not manufacturer:
            continue
        if entry.name.isdigit() or entry.name.startswith("usb"):
            # usb1 = root hub; still useful
            if not product:
                product = f"USB hub ({entry.name})"
        name = product or manufacturer or entry.name
        nodes.append(
            DeviceNode(
                name=name,
                category="Universal Serial Bus devices",
                icon="drive-removable-media-symbolic",
                props={
                    "Product": product,
                    "Manufacturer": manufacturer,
                    "Device": entry.name,
                    "Vendor ID": _read(entry / "idVendor"),
                    "Product ID": _read(entry / "idProduct"),
                    "Type": "USB device",
                },
            )
        )
    return nodes


CATEGORY_ORDER = (
    "Processors",
    "Display adapters",
    "Monitors",
    "Disk drives",
    "Network adapters",
    "Keyboards",
    "Mice and other pointing devices",
    "Sound, video and game controllers",
    "Batteries",
    "Universal Serial Bus devices",
    "Human Interface Devices",
)

CATEGORY_ICONS = {
    "Processors": "cpu-symbolic",
    "Display adapters": "video-display-symbolic",
    "Monitors": "video-display-symbolic",
    "Disk drives": "drive-harddisk-symbolic",
    "Network adapters": "network-wired-symbolic",
    "Keyboards": "input-keyboard-symbolic",
    "Mice and other pointing devices": "input-mouse-symbolic",
    "Sound, video and game controllers": "audio-card-symbolic",
    "Batteries": "battery-symbolic",
    "Universal Serial Bus devices": "drive-removable-media-symbolic",
    "Human Interface Devices": "input-gaming-symbolic",
}


def enumerate_devices() -> list[DeviceNode]:
    devices: list[DeviceNode] = []
    for collector in (
        _collect_processors,
        _collect_display,
        _collect_disks,
        _collect_network,
        _collect_input,
        _collect_sound,
        _collect_batteries,
        _collect_usb,
    ):
        try:
            devices.extend(collector())
        except OSError:
            continue
    return devices


class DeviceManagerWindow(CardWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(
            app,
            title="Device Manager",
            icon_name="computer-symbolic",
            default_width=920,
            default_height=640,
        )
        self.set_icon_name("computer")
        add_classes(self, "fos-devmgr-shell")

        toolbar = add_classes(Gtk.Box(spacing=8), "fos-devmgr-toolbar")
        self.search = add_classes(Gtk.Entry(), "fos-input")
        self.search.set_placeholder_text("Filter devices")
        self.search.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "system-search-symbolic")
        self.search.connect("changed", lambda _e: self._apply_filter())
        toolbar.pack_start(self.search, True, True, 0)
        refresh = button("Refresh", variant="outline", size="sm")
        refresh.connect("clicked", lambda _b: self.reload())
        toolbar.pack_end(refresh, False, False, 0)
        self.body.pack_start(toolbar, False, False, 0)

        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        paned.set_wide_handle(True)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.store = Gtk.TreeStore(str, str, str, str, str)
        self.filter_model = self.store.filter_new()
        self.filter_model.set_visible_func(self._row_visible)
        self.view = add_classes(Gtk.TreeView(model=self.filter_model), "fos-devmgr-tree")
        self.view.set_headers_visible(False)
        self.view.set_search_column(C_SEARCH)
        self.view.set_enable_tree_lines(True)
        col = Gtk.TreeViewColumn("Device")
        pix = Gtk.CellRendererPixbuf()
        text = Gtk.CellRendererText()
        text.props.ellipsize = Pango.EllipsizeMode.END
        col.pack_start(pix, False)
        col.pack_start(text, True)
        col.add_attribute(pix, "icon-name", C_ICON)
        col.add_attribute(text, "text", C_NAME)
        self.view.append_column(col)
        self.view.connect("cursor-changed", self._on_select)
        scroll.add(self.view)
        paned.pack1(scroll, True, False)

        detail_box = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), "fos-devmgr-detail")
        detail_box.pack_start(label("Properties", "fos-label"), False, False, 0)
        detail_scroll = Gtk.ScrolledWindow()
        detail_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        detail_scroll.set_min_content_height(160)
        self.detail = Gtk.Label(label="Select a device to see its properties.", xalign=0.0, yalign=0.0)
        self.detail.set_line_wrap(True)
        self.detail.set_selectable(True)
        add_classes(self.detail, "fos-text", "fos-devmgr-props")
        detail_scroll.add(self.detail)
        detail_box.pack_start(detail_scroll, True, True, 0)
        paned.pack2(detail_box, False, False)
        paned.set_position(420)

        self.body.pack_start(paned, True, True, 0)
        self.status = add_classes(Gtk.Box(spacing=8), "fos-app-footer")
        self.status_text = label("", "fos-small", "fos-muted")
        self.status.pack_start(self.status_text, True, True, 0)
        self.body.pack_start(self.status, False, False, 0)

        self.reload()

    def reload(self) -> None:
        self.store.clear()
        devices = enumerate_devices()
        by_cat: dict[str, list[DeviceNode]] = {}
        for device in devices:
            by_cat.setdefault(device.category, []).append(device)

        total = 0
        for category in CATEGORY_ORDER:
            items = by_cat.pop(category, [])
            if not items:
                continue
            parent = self.store.append(
                None,
                [
                    f"{category} ({len(items)})",
                    "category",
                    CATEGORY_ICONS.get(category, "computer-symbolic"),
                    "",
                    category.lower(),
                ],
            )
            for device in items:
                self.store.append(
                    parent,
                    [
                        device.name,
                        "device",
                        device.icon,
                        device.detail_text(),
                        f"{category} {device.name} {device.detail_text()}".lower(),
                    ],
                )
                total += 1
        for category, items in sorted(by_cat.items()):
            parent = self.store.append(
                None,
                [
                    f"{category} ({len(items)})",
                    "category",
                    CATEGORY_ICONS.get(category, "computer-symbolic"),
                    "",
                    category.lower(),
                ],
            )
            for device in items:
                self.store.append(
                    parent,
                    [
                        device.name,
                        "device",
                        device.icon,
                        device.detail_text(),
                        f"{category} {device.name} {device.detail_text()}".lower(),
                    ],
                )
                total += 1

        self.view.expand_all()
        self.status_text.set_text(f"{total} devices")
        self.detail.set_text("Select a device to see its properties.")
        self._apply_filter()

    def _row_visible(self, model: Gtk.TreeModel, tree_iter, _data=None) -> bool:
        needle = self.search.get_text().strip().lower()
        if not needle:
            return True
        kind = model.get_value(tree_iter, C_KIND)
        search = model.get_value(tree_iter, C_SEARCH) or ""
        if needle in search:
            return True
        if kind == "category":
            child = model.iter_children(tree_iter)
            while child is not None:
                child_search = model.get_value(child, C_SEARCH) or ""
                if needle in child_search:
                    return True
                child = model.iter_next(child)
        return False

    def _apply_filter(self) -> None:
        self.filter_model.refilter()
        self.view.expand_all()

    def _on_select(self, _view=None) -> None:
        model, tree_iter = self.view.get_selection().get_selected()
        if tree_iter is None:
            return
        kind = model.get_value(tree_iter, C_KIND)
        if kind == "category":
            self.detail.set_text("Select a device under this category.")
            return
        detail = model.get_value(tree_iter, C_DETAIL) or ""
        name = model.get_value(tree_iter, C_NAME) or ""
        self.detail.set_text(f"{name}\n\n{detail}" if detail else name)


class DeviceManagerApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window: DeviceManagerWindow | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_prgname("fosos-devicemgr")
        GLib.set_application_name("Device Manager")
        load_css()

    def do_activate(self) -> None:
        if self.window is None:
            self.window = DeviceManagerWindow(self)
            self.window.show_all()
        self.window.present()


def main() -> int:
    return DeviceManagerApp().run(sys.argv)
