#!/usr/bin/env python3
"""Generate FosOS Plymouth two-step assets (centred logo + lower spinner).

Layout is resolution-independent via Plymouth alignments:
  - watermark.png = Dawn Aperture mark, Watermark*Alignment=.5 → true centre
  - throbber/animation = spinner only, VerticalAlignment=.75 with the spinner
    drawn LOGO_TARGET/4 below the image centre so it sits at
    0.75·H + LOGO/4 = midpoint between logo bottom (H/2 + LOGO/2) and
    screen bottom (H), for any panel height H.

With UseEndAnimation=false, Plymouth shows throbber-* (not animation-*).

Requires Pillow (`pip install Pillow` or `python3-pil`).
"""

from __future__ import annotations

import math
import shutil
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("generate-plymouth.py requires Pillow (python3-pil)", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "usr/share/plymouth/themes/fosos"
LOGO_CANDIDATES = (
    ROOT / "usr/share/fosos/logo/fosos-dawn-aperture-512.png",
    ROOT / "usr/share/fosos/logo/fosos-dawn-aperture-256.png",
)
SPINNER = Path("/usr/share/plymouth/themes/spinner")

FG = (250, 250, 250, 250)
FG_DIM = (250, 250, 250, 51)

LOGO_TARGET = 280
SPINNER_RADIUS = 32
SPINNER_LINE = 5
# Spinner-only strip. Image centre is placed at 0.75·H; draw the ring
# LOGO_TARGET/4 below that so it matches the logo-bottom→screen-bottom mid.
FRAME_W = 96
FRAME_H = 220
SPINNER_CY = FRAME_H / 2 + LOGO_TARGET / 4


def _mark_image(logo_path: Path) -> Image.Image:
    """White-on-black logo PNG → white mark on transparent (RGBA)."""
    src = Image.open(logo_path).convert("RGBA")
    pixels = src.load()
    w, h = src.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            lum = (r + g + b) // 3
            if lum < 40:
                pixels[x, y] = (0, 0, 0, 0)
            else:
                pixels[x, y] = (250, 250, 250, max(lum, a))
    return src


def _scaled_mark(mark: Image.Image, target: int) -> Image.Image:
    mw, mh = mark.size
    scale = target / max(mw, mh)
    tw, th = max(1, int(mw * scale)), max(1, int(mh * scale))
    return mark.resize((tw, th), Image.Resampling.LANCZOS)


def _draw_spinner(draw: ImageDraw.ImageDraw, angle: float) -> None:
    cx = FRAME_W / 2
    cy = SPINNER_CY
    bbox = [
        cx - SPINNER_RADIUS,
        cy - SPINNER_RADIUS,
        cx + SPINNER_RADIUS,
        cy + SPINNER_RADIUS,
    ]
    draw.arc(bbox, start=0, end=360, fill=FG_DIM, width=SPINNER_LINE)
    start_deg = math.degrees(angle)
    end_deg = start_deg + math.degrees(1.45)
    draw.arc(bbox, start=start_deg, end=end_deg, fill=FG, width=SPINNER_LINE)


def _write_spinner_sequence(prefix: str, count: int) -> None:
    for i in range(1, count + 1):
        angle = (i - 1) / count * 2 * math.pi
        frame = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
        _draw_spinner(ImageDraw.Draw(frame), angle)
        frame.save(OUT / f"{prefix}-{i:04d}.png")


def main() -> None:
    logo_src = next((p for p in LOGO_CANDIDATES if p.is_file()), None)
    if logo_src is None:
        print(
            f"missing logo; tried: {', '.join(str(p) for p in LOGO_CANDIDATES)}",
            file=sys.stderr,
        )
        sys.exit(1)
    OUT.mkdir(parents=True, exist_ok=True)
    mark = _mark_image(logo_src)

    # Boot path (UseEndAnimation=false): throbber is the spinner animation.
    _write_spinner_sequence("throbber", 30)
    _write_spinner_sequence("animation", 36)

    # Centred logo (Watermark*Alignment=.5). zz-fosos-plymouth restores this
    # after Debian's plymouth hook overwrites two-step watermarks.
    scaled = _scaled_mark(mark, LOGO_TARGET)
    tw, th = scaled.size
    side = max(tw, th, LOGO_TARGET)
    wm = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    wm.paste(scaled, ((side - tw) // 2, (side - th) // 2), scaled)
    wm.save(OUT / "watermark.png")

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

    print(f"Wrote Plymouth frames under {OUT} (logo from {logo_src.name})")


if __name__ == "__main__":
    main()
