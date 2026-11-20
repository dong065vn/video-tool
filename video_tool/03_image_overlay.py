#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03_image_overlay.py — CHỨC NĂNG RIÊNG 3: Ghép 1 ảnh vào video
=============================================================
CHỈ ghép 1 ảnh lên video (ảnh được loop theo độ dài video), không làm gì khác.
Xuất H.264 .mp4, encoder tự chọn theo GPU.

Chế độ ghép (--mode, chỉ khi không dùng khung 9:16):
  - corner : ảnh nhỏ góc phải dưới, rộng 25% video (mặc định).
  - full   : ảnh phủ toàn màn hình (có chỉnh độ mờ --opacity).
  - banner : ảnh làm banner ngang phía trên, cao 25% video.

Khung 9:16 (--frame-916): ra video 1080x1920, ảnh làm nền lấp đầy khung,
video phủ lên trên ở giữa với tỉ lệ --video-scale (mặc định 0.94).

Chạy độc lập:
    python 03_image_overlay.py -i video.mp4 -o out.mp4 --image anh.jpg
    python 03_image_overlay.py -i video.mp4 -o out.mp4 --image anh.jpg --mode full --opacity 0.6
    python 03_image_overlay.py -i video.mp4 -o out.mp4 --image anh.jpg --frame-916
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (build_916_filter_graph, check_ffmpeg, encode_args,
                    print_info, run, validate_params)
from gpu_detect import detect_gpu


def image_overlay(input_path: Path, output_path: Path, image_path: Path,
                  mode="corner", opacity=0.85,
                  frame_916=False, video_scale=0.94, video_position="center",
                  video_left=0, video_right=0, video_top=0, video_bottom=0,
                  encoder="auto", quality_mode="source", quality_value="",
                  preset=None, threads=None, dry_run=False) -> Path:
    """Chỉ ghép 1 ảnh vào video, xuất H.264 .mp4."""
    check_ffmpeg()
    validate_params(image_opacity=opacity, video_scale=video_scale,
                    quality_mode=quality_mode, quality_value=quality_value,
                    video_left=video_left, video_right=video_right,
                    video_top=video_top, video_bottom=video_bottom)
    info = print_info(input_path)
    if not Path(image_path).exists():
        raise FileNotFoundError(f"Không thấy file ảnh: {image_path}")

    det = detect_gpu() if encoder == "auto" else None
    enc = det["encoder"] if det else encoder
    preset = preset or (det["preset"] if det else "medium")
    threads = threads or (det["threads"] if det else 4)
    w, h = info["width"], info["height"]
    fps = info["fps"] or 30.0
    dur = info["duration"] or 0
    print(f"[INFO] Encoder: {enc} (preset {preset}) | Ảnh: {Path(image_path).name} "
          f"({'khung 9:16' if frame_916 else mode})")

    if frame_916:
        fc, vlabel, alabel = build_916_filter_graph(
            info, mirror=False, speed=1.0,
            video_scale=video_scale, video_position=video_position,
            video_left=video_left, video_right=video_right,
            video_top=video_top, video_bottom=video_bottom,
            encoder=enc)
        cmd = ["ffmpeg", "-y",
               "-i", str(input_path),
               "-loop", "1", "-framerate", f"{fps:.2f}", "-t", f"{dur:.3f}",
               "-i", str(image_path),
               "-filter_complex", fc, "-map", vlabel]
        cmd += encode_args(enc, quality_mode, quality_value, preset, threads, info)
        cmd += ["-movflags", "+faststart"]
        if info["has_audio"]:
            cmd += ["-map", "0:a", "-c:a", "copy"]
        cmd += [str(output_path)]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        run(cmd, dry_run=dry_run)
        if not dry_run:
            print_info(output_path)
            print(f"[XONG] Khung 9:16 + ảnh {Path(image_path).name}: {output_path}")
        return output_path

    if mode == "full":
        scale, x, y = f"scale={w}:{h}", "0", "0"
    elif mode == "banner":
        scale, x, y = f"scale={w}:{max(2, h // 4)}", "0", "0"
    else:
        scale, x, y = f"scale={max(2, w // 4)}:-2", "W-w-20", "H-h-20"
    fc = (f"[0:v]format=yuv420p[v0];"
          f"[1:v]{scale},format=rgba,colorchannelmixer=aa={opacity}[img];"
          f"[v0][img]overlay={x}:{y}[vout]")
    if enc == "h264_vaapi":
        fc = fc.replace("[0:v]format=yuv420p[v0]",
                        "[0:v]format=nv12,hwupload[v0]")

    # -t giới hạn input ảnh loop: nếu không, ảnh loop vô hạn làm ffmpeg
    # encode mãi không dừng (đã gặp: file ra phình to vô hạn).
    cmd = ["ffmpeg", "-y",
           "-i", str(input_path),
           "-loop", "1", "-framerate", f"{fps:.2f}", "-t", f"{dur:.3f}",
           "-i", str(image_path),
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
        print(f"[XONG] Ghép ảnh {Path(image_path).name}: {output_path}")
    return output_path


def main():
    p = argparse.ArgumentParser(description="3. Ghép 1 ảnh vào video riêng lẻ")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--image", required=True, help="File ảnh ghép vào video")
    p.add_argument("--mode", default="corner", choices=["corner", "full", "banner"])
    p.add_argument("--opacity", type=float, default=0.85)
    p.add_argument("--frame-916", action="store_true",
                   help="Khung 9:16: ảnh làm nền 1080x1920, video phủ lên ở giữa")
    p.add_argument("--video-scale", type=float, default=0.94)
    p.add_argument("--video-position", default="center",
                   choices=["center", "top", "bottom", "left", "right",
                            "top-left", "top-right", "bottom-left", "bottom-right"])
    p.add_argument("--video-left", type=float, default=0)
    p.add_argument("--video-right", type=float, default=0)
    p.add_argument("--video-top", type=float, default=0)
    p.add_argument("--video-bottom", type=float, default=0)
    p.add_argument("--encoder", default="auto")
    p.add_argument("--quality-mode", default="source",
                   choices=["source", "bitrate", "crf"])
    p.add_argument("--quality-value", default="")
    p.add_argument("--preset", default=None)
    p.add_argument("--threads", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    image_overlay(Path(a.input), Path(a.output), Path(a.image), a.mode,
                  a.opacity, a.frame_916, a.video_scale, a.video_position,
                  a.video_left, a.video_right, a.video_top, a.video_bottom,
                  a.encoder, a.quality_mode, a.quality_value,
                  a.preset, a.threads, a.dry_run)


if __name__ == "__main__":
    main()
