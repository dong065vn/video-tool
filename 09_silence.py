#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
09_silence.py — QUÉT KHOẢNG LẶNG & CẮT BỎ (video KOC / bán hàng)
=================================================================
Video bán hàng / livestream KOC thường có nhiều đoạn chết: người bán
ngừng nói, chờ khách, chuyển cảnh... Cắt các khoảng lặng dài đi thì
video gọn, giữ chân người xem hơn — nhưng phải cắt đúng chỗ, nếu không
sẽ cắt mất nhịp nói tự nhiên.

Thuật toán (2 bước, đều chỉ dùng ffmpeg có sẵn):
  1. ĐO ĐỘ LỚN TRUNG BÌNH của cả video (`volumedetect` -> mean_volume).
     Ngưỡng "im" tính TƯƠNG ĐỐI theo video đó, không dùng một số dB cố
     định: ngưỡng = độ lớn trung bình - margin (mặc định 20 dB).
     Nhờ vậy đoạn nào nhỏ hơn hẳn mức nói bình thường của CHÍNH video
     đó thì bị nhận là im — video quay ồn hay quay nhỏ đều quét được.
     (Muốn ngưỡng tuyệt đối thì dùng --mode absolute --threshold-db -40.)
  2. QUÉT KHOẢNG IM (`silencedetect`): liệt kê mọi khoảng âm thanh dưới
     ngưỡng, kèm thời gian bắt đầu/kết thúc. Sau đó ÁP ĐIỀU KIỆN CẮT
     (toàn bộ đều tự động, không cần duyệt tay — cho render tự động):
       - Chỉ cắt khoảng im DÀI HƠN min_cut (mặc định 1.0s): khoảng ngừng
         ngắn giữa các câu (0.3-0.8s) là nhịp nói tự nhiên, GIỮ LẠI.
       - Khi cắt thì GIỮ ĐỆM pad (mặc định 0.2s) ở hai đầu khoảng im để
         câu nói không bị cắt cụt đầu/cuối.
       - CHỐNG "ĐẢO": đoạn nói kẹp giữa 2 khoảng im mà ngắn hơn min_keep
         (mặc định 0.8s, VD: "vâng", "ừm") thì giữ lại khoảng im NGẮN
         HƠN bên cạnh — không thì video nghe giật cục, câu cụt lủn.
       - GIỮ TỐI ĐA mỗi khoảng im (max_keep_silence, mặc định 5s):
         khoảng im rất dài (VD: 30s) sau khi cắt vẫn còn tối đa 5s —
         phòng trường hợp lúc đó đang chiếu sản phẩm cho khách xem.
       - CẮT MẠNH đầu/cuối (trim_ends, mặc định BẬT): khoảng im ở đầu và
         cuối video cắt luôn dù ngắn hơn min_cut — không có câu nào để cụt.
       - TRẦN CẮT TỔNG (max_cut_ratio, mặc định 30%): nếu tổng thời gian
         sẽ cắt vượt 30% video thì tự tăng min_cut lên (1s -> 2s -> 3s
         -> 5s -> 10s) cho tới khi dưới trần; vẫn vượt thì KHÔNG CẮT GÌ,
         giữ nguyên video. Đây là phanh an toàn cho render tự động.
       - BẢO VỆ video thu quá nhỏ: cả video không có đoạn nào to hơn
         -40 dB (nghi mic lỗi / thu quá nhỏ, ngưỡng tương đối sẽ sai)
         thì KHÔNG CẮT, giữ nguyên video.
     Cắt bằng `trim`/`atrim` + `concat` rồi ENCODE LẠI cả hình lẫn tiếng
     theo CÙNG mốc thời gian — nên hình và tiếng không bị lệch nhau.
     (Cắt bằng `-c copy` ở điểm không phải keyframe mới gây lệch / giật.)

Tốc độ: bước quét chỉ GIẢI MÃ ÂM THANH (không encode, không đọc hình
với `-vn`) nên nhanh hơn thời gian thực nhiều lần — video 5 phút quét
xong trong vài giây. Bước cắt thì encode lại như xử lý video bình thường.

Chạy độc lập:
    python 09_silence.py -i video.mp4 --scan
        # Chỉ quét + in báo cáo, không cắt (xem trước sẽ cắt những đâu)
    python 09_silence.py -i video.mp4
        # Quét rồi cắt, ra video_catlang.mp4 cùng thư mục
    python 09_silence.py -i video.mp4 -o gon.mp4 --min-cut 2.0 --pad 0.3 --margin 15
    python 09_silence.py -i video.mp4 --mode absolute --threshold-db -45 --min-silence 0.3
    # Render tự động, cắt nhẹ (chỉ im > 2s, giữ tối đa 8s mỗi khoảng im):
    python 09_silence.py -i video.mp4 --min-cut 2.0 --pad 0.3 --max-keep-silence 8 --min-keep 1.0

Dùng trong code khác:
    from silence import scan_silences, remove_silence
    s = scan_silences("video.mp4")          # dict: độ lớn, ngưỡng, khoảng im, kế hoạch cắt
    print(format_scan(s))
    remove_silence("video.mp4", min_cut=2.0)  # cắt, ra video_catlang.mp4
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import check_ffmpeg, encode_args, get_info, print_info, run, validate_params
from gpu_detect import detect_gpu

# Ngưỡng tương đối = mean_volume - MARGIN_DB (mặc định 20 dB).
DEFAULT_MARGIN_DB = 20.0
DEFAULT_ABSOLUTE_DB = -40.0
DEFAULT_MIN_SILENCE = 0.5   # giây: im ngắn hơn thì không báo là khoảng im
DEFAULT_MIN_CUT = 1.0       # giây: chỉ cắt khoảng im dài hơn mức này
DEFAULT_PAD = 0.2           # giây: giữ đệm ở hai đầu khoảng im khi cắt
DEFAULT_MIN_KEEP = 0.8      # giây: đoạn nói kẹp giữa 2 khoảng im ngắn hơn
                            # mức này thì giữ lại khoảng im ngắn hơn bên cạnh
DEFAULT_MAX_CUT_RATIO = 0.30  # tổng cắt tối đa 30% thời lượng video
DEFAULT_MAX_KEEP_SILENCE = 5.0  # giây: mỗi khoảng im sau khi cắt còn tối đa
                                # mức này (0 = cắt hết, không giới hạn)
DEFAULT_MIN_PEAK_DB = -40.0  # dB: cả video không có đoạn nào to hơn mức này
                             # thì không cắt (nghi mic lỗi / thu quá nhỏ)
THRESHOLD_MIN, THRESHOLD_MAX = -60.0, -15.0  # kẹp ngưỡng tương đối vào khoảng này


def _run_ffmpeg_stderr(args, timeout=600):
    """Chạy ffmpeg, trả về stderr (nơi volumedetect/silencedetect in kết quả)."""
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg thất bại (exit {r.returncode}):\n{r.stderr[-1500:]}")
    return r.stderr


def measure_loudness(path):
    """Đo độ lớn âm thanh: trả về {"mean_volume": dB, "max_volume": dB}."""
    err = _run_ffmpeg_stderr(["ffmpeg", "-v", "info", "-i", str(path),
                              "-vn", "-af", "volumedetect", "-f", "null", "-"])
    mean = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", err)
    mx = re.search(r"max_volume:\s*(-?[\d.]+)\s*dB", err)
    if not mean:
        raise RuntimeError("Không đo được độ lớn âm thanh (video này có âm thanh không?).")
    return {"mean_volume": float(mean.group(1)),
            "max_volume": float(mx.group(1)) if mx else 0.0}


def resolve_threshold(mode, margin_db, absolute_db, mean_volume):
    """Tính ngưỡng 'im' (dB). Tương đối: mean - margin, kẹp trong [-60, -15]."""
    if mode == "absolute":
        return max(-80.0, min(-10.0, float(absolute_db)))
    t = float(mean_volume) - float(margin_db)
    return max(THRESHOLD_MIN, min(THRESHOLD_MAX, t))


def detect_silences(path, threshold_db, min_silence, duration):
    """Quét tuần tự các mốc bắt đầu/kết thúc im do FFmpeg phát hiện."""
    err = _run_ffmpeg_stderr([
        "ffmpeg", "-v", "info", "-i", str(path), "-vn",
        "-af", f"silencedetect=noise={threshold_db:.2f}dB:d={min_silence:.6f}",
        "-f", "null", "-"])
    events = re.findall(r"silence_(start|end):\s*([0-9]+(?:\.[0-9]+)?)", err)
    out = []
    start = None
    for kind, raw_time in events:
        timestamp = min(float(raw_time), float(duration))
        if kind == "start":
            start = timestamp
        elif start is not None:
            if timestamp - start >= 0.05:
                out.append((round(start, 6), round(timestamp, 6),
                            round(timestamp - start, 6)))
            start = None
    if start is not None and float(duration) - start >= 0.05:
        out.append((round(start, 6), round(float(duration), 6),
                    round(float(duration) - start, 6)))
    return out


def _video_timing(path, fallback_duration):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=duration,nb_frames", "-of", "json",
         str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return float(fallback_duration), None
    streams = json.loads(result.stdout).get("streams", [])
    if not streams:
        return float(fallback_duration), None
    stream = streams[0]
    try:
        duration = float(stream.get("duration") or fallback_duration)
    except (TypeError, ValueError):
        duration = float(fallback_duration)
    try:
        frame_count = int(stream["nb_frames"])
    except (KeyError, TypeError, ValueError):
        frame_count = None
    return duration, frame_count


def _align_plan_to_video_frames(path, cuts, duration):
    """Căn hai đầu mỗi đoạn cắt vào frame video thật, kể cả video VFR."""
    if not cuts:
        return ([(0.0, round(float(duration), 6))], [], [],
                [{"start_frame": 0, "end_frame": None,
                  "start": 0.0, "end": round(float(duration), 6)}], 0.0)

    boundaries = [{} for _ in cuts]
    targets = []
    for index, (start, end) in enumerate(cuts):
        targets.append((float(start), index, "start"))
        targets.append((float(end), index, "end"))
    targets.sort(key=lambda item: item[0])

    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "frame=best_effort_timestamp_time",
        "-of", "csv=p=0", str(path),
    ]
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", errors="replace",
    )
    first_pts = None
    frame_count = 0
    target_index = 0
    terminated = False
    try:
        for raw_line in process.stdout:
            raw_value = raw_line.strip().split(",", 1)[0]
            try:
                pts = float(raw_value)
            except ValueError:
                continue
            if first_pts is None:
                first_pts = pts
            relative_pts = max(0.0, pts - first_pts)
            current_frame = frame_count
            frame_count += 1
            while (target_index < len(targets)
                   and relative_pts + 1e-9 >= targets[target_index][0]):
                _, cut_index, side = targets[target_index]
                boundaries[cut_index][side] = (current_frame, relative_pts)
                target_index += 1
            if target_index == len(targets):
                process.terminate()
                terminated = True
                break
    finally:
        if process.stdout is not None:
            process.stdout.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    if first_pts is None:
        raise RuntimeError("Không đọc được timestamp frame video để căn mốc cắt.")
    if not terminated and process.returncode not in (0, None):
        raise RuntimeError("ffprobe không đọc được danh sách frame video.")

    while target_index < len(targets):
        _, cut_index, side = targets[target_index]
        boundaries[cut_index][side] = (frame_count, float(duration))
        target_index += 1

    aligned = []
    for boundary in boundaries:
        start_frame, start_time = boundary["start"]
        end_frame, end_time = boundary["end"]
        if end_frame <= start_frame or end_time - start_time < 0.05:
            continue
        item = {
            "start_frame": start_frame, "end_frame": end_frame,
            "start": round(start_time, 9), "end": round(end_time, 9),
        }
        if aligned and item["start_frame"] <= aligned[-1]["end_frame"]:
            previous = aligned[-1]
            if item["end_frame"] > previous["end_frame"]:
                previous["end_frame"] = item["end_frame"]
                previous["end"] = item["end"]
        else:
            aligned.append(item)

    keep = []
    frame_keep = []
    aligned_cuts = []
    current_frame = 0
    current_time = 0.0
    for item in aligned:
        start_time = item["start"]
        if start_time - current_time >= 0.05:
            keep.append((round(current_time, 9), start_time))
            frame_keep.append({
                "start_frame": current_frame,
                "end_frame": item["start_frame"],
                "start": round(current_time, 9),
                "end": start_time,
            })
        aligned_cuts.append((start_time, item["end"]))
        current_frame = max(current_frame, item["end_frame"])
        current_time = max(current_time, item["end"])
    if float(duration) - current_time >= 0.05:
        keep.append((round(current_time, 9), round(float(duration), 9)))
        frame_keep.append({
            "start_frame": current_frame, "end_frame": None,
            "start": round(current_time, 9), "end": round(float(duration), 9),
        })
    total_cut = round(sum(end - start for start, end in aligned_cuts), 9)
    return keep, aligned_cuts, aligned, frame_keep, total_cut


def _keep_from_cuts(cuts, duration):
    """Phần bù của các đoạn cắt trên [0, duration] = các đoạn GIỮ LẠI."""
    keep = []
    cur = 0.0
    for (cs, ce) in cuts:
        if cs - cur >= 0.05:
            keep.append((round(cur, 6), round(cs, 6)))
        cur = max(cur, ce)
    if float(duration) - cur >= 0.05:
        keep.append((round(cur, 6), round(float(duration), 6)))
    return keep


def _apply_min_keep(cuts, duration, min_keep):
    """
    Chống "đảo": đoạn nói kẹp giữa 2 lần cắt mà ngắn hơn min_keep
    (VD: "vâng", "ừm" 0.4s) thì bỏ lần cắt NGẮN HƠN bên cạnh — giữ lại
    khoảng im đó để video không nghe giật cục. Lặp tới khi hết đảo.
    """
    cuts = list(cuts)
    while True:
        keep = _keep_from_cuts(cuts, duration)
        removed = False
        for i in range(1, len(keep) - 1):
            ks, ke = keep[i]
            if ke - ks < min_keep:
                left = cuts[i - 1]
                right = cuts[i]
                if (left[1] - left[0]) <= (right[1] - right[0]):
                    del cuts[i - 1]
                else:
                    del cuts[i]
                removed = True
                break
        if not removed:
            return cuts


def plan_cuts(silences, duration, min_cut, pad,
              min_keep=DEFAULT_MIN_KEEP,
              max_keep_silence=DEFAULT_MAX_KEEP_SILENCE,
              trim_ends=True):
    """
    Áp điều kiện cắt lên các khoảng im đã quét.
    Trả về (keep_segments, cuts, total_cut):
      - keep_segments: các đoạn GIỮ LẠI [(start, end), ...]
      - cuts: các đoạn SẼ CẮT [(start, end), ...] (đã trừ đệm pad hai đầu)
    Quy tắc (cho render tự động, không cần duyệt tay):
      - Im ngắn hơn min_cut thì giữ (nhịp nói tự nhiên); khi cắt thì giữ
        đệm pad ở hai đầu để câu không bị cụt.
      - trim_ends: khoảng im ở ĐẦU/CUỐI video cắt luôn dù ngắn hơn
        min_cut (không có câu nào để cụt).
      - max_keep_silence > 0: khoảng im rất dài sau khi cắt vẫn còn tối
        đa mức này (giữ ở đầu khoảng im) — phòng lúc đó đang chiếu sản phẩm.
      - min_keep > 0: chống "đảo" — đoạn nói ngắn kẹp giữa 2 lần cắt thì
        giữ lại khoảng im ngắn hơn bên cạnh.
    """
    cuts = []
    for (s, e, d) in silences:
        is_edge = trim_ends and (s <= 0.05 or e >= float(duration) - 0.05)
        if d < min_cut and not is_edge:
            continue
        cs, ce = s + pad, e - pad
        if max_keep_silence > 0 and d > max_keep_silence:
            # Giữ tối đa max_keep_silence giây ở đầu khoảng im:
            # còn lại = (cs - s) + (e - ce) = max_keep_silence.
            cs = max(cs, s + max_keep_silence - pad)
        cs = max(0.0, cs)
        ce = min(float(duration), ce)
        if ce - cs >= 0.05:
            cuts.append((round(cs, 6), round(ce, 6)))
    if min_keep > 0 and cuts:
        cuts = _apply_min_keep(cuts, duration, min_keep)
    keep = _keep_from_cuts(cuts, duration)
    total_cut = round(sum(ce - cs for (cs, ce) in cuts), 6)
    return keep, cuts, total_cut


def scan_silences(path, mode="relative", margin_db=DEFAULT_MARGIN_DB,
                  absolute_db=DEFAULT_ABSOLUTE_DB,
                  min_silence=DEFAULT_MIN_SILENCE, min_cut=DEFAULT_MIN_CUT,
                  pad=DEFAULT_PAD, min_keep=DEFAULT_MIN_KEEP,
                  max_cut_ratio=DEFAULT_MAX_CUT_RATIO,
                  max_keep_silence=DEFAULT_MAX_KEEP_SILENCE,
                  trim_ends=True, min_peak_db=DEFAULT_MIN_PEAK_DB):
    """
    Quét 1 video: đo độ lớn -> tính ngưỡng -> tìm khoảng im -> lập kế hoạch cắt.
    Trả về dict đầy đủ để GUI/CLI in báo cáo hoặc cắt tiếp.
    Phanh an toàn cho render tự động (xem plan_cuts + docstring):
      - Video thu quá nhỏ (peak < min_peak_db) -> guard, không cắt gì.
      - Tổng cắt vượt max_cut_ratio -> tự tăng min_cut lên tới khi dưới
        trần; vẫn vượt thì không cắt gì (capped_no_cut=True).
    """
    # Kiểm tra số nhập ngay ở đây (không chỉ ở nút Cắt / CLI --scan):
    # nút "Quét khoảng lặng" gọi scan_silences() trực tiếp, nếu không kiểm
    # tra thì nhập min_cut=0 sẽ cho báo cáo cắt từng mili giây, trái với
    # quy tắc "chỉ cắt im dài hơn mức đặt" của người dùng.
    validate_silence_params(mode, margin_db, absolute_db, min_silence, min_cut,
                            pad, min_keep, max_cut_ratio, max_keep_silence,
                            min_peak_db)
    path = Path(path)
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy file: {path}")
    info = get_info(path)
    if not info.get("has_audio"):
        raise RuntimeError("Video này không có luồng âm thanh, không quét được khoảng lặng.")
    if not info.get("has_video"):
        raise RuntimeError("File này không có luồng hình nên không thể căn và cắt theo frame.")
    container_duration = float(info["duration"] or 0)
    duration, source_frames = _video_timing(path, container_duration)
    if duration <= 0:
        raise RuntimeError("Không đọc được thời lượng luồng hình.")
    loud = measure_loudness(path)
    threshold = resolve_threshold(mode, margin_db, absolute_db, loud["mean_volume"])
    silences = detect_silences(path, threshold, min_silence, duration)
    total_silence = round(sum(d for (_, _, d) in silences), 6)

    guard = None
    min_cut_eff = float(min_cut)
    capped_no_cut = False
    eff_peak_db = float(min_peak_db) if min_peak_db is not None else -80.0
    if loud["max_volume"] <= eff_peak_db:
        guard = (f"Âm thanh cả video quá nhỏ hoặc im hoàn toàn (lớn nhất {loud['max_volume']:.1f} dB "
                 f"<= {eff_peak_db:.0f} dB) — nghi mic lỗi / thu quá nhỏ, "
                 f"ngưỡng tương đối sẽ sai nên KHÔNG CẮT (giữ nguyên video).")
        keep, cuts, total_cut = [(0.0, round(duration, 6))], [], 0.0
    else:
        keep, cuts, total_cut = plan_cuts(silences, duration, min_cut, pad,
                                          min_keep, max_keep_silence, trim_ends)
        if not keep:
            guard = "Video gần như toàn khoảng lặng, không còn đoạn nào để giữ — KHÔNG CẮT (giữ nguyên video)."
            keep, cuts, total_cut = [(0.0, round(duration, 6))], [], 0.0
        elif max_cut_ratio > 0 and total_cut / duration > max_cut_ratio:
            for cand in (min_cut * 1.5, min_cut * 2, min_cut * 3,
                         min_cut * 5, 10.0):
                cand = round(float(cand), 2)
                if cand <= min_cut_eff or cand > 10.0:
                    continue
                min_cut_eff = cand
                keep, cuts, total_cut = plan_cuts(
                    silences, duration, cand, pad,
                    min_keep, max_keep_silence, trim_ends)
                if total_cut / duration <= max_cut_ratio:
                    break
            if total_cut / duration > max_cut_ratio:
                keep, cuts, total_cut = [(0.0, round(duration, 6))], [], 0.0
                capped_no_cut = True

    frame_cuts = []
    frame_keep = [{
        "start_frame": 0, "end_frame": None,
        "start": 0.0, "end": round(duration, 6),
    }]
    if cuts:
        keep, cuts, frame_cuts, frame_keep, total_cut = (
            _align_plan_to_video_frames(path, cuts, duration)
        )
        if not keep:
            guard = "Căn theo frame không còn đoạn hình hợp lệ để giữ — KHÔNG CẮT."
            keep, cuts, frame_cuts, total_cut = (
                [(0.0, round(duration, 6))], [], [], 0.0
            )
            frame_keep = [{
                "start_frame": 0, "end_frame": None,
                "start": 0.0, "end": round(duration, 6),
            }]
        elif max_cut_ratio > 0 and total_cut / duration > max_cut_ratio:
            keep, cuts, frame_cuts, total_cut = (
                [(0.0, round(duration, 6))], [], [], 0.0
            )
            frame_keep = [{
                "start_frame": 0, "end_frame": None,
                "start": 0.0, "end": round(duration, 6),
            }]
            capped_no_cut = True
    return {
        "file": str(path), "name": path.name,
        "duration": duration,
        "mean_volume": loud["mean_volume"], "max_volume": loud["max_volume"],
        "threshold": round(threshold, 1), "mode": mode,
        "margin_db": float(margin_db), "absolute_db": float(absolute_db),
        "min_silence": float(min_silence), "min_cut": float(min_cut),
        "min_cut_effective": min_cut_eff,
        "pad": float(pad),
        "min_keep": float(min_keep), "max_cut_ratio": float(max_cut_ratio),
        "max_keep_silence": float(max_keep_silence), "trim_ends": bool(trim_ends),
        "min_peak_db": min_peak_db,
        "guard": guard, "capped_no_cut": capped_no_cut,
        "silences": silences, "keep": keep, "cuts": cuts,
        "frame_cuts": frame_cuts, "frame_keep": frame_keep,
        "fps": float(info.get("fps") or 0), "frame_aligned": bool(frame_cuts),
        "source_frames": source_frames,
        "est_frames": (
            source_frames - sum(
                item["end_frame"] - item["start_frame"] for item in frame_cuts
            )
            if source_frames is not None else None
        ),
        "total_silence": total_silence, "total_cut": total_cut,
        "cut_ratio": round(total_cut / duration, 6) if duration > 0 else 0.0,
        "n_detected": len(silences), "n_cut": len(cuts),
        "est_duration": round(duration - total_cut, 6),
        "has_audio": True, "has_video": True,
    }


def format_scan(s):
    """Báo cáo quét bằng tiếng Việt (dùng cho GUI + CLI)."""
    L = []
    L.append("========== QUÉT KHOẢNG LẶNG ==========")
    L.append(f"File       : {s['name']} ({s['duration']:.1f}s)")
    L.append(f"Độ lớn TB  : {s['mean_volume']:.1f} dB | Lớn nhất: {s['max_volume']:.1f} dB")
    if s["mode"] == "relative":
        L.append(f"Ngưỡng im  : {s['threshold']:.1f} dB (trung bình - {s['margin_db']:.0f} dB)")
    else:
        L.append(f"Ngưỡng im  : {s['threshold']:.1f} dB (tuyệt đối)")
    if s.get("guard"):
        L.append(f"CẢNH BÁO  : {s['guard']}")
    cap_txt = (f"trần cắt {s['max_cut_ratio'] * 100:.0f}%"
               if s["max_cut_ratio"] > 0 else "trần cắt TẮT")
    L.append(f"Điều kiện  : chỉ cắt im > {s['min_cut']}s, đệm {s['pad']}s, "
             f"chống đảo {s['min_keep']}s, giữ tối đa {s['max_keep_silence']}s/khoảng im, "
             f"{'cắt mạnh đầu/cuối, ' if s['trim_ends'] else ''}"
             f"{cap_txt}")
    L.append(f"Phát hiện  : {s['n_detected']} khoảng im (>= {s['min_silence']}s), "
             f"tổng {s['total_silence']:.1f}s")
    if s["cuts"]:
        fps_text = f" ({s['fps']:.3f} fps trung bình)" if s["fps"] else ""
        L.append(f"Căn frame  : dùng timestamp frame thật{fps_text}; "
                 f"hình và tiếng dùng cùng mốc")
    cut_frames = list(zip(s["cuts"], s.get("frame_cuts", [])))
    for i, (st, en, d) in enumerate(s["silences"], 1):
        inner = [
            (cut, frames) for cut, frames in cut_frames
            if cut[0] >= st - 0.01 and cut[1] <= en + 0.01
        ]
        if inner:
            cut_len = sum(cut[1] - cut[0] for cut, _ in inner)
            bounds = ", ".join(
                f"{cut[0]:.6f}-{cut[1]:.6f}s "
                f"(frame {frames['start_frame']}-{frames['end_frame'] - 1})"
                for cut, frames in inner
            )
            verdict = f"CẮT {cut_len:.3f}s tại {bounds}"
        elif d < s["min_cut_effective"]:
            verdict = (f"GIỮ (ngắn hơn {s['min_cut_effective']}s"
                       f" — nhịp nói tự nhiên)")
        else:
            verdict = "GIỮ (chống đảo — giữ lại để video tự nhiên)"
        L.append(f"  #{i}: {st:9.3f}s - {en:9.3f}s ({d:7.3f}s) -> {verdict}")
    if s.get("capped_no_cut"):
        L.append(f"Lưu ý     : Tổng cắt vượt trần {s['max_cut_ratio'] * 100:.0f}% "
                 f"ngay cả khi tăng 'chỉ cắt khi dài hơn' lên "
                 f"{s['min_cut_effective']}s nên KHÔNG CẮT GÌ — giữ nguyên video.")
    elif s["min_cut_effective"] != s["min_cut"]:
        L.append(f"Lưu ý     : Tổng cắt vượt trần {s['max_cut_ratio'] * 100:.0f}% "
                 f"nên đã tự tăng 'chỉ cắt khi dài hơn' từ {s['min_cut']}s "
                 f"lên {s['min_cut_effective']}s.")
    L.append(f"Sẽ cắt    : {s['n_cut']} đoạn, tổng {s['total_cut']:.1f}s")
    if s["duration"] > 0:
        pct = 100.0 * s["total_cut"] / s["duration"]
        L.append(f"Ước tính ra: {s['est_duration']:.1f}s (giảm {pct:.1f}%)")
    L.append("=====================================")
    return "\n".join(L)


def validate_silence_params(mode="relative", margin_db=DEFAULT_MARGIN_DB,
                            absolute_db=DEFAULT_ABSOLUTE_DB,
                            min_silence=DEFAULT_MIN_SILENCE,
                            min_cut=DEFAULT_MIN_CUT, pad=DEFAULT_PAD,
                            min_keep=DEFAULT_MIN_KEEP,
                            max_cut_ratio=DEFAULT_MAX_CUT_RATIO,
                            max_keep_silence=DEFAULT_MAX_KEEP_SILENCE,
                            min_peak_db=DEFAULT_MIN_PEAK_DB):
    """Kiểm tra số người dùng nhập, báo lỗi tiếng Việt rõ ràng trước khi chạy."""
    if mode not in ("relative", "absolute"):
        raise ValueError("Chế độ ngưỡng phải là 'relative' hoặc 'absolute'.")
    try:
        margin_db = float(margin_db)
    except (TypeError, ValueError):
        raise ValueError(f"Margin phải là số, VD: 20. Hiện tại: {margin_db!r}.")
    if not (1 <= margin_db <= 40):
        raise ValueError(f"Margin phải từ 1 đến 40 dB, hiện tại: {margin_db}.")
    try:
        absolute_db = float(absolute_db)
    except (TypeError, ValueError):
        raise ValueError(f"Ngưỡng tuyệt đối phải là số, VD: -40. Hiện tại: {absolute_db!r}.")
    if not (-80 <= absolute_db <= -10):
        raise ValueError(f"Ngưỡng tuyệt đối phải từ -80 đến -10 dB, hiện tại: {absolute_db}.")
    for name, val, lo, hi in (
            ("Im tối thiểu để nhận", min_silence, 0.1, 10),
            ("Chỉ cắt khi im dài hơn", min_cut, 0.1, 30),
            ("Đệm giữ lại", pad, 0, 1),
            ("Đoạn nói tối thiểu (chống đảo)", min_keep, 0, 5),
            ("Giữ tối đa mỗi khoảng im", max_keep_silence, 0, 30)):
        try:
            val = float(val)
        except (TypeError, ValueError):
            raise ValueError(f"{name} phải là số. Hiện tại: {val!r}.")
        if not (lo <= val <= hi):
            raise ValueError(f"{name} phải từ {lo} đến {hi} giây (0 = tắt), hiện tại: {val}.")
    try:
        max_cut_ratio = float(max_cut_ratio)
    except (TypeError, ValueError):
        raise ValueError(f"Trần cắt tổng phải là số, VD: 0.30. Hiện tại: {max_cut_ratio!r}.")
    if not (max_cut_ratio == 0 or 0.05 <= max_cut_ratio <= 0.8):
        raise ValueError(f"Trần cắt tổng phải là 0 (tắt) hoặc từ 0.05 đến 0.8 "
                         f"(5%-80%), hiện tại: {max_cut_ratio}.")
    try:
        min_peak_db = float(min_peak_db) if min_peak_db is not None else None
    except (TypeError, ValueError):
        raise ValueError(f"Ngưỡng bảo vệ thu nhỏ phải là số, VD: -40. Hiện tại: {min_peak_db!r}.")
    if min_peak_db is not None and not (-80 <= min_peak_db <= -10):
        raise ValueError(f"Ngưỡng bảo vệ thu nhỏ phải từ -80 đến -10 dB, hiện tại: {min_peak_db}.")
    return True


def _stream_durations(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,duration,nb_frames", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return {}
    durations = {}
    for stream in json.loads(result.stdout).get("streams", []):
        codec_type = stream.get("codec_type")
        try:
            durations[codec_type] = float(stream["duration"])
        except (KeyError, TypeError, ValueError):
            pass
        if codec_type == "video":
            try:
                durations["video_frames"] = int(stream["nb_frames"])
            except (KeyError, TypeError, ValueError):
                pass
    return durations


def remove_silence(input_path, output_path=None, mode="relative",
                   margin_db=DEFAULT_MARGIN_DB, absolute_db=DEFAULT_ABSOLUTE_DB,
                   min_silence=DEFAULT_MIN_SILENCE, min_cut=DEFAULT_MIN_CUT,
                   pad=DEFAULT_PAD, min_keep=DEFAULT_MIN_KEEP,
                   max_cut_ratio=DEFAULT_MAX_CUT_RATIO,
                   max_keep_silence=DEFAULT_MAX_KEEP_SILENCE,
                   trim_ends=True, min_peak_db=DEFAULT_MIN_PEAK_DB,
                   encoder="auto", quality_mode="source",
                   quality_value="", preset=None, threads=None,
                   dry_run=False, log=print, scan=None):
    """
    Quét rồi cắt các khoảng lặng đủ dài, ra file mới.
    Hình và tiếng cắt theo CÙNG mốc thời gian rồi encode lại nên không lệch.
    Không có khoảng nào đủ dài để cắt (hoặc phanh an toàn kích hoạt) ->
    copy nguyên file ra output.
    scan: dict quét có sẵn (từ scan_silences) thì dùng luôn, khỏi quét lại —
    dùng khi batch đã quét trước để quyết định có cắt hay không.
    """
    check_ffmpeg()
    validate_params(quality_mode=quality_mode, quality_value=quality_value)
    validate_silence_params(mode, margin_db, absolute_db, min_silence, min_cut,
                            pad, min_keep, max_cut_ratio, max_keep_silence,
                            min_peak_db)
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.with_name(input_path.stem + "_catlang.mp4")
    else:
        output_path = Path(output_path)
    info = print_info(input_path, log=log)
    if not info.get("has_audio"):
        raise RuntimeError("Video này không có luồng âm thanh, không cắt được khoảng lặng.")

    # scan có sẵn (batch đã quét + in báo cáo trước) thì dùng luôn, khỏi
    # quét lại và khỏi in báo cáo lần nữa.
    if scan is None:
        scan = scan_silences(input_path, mode, margin_db, absolute_db,
                             min_silence, min_cut, pad, min_keep,
                             max_cut_ratio, max_keep_silence, trim_ends,
                             min_peak_db)
        log(format_scan(scan))
    if not scan["cuts"]:
        if scan.get("guard"):
            reason = "Video thu quá nhỏ, phanh an toàn không cho cắt"
        elif scan.get("capped_no_cut"):
            reason = (f"Tổng cắt vượt trần {scan['max_cut_ratio'] * 100:.0f}% "
                      f"nên không cắt gì để giữ video")
        else:
            reason = "Không có khoảng lặng nào đủ dài để cắt"
        log(f"[INFO] {reason} — copy nguyên file ra.")
        if not dry_run:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_path, output_path)
            log(f"[XONG] (không cắt gì) {output_path}")
        return output_path

    keep = scan["keep"]
    frame_keep = scan["frame_keep"]
    if not keep or len(frame_keep) != len(keep):
        raise RuntimeError("Kế hoạch cắt theo frame không hợp lệ.")
    has_audio = bool(info.get("has_audio"))

    parts = []
    for i, segment in enumerate(frame_keep):
        start = float(segment["start"])
        end = float(segment["end"])
        start_frame = int(segment["start_frame"])
        end_frame = segment["end_frame"]
        trim_args = [f"start_frame={start_frame}"]
        if end_frame is not None:
            trim_args.append(f"end_frame={int(end_frame)}")
        parts.append(
            f"[0:v]trim={':'.join(trim_args)},setpts=PTS-STARTPTS[v{i}]"
        )
        if has_audio:
            segment_duration = end - start
            parts.append(
                f"[0:a]atrim=start={start:.9f}:end={end:.9f},"
                f"asetpts=PTS-STARTPTS,apad,"
                f"atrim=duration={segment_duration:.9f}[a{i}]"
            )
        end_frame_text = str(end_frame - 1) if end_frame is not None else "cuối"
        log(f"[FRAME] Giữ đoạn {i + 1}: {start:.6f}-{end:.6f}s | "
            f"frame {start_frame}-{end_frame_text}")
    v_labels = "".join(f"[v{i}]" for i in range(len(frame_keep)))
    if has_audio:
        labels = "".join(f"[v{i}][a{i}]" for i in range(len(frame_keep)))
        parts.append(
            f"{labels}concat=n={len(frame_keep)}:v=1:a=1[v][acat]"
        )
        parts.append("[acat]aresample=async=1:first_pts=0[a]")
    else:
        parts.append(f"{v_labels}concat=n={len(frame_keep)}:v=1:a=0[v]")
    fc = ";".join(parts)

    det = detect_gpu() if encoder == "auto" else None
    enc = det["encoder"] if det else encoder
    preset = preset or (det["preset"] if det else "medium")
    threads = threads or (det["threads"] if det else 4)
    log(f"[INFO] Encoder: {enc} (preset {preset}) | "
        f"Chất lượng: {quality_mode} {quality_value or '(gốc)'} | "
        f"Cắt {scan['n_cut']} đoạn im, {scan['total_cut']:.1f}s -> còn ~{scan['est_duration']:.1f}s")

    if enc == "h264_vaapi":
        fc += ";[v]format=nv12,hwupload[vout]"
        vmap = "[vout]"
    else:
        vmap = "[v]"
    cmd = ["ffmpeg", "-y", "-i", str(input_path),
           "-filter_complex", fc, "-map", vmap]
    if has_audio:
        cmd += ["-map", "[a]"]
    cmd += encode_args(enc, quality_mode, quality_value, preset, threads, info)
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "128k"]
    cmd += ["-movflags", "+faststart", str(output_path)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    run(cmd, dry_run=dry_run, log=log)
    if not dry_run:
        out_info = print_info(output_path, log=log)
        durations = _stream_durations(output_path)
        expected_frames = scan.get("est_frames")
        actual_frames = durations.get("video_frames")
        if expected_frames is not None and actual_frames is not None:
            if actual_frames != expected_frames:
                output_path.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Đầu ra sai số frame: cần {expected_frames}, nhận {actual_frames}; "
                    "đã xóa file sai."
                )
            log(f"[FRAME] Đầu ra đúng {actual_frames}/{expected_frames} frame.")
        if "video" in durations and "audio" in durations:
            av_delta = abs(durations["video"] - durations["audio"])
            tolerance = max(
                0.05, 1.0 / scan["fps"] if scan.get("fps") else 0.05
            )
            if av_delta > tolerance:
                output_path.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Hình/tiếng lệch {av_delta:.6f}s, vượt {tolerance:.6f}s; "
                    "đã xóa file sai."
                )
            log(f"[SYNC] Hình {durations['video']:.6f}s | "
                f"Tiếng {durations['audio']:.6f}s | lệch {av_delta:.6f}s")
        log(f"[XONG] Cắt khoảng lặng: {info['duration']:.3f}s -> "
            f"{out_info['duration']:.3f}s (đã cắt {scan['total_cut']:.3f}s, "
            f"{scan['n_cut']} đoạn đã căn frame) | Ra: {output_path}")
    return output_path


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Quét khoảng lặng trong video KOC rồi cắt bỏ, ghép lại")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", default="",
                   help="File ra (mặc định: <tên>_catlang.mp4 cùng thư mục)")
    p.add_argument("--mode", default="relative", choices=["relative", "absolute"],
                   help="relative: ngưỡng = độ lớn TB - margin (mặc định); "
                        "absolute: ngưỡng dB cố định")
    p.add_argument("--margin", type=float, default=DEFAULT_MARGIN_DB,
                   help="relative: nhỏ hơn độ lớn TB bao nhiêu dB thì tính là im (mặc định 20)")
    p.add_argument("--threshold-db", type=float, default=DEFAULT_ABSOLUTE_DB,
                   help="absolute: ngưỡng dB cố định (mặc định -40)")
    p.add_argument("--min-silence", type=float, default=DEFAULT_MIN_SILENCE,
                   help="Im tối thiểu bao lâu mới nhận là khoảng im (mặc định 0.5s)")
    p.add_argument("--min-cut", type=float, default=DEFAULT_MIN_CUT,
                   help="Chỉ cắt khoảng im dài hơn mức này (mặc định 1.0s)")
    p.add_argument("--pad", type=float, default=DEFAULT_PAD,
                   help="Giữ đệm bao lâu ở hai đầu khoảng im khi cắt (mặc định 0.2s)")
    p.add_argument("--min-keep", type=float, default=DEFAULT_MIN_KEEP,
                   help="Chống đảo: đoạn nói kẹp giữa 2 khoảng im ngắn hơn mức này "
                        "thì giữ lại khoảng im ngắn hơn bên cạnh (mặc định 0.8s, 0 = tắt)")
    p.add_argument("--max-cut-ratio", type=float, default=DEFAULT_MAX_CUT_RATIO * 100,
                   help="Trần cắt tổng, tính theo %% (mặc định 30): vượt trần thì tự "
                        "tăng --min-cut lên, vẫn vượt thì không cắt gì (0 = tắt)")
    p.add_argument("--max-keep-silence", type=float, default=DEFAULT_MAX_KEEP_SILENCE,
                   help="Mỗi khoảng im sau khi cắt còn tối đa bao nhiêu giây "
                        "(mặc định 5s, 0 = cắt hết)")
    p.add_argument("--no-trim-ends", dest="trim_ends", action="store_false",
                   help="Tắt cắt mạnh khoảng im đầu/cuối video")
    p.add_argument("--min-peak-db", type=float, default=DEFAULT_MIN_PEAK_DB,
                   help="Cả video không có đoạn nào to hơn mức này (dB) thì không cắt, "
                        "nghi mic lỗi (mặc định -40)")
    p.set_defaults(trim_ends=True)
    p.add_argument("--scan", action="store_true",
                   help="Chỉ quét + in báo cáo, không cắt")
    p.add_argument("--encoder", default="auto")
    p.add_argument("--quality-mode", default="source",
                   choices=["source", "bitrate", "crf"])
    p.add_argument("--quality-value", default="")
    p.add_argument("--preset", default=None)
    p.add_argument("--threads", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)

    ratio = a.max_cut_ratio
    ratio = ratio / 100.0 if ratio > 1 else ratio  # CLI nhập % (30) hay tỉ lệ (0.30) đều được
    kw = dict(mode=a.mode, margin_db=a.margin, absolute_db=a.threshold_db,
              min_silence=a.min_silence, min_cut=a.min_cut, pad=a.pad,
              min_keep=a.min_keep, max_cut_ratio=ratio,
              max_keep_silence=a.max_keep_silence, trim_ends=a.trim_ends,
              min_peak_db=a.min_peak_db)
    if a.scan:
        check_ffmpeg()
        vkw = {k: v for k, v in kw.items() if k != "trim_ends"}
        validate_silence_params(**vkw)
        s = scan_silences(a.input, **kw)
        print(format_scan(s))
        return 0
    remove_silence(Path(a.input),
                   Path(a.output) if a.output else None,
                   encoder=a.encoder,
                   quality_mode=a.quality_mode, quality_value=a.quality_value,
                   preset=a.preset, threads=a.threads, dry_run=a.dry_run, **kw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
