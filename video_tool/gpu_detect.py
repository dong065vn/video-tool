#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gpu_detect.py — QUÉT GPU VÀ CHỌN ENCODER PHÙ HỢP VỚI MÁY
=========================================================
Chạy độc lập:
    python gpu_detect.py              # In báo cáo máy + encoder khuyên dùng
    python gpu_detect.py --json       # In JSON để main.py / tool khác đọc
    python gpu_detect.py --probe      # Bỏ cache, quét lại từ đầu

Cách quét (theo thứ tự ưu tiên):
  1. Đọc danh sách encoder của ffmpeg (ffmpeg -encoders).
  2. Kiểm tra phần cứng thật:
     - NVIDIA: nvidia-smi phải liệt kê được GPU.
     - Intel QSV: cần encoder h264_qsv (Windows) hoặc /dev/dri trên Linux.
     - AMD AMF: chỉ có trên Windows, cần encoder h264_amf.
     - VAAPI: chỉ trên Linux, cần /dev/dri/renderD128.
  3. PROBE ENCODE THẬT: encode thử 1 giây video testsrc bằng encoder đó.
     Chỉ tin encoder nào probe thành công — vì ffmpeg liệt kê h264_nvenc
     không có nghĩa là máy có card NVIDIA (VD: máy ảo vẫn liệt kê đủ).

Kết quả: NVENC > QSV > AMF > VAAPI > libx264 (CPU).
Nếu không có GPU nào dùng được thì dùng libx264 và tự chỉnh preset/threads
theo số nhân CPU (máy yếu <= 4 nhân -> preset fast, máy khỏe -> medium).

Trả về dict:
    {
      "gpu": "NVIDIA GeForce RTX 4060" | "Intel ..." | "Không có GPU rời",
      "gpu_vendor": "nvidia" | "intel" | "amd" | "none",
      "encoder": "h264_nvenc" | "h264_qsv" | "h264_amf" | "h264_vaapi" | "libx264",
      "hardware": True | False,
      "cpu_cores": 8, "ram_gb": 16.0,
      "preset": "p4" | "medium" | "fast",
      "threads": 8,
      "reason": "...",
    }
"""
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CACHE_FILE = Path(__file__).parent / "gpu_cache.json"
CACHE_TTL_SECONDS = 24 * 3600


def _activate_ffmpeg(executable):
    """Đặt đúng cặp ffmpeg/ffprobe đã probe thành công lên đầu PATH."""
    executable = Path(executable)
    bin_dir = str(executable.parent)
    parts = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    norm = os.path.normcase(bin_dir.rstrip("\\/"))
    parts = [p for p in parts
             if os.path.normcase(p.rstrip("\\/")) != norm]
    os.environ["PATH"] = os.pathsep.join([bin_dir] + parts)
    os.environ["VIDEO_TOOL_FFMPEG_DIR"] = bin_dir
    return str(executable)


def _ffmpeg_version(executable):
    r = _run([str(executable), "-version"], timeout=10)
    first = r.stdout.splitlines()[0] if r and r.returncode == 0 and r.stdout else ""
    m = re.search(r"\bffmpeg version\s+(?:n)?(\d+)", first, re.IGNORECASE)
    return (int(m.group(1)) if m else 0), first


def ffmpeg_candidates(profile="auto"):
    """Liệt kê mọi FFmpeg khả dụng, ưu tiên bản mới/cũ theo lựa chọn."""
    found = []
    selected_dir = os.environ.get("VIDEO_TOOL_FFMPEG_DIR")
    if selected_dir:
        found.append(Path(selected_dir) / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg"))
    current = shutil.which("ffmpeg")
    if current:
        found.append(Path(current))
    if sys.platform.startswith("win"):
        local_app = Path(os.environ.get("LOCALAPPDATA", ""))
        roots = [
            local_app / "Programs" / "ffmpeg",
            local_app / "Microsoft" / "WinGet" / "Packages",
            Path.home() / "ffmpeg",
            Path("C:/ffmpeg"),
        ]
        for root in roots:
            if root.is_dir():
                found.extend(root.glob("**/ffmpeg.exe"))

    unique = {}
    for path in found:
        try:
            if path.is_file():
                unique.setdefault(os.path.normcase(str(path.resolve())), path.resolve())
        except OSError:
            continue

    candidates = []
    for path in unique.values():
        major, version = _ffmpeg_version(path)
        lower = str(path).lower()
        kind = "legacy" if major and major <= 5 or "legacy" in lower or "5.1.2" in lower else "modern"
        candidates.append({
            "path": str(path),
            "major": major,
            "version": version or path.name,
            "kind": kind,
        })

    prefer_legacy = profile == "nvidia_legacy"
    candidates.sort(key=lambda c: (
        0 if (c["kind"] == "legacy") == prefer_legacy else 1,
        -c["major"],
        c["path"].lower(),
    ))
    return candidates


def ensure_ffmpeg_path(profile="auto"):
    candidates = ffmpeg_candidates(profile)
    if candidates:
        _activate_ffmpeg(candidates[0]["path"])
        return candidates[0]["path"]
    return None


def _run(cmd, timeout=20):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def list_ffmpeg_encoders(ffmpeg="ffmpeg"):
    """Đọc encoder H.264 mà một bản FFmpeg hỗ trợ."""
    r = _run([str(ffmpeg), "-hide_banner", "-encoders"])
    if not r or r.returncode != 0:
        return set()
    encoders = set()
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and (parts[1].startswith("h264_")
                                or parts[1].startswith("libx264")):
            encoders.add(parts[1])
    return encoders


def nvidia_gpu_info():
    """Trả về tên + driver NVIDIA; NVENC vẫn được probe nếu lệnh này thiếu."""
    if shutil.which("nvidia-smi") is None:
        return {}
    r = _run(["nvidia-smi", "--query-gpu=name,driver_version",
              "--format=csv,noheader"])
    if not r or r.returncode != 0:
        return {}
    first = next((ln.strip() for ln in r.stdout.splitlines() if ln.strip()), "")
    if not first:
        return {}
    name, _, driver = first.partition(",")
    return {"name": name.strip(), "driver": driver.strip()}


def nvidia_gpu_name():
    return nvidia_gpu_info().get("name")


def dri_device_present():
    """Linux: có /dev/dri/renderD128 không (cần cho QSV/VAAPI)."""
    return os.path.exists("/dev/dri/renderD128") or os.path.exists("/dev/dri/card0")


def probe_encoder(encoder, extra_args=None, ffmpeg="ffmpeg"):
    """Encode thử 1 giây; chỉ trả True khi encoder tạo được file thật."""
    tmp = Path(tempfile.mkdtemp(prefix="gpu_probe_"))
    out = tmp / "probe.mp4"
    try:
        cmd = [str(ffmpeg), "-y", "-v", "error",
               "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=30",
               "-an"]
        if encoder == "h264_vaapi":
            cmd += ["-vaapi_device", "/dev/dri/renderD128",
                    "-vf", "format=nv12,hwupload",
                    "-c:v", "h264_vaapi"]
        elif encoder == "h264_qsv":
            cmd += ["-pix_fmt", "nv12", "-c:v", "h264_qsv",
                    "-preset", "veryfast", "-global_quality", "25"]
        elif encoder == "h264_nvenc":
            cmd += ["-pix_fmt", "yuv420p", "-c:v", "h264_nvenc",
                    "-preset", "p1", "-cq", "28"]
        elif encoder == "h264_amf":
            cmd += ["-pix_fmt", "yuv420p", "-c:v", "h264_amf",
                    "-quality", "speed", "-rc", "cqp", "-qp", "28"]
        else:
            cmd += ["-pix_fmt", "yuv420p", "-c:v", encoder]
        if extra_args:
            cmd += extra_args
        cmd += [str(out)]
        r = _run(cmd, timeout=30)
        return bool(r and r.returncode == 0 and out.exists()
                    and out.stat().st_size > 0)
    finally:
        try:
            out.unlink(missing_ok=True)
            tmp.rmdir()
        except OSError:
            pass


def machine_info():
    cores = os.cpu_count() or 4
    ram_gb = 0.0
    try:
        if sys.platform.startswith("win"):
            import ctypes
            class MEMSTATUS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = MEMSTATUS()
            st.dwLength = ctypes.sizeof(MEMSTATUS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            ram_gb = st.ullTotalPhys / (1024 ** 3)
        else:
            with open("/proc/meminfo", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        ram_gb = int(line.split()[1]) / (1024 ** 2)
                        break
    except Exception:
        ram_gb = 0.0
    return {"cpu_cores": cores, "ram_gb": round(ram_gb, 1),
            "os": platform.system(), "machine": platform.machine()}


def detect_gpu(use_cache=True, profile="auto"):
    """Probe encoder thật; tự chọn FFmpeg mới hoặc tương thích NVIDIA cũ."""
    if profile not in {"auto", "nvidia_legacy", "nvidia_modern"}:
        raise ValueError(f"Chế độ GPU không hợp lệ: {profile}")

    nv = nvidia_gpu_info()
    if use_cache and CACHE_FILE.exists():
        try:
            cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            cache_path = Path(cached.get("ffmpeg_path", ""))
            cache_ok = (
                time.time() - cached.get("_ts", 0) < CACHE_TTL_SECONDS
                and cached.get("_profile") == profile
                and cache_path.is_file()
                and cached.get("nvidia_driver", "") == nv.get("driver", "")
                and cached.get("nvidia_name", "") == nv.get("name", "")
            )
            if cache_ok:
                _activate_ffmpeg(cache_path)
                cached.pop("_ts", None)
                cached.pop("_profile", None)
                return cached
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    info = machine_info()
    cores = info["cpu_cores"]
    candidates = ffmpeg_candidates(profile)
    cpu_workers = max(1, min(4, cores // 4))
    cpu_threads = max(1, min(16, cores // cpu_workers))
    result = {
        "gpu": "Không có GPU rời",
        "gpu_vendor": "none",
        "encoder": "libx264",
        "hardware": False,
        "cpu_cores": cores,
        "ram_gb": info["ram_gb"],
        "os": info["os"],
        "preset": "fast" if cores <= 4 else "medium",
        "threads": cpu_threads,
        "recommended_workers": cpu_workers,
        "gpu_profile": profile,
        "ffmpeg_profile": "",
        "ffmpeg_version": "",
        "ffmpeg_path": "",
        "nvidia_name": nv.get("name", ""),
        "nvidia_driver": nv.get("driver", ""),
        "reason": "Không tìm thấy GPU dùng được, dùng CPU (libx264).",
        "detail": "",
    }

    failed_probes = []
    selected = None
    for candidate in candidates:
        encoders = list_ffmpeg_encoders(candidate["path"])
        if "h264_nvenc" not in encoders:
            continue
        if probe_encoder("h264_nvenc", ffmpeg=candidate["path"]):
            selected = candidate
            _activate_ffmpeg(candidate["path"])
            workers = 2 if candidate["kind"] == "legacy" else 3
            result.update({
                "gpu": nv.get("name") or "NVIDIA NVENC",
                "gpu_vendor": "nvidia",
                "encoder": "h264_nvenc",
                "hardware": True,
                "preset": "p4",
                "threads": max(1, min(8, cores // workers)),
                "recommended_workers": workers,
                "reason": (
                    f"NVENC hoạt động với FFmpeg {candidate['kind']} "
                    f"(đã probe encode thành công)."
                ),
            })
            break
        failed_probes.append(
            f"h264_nvenc ({candidate['kind']}, {Path(candidate['path']).name})"
        )

    if selected is None and candidates:
        selected = candidates[0]
        _activate_ffmpeg(selected["path"])
        encoders = list_ffmpeg_encoders(selected["path"])
        generic = []
        if "h264_qsv" in encoders and (info["os"] == "Windows" or dri_device_present()):
            generic.append(("h264_qsv", "intel", "Intel Quick Sync Video", "medium"))
        if "h264_amf" in encoders and info["os"] == "Windows":
            generic.append(("h264_amf", "amd", "AMD AMF", "balanced"))
        if ("h264_vaapi" in encoders and info["os"] == "Linux"
                and dri_device_present()):
            generic.append(("h264_vaapi", "intel", "VAAPI", "medium"))
        for encoder, vendor, label, preset in generic:
            if probe_encoder(encoder, ffmpeg=selected["path"]):
                result.update({
                    "gpu": label,
                    "gpu_vendor": vendor,
                    "encoder": encoder,
                    "hardware": True,
                    "preset": preset,
                    "threads": max(1, min(8, cores // 2)),
                    "recommended_workers": 2,
                    "reason": (
                        f"Tìm thấy {label}, {encoder} đã probe encode thành công."
                    ),
                })
                break
            failed_probes.append(encoder)

    if selected:
        result.update({
            "ffmpeg_profile": selected["kind"],
            "ffmpeg_version": selected["version"],
            "ffmpeg_path": selected["path"],
        })

    if not result["hardware"]:
        parts = []
        if not candidates:
            parts.append("không tìm thấy ffmpeg/ffprobe")
        if nv:
            parts.append(
                f"nvidia-smi: {nv.get('name')} (driver {nv.get('driver') or '?'})"
            )
        else:
            parts.append("nvidia-smi không thấy card/driver NVIDIA")
        if failed_probes:
            parts.append("probe thất bại: " + ", ".join(failed_probes))
        result["detail"] = " | ".join(parts)
        result["reason"] = "Dùng CPU (libx264). " + result["detail"]

    try:
        to_cache = dict(result)
        to_cache["_profile"] = profile
        to_cache["_ts"] = time.time()
        CACHE_FILE.write_text(
            json.dumps(to_cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass
    return result


def report(det):
    lines = [
        "========== QUÉT GPU / MÁY ==========",
        f"Hệ điều hành : {det.get('os', '?')} ({platform.machine()})",
        f"CPU          : {det.get('cpu_cores', '?')} nhân | RAM: {det.get('ram_gb', '?')} GB",
        f"GPU          : {det.get('gpu', '?')}",
        f"Encoder      : {det.get('encoder', '?')} ({'phần cứng' if det.get('hardware') else 'CPU'})",
        f"FFmpeg       : {det.get('ffmpeg_profile', '?')} | {det.get('ffmpeg_path', '?')}",
        f"Preset       : {det.get('preset', '?')} | Threads: {det.get('threads', '?')} | Workers: {det.get('recommended_workers', '?')}",
        f"Kết luận     : {det.get('reason', '')}",
    ]
    if det.get("detail"):
        lines.append(f"Chi tiết     : {det['detail']}")
    lines.append("====================================")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Quét GPU và chọn encoder phù hợp với máy")
    p.add_argument("--json", action="store_true", help="In JSON thay vì báo cáo")
    p.add_argument("--probe", action="store_true", help="Bỏ cache, quét lại từ đầu")
    p.add_argument("--profile", default="auto",
                   choices=["auto", "nvidia_legacy", "nvidia_modern"])
    a = p.parse_args()
    det = detect_gpu(use_cache=not a.probe, profile=a.profile)
    if a.json:
        print(json.dumps(det, ensure_ascii=False, indent=2))
    else:
        print(report(det))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
