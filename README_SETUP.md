# Cài đặt môi trường & PATH tự động — chỉ 1 script duy nhất (`setup_python.bat`)

Dùng cho máy Windows chưa có Python / FFmpeg, hoặc có mà quá cũ / gõ `python`, `ffmpeg`, `video-tool` báo lỗi `'... is not recognized'`.

## Cách dùng nhanh nhất (khuyên dùng)

1. Giải nén thư mục tool ra máy (ví dụ `C:\Users\byscom\Downloads\video_tool`).
2. Double-click file **`setup_python.bat`** (script tự đóng gói toàn bộ logic cài đặt PowerShell bên trong, không cần file `.ps1` rời, không cần quyền Admin).
3. Script tự động thực hiện trọn gói:
   - **Kiểm tra Python (`>= 3.10`)**: Bỏ qua stub 0-byte của Windows Store (`WindowsApps`). Nếu chưa có hoặc quá cũ, tự tải bộ cài Python 3.12.8 từ `python.org`, cài silent per-user.
   - **Đặt Python vào User PATH**: Đưa thư mục cài Python và `Scripts` lên đầu `User PATH` để tránh xung đột với Windows Store stub.
   - **Kiểm tra `pip` & cài `requirements.txt`**: Tự nâng cấp `pip` và cài `Pillow`.
   - **Kiểm tra & tự động cài FFmpeg (`ffmpeg` + `ffprobe`)**: Nếu máy chưa có FFmpeg, tự cài qua `winget install Gyan.FFmpeg` (hoặc tải bản portable zip dự phòng) và **đặt sẵn thư mục `bin` của FFmpeg vào `User PATH`**.
   - **Đặt sẵn thư mục `video_tool` vào `User PATH`**: Tạo sẵn launcher `video-tool.bat` và `run_video_tool.bat` để bạn gọi lệnh `video-tool` ở bất kỳ thư mục nào.
4. Sau khi cài xong, mở **CMD / PowerShell MỚI** và dùng ngay ở bất kỳ đâu:
   ```bat
   video-tool                  :: Mở giao diện GUI (main.py)
   video-tool gpu              :: Quét GPU và chọn encoder
   video-tool info -i a.mp4    :: Xem thông số chi tiết video
   video-tool silence -i a.mp4 --scan
   ```
   Hoặc double-click **`run_video_tool.bat`** để mở giao diện đồ họa ngay lập tức.

## Chạy `setup_python.bat` từ CMD / PowerShell theo tùy chọn

```bat
:: Cài đầy đủ (Python + requirements + FFmpeg + đặt sẵn User PATH)
setup_python.bat

:: Chỉ kiểm tra môi trường và PATH hiện tại (không cài, không sửa PATH)
setup_python.bat -CheckOnly

:: Bỏ qua bước tự cài FFmpeg hoặc requirements
setup_python.bat -SkipFFmpeg
setup_python.bat -SkipRequirements
```

## Các file môi trường & launcher

| File | Vai trò |
|---|---|
| `setup_python.bat` | **Script cài đặt duy nhất**: double-click để kiểm tra/cài Python, pip, requirements, FFmpeg và cấu hình `User PATH` vĩnh viễn. |
| `video-tool.bat` | CLI/GUI launcher toàn cục sau khi thư mục được thêm vào PATH (`video-tool`, `video-tool gpu`, `video-tool batch ...`). |
| `run_video_tool.bat` | Double-click để mở nhanh giao diện GUI (`main.py`). |
