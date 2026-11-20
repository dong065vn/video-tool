#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
04_sticker.py — CHỨC NĂNG RIÊNG 4: Ghép 1 sticker (PNG trong suốt) vào video
=============================================================================
CHỈ ghép 1 sticker lên video (sticker được loop theo độ dài video).
Xuất H.264 .mp4, encoder tự chọn theo GPU.

Vị trí (--position): bottom-right (mặc định), top-right, bottom-left,
top-left, center. Kích thước (--scale): tỉ lệ chiều rộng sticker so với
video, VD 0.15 = rộng bằng 15% video.

Chạy độc lập:
    python 04_sticker.py -i video.mp4 -o out.mp4 --sticker sticker.png
    python 04_sticker.py -i video.mp4 -o out.mp4 --sticker sticker.png --position top-right --scale 0.2
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (check_ffmpeg, encode_args, print_info,
                    resolve_sticker_overlay_expr, run, validate_params)
from gpu_detect import detect_gpu

POSITIONS = {
    "auto-corners": ("W-w-20", "20"),
    "bottom-right": ("W-w-20", "H-h-20"),
    "top-right": ("W-w-20", "20"),
    "bottom-left": ("20", "H-h-20"),
    "top-left": ("20", "20"),
    "center": ("(W-w)/2", "(H-h)/2"),
    "top": ("(W-w)/2", "20"),
    "bottom": ("(W-w)/2", "H-h-20"),
    "left": ("20", "(H-h)/2"),
    "right": ("W-w-20", "(H-h)/2"),
}


def sticker_overlay(input_path: Path, output_path: Path, sticker_path: Path,
                    scale=0.15, position="bottom-right",
                    sticker_left=0, sticker_right=0,
                    sticker_top=0, sticker_bottom=0,
                    encoder="auto", quality_mode="source", quality_value="",
                    preset=None, threads=None, dry_run=False) -> Path:
    """Chỉ ghép 1 sticker vào video, xuất H.264 .mp4."""
    check_ffmpeg()
    validate_params(sticker_scale=scale,
                    quality_mode=quality_mode, quality_value=quality_value,
                    sticker_left=sticker_left, sticker_right=sticker_right,
                    sticker_top=sticker_top, sticker_bottom=sticker_bottom)
    info = print_info(input_path)
    if not Path(sticker_path).exists():
        raise FileNotFoundError(f"Không thấy file sticker: {sticker_path}")

    det = detect_gpu() if encoder == "auto" else None
    enc = det["encoder"] if det else encoder
    preset = preset or (det["preset"] if det else "medium")
    threads = threads or (det["threads"] if det else 4)
    w = info["width"]
    fps = info["fps"] or 30.0
    x, y = resolve_sticker_overlay_expr(
        position, left=sticker_left, right=sticker_right,
        top=sticker_top, bottom=sticker_bottom,
    )
    sw = max(2, int(w * scale))
    print(f"[INFO] Encoder: {enc} (preset {preset}) | "
          f"Sticker: {Path(sticker_path).name} ({position}, rộng {sw}px, x={x}, y={y})")

    fc = (f"[0:v]format=yuv420p[v0];"
          f"[1:v]scale={sw}:-2,format=rgba[stk];"
          f"[v0][stk]overlay={x}:{y}[vout]")
    if enc == "h264_vaapi":
        fc = fc.replace("[0:v]format=yuv420p[v0]",
                        "[0:v]format=nv12,hwupload[v0]")

    # -t giới hạn input sticker loop: nếu không, sticker loop vô hạn làm
    # ffmpeg encode mãi không dừng (đã gặp: file ra phình to vô hạn).
    dur = info["duration"] or 0
    cmd = ["ffmpeg", "-y",
           "-i", str(input_path),
           "-loop", "1", "-framerate", f"{fps:.2f}", "-t", f"{dur:.3f}",
           "-i", str(sticker_path),
           "-filter_complex", fc, "-map", "[vout]"]
    cmd += encode_args(enc, quality_mode, quality_value, preset, threads, info)
    cmd += ["-movflags", "+faststart"]
    if info["has_audio"]:
        cmd += ["-map", "0:a", "-c:a", "copy"]
    cmd += [str(output_path)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    run(cmd, dry_run=dry_run)
    if not dry_run:
        print_info(output_path)
        print(f"[XONG] Ghép sticker {Path(sticker_path).name}: {output_path}")
    return output_path


def main():
    p = argparse.ArgumentParser(description="4. Ghép 1 sticker vào video riêng lẻ")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--sticker", required=True, help="File sticker PNG trong suốt")
    p.add_argument("--scale", type=float, default=0.15)
    p.add_argument("--position", default="bottom-right", choices=list(POSITIONS))
    p.add_argument("--sticker-left", "--left", dest="sticker_left", type=float, default=0)
    p.add_argument("--sticker-right", "--right", dest="sticker_right", type=float, default=0)
    p.add_argument("--sticker-top", "--top", dest="sticker_top", type=float, default=0)
    p.add_argument("--sticker-bottom", "--bottom", dest="sticker_bottom", type=float, default=0)
    p.add_argument("--encoder", default="auto")
    p.add_argument("--quality-mode", default="source",
                   choices=["source", "bitrate", "crf"])
    p.add_argument("--quality-value", default="")
    p.add_argument("--preset", default=None)
    p.add_argument("--threads", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    sticker_overlay(Path(a.input), Path(a.output), Path(a.sticker), a.scale,
                    a.position, a.sticker_left, a.sticker_right,
                    a.sticker_top, a.sticker_bottom,
                    a.encoder, a.quality_mode, a.quality_value,
                    a.preset, a.threads, a.dry_run)


if __name__ == "__main__":
    main()
