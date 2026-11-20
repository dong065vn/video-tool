#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
07_media_info.py — XEM THÔNG SỐ CHI TIẾT CỦA VIDEO (ffprobe)
================================================================
Dùng ffprobe (đi kèm ffmpeg, tool đã bắt buộc có) để đọc thông số —
đây là nguồn đáng tin nhất, chính xác hơn metadata của VLC hay
MediaInfo dạng đoán: codec, độ phân giải, fps, bitrate, âm thanh,
phụ đề, thời lượng, dung lượng... đều lấy trực tiếp từ file.

Chạy độc lập:
    python 07_media_info.py video.mp4            # In bảng thông số tiếng Việt
    python 07_media_info.py video.mp4 --json     # In dict đã chuẩn hoá (JSON)

Dùng trong code khác:
    from media_info import get_media_info, format_media_info
    info = get_media_info("video.mp4")
    print(format_media_info(info))
    print(info["video"]["width"], info["video"]["fps"])

Ghi chú về VLC / K-Lite (đọc trước khi hỏi):
  - K-Lite Codec Pack KHÔNG tích hợp được vào tool: nó là gói codec
    cài vào Windows để các trình phát hệ thống chơi được nhiều định
    dạng hơn, không có API cho Python. Tool không cần nó vì ffmpeg
    đã giải mã được gần như mọi định dạng.
  - VLC chỉ dùng cho PHẦN XEM TRƯỚC (08_preview.py), không dùng để
    đọc thông số — ffprobe ở đây mới là nguồn thông số chính xác.
"""
import json
import os
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path


def ffprobe_available():
    """True nếu máy có ffprobe (đi kèm ffmpeg)."""
    return shutil.which("ffprobe") is not None


def _fmt_size(n):
    n = int(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TB"


def _fmt_bitrate(bps):
    bps = int(bps or 0)
    if bps <= 0:
        return "không rõ"
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.2f} Mbps"
    return f"{bps / 1_000:.0f} kbps"


def _fmt_duration(sec):
    try:
        sec = float(sec or 0)
    except (TypeError, ValueError):
        return "không rõ"
    if sec <= 0:
        return "không rõ"
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    frac = sec - int(sec)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}.{int(frac * 10)}"


def _parse_fps(stream):
    """Đọc fps từ avg_frame_rate (dạng '30000/1001'), rớt về r_frame_rate."""
    for key in ("avg_frame_rate", "r_frame_rate"):
        raw = (stream.get(key) or "0/0").strip()
        try:
            f = float(Fraction(raw))
            if f > 0:
                return f
        except (ValueError, ZeroDivisionError):
            continue
    return 0.0


def _first_video(streams):
    for s in streams:
        if s.get("codec_type") == "video":
            return s
    return None


def get_media_info(path):
    """
    Đọc thông số video bằng ffprobe. Trả về dict đã chuẩn hoá.
    Lỗi (không có ffprobe / file không phải video) -> RuntimeError tiếng Việt.
    """
    path = Path(path)
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy file: {path}")
    if not ffprobe_available():
        raise RuntimeError("Không tìm thấy ffprobe trên máy. Cài ffmpeg rồi chạy lại "
                           "(ffprobe đi kèm ffmpeg).")
    cmd = ["ffprobe", "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", "-show_chapters", str(path)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffprobe chạy quá 60 giây, bỏ qua file này.")
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(f"ffprobe không đọc được file này (có thể không phải video): {path}")
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError("ffprobe trả về dữ liệu lỗi, không đọc được thông số.")

    fmt = data.get("format") or {}
    streams = data.get("streams") or []
    chapters = data.get("chapters") or []
    video = _first_video(streams)

    def _num(*keys, default=0):
        for src in (video, fmt):
            if src is None:
                continue
            for k in keys:
                v = src.get(k)
                if v not in (None, "", "N/A"):
                    try:
                        return int(float(v))
                    except (TypeError, ValueError):
                        continue
        return default

    duration = 0.0
    for src in (fmt, video):
        if src and src.get("duration"):
            try:
                duration = float(src["duration"])
                break
            except (TypeError, ValueError):
                pass

    audios = []
    subs = []
    for s in streams:
        if s.get("codec_type") == "audio":
            tags = s.get("tags") or {}
            audios.append({
                "codec": s.get("codec_name", "?"),
                "codec_long": s.get("codec_long_name", ""),
                "sample_rate": int(s.get("sample_rate") or 0),
                "channels": int(s.get("channels") or 0),
                "channel_layout": s.get("channel_layout", ""),
                "bitrate": int(s.get("bit_rate") or 0),
                "language": tags.get("language", ""),
                "title": tags.get("title", ""),
            })
        elif s.get("codec_type") == "subtitle":
            tags = s.get("tags") or {}
            subs.append({
                "codec": s.get("codec_name", "?"),
                "language": tags.get("language", ""),
                "title": tags.get("title", ""),
            })

    info = {
        "file": str(path),
        "name": path.name,
        "size": int(fmt.get("size") or path.stat().st_size),
        "size_h": _fmt_size(fmt.get("size") or path.stat().st_size),
        "format": fmt.get("format_name", "?"),
        "format_long": fmt.get("format_long_name", ""),
        "duration": duration,
        "duration_h": _fmt_duration(duration),
        "bitrate": int(fmt.get("bit_rate") or 0),
        "bitrate_h": _fmt_bitrate(fmt.get("bit_rate") or 0),
        "streams_count": len(streams),
        "chapters": len(chapters),
        "video": None,
        "audio": audios,
        "subtitles": subs,
    }
    if video is not None:
        fps = _parse_fps(video)
        info["video"] = {
            "codec": video.get("codec_name", "?"),
            "codec_long": video.get("codec_long_name", ""),
            "profile": video.get("profile", ""),
            "level": video.get("level", ""),
            "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0),
            "fps": round(fps, 2),
            "fps_h": f"{fps:.2f}" if fps else "không rõ",
            "bitrate": int(video.get("bit_rate") or 0),
            "bitrate_h": _fmt_bitrate(video.get("bit_rate") or 0),
            "pix_fmt": video.get("pix_fmt", ""),
            "color_space": video.get("color_space", ""),
            "color_range": video.get("color_range", ""),
            "color_transfer": video.get("color_transfer", ""),
            "field_order": video.get("field_order", ""),
            "duration": float(video.get("duration") or 0),
        }
    return info


def summary_line(info):
    """1 dòng tóm tắt: 1920x1080 • 30.00 fps • H.264 • 64.0s • 12.3 MB • AAC stereo."""
    v = info.get("video") or {}
    parts = []
    if v.get("width") and v.get("height"):
        parts.append(f"{v['width']}x{v['height']}")
    if v.get("fps"):
        parts.append(f"{v['fps_h']} fps")
    if v.get("codec"):
        parts.append(v["codec"].upper())
    if info.get("duration"):
        parts.append(f"{info['duration']:.1f}s")
    if info.get("size"):
        parts.append(info["size_h"])
    if info.get("audio"):
        a0 = info["audio"][0]
        parts.append(f"{a0['codec'].upper()} {a0.get('channel_layout') or (str(a0['channels']) + ' kênh')}")
    return " • ".join(parts) if parts else "Không đọc được thông số video."


def format_media_info(info):
    """Bảng thông số tiếng Việt, đọc được ngay (dùng cho GUI + CLI)."""
    L = []
    L.append("========== THÔNG SỐ VIDEO ==========")
    L.append(f"File       : {info['name']} ({info['size_h']})")
    L.append(f"Định dạng  : {info['format_long'] or info['format']}")
    L.append(f"Thời lượng : {info['duration_h']} ({info['duration']:.1f} giây)")
    L.append(f"Bitrate    : {info['bitrate_h']}")
    L.append(f"Luồng      : {info['streams_count']} (video {1 if info['video'] else 0} + "
             f"âm thanh {len(info['audio'])} + phụ đề {len(info['subtitles'])})")
    v = info.get("video")
    if v:
        L.append("---------- VIDEO ----------")
        codec = v["codec_long"] or v["codec"]
        prof = f", {v['profile']}" if v.get("profile") else ""
        lvl = f", level {v['level']}" if v.get("level") else ""
        L.append(f"Codec      : {codec}{prof}{lvl}")
        L.append(f"Kích thước : {v['width']}x{v['height']}")
        L.append(f"FPS        : {v['fps_h']}")
        L.append(f"Bitrate    : {v['bitrate_h']}")
        pix = v.get("pix_fmt") or "?"
        color = " | ".join(x for x in (v.get("color_space"), v.get("color_range")) if x)
        L.append(f"Pixel fmt  : {pix}" + (f" | Màu: {color}" if color else ""))
        if v.get("field_order"):
            L.append(f"Quét hình  : {v['field_order']}")
    else:
        L.append("---------- VIDEO ----------")
        L.append("Không có luồng video (file này chỉ có âm thanh?).")
    for i, a in enumerate(info["audio"], 1):
        L.append(f"---------- ÂM THANH #{i} ----------")
        L.append(f"Codec      : {a['codec_long'] or a['codec']}")
        sr = f"{a['sample_rate']} Hz" if a.get("sample_rate") else "?"
        ch = a.get("channel_layout") or (f"{a['channels']} kênh" if a.get("channels") else "?")
        L.append(f"Tần số     : {sr} | Kênh: {ch}")
        L.append(f"Bitrate    : {_fmt_bitrate(a.get('bitrate'))}"
                 + (f" | Ngôn ngữ: {a['language']}" if a.get("language") else "")
                 + (f" | Tên: {a['title']}" if a.get("title") else ""))
    if info["subtitles"]:
        L.append("---------- PHỤ ĐỀ ----------")
        for i, s in enumerate(info["subtitles"], 1):
            L.append(f"#{i}: {s['codec']}"
                     + (f" | Ngôn ngữ: {s['language']}" if s.get("language") else "")
                     + (f" | Tên: {s['title']}" if s.get("title") else ""))
    else:
        L.append("Phụ đề     : không có")
    if info.get("chapters"):
        L.append(f"Chapters   : {info['chapters']}")
    L.append("====================================")
    return "\n".join(L)


def analyze_comparison(info, cfg, index=0, img_path=None, stk_path=None, done_info=None):
    """
    Phân tích & đối chiếu trực tiếp giữa VIDEO NGUỒN (info) và ĐẦU RA (dự kiến
    hoặc file đã xuất thực tế `done_info`), trả về dict cấu trúc rõ ràng gồm:
      - rows: list tuple (Tiêu chí, Nguồn, Đầu ra, Thay đổi / Đánh giá)
      - conclusions: list chuỗi kết luận thông minh giúp người dùng nhìn vào
        biết ngay kết quả đã đạt hay có điểm nào cần lưu ý.
    """
    from common import (FRAME_916_H, FRAME_916_W, MIN_BITRATE_BPS,
                        resolve_sticker_position, resolve_target_bitrate)

    v = info.get("video") or {}
    src_w = int(v.get("width") or 0)
    src_h = int(v.get("height") or 0)
    src_fps = float(v.get("fps") or 30.0)
    src_dur = float(info.get("duration") or 0.0)
    src_br = int(v.get("bitrate") or info.get("bitrate") or 0)
    src_size = int(info.get("size") or 0)
    src_vcodec = (v.get("codec") or "?").upper()
    has_audio = bool(info.get("audio"))
    src_acodec = (info["audio"][0].get("codec", "?").upper()
                  if has_audio else "Không có audio")
    src_abr = int(info["audio"][0].get("bitrate") or 128_000) if has_audio else 0

    speed_on = bool(cfg.get("speed_on", True))
    speed = float(cfg.get("speed", 1.2) or 1.2) if speed_on else 1.0
    if speed <= 0:
        speed = 1.0
    mirror = bool(cfg.get("mirror", True))
    frame_916 = bool(cfg.get("frame_916", True))
    v_scale = float(cfg.get("video_scale", 0.94) or 0.94)
    v_pos = cfg.get("video_position", "center")
    v_dx = int(round(float(cfg.get("video_left", 0) or 0) - float(cfg.get("video_right", 0) or 0)))
    v_dy = int(round(float(cfg.get("video_top", 0) or 0) - float(cfg.get("video_bottom", 0) or 0)))

    image_on = bool(cfg.get("image_on", True))
    image_mode = cfg.get("image_mode", "corner")
    sticker_on = bool(cfg.get("sticker_on", True))
    s_scale = float(cfg.get("sticker_scale", 0.15) or 0.15)
    s_pos_cfg = cfg.get("sticker_position", "auto-corners")
    s_pos = resolve_sticker_position(s_pos_cfg, index=index)
    s_dx = int(round(float(cfg.get("sticker_left", 0) or 0) - float(cfg.get("sticker_right", 0) or 0)))
    s_dy = int(round(float(cfg.get("sticker_top", 0) or 0) - float(cfg.get("sticker_bottom", 0) or 0)))

    q_mode = cfg.get("quality_mode", "source") or "source"
    q_val = (cfg.get("quality_value") or "").strip()
    enc = cfg.get("encoder", "auto") or "auto"
    chunk_on = bool(cfg.get("chunk", True))
    chunk_sec = int(cfg.get("chunk_seconds", 300) or 300)
    sil_on = bool(cfg.get("sil_batch", True))

    # --- Tính thông số đầu ra ---
    if done_info and done_info.get("video"):
        dv = done_info["video"]
        out_w, out_h = int(dv.get("width") or 0), int(dv.get("height") or 0)
        out_fps = float(dv.get("fps") or src_fps)
        out_dur = float(done_info.get("duration") or 0.0)
        out_br = int(dv.get("bitrate") or done_info.get("bitrate") or 0)
        out_size = int(done_info.get("size") or 0)
        out_vcodec = f"{(dv.get('codec') or 'H264').upper()} ({done_info.get('name', 'File đầu ra')})"
        if done_info.get("audio"):
            da = done_info["audio"][0]
            out_acodec = f"{da.get('codec', 'AAC').upper()} ({_fmt_bitrate(da.get('bitrate'))})"
        else:
            out_acodec = "Không có audio"
        is_actual = True
    else:
        is_actual = False
        out_fps = src_fps
        out_w, out_h = (FRAME_916_W, FRAME_916_H) if frame_916 else (src_w, src_h)
        out_dur = src_dur / speed if speed else src_dur
        target_bps, crf = resolve_target_bitrate(q_mode, q_val, {"bitrate": src_br})
        if target_bps:
            out_br = target_bps
        else:
            # Ước lượng bitrate theo CRF để dự tính dung lượng
            crf_val = crf if crf is not None else 20
            base_bps = src_br if src_br > 0 else 3_500_000
            out_br = max(MIN_BITRATE_BPS, int(base_bps * (1.12 ** (20 - crf_val))))
        total_bps = out_br + (128_000 if (has_audio and abs(speed - 1.0) > 0.001) else src_abr)
        out_size = int(out_dur * total_bps / 8) if out_dur > 0 else 0
        out_vcodec = f"H.264 ({enc})"
        out_acodec = ("AAC 128k (encode lại theo speed)"
                      if (has_audio and abs(speed - 1.0) > 0.001)
                      else (f"{src_acodec} (copy giữ nguyên)" if has_audio else "Không có audio"))

    # Tính kích thước khung video con bên trong 1080x1920
    if frame_916 and src_w > 0 and src_h > 0:
        box_w = int(FRAME_916_W * v_scale)
        box_h = int(FRAME_916_H * v_scale)
        ratio = min(box_w / src_w, box_h / src_h)
        fg_w = max(2, int(round(src_w * ratio)))
        fg_h = max(2, int(round(src_h * ratio)))
    else:
        fg_w, fg_h = src_w, src_h

    # Tỉ lệ khung hình
    def _aspect_label(w, h):
        if w <= 0 or h <= 0:
            return "?"
        r = w / h
        if abs(r - 9 / 16) < 0.03:
            return "9:16 (Dọc)"
        if abs(r - 16 / 9) < 0.03:
            return "16:9 (Ngang)"
        if abs(r - 1.0) < 0.03:
            return "1:1 (Vuông)"
        return f"{r:.2f}:1"

    dur_diff = out_dur - src_dur
    dur_pct = (dur_diff / src_dur * 100) if src_dur > 0 else 0.0
    size_diff = out_size - src_size
    size_pct = (size_diff / src_size * 100) if src_size > 0 else 0.0

    rows = [
        (
            "Trạng thái đối chiếu",
            f"Video nguồn #{index + 1}",
            "File thực tế trong thư mục ra" if is_actual else "Mô phỏng đầu ra theo cấu hình",
            "✔ Đã có file xuất thực tế" if is_actual else "⚡ Dự tính trực tiếp trước khi render",
        ),
        (
            "Độ phân giải & Khung",
            f"{src_w}×{src_h} ({_aspect_label(src_w, src_h)})",
            f"{out_w}×{out_h} ({_aspect_label(out_w, out_h)})",
            (f"Khung 9:16 • Video con {fg_w}×{fg_h} ({int(v_scale*100)}%)"
             if frame_916 else "Giữ nguyên kích thước gốc"),
        ),
        (
            "Vị trí & Tọa độ Video",
            "Gốc (0, 0)",
            (f"Neo: {v_pos} | Dịch: X={v_dx:+d}px, Y={v_dy:+d}px"
             if frame_916 else "Toàn khung (không dịch)"),
            ("Đã dịch tọa độ thủ công" if (frame_916 and (v_dx or v_dy))
             else ("Căn chuẩn theo neo " + v_pos if frame_916 else "Mặc định")),
        ),
        (
            "Thời lượng & Tốc độ",
            f"{_fmt_duration(src_dur)} ({src_dur:.1f}s) • 1.00x",
            f"{_fmt_duration(out_dur)} ({out_dur:.1f}s) • {speed:.2f}x",
            (f"{dur_diff:+.1f}s ({dur_pct:+.0f}%)"
             + (" • Có quét cắt im" if (sil_on and not is_actual) else "")),
        ),
        (
            "Lật hình (Mirror)",
            "Không (Gốc)",
            "BẬT (hflip lật ngang)" if mirror else "TẮT (Giữ nguyên)",
            "Đảo chiều ngang chống bản quyền" if mirror else "Giữ nguyên chiều gốc",
        ),
        (
            "Ảnh nền / Ảnh ghép",
            "Không có",
            (f"{Path(img_path).name} ({'Nền 9:16' if frame_916 else image_mode})"
             if (image_on and img_path)
             else ("Nền đen 9:16 (chưa có ảnh)" if frame_916 else "TẮT")),
            ("✔ Đã ghép ảnh nền lấp đầy 1080×1920" if (frame_916 and image_on and img_path)
             else ("⚠ Thiếu ảnh nền -> dùng nền đen" if (frame_916 and image_on and not img_path)
                   else ("✔ Ghép chế độ " + image_mode if (image_on and img_path) else "Không dùng ảnh"))),
        ),
        (
            "Sticker & Góc đặt",
            "Không có",
            (f"{Path(stk_path).name} @ {s_pos} (cỡ {int(s_scale*100)}%, X={s_dx:+d}, Y={s_dy:+d})"
             if (sticker_on and stk_path) else "TẮT / Chưa có sticker"),
            (f"Auto đảo 4 góc -> Góc video #{index + 1}: {s_pos}"
             if (sticker_on and stk_path and s_pos_cfg == "auto-corners")
             else (f"Cố định tại {s_pos}" if (sticker_on and stk_path) else "Không ghép sticker")),
        ),
        (
            "Video Codec & FPS",
            f"{src_vcodec} • {src_fps:.2f} fps",
            f"{out_vcodec} • {out_fps:.2f} fps",
            (f"Thay đổi FPS: {out_fps - src_fps:+.2f} fps"
             if (is_actual and abs(out_fps - src_fps) > 0.05)
             else "Giữ nguyên FPS mượt mà"),
        ),
        (
            "Bitrate hình ảnh",
            _fmt_bitrate(src_br),
            _fmt_bitrate(out_br) + ("" if is_actual else f" ({q_mode})"),
            ("Nâng lên sàn an toàn 800 kbps (tránh bệt màu)"
             if (0 < src_br < MIN_BITRATE_BPS and out_br >= MIN_BITRATE_BPS)
             else ("Giữ tương đương bitrate gốc" if q_mode == "source" else f"Chế độ {q_mode} {q_val}")),
        ),
        (
            "Âm thanh (Audio)",
            f"{src_acodec} ({_fmt_bitrate(src_abr)})" if has_audio else "Không có",
            out_acodec,
            ("Tự động khớp cao độ (atempo) theo speed"
             if (has_audio and abs(speed - 1.0) > 0.001)
             else ("Copy nguyên gốc không giảm chất lượng" if has_audio else "Video câm (-an)")),
        ),
        (
            "Dung lượng file",
            _fmt_size(src_size),
            _fmt_size(out_size) + ("" if is_actual else " (ước tính)"),
            f"{size_pct:+.0f}% so với file gốc" if src_size > 0 else "-",
        ),
        (
            "Chế độ Chia đoạn",
            "1 file liền",
            (f"Chia mỗi {chunk_sec}s (~{max(1, int((src_dur + chunk_sec - 1) // chunk_sec))} đoạn)"
             if (chunk_on and src_dur > chunk_sec)
             else f"Xử lý 1 lần (video ≤ {chunk_sec}s)"),
            ("Tự chia đoạn & hỗ trợ Resume nếu dừng giữa chừng"
             if (chunk_on and src_dur > chunk_sec)
             else "Encode liền mạch 1 lần"),
        ),
    ]

    # --- Tổng hợp nhận xét & kết luận thông minh ---
    conclusions = []
    if frame_916:
        if src_w > src_h:
            conclusions.append(
                f"• [BỐ CỤC 9:16] Video gốc là video NGANG ({src_w}×{src_h}) -> Khi đưa vào khung dọc 1080×1920 "
                f"(tỉ lệ {int(v_scale*100)}%), video con hiển thị kích thước {fg_w}×{fg_h} ở vị trí '{v_pos}', "
                f"phần trên/dưới sẽ lộ {'ảnh nền ' + Path(img_path).name if (image_on and img_path) else 'nền đen'}."
            )
        else:
            conclusions.append(
                f"• [BỐ CỤC 9:16] Video gốc là video DỌC ({src_w}×{src_h}) -> Phủ {int(v_scale*100)}% khung 1080×1920 "
                f"(kích thước {fg_w}×{fg_h}), viền xung quanh lộ {'ảnh nền ' + Path(img_path).name if (image_on and img_path) else 'nền đen'} rất cân đối."
            )
        # Kiểm tra tràn khung nếu dịch tọa độ quá lớn
        avail_x = (FRAME_916_W - fg_w) // 2
        avail_y = (FRAME_916_H - fg_h) // 2
        if v_pos == "center" and (abs(v_dx) > avail_x + 20 or abs(v_dy) > avail_y + 20):
            conclusions.append(
                f"• [CẢNH BÁO TỌA ĐỘ VIDEO] Tọa độ dịch video (X={v_dx:+d}px, Y={v_dy:+d}px) vượt khoảng trống viền "
                f"(±{avail_x}px ngang, ±{avail_y}px dọc) -> Một phần video sẽ bị tràn ra ngoài khung 1080×1920!"
            )
    else:
        conclusions.append(
            f"• [GIỮ KHUNG GỐC] Đang tắt Khung 9:16 -> Video xuất ra giữ nguyên độ phân giải {src_w}×{src_h}."
        )

    if sticker_on and stk_path:
        conclusions.append(
            f"• [STICKER] Video #{index + 1} ghép với '{Path(stk_path).name}' đặt tại góc '{s_pos}' "
            f"(rộng ~{int(out_w * s_scale)}px, dịch X={s_dx:+d}px, Y={s_dy:+d}px)."
        )
    elif sticker_on and not stk_path:
        conclusions.append(
            "• [CẢNH BÁO STICKER] Đang bật ghép Sticker nhưng chưa có file sticker trong thư mục -> Cần chọn thư mục sticker hoặc tắt ghép sticker."
        )

    if src_dur > 0:
        saved = src_dur - out_dur
        conclusions.append(
            f"• [THỜI LƯỢNG] Tốc độ {speed:.2f}x giúp rút ngắn {saved:.1f} giây (từ {_fmt_duration(src_dur)} xuống còn {_fmt_duration(out_dur)})"
            + (" — chưa tính phần rút ngắn thêm nhờ Cắt khoảng im tự động." if sil_on and not is_actual else ".")
        )

    if not has_audio and sil_on:
        conclusions.append(
            "• [LƯU Ý ÂM THANH] Video gốc KHÔNG có luồng âm thanh -> Bước Cắt khoảng im sẽ tự động bỏ qua và giữ nguyên hình."
        )

    if is_actual:
        actual_speed = (src_dur / out_dur) if out_dur > 0 else 1.0
        conclusions.insert(
            0,
            f"• [ĐỐI CHIẾU FILE ĐẦU RA THỰC TẾ] Đang so sánh trực tiếp Video Gốc '{info.get('name', '')}' "
            f"với Video Đầu Ra '{done_info.get('name', '')}': Độ phân giải {src_w}×{src_h} -> {out_w}×{out_h}, "
            f"Thời lượng {src_dur:.1f}s -> {out_dur:.1f}s ({dur_diff:+.1f}s, tốc độ thực tế ~{actual_speed:.2f}x), "
            f"Bitrate {_fmt_bitrate(src_br)} -> {_fmt_bitrate(out_br)}, Dung lượng {_fmt_size(src_size)} -> {_fmt_size(out_size)} ({size_pct:+.0f}%)."
        )
    else:
        conclusions.append(
            "• [KẾT LUẬN TỔNG QUAN] Đang xem thông số Video GỐC và bảng đối chiếu cấu hình dự kiến. Bạn có thể bấm '[📥 Import video đầu ra để so sánh]' ở khung bên cạnh để đối chiếu trực tiếp với 1 file đã xuất bất kỳ."
        )

    return {
        "is_actual": is_actual,
        "rows": rows,
        "conclusions": conclusions,
        "out_width": out_w,
        "out_height": out_h,
        "out_duration": out_dur,
        "out_bitrate": out_br,
        "out_size": out_size,
        "sticker_corner": s_pos,
    }


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="Xem thông số chi tiết của video (ffprobe)")
    p.add_argument("video", help="File video cần xem thông số")
    p.add_argument("--json", action="store_true", help="In dict đã chuẩn hoá dạng JSON")
    a = p.parse_args(argv)
    try:
        info = get_media_info(a.video)
    except RuntimeError as e:
        print(f"[LỖI] {e}")
        return 1
    if a.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(format_media_info(info))
        print("Tóm tắt     : " + summary_line(info))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
