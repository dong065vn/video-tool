#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01_reencode.py — CHỨC NĂNG RIÊNG 1: Re-encode & Strip Metadata
=============================================================
CHỈ làm đúng việc này, không làm crop / flip / overlay / pitch / ghép.
- Input: .flv / .mp4 / .mov / .mkv ... -> Output: .mp4 (H.264 + AAC)
- Xóa sạch metadata: -map_metadata -1
- Đổi FPS: 30 -> 29.97 hoặc 25
- Đổi nhẹ Saturation / Contrast

Chạy độc lập:
    python 01_reencode.py -i input.flv -o output.mp4
    python 01_reencode.py -i input.flv -o output.mp4 --fps 25 --saturation 1.06 --contrast 1.04
    python 01_reencode.py -i input.flv -o output.mp4 --dry-run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import check_ffmpeg, get_info, print_info, run


def reencode(input_path: Path, output_path: Path,
             fps="29.97", saturation=1.06, contrast=1.04,
             crf=20, preset="medium", dry_run=False) -> Path:
    """Chỉ re-encode. Trả về đường dẫn output."""
    check_ffmpeg()
    info = print_info(input_path)

    vf = f"fps={fps},eq=saturation={saturation}:contrast={contrast}:brightness=0.01,format=yuv420p"

    cmd = ["ffmpeg", "-y", "-i", str(input_path),
           "-vf", vf, "-map", "0:v:0"]
    if info["has_audio"]:
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "128k"]
    else:
        cmd += ["-an"]
    cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-pix_fmt", "yuv420p",
            "-map_metadata", "-1",
            "-metadata", "title=", "-metadata", "comment=", "-metadata", "encoder=",
            "-movflags", "+faststart",
            "-r", str(fps), str(output_path)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    run(cmd, dry_run=dry_run)
    if not dry_run:
        print_info(output_path)
        print(f"[XONG] Re-encode: {output_path}")
    return output_path


def main():
    p = argparse.ArgumentParser(description="1. Re-encode + strip metadata + đổi FPS/màu (riêng lẻ)")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--fps", default="29.97")
    p.add_argument("--saturation", type=float, default=1.06)
    p.add_argument("--contrast", type=float, default=1.04)
    p.add_argument("--crf", type=int, default=20)
    p.add_argument("--preset", default="medium")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    reencode(Path(a.input), Path(a.output), a.fps, a.saturation, a.contrast,
             a.crf, a.preset, a.dry_run)


if __name__ == "__main__":
    main()
