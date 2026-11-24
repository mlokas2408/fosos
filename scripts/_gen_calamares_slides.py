#!/usr/bin/env python3
"""Generate FosOS Calamares branding slides and welcome logo."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("requires Pillow", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "packages/fosos-installer/usr/share/calamares/branding/fosos"
MARK = ROOT / "packages/fosos-theme/usr/share/fosos/logo/fosos-dawn-aperture-512.png"
BG = (10, 10, 10)
FG = (250, 250, 250)
MUTED = (161, 161, 161)
W, H = 1280, 720


def _font(size: int) -> ImageFont.ImageFont:
    for name in (
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        path = Path(name)
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _mark(size: int) -> Image.Image:
    src = Image.open(MARK).convert("RGBA")
    pixels = src.load()
    for y in range(src.height):
        for x in range(src.width):
            r, g, b, a = pixels[x, y]
            lum = (r + g + b) // 3
            if lum < 40:
                pixels[x, y] = (0, 0, 0, 0)
            else:
                pixels[x, y] = (250, 250, 250, max(lum, a))
    return src.resize((size, size), Image.Resampling.LANCZOS)


def _base() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    # Soft centre glow
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i, alpha in enumerate((18, 12, 7, 3)):
        pad = 80 + i * 70
        gd.ellipse((pad, pad // 2, W - pad, H - pad // 2), fill=(250, 250, 250, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    return img


def _save_slide(name: str, title: str, subtitle: str, doodle: str) -> None:
    img = _base()
    draw = ImageDraw.Draw(img)
    mark = _mark(160)
    mx = (W - mark.width) // 2
    my = 150
    img.paste(mark, (mx, my), mark)

    # Simple doodle accents
    if doodle == "devices":
        draw.rounded_rectangle((180, 200, 420, 360), radius=18, outline=MUTED, width=3)
        draw.rounded_rectangle((360, 300, 430, 420), radius=14, outline=MUTED, width=3)
        draw.rounded_rectangle((860, 190, 1100, 350), radius=18, outline=MUTED, width=3)
        draw.rounded_rectangle((980, 140, 1040, 250), radius=12, outline=MUTED, width=3)
    elif doodle == "browser":
        draw.rounded_rectangle((390, 120, 890, 420), radius=16, outline=MUTED, width=3)
        draw.ellipse((410, 140, 426, 156), outline=MUTED, width=2)
        draw.ellipse((434, 140, 450, 156), outline=MUTED, width=2)
        draw.ellipse((458, 140, 474, 156), outline=MUTED, width=2)
        draw.rounded_rectangle((490, 136, 820, 160), radius=8, outline=MUTED, width=2)
    elif doodle == "keys":
        draw.rounded_rectangle((470, 210, 810, 300), radius=12, outline=MUTED, width=3)
        draw.ellipse((500, 330, 560, 390), outline=MUTED, width=3)
        draw.line((560, 360, 760, 360), fill=MUTED, width=3)

    title_font = _font(42)
    sub_font = _font(26)
    tw = draw.textlength(title, font=title_font)
    draw.text(((W - tw) / 2, 480), title, fill=FG, font=title_font)
    sw = draw.textlength(subtitle, font=sub_font)
    draw.text(((W - sw) / 2, 545), subtitle, fill=MUTED, font=sub_font)
    img.save(OUT / name, optimize=True)


def _welcome() -> None:
    # Sidebar / product logo: mark on dark tile (not full wallpaper).
    size = 256
    tile = Image.new("RGBA", (size, size), (10, 10, 10, 255))
    mark = _mark(180)
    tile.paste(mark, ((size - mark.width) // 2, (size - mark.height) // 2), mark)
    tile.convert("RGB").save(OUT / "welcome.png", optimize=True)


def main() -> None:
    if not MARK.is_file():
        print(f"missing {MARK}", file=sys.stderr)
        sys.exit(1)
    OUT.mkdir(parents=True, exist_ok=True)
    _welcome()
    _save_slide(
        "slide1.png",
        "FosOS",
        "A calm desktop for everyday work",
        "none",
    )
    _save_slide(
        "slide2.png",
        "Desktop ready when you are",
        "Start menu, taskbar, and settings — familiar from the first sign-in",
        "devices",
    )
    _save_slide(
        "slide3.png",
        "Firefox is built in",
        "Browse privately with the browser that ships on every image",
        "browser",
    )
    _save_slide(
        "slide4.png",
        "Your disk. Your account.",
        "Optional encryption, then updates through the fos command",
        "keys",
    )
    print(f"Wrote slides and welcome.png under {OUT}")


if __name__ == "__main__":
    main()
