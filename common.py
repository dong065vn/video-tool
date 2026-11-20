#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
common.py — Hàm dùng chung cho các tool riêng lẻ.
KHÔNG chứa quy trình, KHÔNG tự chạy bước nào khác.
Mỗi tool chỉ import những hàm nó cần.
"""
import json
import os
import random
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arial.ttf",
]


def ensure_ffmpeg_path():
    """Giữ bản FFmpeg đã probe; chỉ tìm bản cục bộ khi PATH chưa có."""
    if not sys.platform.startswith("win"):
        return
    selected = os.environ.get("VIDEO_TOOL_FFMPEG_DIR", "")
    if selected and (Path(selected) / "ffmpeg.exe").is_file():
        bin_dir = selected
    elif shutil.which("ffmpeg"):
        return
    else:
        local_app = os.environ.get("LOCALAPPDATA", "")
        root = Path(local_app) / "Programs" / "ffmpeg" if local_app else None
        if not root or not root.is_dir():
            return
        candidates = list(root.glob("modern/**/ffmpeg.exe"))
        if not candidates:
            candidates = list(root.glob("**/ffmpeg.exe"))
        if not candidates:
            return
        bin_dir = str(candidates[0].parent)
    parts = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    norm = os.path.normcase(bin_dir.rstrip("\\/"))
    parts = [p for p in parts if os.path.normcase(p.rstrip("\\/")) != norm]
    os.environ["PATH"] = os.pathsep.join([bin_dir] + parts)


ensure_ffmpeg_path()


def check_ffmpeg():
    ensure_ffmpeg_path()
    missing = [name for name in ("ffmpeg", "ffprobe")
               if shutil.which(name) is None]
    if missing:
        raise RuntimeError(
            f"Không tìm thấy {', '.join(missing)}. Hãy chạy setup_python.bat."
        )


def _format_command(cmd):
    return " ".join(
        f'"{part}"' if " " in str(part) else str(part) for part in cmd
    )


def run(cmd, dry_run=False, log=print, progress=None, duration=None):
    """Chạy lệnh, ghi command/thời gian/lỗi và phát tiến độ FFmpeg thực."""
    cmd = [str(part) for part in cmd]
    log(f"[CMD] {_format_command(cmd)}")
    if dry_run:
        return None
    tracked_cmd = cmd
    if progress and Path(cmd[0]).name.lower().startswith("ffmpeg"):
        tracked_cmd = cmd[:1] + ["-progress", "pipe:1", "-nostats"] + cmd[1:]

    started = time.monotonic()
    proc = subprocess.Popen(
        tracked_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    tail = deque(maxlen=80)
    last_percent = -1
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip()
        if line:
            tail.append(line)
        if not progress or not duration:
            continue
        elapsed_us = None
        if line.startswith("out_time_us="):
            elapsed_us = line.partition("=")[2]
        elif line.startswith("out_time_ms="):
            elapsed_us = line.partition("=")[2]
        if elapsed_us:
            try:
                percent = min(99, int(float(elapsed_us) / 1_000_000
                                      / float(duration) * 100))
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            if percent > last_percent:
                last_percent = percent
                progress(percent)
        elif line == "progress=end":
            progress(100)

    returncode = proc.wait()
    elapsed = time.monotonic() - started
    output = "\n".join(tail)
    if returncode != 0:
        log(f"[LỖI] Lệnh thất bại (exit {returncode}, {elapsed:.1f}s).")
        for line in list(tail)[-20:]:
            log(f"[FFMPEG] {line}")
        raise RuntimeError(f"ffmpeg/ffprobe thất bại: {cmd[0]}")
    log(f"[CMD] Hoàn tất sau {elapsed:.1f}s.")
    return subprocess.CompletedProcess(cmd, returncode, output, "")


def get_info(path: Path) -> dict:
    """Chỉ đọc thông tin video, không xử lý gì thêm."""
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json",
           "-show_format", "-show_streams", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Không đọc được file: {path}\n{result.stderr}")
    data = json.loads(result.stdout)
    info = {"duration": 0.0, "width": 0, "height": 0, "fps": 0.0,
            "vcodec": "", "acodec": "", "has_audio": False, "has_video": False,
            "bitrate": 0, "container_bitrate": 0, "audio_bitrate": 0,
            "file_size": 0}
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            info["has_video"] = True
            info["width"] = int(s.get("width", 0))
            info["height"] = int(s.get("height", 0))
            info["vcodec"] = s.get("codec_name", "")
            try:
                info["bitrate"] = int(s.get("bit_rate", 0) or 0)
            except (ValueError, TypeError):
                pass
            num, _, den = s.get("avg_frame_rate", "0/1").partition("/")
            try:
                if float(den) != 0:
                    info["fps"] = float(num) / float(den)
            except ValueError:
                pass
        elif s.get("codec_type") == "audio":
            info["has_audio"] = True
            info["acodec"] = s.get("codec_name", "")
            try:
                info["audio_bitrate"] = int(s.get("bit_rate", 0) or 0)
            except (ValueError, TypeError):
                pass
    fmt = data.get("format", {}) or {}
    try:
        info["duration"] = float(fmt.get("duration", 0) or 0)
    except ValueError:
        pass
    try:
        info["container_bitrate"] = int(fmt.get("bit_rate", 0) or 0)
    except (ValueError, TypeError):
        pass
    try:
        info["file_size"] = int(fmt.get("size", 0) or Path(path).stat().st_size)
    except (ValueError, TypeError, OSError):
        pass

    # Nhiều file (.mkv, .webm, hoặc đoạn cắt segment) không ghi stream bit_rate.
    # Khi đó suy ra bitrate video từ container_bitrate hoặc (file_size * 8 / duration).
    if info["bitrate"] <= 0:
        total_bps = info["container_bitrate"]
        if total_bps <= 0 and info["duration"] > 0 and info["file_size"] > 0:
            total_bps = int(info["file_size"] * 8 / info["duration"])
        if total_bps > 0:
            abps = info["audio_bitrate"] or (128_000 if info["has_audio"] else 0)
            info["bitrate"] = max(1, total_bps - abps)
    return info


def find_font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    for base in ["/usr/share/fonts", "/usr/local/share/fonts"]:
        if os.path.isdir(base):
            for root, _, files in os.walk(base):
                for f in files:
                    if f.lower().endswith((".ttf", ".otf")) and "sans" in f.lower():
                        return os.path.join(root, f)
    return None


def format_info_line(path, info: dict) -> str:
    """Dòng [INFO] mô tả 1 video từ dict info đã đọc (không gọi ffprobe lại)."""
    br = f", {info['bitrate']/1000:.0f}kbps" if info.get("bitrate") else ""
    return (f"[INFO] {Path(path).name}: {info['width']}x{info['height']}, "
            f"{info['fps']:.2f}fps, {info['duration']:.1f}s, "
            f"v={info['vcodec']} a={info['acodec'] or 'không có audio'}{br}")


def print_info(path: Path, log=print):
    info = get_info(path)
    log(format_info_line(path, info))
    return info


# ---------------------------------------------------------------------------
# Bitrate / chất lượng — giữ nguyên chất lượng, chỉnh bitrate tùy ý
# ---------------------------------------------------------------------------
def parse_bitrate(text) -> int:
    """'8M' -> 8000000, '8000k' -> 8000000, 8000000 -> 8000000."""
    if isinstance(text, (int, float)):
        return int(text)
    t = str(text).strip().lower().replace("bps", "")
    if not t:
        return 0
    mult = 1
    if t.endswith("m"):
        mult, t = 1_000_000, t[:-1]
    elif t.endswith("k"):
        mult, t = 1_000, t[:-1]
    try:
        return int(float(t) * mult)
    except ValueError:
        raise ValueError(f"Bitrate không hợp lệ: {text!r}. VD: 8M, 4000k.")


def format_bitrate(bps: int) -> str:
    if bps >= 1_000_000:
        return f"{bps/1_000_000:g}M"
    return f"{bps//1000}k"


# Bitrate tối thiểu: video nguồn có bitrate quá thấp (VD: 13kbps vì toàn màu
# trơn) thì giữ nguyên sẽ làm video ra bị xám/mất màu vì không đủ bit.
MIN_BITRATE_BPS = 800_000


def resolve_target_bitrate(quality_mode: str, quality_value: str, info: dict):
    """
    quality_mode: 'source' (bitrate gốc) | 'bitrate' (nhập tay) | 'crf'.
    Trả về (target_bps | None, crf | None).
    Bitrate đích không bao giờ dưới MIN_BITRATE_BPS (trừ CRF).
    """
    if quality_mode == "crf":
        try:
            crf = int(quality_value)
        except (ValueError, TypeError):
            crf = 20
        return None, max(0, min(51, crf))
    if quality_mode == "bitrate":
        bps = parse_bitrate(quality_value)
        if bps <= 0:
            bps = info.get("bitrate") or 5_000_000
        return max(bps, MIN_BITRATE_BPS), None
    # source: giữ bitrate gốc của video
    bps = info.get("bitrate") or 0
    if bps <= 0:
        return None, 20  # Không đọc được bitrate gốc -> dùng CRF 20
    return max(bps, MIN_BITRATE_BPS), None


def encode_args(encoder: str, quality_mode: str, quality_value: str,
                preset: str, threads: int, info: dict):
    """
    Trả về list tham số encode video H.264 cho ffmpeg.
    - libx264: CRF hoặc -b:v/-maxrate/-bufsize.
    - h264_nvenc: -cq (CRF tương đương) hoặc -b:v VBR.
    - h264_qsv: -global_quality hoặc -b:v.
    - h264_amf: -qp (CQP) hoặc -b:v VBR.
    - h264_vaapi: -b:v (luôn dùng bitrate, cần hwupload trong filter).
    """
    target_bps, crf = resolve_target_bitrate(quality_mode, quality_value, info)
    args = []
    if encoder == "libx264":
        args += ["-c:v", "libx264", "-preset", preset, "-pix_fmt", "yuv420p"]
        if target_bps:
            args += ["-b:v", format_bitrate(target_bps),
                     "-maxrate", format_bitrate(int(target_bps * 1.25)),
                     "-bufsize", format_bitrate(target_bps * 2)]
        else:
            args += ["-crf", str(crf)]
        args += ["-threads", str(max(1, threads))]
    elif encoder == "h264_nvenc":
        args += ["-c:v", "h264_nvenc", "-preset", preset, "-pix_fmt", "yuv420p"]
        if target_bps:
            args += ["-b:v", format_bitrate(target_bps),
                     "-maxrate", format_bitrate(int(target_bps * 1.25)),
                     "-bufsize", format_bitrate(target_bps * 2)]
        else:
            args += ["-rc", "vbr", "-cq", str(crf)]
    elif encoder == "h264_qsv":
        args += ["-c:v", "h264_qsv", "-preset", preset]
        if target_bps:
            args += ["-b:v", format_bitrate(target_bps),
                     "-maxrate", format_bitrate(int(target_bps * 1.25)),
                     "-bufsize", format_bitrate(target_bps * 2)]
        else:
            args += ["-global_quality", str(crf)]
    elif encoder == "h264_amf":
        args += ["-c:v", "h264_amf", "-quality", preset]
        if target_bps:
            args += ["-rc", "vbr", "-b:v", format_bitrate(target_bps),
                     "-maxrate", format_bitrate(int(target_bps * 1.25)),
                     "-bufsize", format_bitrate(target_bps * 2)]
        else:
            args += ["-rc", "cqp", "-qp", str(crf)]
    elif encoder == "h264_vaapi":
        args += ["-c:v", "h264_vaapi"]
        if target_bps:
            args += ["-b:v", format_bitrate(target_bps),
                     "-maxrate", format_bitrate(int(target_bps * 1.25)),
                     "-bufsize", format_bitrate(target_bps * 2)]
        else:
            args += ["-b:v", "5M"]
    else:  # encoder lạ -> về libx264 cho an toàn
        args += ["-c:v", "libx264", "-preset", preset, "-pix_fmt", "yuv420p",
                 "-crf", str(crf if crf is not None else 20)]
    return args


# ---------------------------------------------------------------------------
# Import folder + ghép cặp
# ---------------------------------------------------------------------------
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
STICKER_EXTS = {".png", ".webp"}  # sticker cần kênh alpha


def list_files(folder: Path, exts):
    if not folder or not Path(folder).is_dir():
        return []
    out = [p for p in sorted(Path(folder).iterdir())
           if p.is_file() and p.suffix.lower() in exts]
    return out


def pair_files(videos, others, mode="order", seed=0):
    """
    Ghép từng video với 1 file khác (ảnh / sticker) theo thứ tự.
    - order: xếp theo tên file, video 1 <-> ảnh 1, video 2 <-> ảnh 2...
    - shuffle: xáo trộn thứ tự file ghép (seed cố định để lặp lại được).
    - Nếu ít file ghép hơn video thì lặp lại từ đầu (có ghi log ở nơi gọi).
    Trả về list (video, file_ghep | None).
    """
    others = list(others or [])
    if mode == "shuffle" and len(others) > 1:
        rnd = random.Random(seed)
        others = others[:]
        rnd.shuffle(others)
    pairs = []
    for i, v in enumerate(videos):
        o = others[i % len(others)] if others else None
        pairs.append((v, o))
    return pairs


def vf_for_encoder(vf_chain: str, encoder: str) -> str:
    """Thêm hwupload cho VAAPI, các encoder khác giữ nguyên.
    VAAPI cần format=nv12 TRƯỚC hwupload, nên đổi format=yuv420p
    thành format=nv12 thay vì xếp 2 filter format liên tiếp."""
    if encoder == "h264_vaapi":
        if "format=yuv420p" in vf_chain:
            return vf_chain.replace("format=yuv420p", "format=nv12,hwupload")
        return vf_chain + ",format=nv12,hwupload"
    return vf_chain


def atempo_chain(speed: float):
    """Tách speed thành chuỗi atempo (mỗi atempo tối đa 2.0)."""
    if speed <= 0:
        raise ValueError("Speed phải > 0.")
    parts, rest = [], float(speed)
    while rest > 2.0:
        parts.append("atempo=2.0")
        rest /= 2.0
    parts.append(f"atempo={rest:.4f}")
    return ",".join(parts)


def validate_params(speed=1.0, video_scale=0.94, image_opacity=0.85,
                    sticker_scale=0.15, quality_mode="source",
                    quality_value="", chunk_seconds=300,
                    video_left=0, video_right=0, video_top=0, video_bottom=0,
                    sticker_left=0, sticker_right=0, sticker_top=0, sticker_bottom=0):
    """
    Kiểm tra các số người dùng nhập TRƯỚC khi chạy ffmpeg, báo lỗi rõ
    ràng bằng tiếng Việt thay vì để ffmpeg nổ với lỗi khó hiểu
    (VD: speed=0 -> setpts=PTS/0.0000, chia cho 0).
    Chấp nhận cả số và chuỗi số. Ném ValueError khi sai.
    """
    def _num(value, name, example):
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{name} phải là số, VD: {example}. "
                             f"Hiện tại: {value!r}.")

    def _coord(value, name):
        if value in (None, ""):
            return 0.0
        val = _num(value, name, "20")
        if not (-5000 <= val <= 5000):
            raise ValueError(f"{name} phải từ -5000 đến 5000 px, hiện tại: {val}.")
        return val

    speed = _num(speed, "Speed", "1.2")
    if not (0 < speed <= 8):
        raise ValueError(f"Speed phải từ 0.01 đến 8, hiện tại: {speed}.")
    video_scale = _num(video_scale, "Tỉ lệ video (khung 9:16)", "0.94")
    if not (0 < video_scale <= 1):
        raise ValueError(f"Tỉ lệ video phải từ 0.01 đến 1, hiện tại: {video_scale}.")
    image_opacity = _num(image_opacity, "Độ mờ ảnh", "0.85")
    if not (0 <= image_opacity <= 1):
        raise ValueError(f"Độ mờ ảnh phải từ 0 đến 1, hiện tại: {image_opacity}.")
    sticker_scale = _num(sticker_scale, "Cỡ sticker", "0.15")
    if not (0 < sticker_scale <= 1):
        raise ValueError(f"Cỡ sticker phải từ 0.01 đến 1, hiện tại: {sticker_scale}.")
    chunk_seconds = _num(chunk_seconds, "Độ dài mỗi đoạn", "300")
    if not (10 <= chunk_seconds <= 3600):
        raise ValueError(f"Độ dài mỗi đoạn phải từ 10 đến 3600 giây, hiện tại: {chunk_seconds}.")
    _coord(video_left, "Tọa độ Left của video")
    _coord(video_right, "Tọa độ Right của video")
    _coord(video_top, "Tọa độ Top của video")
    _coord(video_bottom, "Tọa độ Bottom của video")
    _coord(sticker_left, "Tọa độ Left của sticker")
    _coord(sticker_right, "Tọa độ Right của sticker")
    _coord(sticker_top, "Tọa độ Top của sticker")
    _coord(sticker_bottom, "Tọa độ Bottom của sticker")
    if quality_mode == "bitrate":
        if not str(quality_value).strip():
            raise ValueError("Chế độ bitrate yêu cầu nhập giá trị (VD: 8M, 4000k).")
        parse_bitrate(quality_value)  # Ném ValueError rõ ràng nếu sai
    elif quality_mode == "crf" and str(quality_value).strip():
        try:
            c = int(str(quality_value).strip())
            if not (0 <= c <= 51):
                raise ValueError
        except ValueError:
            raise ValueError(f"CRF phải là số nguyên từ 0 đến 51 (VD: 20). Hiện tại: {quality_value!r}.")
    return True


def _parse_coord(val) -> int:
    if val in (None, ""):
        return 0
    return int(round(float(val)))


def resolve_video_overlay_expr(video_position="center",
                               left=0, right=0, top=0, bottom=0):
    """
    Tính biểu thức (x_expr, y_expr) cho FFmpeg overlay video lên khung 9:16.
    - Ngang: căn theo video_position ('left'/'top-left'/'bottom-left',
      'right'/'top-right'/'bottom-right', hoặc giữa) rồi cộng (left - right).
    - Dọc: căn theo video_position ('top'/'top-left'/'top-right',
      'bottom'/'bottom-left'/'bottom-right', hoặc giữa) rồi cộng (top - bottom).
    """
    l_px = _parse_coord(left)
    r_px = _parse_coord(right)
    t_px = _parse_coord(top)
    b_px = _parse_coord(bottom)
    dx = l_px - r_px
    dy = t_px - b_px

    pos = (video_position or "center").strip().lower()
    if pos in ("left", "top-left", "bottom-left"):
        base_x = "0"
    elif pos in ("right", "top-right", "bottom-right"):
        base_x = "W-w"
    else:
        base_x = "(W-w)/2"

    if pos in ("top", "top-left", "top-right"):
        base_y = "0"
    elif pos in ("bottom", "bottom-left", "bottom-right"):
        base_y = "H-h"
    else:
        base_y = "(H-h)/2"

    x_expr = f"{base_x}{dx:+d}" if dx else base_x
    y_expr = f"{base_y}{dy:+d}" if dy else base_y
    return x_expr, y_expr


STICKER_CORNER_CYCLE = (
    "top-right",
    "bottom-left",
    "top-left",
    "bottom-right",
)


def resolve_sticker_position(sticker_position="auto-corners", index=0) -> str:
    """
    Trả về vị trí sticker thực tế cho video thứ `index` (0-based).
    - Nếu sticker_position là 'auto-corners' (hoặc 'auto' / '4-corners'),
      tự động luân chuyển qua 4 góc:
      video 1 -> top-right, video 2 -> bottom-left,
      video 3 -> top-left, video 4 -> bottom-right, rồi lặp lại.
    - Ngược lại giữ nguyên vị trí cố định người dùng đã chọn.
    """
    pos = (sticker_position or "auto-corners").strip().lower()
    if pos in ("auto-corners", "auto", "4-corners", "auto_corners"):
        return STICKER_CORNER_CYCLE[int(index) % len(STICKER_CORNER_CYCLE)]
    return pos


def resolve_sticker_overlay_expr(sticker_position="bottom-right",
                                 left=0, right=0, top=0, bottom=0,
                                 default_margin=20, index=0):
    """
    Tính biểu thức (x_expr, y_expr) cho FFmpeg overlay sticker.
    - Dựa trên vị trí gốc (auto-corners, bottom-right, top-right, bottom-left,
      top-left, center, top, bottom, left, right) với lề mặc định default_margin (20px),
      sau đó dịch theo tọa độ (left - right, top - bottom).
    """
    l_px = _parse_coord(left)
    r_px = _parse_coord(right)
    t_px = _parse_coord(top)
    b_px = _parse_coord(bottom)
    dx = l_px - r_px
    dy = t_px - b_px
    m = int(default_margin)

    pos = resolve_sticker_position(sticker_position, index=index)
    base_map = {
        "bottom-right": (f"W-w-{m}", f"H-h-{m}"),
        "top-right": (f"W-w-{m}", f"{m}"),
        "bottom-left": (f"{m}", f"H-h-{m}"),
        "top-left": (f"{m}", f"{m}"),
        "center": ("(W-w)/2", "(H-h)/2"),
        "top": ("(W-w)/2", f"{m}"),
        "bottom": ("(W-w)/2", f"H-h-{m}"),
        "left": (f"{m}", "(H-h)/2"),
        "right": (f"W-w-{m}", "(H-h)/2"),
    }
    base_x, base_y = base_map.get(pos, base_map["bottom-right"])
    x_expr = f"{base_x}{dx:+d}" if dx else base_x
    y_expr = f"{base_y}{dy:+d}" if dy else base_y
    return x_expr, y_expr


# ---------------------------------------------------------------------------
# Filter graph chung — mirror + speed + ảnh + sticker trong 1 lần encode
# ---------------------------------------------------------------------------
def build_filter_graph(info: dict, mirror=False, speed=1.0,
                       image=None, image_mode="corner", image_opacity=0.85,
                       sticker=None, sticker_scale=0.15,
                       sticker_position="bottom-right",
                       sticker_left=0, sticker_right=0,
                       sticker_top=0, sticker_bottom=0,
                       encoder="libx264"):
    """
    Xây filter_complex cho 1 video. Input video là [0:v]/[0:a],
    ảnh và sticker là các input tiếp theo theo thứ tự thêm vào
    (ảnh trước, sticker sau — xem 05_batch.py).
    Trả về (filter_complex, video_out_label, audio_label | None).
    """
    w, h = info["width"], info["height"]
    fps = info["fps"] or 30.0
    parts = []
    if mirror:
        parts.append("hflip")
    if abs(speed - 1.0) > 0.001:
        parts.append(f"setpts=PTS/{speed:.4f}")
        parts.append(f"fps={fps:.2f}")
    vchain = ",".join(parts)
    if vchain:
        vchain += ","
    vchain += "format=yuv420p"
    if encoder == "h264_vaapi":
        vchain = vchain.replace("format=yuv420p", "format=nv12,hwupload")
    filters = [f"[0:v]{vchain}[v0]"]
    cur, img_idx = "[v0]", 1

    if image is not None:
        if image_mode == "full":
            scale = f"scale={w}:{h}"
            x, y = "0", "0"
        elif image_mode == "banner":
            scale = f"scale={w}:{max(2, h // 4)}"
            x, y = "0", "0"
        else:  # corner: ảnh nhỏ góc phải dưới, rộng 25% video
            scale = f"scale={max(2, w // 4)}:-2"
            x, y = "W-w-20", "H-h-20"
        filters.append(f"[{img_idx}:v]{scale},format=rgba,"
                       f"colorchannelmixer=aa={image_opacity}[img]")
        filters.append(f"{cur}[img]overlay={x}:{y}[v1]")
        cur, img_idx = "[v1]", img_idx + 1

    if sticker is not None:
        sw = max(2, int(w * sticker_scale))
        sx, sy = resolve_sticker_overlay_expr(
            sticker_position,
            left=sticker_left, right=sticker_right,
            top=sticker_top, bottom=sticker_bottom,
        )
        filters.append(f"[{img_idx}:v]scale={sw}:-2,format=rgba[stk]")
        filters.append(f"{cur}[stk]overlay={sx}:{sy}[v2]")
        cur = "[v2]"

    audio_filter = None
    if info.get("has_audio") and abs(speed - 1.0) > 0.001:
        audio_filter = f"[0:a]{atempo_chain(speed)}[aout]"
        filters.append(audio_filter)

    return ";".join(filters), cur, ("[aout]" if audio_filter else None)


# ---------------------------------------------------------------------------
# Khung 9:16 — ảnh làm nền, video phủ lên trên (như ảnh mẫu CapCut)
# ---------------------------------------------------------------------------
FRAME_916_W, FRAME_916_H = 1080, 1920


def build_916_filter_graph(info: dict, mirror=False, speed=1.0,
                           sticker=None, sticker_scale=0.15,
                           sticker_position="bottom-right",
                           sticker_left=0, sticker_right=0,
                           sticker_top=0, sticker_bottom=0,
                           video_scale=0.94, video_position="center",
                           video_left=0, video_right=0,
                           video_top=0, video_bottom=0,
                           encoder="libx264"):
    """
    Xây filter_complex cho khung 9:16 (1080x1920) — bố cục như ảnh mẫu:
      - Nền: ảnh (input [1:v]) scale lấp đầy 1080x1920 rồi crop giữa.
        Không có ảnh thì input [1:v] là màu đen (xem 05_batch.py).
      - Video (input [0:v]): mirror/speed xong, scale vừa khung
        1080*video_scale x 1920*video_scale (giữ tỉ lệ), phủ lên nền,
        căn theo video_position và dịch theo tọa độ left/right/top/bottom.
      - Sticker (input [2:v], nếu có): phủ lên trên cùng, căn theo
        sticker_position và dịch theo tọa độ left/right/top/bottom.
    Trả về (filter_complex, video_out_label, audio_label | None).
    """
    fps = info["fps"] or 30.0
    box_w = max(2, int(FRAME_916_W * video_scale))
    box_h = max(2, int(FRAME_916_H * video_scale))

    # --- Video: mirror -> speed -> scale vừa khung ---
    parts = []
    if mirror:
        parts.append("hflip")
    if abs(speed - 1.0) > 0.001:
        parts.append(f"setpts=PTS/{speed:.4f}")
        parts.append(f"fps={fps:.2f}")
    parts.append(f"scale={box_w}:{box_h}:force_original_aspect_ratio=decrease")
    vchain = ",".join(parts) + ",format=yuv420p"
    if encoder == "h264_vaapi":
        vchain = vchain.replace("format=yuv420p", "format=nv12,hwupload")
    filters = [f"[0:v]{vchain}[vfg]"]

    # --- Nền: ảnh lấp đầy 1080x1920 (crop giữa) ---
    filters.append(f"[1:v]scale={FRAME_916_W}:{FRAME_916_H}:"
                   f"force_original_aspect_ratio=increase,"
                   f"crop={FRAME_916_W}:{FRAME_916_H},format=yuv420p[bg]")

    # --- Phủ video lên nền ---
    vx, vy = resolve_video_overlay_expr(
        video_position,
        left=video_left, right=video_right,
        top=video_top, bottom=video_bottom,
    )
    filters.append(f"[bg][vfg]overlay={vx}:{vy}[v1]")
    cur = "[v1]"

    # --- Sticker lên trên cùng (tính theo khung 1080x1920) ---
    if sticker is not None:
        sw = max(2, int(FRAME_916_W * sticker_scale))
        sx, sy = resolve_sticker_overlay_expr(
            sticker_position,
            left=sticker_left, right=sticker_right,
            top=sticker_top, bottom=sticker_bottom,
        )
        filters.append(f"[2:v]scale={sw}:-2,format=rgba[stk]")
        filters.append(f"{cur}[stk]overlay={sx}:{sy}[v2]")
        cur = "[v2]"

    audio_filter = None
    if info.get("has_audio") and abs(speed - 1.0) > 0.001:
        audio_filter = f"[0:a]{atempo_chain(speed)}[aout]"
        filters.append(audio_filter)

    return ";".join(filters), cur, ("[aout]" if audio_filter else None)

