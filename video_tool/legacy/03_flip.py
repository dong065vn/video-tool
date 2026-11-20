#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03_flip.py — CHỨC NĂNG RIÊNG 2b: Mirror / Flip ngang
====================================================
CHỈ lật ngang (hflip), không làm gì khác. Audio giữ nguyên (-c:a copy).

⚠️ Chỉ dùng khi video KHÔNG có chữ. Nếu có chữ, chữ sẽ bị ngược.

Chạy độc lập:
    python 03_flip.py -i input.mp4 -o output.mp4
    python 03_flip.py -i input.mp4 -o output.mp4 --dry-run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import check_ffmpeg, print_info, run


def flip(input_path: Path, output_path: Path,
         crf=20, preset="medium", dry_run=False) -> Path:
    """Chỉ flip ngang."""
    check_ffmpeg()
    print_info(input_path)

    cmd = ["ffmpeg", "-y", "-i", str(input_path),
           "-vf", "hflip,format=yuv420p",
           "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
           "-pix_fmt", "yuv420p",
           "-c:a", "copy",
           str(output_path)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    run(cmd, dry_run=dry_run)
    if not dry_run:
        print_info(output_path)
        print(f"[XONG] Flip ngang: {output_path}")
    return output_path


def main():
    p = argparse.ArgumentParser(description="2b. Flip ngang riêng lẻ (audio giữ nguyên)")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--crf", type=int, default=20)
    p.add_argument("--preset", default="medium")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    flip(Path(a.input), Path(a.output), a.crf, a.preset, a.dry_run)


if __name__ == "__main__":
    main()
