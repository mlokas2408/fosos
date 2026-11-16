"""Drawn FosOS wallpapers. Safe to import from the greeter (no Wnck/panel)."""

from __future__ import annotations

import math

import cairo
import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk

# Theme id → display name. Greeter/lock always use "dawn".
THEMES: tuple[tuple[str, str], ...] = (
    ("dawn", "Dawn Aperture"),
    ("steel", "Steel grid"),
    ("graphite", "Graphite"),
    ("ink", "Ink flat"),
)

_PALETTES = {
    "dawn": {
        "base": (10 / 255, 10 / 255, 10 / 255),
        "mid": (18 / 255, 18 / 255, 18 / 255),
        "glow": (38 / 255, 38 / 255, 38 / 255),
        "grid": 0.03,
        "water": 0.02,
        "vignette": 0.85,
    },
    "steel": {
        "base": (14 / 255, 16 / 255, 18 / 255),
        "mid": (28 / 255, 32 / 255, 36 / 255),
        "glow": (52 / 255, 58 / 255, 64 / 255),
        "grid": 0.045,
        "water": 0.03,
        "vignette": 0.75,
    },
    "graphite": {
        "base": (22 / 255, 22 / 255, 22 / 255),
        "mid": (32 / 255, 32 / 255, 32 / 255),
        "glow": (48 / 255, 48 / 255, 48 / 255),
        "grid": 0.02,
        "water": 0.015,
        "vignette": 0.7,
    },
    "ink": {
        "base": (8 / 255, 8 / 255, 8 / 255),
        "mid": (8 / 255, 8 / 255, 8 / 255),
        "glow": (8 / 255, 8 / 255, 8 / 255),
        "grid": 0.0,
        "water": 0.0,
        "vignette": 0.0,
    },
}


def ellipse_pattern(cx, cy, rx, ry, stops) -> cairo.RadialGradient:
    pattern = cairo.RadialGradient(0, 0, 0, 0, 0, 1)
    for offset, rgba in stops:
        pattern.add_color_stop_rgba(offset, *rgba)
    pattern.set_matrix(cairo.Matrix(1 / rx, 0, 0, 1 / ry, -cx / rx, -cy / ry))
    return pattern


def draw_grid(cr, x, y, w, h, step, alpha, mask) -> None:
    if alpha <= 0:
        return
    cr.push_group()
    cr.set_source_rgba(1, 1, 1, alpha)
    cr.set_line_width(1)
    gx = x + 0.5
    while gx < x + w:
        cr.move_to(gx, y)
        cr.line_to(gx, y + h)
        gx += step
    gy = y + 0.5
    while gy < y + h:
        cr.move_to(x, gy)
        cr.line_to(x + w, gy)
        gy += step
    cr.stroke()
    cr.pop_group_to_source()
    cr.mask(mask)


def draw_wallpaper(cr, area: Gdk.Rectangle, theme: str = "dawn") -> None:
    palette = _PALETTES.get(theme) or _PALETTES["dawn"]
    base = palette["base"]
    mid = palette["mid"]
    glow = palette["glow"]
    x, y, w, h = area.x, area.y, area.width, area.height
    cr.save()
    cr.rectangle(x, y, w, h)
    cr.clip()

    angle = math.radians(160)
    dx, dy = math.sin(angle), -math.cos(angle)
    length = abs(w * dx) + abs(h * dy)
    cx, cy = x + w / 2, y + h / 2
    linear = cairo.LinearGradient(
        cx - dx * length / 2, cy - dy * length / 2, cx + dx * length / 2, cy + dy * length / 2
    )
    linear.add_color_stop_rgb(0, *base)
    linear.add_color_stop_rgb(0.45, *mid)
    linear.add_color_stop_rgb(1, *base)
    cr.set_source(linear)
    cr.paint()

    if theme != "ink":
        for px, py, rx, ry, alpha, end in ((0.15, 0.20, 0.70, 0.55, 0.55, 0.60), (0.85, 0.75, 0.60, 0.50, 0.40, 0.55)):
            cr.set_source(
                ellipse_pattern(x + w * px, y + h * py, w * rx, h * ry, [(0, (*glow, alpha)), (end, (*glow, 0))])
            )
            cr.paint()

        grid_mask = ellipse_pattern(
            x + w * 0.5, y + h * 0.45, w * 0.8, h * 0.7, [(0.2, (0, 0, 0, 1)), (0.75, (0, 0, 0, 0))]
        )
        draw_grid(cr, x, y, w, h, 48, palette["grid"], grid_mask)

        wx, wy = x + w * 0.88, y + h * 0.82
        radius = math.hypot(w * 0.88, h * 0.82)
        water_mask = ellipse_pattern(wx, wy, radius, radius, [(0, (0, 0, 0, 1)), (0.42, (0, 0, 0, 0))])
        draw_grid(cr, x, y, w, h, 96, palette["water"], water_mask)

        if palette["vignette"] > 0:
            vignette = cairo.LinearGradient(0, y + h, 0, y)
            vignette.add_color_stop_rgba(0, *base, palette["vignette"])
            vignette.add_color_stop_rgba(0.28, *base, 0)
            cr.set_source(vignette)
            cr.paint()

    cr.restore()
