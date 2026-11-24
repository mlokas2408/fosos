#!/usr/bin/env python3
"""Generate FosOS Plymouth two-step frames (logo + spinner on transparent)."""

from __future__ import annotations

import math
import shutil
import sys
from pathlib import Path

try:
    import cairo
except ImportError:
    print("generate-plymouth.py requires python3-cairo", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "usr/share/plymouth/themes/fosos"
LOGO_SRC = ROOT / "usr/share/fosos/logo/fosos-dawn-aperture-256.png"
SPINNER = Path("/usr/share/plymouth/themes/spinner")

FG = (250 / 255, 250 / 255, 250 / 255)


def main() -> None:
    if not LOGO_SRC.is_file():
        print(f"missing logo: {LOGO_SRC}", file=sys.stderr)
        sys.exit(1)
    OUT.mkdir(parents=True, exist_ok=True)
    logo = cairo.ImageSurface.create_from_png(str(LOGO_SRC))
    logo_w, logo_h = logo.get_width(), logo.get_height()

    width, height = 320, 400
    for i in range(1, 37):
        angle = (i - 1) / 36 * 2 * math.pi
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        cr = cairo.Context(surf)
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        target = 128
        scale = target / max(logo_w, logo_h)
        tw, th = logo_w * scale, logo_h * scale
        cr.save()
        cr.translate((width - tw) / 2, 48)
        cr.scale(scale, scale)
        cr.set_source_surface(logo, 0, 0)
        cr.paint()
        cr.restore()
        cx, cy = width / 2, height - 90
        radius = 18
        cr.set_line_width(3.0)
        cr.set_source_rgba(*FG, 0.18)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()
        cr.set_source_rgba(*FG, 0.95)
        cr.arc(cx, cy, radius, angle, angle + 1.5)
        cr.stroke()
        surf.write_to_png(str(OUT / f"animation-{i:04d}.png"))

    for i in range(1, 31):
        angle = (i - 1) / 30 * 2 * math.pi
        size = 64
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
        cr = cairo.Context(surf)
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        cx = cy = size / 2
        radius = size * 0.28
        cr.set_line_width(3.0)
        cr.set_source_rgba(*FG, 0.18)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()
        cr.set_source_rgba(*FG, 0.95)
        cr.arc(cx, cy, radius, angle, angle + 1.5)
        cr.stroke()
        surf.write_to_png(str(OUT / f"throbber-{i:04d}.png"))

    wm = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
    wm.write_to_png(str(OUT / "watermark.png"))

    if SPINNER.is_dir():
        for name in (
            "bullet.png",
            "entry.png",
            "lock.png",
            "capslock.png",
            "keyboard.png",
            "keymap-render.png",
        ):
            src = SPINNER / name
            if src.is_file():
                shutil.copy2(src, OUT / name)

    print(f"Wrote Plymouth frames under {OUT}")


if __name__ == "__main__":
    main()
