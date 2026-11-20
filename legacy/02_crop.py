#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02_crop.py — CHỨC NĂNG RIÊNG 2a: Crop (cắt cúp khung hình)
=========================================================
CHỈ crop, không làm gì khác. Audio giữ nguyên 100% (-c:a copy),
video không đổi FPS / màu / pitch.

Chạy độc lập:
    python 02_crop.py -i input.mp4 -o output.mp4
    python 02_crop.py -i input.mp4 -o output.mp4 --crop 0.05
    python 02_crop.py -i input.mp4 -o output.mp4 --crop 0.03 --dry-run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import check_ffmpeg, print_info, run


def crop(input_path: Path, output_path: Path,
         crop_ratio=0.04, crf=20, preset="medium", dry_run=False) -> Path:
    """Chỉ crop. crop_ratio 0.03-0.05, mặc định 0.04 = 4% mỗi chiều."""
    check_ffmpeg()
    print_info(input_path)

    vf = (f"crop=iw*{1 - crop_ratio:.4f}:ih*{1 - crop_ratio:.4f}:(iw-ow)/2:(ih-oh)/2,"
          f"scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p")

    cmd = ["ffmpeg", "-y", "-i", str(input_path),
           "-vf", vf,
           "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
           "-pix_fmt", "yuv420p",
           "-c:a", "copy",
           str(output_path)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    run(cmd, dry_run=dry_run)
    if not dry_run:
        print_info(output_path)
        print(f"[XONG] Crop {crop_ratio*100:.0f}%: {output_path}")
    return output_path


def main():
    p = argparse.ArgumentParser(description="2a. Crop riêng lẻ (audio giữ nguyên)")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--crop", type=float, default=0.04,
                   help="Tỉ lệ crop mỗi chiều, 0.03-0.05")
    p.add_argument("--crf", type=int, default=20)
    p.add_argument("--preset", default="medium")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    crop(Path(a.input), Path(a.output), a.crop, a.crf, a.preset, a.dry_run)


if __name__ == "__main__":
    main()
