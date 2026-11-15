#!/usr/bin/env python3
"""Write the FosOS wallpaper next to this script."""

import pathlib
import struct
import zlib

WIDTH = 1920
HEIGHT = 1080


def chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def pixel(x: int, y: int) -> bytes:
    nx = (x - WIDTH / 2) / (WIDTH / 2)
    ny = (y - HEIGHT / 2) / (HEIGHT / 2)
    distance = (nx * nx + ny * ny) ** 0.5
    glow = max(0.0, 1.0 - distance) ** 2
    shade = y / (HEIGHT - 1)
    red = 12 + 20 * (1 - shade) + 78 * glow
    green = 16 + 24 * (1 - shade) + 88 * glow
    blue = 22 + 32 * (1 - shade) + 96 * glow
    return bytes((min(int(red), 255), min(int(green), 255), min(int(blue), 255)))


def main() -> None:
    raw = bytearray()
    for y in range(HEIGHT):
        raw.append(0)
        for x in range(WIDTH):
            raw.extend(pixel(x, y))
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    destination = pathlib.Path(__file__).resolve().parent / "usr/share/backgrounds/fosos/fosos-wallpaper.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(png)
    print(destination, len(png))


if __name__ == "__main__":
    main()
