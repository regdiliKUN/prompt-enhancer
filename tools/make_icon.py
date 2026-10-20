#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成应用图标 assets/icon.ico（蓝紫渐变圆角方块 + PE 字样）。"""

import os
import sys
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "assets")
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]

FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/Arialbd.ttf",
]


def gradient(size, top, bottom):
    img = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(img)
    r1, g1, b1 = top
    r2, g2, b2 = bottom
    for y in range(size):
        t = y / max(1, size - 1)
        d.line([(0, y), (size, y)], fill=(int(r1 + (r2 - r1) * t),
                                          int(g1 + (g2 - g1) * t),
                                          int(b1 + (b2 - b1) * t)))
    return img


def rounded_mask(size, radius_ratio=0.22):
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * radius_ratio), fill=255)
    return mask


def load_font(size):
    for path in FONT_CANDIDATES:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def build(size=256):
    base = gradient(size, (79, 140, 255), (124, 92, 255)).convert("RGBA")
    base.putalpha(rounded_mask(size))
    d = ImageDraw.Draw(base)
    font = load_font(int(size * 0.46))
    text = "PE"
    bbox = d.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - w) / 2 - bbox[0]
    y = (size - h) / 2 - bbox[1] - size * 0.02
    d.text((x, y), text, font=font, fill=(255, 255, 255, 255))
    return base


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    base = build(256)
    ico = os.path.join(OUT_DIR, "icon.ico")
    base.save(ico, format="ICO", sizes=[(s, s) for s in SIZES])
    png = os.path.join(OUT_DIR, "icon.png")
    base.save(png, format="PNG")
    print("图标已生成：%s / %s" % (ico, png))


if __name__ == "__main__":
    sys.exit(main())
