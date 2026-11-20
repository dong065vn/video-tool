#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
05_audio_pitch.py — CHỨC NĂNG RIÊNG 3a: Đổi cao độ âm thanh (Pitch)
===================================================================
CHỈ đổi pitch, không động vào video. Video giữ nguyên 100% (-c:v copy).

- pitch 1.02 = +2%, 0.97 = -3% (khoảng ±2-3% trong ảnh)
- rubberband: đổi pitch, giữ nguyên tempo (khuyên dùng)
- asetrate: đổi cả tốc độ rồi bù lại bằng atempo để giữ thời lượng

Chạy độc lập:
    python 05_audio_pitch.py -i input.mp4 -o output.mp4 --pitch 1.02
    python 05_audio_pitch.py -i input.mp4 -o output.mp4 --pitch 0.98 --pitch-mode asetrate
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import check_ffmpeg, print_info, run


def audio_pitch(input_path: Path, output_path: Path,
                pitch=1.02, pitch_mode="rubberband", dry_run=False) -> Path:
    """Chỉ đổi pitch audio."""
    check_ffmpeg()
    info = print_info(input_path)
    if not info["has_audio"]:
        raise RuntimeError("File không có audio, không làm được pitch.")

    if pitch_mode == "rubberband":
        af = f"rubberband=pitch={pitch}"
    else:
        af = f"asetrate=44100*{pitch},aresample=44100,atempo={1.0 / pitch:.6f}"
    af += ",volume=0.98,aresample=44100"

    cmd = ["ffmpeg", "-y", "-i", str(input_path),
           "-af", af,
           "-c:v", "copy",
           "-c:a", "aac", "-b:a", "128k",
           str(output_path)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    run(cmd, dry_run=dry_run)
    if not dry_run:
        print_info(output_path)
        print(f"[XONG] Pitch {pitch} ({pitch_mode}): {output_path}")
    return output_path


def main():
    p = argparse.ArgumentParser(description="3a. Đổi Pitch riêng lẻ (video giữ nguyên)")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--pitch", type=float, default=1.02)
    p.add_argument("--pitch-mode", choices=["rubberband", "asetrate"], default="rubberband")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    audio_pitch(Path(a.input), Path(a.output), a.pitch, a.pitch_mode, a.dry_run)


if __name__ == "__main__":
    main()
