#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
06_chunk.py — CHỨC NĂNG RIÊNG 6: Xử lý video dài theo từng đoạn rồi ghép lại
=============================================================================
Dành cho video dài (< 3GB, 1 tiếng trở lên). Quy trình 3 bước:

  1. CẮT ĐOẠN: ffmpeg -f segment -c copy cắt video gốc thành từng đoạn
     (mặc định 300s/đoạn, cắt tại keyframe nên đoạn thực tế dài hơn
     1 chút). Bước này chỉ copy, không encode lại nên rất nhanh.
  2. XỬ LÝ TỪNG ĐOẠN: mỗi đoạn được xử lý như 1 video riêng bằng đúng
     hàm process_one_video của 05_batch.py (mirror -> speed -> ảnh ->
     sticker -> H.264 .mp4, khung 9:16 nếu bật) nên chất lượng và bố cục
     giống hệt đường xử lý 1 lần. Đoạn nào đã xử lý xong rồi thì BỎ QUA
     (tiếp tục dở dang) — hỏng giữa chừng chỉ làm lại đúng đoạn đó.
  3. GHÉP LẠI: ffmpeg concat (copy, không encode lại) nối các đoạn đã
     xử lý thành video hoàn chỉnh, +faststart để mở nhanh.

Thư mục làm việc: <thư mục ra>/<tên video>_chunks/ — chứa các đoạn gốc
(segNNN.mp4), các đoạn đã xử lý (segNNN_done.mp4) và file concat.txt.
Ghép xong thì tự xóa (trừ khi --keep-chunks). Muốn làm lại từ đầu thì
tắt resume (hoặc xóa thư mục _chunks rồi chạy lại).

LƯU Ý Ổ ĐĨA: lúc đang làm, tool cần chỗ trống khoảng 2 lần dung lượng
video gốc (đoạn gốc + đoạn đã xử lý + file hoàn chỉnh). Ghép xong thì
đoạn tạm bị xóa, chỉ còn file hoàn chỉnh.

Chạy độc lập (1 video dài):
    python 06_chunk.py --video video_dai.mp4 -o video_dai_done.mp4 --images ./anh --stickers ./sticker
    python 06_chunk.py --video video_dai.mp4 -o video_dai_done.mp4 --chunk-seconds 600 --no-resume
    python 06_chunk.py --video video_dai.mp4 -o video_dai_done.mp4 --keep-chunks --dry-run
"""
import argparse
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (check_ffmpeg, get_info, print_info,
                    run, validate_params)

BASE = Path(__file__).parent


def load_tool(filename: str, func_name: str):
    """Nạp 1 file tool theo đường dẫn (tên file bắt đầu bằng số nên phải
    dùng importlib thay vì import thường)."""
    path = BASE / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return getattr(mod, func_name)


def split_video(video, segment_seconds, work_dir, log=print):
    """
    Cắt video gốc thành từng đoạn bằng segment muxer (copy, không encode).
    Cắt tại keyframe nên đoạn thực tế có thể dài hơn segment_seconds 1 chút.
    Trả về list Path các đoạn theo thứ tự. Xóa đoạn gốc cũ trước khi cắt.
    """
    check_ffmpeg()
    video, work_dir = Path(video), Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    # Chỉ xóa đoạn GỐC cũ (segNNN.mp4), giữ lại đoạn ĐÃ XỬ LÝ (segNNN_done.mp4)
    # để lần chạy sau vẫn tiếp tục được.
    for old in work_dir.glob("seg*.mp4"):
        if not old.name.endswith("_done.mp4"):
            old.unlink(missing_ok=True)
    pattern = work_dir / "seg%03d.mp4"
    cmd = ["ffmpeg", "-y", "-i", str(video),
           "-f", "segment", "-segment_time", str(int(segment_seconds)),
           "-segment_format", "mp4", "-reset_timestamps", "1",
           "-c", "copy", "-map", "0", str(pattern)]
    log(f"[CHUNK] Cắt {video.name} thành đoạn {int(segment_seconds)}s (copy, không encode)...")
    run(cmd, dry_run=False, log=log)
    segs = sorted(work_dir.glob("seg*.mp4"))
    segs = [s for s in segs if not s.name.endswith("_done.mp4")]
    if not segs:
        raise RuntimeError(f"Không cắt được đoạn nào từ {video.name}.")
    for s in segs:
        si = get_info(s)
        log(f"[CHUNK]   {s.name}: {si['duration']:.1f}s")
    return segs


def process_video_chunked(video, img, stk, out,
                          mirror=True, speed=1.2,
                          image_on=True, image_mode="corner", image_opacity=0.85,
                          sticker_on=True, sticker_scale=0.15,
                          sticker_position="bottom-right",
                          sticker_left=0, sticker_right=0,
                          sticker_top=0, sticker_bottom=0,
                          frame_916=True, video_scale=0.94, video_position="center",
                          video_left=0, video_right=0,
                          video_top=0, video_bottom=0,
                          enc="libx264", quality_mode="source", quality_value="",
                          preset="medium", threads=4,
                          chunk_seconds=300, resume=True, keep_chunks=False,
                          dry_run=False, log=print, info=None, progress=None,
                          process_one=None):
    """
    Xử lý 1 video dài theo từng đoạn rồi ghép lại thành video hoàn chỉnh.
    img/stk là Path hoặc None. out là file mp4 hoàn chỉnh.
    Trả về đường dẫn file output.
    """
    check_ffmpeg()
    validate_params(speed=speed, video_scale=video_scale,
                    image_opacity=image_opacity, sticker_scale=sticker_scale,
                    quality_mode=quality_mode, quality_value=quality_value,
                    chunk_seconds=chunk_seconds,
                    video_left=video_left, video_right=video_right,
                    video_top=video_top, video_bottom=video_bottom,
                    sticker_left=sticker_left, sticker_right=sticker_right,
                    sticker_top=sticker_top, sticker_bottom=sticker_bottom)
    video, out = Path(video), Path(out)
    if info is None:
        info = print_info(video, log=log)
    # info đã có sẵn thì nơi gọi (05_batch.py) đã ghi dòng [INFO].
    # Tự quét GPU khi encoder còn là "auto" (VD: gọi qua video_processor
    # chunk mà không quét trước) — nếu không, encode_args sẽ rơi về
    # nhánh dự phòng và bỏ qua bitrate đã chọn.
    if enc == "auto":
        from gpu_detect import detect_gpu
        det = detect_gpu() if not dry_run else None
        enc = det["encoder"] if det else "libx264"
        preset = preset or (det["preset"] if det else "medium")
        threads = threads or (det["threads"] if det else 4)
        log(f"[GPU] {det['gpu'] if det else '(dry-run, chưa quét)'} | Encoder: {enc} "
            f"(preset {preset}, threads {threads})")
    total_out = (info["duration"] or 0) / speed if speed else (info["duration"] or 0)
    log(f"[CHUNK] {video.name}: gốc {info['duration']:.1f}s "
        f"({info['duration']/60:.1f} phút) -> ra ~{total_out:.0f}s "
        f"({total_out/60:.1f} phút), chia đoạn {int(chunk_seconds)}s.")
    if dry_run:
        log(f"(dry-run) Sẽ chia {video.name} thành đoạn {int(chunk_seconds)}s, "
            f"xử lý từng đoạn rồi ghép lại -> {out.name}")
        return out

    work_dir = out.parent / f"{out.stem}_chunks"
    work_dir.mkdir(parents=True, exist_ok=True)

    # --- Bước 1: cắt đoạn (nhanh, copy) ---
    segs = split_video(video, chunk_seconds, work_dir, log=log)
    if progress:
        progress(3)
    log(f"[CHUNK] Có {len(segs)} đoạn, xử lý từng đoạn...")

    # --- Bước 2: xử lý từng đoạn (đoạn xong rồi thì bỏ qua khi resume) ---
    process_one = process_one or load_tool("05_batch.py", "process_one_video")
    seg_outs = []
    for i, seg in enumerate(segs, start=1):
        seg_out = work_dir / f"{seg.stem}_done.mp4"
        if resume and seg_out.exists() and seg_out.stat().st_size > 0:
            try:
                si = get_info(seg_out)
                if si["duration"] > 0:
                    log(f"[CHUNK] Đoạn {i}/{len(segs)} đã có ({seg_out.name}, "
                        f"{si['duration']:.1f}s) — bỏ qua, không làm lại.")
                    seg_outs.append(seg_out)
                    if progress:
                        progress(3 + int(i / len(segs) * 94))
                    continue
            except Exception:
                pass  # File đoạn hỏng thì xử lý lại
        log(f"[CHUNK] --- Đoạn {i}/{len(segs)}: {seg.name} ---")
        seg_info = print_info(seg, log=log)
        # Giữ bitrate mục tiêu của video gốc cho từng đoạn: đoạn nhiều cảnh tĩnh
        # hoặc không đọc được stream bit_rate sẽ không bị tụt bitrate xuống thấp.
        if info.get("bitrate"):
            seg_info["bitrate"] = info["bitrate"]
        segment_progress = None
        if progress:
            segment_progress = lambda pct, n=i: progress(
                3 + int(((n - 1) + pct / 100) / len(segs) * 94)
            )
        process_one(seg, img, stk, seg_out,
                    mirror=mirror, speed=speed,
                    image_on=image_on, image_mode=image_mode,
                    image_opacity=image_opacity,
                    sticker_on=sticker_on, sticker_scale=sticker_scale,
                    sticker_position=sticker_position,
                    sticker_left=sticker_left, sticker_right=sticker_right,
                    sticker_top=sticker_top, sticker_bottom=sticker_bottom,
                    frame_916=frame_916, video_scale=video_scale,
                    video_position=video_position,
                    video_left=video_left, video_right=video_right,
                    video_top=video_top, video_bottom=video_bottom,
                    enc=enc, quality_mode=quality_mode,
                    quality_value=quality_value,
                    preset=preset, threads=threads, info=seg_info, log=log,
                    progress=segment_progress)
        seg_outs.append(seg_out)

    # --- Bước 3: ghép lại (concat copy, không encode lại) ---
    list_path = work_dir / "concat.txt"
    lines = []
    for p in seg_outs:
        # Đường dẫn tuyệt đối, dấu / để chạy được cả trên Windows
        ap = str(p.resolve()).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{ap}'\n")
    list_path.write_text("".join(lines), encoding="utf-8")
    log(f"[CHUNK] Ghép {len(seg_outs)} đoạn lại (concat, không encode lại)...")
    if progress:
        progress(98)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
           "-i", str(list_path), "-c", "copy",
           "-movflags", "+faststart", str(out)]
    run(cmd, dry_run=False, log=log)
    print_info(out, log=log)

    # --- Dọn đoạn tạm ---
    if not keep_chunks:
        for p in work_dir.glob("seg*.mp4"):
            p.unlink(missing_ok=True)
        list_path.unlink(missing_ok=True)
        try:
            work_dir.rmdir()
        except OSError:
            pass
        log(f"[CHUNK] Đã xóa thư mục đoạn tạm {work_dir.name}/.")
    else:
        log(f"[CHUNK] Giữ lại thư mục đoạn tạm: {work_dir}")
    if progress:
        progress(100)
    log(f"[XONG] Ghép xong {len(seg_outs)} đoạn -> {out} ({out.stat().st_size/1024:.0f} KB)")
    return out


def main():
    p = argparse.ArgumentParser(description="6. Xử lý 1 video dài theo từng đoạn rồi ghép lại")
    p.add_argument("--video", required=True, help="1 file video dài")
    p.add_argument("-o", "--output", required=True, help="File mp4 hoàn chỉnh")
    p.add_argument("--images", default="", help="Thư mục chứa ảnh ghép (lấy ảnh đầu tiên)")
    p.add_argument("--stickers", default="", help="Thư mục chứa sticker (lấy sticker đầu tiên)")
    p.add_argument("--no-mirror", dest="mirror", action="store_false")
    p.add_argument("--mirror", dest="mirror", action="store_true")
    p.add_argument("--speed", type=float, default=1.2)
    p.add_argument("--no-image", dest="image_on", action="store_false")
    p.add_argument("--image-on", dest="image_on", action="store_true")
    p.add_argument("--image-mode", default="corner", choices=["corner", "full", "banner"])
    p.add_argument("--image-opacity", type=float, default=0.85)
    p.add_argument("--no-sticker", dest="sticker_on", action="store_false")
    p.add_argument("--sticker-on", dest="sticker_on", action="store_true")
    p.add_argument("--sticker-scale", type=float, default=0.15)
    p.add_argument("--sticker-position", default="auto-corners",
                   choices=["auto-corners", "bottom-right", "top-right", "bottom-left", "top-left",
                            "center", "top", "bottom", "left", "right"])
    p.add_argument("--sticker-left", type=float, default=0)
    p.add_argument("--sticker-right", type=float, default=0)
    p.add_argument("--sticker-top", type=float, default=0)
    p.add_argument("--sticker-bottom", type=float, default=0)
    p.add_argument("--no-frame-916", dest="frame_916", action="store_false")
    p.add_argument("--frame-916", dest="frame_916", action="store_true")
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
    p.add_argument("--chunk-seconds", type=int, default=300)
    p.add_argument("--no-resume", dest="resume", action="store_false")
    p.add_argument("--resume", dest="resume", action="store_true")
    p.add_argument("--keep-chunks", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(mirror=True, image_on=True, sticker_on=True, frame_916=True,
                   resume=True)
    a = p.parse_args()

    from common import IMAGE_EXTS, STICKER_EXTS, list_files
    from gpu_detect import detect_gpu
    img = None
    if a.images:
        imgs = list_files(a.images, IMAGE_EXTS)
        img = imgs[0] if imgs else None
    stk = None
    if a.stickers:
        stks = list_files(a.stickers, STICKER_EXTS)
        stk = stks[0] if stks else None
    det = detect_gpu() if (a.encoder == "auto" and not a.dry_run) else None
    enc = det["encoder"] if det else (a.encoder if a.encoder != "auto" else "libx264")
    preset = a.preset or (det["preset"] if det else "medium")
    threads = a.threads or (det["threads"] if det else 4)
    process_video_chunked(
        Path(a.video), img, stk, Path(a.output),
        mirror=a.mirror, speed=a.speed,
        image_on=a.image_on, image_mode=a.image_mode, image_opacity=a.image_opacity,
        sticker_on=a.sticker_on, sticker_scale=a.sticker_scale,
        sticker_position=a.sticker_position,
        sticker_left=a.sticker_left, sticker_right=a.sticker_right,
        sticker_top=a.sticker_top, sticker_bottom=a.sticker_bottom,
        frame_916=a.frame_916, video_scale=a.video_scale,
        video_position=a.video_position,
        video_left=a.video_left, video_right=a.video_right,
        video_top=a.video_top, video_bottom=a.video_bottom,
        enc=enc, quality_mode=a.quality_mode, quality_value=a.quality_value,
        preset=preset, threads=threads,
        chunk_seconds=a.chunk_seconds, resume=a.resume,
        keep_chunks=a.keep_chunks, dry_run=a.dry_run)


if __name__ == "__main__":
    main()
