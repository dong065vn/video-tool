#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
06_audio_speed.py — CHỨC NĂNG RIÊNG 3b: Đổi tốc độ âm thanh (Speed)
====================================================================
CHỈ đổi tốc độ audio bằng atempo, không động vào video (-c:v copy),
không đổi pitch.

- speed 1.02 = nhanh hơn 2%, 0.98 = chậm hơn 2%

Chạy độc lập:
    python 06_audio_speed.py -i input.mp4 -o output.mp4 --speed 1.02
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import check_ffmpeg, print_info, run


def audio_speed(input_path: Path, output_path: Path,
                speed=1.02, dry_run=False) -> Path:
    """Chỉ đổi tốc độ audio."""
    check_ffmpeg()
    info = print_info(input_path)
    if not info["has_audio"]:
        raise RuntimeError("File không có audio, không làm được speed.")

    af = f"atempo={speed},volume=0.98,aresample=44100"

    cmd = ["ffmpeg", "-y", "-i", str(input_path),
           "-af", af,
           "-c:v", "copy",
           "-c:a", "aac", "-b:a", "128k",
           str(output_path)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    run(cmd, dry_run=dry_run)
    if not dry_run:
        print_info(output_path)
        print(f"[XONG] Speed {speed}x: {output_path}")
    return output_path


def main():
    p = argparse.ArgumentParser(description="3b. Đổi Speed riêng lẻ (video giữ nguyên)")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--speed", type=float, default=1.02)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    audio_speed(Path(a.input), Path(a.output), a.speed, a.dry_run)


if __name__ == "__main__":
    main()
