#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Video Tool v2: xử lý batch trong một lần encode và giao diện Dark UI (PyQt6).

Chạy giao diện:
    python main.py

Chạy không giao diện:
    python main.py --cli --videos ./videos --images ./anh --stickers ./sticker -o ./out/
"""
import argparse
import importlib.util
from io import BytesIO
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))


def load_tool(filename: str, func_name: str):
    path = BASE / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return getattr(mod, func_name)


DEFAULT_CONFIG = {
    "videos_dir": "", "video_file": "",
    "images_dir": "", "stickers_dir": "",
    "pair": "order", "seed": 0,
    "output_dir": "video_done",
    "mirror": True,
    "speed_on": True, "speed": 1.2,
    "image_on": True, "image_mode": "corner", "image_opacity": 0.85,
    "frame_916": True, "video_scale": 0.94, "video_position": "center",
    "video_left": 0, "video_right": 0, "video_top": 0, "video_bottom": 0,
    "sticker_on": True, "sticker_scale": 0.15, "sticker_position": "auto-corners",
    "sticker_left": 0, "sticker_right": 0, "sticker_top": 0, "sticker_bottom": 0,
    "quality_mode": "source",
    "quality_value": "",
    "encoder": "auto",
    "gpu_profile": "auto",
    "preset": "", "threads": 0, "workers": 0,
    "chunk": True, "chunk_seconds": 300,
    "resume": True, "keep_chunks": False,
    "sil_batch": True, "sil_mode": "relative", "sil_margin": 20.0,
    "sil_threshold": -40.0, "sil_min_silence": 0.5, "sil_min_cut": 1.0,
    "sil_pad": 0.2, "sil_min_keep": 0.8, "sil_max_cut_ratio": 30.0,
    "sil_max_keep": 5.0, "sil_trim_ends": True,
    "sil_safety": True,
    "dry_run": False,
}


def default_config():
    return dict(DEFAULT_CONFIG)


# ---------------------------------------------------------------------------
# Logic chạy đồng bộ — dùng chung cho GUI và CLI
# ---------------------------------------------------------------------------
def run_pipeline(cfg, log=print, progress=None):
    """Chạy batch song song; log và progress dùng chung cho GUI/CLI."""
    batch_fn = load_tool("05_batch.py", "batch")
    videos_dir = (cfg.get("videos_dir") or "").strip() or None
    video_file = (cfg.get("video_file") or "").strip() or None
    images_dir = (cfg.get("images_dir") or "").strip() or None
    stickers_dir = (cfg.get("stickers_dir") or "").strip() or None
    if not videos_dir and not video_file:
        raise RuntimeError("Chưa chọn thư mục video hoặc một file video trong tab Nguồn.")
    out_dir = (cfg.get("output_dir") or "").strip() or "video_done"
    # Kiểm tra số nhập TRƯỚC khi chạy (báo lỗi rõ ràng thay vì ffmpeg nổ)
    validate_fn = load_tool("common.py", "validate_params")
    validate_fn(speed=cfg.get("speed", 1.2) if cfg.get("speed_on", True) else 1.0,
                video_scale=cfg.get("video_scale", 0.94),
                image_opacity=cfg.get("image_opacity", 0.85),
                sticker_scale=cfg.get("sticker_scale", 0.15),
                quality_mode=cfg.get("quality_mode", "source") or "source",
                quality_value=(cfg.get("quality_value") or "").strip(),
                chunk_seconds=cfg.get("chunk_seconds", 300),
                video_left=cfg.get("video_left", 0),
                video_right=cfg.get("video_right", 0),
                video_top=cfg.get("video_top", 0),
                video_bottom=cfg.get("video_bottom", 0),
                sticker_left=cfg.get("sticker_left", 0),
                sticker_right=cfg.get("sticker_right", 0),
                sticker_top=cfg.get("sticker_top", 0),
                sticker_bottom=cfg.get("sticker_bottom", 0))
    speed = float(cfg.get("speed", 1.2)) if cfg.get("speed_on", True) else 1.0

    log(f"[MAIN] Video: {videos_dir or video_file} | Ảnh: {images_dir or '-'} | "
        f"Sticker: {stickers_dir or '-'} | Ghép cặp: {cfg.get('pair', 'order')}")
    log(f"[MAIN] Mirror: {'BẬT' if cfg.get('mirror') else 'TẮT'} | Speed: {speed}x | "
        f"Ảnh: {'BẬT' if cfg.get('image_on') else 'TẮT'} | "
        f"Sticker: {'BẬT' if cfg.get('sticker_on') else 'TẮT'} | "
        f"Khung 9:16: {'BẬT (1080x1920)' if cfg.get('frame_916') else 'TẮT'} | "
        f"Encoder: {cfg.get('encoder', 'auto')} | "
        f"GPU: {cfg.get('gpu_profile', 'auto')} | "
        f"Workers: {cfg.get('workers', 0) or 'tự động'} | "
        f"Chất lượng: {cfg.get('quality_mode', 'source')} {cfg.get('quality_value') or '(gốc)'} | "
        f"Chia đoạn: {'BẬT (' + str(int(cfg.get('chunk_seconds', 300) or 300)) + 's/đoạn)' if cfg.get('chunk', True) else 'TẮT'} | "
        f"Cắt khoảng lặng: {'BẬT (chỉ cắt im > ' + str(cfg.get('sil_min_cut', 1.0)) + 's)' if cfg.get('sil_batch', True) else 'TẮT'}")
    if cfg.get("dry_run"):
        log("[MAIN] Dry-run: chỉ in kế hoạch, không tạo file thật.")

    _sr = cfg.get("sil_max_cut_ratio", 30)
    sil_ratio = 30.0 if _sr is None or _sr == "" else float(_sr)
    sil_ratio = sil_ratio / 100.0 if sil_ratio > 1 else sil_ratio
    sil_safety = bool(cfg.get("sil_safety", True))
    outputs = batch_fn(
        videos_dir=videos_dir, video_file=video_file,
        images_dir=images_dir if cfg.get("image_on") else None,
        stickers_dir=stickers_dir if cfg.get("sticker_on") else None,
        output_dir=out_dir,
        pair=cfg.get("pair", "order"), seed=int(cfg.get("seed", 0) or 0),
        mirror=bool(cfg.get("mirror", True)), speed=speed,
        image_on=bool(cfg.get("image_on", True)),
        image_mode=cfg.get("image_mode", "corner"),
        image_opacity=float(cfg.get("image_opacity", 0.85) or 0.85),
        sticker_on=bool(cfg.get("sticker_on", True)),
        sticker_scale=float(cfg.get("sticker_scale", 0.15) or 0.15),
        sticker_position=cfg.get("sticker_position", "auto-corners"),
        sticker_left=float(cfg.get("sticker_left", 0) or 0),
        sticker_right=float(cfg.get("sticker_right", 0) or 0),
        sticker_top=float(cfg.get("sticker_top", 0) or 0),
        sticker_bottom=float(cfg.get("sticker_bottom", 0) or 0),
        frame_916=bool(cfg.get("frame_916", True)),
        video_scale=float(cfg.get("video_scale", 0.94) or 0.94),
        video_position=cfg.get("video_position", "center"),
        video_left=float(cfg.get("video_left", 0) or 0),
        video_right=float(cfg.get("video_right", 0) or 0),
        video_top=float(cfg.get("video_top", 0) or 0),
        video_bottom=float(cfg.get("video_bottom", 0) or 0),
        encoder=cfg.get("encoder", "auto") or "auto",
        quality_mode=cfg.get("quality_mode", "source") or "source",
        quality_value=(cfg.get("quality_value") or "").strip(),
        preset=(cfg.get("preset") or "").strip() or None,
        threads=int(cfg.get("threads", 0) or 0) or None,
        dry_run=bool(cfg.get("dry_run", False)), log=log,
        chunk=bool(cfg.get("chunk", True)),
        chunk_seconds=int(cfg.get("chunk_seconds", 300) or 300),
        resume=bool(cfg.get("resume", True)),
        keep_chunks=bool(cfg.get("keep_chunks", False)),
        silence_on=bool(cfg.get("sil_batch", True)),
        silence_mode=cfg.get("sil_mode", "relative") or "relative",
        silence_margin=float(cfg.get("sil_margin", 20) or 20),
        silence_absolute=float(cfg.get("sil_threshold", -40) or -40),
        silence_min_silence=float(cfg.get("sil_min_silence", 0.5) or 0.5),
        silence_min_cut=float(cfg.get("sil_min_cut", 1.0) or 1.0),
        silence_pad=float(cfg.get("sil_pad", 0.2) or 0.2),
        silence_min_keep=float(cfg.get("sil_min_keep", 0.8) or 0.8),
        silence_max_keep=float(cfg.get("sil_max_keep", 5) or 5),
        silence_trim_ends=bool(cfg.get("sil_trim_ends", True)),
        silence_safety=sil_safety,
        silence_max_cut_ratio=(sil_ratio if sil_safety else 0.0),
        workers=int(cfg.get("workers", 0) or 0),
        gpu_profile=cfg.get("gpu_profile", "auto") or "auto",
        progress=progress)
    return outputs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cli_main(argv=None):
    p = argparse.ArgumentParser(description="main.py --cli: xử lý video hàng loạt theo folder")
    p.add_argument("--cli", action="store_true")
    p.add_argument("--videos", default="", help="Thư mục chứa video")
    p.add_argument("--video", default="", help="1 file video duy nhất")
    p.add_argument("--images", default="", help="Thư mục chứa ảnh ghép")
    p.add_argument("--stickers", default="", help="Thư mục chứa sticker")
    p.add_argument("-o", "--output-dir", default="video_done")
    p.add_argument("--pair", default="order", choices=["order", "shuffle"])
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--no-mirror", dest="mirror", action="store_false")
    p.add_argument("--mirror", dest="mirror", action="store_true")
    p.add_argument("--no-speed", dest="speed_on", action="store_false")
    p.add_argument("--speed", type=float, default=1.2)
    p.add_argument("--no-image", dest="image_on", action="store_false")
    p.add_argument("--image-on", dest="image_on", action="store_true")
    p.add_argument("--image-mode", default="corner", choices=["corner", "full", "banner"])
    p.add_argument("--image-opacity", type=float, default=0.85)
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
    p.add_argument("--encoder", default="auto")
    p.add_argument("--quality-mode", default="source", choices=["source", "bitrate", "crf"])
    p.add_argument("--quality-value", default="")
    p.add_argument("--preset", default="")
    p.add_argument("--threads", type=int, default=0)
    p.add_argument("--gpu-profile", default="auto",
                   choices=["auto", "nvidia_legacy", "nvidia_modern"])
    p.add_argument("--workers", type=int, default=0,
                   help="Số video chạy song song; 0 = tự tối ưu")
    p.add_argument("--chunk", dest="chunk", action="store_true")
    p.add_argument("--no-chunk", dest="chunk", action="store_false")
    p.add_argument("--chunk-seconds", type=int, default=300)
    p.add_argument("--resume", dest="resume", action="store_true")
    p.add_argument("--no-resume", dest="resume", action="store_false")
    p.add_argument("--keep-chunks", action="store_true")
    p.add_argument("--silence", dest="sil_batch", action="store_true",
                   help="Bật cắt khoảng lặng trong lúc chạy đồng bộ (mặc định BẬT)")
    p.add_argument("--no-silence", dest="sil_batch", action="store_false")
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
    p.add_argument("--sil-max-cut-ratio", type=float, default=30.0)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(mirror=True, speed_on=True, image_on=True, sticker_on=True, frame_916=True,
                   chunk=True, resume=True, sil_batch=True, sil_trim_ends=True)
    a = p.parse_args(argv)

    cfg = default_config()
    cfg.update({
        "videos_dir": a.videos, "video_file": a.video,
        "images_dir": a.images, "stickers_dir": a.stickers,
        "output_dir": a.output_dir, "pair": a.pair, "seed": a.seed,
        "mirror": a.mirror, "speed_on": a.speed_on, "speed": a.speed,
        "image_on": a.image_on, "image_mode": a.image_mode,
        "image_opacity": a.image_opacity,
        "sticker_on": a.sticker_on, "sticker_scale": a.sticker_scale,
        "sticker_position": a.sticker_position,
        "sticker_left": a.sticker_left, "sticker_right": a.sticker_right,
        "sticker_top": a.sticker_top, "sticker_bottom": a.sticker_bottom,
        "frame_916": a.frame_916, "video_scale": a.video_scale,
        "video_position": a.video_position,
        "video_left": a.video_left, "video_right": a.video_right,
        "video_top": a.video_top, "video_bottom": a.video_bottom,
        "encoder": a.encoder, "gpu_profile": a.gpu_profile,
        "quality_mode": a.quality_mode,
        "quality_value": a.quality_value, "preset": a.preset,
        "threads": a.threads, "workers": a.workers, "dry_run": a.dry_run,
        "chunk": a.chunk, "chunk_seconds": a.chunk_seconds,
        "resume": a.resume, "keep_chunks": a.keep_chunks,
        "sil_batch": a.sil_batch, "sil_mode": a.sil_mode,
        "sil_margin": a.sil_margin, "sil_threshold": a.sil_threshold_db,
        "sil_min_silence": a.sil_min_silence, "sil_min_cut": a.sil_min_cut,
        "sil_pad": a.sil_pad, "sil_min_keep": a.sil_min_keep,
        "sil_max_cut_ratio": a.sil_max_cut_ratio, "sil_max_keep": a.sil_max_keep,
        "sil_trim_ends": a.sil_trim_ends, "sil_safety": a.sil_safety,
    })
    run_pipeline(cfg)
    return 0


# ---------------------------------------------------------------------------
# GUI — PyQt6 Dark Theme
# ---------------------------------------------------------------------------
DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0f1117;
    color: #e2e8f0;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 12px;
}

QFrame#HeaderBar {
    background-color: #161922;
    border: 1px solid #262b3d;
    border-radius: 10px;
}

QLabel#AppTitle {
    color: #f8fafc;
    font-size: 16px;
    font-weight: 700;
}

QLabel#AppSubTitle {
    color: #94a3b8;
    font-size: 11px;
}

QLabel#StatusBadge {
    background-color: #1e2433;
    color: #a5b4fc;
    border: 1px solid #313a52;
    border-radius: 6px;
    padding: 3px 9px;
    font-size: 11px;
    font-weight: 600;
}

QLabel#MutedLabel {
    color: #94a3b8;
    font-size: 11px;
}

QTabWidget::pane {
    border: 1px solid #262b3d;
    background-color: #131620;
    border-radius: 10px;
    top: -1px;
}

QTabBar::tab {
    background-color: #161922;
    color: #94a3b8;
    border: 1px solid #262b3d;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 7px 15px;
    margin-right: 4px;
    font-size: 12px;
    font-weight: 600;
}

QTabBar::tab:hover {
    background-color: #1e2230;
    color: #e2e8f0;
}

QTabBar::tab:selected {
    background-color: #4f46e5;
    color: #ffffff;
    border-color: #6366f1;
}

QGroupBox {
    background-color: #171b26;
    border: 1px solid #262b3d;
    border-radius: 10px;
    margin-top: 12px;
    padding: 12px 10px 10px 10px;
    font-size: 12px;
    font-weight: 600;
    color: #f1f5f9;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 6px;
    color: #a5b4fc;
    background-color: #171b26;
}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #0d1017;
    color: #f1f5f9;
    border: 1px solid #2e354b;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 18px;
    font-size: 12px;
    selection-background-color: #4f46e5;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #6366f1;
    background-color: #111520;
}

QComboBox::drop-down {
    border: none;
    width: 22px;
}

QComboBox QAbstractItemView {
    background-color: #171b26;
    color: #f1f5f9;
    border: 1px solid #334155;
    selection-background-color: #4f46e5;
    selection-color: #ffffff;
}

QPushButton {
    background-color: #232838;
    color: #e2e8f0;
    border: 1px solid #333b52;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #2e364d;
    border-color: #475569;
}

QPushButton:pressed {
    background-color: #1e2333;
}

QPushButton:disabled {
    background-color: #161923;
    color: #475569;
    border-color: #222634;
}

QPushButton#PrimaryButton {
    background-color: #4f46e5;
    color: #ffffff;
    border: 1px solid #6366f1;
    padding: 6px 16px;
    font-size: 12px;
    font-weight: 700;
}

QPushButton#PrimaryButton:hover {
    background-color: #4338ca;
    border-color: #818cf8;
}

QPushButton#PrimaryButton:disabled {
    background-color: #1e1b4b;
    color: #64748b;
    border-color: #312e81;
}

QPushButton#AccentButton {
    background-color: #0284c7;
    color: #ffffff;
    border: 1px solid #38bdf8;
}

QPushButton#AccentButton:hover {
    background-color: #0369a1;
}

QPushButton#SubtleButton {
    background-color: #1b2030;
    color: #cbd5e1;
    border: 1px solid #2b3248;
    padding: 4px 9px;
    font-size: 11px;
}

QPushButton#SubtleButton:hover {
    background-color: #262d42;
    color: #ffffff;
}

QPushButton#TableActionBtn {
    background-color: #1e293b;
    color: #38bdf8;
    border: 1px solid #0284c7;
    border-radius: 5px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}

QPushButton#TableActionBtn:hover {
    background-color: #0284c7;
    color: #ffffff;
}

QCheckBox {
    spacing: 7px;
    color: #e2e8f0;
    font-size: 12px;
}

QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid #475569;
    background-color: #0d1017;
}

QCheckBox::indicator:hover {
    border-color: #818cf8;
}

QCheckBox::indicator:checked {
    background-color: #4f46e5;
    border-color: #6366f1;
}

QProgressBar {
    background-color: #0d1017;
    border: 1px solid #2e354b;
    border-radius: 7px;
    height: 18px;
    text-align: center;
    color: #f8fafc;
    font-size: 11px;
    font-weight: 700;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #4f46e5, stop:1 #06b6d4);
    border-radius: 6px;
}

QTreeWidget {
    background-color: #0d1017;
    alternate-background-color: #121622;
    color: #e2e8f0;
    border: 1px solid #262b3d;
    border-radius: 8px;
    gridline-color: #1e2436;
    font-size: 11px;
}

QTreeWidget::item {
    padding: 3px 4px;
}

QTreeWidget::item:selected {
    background-color: #312e81;
    color: #ffffff;
}

QHeaderView::section {
    background-color: #181c29;
    color: #94a3b8;
    border: none;
    border-bottom: 1px solid #262b3d;
    border-right: 1px solid #262b3d;
    padding: 5px 6px;
    font-size: 11px;
    font-weight: 700;
}

QPlainTextEdit {
    background-color: #0b0d13;
    color: #cbd5e1;
    border: 1px solid #262b3d;
    border-radius: 8px;
    padding: 6px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 11px;
}

QLabel#PreviewCanvas {
    background-color: #090b10;
    color: #94a3b8;
    border: 1px dashed #334155;
    border-radius: 8px;
    padding: 6px;
    font-size: 11px;
}

QScrollBar:vertical {
    background: #12151f;
    width: 10px;
    margin: 0px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background: #2e354b;
    min-height: 24px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #475569;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""


def gui_main():
    from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
    from PyQt6.QtGui import QFont, QImage, QPixmap
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDoubleSpinBox,
        QFileDialog,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSpinBox,
        QSplitter,
        QTabWidget,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
    )
    import layout_preview as layout_preview_mod

    GPU_PROFILES = {
        "Tự động (NVIDIA cũ + mới)": "auto",
        "NVIDIA cũ (FFmpeg tương thích)": "nvidia_legacy",
        "NVIDIA mới (FFmpeg mới nhất)": "nvidia_modern",
    }

    SIL_PRESETS = {
        "Nhẹ": dict(sil_min_cut=2.0, sil_pad=0.3, sil_max_keep=8.0, sil_min_keep=1.0),
        "Vừa": dict(sil_min_cut=1.0, sil_pad=0.2, sil_max_keep=5.0, sil_min_keep=0.8),
        "Mạnh": dict(sil_min_cut=0.8, sil_pad=0.15, sil_max_keep=3.0, sil_min_keep=0.5),
    }

    class Bridge(QObject):
        log_signal = pyqtSignal(str)
        progress_signal = pyqtSignal(dict)
        preview_ready_signal = pyqtSignal(int, object, str)
        preview_error_signal = pyqtSignal(int, str)
        popup_inspect_ready_signal = pyqtSignal(
            int, object, object, str, str, dict, str, str
        )
        popup_inspect_error_signal = pyqtSignal(int, str)
        gpu_ready_signal = pyqtSignal(dict, str)
        gpu_error_signal = pyqtSignal(str)
        gpu_done_signal = pyqtSignal()
        batch_done_signal = pyqtSignal(str)
        batch_error_signal = pyqtSignal(str)
        batch_finally_signal = pyqtSignal()
        silence_scan_ready_signal = pyqtSignal(str, dict, str)
        silence_scan_error_signal = pyqtSignal(str, str)
        silence_scan_finally_signal = pyqtSignal()
        silence_cut_done_signal = pyqtSignal(str)
        silence_cut_error_signal = pyqtSignal(str)
        silence_cut_finally_signal = pyqtSignal()

    class VideoPreviewDialog(QDialog):
        """
        Popup xuất hiện khi bấm [▷ Xem] ở danh sách video (giống hệt cơ chế
        modal trong ảnh mẫu):
        - Góc trái: Khung hình Video GỐC + thông số kỹ thuật ffprobe của Video Gốc.
        - Bên cạnh: Nút [📥 Import video đầu ra để so sánh...] -> khi chọn file sẽ
          hiện ngay Khung hình Video Đầu ra + thông số ffprobe của Video Đầu ra
          + Bảng So sánh & Kết luận phân tích tự động.
        """

        def __init__(self, parent_win: "MainWindow", row_index: int):
            super().__init__(parent_win)
            self.parent_win = parent_win
            self.row_index = row_index
            self.setModal(False)
            self.setWindowTitle("Xem trước & So sánh Video")
            self.resize(1120, 650)
            self.setMinimumSize(860, 520)

            root = QVBoxLayout(self)
            root.setContentsMargins(14, 12, 14, 12)
            root.setSpacing(10)

            # --- Thanh tiêu đề Popup ---
            top_bar = QHBoxLayout()
            self.popup_title_lbl = QLabel("Xem trước:")
            self.popup_title_lbl.setObjectName("AppTitle")
            top_bar.addWidget(self.popup_title_lbl)
            top_bar.addStretch(1)

            self.btn_popup_prev = QPushButton("◀ Video trước")
            self.btn_popup_prev.setObjectName("SubtleButton")
            self.btn_popup_prev.clicked.connect(self._on_prev)
            self.btn_popup_next = QPushButton("Video tiếp ▶")
            self.btn_popup_next.setObjectName("SubtleButton")
            self.btn_popup_next.clicked.connect(self._on_next)

            btn_close = QPushButton("✕ Đóng")
            btn_close.setObjectName("SubtleButton")
            btn_close.clicked.connect(self.close)

            top_bar.addWidget(self.btn_popup_prev)
            top_bar.addWidget(self.btn_popup_next)
            top_bar.addWidget(btn_close)
            root.addLayout(top_bar)

            # --- Nội dung chính của Popup ---
            body = QHBoxLayout()
            body.setSpacing(10)

            # 1. Khung trái: Video GỐC (Hình bên trái + Thông số bên phải)
            src_box = QGroupBox("1. Video GỐC (Từ nguồn đã import)")
            src_col = QVBoxLayout(src_box)
            src_col.setContentsMargins(8, 10, 8, 8)
            src_col.setSpacing(6)

            src_hdr = QHBoxLayout()
            self.src_name_lbl = QLabel("Video gốc")
            self.src_name_lbl.setStyleSheet("font-weight: 700; color: #f8fafc;")
            btn_play_src = QPushButton("▷ Phát video gốc")
            btn_play_src.setObjectName("AccentButton")
            btn_play_src.clicked.connect(self.parent_win.on_preview_play)
            src_hdr.addWidget(self.src_name_lbl, 1)
            src_hdr.addWidget(btn_play_src)
            src_col.addLayout(src_hdr)

            src_split = QHBoxLayout()
            src_split.setSpacing(8)
            self.src_canvas = QLabel("Đang tải hình...")
            self.src_canvas.setObjectName("PreviewCanvas")
            self.src_canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.src_canvas.setFixedSize(216, 360)
            src_split.addWidget(self.src_canvas)

            self.src_info_edit = QPlainTextEdit()
            self.src_info_edit.setReadOnly(True)
            src_split.addWidget(self.src_info_edit, 1)
            src_col.addLayout(src_split, 1)

            self.src_note_lbl = QLabel(
                "Xem để kiểm tra video ổn không trước khi chạy. Đây là video GỐC (chưa ghép nền/sticker)."
            )
            self.src_note_lbl.setObjectName("MutedLabel")
            self.src_note_lbl.setWordWrap(True)
            src_col.addWidget(self.src_note_lbl)
            body.addWidget(src_box, 5)

            # 2. Khung giữa: Video ĐẦU RA để so sánh (Nút Import bên cạnh + Hình + Thông số)
            out_box = QGroupBox("2. So sánh với Video ĐẦU RA (Bấm Import bên dưới)")
            out_col = QVBoxLayout(out_box)
            out_col.setContentsMargins(8, 10, 8, 8)
            out_col.setSpacing(6)

            out_hdr = QHBoxLayout()
            out_hdr.setSpacing(6)
            btn_import_out = QPushButton("📥 Import video đầu ra...")
            btn_import_out.setObjectName("PrimaryButton")
            btn_import_out.clicked.connect(self._on_import_output)

            btn_auto_out = QPushButton("Tự động")
            btn_auto_out.setObjectName("SubtleButton")
            btn_auto_out.clicked.connect(self._on_reset_output)

            btn_play_out = QPushButton("▷ Phát đầu ra")
            btn_play_out.setObjectName("SubtleButton")
            btn_play_out.clicked.connect(self.parent_win.on_preview_play_done)

            out_hdr.addWidget(btn_import_out)
            out_hdr.addWidget(btn_auto_out)
            out_hdr.addStretch(1)
            out_hdr.addWidget(btn_play_out)
            out_col.addLayout(out_hdr)

            out_split = QHBoxLayout()
            out_split.setSpacing(8)
            self.out_canvas = QLabel("Bấm [📥 Import video đầu ra...]\nđể nạp video cần so sánh")
            self.out_canvas.setObjectName("PreviewCanvas")
            self.out_canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.out_canvas.setFixedSize(216, 360)
            out_split.addWidget(self.out_canvas)

            self.out_info_edit = QPlainTextEdit()
            self.out_info_edit.setReadOnly(True)
            src_split_placeholder = (
                "Thông số chi tiết ffprobe của Video ĐẦU RA sẽ hiện tại đây sau khi bạn bấm [📥 Import video đầu ra...]."
            )
            self.out_info_edit.setPlaceholderText(src_split_placeholder)
            out_split.addWidget(self.out_info_edit, 1)
            out_col.addLayout(out_split, 1)

            self.out_note_lbl = QLabel(
                "Bấm [📥 Import video đầu ra...] để chọn file thành phẩm bất kỳ lên đối chiếu với video gốc bên trái."
            )
            self.out_note_lbl.setObjectName("MutedLabel")
            self.out_note_lbl.setWordWrap(True)
            out_col.addWidget(self.out_note_lbl)
            body.addWidget(out_box, 5)

            # 3. Khung phải: Bảng So sánh & Kết luận phân tích tự động
            cmp_box = QGroupBox("3. Bảng So sánh & Kết luận phân tích")
            cmp_col = QVBoxLayout(cmp_box)
            cmp_col.setContentsMargins(8, 10, 8, 8)
            cmp_col.setSpacing(6)

            self.cmp_table = QTreeWidget()
            self.cmp_table.setColumnCount(4)
            self.cmp_table.setHeaderLabels([
                "Tiêu chí", "Video Gốc", "Video Đầu ra", "Đánh giá"
            ])
            self.cmp_table.setAlternatingRowColors(True)
            self.cmp_table.setRootIsDecorated(False)
            ch = self.cmp_table.header()
            ch.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            ch.resizeSection(0, 115)
            ch.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
            ch.resizeSection(1, 120)
            ch.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
            ch.resizeSection(2, 135)
            ch.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
            cmp_col.addWidget(self.cmp_table, 3)

            v_lbl = QLabel("Kết luận phân tích tự động:")
            v_lbl.setObjectName("MutedLabel")
            cmp_col.addWidget(v_lbl)

            self.verdict_edit = QPlainTextEdit()
            self.verdict_edit.setReadOnly(True)
            self.verdict_edit.setMaximumHeight(125)
            cmp_col.addWidget(self.verdict_edit, 1)
            body.addWidget(cmp_box, 5)

            root.addLayout(body, 1)

        def _on_prev(self):
            self.parent_win.prev_media_video(open_popup=True)

        def _on_next(self):
            self.parent_win.next_media_video(open_popup=True)

        def _on_import_output(self):
            self.parent_win.on_import_compare_video(parent_widget=self)

        def _on_reset_output(self):
            self.parent_win.on_reset_compare_video()

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Video Tool v2 — Studio Dark Edition (PyQt6)")
            self.resize(1260, 840)
            self.setMinimumSize(1020, 680)

            self.bridge = Bridge()
            self.log_lock = threading.Lock()
            self.active_log = {"path": None}
            self.running = {"flag": False}
            self.preview = {"player": None, "proc": None, "path": ""}
            self.layout_state = {
                "seq": 0,
                "frame_key": None,
                "frame": None,
                "combo_index": 0,
                "combo_total": 0,
            }
            self.media_state = {
                "seq": 0,
                "index": 0,
                "combos": [],
                "info_cache": {},
                "frame_cache": {},
                "compare_path": "",
                "compare_overrides": {},
                "popup": None,
            }

            self.preview_debounce = QTimer(self)
            self.preview_debounce.setSingleShot(True)
            self.preview_debounce.setInterval(180)
            self.preview_debounce.timeout.connect(self.refresh_layout_preview)

            self._build_ui()
            self._connect_signals()

            self.log("Sẵn sàng. Giao diện PyQt6 Dark UI đã khởi tạo.")
            self.schedule_layout_preview()
            self.refresh_media_tab(reset_index=True)
            QTimer.singleShot(150, lambda: self.on_scan_gpu(use_cache=True))

        # -------------------------------------------------------------------
        # Xây dựng giao diện
        # -------------------------------------------------------------------
        def _build_ui(self):
            central = QWidget()
            self.setCentralWidget(central)
            root_layout = QVBoxLayout(central)
            root_layout.setContentsMargins(14, 12, 14, 12)
            root_layout.setSpacing(10)

            # --- Thanh Header cố định trên cùng ---
            header = QFrame()
            header.setObjectName("HeaderBar")
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(16, 10, 16, 10)
            header_layout.setSpacing(12)

            title_col = QVBoxLayout()
            title_col.setSpacing(2)
            title_lbl = QLabel("Video Tool v2")
            title_lbl.setObjectName("AppTitle")
            subtitle_lbl = QLabel(
                "Batch Video • Mirror • Speed • Khung 9:16 • Tọa độ Video & Sticker • Cắt khoảng im"
            )
            subtitle_lbl.setObjectName("AppSubTitle")
            title_col.addWidget(title_lbl)
            title_col.addWidget(subtitle_lbl)
            header_layout.addLayout(title_col)
            header_layout.addStretch(1)

            self.status_badge = QLabel("Sẵn sàng.")
            self.status_badge.setObjectName("StatusBadge")
            header_layout.addWidget(self.status_badge)

            self.dry_run_chk = QCheckBox("Dry-run (chỉ in kế hoạch)")
            header_layout.addWidget(self.dry_run_chk)

            self.defaults_btn = QPushButton("Khôi phục mặc định")
            self.defaults_btn.clicked.connect(self.on_defaults)
            header_layout.addWidget(self.defaults_btn)

            self.help_btn = QPushButton("Hướng dẫn")
            self.help_btn.clicked.connect(self.on_help)
            header_layout.addWidget(self.help_btn)

            self.toggle_log_btn = QPushButton("▾ Ẩn Tiến độ & Log")
            self.toggle_log_btn.setObjectName("SubtleButton")
            self.toggle_log_btn.clicked.connect(self.toggle_bottom_log_panel)
            header_layout.addWidget(self.toggle_log_btn)

            self.run_btn = QPushButton("▶ Chạy đồng bộ")
            self.run_btn.setObjectName("PrimaryButton")
            self.run_btn.clicked.connect(self.on_run)
            header_layout.addWidget(self.run_btn)

            root_layout.addWidget(header)

            # --- Splitter dọc: Trên là 5 Tabs chức năng | Dưới là Khung Tiến độ & Log ghim cố định (có thể ẩn/hiện) ---
            self.main_splitter = QSplitter(Qt.Orientation.Vertical)
            self.main_splitter.setChildrenCollapsible(False)
            root_layout.addWidget(self.main_splitter, 1)

            self.tabs = QTabWidget()
            self.main_splitter.addWidget(self.tabs)

            self.source_tab = QWidget()
            self.layout_tab = QWidget()
            self.export_tab = QWidget()
            self.media_tab = QWidget()
            self.silence_tab = QWidget()

            self.tabs.addTab(self.source_tab, "1. Nguồn dữ liệu")
            self.tabs.addTab(self.layout_tab, "2. Bố cục & Preview")
            self.tabs.addTab(self.export_tab, "3. Xuất & GPU")
            self.tabs.addTab(self.media_tab, "4. Xem video")
            self.tabs.addTab(self.silence_tab, "5. Cắt khoảng im")

            self._build_source_tab()
            self._build_layout_tab()
            self._build_export_tab()
            self._build_media_tab()
            self._build_silence_tab()

            self.bottom_log_panel = QWidget()
            self._build_bottom_log_panel()
            self.main_splitter.addWidget(self.bottom_log_panel)
            self.main_splitter.setStretchFactor(0, 4)
            self.main_splitter.setStretchFactor(1, 1)
            self.main_splitter.setSizes([560, 210])

        def _build_source_tab(self):
            layout = QVBoxLayout(self.source_tab)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(14)

            box_in = QGroupBox("Thư mục / File đầu vào")
            grid = QGridLayout(box_in)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(10)

            self.videos_dir_edit = QLineEdit()
            self.videos_dir_edit.setPlaceholderText("Chọn thư mục chứa các video nguồn (.mp4, .mov, .mkv, .avi, .webm)...")
            btn_videos_dir = QPushButton("Chọn thư mục...")
            btn_videos_dir.clicked.connect(lambda: self._browse_dir(self.videos_dir_edit))
            btn_clear_vdir = QPushButton("Xóa")
            btn_clear_vdir.setObjectName("SubtleButton")
            btn_clear_vdir.clicked.connect(self.videos_dir_edit.clear)
            grid.addWidget(QLabel("Thư mục video:"), 0, 0)
            grid.addWidget(self.videos_dir_edit, 0, 1)
            grid.addWidget(btn_videos_dir, 0, 2)
            grid.addWidget(btn_clear_vdir, 0, 3)

            self.video_file_edit = QLineEdit()
            self.video_file_edit.setPlaceholderText("Hoặc chọn 1 file video lẻ duy nhất...")
            btn_video_file = QPushButton("Chọn file...")
            btn_video_file.clicked.connect(self._browse_video_file)
            btn_clear_vfile = QPushButton("Xóa")
            btn_clear_vfile.setObjectName("SubtleButton")
            btn_clear_vfile.clicked.connect(self.video_file_edit.clear)
            grid.addWidget(QLabel("Hoặc 1 file video:"), 1, 0)
            grid.addWidget(self.video_file_edit, 1, 1)
            grid.addWidget(btn_video_file, 1, 2)
            grid.addWidget(btn_clear_vfile, 1, 3)

            self.images_dir_edit = QLineEdit()
            self.images_dir_edit.setPlaceholderText("Thư mục chứa ảnh nền / ảnh ghép (.jpg, .png, .webp)...")
            btn_images_dir = QPushButton("Chọn thư mục...")
            btn_images_dir.clicked.connect(lambda: self._browse_dir(self.images_dir_edit))
            btn_clear_idir = QPushButton("Xóa")
            btn_clear_idir.setObjectName("SubtleButton")
            btn_clear_idir.clicked.connect(self.images_dir_edit.clear)
            grid.addWidget(QLabel("Thư mục ảnh:"), 2, 0)
            grid.addWidget(self.images_dir_edit, 2, 1)
            grid.addWidget(btn_images_dir, 2, 2)
            grid.addWidget(btn_clear_idir, 2, 3)

            self.stickers_dir_edit = QLineEdit()
            self.stickers_dir_edit.setPlaceholderText("Thư mục chứa sticker PNG/WebP trong suốt...")
            btn_stickers_dir = QPushButton("Chọn thư mục...")
            btn_stickers_dir.clicked.connect(lambda: self._browse_dir(self.stickers_dir_edit))
            btn_clear_sdir = QPushButton("Xóa")
            btn_clear_sdir.setObjectName("SubtleButton")
            btn_clear_sdir.clicked.connect(self.stickers_dir_edit.clear)
            grid.addWidget(QLabel("Thư mục sticker:"), 3, 0)
            grid.addWidget(self.stickers_dir_edit, 3, 1)
            grid.addWidget(btn_stickers_dir, 3, 2)
            grid.addWidget(btn_clear_sdir, 3, 3)

            layout.addWidget(box_in)

            box_out = QGroupBox("Ghép cặp & Đầu ra")
            out_grid = QGridLayout(box_out)
            out_grid.setHorizontalSpacing(12)
            out_grid.setVerticalSpacing(10)

            self.pair_combo = QComboBox()
            self.pair_combo.addItems(["order", "shuffle"])
            self.pair_combo.setFixedWidth(130)

            self.output_dir_edit = QLineEdit("video_done")
            btn_out_dir = QPushButton("Chọn thư mục ra...")
            btn_out_dir.clicked.connect(lambda: self._browse_dir(self.output_dir_edit))

            out_grid.addWidget(QLabel("Chế độ ghép cặp:"), 0, 0)
            out_grid.addWidget(self.pair_combo, 0, 1)
            out_grid.addWidget(QLabel("Thư mục xuất video:"), 0, 2)
            out_grid.addWidget(self.output_dir_edit, 0, 3)
            out_grid.addWidget(btn_out_dir, 0, 4)
            out_grid.setColumnStretch(3, 1)

            layout.addWidget(box_out)

            nav_row = QHBoxLayout()
            btn_to_layout = QPushButton("Tiếp theo: Chỉnh Bố cục & Xem Preview →")
            btn_to_layout.setObjectName("AccentButton")
            btn_to_layout.clicked.connect(lambda: self.tabs.setCurrentWidget(self.layout_tab))
            nav_row.addWidget(btn_to_layout)
            nav_row.addStretch(1)
            layout.addLayout(nav_row)
            layout.addStretch(1)

        def _make_coord_grid(self, prefix: str, reset_slot):
            """Tạo cụm 4 ô tọa độ Left / Right / Top / Bottom gọn gàng + nút Đặt lại 0."""
            container = QFrame()
            grid = QGridLayout(container)
            grid.setContentsMargins(0, 4, 0, 0)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(6)

            title = QLabel("Tọa độ dịch chuyển (px):")
            title.setObjectName("MutedLabel")
            grid.addWidget(title, 0, 0, 1, 8)

            spins = {}
            cols = [("Left:", "left", 0), ("Right:", "right", 2),
                    ("Top:", "top", 4), ("Bottom:", "bottom", 6)]
            for label_text, key, col in cols:
                lbl = QLabel(label_text)
                spin = QSpinBox()
                spin.setRange(-5000, 5000)
                spin.setSingleStep(10)
                spin.setValue(0)
                spin.setSuffix(" px")
                spin.setFixedWidth(92)
                grid.addWidget(lbl, 1, col)
                grid.addWidget(spin, 1, col + 1)
                spins[key] = spin

            btn_reset = QPushButton("Đặt lại 0")
            btn_reset.setObjectName("SubtleButton")
            btn_reset.clicked.connect(reset_slot)
            grid.addWidget(btn_reset, 1, 8)
            grid.setColumnStretch(9, 1)
            return container, spins

        def _build_layout_tab(self):
            outer = QHBoxLayout(self.layout_tab)
            outer.setContentsMargins(14, 14, 14, 14)
            outer.setSpacing(16)

            # --- Cột trái: Các bảng điều khiển bố cục ---
            left_scroll = QScrollArea()
            left_scroll.setWidgetResizable(True)
            left_scroll.setFrameShape(QFrame.Shape.NoFrame)
            left_container = QWidget()
            left_col = QVBoxLayout(left_container)
            left_col.setContentsMargins(0, 0, 4, 0)
            left_col.setSpacing(12)

            # 1. Mirror & Tốc độ gộp chung 1 hàng gọn gàng
            box_ms = QGroupBox("Mirror & Tốc độ phát")
            ms_layout = QHBoxLayout(box_ms)
            ms_layout.setSpacing(16)
            self.mirror_chk = QCheckBox("Bật Mirror (lật ngang video)")
            self.mirror_chk.setChecked(True)
            self.speed_on_chk = QCheckBox("Bật tăng tốc:")
            self.speed_on_chk.setChecked(True)
            self.speed_spin = QDoubleSpinBox()
            self.speed_spin.setRange(0.05, 8.0)
            self.speed_spin.setSingleStep(0.05)
            self.speed_spin.setDecimals(2)
            self.speed_spin.setValue(1.20)
            self.speed_spin.setSuffix("x")
            self.speed_spin.setFixedWidth(90)
            ms_layout.addWidget(self.mirror_chk)
            ms_layout.addSpacing(12)
            ms_layout.addWidget(self.speed_on_chk)
            ms_layout.addWidget(self.speed_spin)
            ms_layout.addStretch(1)
            left_col.addWidget(box_ms)

            # 2. Ảnh nền & Khung 9:16 + Tọa độ Video
            box_video = QGroupBox("Ảnh nền, Khung 9:16 & Căn chỉnh Video")
            v_layout = QVBoxLayout(box_video)
            v_layout.setSpacing(10)

            row_img = QHBoxLayout()
            self.image_on_chk = QCheckBox("Bật ghép ảnh")
            self.image_on_chk.setChecked(True)
            self.image_mode_combo = QComboBox()
            self.image_mode_combo.addItems(["corner", "full", "banner"])
            self.image_mode_combo.setFixedWidth(105)
            self.image_opacity_spin = QDoubleSpinBox()
            self.image_opacity_spin.setRange(0.0, 1.0)
            self.image_opacity_spin.setSingleStep(0.05)
            self.image_opacity_spin.setDecimals(2)
            self.image_opacity_spin.setValue(0.85)
            self.image_opacity_spin.setFixedWidth(85)

            row_img.addWidget(self.image_on_chk)
            row_img.addSpacing(10)
            row_img.addWidget(QLabel("Chế độ (khi tắt 9:16):"))
            row_img.addWidget(self.image_mode_combo)
            row_img.addSpacing(10)
            row_img.addWidget(QLabel("Độ mờ:"))
            row_img.addWidget(self.image_opacity_spin)
            row_img.addStretch(1)
            v_layout.addLayout(row_img)

            row_916 = QHBoxLayout()
            self.frame_916_chk = QCheckBox("Khung dọc 9:16 (1080×1920)")
            self.frame_916_chk.setChecked(True)
            self.video_scale_spin = QDoubleSpinBox()
            self.video_scale_spin.setRange(0.05, 1.0)
            self.video_scale_spin.setSingleStep(0.02)
            self.video_scale_spin.setDecimals(2)
            self.video_scale_spin.setValue(0.94)
            self.video_scale_spin.setFixedWidth(85)
            self.video_pos_combo = QComboBox()
            self.video_pos_combo.addItems([
                "center", "top", "bottom", "left", "right",
                "top-left", "top-right", "bottom-left", "bottom-right",
            ])
            self.video_pos_combo.setFixedWidth(125)

            row_916.addWidget(self.frame_916_chk)
            row_916.addSpacing(10)
            row_916.addWidget(QLabel("Tỉ lệ video:"))
            row_916.addWidget(self.video_scale_spin)
            row_916.addSpacing(10)
            row_916.addWidget(QLabel("Vị trí neo:"))
            row_916.addWidget(self.video_pos_combo)
            row_916.addStretch(1)
            v_layout.addLayout(row_916)

            v_coord_widget, self.video_coord_spins = self._make_coord_grid(
                "video", self.reset_video_coords
            )
            v_layout.addWidget(v_coord_widget)

            # Hàng nút căn nhanh cho Video
            quick_v = QHBoxLayout()
            quick_v_lbl = QLabel("Căn nhanh Video:")
            quick_v_lbl.setObjectName("MutedLabel")
            quick_v.addWidget(quick_v_lbl)
            for label_txt, pos_val in [
                ("Giữa", "center"), ("Trên", "top"), ("Dưới", "bottom"),
                ("Trái", "left"), ("Phải", "right"),
            ]:
                b = QPushButton(label_txt)
                b.setObjectName("SubtleButton")
                b.clicked.connect(
                    lambda _=False, p=pos_val: self._quick_align_video(p)
                )
                quick_v.addWidget(b)
            quick_v.addStretch(1)
            v_layout.addLayout(quick_v)

            left_col.addWidget(box_video)

            # 3. Sticker & Tọa độ Sticker
            box_sticker = QGroupBox("Sticker & Căn chỉnh tọa độ Sticker")
            s_layout = QVBoxLayout(box_sticker)
            s_layout.setSpacing(10)

            row_stk = QHBoxLayout()
            self.sticker_on_chk = QCheckBox("Bật ghép sticker")
            self.sticker_on_chk.setChecked(True)
            self.sticker_scale_spin = QDoubleSpinBox()
            self.sticker_scale_spin.setRange(0.01, 1.0)
            self.sticker_scale_spin.setSingleStep(0.02)
            self.sticker_scale_spin.setDecimals(2)
            self.sticker_scale_spin.setValue(0.15)
            self.sticker_scale_spin.setFixedWidth(85)
            self.sticker_pos_combo = QComboBox()
            self.sticker_pos_combo.addItems([
                "auto-corners", "bottom-right", "top-right", "bottom-left", "top-left",
                "center", "top", "bottom", "left", "right",
            ])
            self.sticker_pos_combo.setCurrentText("auto-corners")
            self.sticker_pos_combo.setFixedWidth(135)

            row_stk.addWidget(self.sticker_on_chk)
            row_stk.addSpacing(10)
            row_stk.addWidget(QLabel("Cỡ (rộng/video):"))
            row_stk.addWidget(self.sticker_scale_spin)
            row_stk.addSpacing(10)
            row_stk.addWidget(QLabel("Vị trí neo:"))
            row_stk.addWidget(self.sticker_pos_combo)
            row_stk.addStretch(1)
            s_layout.addLayout(row_stk)

            s_coord_widget, self.sticker_coord_spins = self._make_coord_grid(
                "sticker", self.reset_sticker_coords
            )
            s_layout.addWidget(s_coord_widget)

            # Hàng nút căn nhanh cho Sticker
            quick_s = QHBoxLayout()
            quick_s_lbl = QLabel("Căn nhanh Sticker:")
            quick_s_lbl.setObjectName("MutedLabel")
            quick_s.addWidget(quick_s_lbl)
            for label_txt, pos_val in [
                ("Auto 4 góc", "auto-corners"),
                ("Góc phải dưới", "bottom-right"),
                ("Góc phải trên", "top-right"),
                ("Góc trái dưới", "bottom-left"),
                ("Góc trái trên", "top-left"),
                ("Giữa", "center"),
            ]:
                b = QPushButton(label_txt)
                b.setObjectName("SubtleButton")
                b.clicked.connect(
                    lambda _=False, p=pos_val: self._quick_align_sticker(p)
                )
                quick_s.addWidget(b)
            quick_s.addStretch(1)
            s_layout.addLayout(quick_s)

            left_col.addWidget(box_sticker)
            left_col.addStretch(1)
            left_scroll.setWidget(left_container)
            outer.addWidget(left_scroll, 3)

            # --- Cột phải: Khung Preview trực tiếp ---
            preview_box = QGroupBox("Preview bố cục đầu ra (Cập nhật trực tiếp)")
            p_layout = QVBoxLayout(preview_box)
            p_layout.setSpacing(10)

            nav_combo_row = QHBoxLayout()
            self.btn_prev_combo = QPushButton("◀ Trước")
            self.btn_prev_combo.setObjectName("SubtleButton")
            self.btn_prev_combo.clicked.connect(self.prev_preview_combo)
            self.combo_indicator_lbl = QLabel("Tổ hợp: 0 / 0")
            self.combo_indicator_lbl.setObjectName("StatusBadge")
            self.combo_indicator_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.btn_next_combo = QPushButton("Tiếp (Next) ▶")
            self.btn_next_combo.setObjectName("AccentButton")
            self.btn_next_combo.clicked.connect(self.next_preview_combo)
            nav_combo_row.addWidget(self.btn_prev_combo)
            nav_combo_row.addWidget(self.combo_indicator_lbl, 1)
            nav_combo_row.addWidget(self.btn_next_combo)
            p_layout.addLayout(nav_combo_row)

            self.layout_preview_label = QLabel(
                "Chưa có video\nChọn file hoặc thư mục video ở tab Nguồn"
            )
            self.layout_preview_label.setObjectName("PreviewCanvas")
            self.layout_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout_preview_label.setMinimumSize(320, 410)
            self.layout_preview_label.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            p_layout.addWidget(self.layout_preview_label, 1)

            self.layout_preview_status_lbl = QLabel(
                "Chọn video/ảnh/sticker để xem trước bố cục."
            )
            self.layout_preview_status_lbl.setObjectName("MutedLabel")
            self.layout_preview_status_lbl.setWordWrap(True)
            p_layout.addWidget(self.layout_preview_status_lbl)

            p_btn_row = QHBoxLayout()
            btn_refresh_preview = QPushButton("Làm mới Preview")
            btn_refresh_preview.clicked.connect(self.refresh_layout_preview)
            btn_reset_all_coords = QPushButton("Đặt lại mọi tọa độ về 0")
            btn_reset_all_coords.setObjectName("SubtleButton")
            btn_reset_all_coords.clicked.connect(self._reset_all_coords)
            p_btn_row.addWidget(btn_refresh_preview)
            p_btn_row.addWidget(btn_reset_all_coords)
            p_btn_row.addStretch(1)
            p_layout.addLayout(p_btn_row)

            outer.addWidget(preview_box, 2)

        def _build_export_tab(self):
            layout = QVBoxLayout(self.export_tab)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(14)

            box_q = QGroupBox("Chất lượng & Bitrate")
            q_layout = QHBoxLayout(box_q)
            q_layout.setSpacing(12)
            self.quality_mode_combo = QComboBox()
            self.quality_mode_combo.addItems(["source", "bitrate", "crf"])
            self.quality_mode_combo.setFixedWidth(130)
            self.quality_value_edit = QLineEdit()
            self.quality_value_edit.setPlaceholderText("Để trống nếu chọn source; VD: 8M, 4000k hoặc CRF 20")
            self.quality_value_edit.setFixedWidth(280)
            q_layout.addWidget(QLabel("Chế độ chất lượng:"))
            q_layout.addWidget(self.quality_mode_combo)
            q_layout.addSpacing(12)
            q_layout.addWidget(QLabel("Giá trị:"))
            q_layout.addWidget(self.quality_value_edit)
            q_layout.addStretch(1)
            layout.addWidget(box_q)

            box_gpu = QGroupBox("GPU & Hiệu năng xử lý song song")
            g_grid = QGridLayout(box_gpu)
            g_grid.setHorizontalSpacing(12)
            g_grid.setVerticalSpacing(10)

            self.scan_gpu_btn = QPushButton("Quét GPU")
            self.scan_gpu_btn.setObjectName("AccentButton")
            self.scan_gpu_btn.clicked.connect(lambda: self.on_scan_gpu(use_cache=False))
            btn_use_cpu = QPushButton("Dùng CPU (libx264)")
            btn_use_cpu.clicked.connect(self.on_use_cpu)

            self.encoder_combo = QComboBox()
            self.encoder_combo.setEditable(True)
            self.encoder_combo.addItems([
                "auto", "libx264", "h264_nvenc", "h264_qsv", "h264_amf", "h264_vaapi"
            ])
            self.encoder_combo.setFixedWidth(140)

            self.preset_edit = QLineEdit()
            self.preset_edit.setPlaceholderText("Tự động")
            self.preset_edit.setFixedWidth(120)

            g_grid.addWidget(self.scan_gpu_btn, 0, 0)
            g_grid.addWidget(btn_use_cpu, 0, 1)
            g_grid.addWidget(QLabel("Encoder:"), 0, 2)
            g_grid.addWidget(self.encoder_combo, 0, 3)
            g_grid.addWidget(QLabel("Preset:"), 0, 4)
            g_grid.addWidget(self.preset_edit, 0, 5)
            g_grid.setColumnStretch(6, 1)

            self.gpu_profile_combo = QComboBox()
            self.gpu_profile_combo.addItems(list(GPU_PROFILES.keys()))
            self.gpu_profile_combo.setFixedWidth(250)

            self.workers_spin = QSpinBox()
            self.workers_spin.setRange(0, 16)
            self.workers_spin.setValue(0)
            self.workers_spin.setFixedWidth(85)

            self.threads_spin = QSpinBox()
            self.threads_spin.setRange(0, 128)
            self.threads_spin.setValue(0)
            self.threads_spin.setFixedWidth(85)

            g_grid.addWidget(QLabel("Chế độ GPU:"), 1, 0)
            g_grid.addWidget(self.gpu_profile_combo, 1, 1, 1, 2)
            g_grid.addWidget(QLabel("Workers (0 = tự động):"), 1, 3)
            g_grid.addWidget(self.workers_spin, 1, 4)
            g_grid.addWidget(QLabel("Threads/worker:"), 1, 5)
            g_grid.addWidget(self.threads_spin, 1, 6)

            self.gpu_info_lbl = QLabel("Đang tự nhận diện GPU và bản FFmpeg phù hợp...")
            self.gpu_info_lbl.setObjectName("MutedLabel")
            self.gpu_info_lbl.setWordWrap(True)
            g_grid.addWidget(self.gpu_info_lbl, 2, 0, 1, 7)

            layout.addWidget(box_gpu)

            box_chunk = QGroupBox("Video dài — Chia đoạn an toàn (06_chunk.py)")
            c_layout = QHBoxLayout(box_chunk)
            c_layout.setSpacing(16)
            self.chunk_chk = QCheckBox("Chia video dài thành từng đoạn")
            self.chunk_chk.setChecked(True)
            self.chunk_seconds_spin = QSpinBox()
            self.chunk_seconds_spin.setRange(10, 3600)
            self.chunk_seconds_spin.setSingleStep(60)
            self.chunk_seconds_spin.setValue(300)
            self.chunk_seconds_spin.setSuffix(" s")
            self.chunk_seconds_spin.setFixedWidth(100)
            self.resume_chk = QCheckBox("Tiếp tục đoạn đã xử lý (Resume)")
            self.resume_chk.setChecked(True)
            self.keep_chunks_chk = QCheckBox("Giữ lại file đoạn tạm")

            c_layout.addWidget(self.chunk_chk)
            c_layout.addWidget(QLabel("Độ dài mỗi đoạn:"))
            c_layout.addWidget(self.chunk_seconds_spin)
            c_layout.addWidget(self.resume_chk)
            c_layout.addWidget(self.keep_chunks_chk)
            c_layout.addStretch(1)
            layout.addWidget(box_chunk)
            layout.addStretch(1)

        def _build_media_tab(self):
            layout = QVBoxLayout(self.media_tab)
            layout.setContentsMargins(12, 10, 12, 10)
            layout.setSpacing(8)

            # --- Bảng danh sách video lần lượt từ Nguồn (Bấm [▷ Xem] mới mở Popup xem & so sánh) ---
            list_box = QGroupBox(
                "Danh sách video đã import từ Nguồn — Bấm nút [▷ Xem] ở cột Hành động (hoặc đúp chuột) để mở Popup Xem trước & So sánh"
            )
            list_col = QVBoxLayout(list_box)
            list_col.setContentsMargins(8, 8, 8, 8)
            list_col.setSpacing(6)

            nav_bar = QHBoxLayout()
            nav_bar.setSpacing(8)
            self.btn_media_prev = QPushButton("◀ Trước")
            self.btn_media_prev.setObjectName("SubtleButton")
            self.btn_media_prev.clicked.connect(lambda: self.prev_media_video(open_popup=False))

            self.btn_media_next = QPushButton("Tiếp (Next) ▶")
            self.btn_media_next.setObjectName("SubtleButton")
            self.btn_media_next.clicked.connect(lambda: self.next_media_video(open_popup=False))

            self.media_count_badge = QLabel("0 / 0 video")
            self.media_count_badge.setObjectName("StatusBadge")

            btn_open_selected = QPushButton("▷ Xem & So sánh video đang chọn (Popup)")
            btn_open_selected.setObjectName("AccentButton")
            btn_open_selected.clicked.connect(self.open_current_media_popup)

            btn_reload_media = QPushButton("🔄 Làm mới danh sách")
            btn_reload_media.setObjectName("SubtleButton")
            btn_reload_media.clicked.connect(lambda: self.refresh_media_tab(reset_index=False))

            nav_bar.addWidget(self.btn_media_prev)
            nav_bar.addWidget(self.btn_media_next)
            nav_bar.addWidget(self.media_count_badge)
            nav_bar.addSpacing(8)
            nav_bar.addWidget(btn_open_selected)
            nav_bar.addStretch(1)
            nav_bar.addWidget(btn_reload_media)
            list_col.addLayout(nav_bar)

            self.media_list_table = QTreeWidget()
            self.media_list_table.setColumnCount(7)
            self.media_list_table.setHeaderLabels([
                "#", "Tên video gốc", "Dung lượng", "Cập nhật gần nhất",
                "Ảnh & Sticker ghép", "Trạng thái đầu ra", "Hành động"
            ])
            self.media_list_table.setAlternatingRowColors(True)
            self.media_list_table.setRootIsDecorated(False)
            self.media_list_table.currentItemChanged.connect(self._on_media_table_item_changed)
            self.media_list_table.itemDoubleClicked.connect(
                lambda item, _col: self.open_media_popup(
                    int(item.data(0, Qt.ItemDataRole.UserRole) or 0)
                )
            )
            mh = self.media_list_table.header()
            mh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            mh.resizeSection(0, 45)
            mh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            mh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            mh.resizeSection(2, 95)
            mh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
            mh.resizeSection(3, 135)
            mh.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
            mh.resizeSection(4, 240)
            mh.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
            mh.resizeSection(5, 160)
            mh.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
            mh.resizeSection(6, 100)
            list_col.addWidget(self.media_list_table, 1)

            hint_lbl = QLabel(
                "💡 Mẹo: Video và thông số chi tiết sẽ hiện trên cửa sổ Popup riêng khi bạn bấm [▷ Xem] ở từng dòng — giúp màn hình danh sách luôn gọn gàng, rộng rãi."
            )
            hint_lbl.setObjectName("MutedLabel")
            list_col.addWidget(hint_lbl)
            layout.addWidget(list_box, 1)

        def _build_silence_tab(self):
            layout = QVBoxLayout(self.silence_tab)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(12)

            top_bar = QHBoxLayout()
            btn_pick = QPushButton("Chọn video KOC...")
            btn_pick.clicked.connect(self.on_pick_silence)
            self.sil_path_edit = QLineEdit()
            self.sil_path_edit.setPlaceholderText("Chọn file video cần quét hoặc cắt riêng khoảng lặng...")
            self.btn_sil_scan = QPushButton("🔍 Quét khoảng im")
            self.btn_sil_scan.setObjectName("AccentButton")
            self.btn_sil_scan.clicked.connect(self.on_silence_scan)
            self.btn_sil_cut = QPushButton("✂ Cắt khoảng im ngay")
            self.btn_sil_cut.setObjectName("PrimaryButton")
            self.btn_sil_cut.clicked.connect(self.on_silence_cut)

            top_bar.addWidget(btn_pick)
            top_bar.addWidget(self.sil_path_edit, 1)
            top_bar.addWidget(self.btn_sil_scan)
            top_bar.addWidget(self.btn_sil_cut)
            layout.addLayout(top_bar)

            box_cfg = QGroupBox("Thông số nhận diện & Phanh an toàn")
            grid = QGridLayout(box_cfg)
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(10)

            self.sil_preset_combo = QComboBox()
            self.sil_preset_combo.addItems(["Nhẹ", "Vừa", "Mạnh", "Tự chọn"])
            self.sil_preset_combo.setCurrentText("Vừa")
            self.sil_preset_combo.currentTextChanged.connect(self.on_sil_preset)

            self.sil_mode_combo = QComboBox()
            self.sil_mode_combo.addItems(["relative", "absolute"])

            self.sil_margin_spin = QDoubleSpinBox()
            self.sil_margin_spin.setRange(1.0, 80.0)
            self.sil_margin_spin.setValue(20.0)
            self.sil_margin_spin.setSuffix(" dB")

            self.sil_threshold_spin = QDoubleSpinBox()
            self.sil_threshold_spin.setRange(-90.0, 0.0)
            self.sil_threshold_spin.setValue(-40.0)
            self.sil_threshold_spin.setSuffix(" dB")

            grid.addWidget(QLabel("Preset:"), 0, 0)
            grid.addWidget(self.sil_preset_combo, 0, 1)
            grid.addWidget(QLabel("Chế độ ngưỡng:"), 0, 2)
            grid.addWidget(self.sil_mode_combo, 0, 3)
            grid.addWidget(QLabel("Margin tương đối:"), 0, 4)
            grid.addWidget(self.sil_margin_spin, 0, 5)
            grid.addWidget(QLabel("Ngưỡng tuyệt đối:"), 0, 6)
            grid.addWidget(self.sil_threshold_spin, 0, 7)

            self.sil_min_silence_spin = QDoubleSpinBox()
            self.sil_min_silence_spin.setRange(0.1, 30.0)
            self.sil_min_silence_spin.setSingleStep(0.1)
            self.sil_min_silence_spin.setValue(0.5)
            self.sil_min_silence_spin.setSuffix(" s")

            self.sil_min_cut_spin = QDoubleSpinBox()
            self.sil_min_cut_spin.setRange(0.2, 60.0)
            self.sil_min_cut_spin.setSingleStep(0.1)
            self.sil_min_cut_spin.setValue(1.0)
            self.sil_min_cut_spin.setSuffix(" s")

            self.sil_pad_spin = QDoubleSpinBox()
            self.sil_pad_spin.setRange(0.0, 5.0)
            self.sil_pad_spin.setSingleStep(0.05)
            self.sil_pad_spin.setValue(0.2)
            self.sil_pad_spin.setSuffix(" s")

            self.sil_min_keep_spin = QDoubleSpinBox()
            self.sil_min_keep_spin.setRange(0.0, 30.0)
            self.sil_min_keep_spin.setSingleStep(0.1)
            self.sil_min_keep_spin.setValue(0.8)
            self.sil_min_keep_spin.setSuffix(" s")

            grid.addWidget(QLabel("Nhận im từ:"), 1, 0)
            grid.addWidget(self.sil_min_silence_spin, 1, 1)
            grid.addWidget(QLabel("Chỉ cắt khi dài hơn:"), 1, 2)
            grid.addWidget(self.sil_min_cut_spin, 1, 3)
            grid.addWidget(QLabel("Đệm giữ lại:"), 1, 4)
            grid.addWidget(self.sil_pad_spin, 1, 5)
            grid.addWidget(QLabel("Đoạn nói tối thiểu:"), 1, 6)
            grid.addWidget(self.sil_min_keep_spin, 1, 7)

            self.sil_max_cut_ratio_spin = QDoubleSpinBox()
            self.sil_max_cut_ratio_spin.setRange(0.0, 100.0)
            self.sil_max_cut_ratio_spin.setSingleStep(5.0)
            self.sil_max_cut_ratio_spin.setValue(30.0)
            self.sil_max_cut_ratio_spin.setSuffix(" %")

            self.sil_max_keep_spin = QDoubleSpinBox()
            self.sil_max_keep_spin.setRange(0.0, 120.0)
            self.sil_max_keep_spin.setSingleStep(0.5)
            self.sil_max_keep_spin.setValue(5.0)
            self.sil_max_keep_spin.setSuffix(" s")

            self.sil_trim_ends_chk = QCheckBox("Cắt mạnh đầu/cuối")
            self.sil_trim_ends_chk.setChecked(True)
            self.sil_batch_chk = QCheckBox("Áp dụng cắt khoảng im khi chạy Batch")
            self.sil_batch_chk.setChecked(True)
            self.sil_safety_chk = QCheckBox("Bật phanh an toàn")
            self.sil_safety_chk.setChecked(True)

            grid.addWidget(QLabel("Trần cắt tổng:"), 2, 0)
            grid.addWidget(self.sil_max_cut_ratio_spin, 2, 1)
            grid.addWidget(QLabel("Giữ tối đa/khoảng im:"), 2, 2)
            grid.addWidget(self.sil_max_keep_spin, 2, 3)
            grid.addWidget(self.sil_trim_ends_chk, 2, 4, 1, 2)
            grid.addWidget(self.sil_batch_chk, 3, 0, 1, 4)
            grid.addWidget(self.sil_safety_chk, 3, 4, 1, 4)

            layout.addWidget(box_cfg)

            self.sil_text = QPlainTextEdit()
            self.sil_text.setReadOnly(True)
            self.sil_text.setPlaceholderText("Báo cáo quét khoảng im sẽ hiển thị chi tiết tại đây...")
            layout.addWidget(self.sil_text, 1)

        def _build_bottom_log_panel(self):
            box = QGroupBox("Tiến độ & Nhật ký xử lý (Ghim cố định — có thể ẩn/hiện)")
            layout = QVBoxLayout(self.bottom_log_panel)
            layout.setContentsMargins(0, 2, 0, 0)
            layout.addWidget(box)

            b_col = QVBoxLayout(box)
            b_col.setContentsMargins(10, 10, 10, 8)
            b_col.setSpacing(6)

            top_row = QHBoxLayout()
            top_row.setSpacing(8)
            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)

            btn_clear_log = QPushButton("Xóa nhật ký")
            btn_clear_log.setObjectName("SubtleButton")
            btn_clear_log.clicked.connect(self.log_text_clear)

            btn_hide_log = QPushButton("▾ Ẩn khung Log")
            btn_hide_log.setObjectName("SubtleButton")
            btn_hide_log.clicked.connect(self.toggle_bottom_log_panel)

            top_row.addWidget(QLabel("Tiến độ tổng:"))
            top_row.addWidget(self.progress_bar, 1)
            top_row.addWidget(btn_clear_log)
            top_row.addWidget(btn_hide_log)
            b_col.addLayout(top_row)

            split_row = QHBoxLayout()
            split_row.setSpacing(8)

            self.worker_table = QTreeWidget()
            self.worker_table.setColumnCount(4)
            self.worker_table.setHeaderLabels(["Worker", "Video đang xử lý", "Tiến độ", "Trạng thái"])
            self.worker_table.setAlternatingRowColors(True)
            self.worker_table.setRootIsDecorated(False)
            self.worker_table.setMinimumHeight(85)
            header = self.worker_table.header()
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(0, 80)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(2, 70)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(3, 130)
            split_row.addWidget(self.worker_table, 2)

            self.log_text = QPlainTextEdit()
            self.log_text.setReadOnly(True)
            self.log_text.setMinimumHeight(85)
            split_row.addWidget(self.log_text, 3)

            b_col.addLayout(split_row, 1)

        def toggle_bottom_log_panel(self):
            visible = not self.bottom_log_panel.isVisible()
            self.bottom_log_panel.setVisible(visible)
            self.toggle_log_btn.setText(
                "▾ Ẩn Tiến độ & Log" if visible else "▴ Hiện Tiến độ & Log"
            )

        # -------------------------------------------------------------------
        # Kết nối sự kiện
        # -------------------------------------------------------------------
        def _connect_signals(self):
            self.bridge.log_signal.connect(self._append_log)
            self.bridge.progress_signal.connect(self._update_progress)
            self.bridge.preview_ready_signal.connect(self._apply_layout_preview)
            self.bridge.preview_error_signal.connect(self._apply_layout_preview_error)
            self.bridge.popup_inspect_ready_signal.connect(self._apply_popup_inspect)
            self.bridge.popup_inspect_error_signal.connect(self._apply_popup_inspect_error)
            self.bridge.gpu_ready_signal.connect(self._on_gpu_ready)
            self.bridge.gpu_error_signal.connect(
                lambda msg: QMessageBox.critical(self, "Lỗi quét GPU", msg)
            )
            self.bridge.gpu_done_signal.connect(self._on_gpu_done)
            self.bridge.batch_done_signal.connect(self._on_batch_done)
            self.bridge.batch_error_signal.connect(
                lambda msg: QMessageBox.critical(self, "Lỗi xử lý", msg)
            )
            self.bridge.batch_finally_signal.connect(lambda: self.set_running(False))

            self.bridge.silence_scan_ready_signal.connect(self._on_silence_scan_ready)
            self.bridge.silence_scan_error_signal.connect(self._on_silence_scan_error)
            self.bridge.silence_scan_finally_signal.connect(lambda: self.set_running(False))

            self.bridge.silence_cut_done_signal.connect(self._on_silence_cut_done)
            self.bridge.silence_cut_error_signal.connect(
                lambda msg: QMessageBox.critical(self, "Lỗi cắt khoảng lặng", msg)
            )
            self.bridge.silence_cut_finally_signal.connect(lambda: self.set_running(False))

            self.tabs.currentChanged.connect(self._on_tab_changed)

            # Tự động cập nhật preview khi thay đổi bất kỳ thông số nguồn / bố cục / tọa độ
            for edit in (
                self.videos_dir_edit, self.video_file_edit,
                self.images_dir_edit, self.stickers_dir_edit,
            ):
                edit.textChanged.connect(self._on_sources_changed)

            self.output_dir_edit.textChanged.connect(
                lambda _: self.refresh_media_tab(reset_index=False)
                if self.tabs.currentWidget() is self.media_tab else None
            )
            self.pair_combo.currentTextChanged.connect(self._on_sources_changed)

            for chk in (
                self.mirror_chk, self.speed_on_chk, self.image_on_chk,
                self.frame_916_chk, self.sticker_on_chk,
                self.chunk_chk, self.sil_batch_chk,
            ):
                chk.toggled.connect(self._on_layout_or_config_changed)

            for combo in (
                self.image_mode_combo, self.video_pos_combo, self.sticker_pos_combo,
                self.quality_mode_combo, self.encoder_combo,
            ):
                combo.currentTextChanged.connect(self._on_layout_or_config_changed)

            self.quality_value_edit.textChanged.connect(self._on_layout_or_config_changed)

            for spin in (
                self.speed_spin, self.image_opacity_spin,
                self.video_scale_spin, self.sticker_scale_spin,
                self.chunk_seconds_spin,
                *self.video_coord_spins.values(),
                *self.sticker_coord_spins.values(),
            ):
                spin.valueChanged.connect(self._on_layout_or_config_changed)

        # -------------------------------------------------------------------
        # Các hàm tiện ích giao diện
        # -------------------------------------------------------------------
        def log_text_clear(self):
            self.log_text.clear()

        def log(self, msg):
            timestamp = datetime.now().strftime("%H:%M:%S")
            lines = str(msg).splitlines() or [""]
            formatted = "\n".join(f"[{timestamp}] {line}" for line in lines)
            with self.log_lock:
                path = self.active_log["path"]
                if path:
                    with path.open("a", encoding="utf-8") as handle:
                        handle.write(formatted + "\n")
            self.bridge.log_signal.emit(formatted)

        def _append_log(self, text: str):
            self.log_text.appendPlainText(text)

        def emit_progress(self, event: dict):
            self.bridge.progress_signal.emit(event)

        def _update_progress(self, payload: dict):
            worker = payload["worker"]
            key = f"Worker {worker}"
            found = None
            for i in range(self.worker_table.topLevelItemCount()):
                it = self.worker_table.topLevelItem(i)
                if it.text(0) == key:
                    found = it
                    break
            if found is None:
                found = QTreeWidgetItem([key, "", "", ""])
                self.worker_table.addTopLevelItem(found)
            found.setText(1, str(payload["video"]))
            found.setText(2, f"{payload['percent']}%")
            found.setText(3, str(payload["status"]))
            self.progress_bar.setValue(int(payload["overall"]))
            self.status_badge.setText(
                f"Đang chạy {payload['overall']}% — {payload['index']}/{payload['total']} video"
            )

        def _browse_dir(self, target_edit: QLineEdit):
            d = QFileDialog.getExistingDirectory(self, "Chọn thư mục")
            if d:
                target_edit.setText(d)

        def _browse_video_file(self):
            f, _ = QFileDialog.getOpenFileName(
                self, "Chọn 1 file video", "",
                "Video (*.mp4 *.mov *.mkv *.avi *.webm)"
            )
            if f:
                self.video_file_edit.setText(f)

        def reset_video_coords(self):
            for spin in self.video_coord_spins.values():
                spin.blockSignals(True)
                spin.setValue(0)
                spin.blockSignals(False)
            self.schedule_layout_preview()

        def reset_sticker_coords(self):
            for spin in self.sticker_coord_spins.values():
                spin.blockSignals(True)
                spin.setValue(0)
                spin.blockSignals(False)
            self.schedule_layout_preview()

        def _reset_all_coords(self):
            self.reset_video_coords()
            self.reset_sticker_coords()

        def _quick_align_video(self, pos: str):
            self.video_pos_combo.setCurrentText(pos)
            self.reset_video_coords()

        def _quick_align_sticker(self, pos: str):
            self.sticker_pos_combo.setCurrentText(pos)
            self.reset_sticker_coords()

        # -------------------------------------------------------------------
        # Preview bố cục trực tiếp & Điều hướng Tổ hợp (Trước / Next)
        # -------------------------------------------------------------------
        def _on_sources_changed(self, *_args):
            self.layout_state["combo_index"] = 0
            self.media_state["index"] = 0
            self.schedule_layout_preview()
            self.refresh_media_tab(reset_index=True)

        def _on_layout_or_config_changed(self, *_args):
            self.schedule_layout_preview()
            popup = self.media_state.get("popup")
            if popup is not None and popup.isVisible():
                self._inspect_popup_video()

        def _on_tab_changed(self, _idx: int):
            if self.tabs.currentWidget() is self.media_tab:
                self.refresh_media_tab(reset_index=False)

        def _on_batch_done(self, log_path: str):
            self.refresh_media_tab(reset_index=False)
            QMessageBox.information(
                self, "Hoàn tất", f"Đã xử lý xong.\nNhật ký: {log_path}"
            )

        def prev_preview_combo(self):
            total = self.layout_state.get("combo_total", 0)
            if total > 1:
                self.layout_state["combo_index"] = (self.layout_state["combo_index"] - 1) % total
                self.media_state["index"] = self.layout_state["combo_index"]
                self.refresh_layout_preview()

        def next_preview_combo(self):
            total = self.layout_state.get("combo_total", 0)
            if total > 1:
                self.layout_state["combo_index"] = (self.layout_state["combo_index"] + 1) % total
                self.media_state["index"] = self.layout_state["combo_index"]
                self.refresh_layout_preview()

        def schedule_layout_preview(self, *_args):
            self.preview_debounce.start()

        def refresh_layout_preview(self):
            self.layout_state["seq"] += 1
            token = self.layout_state["seq"]
            try:
                combos = layout_preview_mod.list_preview_combinations(
                    self.videos_dir_edit.text().strip(),
                    self.video_file_edit.text().strip(),
                    self.images_dir_edit.text().strip(),
                    self.stickers_dir_edit.text().strip(),
                    self.image_on_chk.isChecked(),
                    self.sticker_on_chk.isChecked(),
                    pair=self.pair_combo.currentText(),
                    seed=0,
                )
                total = len(combos)
                self.layout_state["combo_total"] = total
                if total > 0:
                    idx = self.layout_state["combo_index"] % total
                    self.layout_state["combo_index"] = idx
                    video, image, sticker = combos[idx]
                else:
                    idx = 0
                    video, image, sticker = None, None, None

                stk_pos_setting = self.sticker_pos_combo.currentText()
                effective_stk_pos = layout_preview_mod.resolve_sticker_position(
                    stk_pos_setting, index=idx
                )
                if total > 0:
                    self.combo_indicator_lbl.setText(
                        f"Tổ hợp {idx + 1} / {total}  •  Sticker: {effective_stk_pos}"
                    )
                else:
                    self.combo_indicator_lbl.setText("Tổ hợp: 0 / 0")
                self.btn_prev_combo.setEnabled(total > 1)
                self.btn_next_combo.setEnabled(total > 1)

                config = {
                    "combo_index": idx,
                    "mirror": self.mirror_chk.isChecked(),
                    "image_on": self.image_on_chk.isChecked(),
                    "image_mode": self.image_mode_combo.currentText(),
                    "image_opacity": self.image_opacity_spin.value(),
                    "frame_916": self.frame_916_chk.isChecked(),
                    "video_scale": self.video_scale_spin.value(),
                    "video_position": self.video_pos_combo.currentText(),
                    "video_left": self.video_coord_spins["left"].value(),
                    "video_right": self.video_coord_spins["right"].value(),
                    "video_top": self.video_coord_spins["top"].value(),
                    "video_bottom": self.video_coord_spins["bottom"].value(),
                    "sticker_on": self.sticker_on_chk.isChecked(),
                    "sticker_scale": self.sticker_scale_spin.value(),
                    "sticker_position": stk_pos_setting,
                    "sticker_left": self.sticker_coord_spins["left"].value(),
                    "sticker_right": self.sticker_coord_spins["right"].value(),
                    "sticker_top": self.sticker_coord_spins["top"].value(),
                    "sticker_bottom": self.sticker_coord_spins["bottom"].value(),
                }
            except Exception as exc:
                self.layout_preview_status_lbl.setText(f"Không đọc được nguồn preview: {exc}")
                return

            if video is None:
                self.layout_preview_label.setPixmap(QPixmap())
                self.layout_preview_label.setText(
                    "Chưa có video\nChọn file hoặc thư mục video ở tab Nguồn"
                )
                self.layout_preview_status_lbl.setText(
                    "Preview sẽ tự cập nhật trực tiếp ngay khi chọn đủ nguồn."
                )
                return

            self.layout_preview_status_lbl.setText(
                f"Đang dựng preview Tổ hợp {idx + 1}/{total} ({video.name})..."
            )
            frame_key = (str(video.resolve()), video.stat().st_mtime_ns)

            def worker():
                try:
                    if self.layout_state["frame_key"] == frame_key:
                        frame = self.layout_state["frame"]
                    else:
                        frame = layout_preview_mod.extract_video_frame(video)
                        self.layout_state["frame_key"] = frame_key
                        self.layout_state["frame"] = frame
                    composed = layout_preview_mod.compose_preview(
                        frame, config, image_path=image, sticker_path=sticker
                    )
                    v_coord = (
                        f"L:{config['video_left']} R:{config['video_right']} "
                        f"T:{config['video_top']} B:{config['video_bottom']}"
                    )
                    s_coord = (
                        f"L:{config['sticker_left']} R:{config['sticker_right']} "
                        f"T:{config['sticker_top']} B:{config['sticker_bottom']}"
                    )
                    details = (
                        f"[{idx + 1}/{total}] {composed.width}×{composed.height} | "
                        f"Video: {video.name} ({v_coord}) | "
                        f"Ảnh: {image.name if image else '-'} | "
                        f"Sticker: {sticker.name if sticker else '-'} @ {effective_stk_pos} ({s_coord})"
                    )
                except Exception as exc:
                    self.bridge.preview_error_signal.emit(token, str(exc))
                    return
                self.bridge.preview_ready_signal.emit(token, composed, details)

            threading.Thread(target=worker, daemon=True).start()

        def _apply_layout_preview(self, token: int, pil_image, details: str):
            if token != self.layout_state["seq"]:
                return
            buf = BytesIO()
            pil_image.save(buf, format="PNG")
            qimg = QImage.fromData(buf.getvalue(), "PNG")
            pix = QPixmap.fromImage(qimg)
            self.layout_preview_label.setText("")
            self.layout_preview_label.setPixmap(pix)
            self.layout_preview_status_lbl.setText(details)

        def _apply_layout_preview_error(self, token: int, message: str):
            if token != self.layout_state["seq"]:
                return
            self.layout_preview_label.setPixmap(QPixmap())
            self.layout_preview_label.setText("Không dựng được preview")
            self.layout_preview_status_lbl.setText(message)

        # -------------------------------------------------------------------
        # Thu thập cấu hình & Chạy Batch
        # -------------------------------------------------------------------
        def collect_config(self):
            c = default_config()
            c.update({
                "videos_dir": self.videos_dir_edit.text().strip(),
                "video_file": self.video_file_edit.text().strip(),
                "images_dir": self.images_dir_edit.text().strip(),
                "stickers_dir": self.stickers_dir_edit.text().strip(),
                "pair": self.pair_combo.currentText(),
                "output_dir": self.output_dir_edit.text().strip() or "video_done",
                "mirror": self.mirror_chk.isChecked(),
                "speed_on": self.speed_on_chk.isChecked(),
                "speed": float(self.speed_spin.value()),
                "image_on": self.image_on_chk.isChecked(),
                "image_mode": self.image_mode_combo.currentText(),
                "image_opacity": float(self.image_opacity_spin.value()),
                "frame_916": self.frame_916_chk.isChecked(),
                "video_scale": float(self.video_scale_spin.value()),
                "video_position": self.video_pos_combo.currentText(),
                "video_left": float(self.video_coord_spins["left"].value()),
                "video_right": float(self.video_coord_spins["right"].value()),
                "video_top": float(self.video_coord_spins["top"].value()),
                "video_bottom": float(self.video_coord_spins["bottom"].value()),
                "sticker_on": self.sticker_on_chk.isChecked(),
                "sticker_scale": float(self.sticker_scale_spin.value()),
                "sticker_position": self.sticker_pos_combo.currentText(),
                "sticker_left": float(self.sticker_coord_spins["left"].value()),
                "sticker_right": float(self.sticker_coord_spins["right"].value()),
                "sticker_top": float(self.sticker_coord_spins["top"].value()),
                "sticker_bottom": float(self.sticker_coord_spins["bottom"].value()),
                "quality_mode": self.quality_mode_combo.currentText(),
                "quality_value": self.quality_value_edit.text().strip(),
                "encoder": self.encoder_combo.currentText().strip() or "auto",
                "gpu_profile": GPU_PROFILES.get(self.gpu_profile_combo.currentText(), "auto"),
                "preset": self.preset_edit.text().strip(),
                "threads": int(self.threads_spin.value()),
                "workers": int(self.workers_spin.value()),
                "chunk": self.chunk_chk.isChecked(),
                "chunk_seconds": int(self.chunk_seconds_spin.value()),
                "resume": self.resume_chk.isChecked(),
                "keep_chunks": self.keep_chunks_chk.isChecked(),
                "sil_batch": self.sil_batch_chk.isChecked(),
                "sil_mode": self.sil_mode_combo.currentText(),
                "sil_margin": float(self.sil_margin_spin.value()),
                "sil_threshold": float(self.sil_threshold_spin.value()),
                "sil_min_silence": float(self.sil_min_silence_spin.value()),
                "sil_min_cut": float(self.sil_min_cut_spin.value()),
                "sil_pad": float(self.sil_pad_spin.value()),
                "sil_min_keep": float(self.sil_min_keep_spin.value()),
                "sil_max_cut_ratio": float(self.sil_max_cut_ratio_spin.value()),
                "sil_max_keep": float(self.sil_max_keep_spin.value()),
                "sil_trim_ends": self.sil_trim_ends_chk.isChecked(),
                "sil_safety": self.sil_safety_chk.isChecked(),
                "dry_run": self.dry_run_chk.isChecked(),
            })
            return c

        def set_running(self, active: bool):
            self.running["flag"] = active
            self.run_btn.setEnabled(not active)
            self.btn_sil_scan.setEnabled(not active)
            self.btn_sil_cut.setEnabled(not active)
            if active:
                self.progress_bar.setValue(0)
                self.status_badge.setText("Đang xử lý...")
            else:
                self.status_badge.setText(
                    "Hoàn tất 100%." if self.progress_bar.value() >= 100 else "Sẵn sàng."
                )

        def on_run(self):
            if self.running["flag"]:
                return
            try:
                cfg_run = self.collect_config()
                out_dir = Path(cfg_run["output_dir"]).expanduser()
                out_dir.mkdir(parents=True, exist_ok=True)
                self.active_log["path"] = out_dir / (
                    f"video_tool_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                )
            except Exception as e:
                QMessageBox.critical(self, "Thiếu / sai thông tin", str(e))
                return

            if not self.bottom_log_panel.isVisible():
                self.toggle_bottom_log_panel()
            self.log_text.clear()
            self.worker_table.clear()
            self.set_running(True)
            self.log(f"[MAIN] Nhật ký chi tiết: {self.active_log['path']}")

            def worker():
                try:
                    run_pipeline(cfg_run, log=self.log, progress=self.emit_progress)
                    self.log("[MAIN] HOÀN TẤT.")
                    self.bridge.batch_done_signal.emit(str(self.active_log["path"]))
                except Exception as e:
                    self.log(f"[LỖI] {e}")
                    self.log(traceback.format_exc())
                    self.bridge.batch_error_signal.emit(str(e))
                finally:
                    self.bridge.batch_finally_signal.emit()

            threading.Thread(target=worker, daemon=True).start()

        # -------------------------------------------------------------------
        # GPU & Mặc định
        # -------------------------------------------------------------------
        def on_scan_gpu(self, use_cache=False):
            self.scan_gpu_btn.setEnabled(False)
            self.status_badge.setText("Đang quét GPU...")
            profile = GPU_PROFILES.get(self.gpu_profile_combo.currentText(), "auto")

            def worker():
                try:
                    det_fn = load_tool("gpu_detect.py", "detect_gpu")
                    det = det_fn(use_cache=use_cache, profile=profile)
                    info = (
                        f"GPU: {det['gpu']} | Encoder: {det['encoder']} "
                        f"({'phần cứng' if det['hardware'] else 'CPU'}) | "
                        f"FFmpeg: {det.get('ffmpeg_profile') or '-'} | "
                        f"Preset: {det['preset']} | Threads: {det['threads']} | "
                        f"Workers tự động: {det.get('recommended_workers', 1)} | "
                        f"CPU {det['cpu_cores']} nhân, RAM {det['ram_gb']} GB"
                    )
                    if det.get("detail"):
                        info += f"\nChi tiết: {det['detail']}"
                    self.bridge.gpu_ready_signal.emit(det, info)
                    self.log(f"[GPU] {info}")
                    self.log(f"[GPU] {det['reason']}")
                    self.log(f"[GPU] FFmpeg: {det.get('ffmpeg_path') or 'không tìm thấy'}")
                except Exception as e:
                    self.log(f"[LỖI GPU] {e}")
                    self.bridge.gpu_error_signal.emit(str(e))
                finally:
                    self.bridge.gpu_done_signal.emit()

            threading.Thread(target=worker, daemon=True).start()

        def _on_gpu_ready(self, det: dict, info: str):
            self.gpu_info_lbl.setText(info)
            self.encoder_combo.setCurrentText(det["encoder"])
            self.preset_edit.setText(det["preset"])
            self.threads_spin.setValue(int(det["threads"]))

        def _on_gpu_done(self):
            self.scan_gpu_btn.setEnabled(True)
            if not self.running["flag"]:
                self.status_badge.setText("Sẵn sàng.")

        def on_use_cpu(self):
            self.encoder_combo.setCurrentText("libx264")
            self.preset_edit.setText("medium")
            self.gpu_info_lbl.setText("Đã chọn CPU (libx264) theo yêu cầu — không dùng GPU.")
            self.log("[GPU] Đã chọn CPU (libx264) theo yêu cầu.")

        def on_defaults(self):
            self.mirror_chk.setChecked(True)
            self.speed_on_chk.setChecked(True)
            self.speed_spin.setValue(1.20)
            self.image_on_chk.setChecked(True)
            self.image_mode_combo.setCurrentText("corner")
            self.image_opacity_spin.setValue(0.85)
            self.frame_916_chk.setChecked(True)
            self.video_scale_spin.setValue(0.94)
            self.video_pos_combo.setCurrentText("center")
            self.reset_video_coords()
            self.sticker_on_chk.setChecked(True)
            self.sticker_scale_spin.setValue(0.15)
            self.sticker_pos_combo.setCurrentText("auto-corners")
            self.reset_sticker_coords()
            self.quality_mode_combo.setCurrentText("source")
            self.quality_value_edit.clear()
            self.encoder_combo.setCurrentText("auto")
            self.preset_edit.clear()
            self.threads_spin.setValue(0)
            self.gpu_profile_combo.setCurrentIndex(0)
            self.workers_spin.setValue(0)
            self.chunk_chk.setChecked(True)
            self.chunk_seconds_spin.setValue(300)
            self.resume_chk.setChecked(True)
            self.keep_chunks_chk.setChecked(False)
            self.pair_combo.setCurrentText("order")
            self.output_dir_edit.setText("video_done")
            self.sil_preset_combo.setCurrentText("Vừa")
            self.sil_mode_combo.setCurrentText("relative")
            self.sil_margin_spin.setValue(20.0)
            self.sil_threshold_spin.setValue(-40.0)
            self.sil_min_silence_spin.setValue(0.5)
            self.sil_min_cut_spin.setValue(1.0)
            self.sil_pad_spin.setValue(0.2)
            self.sil_min_keep_spin.setValue(0.8)
            self.sil_max_cut_ratio_spin.setValue(30.0)
            self.sil_max_keep_spin.setValue(5.0)
            self.sil_trim_ends_chk.setChecked(True)
            self.sil_batch_chk.setChecked(True)
            self.sil_safety_chk.setChecked(True)
            self.dry_run_chk.setChecked(False)
            self.status_badge.setText("Đã khôi phục cấu hình mặc định.")
            self.schedule_layout_preview()

        def on_help(self):
            QMessageBox.information(
                self,
                "Hướng dẫn quan trọng",
                "• Chọn nguồn ở tab 1; sang tab 2 để chỉnh bố cục và xem Preview trực tiếp.\n"
                "• Nút '◀ Trước' và 'Tiếp (Next) ▶' trong khung Preview cho phép xem trước từng tổ hợp Video + Ảnh + Sticker tiếp theo sẽ trông như thế nào.\n"
                "• Sticker mặc định để 'auto-corners': tự động đảo 4 góc luân phiên qua từng video (Video 1: top-right -> Video 2: bottom-left -> Video 3: top-left -> Video 4: bottom-right).\n"
                "• Căn chỉnh tọa độ Left / Right / Top / Bottom (px): chỉnh được cho cả Video (khung 9:16) và Sticker, cập nhật trực tiếp ngay trong khung Preview.\n"
                "• GPU: để Tự động cho cả NVIDIA cũ và mới; hai chế độ NVIDIA dùng để ép khi cần.\n"
                "• Workers = 0 để tool tự chia tài nguyên; CPU encoding tự giảm threads/worker.\n"
                "• Phanh an toàn giới hạn tổng thời lượng cắt im và bảo vệ video thu quá nhỏ.\n"
                "• Nút '▶ Chạy đồng bộ' nằm cố định trên thanh Header để bấm chạy từ bất kỳ tab nào.",
            )

        # -------------------------------------------------------------------
        # Xem toàn bộ video đã import, So sánh & Phân tích kết quả (Tab 4)
        # -------------------------------------------------------------------
        @staticmethod
        def _fmt_bytes(n: int) -> str:
            val = float(n or 0)
            for unit in ("B", "KB", "MB", "GB"):
                if val < 1024 or unit == "GB":
                    return f"{val:.1f} {unit}" if unit != "B" else f"{int(val)} B"
                val /= 1024
            return f"{val:.1f} GB"

        def _resolve_compare_output_path(self, idx: int, src_video: Path):
            """
            Tìm file video đầu ra để so sánh với `src_video`:
            1. Nếu người dùng đã bấm [📥 Import video đầu ra...] cho dòng này -> dùng file đó.
            2. Nếu chưa import tay -> tự tìm `<stem>_done.mp4` trong thư mục đầu ra.
            """
            overrides = self.media_state.get("compare_overrides") or {}
            custom = overrides.get(idx) or self.media_state.get("compare_path") or ""
            if custom and Path(custom).is_file():
                return Path(custom), True
            out_dir = Path(self.output_dir_edit.text().strip() or "video_done").expanduser()
            candidate = out_dir / f"{src_video.stem}_done.mp4"
            if candidate.is_file() and candidate.stat().st_size > 0:
                return candidate, False
            return None, False

        def refresh_media_tab(self, reset_index=False):
            """Tự động nạp toàn bộ danh sách video đã import từ tab Nguồn vào bảng có nút [▷ Xem]."""
            try:
                combos = layout_preview_mod.list_preview_combinations(
                    self.videos_dir_edit.text().strip(),
                    self.video_file_edit.text().strip(),
                    self.images_dir_edit.text().strip(),
                    self.stickers_dir_edit.text().strip(),
                    self.image_on_chk.isChecked(),
                    self.sticker_on_chk.isChecked(),
                    pair=self.pair_combo.currentText(),
                    seed=0,
                )
            except Exception:
                combos = []

            self.media_state["combos"] = combos
            total = len(combos)
            if reset_index or total == 0:
                idx = 0
                if reset_index:
                    self.media_state["compare_overrides"] = {}
                    self.media_state["compare_path"] = ""
            else:
                idx = self.media_state.get("index", 0) % total
            self.media_state["index"] = idx

            self.media_list_table.blockSignals(True)
            self.media_list_table.clear()
            stk_pos_setting = self.sticker_pos_combo.currentText()

            for i, (vid, img, stk) in enumerate(combos):
                corner = layout_preview_mod.resolve_sticker_position(stk_pos_setting, index=i)
                try:
                    st = vid.stat()
                    size_str = self._fmt_bytes(st.st_size)
                    mtime_str = datetime.fromtimestamp(st.st_mtime).strftime("%H:%M %d/%m/%Y")
                except OSError:
                    size_str = "-"
                    mtime_str = "-"

                pair_str = (
                    f"Ảnh: {img.name if img else '-'} | "
                    f"Stk: {stk.name if stk else '-'} ({corner})"
                )
                cmp_file, is_custom = self._resolve_compare_output_path(i, vid)
                if cmp_file is not None:
                    status_str = f"✔ Đã import: {cmp_file.name}" if is_custom else f"✔ Đã xuất: {cmp_file.name}"
                else:
                    status_str = "Chờ xuất (Mô phỏng)"

                item = QTreeWidgetItem([
                    str(i + 1), vid.name, size_str, mtime_str, pair_str, status_str, ""
                ])
                item.setData(0, Qt.ItemDataRole.UserRole, i)
                self.media_list_table.addTopLevelItem(item)

                btn_view = QPushButton("▷ Xem")
                btn_view.setObjectName("TableActionBtn")
                btn_view.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_view.clicked.connect(lambda _=False, row_idx=i: self.open_media_popup(row_idx))
                self.media_list_table.setItemWidget(item, 6, btn_view)

            if total > 0:
                target_item = self.media_list_table.topLevelItem(idx)
                if target_item is not None:
                    self.media_list_table.setCurrentItem(target_item)
                self.media_count_badge.setText(f"Video {idx + 1} / {total}")
            else:
                self.media_count_badge.setText("0 / 0 video")
            self.media_list_table.blockSignals(False)

            self.btn_media_prev.setEnabled(total > 1)
            self.btn_media_next.setEnabled(total > 1)

            popup = self.media_state.get("popup")
            if popup is not None and popup.isVisible():
                self._inspect_popup_video()

        def open_current_media_popup(self):
            combos = self.media_state.get("combos") or []
            if not combos:
                QMessageBox.information(
                    self,
                    "Chưa có video",
                    "Hãy chọn thư mục video hoặc 1 file video ở tab 1. Nguồn dữ liệu trước.",
                )
                return
            self.open_media_popup(self.media_state.get("index", 0))

        def open_media_popup(self, idx: int):
            """Chỉ khi bấm [▷ Xem] mới mở cửa sổ Popup hiển thị video gốc bên trái, thông tin bên phải & so sánh đầu ra."""
            combos = self.media_state.get("combos") or []
            if not (0 <= idx < len(combos)):
                return
            self._select_media_row(idx)
            popup = self.media_state.get("popup")
            if popup is None:
                popup = VideoPreviewDialog(self, idx)
                self.media_state["popup"] = popup
            else:
                popup.row_index = idx
            popup.show()
            popup.raise_()
            popup.activateWindow()
            self._inspect_popup_video()

        def _select_media_row(self, idx: int):
            combos = self.media_state.get("combos") or []
            if not (0 <= idx < len(combos)):
                return
            self.media_state["index"] = idx
            self.layout_state["combo_index"] = idx
            self.media_list_table.blockSignals(True)
            item = self.media_list_table.topLevelItem(idx)
            if item is not None:
                self.media_list_table.setCurrentItem(item)
            self.media_list_table.blockSignals(False)
            self.media_count_badge.setText(f"Video {idx + 1} / {len(combos)}")

        def _on_media_table_item_changed(self, current, _previous):
            if current is None:
                return
            idx = current.data(0, Qt.ItemDataRole.UserRole)
            if idx is None:
                return
            idx = int(idx)
            if idx != self.media_state.get("index", -1):
                self.media_state["index"] = idx
                self.layout_state["combo_index"] = idx
                total = len(self.media_state.get("combos") or [])
                if total > 0:
                    self.media_count_badge.setText(f"Video {idx + 1} / {total}")
                popup = self.media_state.get("popup")
                if popup is not None and popup.isVisible():
                    self._inspect_popup_video()

        def prev_media_video(self, open_popup=False):
            combos = self.media_state.get("combos") or []
            if len(combos) > 1:
                idx = (self.media_state.get("index", 0) - 1) % len(combos)
                if open_popup:
                    self.open_media_popup(idx)
                else:
                    self._select_media_row(idx)
                    popup = self.media_state.get("popup")
                    if popup is not None and popup.isVisible():
                        self._inspect_popup_video()

        def next_media_video(self, open_popup=False):
            combos = self.media_state.get("combos") or []
            if len(combos) > 1:
                idx = (self.media_state.get("index", 0) + 1) % len(combos)
                if open_popup:
                    self.open_media_popup(idx)
                else:
                    self._select_media_row(idx)
                    popup = self.media_state.get("popup")
                    if popup is not None and popup.isVisible():
                        self._inspect_popup_video()

        def on_import_compare_video(self, parent_widget=None):
            """Nút [📥 Import video đầu ra...] trên Popup để chọn file thành phẩm bất kỳ lên so sánh với video gốc."""
            f, _ = QFileDialog.getOpenFileName(
                parent_widget or self,
                "Chọn video đầu ra để so sánh với video gốc đang xem",
                self.output_dir_edit.text().strip() or "",
                "Video (*.mp4 *.mov *.mkv *.avi *.webm)",
            )
            if not f:
                return
            idx = self.media_state.get("index", 0)
            overrides = self.media_state.setdefault("compare_overrides", {})
            overrides[idx] = f
            self.media_state["compare_path"] = f
            self.refresh_media_tab(reset_index=False)

        def on_reset_compare_video(self):
            """Quay về chế độ tự động tìm file <tên>_done.mp4 hoặc dựng mô phỏng đầu ra."""
            idx = self.media_state.get("index", 0)
            overrides = self.media_state.get("compare_overrides") or {}
            overrides.pop(idx, None)
            self.media_state["compare_path"] = ""
            self.refresh_media_tab(reset_index=False)

        def _inspect_popup_video(self):
            popup = self.media_state.get("popup")
            combos = self.media_state.get("combos") or []
            if popup is None or not combos:
                return

            idx = self.media_state.get("index", 0) % len(combos)
            video, image, sticker = combos[idx]
            cfg = self.collect_config()
            cfg["combo_index"] = idx

            cmp_file, is_custom_cmp = self._resolve_compare_output_path(idx, video)

            self.media_state["seq"] += 1
            token = self.media_state["seq"]
            popup.popup_title_lbl.setText(
                f"Xem trước #{idx + 1}/{len(combos)}: {video.name}"
            )
            popup.src_name_lbl.setText(f"Gốc: {video.name}")
            popup.src_note_lbl.setText(f"Đang nạp khung hình & thông số gốc của {video.name}...")
            popup.btn_popup_prev.setEnabled(len(combos) > 1)
            popup.btn_popup_next.setEnabled(len(combos) > 1)
            frame_key = (str(video.resolve()), video.stat().st_mtime_ns)

            def worker():
                try:
                    # 1. Lấy frame GỐC của video nguồn (chưa ghép nền/sticker)
                    frame_cache = self.media_state["frame_cache"]
                    if frame_key in frame_cache:
                        src_frame = frame_cache[frame_key]
                    else:
                        src_frame = layout_preview_mod.extract_video_frame(video)
                        frame_cache[frame_key] = src_frame

                    raw_preview = src_frame.copy()
                    raw_preview.thumbnail((212, 354))

                    # 2. Đọc ffprobe thông số VIDEO GỐC
                    get_fn = load_tool("07_media_info.py", "get_media_info")
                    fmt_fn = load_tool("07_media_info.py", "format_media_info")
                    sum_fn = load_tool("07_media_info.py", "summary_line")
                    cmp_fn = load_tool("07_media_info.py", "analyze_comparison")

                    info_cache = self.media_state["info_cache"]
                    if frame_key in info_cache:
                        src_info = info_cache[frame_key]
                    else:
                        src_info = get_fn(video)
                        info_cache[frame_key] = src_info

                    src_info_txt = fmt_fn(src_info) + "\nTóm tắt     : " + sum_fn(src_info)
                    src_note = (
                        f"Xem để kiểm tra video ổn không trước khi chạy. Đây là video GỐC: {sum_fn(src_info)} (chưa ghép nền/sticker)."
                    )

                    # 3. Xử lý VIDEO ĐẦU RA (file đã Import / file đã xuất / hoặc mô phỏng cấu hình)
                    done_info = None
                    out_preview = None
                    if cmp_file is not None and cmp_file.is_file():
                        cmp_key = (str(cmp_file.resolve()), cmp_file.stat().st_mtime_ns)
                        if cmp_key in info_cache:
                            done_info = info_cache[cmp_key]
                        else:
                            done_info = get_fn(cmp_file)
                            info_cache[cmp_key] = done_info

                        if cmp_key in frame_cache:
                            out_frame = frame_cache[cmp_key]
                        else:
                            out_frame = layout_preview_mod.extract_video_frame(cmp_file)
                            frame_cache[cmp_key] = out_frame
                        out_preview = out_frame.copy()
                        out_preview.thumbnail((212, 354))
                        out_info_txt = fmt_fn(done_info) + "\nTóm tắt     : " + sum_fn(done_info)
                        tag = "đã Import thủ công" if is_custom_cmp else "đã xuất trong thư mục ra"
                        out_note = f"Đang so sánh với file thực tế ({tag}): {cmp_file.name} • {sum_fn(done_info)}"
                    else:
                        out_preview = layout_preview_mod.compose_preview(
                            src_frame, cfg, image_path=image, sticker_path=sticker
                        )
                        out_preview = out_preview.copy()
                        out_preview.thumbnail((212, 354))

                    analysis = cmp_fn(
                        src_info, cfg, index=idx,
                        img_path=image, stk_path=sticker, done_info=done_info,
                    )

                    if done_info is None:
                        out_lines = [
                            "========== ĐẦU RA DỰ KIẾN (MÔ PHỎNG) ==========",
                            "(Chưa import file đầu ra thực tế — bấm [📥 Import video đầu ra...] ở trên để nạp file thật)",
                            f"Khung xuất : {analysis['out_width']}×{analysis['out_height']}",
                            f"Thời lượng : ~{analysis['out_duration']:.1f} giây (Speed {cfg['speed']:.2f}x)",
                            f"Mirror     : {'BẬT (lật ngang)' if cfg['mirror'] else 'TẮT'}",
                            f"Ảnh ghép   : {image.name if (cfg['image_on'] and image) else 'Không có'}",
                            f"Sticker    : {sticker.name if (cfg['sticker_on'] and sticker) else 'Không có'} @ {analysis['sticker_corner']}",
                            f"Tọa độ Vid : L={int(cfg['video_left'])} R={int(cfg['video_right'])} T={int(cfg['video_top'])} B={int(cfg['video_bottom'])} px",
                            f"Tọa độ Stk : L={int(cfg['sticker_left'])} R={int(cfg['sticker_right'])} T={int(cfg['sticker_top'])} B={int(cfg['sticker_bottom'])} px",
                            "===============================================",
                        ]
                        out_info_txt = "\n".join(out_lines)
                        out_note = (
                            f"Mô phỏng đầu ra: {analysis['out_width']}×{analysis['out_height']} • "
                            f"~{analysis['out_duration']:.1f}s • Sticker @ {analysis['sticker_corner']}. "
                            f"Bấm [📥 Import video đầu ra...] để chọn file thành phẩm lên so sánh."
                        )
                except Exception as exc:
                    self.bridge.popup_inspect_error_signal.emit(token, str(exc))
                    return
                self.bridge.popup_inspect_ready_signal.emit(
                    token, raw_preview, out_preview, src_note, out_note,
                    analysis, src_info_txt, out_info_txt
                )

            threading.Thread(target=worker, daemon=True).start()

        @staticmethod
        def _pil_to_qpixmap(pil_img):
            buf = BytesIO()
            pil_img.save(buf, format="PNG")
            qimg = QImage.fromData(buf.getvalue(), "PNG")
            return QPixmap.fromImage(qimg)

        def _apply_popup_inspect(
            self, token: int, raw_preview, out_preview,
            src_note: str, out_note: str, analysis: dict,
            src_info_txt: str, out_info_txt: str,
        ):
            if token != self.media_state["seq"]:
                return
            popup = self.media_state.get("popup")
            if popup is None:
                return
            if raw_preview is not None:
                popup.src_canvas.setText("")
                popup.src_canvas.setPixmap(self._pil_to_qpixmap(raw_preview))
            if out_preview is not None:
                popup.out_canvas.setText("")
                popup.out_canvas.setPixmap(self._pil_to_qpixmap(out_preview))

            popup.src_note_lbl.setText(src_note)
            popup.out_note_lbl.setText(out_note)
            popup.src_info_edit.setPlainText(src_info_txt)
            popup.out_info_edit.setPlainText(out_info_txt)

            popup.cmp_table.clear()
            for metric, src_val, out_val, note in analysis.get("rows", []):
                item = QTreeWidgetItem([str(metric), str(src_val), str(out_val), str(note)])
                popup.cmp_table.addTopLevelItem(item)

            popup.verdict_edit.setPlainText("\n".join(analysis.get("conclusions", [])))

        def _apply_popup_inspect_error(self, token: int, message: str):
            if token != self.media_state["seq"]:
                return
            popup = self.media_state.get("popup")
            if popup is None:
                return
            popup.src_canvas.setPixmap(QPixmap())
            popup.src_canvas.setText("Không đọc được video")
            popup.src_note_lbl.setText(message)

        def on_preview_play(self):
            combos = self.media_state.get("combos") or []
            if not combos:
                QMessageBox.warning(
                    self, "Chưa có video nguồn",
                    "Hãy chọn thư mục video hoặc 1 file video ở tab 1. Nguồn dữ liệu trước."
                )
                return
            idx = self.media_state.get("index", 0) % len(combos)
            video_path = str(combos[idx][0])
            try:
                play_fn = load_tool("08_preview.py", "play_external")
                self.preview["proc"] = play_fn(video_path, log=self.log)
            except Exception as e:
                QMessageBox.critical(self, "Không mở được video", str(e))

        def on_preview_play_done(self):
            combos = self.media_state.get("combos") or []
            if not combos:
                QMessageBox.warning(
                    self, "Chưa có video nguồn",
                    "Hãy chọn thư mục video hoặc 1 file video ở tab 1. Nguồn dữ liệu trước."
                )
                return
            idx = self.media_state.get("index", 0) % len(combos)
            video = combos[idx][0]
            cmp_file, _ = self._resolve_compare_output_path(idx, video)
            if cmp_file is None or not cmp_file.is_file():
                QMessageBox.information(
                    self, "Chưa có video đầu ra",
                    "Chưa có file video đầu ra để phát.\n"
                    "Bạn có thể bấm nút [📥 Import video đầu ra...] để chọn file hoặc bấm '▶ Chạy đồng bộ' để render trước."
                )
                return
            try:
                play_fn = load_tool("08_preview.py", "play_external")
                self.preview["proc"] = play_fn(str(cmp_file), log=self.log)
            except Exception as e:
                QMessageBox.critical(self, "Không mở được video đầu ra", str(e))

        def on_preview_stop(self):
            if self.preview.get("player") is not None:
                self.preview["player"].stop()
            try:
                load_tool("08_preview.py", "stop_external")(self.preview.get("proc"))
            except Exception:
                pass
            self.preview["proc"] = None

        # -------------------------------------------------------------------
        # Quét & Cắt khoảng im (Tab 5)
        # -------------------------------------------------------------------
        def on_sil_preset(self, text: str):
            p = SIL_PRESETS.get(text)
            if p:
                self.sil_min_cut_spin.setValue(p["sil_min_cut"])
                self.sil_pad_spin.setValue(p["sil_pad"])
                self.sil_max_keep_spin.setValue(p["sil_max_keep"])
                self.sil_min_keep_spin.setValue(p["sil_min_keep"])

        def on_pick_silence(self):
            f, _ = QFileDialog.getOpenFileName(
                self, "Chọn video KOC để cắt khoảng lặng", "",
                "Video (*.mp4 *.mov *.mkv *.avi *.webm)"
            )
            if f:
                self.sil_path_edit.setText(f)

        def _sil_params(self):
            ratio = float(self.sil_max_cut_ratio_spin.value())
            ratio = ratio / 100.0 if ratio > 1 else ratio
            safety = self.sil_safety_chk.isChecked()
            return dict(
                mode=self.sil_mode_combo.currentText(),
                margin_db=float(self.sil_margin_spin.value()),
                absolute_db=float(self.sil_threshold_spin.value()),
                min_silence=float(self.sil_min_silence_spin.value()),
                min_cut=float(self.sil_min_cut_spin.value()),
                pad=float(self.sil_pad_spin.value()),
                min_keep=float(self.sil_min_keep_spin.value()),
                max_cut_ratio=(ratio if safety else 0.0),
                max_keep_silence=float(self.sil_max_keep_spin.value()),
                trim_ends=self.sil_trim_ends_chk.isChecked(),
                min_peak_db=(-40.0 if safety else None),
            )

        def on_silence_scan(self):
            p = self.sil_path_edit.text().strip()
            if not p:
                QMessageBox.warning(
                    self, "Chưa chọn video", "Chọn video trong tab Cắt khoảng im trước."
                )
                return
            if self.running["flag"]:
                QMessageBox.warning(
                    self, "Đang chạy", "Đang xử lý tác vụ khác, chờ xong đã."
                )
                return
            try:
                params = self._sil_params()
            except ValueError as exc:
                QMessageBox.critical(self, "Số nhập sai", str(exc))
                return

            self.set_running(True)
            self.status_badge.setText("Đang quét âm thanh & căn mốc theo frame thật...")
            self.progress_bar.setValue(10)

            def worker():
                try:
                    scan_fn = load_tool("09_silence.py", "scan_silences")
                    fmt_fn = load_tool("09_silence.py", "format_scan")
                    result = scan_fn(p, **params)
                    report = fmt_fn(result)
                    self.bridge.silence_scan_ready_signal.emit(p, result, report)
                except Exception as exc:
                    self.bridge.silence_scan_error_signal.emit(p, str(exc))
                finally:
                    self.bridge.silence_scan_finally_signal.emit()

            threading.Thread(target=worker, daemon=True).start()

        def _on_silence_scan_ready(self, p: str, result: dict, report: str):
            self.sil_text.setPlainText(report)
            self.progress_bar.setValue(100)
            self.log(
                f"[IM] {Path(p).name} — phát hiện {result['n_detected']} khoảng im, "
                f"sẽ cắt {result['n_cut']} đoạn đã căn frame "
                f"({result['total_cut']:.3f}s), còn ~{result['est_duration']:.3f}s"
            )

        def _on_silence_scan_error(self, p: str, msg: str):
            self.log(f"[LỖI IM] Không quét được {Path(p).name}: {msg}")
            QMessageBox.critical(self, "Không quét được", msg)

        def on_silence_cut(self):
            p = self.sil_path_edit.text().strip()
            if not p:
                QMessageBox.warning(
                    self, "Chưa chọn video", "Chọn video trong tab Cắt khoảng im trước."
                )
                return
            if self.running["flag"]:
                QMessageBox.warning(
                    self, "Đang chạy", "Đang xử lý video khác, chờ xong đã."
                )
                return
            try:
                params = self._sil_params()
            except ValueError as e:
                QMessageBox.critical(self, "Số nhập sai", str(e))
                return

            self.set_running(True)
            self.status_badge.setText("Đang cắt khoảng lặng...")
            enc = self.encoder_combo.currentText().strip() or "auto"
            qmode = self.quality_mode_combo.currentText()
            qval = self.quality_value_edit.text().strip()
            preset = self.preset_edit.text().strip() or None
            threads = int(self.threads_spin.value()) or None

            def work():
                try:
                    cut_fn = load_tool("09_silence.py", "remove_silence")
                    out = cut_fn(
                        Path(p),
                        encoder=enc,
                        quality_mode=qmode,
                        quality_value=qval,
                        preset=preset,
                        threads=threads,
                        log=self.log,
                        **params,
                    )
                    self.bridge.silence_cut_done_signal.emit(str(out))
                except Exception as e:
                    self.log(f"[LỖI] Cắt khoảng lặng: {e}")
                    self.bridge.silence_cut_error_signal.emit(str(e))
                finally:
                    self.bridge.silence_cut_finally_signal.emit()

            threading.Thread(target=work, daemon=True).start()

        def _on_silence_cut_done(self, out_path: str):
            self.progress_bar.setValue(100)
            QMessageBox.information(
                self, "Xong", f"Đã cắt khoảng lặng.\nFile ra: {out_path}"
            )

        def closeEvent(self, event):
            self.on_preview_stop()
            if self.preview.get("player") is not None:
                try:
                    self.preview["player"].release()
                except Exception:
                    pass
            super().closeEvent(event)

    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLESHEET)
    win = MainWindow()
    win.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    if "--cli" in sys.argv:
        raise SystemExit(cli_main())
    gui_main()
