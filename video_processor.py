#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
video_processor.py — Bộ điều phối v2, MỖI LỆNH CHỈ GỌI 1 CHỨC NĂNG RIÊNG
=======================================================================
Không còn convert FLV (file 01_reencode.py cũ đã chuyển vào legacy/).
Mỗi subcommand dưới đây chỉ nạp và chạy đúng 1 file riêng trong cùng thư mục.
Muốn chạy chức năng nào thì gọi đúng lệnh đó — hoặc chạy trực tiếp file đó.

    python video_processor.py gpu
    python video_processor.py mirror  -i in.mp4 -o out.mp4
    python video_processor.py speed   -i in.mp4 -o out.mp4 --speed 1.2
    python video_processor.py image   -i in.mp4 -o out.mp4 --image anh.jpg
    python video_processor.py sticker -i in.mp4 -o out.mp4 --sticker st.png
    python video_processor.py batch   --videos ./videos --images ./anh --stickers ./sticker -o ./out/
    python video_processor.py chunk   --video video_dai.mp4 -o done.mp4 --images ./anh --stickers ./sticker
    python video_processor.py info    -i video.mp4
    python video_processor.py play    -i video.mp4
    python video_processor.py play    --check
    python video_processor.py silence -i video.mp4 --scan
    python video_processor.py silence -i video.mp4 -o gon.mp4 --min-cut 2.0

Chạy trực tiếp cũng được, kết quả như nhau:
    python gpu_detect.py
    python 01_mirror.py -i in.mp4 -o out.mp4
    python 02_speed.py -i in.mp4 -o out.mp4 --speed 1.2
    python 03_image_overlay.py -i in.mp4 -o out.mp4 --image anh.jpg
    python 04_sticker.py -i in.mp4 -o out.mp4 --sticker st.png
    python 05_batch.py --videos ./videos --images ./anh --stickers ./sticker -o ./out/
    python 06_chunk.py --video video_dai.mp4 -o done.mp4 --images ./anh --stickers ./sticker
"""
import argparse
import importlib.util
import sys
from pathlib import Path

BASE = Path(__file__).parent


def load_tool(filename: str, func_name: str):
    """Nạp đúng 1 file tool theo đường dẫn (tên file bắt đầu bằng số nên
    không import kiểu `import 01_...` được, phải dùng importlib)."""
    path = BASE / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return getattr(mod, func_name)


def _enc_args(p):
    p.add_argument("--encoder", default="auto")
    p.add_argument("--quality-mode", default="source",
                   choices=["source", "bitrate", "crf"])
    p.add_argument("--quality-value", default="")
    p.add_argument("--preset", default=None)
    p.add_argument("--threads", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")


def main():
    parser = argparse.ArgumentParser(
        description="Mỗi lệnh = 1 chức năng riêng, không chạy theo quy trình",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    # 0. GPU detect — chỉ file gpu_detect.py
    p = sub.add_parser("gpu", help="0. Quét GPU và chọn encoder")
    p.add_argument("--json", action="store_true")
    p.add_argument("--probe", action="store_true")
    p.add_argument("--profile", default="auto",
                   choices=["auto", "nvidia_legacy", "nvidia_modern"])

    # 1. Mirror — chỉ file 01_mirror.py
    p = sub.add_parser("mirror", help="1. Mirror ngang riêng")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", required=True)
    _enc_args(p)

    # 2. Speed — chỉ file 02_speed.py
    p = sub.add_parser("speed", help="2. Tăng tốc độ riêng")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--speed", type=float, default=1.2)
    _enc_args(p)

    # 3. Image overlay — chỉ file 03_image_overlay.py
    p = sub.add_parser("image", help="3. Ghép 1 ảnh vào video riêng")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--image", required=True)
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
    _enc_args(p)

    # 4. Sticker — chỉ file 04_sticker.py
    p = sub.add_parser("sticker", help="4. Ghép 1 sticker vào video riêng")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--sticker", required=True)
    p.add_argument("--scale", type=float, default=0.15)
    p.add_argument("--position", default="auto-corners",
                   choices=["auto-corners", "bottom-right", "top-right", "bottom-left", "top-left",
                            "center", "top", "bottom", "left", "right"])
    p.add_argument("--sticker-left", "--left", dest="sticker_left", type=float, default=0)
    p.add_argument("--sticker-right", "--right", dest="sticker_right", type=float, default=0)
    p.add_argument("--sticker-top", "--top", dest="sticker_top", type=float, default=0)
    p.add_argument("--sticker-bottom", "--bottom", dest="sticker_bottom", type=float, default=0)
    _enc_args(p)

    # 5. Batch — chỉ file 05_batch.py
    p = sub.add_parser("batch", help="5. Xử lý hàng loạt theo folder")
    p.add_argument("--videos", default="")
    p.add_argument("--video", default="")
    p.add_argument("--images", default="")
    p.add_argument("--stickers", default="")
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
    p.add_argument("--frame-916", dest="frame_916", action="store_true")
    p.add_argument("--video-scale", type=float, default=0.94)
    p.add_argument("--video-position", default="center",
                   choices=["center", "top", "bottom", "left", "right",
                            "top-left", "top-right", "bottom-left", "bottom-right"])
    p.add_argument("--video-left", type=float, default=0)
    p.add_argument("--video-right", type=float, default=0)
    p.add_argument("--video-top", type=float, default=0)
    p.add_argument("--video-bottom", type=float, default=0)
    _enc_args(p)
    p.add_argument("--workers", type=int, default=0)
    p.add_argument("--gpu-profile", default="auto",
                   choices=["auto", "nvidia_legacy", "nvidia_modern"])
    p.add_argument("--chunk", dest="chunk", action="store_true",
                   help="Chia video dài thành từng đoạn rồi ghép lại (mặc định BẬT)")
    p.add_argument("--no-chunk", dest="chunk", action="store_false")
    p.add_argument("--chunk-seconds", type=int, default=300)
    p.add_argument("--resume", dest="resume", action="store_true")
    p.add_argument("--no-resume", dest="resume", action="store_false")
    p.add_argument("--keep-chunks", action="store_true")
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
    p.add_argument("--sil-max-cut-ratio", type=float, default=30.0)
    p.set_defaults(mirror=True, image_on=True, sticker_on=True, frame_916=True,
                   chunk=True, resume=True, silence_on=False, sil_trim_ends=True)

    # 6. Chunk — chỉ file 06_chunk.py (1 video dài, chia đoạn rồi ghép lại)
    p = sub.add_parser("chunk", help="6. Xử lý 1 video dài theo từng đoạn rồi ghép lại")
    p.add_argument("--video", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--images", default="")
    p.add_argument("--stickers", default="")
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
    _enc_args(p)
    p.add_argument("--chunk-seconds", type=int, default=300)
    p.add_argument("--resume", dest="resume", action="store_true")
    p.add_argument("--no-resume", dest="resume", action="store_false")
    p.add_argument("--keep-chunks", action="store_true")
    p.set_defaults(mirror=True, image_on=True, sticker_on=True, frame_916=True,
                   resume=True)

    # 7. Info — chỉ file 07_media_info.py (xem thông số chi tiết, ffprobe)
    p = sub.add_parser("info", help="7. Xem thông số chi tiết của 1 video (ffprobe)")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("--json", action="store_true")

    # 8. Play — chỉ file 08_preview.py (xem trước: VLC / ffplay / mặc định)
    p = sub.add_parser("play", help="8. Xem trước video (VLC nhúng / ffplay / mặc định)")
    p.add_argument("-i", "--input", default="")
    p.add_argument("--check", action="store_true",
                   help="Chỉ kiểm tra máy xem được bằng cách nào, không mở video")

    # 9. Silence — chỉ file 09_silence.py (quét khoảng lặng & cắt bỏ, video KOC)
    p = sub.add_parser("silence", help="9. Quét khoảng lặng trong video KOC rồi cắt bỏ")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", default="",
                   help="File ra (mặc định: <tên>_catlang.mp4 cùng thư mục)")
    p.add_argument("--mode", default="relative", choices=["relative", "absolute"],
                   help="relative: ngưỡng = độ lớn TB - margin (mặc định); "
                        "absolute: ngưỡng dB cố định")
    p.add_argument("--margin", type=float, default=20.0)
    p.add_argument("--threshold-db", type=float, default=-40.0)
    p.add_argument("--min-silence", type=float, default=0.5)
    p.add_argument("--min-cut", type=float, default=1.0)
    p.add_argument("--pad", type=float, default=0.2)
    p.add_argument("--min-keep", type=float, default=0.8,
                   help="Chống đảo: đoạn nói ngắn hơn mức này kẹp giữa 2 khoảng im "
                        "thì giữ lại khoảng im ngắn hơn bên cạnh (0 = tắt)")
    p.add_argument("--max-cut-ratio", type=float, default=30.0,
                   help="Trần cắt tổng, tính theo %% (mặc định 30): vượt trần thì tự "
                        "tăng --min-cut lên, vẫn vượt thì không cắt gì (0 = tắt)")
    p.add_argument("--max-keep-silence", type=float, default=5.0,
                   help="Mỗi khoảng im sau khi cắt còn tối đa bao nhiêu giây (0 = cắt hết)")
    p.add_argument("--no-trim-ends", dest="trim_ends", action="store_false",
                   help="Tắt cắt mạnh khoảng im đầu/cuối video")
    p.add_argument("--min-peak-db", type=float, default=-40.0)
    p.set_defaults(trim_ends=True)
    p.add_argument("--scan", action="store_true",
                   help="Chỉ quét + in báo cáo, không cắt")
    _enc_args(p)

    args = parser.parse_args()

    # Mỗi nhánh chỉ gọi đúng 1 hàm của 1 file, không gọi thêm hàm nào khác.
    if args.command == "gpu":
        fn = load_tool("gpu_detect.py", "detect_gpu")
        det = fn(use_cache=not args.probe, profile=args.profile)
        if args.json:
            import json
            print(json.dumps(det, ensure_ascii=False, indent=2))
        else:
            from gpu_detect import report
            print(report(det))
    elif args.command == "mirror":
        fn = load_tool("01_mirror.py", "mirror")
        fn(Path(args.input), Path(args.output), args.encoder, args.quality_mode,
           args.quality_value, args.preset, args.threads, args.dry_run)
    elif args.command == "speed":
        fn = load_tool("02_speed.py", "speed_up")
        fn(Path(args.input), Path(args.output), args.speed, args.encoder,
           args.quality_mode, args.quality_value, args.preset, args.threads, args.dry_run)
    elif args.command == "image":
        fn = load_tool("03_image_overlay.py", "image_overlay")
        fn(Path(args.input), Path(args.output), Path(args.image), args.mode,
           args.opacity, args.frame_916, args.video_scale, args.video_position,
           args.video_left, args.video_right, args.video_top, args.video_bottom,
           args.encoder, args.quality_mode, args.quality_value,
           args.preset, args.threads, args.dry_run)
    elif args.command == "sticker":
        fn = load_tool("04_sticker.py", "sticker_overlay")
        fn(Path(args.input), Path(args.output), Path(args.sticker), args.scale,
           args.position, args.sticker_left, args.sticker_right,
           args.sticker_top, args.sticker_bottom,
           args.encoder, args.quality_mode, args.quality_value,
           args.preset, args.threads, args.dry_run)
    elif args.command == "batch":
        ratio = args.sil_max_cut_ratio
        ratio = ratio / 100.0 if ratio > 1 else ratio
        fn = load_tool("05_batch.py", "batch")
        fn(args.videos or None, args.video or None, args.images or None,
           args.stickers or None, args.output_dir, args.pair, args.seed,
           args.mirror, args.speed, args.image_on, args.image_mode,
           args.image_opacity, args.sticker_on, args.sticker_scale,
           args.sticker_position,
           args.sticker_left, args.sticker_right,
           args.sticker_top, args.sticker_bottom,
           args.frame_916, args.video_scale,
           args.video_position,
           args.video_left, args.video_right,
           args.video_top, args.video_bottom,
           args.encoder, args.quality_mode,
           args.quality_value, args.preset, args.threads, args.dry_run,
           chunk=args.chunk, chunk_seconds=args.chunk_seconds,
           resume=args.resume, keep_chunks=args.keep_chunks,
           silence_on=args.silence_on, silence_mode=args.sil_mode,
           silence_margin=args.sil_margin,
           silence_absolute=args.sil_threshold_db,
           silence_min_silence=args.sil_min_silence,
           silence_min_cut=args.sil_min_cut, silence_pad=args.sil_pad,
           silence_min_keep=args.sil_min_keep,
           silence_max_keep=args.sil_max_keep,
           silence_trim_ends=args.sil_trim_ends,
           silence_safety=args.sil_safety, silence_max_cut_ratio=ratio,
           workers=args.workers, gpu_profile=args.gpu_profile)
    elif args.command == "chunk":
        from common import IMAGE_EXTS, STICKER_EXTS, list_files
        img = None
        if args.images:
            imgs = list_files(args.images, IMAGE_EXTS)
            img = imgs[0] if imgs else None
        stk = None
        if args.stickers:
            stks = list_files(args.stickers, STICKER_EXTS)
            stk = stks[0] if stks else None
        fn = load_tool("06_chunk.py", "process_video_chunked")
        fn(Path(args.video), img, stk, Path(args.output),
           mirror=args.mirror, speed=args.speed,
           image_on=args.image_on, image_mode=args.image_mode,
           image_opacity=args.image_opacity,
           sticker_on=args.sticker_on, sticker_scale=args.sticker_scale,
           sticker_position=args.sticker_position,
           sticker_left=args.sticker_left, sticker_right=args.sticker_right,
           sticker_top=args.sticker_top, sticker_bottom=args.sticker_bottom,
           frame_916=args.frame_916, video_scale=args.video_scale,
           video_position=args.video_position,
           video_left=args.video_left, video_right=args.video_right,
           video_top=args.video_top, video_bottom=args.video_bottom,
           enc=args.encoder, quality_mode=args.quality_mode,
           quality_value=args.quality_value,
           preset=args.preset, threads=args.threads,
           chunk_seconds=args.chunk_seconds, resume=args.resume,
           keep_chunks=args.keep_chunks, dry_run=args.dry_run)
    elif args.command == "info":
        get_fn = load_tool("07_media_info.py", "get_media_info")
        info = get_fn(args.input)
        if args.json:
            import json
            print(json.dumps(info, ensure_ascii=False, indent=2))
        else:
            fmt_fn = load_tool("07_media_info.py", "format_media_info")
            sum_fn = load_tool("07_media_info.py", "summary_line")
            print(fmt_fn(info))
            print("Tóm tắt     : " + sum_fn(info))
    elif args.command == "play":
        fn = load_tool("08_preview.py", "main")
        if args.check or not args.input:
            fn(["--check"])
        else:
            fn([args.input])
    elif args.command == "silence":
        ratio = args.max_cut_ratio
        ratio = ratio / 100.0 if ratio > 1 else ratio
        kw = dict(mode=args.mode, margin_db=args.margin,
                  absolute_db=args.threshold_db, min_silence=args.min_silence,
                  min_cut=args.min_cut, pad=args.pad, min_keep=args.min_keep,
                  max_cut_ratio=ratio, max_keep_silence=args.max_keep_silence,
                  trim_ends=args.trim_ends, min_peak_db=args.min_peak_db)
        if args.scan:
            scan_fn = load_tool("09_silence.py", "scan_silences")
            fmt_fn = load_tool("09_silence.py", "format_scan")
            s = scan_fn(args.input, **kw)
            print(fmt_fn(s))
        else:
            fn = load_tool("09_silence.py", "remove_silence")
            fn(Path(args.input), Path(args.output) if args.output else None,
               encoder=args.encoder,
               quality_mode=args.quality_mode, quality_value=args.quality_value,
               preset=args.preset, threads=args.threads, dry_run=args.dry_run,
               **kw)


if __name__ == "__main__":
    main()
