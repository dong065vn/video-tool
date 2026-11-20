#!/usr/bin/env python3
"""Render a small still preview that matches the batch composition layout."""
from io import BytesIO
from pathlib import Path
import subprocess

from PIL import Image, ImageEnhance, ImageOps

from common import (FRAME_916_H, FRAME_916_W, IMAGE_EXTS, STICKER_EXTS,
                    VIDEO_EXTS, list_files, pair_files,
                    resolve_sticker_position)

PREVIEW_916 = (216, 384)
PREVIEW_MAX = (520, 384)
_RESAMPLE = Image.Resampling.LANCZOS


def list_preview_combinations(videos_dir="", video_file="", images_dir="",
                              stickers_dir="", image_on=True, sticker_on=True,
                              pair="order", seed=0):
    """
    Trả về danh sách toàn bộ tổ hợp (video, image, sticker) giống hệt như
    05_batch.py sẽ ghép cặp để người dùng bấm Trước / Tiếp (Next) xem từng video.
    """
    if video_file and Path(video_file).is_file():
        videos = [Path(video_file)]
    elif videos_dir:
        videos = list_files(videos_dir, VIDEO_EXTS)
    else:
        videos = []
    if not videos:
        return []
    images = list_files(images_dir, IMAGE_EXTS) if image_on and images_dir else []
    stickers = list_files(stickers_dir, STICKER_EXTS) if sticker_on and stickers_dir else []
    img_pairs = pair_files(videos, images, pair, seed) if image_on else [(v, None) for v in videos]
    stk_pairs = pair_files(videos, stickers, pair, seed) if sticker_on else [(v, None) for v in videos]
    return [
        (videos[i], img_pairs[i][1], stk_pairs[i][1])
        for i in range(len(videos))
    ]


def select_preview_sources(videos_dir="", video_file="", images_dir="",
                           stickers_dir="", image_on=True, sticker_on=True,
                           pair="order", seed=0, index=0):
    """Select the paired files at `index` (0-based), wrapping around."""
    combos = list_preview_combinations(
        videos_dir=videos_dir, video_file=video_file,
        images_dir=images_dir, stickers_dir=stickers_dir,
        image_on=image_on, sticker_on=sticker_on,
        pair=pair, seed=seed,
    )
    if not combos:
        return None, None, None
    return combos[int(index) % len(combos)]


def extract_video_frame(video, timestamp=0.1):
    """Decode one video frame to memory without creating a temporary image file."""
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(timestamp), "-i", str(video),
         "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"],
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0 or not result.stdout:
        message = result.stderr.decode("utf-8", errors="replace")[-1000:]
        raise RuntimeError(f"Không lấy được hình từ {Path(video).name}: {message}")
    with Image.open(BytesIO(result.stdout)) as image:
        frame = image.convert("RGBA")
        frame.load()
        return frame


def _open_rgba(path):
    with Image.open(path) as image:
        result = image.convert("RGBA")
        result.load()
        return result


def _fit_inside(image, width, height):
    result = image.copy()
    result.thumbnail((max(1, width), max(1, height)), _RESAMPLE)
    return result


def _set_opacity(image, opacity):
    result = image.copy()
    alpha = result.getchannel("A")
    result.putalpha(ImageEnhance.Brightness(alpha).enhance(opacity))
    return result


def _position(canvas_size, item_size, name, margin, dx=0, dy=0):
    width, height = canvas_size
    item_width, item_height = item_size
    pos = (name or "bottom-right").strip().lower()
    positions = {
        "bottom-right": (width - item_width - margin, height - item_height - margin),
        "top-right": (width - item_width - margin, margin),
        "bottom-left": (margin, height - item_height - margin),
        "top-left": (margin, margin),
        "center": ((width - item_width) // 2, (height - item_height) // 2),
        "top": ((width - item_width) // 2, margin),
        "bottom": ((width - item_width) // 2, height - item_height - margin),
        "left": (margin, (height - item_height) // 2),
        "right": (width - item_width - margin, (height - item_height) // 2),
    }
    bx, by = positions.get(pos, positions["bottom-right"])
    return bx + dx, by + dy


def _video_position(canvas_size, item_size, name, dx=0, dy=0):
    width, height = canvas_size
    item_width, item_height = item_size
    pos = (name or "center").strip().lower()
    if pos in ("left", "top-left", "bottom-left"):
        bx = 0
    elif pos in ("right", "top-right", "bottom-right"):
        bx = width - item_width
    else:
        bx = (width - item_width) // 2

    if pos in ("top", "top-left", "top-right"):
        by = 0
    elif pos in ("bottom", "bottom-left", "bottom-right"):
        by = height - item_height
    else:
        by = (height - item_height) // 2

    return bx + dx, by + dy


def _number(config, name, default, low, high):
    raw = config.get(name, default)
    if raw in (None, ""):
        raw = default
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} phải là số, hiện tại: {raw!r}") from exc
    if not low <= value <= high:
        raise ValueError(f"{name} phải từ {low} đến {high}, hiện tại: {value}")
    return value


def compose_preview(frame, config, image_path=None, sticker_path=None):
    """Compose frame/image/sticker using the same geometry as common.py."""
    video = frame.convert("RGBA")
    if config.get("mirror"):
        video = ImageOps.mirror(video)

    frame_916 = bool(config.get("frame_916", True))
    image_on = bool(config.get("image_on", True))
    sticker_on = bool(config.get("sticker_on", True))
    video_scale = _number(config, "video_scale", 0.94, 0.01, 1.0)
    sticker_scale = _number(config, "sticker_scale", 0.15, 0.01, 1.0)
    opacity = _number(config, "image_opacity", 0.85, 0.0, 1.0)

    v_left = _number(config, "video_left", 0, -5000, 5000)
    v_right = _number(config, "video_right", 0, -5000, 5000)
    v_top = _number(config, "video_top", 0, -5000, 5000)
    v_bottom = _number(config, "video_bottom", 0, -5000, 5000)

    s_left = _number(config, "sticker_left", 0, -5000, 5000)
    s_right = _number(config, "sticker_right", 0, -5000, 5000)
    s_top = _number(config, "sticker_top", 0, -5000, 5000)
    s_bottom = _number(config, "sticker_bottom", 0, -5000, 5000)

    if frame_916:
        width, height = PREVIEW_916
        scale_x = width / FRAME_916_W
        scale_y = height / FRAME_916_H
        if image_on and image_path:
            background = ImageOps.fit(_open_rgba(image_path), (width, height),
                                      method=_RESAMPLE, centering=(0.5, 0.5))
        else:
            background = Image.new("RGBA", (width, height), "black")
        foreground = _fit_inside(
            video, int(width * video_scale), int(height * video_scale)
        )
        v_dx = round((v_left - v_right) * scale_x)
        v_dy = round((v_top - v_bottom) * scale_y)
        x, y = _video_position(
            (width, height), foreground.size,
            config.get("video_position", "center"),
            dx=v_dx, dy=v_dy,
        )
        background.alpha_composite(foreground, (x, y))
        canvas = background
        margin = max(1, round(width * 20 / FRAME_916_W))
    else:
        source_width, source_height = video.size
        ratio = min(PREVIEW_MAX[0] / max(1, source_width),
                    PREVIEW_MAX[1] / max(1, source_height))
        width = max(2, round(source_width * ratio))
        height = max(2, round(source_height * ratio))
        scale_x = width / max(1, source_width)
        scale_y = height / max(1, source_height)
        canvas = video.resize((width, height), _RESAMPLE)
        margin = max(2, round(width * 20 / max(1, source_width)))
        if image_on and image_path:
            overlay = _open_rgba(image_path)
            mode = config.get("image_mode", "corner")
            if mode == "full":
                overlay = overlay.resize((width, height), _RESAMPLE)
                xy = (0, 0)
            elif mode == "banner":
                overlay = overlay.resize((width, max(2, height // 4)), _RESAMPLE)
                xy = (0, 0)
            else:
                overlay = _fit_inside(overlay, max(2, width // 4), height)
                xy = (width - overlay.width - margin,
                      height - overlay.height - margin)
            canvas.alpha_composite(_set_opacity(overlay, opacity), xy)

    if sticker_on and sticker_path:
        sticker = _open_rgba(sticker_path)
        sticker = _fit_inside(sticker, max(2, int(canvas.width * sticker_scale)),
                              canvas.height)
        s_dx = round((s_left - s_right) * scale_x)
        s_dy = round((s_top - s_bottom) * scale_y)
        effective_pos = resolve_sticker_position(
            config.get("sticker_position", "auto-corners"),
            index=int(config.get("combo_index", 0) or 0),
        )
        xy = _position(
            canvas.size, sticker.size,
            effective_pos,
            margin, dx=s_dx, dy=s_dy,
        )
        canvas.alpha_composite(sticker, xy)
    return canvas
