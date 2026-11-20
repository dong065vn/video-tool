#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
07_concat.py — CHỨC NĂNG RIÊNG 4: Ghép nối thành file dài
=========================================================
CHỈ ghép, không re-encode / crop / flip / overlay / pitch từng đoạn.
Dùng concat demuxer + -c copy nên rất nhanh.

- Xáo trộn thứ tự, không để 2 đoạn giống nhau kề nhau
- Lặp playlist cho tới đủ --target-hours
- Cảnh báo nếu đoạn nào < 15 phút

⚠️ Yêu cầu: các file đầu vào phải CÙNG codec / độ phân giải / FPS.
Nếu khác nhau, hãy chạy 01_reencode.py cho từng file trước — tự chọn,
tool này không tự làm thay.

Chạy độc lập:
    python 07_concat.py -i a.mp4 b.mp4 c.mp4 -o live_2h30.mp4 --target-hours 2.5
    python 07_concat.py -i a.mp4 b.mp4 -o live.mp4 --target-hours 0.01 --no-shuffle
"""
import argparse
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import check_ffmpeg, get_info, print_info, run


def concat_long(inputs, output_path: Path,
                target_hours=2.5, shuffle=True, dry_run=False) -> Path:
    """Chỉ ghép. Trả về đường dẫn output."""
    check_ffmpeg()
    inputs = [Path(p) for p in inputs]
    for p in inputs:
        if not p.exists():
            raise FileNotFoundError(f"Không thấy file input: {p}")
        print_info(p)

    target_sec = target_hours * 3600
    infos = {p: get_info(p) for p in inputs}
    for p, inf in infos.items():
        if 0 < inf["duration"] < 900:
            print(f"[LƯU Ý] {p.name} chỉ dài {inf['duration']/60:.1f} phút (< 15 phút).")

    total_one_round = sum(inf["duration"] for inf in infos.values())
    if total_one_round <= 0:
        raise RuntimeError("Không tính được tổng thời lượng các đoạn.")
    print(f"[INFO] 1 vòng playlist: {total_one_round/60:.1f} phút, "
          f"cần {target_sec/60:.1f} phút")

    playlist = []
    acc = 0.0
    last = None
    while acc < target_sec:
        order = inputs[:]
        if shuffle:
            random.shuffle(order)
        if last is not None and order and order[0] == last:
            order.append(order.pop(0))
        for seg in order:
            if acc >= target_sec:
                break
            playlist.append(seg)
            acc += infos[seg]["duration"]
            last = seg
    print(f"[INFO] Playlist: {len(playlist)} đoạn, tổng ~{acc/3600:.2f} giờ")

    # Ghi concat list vào file tạm (chỉ là file text, không phải xử lý video)
    tmpdir = Path(tempfile.mkdtemp(prefix="concat_"))
    list_file = tmpdir / "concat.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for seg in playlist:
            safe = str(seg.resolve()).replace("'", "'\\''")
            f.write(f"file '{safe}'\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
           "-i", str(list_file),
           "-c", "copy",
           "-map_metadata", "-1",
           "-movflags", "+faststart",
           str(output_path)]
    run(cmd, dry_run=dry_run)
    if not dry_run:
        print_info(output_path)
        print(f"[XONG] Ghép dài: {output_path} — {get_info(output_path)['duration']/3600:.2f} giờ")
    return output_path


def main():
    p = argparse.ArgumentParser(description="4. Ghép dài riêng lẻ (chỉ concat, -c copy)")
    p.add_argument("-i", "--inputs", nargs="+", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--target-hours", type=float, default=2.5)
    p.add_argument("--shuffle", action="store_true", default=True)
    p.add_argument("--no-shuffle", dest="shuffle", action="store_false")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    concat_long(a.inputs, Path(a.output), a.target_hours, a.shuffle, a.dry_run)


if __name__ == "__main__":
    main()
