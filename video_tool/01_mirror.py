#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01_mirror.py — CHỨC NĂNG RIÊNG 1: Mirror / Flip ngang
=====================================================
CHỈ lật ngang (hflip), không làm gì khác. Audio giữ nguyên (-c:a copy).
Xuất H.264 .mp4, encoder tự chọn theo GPU (NVENC/QSV/AMF/CPU).

⚠️ Chỉ dùng khi video KHÔNG có chữ. Nếu có chữ, chữ sẽ bị ngược.

Chạy độc lập:
    python 01_mirror.py -i input.mp4 -o output.mp4
    python 01_mirror.py -i input.mp4 -o output.mp4 --encoder h264_nvenc --quality-mode crf --quality-value 20
    python 01_mirror.py -i input.mp4 -o output.mp4 --quality-mode bitrate --quality-value 8M
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (check_ffmpeg, encode_args, print_info, run,
                    validate_params, vf_for_encoder)
from gpu_detect import detect_gpu


def mirror(input_path: Path, output_path: Path,
           encoder="auto", quality_mode="source", quality_value="",
           preset=None, threads=None, dry_run=False) -> Path:
    """Chỉ mirror ngang, xuất H.264 .mp4."""
    check_ffmpeg()
    validate_params(quality_mode=quality_mode, quality_value=quality_value)
    info = print_info(input_path)

    det = detect_gpu() if encoder == "auto" else None
    enc = det["encoder"] if det else encoder
    preset = preset or (det["preset"] if det else "medium")
    threads = threads or (det["threads"] if det else 4)
    print(f"[INFO] Encoder: {enc} (preset {preset}) | "
          f"Chất lượng: {quality_mode} {quality_value or '(gốc)'}")

    cmd = ["ffmpeg", "-y", "-i", str(input_path),
           "-vf", vf_for_encoder("hflip,format=yuv420p", enc)]
    cmd += encode_args(enc, quality_mode, quality_value, preset, threads, info)
    cmd += ["-movflags", "+faststart",
            "-c:a", "copy",
            str(output_path)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    run(cmd, dry_run=dry_run)
    if not dry_run:
        print_info(output_path)
        print(f"[XONG] Mirror: {output_path}")
    return output_path


def main():
    p = argparse.ArgumentParser(description="1. Mirror ngang riêng lẻ (xuất H.264 .mp4)")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--encoder", default="auto",
                   help="auto | libx264 | h264_nvenc | h264_qsv | h264_amf | h264_vaapi")
    p.add_argument("--quality-mode", default="source",
                   choices=["source", "bitrate", "crf"])
    p.add_argument("--quality-value", default="")
    p.add_argument("--preset", default=None)
    p.add_argument("--threads", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    mirror(Path(a.input), Path(a.output), a.encoder, a.quality_mode,
           a.quality_value, a.preset, a.threads, a.dry_run)


if __name__ == "__main__":
    main()
