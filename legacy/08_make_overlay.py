#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
08_make_overlay.py — CHỨC NĂNG RIÊNG: Tạo ảnh overlay PNG trong suốt
======================================================================
CHỈ tạo ảnh PNG bằng Pillow, không xử lý video.
Ảnh tạo ra dùng làm overlay trong OBS hoặc đưa vào 04_overlay.py sau.

Chạy độc lập:
    python 08_make_overlay.py -o overlay.png --voucher "GIAM 50% - FREESHIP"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def make_overlay_png(path: Path, width=1920, height=1080,
                     voucher="GIAM 50% - FREESHIP"):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("[LỖI] Chưa cài Pillow. pip install Pillow")
        sys.exit(1)

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, width - 1, 8], fill=(255, 0, 0, 230))
    d.rectangle([0, height - 9, width - 1, height - 1], fill=(255, 0, 0, 230))
    d.rectangle([0, 0, 8, height - 1], fill=(255, 0, 0, 230))
    d.rectangle([width - 9, 0, width - 1, height - 1], fill=(255, 0, 0, 230))
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 56)
    except Exception:
        font = ImageFont.load_default()
    bbox = d.textbbox((0, 0), voucher, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x0 = (width - tw) // 2 - 30
    y0 = height - th - 110
    d.rounded_rectangle([x0, y0, x0 + tw + 60, y0 + th + 36],
                        radius=18, fill=(220, 0, 0, 215))
    d.text((x0 + 30, y0 + 14), voucher, font=font, fill=(255, 235, 0, 255))
    img.save(path)
    print(f"[XONG] Đã tạo overlay PNG: {path}")
    return path


def main():
    p = argparse.ArgumentParser(description="Tạo ảnh overlay PNG riêng lẻ")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--voucher", default="GIAM 50% - FREESHIP")
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    a = p.parse_args()
    make_overlay_png(Path(a.output), a.width, a.height, a.voucher)


if __name__ == "__main__":
    main()
