#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
05_batch.py — CHỨC NĂNG RIÊNG 5: Xử lý hàng loạt theo folder (ghép lần lượt)
=============================================================================
Đọc 3 folder, ghép lần lượt từng video với 1 ảnh khác nhau + 1 sticker khác
nhau theo thứ tự tên file, rồi xử lý MỖI VIDEO TRONG 1 LẦN ENCODE DUY NHẤT:
mirror -> tăng speed -> ghép ảnh -> ghép sticker -> xuất H.264 .mp4.
Encode 1 lần giữ chất lượng tốt nhất (không encode lại nhiều lần).

VIDEO DÀI (mặc định BẬT --chunk): video dài hơn 1 đoạn sẽ được xử lý theo
từng đoạn rồi ghép lại (xem 06_chunk.py): cắt video gốc thành từng đoạn
(không encode lại), xử lý từng đoạn như 1 video riêng, rồi ghép các đoạn
đã xử lý lại bằng concat (copy, không encode lại). Lợi ích cho video dài
(< 3GB, 1 tiếng trở lên): hỏng giữa chừng chỉ làm lại đúng đoạn đó (mở lại
tool chạy tiếp, đoạn xong rồi sẽ tự bỏ qua), không mất cả tiếng encode.
Video ngắn hơn 1 đoạn thì vẫn xử lý 1 lần như cũ.

KHUNG 9:16 MẶC ĐỊNH BẬT (--frame-916): video thành phẩm ra 1080x1920,
ảnh làm nền lấp đầy khung, video phủ lên trên ở giữa với tỉ lệ 94%
(như Scale 94% trong ảnh mẫu), sticker phủ lên trên cùng. Không có ảnh
thì nền đen. Tắt bằng --no-frame-916 để về kiểu cũ (giữ nguyên kích thước
video, ảnh ghép góc/phủ/banner lên video).

CẮT KHOẢNG IM (mặc định TẮT ở CLI, BẬT ở GUI — xem 09_silence.py):
mỗi video được quét khoảng im trước khi xử lý chính; các mốc cắt được
căn vào timestamp frame thật rồi cắt hình và tiếng cùng mốc. Có khoảng
im đủ dài thì cắt ra file tạm rồi xử lý chính trên file đó. Phanh an
toàn mặc định bật khi cắt im: giới hạn tổng thời lượng cắt và giữ nguyên
video thu quá nhỏ. Không có audio / không có khoảng nào đủ dài / lỗi
quét thì dùng file gốc, không làm hỏng cả batch.

VỀ ĐỘ DÀI VIDEO RA (đã kiểm chứng 2026-11-18): độ dài video ra =
thời lượng gốc / speed (VD: 60 phút, speed 1.2x -> 50 phút). Chế độ
bitrate KHÔNG cắt ngắn video — bitrate chỉ đổi chất lượng/dung lượng.
Nếu video ra ngắn hơn hẳn dự kiến thì kiểm tra lại speed ở BOX 2
(VD: speed 3x thì 60 phút chỉ còn 20 phút — đó là đúng, không phải lỗi)
và dòng [INFO] thời lượng gốc trong log.

- Video folder: .mp4/.mov/.mkv/.avi/.webm (KHÔNG nhận .flv — đã bỏ convert FLV,
  file .flv sẽ bị bỏ qua kèm cảnh báo).
- Ảnh folder: .jpg/.png/.webp — video 1 <-> ảnh 1, video 2 <-> ảnh 2...
  Ít ảnh hơn video thì lặp lại từ đầu.
- Sticker folder: .png/.webp (cần kênh alpha) — ghép lần lượt tương tự.
- Ghép cặp: --pair order (theo tên file) hoặc shuffle (xáo trộn).

Chạy độc lập:
    python 05_batch.py --videos ./videos --images ./anh --stickers ./sticker -o ./out/
    python 05_batch.py --videos ./videos --images ./anh -o ./out/ --no-mirror --speed 1.10
    python 05_batch.py --video mot_video.mp4 --images ./anh --stickers ./sticker -o ./out/
    python 05_batch.py --videos ./videos -o ./out/ --no-frame-916
    python 05_batch.py --video video_dai.mp4 -o ./out/ --chunk-seconds 300
    python 05_batch.py --videos ./videos -o ./out/ --no-chunk
"""
import argparse
import importlib.util
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (FRAME_916_H, FRAME_916_W, IMAGE_EXTS, STICKER_EXTS,
                    VIDEO_EXTS, build_916_filter_graph, build_filter_graph,
                    check_ffmpeg, encode_args, list_files, pair_files,
                    print_info, resolve_sticker_position, run, validate_params)
from gpu_detect import detect_gpu, machine_info

BASE = Path(__file__).parent


def load_tool(filename: str, func_name: str):
    """Nạp 1 file tool theo đường dẫn (tên file bắt đầu bằng số nên phải
    dùng importlib thay vì import thường). Dùng để gọi 06_chunk.py mà
    không tạo vòng import lẫn nhau với 05_batch.py."""
    path = BASE / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return getattr(mod, func_name)


def _maybe_cut_silence(video, out_dir, sil_kw, enc, quality_mode,
                       quality_value, preset, threads, log, tools=None):
    """Cắt khoảng lặng trước khi render; lỗi thì giữ nguyên nguồn."""
    try:
        if tools is None:
            tools = (
                load_tool("09_silence.py", "scan_silences"),
                load_tool("09_silence.py", "format_scan"),
                load_tool("09_silence.py", "remove_silence"),
            )
        scan_fn, fmt_fn, cut_fn = tools
        scan = scan_fn(video, **sil_kw)
        log(fmt_fn(scan))
        if not scan["cuts"]:
            log(f"[IM] {Path(video).name}: không cắt khoảng lặng — giữ nguyên file gốc.")
            return None, scan
        tmp = Path(out_dir) / f".{Path(video).stem}_catlang_tmp.mp4"
        cut_fn(video, tmp, encoder=enc, quality_mode=quality_mode,
               quality_value=quality_value, preset=preset, threads=threads,
               log=log, scan=scan, **sil_kw)
        return tmp, scan
    except Exception as e:
        log(f"[IM] {Path(video).name}: không cắt được khoảng lặng ({e}) — xử lý bằng file gốc.")
        return None, None


def process_one_video(video, img, stk, out,
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
                      preset="medium", threads=4, dry_run=False, log=print,
                      info=None, progress=None):
    """
    Xử lý 1 video (hoặc 1 đoạn video) trong 1 lần encode duy nhất:
    mirror -> speed -> ảnh -> sticker -> H.264 .mp4.
    Hàm dùng chung cho cả đường xử lý 1 lần (video ngắn) và đường chia
    đoạn (06_chunk.py gọi lại cho từng đoạn), để 2 đường luôn cho ra
    cùng 1 chất lượng/bố cục.
    Trả về đường dẫn file output.
    """
    video, out = Path(video), Path(out)
    if info is None:
        info = print_info(video, log=log)
    # info đã có sẵn thì nơi gọi đã ghi dòng [INFO].
    fps = info["fps"] or 30.0
    # Độ dài video sau khi tăng speed (dùng để giới hạn input loop).
    # LƯU Ý: -t dưới đây chỉ giới hạn ảnh/sticker/nền loop (input phụ),
    # nó KHÔNG cắt ngắn video chính — video ra dài bao nhiêu là do
    # chính các frame video sau khi tăng speed quyết định. Đã kiểm chứng:
    # nền -t=10s mà video 30s thì video ra vẫn đủ 25s (speed 1.2x).
    # Độ dài ra luôn = thời lượng gốc / speed, bitrate không làm đổi nó.
    out_dur = (info["duration"] or 0) / speed if speed else (info["duration"] or 0)
    log(f"[INFO] Dự kiến ra: {out_dur:.0f}s ({out_dur/60:.1f} phút) = "
        f"gốc {info['duration']:.1f}s / speed {speed}x.")
    if dry_run:
        log(f"(dry-run) Sẽ xử lý {video.name} -> {out.name}")
        return out

    cmd = ["ffmpeg", "-y", "-i", str(video)]
    # -t giới hạn input loop: ảnh/sticker loop vô hạn sẽ làm ffmpeg
    # encode mãi không dừng (đã gặp: file ra phình to vô hạn, và đã thử
    # bỏ -t + eof_action=endall thì vẫn chạy vô hạn vì input sticker
    # loop không bao giờ hết — nên -t là bắt buộc, không được bỏ).
    if frame_916:
        fc, vlabel, alabel = build_916_filter_graph(
            info, mirror=mirror, speed=speed,
            sticker=stk if sticker_on else None, sticker_scale=sticker_scale,
            sticker_position=sticker_position,
            sticker_left=sticker_left, sticker_right=sticker_right,
            sticker_top=sticker_top, sticker_bottom=sticker_bottom,
            video_scale=video_scale, video_position=video_position,
            video_left=video_left, video_right=video_right,
            video_top=video_top, video_bottom=video_bottom,
            encoder=enc)
        # Input [1] luôn là nền: ảnh thật, hoặc màu đen nếu không có ảnh
        if image_on and img is not None:
            cmd += ["-loop", "1", "-framerate", f"{fps:.2f}",
                    "-t", f"{out_dur:.3f}", "-i", str(img)]
        else:
            cmd += ["-f", "lavfi", "-t", f"{out_dur:.3f}",
                    "-i", f"color=c=black:s={FRAME_916_W}x{FRAME_916_H}:r={fps:.2f}"]
        if sticker_on and stk is not None:
            cmd += ["-loop", "1", "-framerate", f"{fps:.2f}",
                    "-t", f"{out_dur:.3f}", "-i", str(stk)]
    else:
        fc, vlabel, alabel = build_filter_graph(
            info, mirror=mirror, speed=speed,
            image=img if image_on else None, image_mode=image_mode,
            image_opacity=image_opacity,
            sticker=stk if sticker_on else None, sticker_scale=sticker_scale,
            sticker_position=sticker_position,
            sticker_left=sticker_left, sticker_right=sticker_right,
            sticker_top=sticker_top, sticker_bottom=sticker_bottom,
            encoder=enc)
        if image_on and img is not None:
            cmd += ["-loop", "1", "-framerate", f"{fps:.2f}",
                    "-t", f"{out_dur:.3f}", "-i", str(img)]
        if sticker_on and stk is not None:
            cmd += ["-loop", "1", "-framerate", f"{fps:.2f}",
                    "-t", f"{out_dur:.3f}", "-i", str(stk)]
    cmd += ["-filter_complex", fc, "-map", vlabel]
    cmd += encode_args(enc, quality_mode, quality_value, preset, threads, info)
    cmd += ["-movflags", "+faststart"]
    if info["has_audio"] and alabel:
        cmd += ["-map", alabel, "-c:a", "aac", "-b:a", "128k"]
    elif info["has_audio"]:
        cmd += ["-map", "0:a", "-c:a", "copy"]
    else:
        cmd += ["-an"]
    cmd += [str(out)]

    out.parent.mkdir(parents=True, exist_ok=True)
    run(cmd, dry_run=False, log=log, progress=progress, duration=out_dur)
    print_info(out, log=log)
    log(f"[XONG] {out.name} ({out.stat().st_size/1024:.0f} KB)")
    return out


def batch(videos_dir=None, video_file=None, images_dir=None, stickers_dir=None,
          output_dir=None, pair="order", seed=0,
          mirror=True, speed=1.2,
          image_on=True, image_mode="corner", image_opacity=0.85,
          sticker_on=True, sticker_scale=0.15, sticker_position="auto-corners",
          sticker_left=0, sticker_right=0, sticker_top=0, sticker_bottom=0,
          frame_916=True, video_scale=0.94, video_position="center",
          video_left=0, video_right=0, video_top=0, video_bottom=0,
          encoder="auto", quality_mode="source", quality_value="",
          preset=None, threads=None, dry_run=False, log=print,
          chunk=True, chunk_seconds=300, resume=True, keep_chunks=False,
          silence_on=False, silence_mode="relative", silence_margin=20.0,
          silence_absolute=-40.0, silence_min_silence=0.5, silence_min_cut=1.0,
          silence_pad=0.2, silence_min_keep=0.8, silence_max_keep=5.0,
          silence_trim_ends=True, silence_safety=True,
          silence_max_cut_ratio=0.30, silence_min_peak_db=-40.0,
          workers=0, gpu_profile="auto", progress=None):
    """Xử lý hàng loạt, trả về danh sách file output."""
    check_ffmpeg()
    validate_params(speed=speed, video_scale=video_scale,
                    image_opacity=image_opacity, sticker_scale=sticker_scale,
                    quality_mode=quality_mode, quality_value=quality_value,
                    chunk_seconds=chunk_seconds,
                    video_left=video_left, video_right=video_right,
                    video_top=video_top, video_bottom=video_bottom,
                    sticker_left=sticker_left, sticker_right=sticker_right,
                    sticker_top=sticker_top, sticker_bottom=sticker_bottom)
    if output_dir is None:
        raise ValueError("Chưa chọn thư mục output.")
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Liệt kê video ---
    if video_file:
        vf = Path(video_file)
        if not vf.is_file():
            raise FileNotFoundError(f"Không tìm thấy file video: {vf}")
        if vf.suffix.lower() == ".flv":
            raise RuntimeError(f"{vf.name}: file .flv không còn được hỗ trợ (đã bỏ convert FLV).")
        videos = [vf]
    else:
        videos = list_files(videos_dir, VIDEO_EXTS)
        # Báo rõ file .flv bị bỏ qua (đã bỏ convert FLV)
        if videos_dir and Path(videos_dir).is_dir():
            flv = sorted(p for p in Path(videos_dir).iterdir()
                         if p.is_file() and p.suffix.lower() == ".flv")
            for f in flv:
                log(f"[BO QUA] {f.name}: file .flv không còn được hỗ trợ (đã bỏ convert FLV).")
    if not videos:
        raise RuntimeError("Không tìm thấy video nào (.mp4/.mov/.mkv/.avi/.webm).")
    images = list_files(images_dir, IMAGE_EXTS) if images_dir else []
    stickers = list_files(stickers_dir, STICKER_EXTS) if stickers_dir else []
    if image_on and not images and not frame_916:
        raise RuntimeError("Đã bật ghép ảnh nhưng thư mục ảnh trống.")
    if image_on and not images and frame_916:
        log("[INFO] Không có ảnh nền — khung 9:16 sẽ dùng nền đen.")
    if sticker_on and not stickers:
        raise RuntimeError("Đã bật ghép sticker nhưng thư mục sticker trống.")
    if len(images) < len(videos) and images:
        log(f"[INFO] Có {len(images)} ảnh cho {len(videos)} video — ảnh sẽ lặp lại từ đầu.")
    if len(stickers) < len(videos) and stickers:
        log(f"[INFO] Có {len(stickers)} sticker cho {len(videos)} video — sticker sẽ lặp lại từ đầu.")

    # Probe lại khi tự chọn hoặc dùng NVENC để kích hoạt đúng bản FFmpeg.
    should_detect = encoder in {"auto", "h264_nvenc"} and not dry_run
    det = detect_gpu(profile=gpu_profile) if should_detect else None
    enc = det["encoder"] if det else (encoder if encoder != "auto" else "libx264")
    preset = preset or (det["preset"] if det else "medium")
    machine = det or machine_info()
    cores = int(machine.get("cpu_cores", 4) or 4)
    requested_workers = max(0, int(workers or 0))
    if requested_workers:
        worker_count = requested_workers
    elif det:
        worker_count = int(det.get("recommended_workers", 1) or 1)
    elif enc == "h264_nvenc":
        worker_count = 2 if gpu_profile == "nvidia_legacy" else 3
    elif enc == "libx264":
        worker_count = max(1, min(4, cores // 4))
    else:
        worker_count = 2
    worker_count = max(1, min(worker_count, len(videos), 8))
    threads = threads or (det["threads"] if det else min(cores, 16))
    if enc == "libx264":
        threads = max(1, min(int(threads), max(1, cores // worker_count)))
    log(f"[GPU] {det['gpu'] if det else ('(dry-run, chưa quét)' if dry_run else encoder)} | Encoder: {enc} "
        f"(preset {preset}, {threads} threads/worker) | "
        f"FFmpeg: {det.get('ffmpeg_profile', '-') if det else '-'} | "
        f"Chất lượng: {quality_mode} {quality_value or '(bitrate gốc)'}")
    if det and det.get("detail"):
        log(f"[GPU] {det['detail']}")
    log(f"[PERF] {worker_count} worker chạy song song | CPU {cores} luồng logic | "
        f"chế độ GPU: {gpu_profile}.")
    log(f"[BATCH] {len(videos)} video | Mirror: {'BẬT' if mirror else 'TẮT'} | "
        f"Speed: {speed}x | Ảnh: {'BẬT' if image_on else 'TẮT'} | "
        f"Sticker: {'BẬT' if sticker_on else 'TẮT'} | "
        f"Khung 9:16: {'BẬT (1080x1920, video phủ ' + str(video_scale) + ')' if frame_916 else 'TẮT'} | "
        f"Chia đoạn: {'BẬT (' + str(int(chunk_seconds)) + 's/đoạn, tiếp tục dở dang)' if chunk else 'TẮT (1 lần encode/video)'}")

    # --- Cắt khoảng lặng: chuẩn bị tham số 1 lần cho cả batch ---
    # Điều kiện 2 (trần cắt tổng) + 5 (bảo vệ thu quá nhỏ) chỉ bật khi
    # phanh an toàn được tick — mặc định TẮT, để test sau.
    sil_kw = None
    if silence_on:
        sil_kw = dict(mode=silence_mode, margin_db=float(silence_margin),
                      absolute_db=float(silence_absolute),
                      min_silence=float(silence_min_silence),
                      min_cut=float(silence_min_cut), pad=float(silence_pad),
                      min_keep=float(silence_min_keep),
                      max_cut_ratio=(float(silence_max_cut_ratio)
                                     if silence_safety else 0.0),
                      max_keep_silence=float(silence_max_keep),
                      trim_ends=bool(silence_trim_ends),
                      min_peak_db=(float(silence_min_peak_db)
                                   if silence_safety else None))
        vkw = {k: v for k, v in sil_kw.items() if k != "trim_ends"}
        load_tool("09_silence.py", "validate_silence_params")(**vkw)
        cap_txt = (f"trần cắt {int(sil_kw['max_cut_ratio'] * 100)}%"
                   if silence_safety else "trần cắt TẮT")
        log(f"[IM] Cắt khoảng lặng: BẬT (chỉ cắt im > {sil_kw['min_cut']}s, "
            f"đệm {sil_kw['pad']}s, chống đảo {sil_kw['min_keep']}s, "
            f"giữ tối đa {sil_kw['max_keep_silence']}s/khoảng im, "
            f"{'cắt mạnh đầu/cuối, ' if sil_kw['trim_ends'] else ''}"
            f"{cap_txt}, "
            f"{'bảo vệ thu nhỏ BẬT' if silence_safety else 'bảo vệ thu nhỏ TẮT'})")
    else:
        log("[IM] Cắt khoảng lặng: TẮT.")

    img_pairs = pair_files(videos, images, pair, seed) if image_on else [(v, None) for v in videos]
    stk_pairs = pair_files(videos, stickers, pair, seed) if sticker_on else [(v, None) for v in videos]
    silence_tools = None
    if sil_kw is not None:
        silence_tools = (
            load_tool("09_silence.py", "scan_silences"),
            load_tool("09_silence.py", "format_scan"),
            load_tool("09_silence.py", "remove_silence"),
        )
    chunk_fn = load_tool("06_chunk.py", "process_video_chunked") if chunk else None

    progress_lock = threading.Lock()
    job_progress = {idx: 0 for idx in range(1, len(videos) + 1)}

    def emit(idx, worker_id, video, percent, status):
        percent = max(0, min(100, int(percent)))
        with progress_lock:
            job_progress[idx] = max(job_progress[idx], percent)
            overall = int(sum(job_progress.values()) / len(job_progress))
        if progress:
            progress({
                "worker": worker_id,
                "video": Path(video).name,
                "percent": percent,
                "status": status,
                "overall": overall,
                "index": idx,
                "total": len(videos),
            })

    def process_job(idx, video):
        name = threading.current_thread().name
        try:
            worker_id = int(name.rsplit("_", 1)[1]) + 1
        except (IndexError, ValueError):
            worker_id = 1
        img = img_pairs[idx - 1][1] if image_on else None
        stk = stk_pairs[idx - 1][1] if sticker_on else None
        effective_stk_pos = resolve_sticker_position(sticker_position, index=idx - 1)
        out = out_dir / f"{video.stem}_done.mp4"
        started = time.monotonic()
        emit(idx, worker_id, video, 0, "Bắt đầu")
        log(f"[WORKER {worker_id}] {idx}/{len(videos)} {video.name} -> {out.name} "
            f"(ảnh: {img.name if img else '-'}, "
            f"sticker: {stk.name if stk else '-'} @ {effective_stk_pos})")
        if dry_run:
            log(f"[WORKER {worker_id}] (dry-run) Sẽ xử lý {video.name} -> {out.name}")
            emit(idx, worker_id, video, 100, "Dry-run xong")
            return None

        info = print_info(video, log=log)
        orig_bitrate = info.get("bitrate") or 0
        src, sil_tmp = video, None
        if sil_kw is not None:
            emit(idx, worker_id, video, 2, "Quét khoảng lặng")
            sil_tmp, _scan = _maybe_cut_silence(
                video, out_dir, sil_kw, enc, quality_mode, quality_value,
                preset, threads, log, tools=silence_tools)
            if sil_tmp is not None:
                src = sil_tmp
                info = print_info(src, log=log)
                # Giữ đúng bitrate mục tiêu của video gốc cho bước encode chính,
                # tránh bị tụt bitrate qua 2 lần encode (cắt lặng -> ghép khung).
                if orig_bitrate > 0:
                    info["bitrate"] = orig_bitrate
        render_start = 8 if sil_kw is not None else 2

        def render_progress(percent):
            mapped = render_start + int(percent * (100 - render_start) / 100)
            emit(idx, worker_id, video, mapped, "Đang encode")

        try:
            use_chunk = bool(chunk) and (info["duration"] or 0) > chunk_seconds
            if use_chunk:
                done = chunk_fn(
                    src, img if image_on else None, stk if sticker_on else None, out,
                    mirror=mirror, speed=speed,
                    image_on=image_on, image_mode=image_mode, image_opacity=image_opacity,
                    sticker_on=sticker_on, sticker_scale=sticker_scale,
                    sticker_position=effective_stk_pos,
                    sticker_left=sticker_left, sticker_right=sticker_right,
                    sticker_top=sticker_top, sticker_bottom=sticker_bottom,
                    frame_916=frame_916, video_scale=video_scale,
                    video_position=video_position,
                    video_left=video_left, video_right=video_right,
                    video_top=video_top, video_bottom=video_bottom,
                    enc=enc, quality_mode=quality_mode, quality_value=quality_value,
                    preset=preset, threads=threads,
                    chunk_seconds=int(chunk_seconds), resume=resume,
                    keep_chunks=keep_chunks, info=info, log=log,
                    progress=render_progress, process_one=process_one_video)
            else:
                if chunk:
                    log(f"[WORKER {worker_id}] Video ngắn ({info['duration']:.0f}s ≤ "
                        f"{int(chunk_seconds)}s/đoạn) — xử lý một lần.")
                done = process_one_video(
                    src, img, stk, out,
                    mirror=mirror, speed=speed,
                    image_on=image_on, image_mode=image_mode, image_opacity=image_opacity,
                    sticker_on=sticker_on, sticker_scale=sticker_scale,
                    sticker_position=effective_stk_pos,
                    sticker_left=sticker_left, sticker_right=sticker_right,
                    sticker_top=sticker_top, sticker_bottom=sticker_bottom,
                    frame_916=frame_916, video_scale=video_scale,
                    video_position=video_position,
                    video_left=video_left, video_right=video_right,
                    video_top=video_top, video_bottom=video_bottom,
                    enc=enc, quality_mode=quality_mode, quality_value=quality_value,
                    preset=preset, threads=threads, info=info, log=log,
                    progress=render_progress)
            emit(idx, worker_id, video, 100, "Hoàn tất")
            log(f"[WORKER {worker_id}] Xong {video.name} sau "
                f"{time.monotonic() - started:.1f}s ({done.stat().st_size/1024:.0f} KB).")
            return done
        finally:
            if sil_tmp is not None and sil_tmp.exists():
                try:
                    sil_tmp.unlink()
                    log(f"[IM] Đã xóa file tạm cắt lặng: {sil_tmp.name}")
                except OSError as e:
                    log(f"[IM] Không xóa được file tạm {sil_tmp.name}: {e}")

    outputs_by_index = {}
    failures = []
    batch_started = time.monotonic()
    with ThreadPoolExecutor(max_workers=worker_count,
                            thread_name_prefix="video-worker") as executor:
        futures = {
            executor.submit(process_job, idx, video): (idx, video)
            for idx, video in enumerate(videos, start=1)
        }
        for future in as_completed(futures):
            idx, video = futures[future]
            try:
                done = future.result()
                if done is not None:
                    outputs_by_index[idx] = done
            except Exception as e:
                failures.append((video, e))
                log(f"[LỖI] {video.name}: {e}")

    outputs = [outputs_by_index[idx] for idx in sorted(outputs_by_index)]
    elapsed = time.monotonic() - batch_started
    if dry_run:
        log(f"[BATCH] Dry-run xong {len(videos)} video.")
        return []
    log(f"[XONG] Hoàn tất {len(outputs)}/{len(videos)} video sau {elapsed:.1f}s -> {out_dir}")
    if failures:
        names = ", ".join(video.name for video, _ in failures)
        raise RuntimeError(f"{len(failures)} video xử lý lỗi: {names}")
    return outputs


def main():
    p = argparse.ArgumentParser(description="5. Xử lý hàng loạt theo folder (1 lần encode/video, video dài tự chia đoạn)")
    p.add_argument("--videos", default="", help="Thư mục chứa video")
    p.add_argument("--video", default="", help="1 file video duy nhất")
    p.add_argument("--images", default="", help="Thư mục chứa ảnh ghép")
    p.add_argument("--stickers", default="", help="Thư mục chứa sticker")
    p.add_argument("-o", "--output-dir", required=True)
    p.add_argument("--pair", default="order", choices=["order", "shuffle"])
    p.add_argument("--seed", type=int, default=0)
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
    p.add_argument("--frame-916", dest="frame_916", action="store_true",
                   help="Khung 9:16 mặc định BẬT (1080x1920, ảnh làm nền, video phủ lên)")
    p.add_argument("--video-scale", type=float, default=0.94,
                   help="Tỉ lệ video phủ lên nền 9:16 (0.94 = như Scale 94%% trong ảnh mẫu)")
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
    p.add_argument("--workers", type=int, default=0,
                   help="Số video chạy song song; 0 = tự tối ưu theo GPU/CPU")
    p.add_argument("--gpu-profile", default="auto",
                   choices=["auto", "nvidia_legacy", "nvidia_modern"])
    p.add_argument("--chunk", dest="chunk", action="store_true",
                   help="Chia video dài thành từng đoạn rồi ghép lại (mặc định BẬT)")
    p.add_argument("--no-chunk", dest="chunk", action="store_false",
                   help="Tắt chia đoạn: xử lý mỗi video trong 1 lần encode duy nhất")
    p.add_argument("--chunk-seconds", type=int, default=300,
                   help="Độ dài mỗi đoạn khi chia video dài (giây, 10-3600, mặc định 300)")
    p.add_argument("--no-resume", dest="resume", action="store_false",
                   help="Không tiếp tục đoạn đã xử lý: làm lại tất cả các đoạn từ đầu")
    p.add_argument("--resume", dest="resume", action="store_true")
    p.add_argument("--keep-chunks", action="store_true",
                   help="Giữ lại thư mục chứa các đoạn tạm sau khi ghép xong")
    p.add_argument("--silence", dest="silence_on", action="store_true",
                   help="Bật cắt khoảng lặng trước khi xử lý chính (điều kiện 1/3/4)")
    p.add_argument("--no-silence", dest="silence_on", action="store_false")
    p.add_argument("--sil-mode", default="relative", choices=["relative", "absolute"])
    p.add_argument("--sil-margin", type=float, default=20.0)
    p.add_argument("--sil-threshold-db", type=float, default=-40.0)
    p.add_argument("--sil-min-silence", type=float, default=0.5)
    p.add_argument("--sil-min-cut", type=float, default=1.0)
    p.add_argument("--sil-pad", type=float, default=0.2)
    p.add_argument("--sil-min-keep", type=float, default=0.8)
    p.add_argument("--sil-max-keep", type=float, default=5.0)
    p.add_argument("--sil-no-trim-ends", dest="sil_trim_ends", action="store_false")
    p.add_argument("--sil-safety", action=argparse.BooleanOptionalAction, default=True,
                   help="Bật/tắt trần cắt tổng và bảo vệ video thu quá nhỏ")
    p.add_argument("--sil-max-cut-ratio", type=float, default=30.0,
                   help="Trần cắt tổng, tính theo %% (mặc định 30, chỉ dùng khi --sil-safety)")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(mirror=True, image_on=True, sticker_on=True, frame_916=True,
                   chunk=True, resume=True, silence_on=False, sil_trim_ends=True)
    a = p.parse_args()
    ratio = a.sil_max_cut_ratio
    ratio = ratio / 100.0 if ratio > 1 else ratio
    batch(a.videos or None, a.video or None, a.images or None,
          a.stickers or None, a.output_dir, a.pair, a.seed,
          a.mirror, a.speed, a.image_on, a.image_mode, a.image_opacity,
          a.sticker_on, a.sticker_scale, a.sticker_position,
          a.sticker_left, a.sticker_right, a.sticker_top, a.sticker_bottom,
          a.frame_916, a.video_scale, a.video_position,
          a.video_left, a.video_right, a.video_top, a.video_bottom,
          a.encoder, a.quality_mode, a.quality_value,
          a.preset, a.threads, a.dry_run,
          chunk=a.chunk, chunk_seconds=a.chunk_seconds,
          resume=a.resume, keep_chunks=a.keep_chunks,
          silence_on=a.silence_on, silence_mode=a.sil_mode,
          silence_margin=a.sil_margin, silence_absolute=a.sil_threshold_db,
          silence_min_silence=a.sil_min_silence, silence_min_cut=a.sil_min_cut,
          silence_pad=a.sil_pad, silence_min_keep=a.sil_min_keep,
          silence_max_keep=a.sil_max_keep, silence_trim_ends=a.sil_trim_ends,
          silence_safety=a.sil_safety, silence_max_cut_ratio=ratio,
          workers=a.workers, gpu_profile=a.gpu_profile)


if __name__ == "__main__":
    main()
