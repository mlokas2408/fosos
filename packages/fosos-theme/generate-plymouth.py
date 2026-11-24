#!/usr/bin/env python3
"""Generate FosOS Plymouth two-step frames (logo + spinner on transparent).

With UseEndAnimation=false, Plymouth's two-step plugin shows throbber-* during
boot and never plays animation-*. The Dawn Aperture mark must therefore live in
the throbber frames (not only in animation frames).

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

# Sized for 1080p+ / HiDPI laptops: logo ~280px, spinner ~64px diameter.
# Compact frame so logo+spinner read as one centred unit.
FRAME_W, FRAME_H = 480, 560
LOGO_TARGET = 280
SPINNER_RADIUS = 32
SPINNER_LINE = 5
LOGO_TOP = 36
# ~48px clear air between mark bottom and spinner top (radius 32).
SPINNER_CY = LOGO_TOP + LOGO_TARGET + 80


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


def _paste_mark(frame: Image.Image, mark: Image.Image) -> None:
    mw, mh = mark.size
    scale = LOGO_TARGET / max(mw, mh)
    tw, th = max(1, int(mw * scale)), max(1, int(mh * scale))
    scaled = mark.resize((tw, th), Image.Resampling.LANCZOS)
    x = (FRAME_W - tw) // 2
    frame.paste(scaled, (x, LOGO_TOP), scaled)


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


def _write_logo_spinner_sequence(mark: Image.Image, prefix: str, count: int) -> None:
    for i in range(1, count + 1):
        angle = (i - 1) / count * 2 * math.pi
        frame = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
        _paste_mark(frame, mark)
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

    # Boot path (UseEndAnimation=false): throbber is what the user sees.
    _write_logo_spinner_sequence(mark, "throbber", 30)
    # Keep animation frames branded too (end-animation / future toggles).
    _write_logo_spinner_sequence(mark, "animation", 36)

    # two-step always draws watermark.png near the bottom; keep a fully
    # transparent placeholder so only the centred throbber (logo+spinner)
    # is visible. zz-fosos-plymouth restores this after Debian's plymouth hook.
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(OUT / "watermark.png")

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
