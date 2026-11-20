# Video Tool v2 — Folder → Mirror → Speed → Ảnh → Sticker → H.264 .mp4

## Chưa có Python / FFmpeg trên Windows? — Chạy `setup_python.bat` trước

Double-click file **`setup_python.bat`** (script cài đặt duy nhất, đã đóng gói toàn bộ logic bên trong) trong thư mục này. Nó sẽ thiết lập trọn gói:
1. Kiểm tra Python (`>= 3.10`), nếu chưa có thì tự tải Python 3.12.8 từ `python.org`, cài silent per-user.
2. Cài đặt thư viện trong `requirements.txt`.
3. Kiểm tra `ffmpeg` & `ffprobe`, nếu chưa có thì tự động cài FFmpeg. Máy
   NVIDIA driver cũ được cài thêm FFmpeg 5.1.2 trong thư mục `legacy`;
   bản mới nằm riêng trong `modern`, không ghi đè lẫn nhau.
4. **Đặt sẵn vào môi trường `User PATH` vĩnh viễn**: thư mục Python,
   `Scripts`, FFmpeg và chính thư mục `video_tool`.

Sau đó mở CMD / PowerShell **mới** ở bất kỳ đâu rồi gõ `video-tool` (hoặc `python main.py`, hoặc double-click `run_video_tool.bat`). Chi tiết xem `README_SETUP.md`.

## Thay đổi lớn ở v2

- **Đã bỏ convert FLV.** Không còn bước `.flv` → `.mp4` nữa. Các file
  `.flv` trong thư mục video sẽ bị bỏ qua kèm cảnh báo. Các module cũ
  (re-encode, crop, overlay chữ, pitch, concat, tạo overlay PNG) vẫn còn
  nguyên trong thư mục **`legacy/`** nếu bạn cần dùng lại.
- **Import theo folder, ghép lần lượt:** chuẩn bị 3 thư mục — video, ảnh,
  sticker. Tool ghép từng video với 1 ảnh **khác nhau** và 1 sticker
  **khác nhau** theo thứ tự tên file: video 1 ↔ ảnh 1 ↔ sticker 1,
  video 2 ↔ ảnh 2 ↔ sticker 2... Ít ảnh/sticker hơn video thì lặp lại
  từ đầu. Có chế độ `shuffle` để xáo trộn thứ tự ghép.
- **1 lần encode duy nhất cho mỗi video:** mirror + tăng speed + ghép ảnh
  + ghép sticker được gộp vào 1 filter graph, encode 1 lần ra H.264 .mp4
  — giữ chất lượng tốt nhất thay vì encode lại nhiều lần.
- **Khung 9:16 mặc định:** video thành phẩm ra **1080x1920** đúng như bố
  cục trong ảnh mẫu — ảnh làm nền lấp đầy khung, video phủ lên trên ở
  giữa với tỉ lệ **0.94** (như Scale 94% trong CapCut), sticker phủ lên
  trên cùng. Không có ảnh thì nền đen. Muốn về kiểu cũ (giữ nguyên kích
  thước video, ảnh ghép góc/phủ/banner) thì tắt checkbox Khung 9:16 ở
  tab **Bố cục & Preview** hoặc thêm `--no-frame-916`.
- **GPU tự quét cho NVIDIA cũ và mới:** tool thử encode thật với từng bản
  FFmpeg, ưu tiên bản mới rồi tự chuyển sang bản tương thích nếu driver
  NVENC cũ. Tab **Xuất & GPU** có thêm hai lựa chọn ép `NVIDIA cũ` và `NVIDIA mới`;
  mặc định `Tự động` là lựa chọn nên dùng. Intel QSV, AMD AMF và CPU vẫn
  là các đường dự phòng.
- **Xử lý song song:** nhiều video chạy đồng thời bằng worker riêng. Giá
  trị `Workers = 0` tự chọn theo GPU/CPU và tự giảm threads/worker khi
  dùng `libx264` để không vượt số luồng CPU.
- **Tiến độ và log:** bảng worker hiển thị video, trạng thái và phần trăm
  encode thực từ FFmpeg. Mỗi lần chạy tạo một file log có timestamp trong
  thư mục đầu ra.

## Giao diện chính — `main.py` (PyQt6 Studio Dark UI)

```bash
python main.py
```

Giao diện được thiết kế trên nền **PyQt6 Dark Theme** hiện đại, thanh Header cố định phía trên luôn có sẵn nút **`▶ Chạy đồng bộ`**, **`Khôi phục mặc định`**, **`Dry-run`**, **`Hướng dẫn`** và badge trạng thái thời gian thực:

- **1. Nguồn dữ liệu:** chọn thư mục video / ảnh / sticker hoặc một file video, có nút `Xóa` nhanh cho từng ô, cách ghép cặp `order`/`shuffle` và thư mục đầu ra.
- **2. Bố cục & Preview:** chỉnh mirror, tốc độ (gộp gọn trên 1 hàng), ảnh, khung 9:16, tỉ lệ/vị trí và **tọa độ `Left` / `Right` / `Top` / `Bottom` (px)** kèm các nút **Căn nhanh** cho cả **Video** lẫn **Sticker**.
  - **Auto đặt Sticker ở 4 góc (`auto-corners` — mặc định):** Sticker tự động luân chuyển qua 4 góc theo từng video trong batch (Video 1: `top-right` → Video 2: `bottom-left` → Video 3: `top-left` → Video 4: `bottom-right`, rồi lặp lại) để không giữ nguyên một chỗ.
  - **Nút `◀ Trước` / `Tiếp (Next) ▶` trên khung Preview:** Cho phép duyệt xem trước từng tổ hợp `Video + Ảnh nền + Sticker + Góc sticker` tiếp theo sẽ trông như thế nào trước khi bấm chạy batch.
- **3. Xuất & GPU:** chất lượng, bitrate, encoder, ba chế độ GPU
  `Tự động (NVIDIA cũ + mới)` / `NVIDIA cũ` / `NVIDIA mới`, worker,
  threads/worker và chia video dài.
- **4. Xem video (Danh sách video có nút `[▷ Xem]` mở Popup riêng):**
  - Màn hình chính chỉ hiển thị **bảng danh sách toàn bộ video nguồn đã import** (`#`, `Tên video gốc`, `Dung lượng`, `Cập nhật gần nhất`, `Ảnh & Sticker ghép`, `Trạng thái đầu ra`, và cột `Hành động` có nút **`[▷ Xem]`** trên từng dòng).
  - **Chỉ khi bấm `[▷ Xem]`** (hoặc đúp chuột vào dòng), một **cửa sổ Popup riêng (`VideoPreviewDialog`)** mới hiện lên (giống mẫu quản lý video):
    1. **Bên trái (`1. Video GỐC`):** Hiển thị hình ảnh Video GỐC ở bên trái và bảng thông số kỹ thuật `ffprobe` chi tiết ở bên phải, kèm nút `▷ Phát video gốc`.
    2. **Ở giữa (`2. So sánh với Video ĐẦU RA`):** Có nút **`[📥 Import video đầu ra...]`** để chọn 1 file video đầu ra bất kỳ lên xem hình ảnh đầu ra + thông số `ffprobe` chi tiết.
    3. **Bên phải (`3. Bảng So sánh & Kết luận phân tích`):** Đối chiếu 4 cột (*Tiêu chí* | *Video Gốc* | *Video Đầu ra* | *Đánh giá*) và tự động viết kết luận phân tích.
- **5. Cắt khoảng im:** quét trực tiếp, xem kế hoạch rồi cắt riêng một video;
  hoặc bật cắt khoảng im cho batch. Báo cáo ghi rõ timestamp, số frame
  đầu/cuối thực tế và thời lượng sẽ giữ/cắt.
- **Khung Tiến độ & Nhật ký ghim cố định ở đáy (Bottom Dock — có thể ẩn/hiện):** Không chia thành tab riêng mà ghim cố định ở phía dưới màn hình qua thanh kéo `QSplitter` (bên trái là bảng Worker, bên phải là Log thời gian thực, phía trên là thanh tiến độ tổng). Có thể bấm nút **`▾ Ẩn Tiến độ & Log`** trên thanh Header hoặc **`▾ Ẩn khung Log`** ngay tại khung đáy để thu gọn bất cứ lúc nào.

Mặc định: Mirror + Speed 1.2x + ảnh + sticker + khung 9:16 bật, bitrate
gốc, GPU tự nhận diện, Workers `0` (tự tối ưu), chia đoạn 300 giây bật.
Các giải thích dài nằm trong nút **Hướng dẫn**.

Chạy không giao diện (cùng logic):

```bash
python main.py --cli --videos ./videos --images ./anh --stickers ./sticker -o ./out/
python main.py --cli --videos ./videos --images ./anh -o ./out/ --speed 1.10 --quality-mode bitrate --quality-value 8M
python main.py --cli --video mot_video.mp4 --images ./anh --stickers ./sticker -o ./out/ --no-mirror
# Tự tối ưu worker (mặc định) hoặc đặt 4 worker
python main.py --cli --videos ./videos -o ./out/ --workers 0
python main.py --cli --videos ./videos -o ./out/ --workers 4
# Ép đường NVIDIA cũ/mới khi cần; auto vẫn là mặc định
python main.py --cli --videos ./videos -o ./out/ --gpu-profile nvidia_legacy
python main.py --cli --videos ./videos -o ./out/ --gpu-profile nvidia_modern
# Tắt khung 9:16 hoặc tắt chia đoạn
python main.py --cli --videos ./videos -o ./out/ --no-frame-916
python main.py --cli --videos ./videos -o ./out/ --no-chunk
```

## Cấu trúc

| File | Chức năng riêng | Nó làm gì | Nó KHÔNG làm gì |
|---|---|---|---|
| `common.py` | Hàm dùng chung | `ffprobe`, chạy lệnh, `encode_args` (CRF/bitrate/gốc), `pair_files`, `build_filter_graph` | Không xử lý video |
| `gpu_detect.py` | 0. Quét GPU | Phát hiện NVIDIA/Intel/AMD, probe encode thật, chọn encoder + preset/threads | Không xử lý video |
| `01_mirror.py` | 1. Mirror | Lật ngang `hflip`, xuất H.264 .mp4 | Không đổi gì khác (audio `-c:a copy`) |
| `02_speed.py` | 2. Tăng speed | Video `setpts` + audio `atempo`, xuất H.264 .mp4 | Không đổi pitch |
| `03_image_overlay.py` | 3. Ghép ảnh | Ghép 1 ảnh (corner/full/banner), xuất H.264 .mp4 | Không động vào bước khác |
| `04_sticker.py` | 4. Ghép sticker | Ghép 1 sticker PNG trong suốt, xuất H.264 .mp4 | Không động vào bước khác |
| `05_batch.py` | 5. Hàng loạt | Đọc 3 folder, ghép cặp lần lượt, 1 lần encode/video (video dài tự chia đoạn) | Không convert FLV |
| `06_chunk.py` | 6. Video dài | Cắt video dài thành từng đoạn, xử lý từng đoạn, ghép lại; đoạn xong rồi tự bỏ qua | Không encode lại khi cắt/ghép |
| `07_media_info.py` | 7. Thông số video | Đọc thông số chi tiết bằng ffprobe: codec, độ phân giải, fps, bitrate, âm thanh, phụ đề, thời lượng | Không phát video, không sửa file |
| `08_preview.py` | 8. Xem trước video | Phát video: VLC nhúng (nếu có) → ffplay → trình phát mặc định của máy | Không sửa file, không cần K-Lite |
| `layout_preview.py` | Preview bố cục | Lấy một frame video và dựng preview ảnh/sticker/khung hình theo tỉ lệ đầu ra | Không encode hoặc sửa video |
| `09_silence.py` | 9. Cắt khoảng lặng | Quét khoảng im theo độ lớn trung bình của video rồi cắt bỏ, ghép lại (video KOC); tích hợp vào chạy đồng bộ: cắt lặng TRƯỚC khi xử lý chính, file tạm tự xóa | Không cắt khoảng ngừng ngắn (nhịp nói), không làm lệch hình/tiếng |
| `video_processor.py` | Điều phối | Mỗi lệnh chỉ gọi đúng 1 file trên | Không tự chạy quy trình |
| `legacy/` | Module v1 cũ | Re-encode FLV, crop, overlay chữ, pitch, concat... | Không dùng trong v2 |

## Cài đặt

```bash
sudo apt install ffmpeg          # Ubuntu / Debian
brew install ffmpeg              # macOS
pip install -r requirements.txt  # Pillow dùng cho preview bố cục
```

## Cách chạy — 2 cách như nhau

### Cách A: chạy trực tiếp từng file

```bash
# 0. Quét GPU (auto thử FFmpeg mới rồi bản tương thích)
python gpu_detect.py
python gpu_detect.py --json
python gpu_detect.py --profile nvidia_legacy
python gpu_detect.py --profile nvidia_modern
# 1. Mirror riêng
python 01_mirror.py -i in.mp4 -o out.mp4

# 2. Tăng speed riêng
python 02_speed.py -i in.mp4 -o out.mp4 --speed 1.2

# 3. Ghép 1 ảnh riêng
python 03_image_overlay.py -i in.mp4 -o out.mp4 --image anh.jpg
python 03_image_overlay.py -i in.mp4 -o out.mp4 --image anh.jpg --mode full --opacity 0.6
# 3b. Khung 9:16 cho 1 video riêng (ảnh làm nền, video phủ 94% ở giữa)
python 03_image_overlay.py -i in.mp4 -o out.mp4 --image anh.jpg --frame-916

# 4. Ghép 1 sticker riêng
python 04_sticker.py -i in.mp4 -o out.mp4 --sticker st.png
python 04_sticker.py -i in.mp4 -o out.mp4 --sticker st.png --position top-right --scale 0.2

# 5. Hàng loạt theo folder; 0 = tự tối ưu số worker
python 05_batch.py --videos ./videos --images ./anh --stickers ./sticker -o ./out/ --workers 0
python 05_batch.py --videos ./videos -o ./out/ --workers 4 --gpu-profile nvidia_modern
# 6. Video dài: chia đoạn 300s, xử lý từng đoạn, ghép lại (1 video duy nhất)
python 06_chunk.py --video video_dai.mp4 -o video_dai_done.mp4 --images ./anh --stickers ./sticker
python 06_chunk.py --video video_dai.mp4 -o video_dai_done.mp4 --chunk-seconds 600 --keep-chunks

# 7. Xem thông số chi tiết của 1 video (ffprobe)
python 07_media_info.py video.mp4
python 07_media_info.py video.mp4 --json

# 8. Xem trước video (VLC nhúng / ffplay / mặc định)
python 08_preview.py --check
python 08_preview.py video.mp4

# 9. Quét khoảng lặng rồi cắt bỏ (video KOC)
python 09_silence.py -i video.mp4 --scan
python 09_silence.py -i video.mp4
python 09_silence.py -i video.mp4 -o gon.mp4 --min-cut 2.0 --pad 0.3 --margin 15
```

### Cách B: chạy qua `video_processor.py` (mỗi lệnh vẫn chỉ gọi 1 file)

```bash
python video_processor.py gpu --profile auto
python video_processor.py mirror  -i in.mp4 -o out.mp4
python video_processor.py speed   -i in.mp4 -o out.mp4 --speed 1.2
python video_processor.py image   -i in.mp4 -o out.mp4 --image anh.jpg
python video_processor.py sticker -i in.mp4 -o out.mp4 --sticker st.png
python video_processor.py batch   --videos ./videos --images ./anh --stickers ./sticker -o ./out/ --workers 0
python video_processor.py chunk   --video video_dai.mp4 -o done.mp4 --images ./anh --stickers ./sticker
python video_processor.py info    -i video.mp4
python video_processor.py play    -i video.mp4
python video_processor.py play    --check
python video_processor.py silence -i video.mp4 --scan
python video_processor.py silence -i video.mp4 -o gon.mp4 --min-cut 2.0
```

## Cắt khoảng im (video KOC) — tab **Cắt khoảng im**

Video bán hàng / livestream KOC thường có nhiều đoạn chết: người bán
ngừng nói, chờ khách, chuyển cảnh... Cắt các khoảng lặng dài đi thì
video gọn, giữ chân người xem hơn — nhưng phải cắt đúng chỗ, nếu không
sẽ cắt mất nhịp nói tự nhiên. Tool làm theo 2 bước, đều chỉ dùng ffmpeg
có sẵn (không cần cài thêm gì):

**1. Quét — có nhận ra đoạn "nhỏ hơn bình thường" không? Có.**
Tool đo độ lớn trung bình của CẢ video (`volumedetect` → `mean_volume`)
rồi tính ngưỡng im TƯƠNG ĐỐI theo video đó: ngưỡng = độ lớn trung bình
− margin (mặc định 20 dB). Đoạn nào nhỏ hơn hẳn mức nói bình thường của
chính video đó thì bị nhận là im — kể cả đoạn không im hẳn mà chỉ nhỏ
tiếng (tiếng nền, nói lí nhí). Video quay ồn hay quay nhỏ đều quét được,
vì ngưỡng đi theo từng video chứ không phải một số dB cố định. Muốn
ngưỡng tuyệt đối thì chuyển sang `absolute` và nhập dB (VD: −40).
Sau đó `silencedetect` liệt kê mọi khoảng dưới ngưỡng. Với các đoạn đủ
điều kiện cắt, tool đọc timestamp của frame video thật và đẩy hai đầu
đoạn cắt tới đúng biên frame an toàn. Bấm `[Quét khoảng im]` để chạy
trực tiếp và xem báo cáo trước — chưa sửa file: độ lớn, ngưỡng, khoảng
im, mốc giây, số frame cắt, tổng thời lượng cắt và thời lượng đầu ra.

**2. Cắt — khi nào cắt, khi nào không? Toàn bộ đều tự động, không cần
duyệt tay từng đoạn (hợp với render tự động).** Nguyên tắc: khi nghi
ngờ thì GIỮ, không cắt — thà còn 5 giây im thừa còn hơn mất video.
- **Chỉ cắt khoảng im dài hơn mức bạn đặt** (mặc định 1.0s): khoảng
  ngừng ngắn giữa các câu (0.3–0.8s) là nhịp nói tự nhiên, GIỮ LẠI.
  Video KOC nói nhanh, khoảng ngừng ngắn nhiều thì tăng mức này lên
  (VD: 2.0s); video nào chết lâu mới cắt thì để 1.0s.
- **Khi cắt thì giữ đệm 0.2s ở hai đầu** khoảng im để câu nói không bị
  cắt cụt đầu/cuối. Đệm này cũng chỉnh được (0–1s).
- **Im tối thiểu để nhận** (mặc định 0.5s): im ngắn hơn mức này thì
  không tính là khoảng im ngay từ đầu.
- **Chống "đảo"** (mặc định 0.8s): đoạn nói kẹp giữa 2 khoảng im mà
  ngắn hơn 0.8s (VD: "vâng", "ừm") thì giữ lại khoảng im NGẮN HƠN bên
  cạnh — không thì video nghe giật cục, câu cụt lủn.
- **Giữ tối đa mỗi khoảng im** (mặc định 5s): khoảng im rất dài (VD:
  30s) sau khi cắt vẫn còn tối đa 5s — phòng trường hợp lúc đó đang
  chiếu sản phẩm cho khách xem. Đặt 0 là cắt hết.
- **Cắt mạnh đầu/cuối** (mặc định BẬT): khoảng im ở đầu và cuối video
  cắt luôn dù ngắn hơn mức đặt — không có câu nói nào để cụt.
- **Trần cắt tổng** (mặc định 30%): nếu tổng thời gian sẽ cắt vượt
  30% video thì tool tự tăng "chỉ cắt khi dài hơn" lên (1s → 2s → 3s
  → 5s → 10s) cho tới khi dưới trần; vẫn vượt thì KHÔNG CẮT GÌ, giữ
  nguyên video. Đây là phanh an toàn để render tự động không bao giờ
  cắt mất video. Đặt 0 là tắt trần.
- **Bảo vệ video thu quá nhỏ:** cả video không có đoạn nào to hơn
  −40 dB (nghi mic lỗi / thu quá nhỏ, ngưỡng tương đối sẽ sai) thì
  KHÔNG CẮT, giữ nguyên video.
- **Preset 1 chạm:** Nhẹ (chỉ cắt im trên 2s, đệm 0.3s, giữ tối đa
  8s) / Vừa (1s, 0.2s, 5s — mặc định) / Mạnh (0.8s, 0.15s, 3s).
  Chọn preset rồi bấm cắt, khỏi nhập số. Chỉnh tay 1 số thì preset
  tự về "Tự chọn".

Đã kiểm chứng từng điều kiện trên video test (đo thật, không đoán):
chống đảo giữ đúng khoảng im 2.6s bên cạnh tiếng "vâng" 0.4s; khoảng
im 20s trong video 30s thì không cắt gì (vượt trần 30%); khoảng im
20s trong video 60s thì cắt đúng 15s, còn 5s; im đầu/cuối 0.6s–0.8s
vẫn cắt dù ngắn hơn mức 1.0s; video thu quá nhỏ (lớn nhất −68 dB)
thì báo cảnh báo và không cắt.

**Quét hoạt động thế nào?** Tool quét âm thanh bằng `silencedetect`.
Khi có đoạn đủ điều kiện cắt, tool đọc metadata timestamp của frame bằng
`ffprobe`; không giải mã pixel hình. Ưu tiên độ chính xác của biên cắt,
không thay việc quét thật bằng một tác vụ chạy nền.

**Ghép lại có bị lệch hình/tiếng không?** Mỗi đoạn hình dùng
`trim=start_frame/end_frame` theo đúng chỉ số frame đã quét. Âm thanh
dùng `atrim` theo timestamp của chính các frame đó, được đệm/cắt về đúng
thời lượng đoạn rồi mới `concat`. Log cuối ghi riêng thời lượng hình,
tiếng và độ lệch đo bằng `ffprobe`. Tool encode lại tại điểm cắt; không
dùng `-c copy` ở điểm không phải keyframe.

Ví dụ chạy riêng:

```bash
python 09_silence.py -i video.mp4 --scan
python 09_silence.py -i video.mp4 -o gon.mp4 --min-cut 2.0 --pad 0.3 --margin 15
python 09_silence.py -i video.mp4 --mode absolute --threshold-db -45 --min-silence 0.3
# Render tự động, cắt nhẹ: chỉ im > 2s, giữ tối đa 8s mỗi khoảng im, trần cắt 20%
python 09_silence.py -i video.mp4 --min-cut 2.0 --pad 0.3 --max-keep-silence 8 --min-keep 1.0 --max-cut-ratio 20
```

File ra mặc định: `<tên>_catlang.mp4` cùng thư mục với video gốc.
Video không có âm thanh thì báo lỗi rõ ràng thay vì chạy rồi mới hỏng.

**Tích hợp vào chạy đồng bộ — mặc định BẬT trong GUI:** mỗi video được
quét khoảng im trước khi xử lý chính; có khoảng im đủ dài thì cắt theo
frame ra file tạm (`.<tên>_catlang_tmp.mp4` trong thư mục output, tự xóa
sau khi xong), rồi chạy mirror/speed/ảnh/sticker/chia đoạn trên file tạm.
Thứ tự: cắt im → chia đoạn nếu cần → xử lý từng đoạn → ghép lại. Không
có khoảng im đủ dài, không có tiếng hoặc lỗi quét thì batch dùng file gốc.
Đã kiểm chứng: video 40s có 3 khoảng im → chạy đồng bộ ra **25.2s**
(30.2s sau cắt lặng / speed 1.2x); video 40s + chia đoạn 10s cũng ra
**25.2s**; video không có tiếng vẫn ra đủ 10s/1.2x; tắt cắt lặng thì ra
đủ 40s/1.2x = **33.3s** như cũ.

**Phanh an toàn — mặc định BẬT:** checkbox `Bật phanh an toàn` và CLI
`--sil-safety` giới hạn tổng thời lượng cắt (mặc định 30%) và bảo vệ
video thu quá nhỏ. Nếu kế hoạch vượt trần, tool tăng mức im tối thiểu;
vẫn vượt thì giữ nguyên video. Dùng `--no-sil-safety` chỉ khi bạn chủ
động muốn tắt hai bảo vệ này.

Ví dụ chạy đồng bộ có cắt lặng (CLI):

```bash
python 05_batch.py --videos ./videos --images ./anh -o ./out/ --silence
python main.py --cli --videos ./videos --images ./anh -o ./out/ --no-silence
python video_processor.py batch --videos ./videos --images ./anh -o ./out/ --silence --sil-min-cut 2.0
python 05_batch.py --video video.mp4 -o ./out/ --silence --sil-safety --sil-max-cut-ratio 20
```

## Xem trước & Thông số video (BOX 8) — VLC / K-Lite, hiểu đúng

**Thông số chi tiết — dùng ffprobe, không dùng VLC:**
`07_media_info.py` chạy `ffprobe -show_format -show_streams` rồi in bảng
tiếng Việt: định dạng file, thời lượng, bitrate tổng, codec video (kèm
profile/level), độ phân giải, fps (kể cả 29.97), bitrate video, pixel
format, màu sắc, từng luồng âm thanh (codec, tần số, kênh, bitrate, ngôn
ngữ), phụ đề, chapters. Đây là nguồn chính xác nhất vì số liệu lấy trực
tiếp từ file — metadata của VLC hay MediaInfo chỉ là bản tóm tắt, có
trường đoán sai. Chạy riêng: `python 07_media_info.py video.mp4`
(hoặc `video_processor.py info -i video.mp4`).

**Xem trước video — VLC nhúng là tuỳ chọn, không bắt buộc:**
`08_preview.py` chọn cách xem tốt nhất có trên máy, theo thứ tự:
1. **VLC nhúng trong tool** — video chạy ngay trong khung đen ở BOX 8,
   có nút Phát / Tạm dừng / Dừng + đồng hồ thời gian. Cần 2 thứ trên
   laptop: cài **VLC Player** từ videolan.org (bản 64-bit, cùng bản với
   Python) rồi chạy `pip install python-vlc`.
2. **ffplay** — đi kèm ffmpeg nên máy nào có tool cũng có sẵn: mở video
   trong cửa sổ riêng, tự tắt khi hết video.
3. **Trình phát mặc định của máy** — Windows Media Player, VLC ngoài...
   nếu cả 2 cách trên đều không có.

Chưa cài VLC thì tool vẫn xem được bằng ffplay, không lỗi gì cả — chỉ
không nhúng được video vào trong cửa sổ tool thôi. Kiểm tra máy mình
xem được bằng cách nào: `python 08_preview.py --check`.

**K-Lite Codec Pack không tích hợp được vào tool — và cũng không cần:**
K-Lite chỉ là gói codec cài vào Windows để các trình phát hệ thống
(Windows Media Player...) chơi được nhiều định dạng hơn. Nó không có
API cho Python nên tool không thể "tích hợp" nó, và tool cũng không
cần nó: ffmpeg/ffprobe đã giải mã được gần như mọi định dạng, VLC thì
tự mang codec của nó. Cài K-Lite chỉ có ích khi bạn muốn mở video bằng
trình phát hệ thống của Windows, không liên quan gì tới tool này.

Muốn xem trước lệnh mà không chạy: thêm `--dry-run` vào bất kỳ file nào.

## Kiểm tra số nhập — báo lỗi rõ ràng trước khi chạy

Tool tự kiểm tra các số bạn nhập (speed, tỉ lệ video, độ mờ, cỡ sticker,
bitrate) **trước khi chạy ffmpeg**. Nhập sai sẽ báo lỗi tiếng Việt cụ thể,
VD: `Speed phải từ 0.01 đến 8, hiện tại: 0.0.` — thay vì để ffmpeg nổ với
lỗi khó hiểu. Giới hạn: speed 0.01–8, tỉ lệ video 0.01–1, độ mờ 0–1,
cỡ sticker 0.01–1, bitrate dạng `8M`/`4000k`.

## Khung 9:16 — hiểu đúng

Bố cục đúng như ảnh mẫu CapCut (video `HYthrift co.mp4` speed 1.2x trên
nền ảnh, Scale 94%, Position giữa):

- Ảnh nền được scale lấp đầy 1080x1920 rồi crop giữa — ảnh ngang hay dọc
  đều lấp đầy khung, không bị méo, không có viền đen.
- Video phủ lên trên, scale vừa khung 1080×0.94 x 1920×0.94 (1015x1804)
  và giữ đúng tỉ lệ gốc: video dọc gần như lấp đầy khung (chỉ chừa viền
  mỏng), video ngang thì nằm giữa, nền ảnh lộ ra trên/dưới.
- Vị trí `center` (mặc định) / `top` / `bottom` chỉnh video lên/xuống
  trong khung.
- Mirror, speed, sticker vẫn áp dụng như cũ, tất cả trong 1 lần encode.
- Không có ảnh nền thì nền đen. Muốn giữ nguyên kích thước video gốc
  (không ra 9:16) thì tắt Khung 9:16 — lúc đó ảnh quay về chế độ ghép
  góc/phủ/banner lên video.
- Lưu ý: ảnh mẫu còn có Stabilize và Enhance quality của CapCut — đó là
  tính năng AI của CapCut, không nằm trong tool này (tool chỉ làm đúng
  bố cục: nền ảnh + video 94% + speed 1.2x + mirror + sticker + H.264).

## Video dài (< 3GB, 1 tiếng trở lên) — chia đoạn rồi ghép lại

Video dài được xử lý khác video ngắn (mặc định BẬT ở BOX 7, tắt bằng
`--no-chunk`):

1. **Cắt đoạn:** tool cắt video gốc thành từng đoạn (mặc định 300s/đoạn)
   bằng `-c copy` — chỉ copy, không encode lại nên rất nhanh. Cắt tại
   keyframe nên đoạn thực tế có thể dài hơn 300s một chút.
2. **Xử lý từng đoạn:** mỗi đoạn được xử lý như 1 video riêng (mirror,
   speed, ảnh, sticker, khung 9:16 — giống hệt đường xử lý 1 lần).
3. **Ghép lại:** nối các đoạn đã xử lý bằng concat (copy, không encode
   lại) thành video hoàn chỉnh.

- **Hỏng giữa chừng không mất công làm lại:** đoạn nào xử lý xong rồi
  thì lần chạy sau tự bỏ qua. Đang render tới đoạn 8/12 mà mất điện thì
  mở lại tool chạy tiếp, tool chỉ làm từ đoạn 8 trở đi. Thư mục đoạn tạm
  nằm ở `<thư mục ra>/<tên video>_chunks/`; ghép xong thì tự xóa (tick
  "Giữ file đoạn tạm" nếu muốn giữ lại kiểm tra).
- **Ổ đĩa:** lúc đang làm cần chỗ trống khoảng 2 lần dung lượng video gốc
  (đoạn gốc + đoạn đã xử lý + file hoàn chỉnh). Ghép xong đoạn tạm bị xóa,
  chỉ còn file hoàn chỉnh.
- Video ngắn hơn 1 đoạn thì xử lý 1 lần như cũ, không chia đoạn.
- Chạy riêng 1 video dài: `python 06_chunk.py --video video_dai.mp4
  -o done.mp4 --images ./anh --stickers ./sticker`, hoặc
  `python video_processor.py chunk --video video_dai.mp4 -o done.mp4`.

## Độ dài video ra — hiểu đúng (bitrate không cắt ngắn video)

- Độ dài video ra = **thời lượng gốc / speed**. VD: video 60 phút,
  speed 1.2x → ra 50 phút; speed 3x → ra 20 phút (đó là đúng, không
  phải lỗi — video nhanh gấp 3 thì chỉ còn 1/3 thời lượng, dung lượng
  cũng giảm theo).
- **Chế độ bitrate không làm ngắn video.** Bitrate (`source` / `bitrate`
  / `crf`) chỉ đổi chất lượng và dung lượng file, không đổi thời lượng.
  Đã kiểm chứng: cùng 1 video 30s, chế độ bitrate cho ra đủ 25s
  (30 / 1.2), và giới hạn `-t` trên ảnh nền cũng không cắt ngắn video
  (nền chỉ 10s mà video ra vẫn đủ 25s) — độ dài ra do chính các frame
  video sau khi tăng speed quyết định.
- Nếu video ra ngắn hơn hẳn dự kiến, kiểm tra 2 chỗ trong log trước
  khi chạy lại: dòng `[INFO] Dự kiến ra: ...` (tool in ra trước mỗi
  video) và speed đang để ở BOX 2. Nếu dự kiến đã là 20 phút thì tool
  đang làm đúng theo speed bạn đặt — muốn video dài hơn thì giảm speed
  xuống (VD: 1.2x).

## Chất lượng & Bitrate — hiểu đúng

- `source` (mặc định): lấy bitrate của video gốc làm bitrate đích. Video
  gốc 8Mbps thì ra ~8Mbps, gốc 2Mbps thì ra ~2Mbps.
- `bitrate`: nhập tay, VD `8M`, `4M`, `1500k`. Encoder vẫn là ABR nên
  video đơn giản (ít chi tiết) có thể ra thấp hơn số nhập — đó là bình
  thường, encoder không "độn" bit thừa.
- `crf`: chất lượng cố định, VD `20` (18 = nét hơn, 23 = nhẹ hơn).
  Với NVENC thì dùng `-cq` tương đương, QSV dùng `-global_quality`,
  AMF dùng `-qp`.
- Sàn 800kbps: nếu video gốc có bitrate quá thấp (VD: 13kbps vì toàn màu
  trơn) thì giữ nguyên sẽ làm video ra bị xám/mất màu, nên tool tự nâng
  lên tối thiểu 800kbps.

## GPU — hiểu đúng

- Thứ tự ưu tiên: **NVENC (NVIDIA) > QSV (Intel) > AMF (AMD) > CPU
  (libx264)**. Trên laptop có card rời NVIDIA thì dùng NVENC sẽ nhanh hơn
  CPU nhiều lần; laptop chỉ có Intel iGPU thì dùng QSV; máy bàn không có
  card thì dùng CPU với preset/threads tự chỉnh theo số nhân.
- Tool không tin danh sách encoder của ffmpeg: mỗi encoder đều phải
  **encode thử 1 giây thật** mới được chọn. Máy ảo liệt kê đủ `h264_nvenc`
  nhưng không có card thì probe thất bại và tool tự về CPU.
- Kết quả quét được cache 7 ngày trong `gpu_cache.json` (bấm Quét GPU
  trong giao diện hoặc `python gpu_detect.py --probe` để quét lại).
- Muốn ép dùng CPU dù máy có card: chọn Encoder `libx264` hoặc bấm
  `[Dùng CPU]` ở BOX 6.

## Dùng với OBS

1. Chuẩn bị 3 thư mục: video nguồn, ảnh, sticker.
2. Mở `main.py`, chọn 3 thư mục ở BOX 0, tick các bước cần, bấm Chạy.
3. File ra nằm trong `video_done/` với tên `<tên gốc>_done.mp4`.
4. Trong OBS: `Sources → + → Media Source → chọn file mp4`.
