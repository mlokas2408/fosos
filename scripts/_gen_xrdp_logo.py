#!/usr/bin/env python3
"""Generate FosOS xrdp login bitmaps (Dawn Aperture mark + Sign in banner)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "packages/fosos-desktop/usr/share/fosos-desktop/xrdp"
MARK_PNG = ROOT / "packages/fosos-theme/usr/share/fosos/logo/fosos-dawn-aperture-256.png"

BG = (10, 10, 10)  # #0a0a0a
CARD = (23, 23, 23)  # #171717
FG = (250, 250, 250)  # #fafafa
MUTED = (161, 161, 161)  # #a1a1a1


def write_bmp(path: Path, width: int, height: int, pixels: list[list[tuple[int, int, int]]]) -> None:
    row_raw = width * 3
    pad = (4 - (row_raw % 4)) % 4
    data = bytearray()
    for y in range(height - 1, -1, -1):
        for x in range(width):
            r, g, b = pixels[y][x]
            data += bytes((b, g, r))
        data += b"\x00" * pad
    header = bytearray()
    header += b"BM"
    header += struct.pack("<IHHI", 54 + len(data), 0, 0, 54)
    header += struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(data), 2835, 2835, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + data)


def blank(width: int, height: int, color: tuple[int, int, int]) -> list[list[tuple[int, int, int]]]:
    return [[color for _ in range(width)] for _ in range(height)]


def blend(dst, x: int, y: int, color, alpha: float = 1.0) -> None:
    if not (0 <= y < len(dst) and 0 <= x < len(dst[0])):
        return
    if alpha >= 1.0:
        dst[y][x] = color
        return
    r0, g0, b0 = dst[y][x]
    r1, g1, b1 = color
    dst[y][x] = (
        int(r0 + (r1 - r0) * alpha),
        int(g0 + (g1 - g0) * alpha),
        int(b0 + (b1 - b0) * alpha),
    )


def load_png_rgba(path: Path) -> tuple[int, int, list[list[tuple[int, int, int, int]]]]:
    raw = path.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    width = height = None
    idat = bytearray()
    while pos < len(raw):
        length = struct.unpack(">I", raw[pos : pos + 4])[0]
        ctype = raw[pos + 4 : pos + 8]
        data = raw[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", data[:10])
            if bit_depth != 8 or color_type not in (2, 6):
                raise SystemExit(f"Unsupported PNG format in {path}")
        elif ctype == b"IDAT":
            idat += data
        elif ctype == b"IEND":
            break
    assert width and height
    decompressed = zlib.decompress(bytes(idat))
    channels = 4 if color_type == 6 else 3
    stride = 1 + width * channels
    rows: list[list[tuple[int, int, int, int]]] = []
    prev = bytearray(width * channels)
    offset = 0
    for _ in range(height):
        filt = decompressed[offset]
        scan = bytearray(decompressed[offset + 1 : offset + stride])
        offset += stride
        if filt == 1:  # Sub
            for i in range(channels, len(scan)):
                scan[i] = (scan[i] + scan[i - channels]) & 255
        elif filt == 2:  # Up
            for i in range(len(scan)):
                scan[i] = (scan[i] + prev[i]) & 255
        elif filt == 3:  # Average
            for i in range(len(scan)):
                left = scan[i - channels] if i >= channels else 0
                up = prev[i]
                scan[i] = (scan[i] + ((left + up) >> 1)) & 255
        elif filt == 4:  # Paeth
            for i in range(len(scan)):
                a = scan[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if pa <= pb and pa <= pc else b if pb <= pc else c
                scan[i] = (scan[i] + pr) & 255
        elif filt != 0:
            raise SystemExit(f"Unsupported PNG filter {filt}")
        prev = scan
        row = []
        for x in range(width):
            i = x * channels
            if channels == 4:
                row.append((scan[i], scan[i + 1], scan[i + 2], scan[i + 3]))
            else:
                row.append((scan[i], scan[i + 1], scan[i + 2], 255))
        rows.append(row)
    return width, height, rows


def blit_rgba(dst, dx: int, dy: int, rgba, scale: int = 1) -> None:
    h = len(rgba)
    w = len(rgba[0])
    for y in range(h):
        for x in range(w):
            r, g, b, a = rgba[y][x]
            if a < 8:
                continue
            for sy in range(scale):
                for sx in range(scale):
                    blend(dst, dx + x * scale + sx, dy + y * scale + sy, (r, g, b), a / 255.0)


# 5x7 capitals + space for Sign in / FosOS (minimal glyph set).
FONT = {
    " ": [0, 0, 0, 0, 0, 0, 0],
    "A": [0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "E": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    "F": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10],
    "G": [0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0E],
    "I": [0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x1F],
    "N": [0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11],
    "O": [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "S": [0x0E, 0x11, 0x10, 0x0E, 0x01, 0x11, 0x0E],
    "g": [0x00, 0x0E, 0x11, 0x11, 0x0F, 0x01, 0x0E],
    "i": [0x04, 0x00, 0x0C, 0x04, 0x04, 0x04, 0x0E],
    "n": [0x00, 0x1A, 0x15, 0x15, 0x15, 0x15, 0x15],
    "o": [0x00, 0x0E, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "s": [0x00, 0x0F, 0x10, 0x0E, 0x01, 0x1E, 0x00],
}


def draw_text(dst, x: int, y: int, text: str, color, scale: int = 2, tracking: int = 1) -> int:
    cx = x
    for ch in text:
        glyph = FONT.get(ch, FONT[" "])
        for row, bits in enumerate(glyph):
            for col in range(5):
                if bits & (0x10 >> col):
                    for sy in range(scale):
                        for sx in range(scale):
                            blend(dst, cx + col * scale + sx, y + row * scale + sy, color)
        cx += (5 + tracking) * scale
    return cx


def make_mark_bmp() -> None:
    if not MARK_PNG.is_file():
        raise SystemExit(f"Missing {MARK_PNG}")
    _, _, rgba = load_png_rgba(MARK_PNG)
    # Crop to content-ish square and scale down for login header.
    size = 96
    canvas = blank(size, size, CARD)
    # Source is 256x256 with black bg + white mark; sample into card.
    step = 256 / size
    for y in range(size):
        for x in range(size):
            sx = min(255, int(x * step))
            sy = min(255, int(y * step))
            r, g, b, a = rgba[sy][sx]
            # Treat near-black as transparent so card shows through.
            if r + g + b < 40:
                continue
            blend(canvas, x, y, (r, g, b), max(a / 255.0, 0.85))
    write_bmp(OUT_DIR / "fosos-dawn-aperture.bmp", size, size, canvas)


def make_banner_bmp() -> None:
    # Wide header used as ls_logo: mark + FosOS + Sign in on card tone.
    w, h = 340, 120
    canvas = blank(w, h, CARD)
    if MARK_PNG.is_file():
        _, _, rgba = load_png_rgba(MARK_PNG)
        # Place a 64px mark on the left.
        mark = 64
        step = 256 / mark
        scaled = []
        for y in range(mark):
            row = []
            for x in range(mark):
                sx = min(255, int(x * step))
                sy = min(255, int(y * step))
                row.append(rgba[sy][sx])
            scaled.append(row)
        blit_rgba(canvas, 24, 28, scaled, scale=1)
    draw_text(canvas, 104, 34, "FosOS", FG, scale=3, tracking=1)
    draw_text(canvas, 104, 72, "Sign in", MUTED, scale=2, tracking=1)
    # Hairline under brand block (square FosOS card language).
    for x in range(24, w - 24):
        blend(canvas, x, h - 1, (255, 255, 255), 0.10)
    write_bmp(OUT_DIR / "fosos-rdp-login-banner.bmp", w, h, canvas)


def make_background_bmp() -> None:
    # Small tile; xrdp will scale/zoom to the screen.
    w, h = 64, 64
    canvas = blank(w, h, BG)
    write_bmp(OUT_DIR / "fosos-rdp-login-bg.bmp", w, h, canvas)


def main() -> None:
    make_mark_bmp()
    make_banner_bmp()
    make_background_bmp()
    print(f"Wrote bitmaps under {OUT_DIR}")


if __name__ == "__main__":
    main()
