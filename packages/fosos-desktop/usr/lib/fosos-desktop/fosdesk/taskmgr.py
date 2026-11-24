"""FosOS Task Manager: Windows-aligned Processes, Performance, Startup, Details."""

from __future__ import annotations

import configparser
import os
import pwd
import shutil
import signal
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cairo
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango, Wnck

from .ui import add_classes, button, fos_confirm, label, load_css, set_class
from .windowchrome import CardWindow

APP_ID = "org.fosos.TaskManager"
PROC = Path("/proc")
REFRESH_MS = 1000
HISTORY_LEN = 60
USER_AUTOSTART = Path.home() / ".config" / "autostart"
SYSTEM_AUTOSTART = Path("/etc/xdg/autostart")

# Already started by fosos-session before the XDG autostart pass.
SKIP_AUTOSTART_BASENAMES = {
    "xdg-user-dirs-update",
    "gnome-keyring-daemon",
    "lxpolkit",
    "polkit-gnome-authentication-agent-1",
    "polkit-mate-authentication-agent-1",
    "xfce-polkit",
    "polkit-ukui-authentication-agent-1",
    "xsettingsd",
    "xcape",
    "xss-lock",
    "fosos-lock",
    "fosos-shell",
    "openbox",
}

# Graph accents (Windows Task Manager–like on dark chrome).
COLOR_CPU = (0.00, 0.70, 0.58)  # teal
COLOR_MEM = (0.56, 0.44, 0.78)  # lilac
COLOR_DISK = (0.78, 0.70, 0.35)  # gold
COLOR_NET = (0.83, 0.36, 0.29)  # coral

# Processes TreeStore
P_NAME = 0
P_PID = 1
P_STATUS = 2
P_CPU = 3
P_CPU_TEXT = 4
P_MEM = 5
P_MEM_TEXT = 6
P_DISK = 7
P_DISK_TEXT = 8
P_NET_TEXT = 9
P_SEARCH = 10
P_KIND = 11  # "section" | "app" | "proc"

# Details ListStore
D_NAME = 0
D_PID = 1
D_STATUS = 2
D_USER = 3
D_CPU = 4
D_CPU_TEXT = 5
D_MEM = 6
D_MEM_TEXT = 7
D_SEARCH = 8

# Startup ListStore
S_NAME = 0
S_STATUS = 1
S_IMPACT = 2
S_ENABLED = 3
S_ID = 4
S_DESC = 5


@dataclass
class ProcSample:
    pid: int
    ppid: int
    name: str
    user: str
    status: str
    cpu_jiffies: int
    mem_bytes: int
    io_bytes: int
    cmdline: str = ""


@dataclass
class StartupApp:
    id: str
    name: str
    exec_line: str
    exec_basename: str
    enabled: bool
    impact: str
    description: str
    path: Path
    system: bool


@dataclass
class PerfSnapshot:
    cpu_pct: float = 0.0
    mem_used: int = 0
    mem_total: int = 0
    mem_available: int = 0
    mem_cached: int = 0
    mem_commit: int = 0
    disk_read_bps: float = 0.0
    disk_write_bps: float = 0.0
    disk_util: float = 0.0
    disk_name: str = "Disk"
    net_recv_bps: float = 0.0
    net_sent_bps: float = 0.0
    net_name: str = "Ethernet"
    processes: int = 0
    threads: int = 0
    uptime_s: float = 0.0
    cpu_model: str = ""
    cpu_cores: int = 1
    cpu_freq_mhz: float = 0.0


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _uid_name(uid: int, cache: dict[int, str]) -> str:
    if uid in cache:
        return cache[uid]
    try:
        name = pwd.getpwuid(uid).pw_name
    except KeyError:
        name = str(uid)
    cache[uid] = name
    return name


def format_mem(nbytes: float) -> str:
    n = float(nbytes)
    if n < 1024:
        return f"{n:.0f} B"
    if n < 1024**2:
        return f"{n / 1024:.0f} KB"
    if n < 1024**3:
        return f"{n / 1024**2:.1f} MB"
    return f"{n / 1024**3:.2f} GB"


def format_cpu(pct: float) -> str:
    if pct < 0.05:
        return "0.0"
    if pct < 10:
        return f"{pct:.1f}"
    return f"{pct:.0f}"


def format_rate(bps: float) -> str:
    if bps < 1024:
        return f"{bps:.0f} B/s"
    if bps < 1024**2:
        return f"{bps / 1024:.1f} KB/s"
    if bps < 1024**3:
        return f"{bps / 1024**2:.1f} MB/s"
    return f"{bps / 1024**3:.2f} GB/s"


def format_uptime(seconds: float) -> str:
    s = int(max(seconds, 0))
    days, rem = divmod(s, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    if days:
        return f"{days}:{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{hours:02d}:{mins:02d}:{secs:02d}"


def _total_cpu_jiffies() -> int:
    text = _read_text(PROC / "stat")
    if not text:
        return 0
    for line in text.splitlines():
        if line.startswith("cpu "):
            parts = line.split()
            try:
                return sum(int(x) for x in parts[1:])
            except ValueError:
                return 0
    return 0


def _process_name(pid: int, status_name: str, cmdline: str) -> str:
    if cmdline:
        argv0 = cmdline.split("\0", 1)[0].strip()
        if argv0:
            return os.path.basename(argv0) or argv0
    return status_name or f"[{pid}]"


def _read_io_bytes(pid: int) -> int:
    text = _read_text(PROC / str(pid) / "io")
    if not text:
        return 0
    read_b = write_b = 0
    for line in text.splitlines():
        if line.startswith("read_bytes:"):
            try:
                read_b = int(line.split()[1])
            except (IndexError, ValueError):
                pass
        elif line.startswith("write_bytes:"):
            try:
                write_b = int(line.split()[1])
            except (IndexError, ValueError):
                pass
    return read_b + write_b


def sample_processes() -> tuple[list[ProcSample], int]:
    total = _total_cpu_jiffies()
    uid_cache: dict[int, str] = {}
    rows: list[ProcSample] = []
    try:
        entries = list(PROC.iterdir())
    except OSError:
        return [], total

    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        status = _read_text(entry / "status")
        if status is None:
            continue
        proc_name = ""
        uid = 0
        rss_kb = 0
        state = "R"
        threads = 1
        for line in status.splitlines():
            if line.startswith("Name:"):
                proc_name = line.split(":", 1)[1].strip()
            elif line.startswith("State:"):
                state = line.split(":", 1)[1].strip()[:1] or "R"
            elif line.startswith("Uid:"):
                try:
                    uid = int(line.split()[1])
                except (IndexError, ValueError):
                    uid = 0
            elif line.startswith("VmRSS:"):
                try:
                    rss_kb = int(line.split()[1])
                except (IndexError, ValueError):
                    rss_kb = 0
            elif line.startswith("Threads:"):
                try:
                    threads = int(line.split()[1])
                except (IndexError, ValueError):
                    threads = 1
        stat = _read_text(entry / "stat")
        if stat is None:
            continue
        try:
            after = stat.rsplit(")", 1)[1].split()
            ppid = int(after[1])
            cpu_jiffies = int(after[11]) + int(after[12])
        except (IndexError, ValueError):
            continue
        cmdline = _read_text(entry / "cmdline") or ""
        # Kernel threads have empty cmdline.
        is_kernel = not cmdline
        status_label = {
            "R": "Running",
            "S": "Running",
            "D": "Running",
            "T": "Suspended",
            "t": "Suspended",
            "Z": "Suspended",
            "I": "Running",
        }.get(state, "Running")
        rows.append(
            ProcSample(
                pid=pid,
                ppid=ppid,
                name=_process_name(pid, proc_name, cmdline),
                user=_uid_name(uid, uid_cache),
                status=status_label if not is_kernel else "Running",
                cpu_jiffies=cpu_jiffies,
                mem_bytes=0 if is_kernel else rss_kb * 1024,
                io_bytes=_read_io_bytes(pid),
                cmdline=cmdline.replace("\0", " ").strip(),
            )
        )
        # stash thread count on object dynamically for perf totals
        setattr(rows[-1], "threads", threads)
        setattr(rows[-1], "is_kernel", is_kernel)
    return rows, total


def windowed_pids() -> set[int]:
    try:
        screen = Wnck.Screen.get_default()
        if screen is None:
            return set()
        screen.force_update()
        pids: set[int] = set()
        for window in screen.get_windows() or []:
            if window.is_skip_tasklist():
                continue
            if window.get_window_type() not in (
                Wnck.WindowType.NORMAL,
                Wnck.WindowType.DIALOG,
            ):
                continue
            pid = window.get_pid()
            if pid > 0:
                pids.add(pid)
        return pids
    except Exception:
        return set()


def _meminfo_dict() -> dict[str, int]:
    text = _read_text(PROC / "meminfo") or ""
    out: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].endswith(":"):
            try:
                out[parts[0][:-1]] = int(parts[1]) * 1024
            except ValueError:
                pass
    return out


def _root_block() -> str:
    text = _read_text(PROC / "mounts") or ""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "/":
            dev = parts[0]
            name = os.path.basename(dev)
            # nvme0n1p2 → nvme0n1 ; sda1 → sda
            if "nvme" in name and "p" in name:
                return name.rsplit("p", 1)[0]
            while name and name[-1].isdigit():
                name = name[:-1]
            return name or os.path.basename(dev)
    return "disk"


def _disk_counters(block: str) -> tuple[int, int, int]:
    """Return (read_bytes, write_bytes, io_ticks_ms)."""
    text = _read_text(PROC / "diskstats") or ""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 14:
            continue
        if parts[2] != block:
            continue
        try:
            sectors_read = int(parts[5])
            sectors_written = int(parts[9])
            io_ticks = int(parts[12])
        except ValueError:
            return 0, 0, 0
        return sectors_read * 512, sectors_written * 512, io_ticks
    return 0, 0, 0


def _net_counters() -> tuple[str, int, int]:
    """Best non-loopback iface → (name, rx_bytes, tx_bytes)."""
    text = _read_text(PROC / "net" / "dev") or ""
    best = ("Ethernet", 0, 0)
    best_score = -1
    for line in text.splitlines()[2:]:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        iface = name.strip()
        if iface == "lo":
            continue
        parts = rest.split()
        if len(parts) < 9:
            continue
        try:
            rx, tx = int(parts[0]), int(parts[8])
        except ValueError:
            continue
        score = rx + tx
        # Prefer interfaces that have carried traffic; else first physical-looking.
        if score > best_score:
            best_score = score
            label_name = "Wi-Fi" if iface.startswith(("wl", "wlan")) else "Ethernet"
            if iface.startswith("ww"):
                label_name = "Cellular"
            best = (f"{label_name} ({iface})", rx, tx)
    return best


def _cpu_model() -> str:
    text = _read_text(PROC / "cpuinfo") or ""
    for line in text.splitlines():
        if line.startswith("model name"):
            return line.split(":", 1)[1].strip()
    return platform_machine()


def platform_machine() -> str:
    return os.uname().machine


def _cpu_freq_mhz() -> float:
    for path in (
        Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"),
        Path("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_cur_freq"),
    ):
        text = _read_text(path)
        if text:
            try:
                return int(text.strip()) / 1000.0
            except ValueError:
                pass
    text = _read_text(PROC / "cpuinfo") or ""
    for line in text.splitlines():
        if line.startswith("cpu MHz"):
            try:
                return float(line.split(":", 1)[1].strip())
            except ValueError:
                pass
    return 0.0


def _uptime() -> float:
    text = _read_text(PROC / "uptime")
    if not text:
        return 0.0
    try:
        return float(text.split()[0])
    except ValueError:
        return 0.0


# --- Startup (XDG autostart) -------------------------------------------------


def _parse_desktop(path: Path) -> configparser.RawConfigParser | None:
    parser = configparser.RawConfigParser(interpolation=None)
    parser.optionxform = str  # desktop keys are case-sensitive
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error:
        return None
    if not parser.has_section("Desktop Entry"):
        return None
    return parser


def _desktop_shown_on_fosos(entry: configparser.RawConfigParser) -> bool:
    section = entry["Desktop Entry"]
    only = section.get("OnlyShowIn", "").strip()
    not_in = section.get("NotShowIn", "").strip()
    if only:
        allowed = {x.strip() for x in only.split(";") if x.strip()}
        if not allowed.intersection({"FosOS", "GNOME", "XFCE", "Unity", "MATE"}):
            return False
    if not_in:
        blocked = {x.strip() for x in not_in.split(";") if x.strip()}
        if "FosOS" in blocked:
            return False
    return True


def _exec_basename(exec_line: str) -> str:
    # Strip field codes and take first token basename.
    cleaned = exec_line.replace("%f", "").replace("%F", "").replace("%u", "")
    cleaned = cleaned.replace("%U", "").replace("%i", "").replace("%c", "")
    cleaned = cleaned.replace("%k", "").strip()
    if not cleaned:
        return ""
    # Handle `env FOO=bar cmd` lightly: last non-assignment-looking token path.
    parts = cleaned.split()
    cmd = parts[0]
    if cmd == "env" and len(parts) > 1:
        for part in parts[1:]:
            if "=" not in part:
                cmd = part
                break
    return os.path.basename(cmd)


def _is_enabled(entry: configparser.RawConfigParser) -> bool:
    section = entry["Desktop Entry"]
    if section.get("Hidden", "false").lower() in ("true", "1"):
        return False
    flag = section.get("X-GNOME-Autostart-enabled", "true")
    return flag.lower() not in ("false", "0")


def _impact_for(basename: str) -> str:
    heavy = {"firefox", "firefox-esr", "thunderbird", "steam", "discord", "slack", "teams", "zoom"}
    medium = {"nm-applet", "blueman-applet", "fosos-welcome", "dropbox", "onedrive"}
    base = basename.lower()
    if base in heavy or any(base.startswith(h) for h in heavy):
        return "High"
    if base in medium:
        return "Medium"
    return "Low"


def list_startup_apps() -> list[StartupApp]:
    """Merge system + user XDG autostart; user files override by filename."""
    files: dict[str, tuple[Path, bool]] = {}
    if SYSTEM_AUTOSTART.is_dir():
        for path in SYSTEM_AUTOSTART.glob("*.desktop"):
            files[path.name] = (path, True)
    if USER_AUTOSTART.is_dir():
        for path in USER_AUTOSTART.glob("*.desktop"):
            files[path.name] = (path, False)

    apps: list[StartupApp] = []
    for name, (path, system) in sorted(files.items(), key=lambda item: item[0].lower()):
        entry = _parse_desktop(path)
        if entry is None or not _desktop_shown_on_fosos(entry):
            continue
        section = entry["Desktop Entry"]
        exec_line = section.get("Exec", "").strip()
        if not exec_line:
            continue
        display = section.get("Name", name)
        apps.append(
            StartupApp(
                id=name,
                name=display,
                exec_line=exec_line,
                exec_basename=_exec_basename(exec_line),
                enabled=_is_enabled(entry),
                impact=_impact_for(_exec_basename(exec_line)),
                description=section.get("Comment", "") or exec_line,
                path=path,
                system=system,
            )
        )
    apps.sort(key=lambda a: a.name.lower())
    return apps


def set_startup_enabled(desktop_id: str, enabled: bool) -> bool:
    """Write a user autostart override enabling or disabling the entry."""
    source = USER_AUTOSTART / desktop_id
    if not source.is_file():
        source = SYSTEM_AUTOSTART / desktop_id
    if not source.is_file():
        return False
    entry = _parse_desktop(source)
    if entry is None:
        return False
    entry["Desktop Entry"]["X-GNOME-Autostart-enabled"] = "true" if enabled else "false"
    entry["Desktop Entry"]["Hidden"] = "false" if enabled else "true"
    USER_AUTOSTART.mkdir(parents=True, exist_ok=True)
    dest = USER_AUTOSTART / desktop_id
    try:
        with dest.open("w", encoding="utf-8") as handle:
            entry.write(handle, space_around_delimiters=False)
    except OSError:
        return False
    return True


def run_session_autostart() -> None:
    """Launch enabled XDG autostart apps (called from fosos-session)."""
    for app in list_startup_apps():
        if not app.enabled:
            continue
        if app.exec_basename in SKIP_AUTOSTART_BASENAMES:
            continue
        if shutil.which(app.exec_basename) is None and not Path(app.exec_line.split()[0]).is_file():
            # Still try — Exec may be an absolute path already handled above.
            first = app.exec_line.split()[0]
            if not Path(first).is_file() and shutil.which(first) is None:
                continue
        launched = False
        try:
            info = Gio.DesktopAppInfo.new_from_filename(str(app.path))
            if info is not None:
                display = Gdk.Display.get_default()
                ctx = display.get_app_launch_context() if display is not None else None
                launched = bool(info.launch([], ctx))
        except GLib.Error:
            launched = False
        if launched:
            continue
        try:
            subprocess.Popen(
                app.exec_line,
                shell=True,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass


# --- Performance sampling ----------------------------------------------------


class PerfCollector:
    def __init__(self) -> None:
        self._prev_cpu = _total_cpu_jiffies()
        self._prev_time = time.monotonic()
        self._block = _root_block()
        self._prev_disk = _disk_counters(self._block)
        self._prev_net = _net_counters()
        self._cpu_model = _cpu_model()
        self._cpu_cores = os.cpu_count() or 1
        self.history_cpu: deque[float] = deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self.history_mem: deque[float] = deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self.history_disk: deque[float] = deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self.history_net: deque[float] = deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self.last = PerfSnapshot(cpu_model=self._cpu_model, cpu_cores=self._cpu_cores, disk_name=self._block)

    def tick(self, processes: list[ProcSample] | None = None) -> PerfSnapshot:
        now = time.monotonic()
        dt = max(now - self._prev_time, 0.001)
        cpu_now = _total_cpu_jiffies()
        # Aggregate cpu line sums all cores; normalize to 0–100 overall.
        delta_jiffies = max(cpu_now - self._prev_cpu, 0)
        # /proc/stat jiffies advance ~ cores * Hz per second.
        try:
            hz = os.sysconf("SC_CLK_TCK")
        except (ValueError, OSError):
            hz = 100
        cpu_pct = min(100.0, 100.0 * delta_jiffies / (dt * hz * self._cpu_cores))

        mem = _meminfo_dict()
        mem_total = mem.get("MemTotal", 0)
        mem_avail = mem.get("MemAvailable", 0)
        mem_used = max(mem_total - mem_avail, 0)
        mem_cached = mem.get("Cached", 0) + mem.get("Buffers", 0)
        mem_commit = mem.get("Committed_AS", 0)
        mem_pct = (100.0 * mem_used / mem_total) if mem_total else 0.0

        disk_now = _disk_counters(self._block)
        d_read = max(disk_now[0] - self._prev_disk[0], 0) / dt
        d_write = max(disk_now[1] - self._prev_disk[1], 0) / dt
        d_ticks = max(disk_now[2] - self._prev_disk[2], 0)
        disk_util = min(100.0, 100.0 * d_ticks / (dt * 1000.0))

        net_name, rx, tx = _net_counters()
        prev_name, prev_rx, prev_tx = self._prev_net
        if net_name == prev_name:
            n_recv = max(rx - prev_rx, 0) / dt
            n_sent = max(tx - prev_tx, 0) / dt
        else:
            n_recv = n_sent = 0.0
        net_pct = min(100.0, 100.0 * (n_recv + n_sent) / (100 * 1024 * 1024))  # scale vs 100 MB/s

        procs = processes if processes is not None else []
        threads = sum(getattr(p, "threads", 1) for p in procs) if procs else 0
        if not procs:
            # lightweight count
            try:
                threads = 0
                count = 0
                for entry in PROC.iterdir():
                    if entry.name.isdigit():
                        count += 1
                procs_count = count
            except OSError:
                procs_count = 0
        else:
            procs_count = len(procs)

        snap = PerfSnapshot(
            cpu_pct=cpu_pct,
            mem_used=mem_used,
            mem_total=mem_total,
            mem_available=mem_avail,
            mem_cached=mem_cached,
            mem_commit=mem_commit,
            disk_read_bps=d_read,
            disk_write_bps=d_write,
            disk_util=disk_util,
            disk_name=f"Disk 0 ({self._block})",
            net_recv_bps=n_recv,
            net_sent_bps=n_sent,
            net_name=net_name,
            processes=procs_count,
            threads=threads or procs_count,
            uptime_s=_uptime(),
            cpu_model=self._cpu_model,
            cpu_cores=self._cpu_cores,
            cpu_freq_mhz=_cpu_freq_mhz(),
        )
        self.history_cpu.append(cpu_pct)
        self.history_mem.append(mem_pct)
        self.history_disk.append(disk_util)
        self.history_net.append(net_pct)
        self._prev_cpu = cpu_now
        self._prev_time = now
        self._prev_disk = disk_now
        self._prev_net = (net_name, rx, tx)
        self.last = snap
        return snap


# --- Widgets -----------------------------------------------------------------


class HistoryGraph(Gtk.DrawingArea):
    def __init__(self, color: tuple[float, float, float], history: deque[float]) -> None:
        super().__init__()
        self.color = color
        self.history = history
        self.set_size_request(200, 120)
        self.set_hexpand(True)
        self.set_vexpand(True)
        add_classes(self, "fos-taskmgr-graph")
        self.connect("draw", self._on_draw)

    def _on_draw(self, _widget, cr: cairo.Context) -> bool:
        alloc = self.get_allocation()
        w, h = alloc.width, alloc.height
        cr.set_source_rgb(0.09, 0.09, 0.09)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        # grid
        cr.set_source_rgba(1, 1, 1, 0.06)
        cr.set_line_width(1)
        for i in range(1, 4):
            y = h * i / 4
            cr.move_to(0, y)
            cr.line_to(w, y)
            cr.stroke()

        values = list(self.history)
        if len(values) < 2 or w < 2 or h < 2:
            return False
        r, g, b = self.color
        cr.set_source_rgba(r, g, b, 0.25)
        cr.move_to(0, h)
        for i, value in enumerate(values):
            x = i * (w - 1) / (len(values) - 1)
            y = h - (max(0.0, min(value, 100.0)) / 100.0) * (h - 2) - 1
            cr.line_to(x, y)
        cr.line_to(w, h)
        cr.close_path()
        cr.fill()

        cr.set_source_rgb(r, g, b)
        cr.set_line_width(1.5)
        for i, value in enumerate(values):
            x = i * (w - 1) / (len(values) - 1)
            y = h - (max(0.0, min(value, 100.0)) / 100.0) * (h - 2) - 1
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()
        return False


def _kill_pid(pid: int) -> str | None:
    """SIGTERM a process; return error message or None."""
    try:
        os.kill(pid, signal.SIGTERM)
        return None
    except ProcessLookupError:
        return None
    except PermissionError:
        try:
            Gio.Subprocess.new(
                ["pkexec", "kill", "-TERM", str(pid)],
                Gio.SubprocessFlags.NONE,
            )
            return None
        except GLib.Error as exc:
            return str(exc.message)


class TaskManagerWindow(CardWindow):
    def __init__(self, app: "TaskManagerApp") -> None:
        super().__init__(
            app,
            title="Task Manager",
            icon_name="utilities-system-monitor-symbolic",
            default_width=920,
            default_height=640,
        )
        self.set_icon_name("utilities-system-monitor")
        self.app = app
        self.perf = PerfCollector()
        self._prev_cpu: dict[int, int] = {}
        self._prev_io: dict[int, int] = {}
        self._prev_total = 0
        self._prev_mono = time.monotonic()
        self._selected_pid: int | None = None
        self._selected_pids: list[int] = []
        self._filter_text = ""
        self._page = "processes"
        self._perf_page = "cpu"

        # Tab strip (Windows-style top categories)
        tabs = add_classes(Gtk.Box(spacing=4), "fos-app-toolbar", "fos-taskmgr-tabs")
        self._tab_buttons: dict[str, Gtk.Button] = {}
        for key, title in (
            ("processes", "Processes"),
            ("performance", "Performance"),
            ("startup", "Startup apps"),
            ("details", "Details"),
        ):
            btn = button(title, variant="ghost", size="sm")
            btn.connect("clicked", lambda _b, k=key: self._show_page(k))
            tabs.pack_start(btn, False, False, 0)
            self._tab_buttons[key] = btn
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        tabs.pack_start(spacer, True, True, 0)
        self.end_btn = button("End task", variant="destructive", size="sm")
        self.end_btn.set_sensitive(False)
        self.end_btn.connect("clicked", lambda _b: self.end_task())
        tabs.pack_start(self.end_btn, False, False, 0)
        self.body.pack_start(tabs, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        self.body.pack_start(self.stack, True, True, 0)

        self._build_processes()
        self._build_performance()
        self._build_startup()
        self._build_details()

        self.footer = add_classes(Gtk.Box(spacing=16), "fos-app-footer")
        self.status_cpu = label("CPU: —", "fos-small", "fos-muted")
        self.status_mem = label("Memory: —", "fos-small", "fos-muted")
        self.status_disk = label("Disk: —", "fos-small", "fos-muted")
        self.status_net = label("Network: —", "fos-small", "fos-muted")
        for widget in (self.status_cpu, self.status_mem, self.status_disk, self.status_net):
            self.footer.pack_start(widget, False, False, 0)
        self.body.pack_start(self.footer, False, False, 0)

        accel = Gtk.AccelGroup()
        self.add_accel_group(accel)
        key, mods = Gtk.accelerator_parse("<Control>f")
        self.search.add_accelerator("grab-focus", accel, key, mods, Gtk.AccelFlags.VISIBLE)
        key, mods = Gtk.accelerator_parse("F5")
        accel.connect(key, mods, Gtk.AccelFlags.VISIBLE, lambda *_a: self.refresh() or True)
        key, mods = Gtk.accelerator_parse("Delete")
        accel.connect(key, mods, Gtk.AccelFlags.VISIBLE, lambda *_a: self.end_task() or True)

        self._show_page("processes")
        self.refresh()
        self._timer = GLib.timeout_add(REFRESH_MS, self._on_timer)
        self.connect("destroy", self._on_destroy)

    # --- page chrome ---------------------------------------------------------

    def _show_page(self, key: str) -> None:
        self._page = key
        self.stack.set_visible_child_name(key)
        for name, btn in self._tab_buttons.items():
            set_class(btn, "secondary", name == key)
            set_class(btn, "ghost", name != key)
        self.end_btn.set_visible(key in ("processes", "details"))
        if key == "startup":
            self._reload_startup()
        self._sync_end_sensitive()

    def _sync_end_sensitive(self) -> None:
        if self._page == "processes":
            self.end_btn.set_sensitive(bool(self._selected_pids))
        elif self._page == "details":
            self.end_btn.set_sensitive(self._selected_pid is not None)
        else:
            self.end_btn.set_sensitive(False)

    def _on_destroy(self, *_args) -> None:
        if getattr(self, "_timer", 0):
            GLib.source_remove(self._timer)
            self._timer = 0

    def _on_timer(self) -> bool:
        self.refresh()
        return True

    def refresh(self) -> None:
        samples, total = sample_processes()
        now = time.monotonic()
        dt = max(now - self._prev_mono, 0.001)
        prev_cpu = self._prev_cpu
        prev_io = self._prev_io
        prev_total = self._prev_total
        delta_total = max(total - prev_total, 1) if prev_total else 0

        cpu_map: dict[int, float] = {}
        disk_map: dict[int, float] = {}
        next_cpu: dict[int, int] = {}
        next_io: dict[int, int] = {}
        for sample in samples:
            next_cpu[sample.pid] = sample.cpu_jiffies
            next_io[sample.pid] = sample.io_bytes
            if prev_total and sample.pid in prev_cpu and delta_total:
                cpu_map[sample.pid] = 100.0 * max(sample.cpu_jiffies - prev_cpu[sample.pid], 0) / delta_total
            else:
                cpu_map[sample.pid] = 0.0
            if sample.pid in prev_io:
                disk_map[sample.pid] = max(sample.io_bytes - prev_io[sample.pid], 0) / dt
            else:
                disk_map[sample.pid] = 0.0

        self._prev_cpu = next_cpu
        self._prev_io = next_io
        self._prev_total = total
        self._prev_mono = now

        snap = self.perf.tick(samples)
        self._update_footer(snap)
        self._refresh_processes(samples, cpu_map, disk_map)
        self._refresh_details(samples, cpu_map)
        self._refresh_performance(snap)

    def _update_footer(self, snap: PerfSnapshot) -> None:
        mem_pct = (100.0 * snap.mem_used / snap.mem_total) if snap.mem_total else 0.0
        self.status_cpu.set_text(f"CPU: {format_cpu(snap.cpu_pct)}%")
        self.status_mem.set_text(f"Memory: {format_cpu(mem_pct)}%")
        self.status_disk.set_text(f"Disk: {format_cpu(snap.disk_util)}%")
        net_total = snap.net_recv_bps + snap.net_sent_bps
        self.status_net.set_text(f"Network: {format_rate(net_total)}")

    # --- Processes -----------------------------------------------------------

    def _build_processes(self) -> None:
        page = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-taskmgr-table-page")
        bar = add_classes(Gtk.Box(spacing=8), "fos-taskmgr-toolbar")
        self.search = add_classes(Gtk.Entry(), "fos-input")
        self.search.set_placeholder_text("Search processes")
        self.search.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "system-search-symbolic")
        self.search.set_width_chars(28)
        self.search.connect("changed", self._on_search)
        bar.pack_end(self.search, False, False, 0)
        tip = label("Apps and background processes", "fos-small", "fos-muted")
        bar.pack_start(tip, False, False, 0)
        page.pack_start(bar, False, False, 0)

        # Memory/disk use float so RSS can exceed 32-bit Gtk.TreeStore ints.
        self.proc_store = Gtk.TreeStore(str, int, str, float, str, float, str, float, str, str, str, str)
        self.proc_filter = self.proc_store.filter_new()
        self.proc_filter.set_visible_func(self._proc_visible)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.proc_tree = Gtk.TreeView(model=self.proc_filter)
        self.proc_tree.set_headers_clickable(True)
        self.proc_tree.set_enable_search(False)
        self.proc_tree.set_show_expanders(True)
        self.proc_tree.set_level_indentation(8)
        add_classes(self.proc_tree, "fos-taskmgr-tree")
        self.proc_tree.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        self.proc_tree.get_selection().connect("changed", self._on_proc_selection)
        self.proc_tree.connect("button-press-event", self._on_proc_press)
        self._add_column(self.proc_tree, "Name", P_NAME, expand=True, min_width=200)
        self._add_column(self.proc_tree, "Status", P_STATUS, min_width=88)
        self._add_column(self.proc_tree, "CPU", P_CPU_TEXT, sort_id=P_CPU, xalign=1.0, min_width=56)
        self._add_column(self.proc_tree, "Memory", P_MEM_TEXT, sort_id=P_MEM, xalign=1.0, min_width=80)
        self._add_column(self.proc_tree, "Disk", P_DISK_TEXT, sort_id=P_DISK, xalign=1.0, min_width=80)
        self._add_column(self.proc_tree, "Network", P_NET_TEXT, xalign=1.0, min_width=72)
        scroller.add(self.proc_tree)
        page.pack_start(scroller, True, True, 0)
        self.stack.add_named(page, "processes")

    def _add_column(
        self,
        tree: Gtk.TreeView,
        title: str,
        col_id: int,
        *,
        sort_id: int | None = None,
        expand: bool = False,
        xalign: float = 0.0,
        min_width: int = 0,
    ) -> None:
        renderer = Gtk.CellRendererText()
        renderer.set_property("xalign", xalign)
        renderer.set_property("ellipsize", Pango.EllipsizeMode.END if expand else Pango.EllipsizeMode.NONE)
        column = Gtk.TreeViewColumn(title, renderer, text=col_id)
        if sort_id is not None:
            column.set_sort_column_id(sort_id)
        column.set_resizable(True)
        column.set_min_width(min_width)
        if expand:
            column.set_expand(True)
        tree.append_column(column)

    def _on_search(self, entry: Gtk.Entry) -> None:
        self._filter_text = entry.get_text().strip().lower()
        self.proc_filter.refilter()
        if hasattr(self, "details_filter"):
            self.details_filter.refilter()

    def _proc_visible(self, model: Gtk.TreeModel, it: Gtk.TreeIter, _data=None) -> bool:
        kind = model.get_value(it, P_KIND)
        if kind == "section":
            # Show section if any child visible.
            child = model.iter_children(it)
            while child is not None:
                if self._proc_visible(model, child):
                    return True
                child = model.iter_next(child)
            return not self._filter_text
        if not self._filter_text:
            return True
        return self._filter_text in (model.get_value(it, P_SEARCH) or "")

    def _on_proc_selection(self, selection: Gtk.TreeSelection) -> None:
        model, it = selection.get_selected()
        self._selected_pids = []
        self._selected_pid = None
        if it is None:
            self._sync_end_sensitive()
            return
        kind = model.get_value(it, P_KIND)
        if kind == "section":
            self._sync_end_sensitive()
            return
        if kind == "app":
            child = model.iter_children(it)
            while child is not None:
                self._selected_pids.append(int(model.get_value(child, P_PID)))
                child = model.iter_next(child)
            pid = int(model.get_value(it, P_PID))
            if pid > 0:
                self._selected_pids.insert(0, pid)
        else:
            pid = int(model.get_value(it, P_PID))
            self._selected_pids = [pid]
            self._selected_pid = pid
        self._sync_end_sensitive()

    def _on_proc_press(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button != 3:
            return False
        path_info = self.proc_tree.get_path_at_pos(int(event.x), int(event.y))
        if path_info is None:
            return False
        path, _c, _x, _y = path_info
        self.proc_tree.get_selection().select_path(path)
        menu = Gtk.Menu()
        add_classes(menu, "context-menu")
        end = Gtk.MenuItem(label="End task")
        end.connect("activate", lambda _i: self.end_task())
        menu.append(end)
        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def _refresh_processes(
        self,
        samples: list[ProcSample],
        cpu_map: dict[int, float],
        disk_map: dict[int, float],
    ) -> None:
        apps_pids = windowed_pids()
        # Expand apps set: include children of windowed pids one level.
        by_ppid: dict[int, list[ProcSample]] = {}
        for sample in samples:
            by_ppid.setdefault(sample.ppid, []).append(sample)

        app_roots: list[ProcSample] = []
        background: list[ProcSample] = []
        claimed: set[int] = set()

        for sample in samples:
            if getattr(sample, "is_kernel", False):
                continue
            if sample.pid in apps_pids:
                app_roots.append(sample)
                claimed.add(sample.pid)

        # Claim direct children of apps as part of the app group.
        app_children: dict[int, list[ProcSample]] = {s.pid: [] for s in app_roots}
        for root in app_roots:
            for child in by_ppid.get(root.pid, []):
                if child.pid in claimed or getattr(child, "is_kernel", False):
                    continue
                app_children[root.pid].append(child)
                claimed.add(child.pid)

        for sample in samples:
            if sample.pid in claimed or getattr(sample, "is_kernel", False):
                continue
            background.append(sample)

        selected = list(self._selected_pids)

        self.proc_store.clear()
        apps_iter = self.proc_store.append(
            None,
            self._proc_row(f"Apps ({len(app_roots)})", 0, "", 0, 0, 0, "", "section"),
        )
        for root in sorted(app_roots, key=lambda s: (-cpu_map.get(s.pid, 0), s.name.lower())):
            children = app_children.get(root.pid, [])
            cpu = cpu_map.get(root.pid, 0.0) + sum(cpu_map.get(c.pid, 0.0) for c in children)
            mem = root.mem_bytes + sum(c.mem_bytes for c in children)
            disk = disk_map.get(root.pid, 0.0) + sum(disk_map.get(c.pid, 0.0) for c in children)
            parent = self.proc_store.append(
                apps_iter,
                self._proc_row(root.name, root.pid, root.status, cpu, mem, disk, f"{root.name} {root.pid}", "app"),
            )
            for child in sorted(children, key=lambda s: s.name.lower()):
                self.proc_store.append(
                    parent,
                    self._proc_row(
                        child.name,
                        child.pid,
                        child.status,
                        cpu_map.get(child.pid, 0.0),
                        child.mem_bytes,
                        disk_map.get(child.pid, 0.0),
                        f"{child.name} {child.pid} {child.user}",
                        "proc",
                    ),
                )

        bg_iter = self.proc_store.append(
            None,
            self._proc_row(f"Background processes ({len(background)})", 0, "", 0, 0, 0, "", "section"),
        )
        for sample in sorted(background, key=lambda s: (-cpu_map.get(s.pid, 0), s.name.lower())):
            self.proc_store.append(
                bg_iter,
                self._proc_row(
                    sample.name,
                    sample.pid,
                    sample.status,
                    cpu_map.get(sample.pid, 0.0),
                    sample.mem_bytes,
                    disk_map.get(sample.pid, 0.0),
                    f"{sample.name} {sample.pid} {sample.user}",
                    "proc",
                ),
            )

        # Expand sections by default; restore named expansions.
        self.proc_tree.expand_row(self.proc_store.get_path(apps_iter), False)
        self.proc_tree.expand_row(self.proc_store.get_path(bg_iter), False)
        if selected:
            self._reselect_proc_pids(selected)

    def _proc_row(
        self,
        name: str,
        pid: int,
        status: str,
        cpu: float,
        mem: float,
        disk: float,
        search: str,
        kind: str,
    ) -> list:
        return [
            name,
            pid,
            status,
            float(cpu),
            "" if kind == "section" else format_cpu(cpu),
            float(mem),
            "" if kind == "section" else format_mem(mem),
            float(disk),
            "" if kind == "section" else format_rate(disk),
            "" if kind == "section" else "—",
            search.lower(),
            kind,
        ]

    def _reselect_proc_pids(self, pids: list[int]) -> None:
        want = set(pids)
        found = False

        def walk(model, _path, it) -> bool:
            nonlocal found
            if model.get_value(it, P_KIND) == "section":
                return False
            if int(model.get_value(it, P_PID)) in want:
                self.proc_tree.get_selection().select_iter(it)
                found = True
                return True
            return False

        self.proc_filter.foreach(walk)
        if not found:
            self._selected_pids = []
            self._sync_end_sensitive()

    # --- Performance ---------------------------------------------------------

    def _build_performance(self) -> None:
        page = Gtk.Box(spacing=0)
        side = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4), "fos-sidebar", "fos-taskmgr-perf-nav")
        side.set_size_request(160, -1)
        side.set_border_width(8)
        self._perf_nav: dict[str, Gtk.Button] = {}
        self._perf_nav_stats: dict[str, Gtk.Label] = {}
        for key, title in (
            ("cpu", "CPU"),
            ("memory", "Memory"),
            ("disk", "Disk 0"),
            ("network", "Ethernet"),
        ):
            btn = button(variant="ghost", size="sm")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_halign(Gtk.Align.START)
            title_l = label(title, "fos-text")
            stat_l = label("—", "fos-small", "fos-muted")
            box.pack_start(title_l, False, False, 0)
            box.pack_start(stat_l, False, False, 0)
            btn.add(box)
            btn.connect("clicked", lambda _b, k=key: self._show_perf(k))
            side.pack_start(btn, False, False, 0)
            self._perf_nav[key] = btn
            self._perf_nav_stats[key] = stat_l
            if key == "network":
                self._perf_net_title = title_l
            if key == "disk":
                self._perf_disk_title = title_l
        page.pack_start(side, False, False, 0)

        self.perf_stack = Gtk.Stack()
        self.perf_stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.perf_stack.set_hexpand(True)
        self.perf_stack.set_vexpand(True)

        self.graph_cpu = HistoryGraph(COLOR_CPU, self.perf.history_cpu)
        self.graph_mem = HistoryGraph(COLOR_MEM, self.perf.history_mem)
        self.graph_disk = HistoryGraph(COLOR_DISK, self.perf.history_disk)
        self.graph_net = HistoryGraph(COLOR_NET, self.perf.history_net)

        self.perf_labels: dict[str, dict[str, Gtk.Label]] = {}
        self.perf_stack.add_named(self._perf_panel("CPU", self.graph_cpu, "cpu", COLOR_CPU), "cpu")
        self.perf_stack.add_named(self._perf_panel("Memory", self.graph_mem, "memory", COLOR_MEM), "memory")
        self.perf_stack.add_named(self._perf_panel("Disk 0", self.graph_disk, "disk", COLOR_DISK), "disk")
        self.perf_stack.add_named(self._perf_panel("Ethernet", self.graph_net, "network", COLOR_NET), "network")
        page.pack_start(self.perf_stack, True, True, 0)
        self.stack.add_named(page, "performance")
        self._show_perf("cpu")

    def _perf_panel(
        self,
        title: str,
        graph: HistoryGraph,
        key: str,
        color: tuple[float, float, float],
    ) -> Gtk.Widget:
        box = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), "fos-taskmgr-perf-panel")
        box.set_border_width(12)
        head = label(title, "fos-title")
        if key == "cpu":
            self.perf_cpu_title = head
        elif key == "memory":
            self.perf_mem_title = head
        elif key == "disk":
            self.perf_disk_heading = head
        else:
            self.perf_net_heading = head
        box.pack_start(head, False, False, 0)
        util = label("% Utilization", "fos-small", "fos-muted")
        box.pack_start(util, False, False, 0)
        graph.set_size_request(-1, 220)
        box.pack_start(graph, True, True, 0)

        grid = Gtk.Grid()
        grid.set_column_spacing(24)
        grid.set_row_spacing(8)
        grid.set_column_homogeneous(True)
        labels: dict[str, Gtk.Label] = {}
        fields = {
            "cpu": ("Utilization", "Speed", "Processes", "Threads", "Uptime", "Cores"),
            "memory": ("In use", "Available", "Committed", "Cached", "In use %", "Total"),
            "disk": ("Active time", "Read speed", "Write speed", "Capacity", "", ""),
            "network": ("Send", "Receive", "Adapter", "", "", ""),
        }[key]
        for index, name in enumerate(fields):
            if not name:
                continue
            row, col = divmod(index, 3)
            cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            cell.pack_start(label(name, "fos-small", "fos-muted"), False, False, 0)
            value = label("—", "fos-text")
            cell.pack_start(value, False, False, 0)
            grid.attach(cell, col, row, 1, 1)
            labels[name] = value
        self.perf_labels[key] = labels
        box.pack_start(grid, False, False, 0)
        return box

    def _show_perf(self, key: str) -> None:
        self._perf_page = key
        self.perf_stack.set_visible_child_name(key)
        for name, btn in self._perf_nav.items():
            set_class(btn, "secondary", name == key)
            set_class(btn, "ghost", name != key)

    def _refresh_performance(self, snap: PerfSnapshot) -> None:
        mem_pct = (100.0 * snap.mem_used / snap.mem_total) if snap.mem_total else 0.0
        self._perf_nav_stats["cpu"].set_text(f"{format_cpu(snap.cpu_pct)}%")
        self._perf_nav_stats["memory"].set_text(f"{format_cpu(mem_pct)}%")
        self._perf_nav_stats["disk"].set_text(f"{format_cpu(snap.disk_util)}%")
        self._perf_nav_stats["network"].set_text(format_rate(snap.net_recv_bps + snap.net_sent_bps))
        self._perf_disk_title.set_text("Disk 0")
        short_net = snap.net_name.split("(", 1)[0].strip() or "Ethernet"
        self._perf_net_title.set_text(short_net)

        self.perf_cpu_title.set_text(snap.cpu_model or "CPU")
        self.perf_disk_heading.set_text(snap.disk_name)
        self.perf_net_heading.set_text(snap.net_name)

        cpu = self.perf_labels["cpu"]
        cpu["Utilization"].set_text(f"{format_cpu(snap.cpu_pct)}%")
        cpu["Speed"].set_text(f"{snap.cpu_freq_mhz / 1000:.2f} GHz" if snap.cpu_freq_mhz else "—")
        cpu["Processes"].set_text(str(snap.processes))
        cpu["Threads"].set_text(str(snap.threads))
        cpu["Uptime"].set_text(format_uptime(snap.uptime_s))
        cpu["Cores"].set_text(str(snap.cpu_cores))

        mem = self.perf_labels["memory"]
        mem["In use"].set_text(format_mem(snap.mem_used))
        mem["Available"].set_text(format_mem(snap.mem_available))
        mem["Committed"].set_text(format_mem(snap.mem_commit))
        mem["Cached"].set_text(format_mem(snap.mem_cached))
        mem["In use %"].set_text(f"{format_cpu(mem_pct)}%")
        mem["Total"].set_text(format_mem(snap.mem_total))

        disk = self.perf_labels["disk"]
        disk["Active time"].set_text(f"{format_cpu(snap.disk_util)}%")
        disk["Read speed"].set_text(format_rate(snap.disk_read_bps))
        disk["Write speed"].set_text(format_rate(snap.disk_write_bps))
        try:
            usage = shutil.disk_usage("/")
            disk["Capacity"].set_text(f"{format_mem(usage.used)} / {format_mem(usage.total)}")
        except OSError:
            disk["Capacity"].set_text("—")

        net = self.perf_labels["network"]
        net["Send"].set_text(format_rate(snap.net_sent_bps))
        net["Receive"].set_text(format_rate(snap.net_recv_bps))
        net["Adapter"].set_text(snap.net_name)

        for graph in (self.graph_cpu, self.graph_mem, self.graph_disk, self.graph_net):
            graph.queue_draw()

    # --- Startup -------------------------------------------------------------

    def _build_startup(self) -> None:
        page = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-taskmgr-table-page")
        bar = add_classes(Gtk.Box(spacing=8), "fos-taskmgr-toolbar")
        self.startup_enable_btn = button("Enable", variant="default", size="sm")
        self.startup_enable_btn.set_sensitive(False)
        self.startup_enable_btn.connect("clicked", lambda _b: self._toggle_startup(True))
        bar.pack_start(self.startup_enable_btn, False, False, 0)
        self.startup_disable_btn = button("Disable", variant="ghost", size="sm")
        self.startup_disable_btn.set_sensitive(False)
        self.startup_disable_btn.connect("clicked", lambda _b: self._toggle_startup(False))
        bar.pack_start(self.startup_disable_btn, False, False, 0)
        tip = label("Apps that run when you sign in. Changes apply at next sign-in.", "fos-small", "fos-muted")
        tip.set_line_wrap(True)
        bar.pack_start(tip, True, True, 0)
        page.pack_start(bar, False, False, 0)

        self.startup_store = Gtk.ListStore(str, str, str, bool, str, str)
        scroller = Gtk.ScrolledWindow()
        self.startup_tree = Gtk.TreeView(model=self.startup_store)
        add_classes(self.startup_tree, "fos-taskmgr-tree")
        self.startup_tree.get_selection().connect("changed", self._on_startup_selection)
        self._add_column(self.startup_tree, "Name", S_NAME, expand=True, min_width=180)
        self._add_column(self.startup_tree, "Status", S_STATUS, min_width=88)
        self._add_column(self.startup_tree, "Startup impact", S_IMPACT, min_width=110)
        scroller.add(self.startup_tree)
        page.pack_start(scroller, True, True, 0)
        self.stack.add_named(page, "startup")

    def _reload_startup(self) -> None:
        selected = None
        model, it = self.startup_tree.get_selection().get_selected()
        if it is not None:
            selected = model.get_value(it, S_ID)
        self.startup_store.clear()
        for app in list_startup_apps():
            self.startup_store.append(
                [
                    app.name,
                    "Enabled" if app.enabled else "Disabled",
                    app.impact,
                    app.enabled,
                    app.id,
                    app.description,
                ]
            )
        if selected:
            it = self.startup_store.get_iter_first()
            while it is not None:
                if self.startup_store.get_value(it, S_ID) == selected:
                    self.startup_tree.get_selection().select_iter(it)
                    break
                it = self.startup_store.iter_next(it)

    def _on_startup_selection(self, selection: Gtk.TreeSelection) -> None:
        model, it = selection.get_selected()
        if it is None:
            self.startup_enable_btn.set_sensitive(False)
            self.startup_disable_btn.set_sensitive(False)
            return
        enabled = bool(model.get_value(it, S_ENABLED))
        self.startup_enable_btn.set_sensitive(not enabled)
        self.startup_disable_btn.set_sensitive(enabled)

    def _toggle_startup(self, enable: bool) -> None:
        model, it = self.startup_tree.get_selection().get_selected()
        if it is None:
            return
        desktop_id = model.get_value(it, S_ID)
        name = model.get_value(it, S_NAME)
        if not set_startup_enabled(desktop_id, enable):
            return
        self._reload_startup()
        state = "enabled" if enable else "disabled"
        self.status_cpu.set_text(f"{name} {state} at next sign-in")

    # --- Details -------------------------------------------------------------

    def _build_details(self) -> None:
        page = add_classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fos-taskmgr-table-page")
        self.details_store = Gtk.ListStore(str, int, str, str, float, str, float, str, str)
        self.details_filter = self.details_store.filter_new()
        self.details_filter.set_visible_func(self._details_visible)
        self.details_sort = Gtk.TreeModelSort(model=self.details_filter)
        self.details_sort.set_sort_column_id(D_CPU, Gtk.SortType.DESCENDING)
        scroller = Gtk.ScrolledWindow()
        self.details_tree = Gtk.TreeView(model=self.details_sort)
        add_classes(self.details_tree, "fos-taskmgr-tree")
        self.details_tree.get_selection().connect("changed", self._on_details_selection)
        self.details_tree.connect("button-press-event", self._on_details_press)
        self._add_column(self.details_tree, "Name", D_NAME, expand=True, min_width=160)
        self._add_column(self.details_tree, "PID", D_PID, xalign=1.0, min_width=64)
        self._add_column(self.details_tree, "Status", D_STATUS, min_width=88)
        self._add_column(self.details_tree, "User name", D_USER, min_width=88)
        self._add_column(self.details_tree, "CPU", D_CPU_TEXT, sort_id=D_CPU, xalign=1.0, min_width=56)
        self._add_column(self.details_tree, "Memory", D_MEM_TEXT, sort_id=D_MEM, xalign=1.0, min_width=80)
        scroller.add(self.details_tree)
        page.pack_start(scroller, True, True, 0)
        self.stack.add_named(page, "details")

    def _details_visible(self, model: Gtk.TreeModel, it: Gtk.TreeIter, _data=None) -> bool:
        if not self._filter_text:
            return True
        return self._filter_text in (model.get_value(it, D_SEARCH) or "")

    def _on_details_selection(self, selection: Gtk.TreeSelection) -> None:
        model, it = selection.get_selected()
        if it is None:
            self._selected_pid = None
        else:
            self._selected_pid = int(model.get_value(it, D_PID))
            self._selected_pids = [self._selected_pid]
        self._sync_end_sensitive()

    def _on_details_press(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button != 3:
            return False
        path_info = self.details_tree.get_path_at_pos(int(event.x), int(event.y))
        if path_info is None:
            return False
        path, _c, _x, _y = path_info
        self.details_tree.get_selection().select_path(path)
        menu = Gtk.Menu()
        add_classes(menu, "context-menu")
        end = Gtk.MenuItem(label="End task")
        end.connect("activate", lambda _i: self.end_task())
        menu.append(end)
        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def _refresh_details(self, samples: list[ProcSample], cpu_map: dict[int, float]) -> None:
        selected = self._selected_pid
        self.details_store.clear()
        for sample in samples:
            if getattr(sample, "is_kernel", False):
                continue
            cpu = cpu_map.get(sample.pid, 0.0)
            self.details_store.append(
                [
                    sample.name,
                    sample.pid,
                    sample.status,
                    sample.user,
                    cpu,
                    format_cpu(cpu),
                    float(sample.mem_bytes),
                    format_mem(sample.mem_bytes),
                    f"{sample.name} {sample.pid} {sample.user}".lower(),
                ]
            )
        if selected is not None:
            it = self.details_sort.get_iter_first()
            while it is not None:
                if int(self.details_sort.get_value(it, D_PID)) == selected:
                    self.details_tree.get_selection().select_iter(it)
                    return
                it = self.details_sort.iter_next(it)
            self._selected_pid = None
            self._sync_end_sensitive()

    # --- End task ------------------------------------------------------------

    def end_task(self) -> None:
        pids = list(dict.fromkeys(self._selected_pids or ([self._selected_pid] if self._selected_pid else [])))
        pids = [p for p in pids if p and p > 0]
        if not pids:
            return
        names = []
        for pid in pids[:3]:
            names.append(str(pid))
        # Prefer display names from current page.
        tree = self.proc_tree if self._page == "processes" else self.details_tree
        model, it = tree.get_selection().get_selected()
        title_name = "selected processes"
        if it is not None:
            title_name = model.get_value(it, 0)

        if any(pid in (os.getpid(), os.getppid()) for pid in pids):
            if not fos_confirm(
                self,
                "End Task Manager?",
                "This will close Task Manager itself.",
                ok="End task",
                destructive=True,
            ):
                return
        elif not fos_confirm(
            self,
            f"End “{title_name}”?",
            "Unsaved work in that app may be lost.",
            ok="End task",
            destructive=True,
        ):
            return

        for pid in pids:
            _kill_pid(pid)

        def force_kill() -> bool:
            for pid in pids:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    continue
                except PermissionError:
                    continue
                try:
                    os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
            self.refresh()
            return False

        GLib.timeout_add(800, force_kill)
        GLib.timeout_add(200, lambda: self.refresh() or False)


class TaskManagerApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window: TaskManagerWindow | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_prgname("fosos-taskmgr")
        GLib.set_application_name("Task Manager")
        load_css()

    def do_activate(self) -> None:
        if self.window is None:
            self.window = TaskManagerWindow(self)
            self.window.show_all()
        self.window.present()


def main() -> int:
    return TaskManagerApp().run(sys.argv)
