#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
08_preview.py — XEM TRƯỚC VIDEO (VLC nhúng, rớt về ffplay / trình phát mặc định)
================================================================================
Thứ tự ưu tiên khi bấm Phát trong tool:
  1. VLC NHÚNG trong cửa sổ tool (cần: đã cài VLC Player + `pip install python-vlc`).
     Video chạy ngay trong BOX 8, có nút Phát / Tạm dừng / Dừng + giờ chạy.
  2. ffplay (đi kèm ffmpeg, tool đã bắt buộc có): mở cửa sổ riêng để xem.
  3. Trình phát mặc định của máy (Windows Media Player, VLC ngoài...):
     `os.startfile` trên Windows, `xdg-open` trên Linux, `open` trên macOS.

Vì sao không dùng K-Lite Codec Pack ở đây:
  - K-Lite chỉ là gói codec cài vào Windows cho các trình phát hệ thống,
    không có API cho Python nên tool không "tích hợp" được nó.
  - ffmpeg/ffplay đã giải mã được gần như mọi định dạng, VLC cũng tự
    mang codec của nó — nên K-Lite là thừa đối với tool này.

Chạy độc lập:
    python 08_preview.py --check        # Kiểm tra máy xem được bằng cách nào
    python 08_preview.py video.mp4      # Mở video bằng cách tốt nhất có trên máy

Dùng trong code khác (GUI):
    from preview import vlc_status, best_mode, play_external, VlcEmbed
    st = vlc_status()            # {"ok": True/False, "note": "..."}
    mode = best_mode()           # "vlc" | "ffplay" | "system"
    proc = play_external(path)   # mở ffplay / trình phát mặc định, trả về Popen hoặc None
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path


def vlc_status():
    """
    Kiểm tra xem máy có xem nhúng bằng VLC được không.
    Trả về dict {"ok": bool, "python_vlc": bool, "libvlc": bool, "note": str}.
    """
    try:
        import vlc  # noqa: F401  (chỉ kiểm tra import được không)
    except ImportError:
        return {"ok": False, "python_vlc": False, "libvlc": False,
                "note": "Chưa cài python-vlc. Cài bằng: pip install python-vlc"}
    try:
        import vlc
        inst = vlc.Instance("--quiet")
        inst.release()
    except Exception as e:
        return {"ok": False, "python_vlc": True, "libvlc": False,
                "note": f"Đã có python-vlc nhưng không tạo được VLC "
                        f"(chưa cài VLC Player hoặc sai bản 32/64-bit?): {e}"}
    return {"ok": True, "python_vlc": True, "libvlc": True,
            "note": "VLC sẵn sàng — xem nhúng trong tool."}


def ffplay_available():
    """True nếu máy có ffplay (đi kèm ffmpeg bản đầy đủ)."""
    return shutil.which("ffplay") is not None


def best_mode():
    """Cách xem tốt nhất có trên máy này: 'vlc' | 'ffplay' | 'system'."""
    if vlc_status()["ok"]:
        return "vlc"
    if ffplay_available():
        return "ffplay"
    return "system"


def play_external(path, log=print):
    """
    Mở video bằng trình phát NGOÀI tool (cửa sổ riêng).
    Ưu tiên ffplay (đi kèm ffmpeg), rớt về trình phát mặc định của máy.
    Trả về subprocess.Popen của ffplay (để GUI bấm Dừng thì tắt được),
    hoặc None nếu mở bằng trình phát mặc định.
    """
    path = str(Path(path))
    if not Path(path).exists():
        raise RuntimeError(f"Không tìm thấy file: {path}")
    if ffplay_available():
        cmd = ["ffplay", "-autoexit", "-window_title", f"Xem trước — {Path(path).name}", path]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            log(f"[XEM] Đang mở bằng ffplay: {Path(path).name}")
            return proc
        except OSError as e:
            log(f"[XEM] Không mở được ffplay ({e}), thử trình phát mặc định...")
    # Rớt về trình phát mặc định của hệ điều hành
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606 (mở file do chính người dùng chọn)
            log(f"[XEM] Đang mở bằng trình phát mặc định của Windows: {Path(path).name}")
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            log(f"[XEM] Đang mở bằng trình phát mặc định của macOS: {Path(path).name}")
        else:
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            log(f"[XEM] Đang mở bằng trình phát mặc định của Linux: {Path(path).name}")
    except OSError as e:
        raise RuntimeError(f"Không mở được video bằng trình phát mặc định: {e}")
    return None


def stop_external(proc):
    """Tắt tiến trình ffplay đã mở bằng play_external (nếu có)."""
    if proc is None:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
    except OSError:
        pass


class VlcEmbed:
    """
    Trình phát VLC NHÚNG vào 1 widget (PyQt6 QWidget hoặc Tkinter Frame).
    Chỉ tạo được khi vlc_status()["ok"] là True, nếu không sẽ nổ lỗi —
    GUI phải kiểm tra trước rồi mới tạo, và rớt về play_external khi lỗi.
    Tạo LẦN ĐẦU khi người dùng bấm Phát (lúc đó widget đã hiện lên màn hình,
    winId() / winfo_id() mới có id cửa sổ thật để VLC bám vào).
    """

    def __init__(self, frame):
        import vlc
        self._vlc = vlc
        self.frame = frame
        self.instance = vlc.Instance("--no-video-title-show", "--quiet")
        self.player = self.instance.media_player_new()
        if hasattr(frame, "winId"):
            wid = int(frame.winId())
        elif hasattr(frame, "winfo_id"):
            wid = int(frame.winfo_id())
        else:
            wid = int(frame)
        if sys.platform.startswith("win"):
            self.player.set_hwnd(wid)
        elif sys.platform == "darwin":
            self.player.set_nsobject(wid)
        else:
            self.player.set_xwindow(wid)
        self._path = None

    def load(self, path):
        media = self.instance.media_new(str(path))
        self.player.set_media(media)
        self._path = str(path)

    def play(self):
        return self.player.play() == 0

    def pause(self):
        self.player.pause()

    def stop(self):
        self.player.stop()

    def is_playing(self):
        try:
            return self.player.is_playing() == 1
        except Exception:
            return False

    def time_ms(self):
        try:
            return max(0, int(self.player.get_time()))
        except Exception:
            return 0

    def length_ms(self):
        try:
            return max(0, int(self.player.get_length()))
        except Exception:
            return 0

    def set_time(self, ms):
        try:
            self.player.set_time(int(ms))
        except Exception:
            pass

    def release(self):
        try:
            self.stop()
            self.player.release()
            self.instance.release()
        except Exception:
            pass


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="Xem trước video (VLC / ffplay / mặc định)")
    p.add_argument("video", nargs="?", default="", help="File video cần mở")
    p.add_argument("--check", action="store_true",
                   help="Chỉ kiểm tra máy xem được bằng cách nào, không mở video")
    a = p.parse_args(argv)

    st = vlc_status()
    print("========== KIỂM TRA XEM VIDEO ==========")
    print(f"python-vlc : {'có' if st['python_vlc'] else 'không'}")
    print(f"libvlc     : {'có' if st['libvlc'] else 'không'}")
    print(f"ffplay     : {'có' if ffplay_available() else 'không'}")
    print(f"Cách tốt nhất trên máy này: {best_mode()}")
    print(f"Ghi chú    : {st['note']}")
    if not st["ok"]:
        print("Để xem nhúng trong tool: 1) cài VLC Player từ videolan.org "
              "(bản 64-bit, cùng bản với Python), 2) chạy: pip install python-vlc")
    print("========================================")
    if a.check or not a.video:
        return 0
    proc = play_external(a.video)
    if proc is not None:
        proc.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
