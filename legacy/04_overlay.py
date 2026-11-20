#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
04_overlay.py — CHỨC NĂNG RIÊNG 2c: Dynamic Overlay
====================================================
CHỈ chèn lớp phủ động, không crop / flip / đổi FPS / đổi màu / đổi audio.
Audio giữ nguyên (-c:a copy).

Gồm:
- border: khung viền đỏ + thanh vàng chạy ngang mép trên
- clock: đồng hồ giờ thực (dạng 15-47-42) + chữ LIVE
- voucher: chữ voucher nhấp nháy (hiện 1.2s / mờ 0.8s)
- countdown: đếm ngược theo phút
- all: tất cả các lớp trên

Chạy độc lập:
    python 04_overlay.py -i input.mp4 -o output.mp4 --overlay all
    python 04_overlay.py -i input.mp4 -o output.mp4 --overlay voucher --voucher "GIAM 50% - FREESHIP"
    python 04_overlay.py -i input.mp4 -o output.mp4 --overlay clock
    python 04_overlay.py -i input.mp4 -o output.mp4 --overlay all --countdown 120
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import check_ffmpeg, find_font, print_info, run


def escape_drawtext(text: str) -> str:
    # Dùng với expansion=none: chỉ escape \, :, '. Không escape % (đã test).
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def build_overlay_filters(mode, voucher, countdown_min, font_path):
    filters = []
    has_font = font_path is not None

    def dt(text, x, y, fontsize=48, fontcolor="white",
           box=1, boxcolor="black@0.6", boxborderw=12, extra=""):
        if not has_font:
            return None
        f = (f"drawtext=fontfile={font_path}:text='{escape_drawtext(text)}'"
             f":expansion=none"
             f":x={x}:y={y}:fontsize={fontsize}:fontcolor={fontcolor}"
             f":box={box}:boxcolor={boxcolor}:boxborderw={boxborderw}")
        if extra:
            f += f":{extra}"
        return f

    if mode in ("border", "all"):
        filters.append("drawbox=x=0:y=0:w=iw:h=6:color=red@0.9:t=fill")
        filters.append("drawbox=x=0:y=ih-6:w=iw:h=6:color=red@0.9:t=fill")
        filters.append("drawbox=x=0:y=0:w=6:h=ih:color=red@0.9:t=fill")
        filters.append("drawbox=x=iw-6:y=0:w=6:h=ih:color=red@0.9:t=fill")
        filters.append("drawbox=x='mod(t*120\\,iw)':y=0:w=120:h=6:color=yellow@0.95:t=fill")

    if mode in ("clock", "all") and has_font:
        clock_f = (
            "drawtext=fontfile=" + font_path
            + ":text='%{localtime\\:%H-%M-%S}'"
            + ":x=(w-text_w-20):y=20:fontsize=42:fontcolor=yellow"
            + ":box=1:boxcolor=black@0.6:boxborderw=12"
        )
        filters.append(clock_f)
        f2 = dt("LIVE", "20", "20", fontsize=42, fontcolor="red",
                boxcolor="white@0.85")
        if f2:
            filters.append(f2)

    if countdown_min > 0 and has_font:
        total_sec = countdown_min * 60
        eif_part = "%{eif\\:" + str(total_sec) + "-t\\:d}"
        expr = (
            "drawtext=fontfile=" + font_path
            + ":text='Con lai " + eif_part + " giay'"
            + ":x=(w-text_w)/2:y=20:fontsize=40:fontcolor=white"
            + ":box=1:boxcolor=black@0.6:boxborderw=10"
        )
        filters.append(expr)

    if mode in ("voucher", "all") and voucher and has_font:
        f = dt(voucher, "(w-text_w)/2", "h-th-90",
               fontsize=56, fontcolor="yellow", boxcolor="red@0.85", boxborderw=16,
               extra="enable='lt(mod(t\\,2)\\,1.2)'")
        if f:
            filters.append(f)
        f2 = dt(voucher, "(w-text_w)/2", "h-th-90",
                fontsize=56, fontcolor="white", boxcolor="black@0.55", boxborderw=16,
                extra="enable='gte(mod(t\\,2)\\,1.2)'")
        if f2:
            filters.append(f2)

    return [f for f in filters if f]


def overlay(input_path: Path, output_path: Path,
            mode="all", voucher="GIAM 50% - FREESHIP", countdown=0,
            crf=20, preset="medium", dry_run=False) -> Path:
    """Chỉ overlay động."""
    check_ffmpeg()
    print_info(input_path)
    font_path = find_font()
    if font_path:
        print(f"[INFO] Font drawtext: {font_path}")
    else:
        print("[CẢNH BÁO] Không tìm thấy font — overlay chữ sẽ bị bỏ, chỉ còn drawbox.")

    vf = ",".join(build_overlay_filters(mode, voucher, countdown, font_path))
    if not vf:
        raise RuntimeError("Không có filter overlay nào được tạo. Kiểm tra --overlay và font.")

    cmd = ["ffmpeg", "-y", "-i", str(input_path),
           "-vf", vf + ",format=yuv420p",
           "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
           "-pix_fmt", "yuv420p",
           "-c:a", "copy",
           str(output_path)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    run(cmd, dry_run=dry_run)
    if not dry_run:
        print_info(output_path)
        print(f"[XONG] Overlay ({mode}): {output_path}")
    return output_path


def main():
    p = argparse.ArgumentParser(description="2c. Dynamic Overlay riêng lẻ (audio giữ nguyên)")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--overlay", choices=["clock", "voucher", "border", "all"],
                   default="all")
    p.add_argument("--voucher", default="GIAM 50% - FREESHIP")
    p.add_argument("--countdown", type=int, default=0, help="Đếm ngược (phút), 0=tắt")
    p.add_argument("--crf", type=int, default=20)
    p.add_argument("--preset", default="medium")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    overlay(Path(a.input), Path(a.output), a.overlay, a.voucher,
            a.countdown, a.crf, a.preset, a.dry_run)


if __name__ == "__main__":
    main()
