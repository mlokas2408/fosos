"""Drawn FosOS wallpaper. Safe to import from the greeter (no Wnck/panel)."""

from __future__ import annotations

import math

import cairo
import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk

BASE = (10 / 255, 10 / 255, 10 / 255)
MID = (18 / 255, 18 / 255, 18 / 255)
GLOW = (38 / 255, 38 / 255, 38 / 255)


def ellipse_pattern(cx, cy, rx, ry, stops) -> cairo.RadialGradient:
    pattern = cairo.RadialGradient(0, 0, 0, 0, 0, 1)
    for offset, rgba in stops:
        pattern.add_color_stop_rgba(offset, *rgba)
    pattern.set_matrix(cairo.Matrix(1 / rx, 0, 0, 1 / ry, -cx / rx, -cy / ry))
    return pattern


def draw_grid(cr, x, y, w, h, step, alpha, mask) -> None:
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


def draw_wallpaper(cr, area: Gdk.Rectangle) -> None:
    x, y, w, h = area.x, area.y, area.width, area.height
    cr.save()
    cr.rectangle(x, y, w, h)
    cr.clip()

    # linear-gradient(160deg, base, mid 45%, base)
    angle = math.radians(160)
    dx, dy = math.sin(angle), -math.cos(angle)
    length = abs(w * dx) + abs(h * dy)
    cx, cy = x + w / 2, y + h / 2
    linear = cairo.LinearGradient(
        cx - dx * length / 2, cy - dy * length / 2, cx + dx * length / 2, cy + dy * length / 2
    )
    linear.add_color_stop_rgb(0, *BASE)
    linear.add_color_stop_rgb(0.45, *MID)
    linear.add_color_stop_rgb(1, *BASE)
    cr.set_source(linear)
    cr.paint()

    for px, py, rx, ry, alpha, end in ((0.15, 0.20, 0.70, 0.55, 0.55, 0.60), (0.85, 0.75, 0.60, 0.50, 0.40, 0.55)):
        cr.set_source(
            ellipse_pattern(x + w * px, y + h * py, w * rx, h * ry, [(0, (*GLOW, alpha)), (end, (*GLOW, 0))])
        )
        cr.paint()

    grid_mask = ellipse_pattern(x + w * 0.5, y + h * 0.45, w * 0.8, h * 0.7, [(0.2, (0, 0, 0, 1)), (0.75, (0, 0, 0, 0))])
    draw_grid(cr, x, y, w, h, 48, 0.03, grid_mask)

    wx, wy = x + w * 0.88, y + h * 0.82
    radius = math.hypot(w * 0.88, h * 0.82)
    water_mask = ellipse_pattern(wx, wy, radius, radius, [(0, (0, 0, 0, 1)), (0.42, (0, 0, 0, 0))])
    draw_grid(cr, x, y, w, h, 96, 0.02, water_mask)

    vignette = cairo.LinearGradient(0, y + h, 0, y)
    vignette.add_color_stop_rgba(0, *BASE, 0.85)
    vignette.add_color_stop_rgba(0.28, *BASE, 0)
    cr.set_source(vignette)
    cr.paint()
    cr.restore()
