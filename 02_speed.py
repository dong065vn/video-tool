#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02_speed.py — CHỨC NĂNG RIÊNG 2: Tăng tốc độ video + audio
==========================================================
CHỈ tăng/giảm tốc độ (video setpts + audio atempo, giữ đúng nhịp, không đổi pitch).
Xuất H.264 .mp4, encoder tự chọn theo GPU.

- speed 1.2 = nhanh hơn 20%, 1.10 = nhanh hơn 10%, 0.95 = chậm hơn 5%
- Video không có audio vẫn làm được (chỉ tăng tốc video).

Chạy độc lập:
    python 02_speed.py -i input.mp4 -o output.mp4 --speed 1.2
    python 02_speed.py -i input.mp4 -o output.mp4 --speed 1.10 --quality-mode crf --quality-value 20
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (atempo_chain, check_ffmpeg, encode_args, print_info, run,
                    validate_params, vf_for_encoder)
from gpu_detect import detect_gpu


def speed_up(input_path: Path, output_path: Path, speed=1.2,
             encoder="auto", quality_mode="source", quality_value="",
             preset=None, threads=None, dry_run=False) -> Path:
    """Chỉ đổi tốc độ video + audio, xuất H.264 .mp4."""
    check_ffmpeg()
    validate_params(speed=speed,
                    quality_mode=quality_mode, quality_value=quality_value)
    info = print_info(input_path)

    det = detect_gpu() if encoder == "auto" else None
    enc = det["encoder"] if det else encoder
    preset = preset or (det["preset"] if det else "medium")
    threads = threads or (det["threads"] if det else 4)
    fps = info["fps"] or 30.0
    print(f"[INFO] Encoder: {enc} (preset {preset}) | Speed: {speed}x | "
          f"Chất lượng: {quality_mode} {quality_value or '(gốc)'}")

    vf = vf_for_encoder(f"setpts=PTS/{speed:.4f},fps={fps:.2f},format=yuv420p", enc)
    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-vf", vf]
    cmd += encode_args(enc, quality_mode, quality_value, preset, threads, info)
    cmd += ["-movflags", "+faststart"]
    if info["has_audio"]:
        cmd += ["-af", atempo_chain(speed), "-c:a", "aac", "-b:a", "128k"]
    else:
        cmd += ["-an"]
    cmd += [str(output_path)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    run(cmd, dry_run=dry_run)
    if not dry_run:
        print_info(output_path)
        print(f"[XONG] Speed {speed}x: {output_path}")
    return output_path


def main():
    p = argparse.ArgumentParser(description="2. Tăng tốc độ riêng lẻ (video + audio)")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--speed", type=float, default=1.2)
    p.add_argument("--encoder", default="auto")
    p.add_argument("--quality-mode", default="source",
                   choices=["source", "bitrate", "crf"])
    p.add_argument("--quality-value", default="")
    p.add_argument("--preset", default=None)
    p.add_argument("--threads", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    speed_up(Path(a.input), Path(a.output), a.speed, a.encoder,
             a.quality_mode, a.quality_value, a.preset, a.threads, a.dry_run)


if __name__ == "__main__":
    main()
