# Mandarin Studio · ElevenLabs

Tool Windows tạo video học tiếng Trung từ chủ đề: chữ Hán giản thể + pinyin có dấu thanh + nghĩa tiếng Việt.

## Cách dùng

1. Cài Python 3.12 trở lên trên Windows, tải repo rồi chạy `start.bat` lần đầu để cài thư viện. Chạy `install_shortcuts.ps1` bằng PowerShell để tạo icon. Những lần sau nhấp đúp **Mandarin Studio** trên Desktop hoặc trong Start Menu. App mở không kèm terminal, có icon riêng. `start.bat` vẫn dùng được để cài môi trường khi cần; cách này có thể hiện terminal trong lúc khởi tạo. Lỗi khởi động được ghi ở `startup.log`.
2. Tab **Cấu hình**: nhập Gemini API key để viết hội thoại; chọn model, chất lượng và thư mục xuất.
3. Tab **ElevenLabs**: nhập ElevenLabs API key, Voice ID cho Ngọc và Quân, chọn model và tốc độ. Ưu tiên giọng Mandarin đã nghe thử trong tài khoản của bạn. Dùng Voice ID, không dùng tên giọng hoặc URL.
4. Tab **Bài học**: nhập chủ đề, chọn HSK 1–2 / 3–4 / 5–6, thời lượng mục tiêu và tên kênh.
5. Bấm **Tạo video tự động từ chủ đề**. Tool viết kịch bản, tạo giọng tiếng Trung và xuất MP4.

Để dùng bài có sẵn: bấm **Bài mẫu** hoặc **Mở JSON**, chỉnh nội dung rồi bấm **Tạo giọng & xuất MP4**. Cả hai cách xuất đều cần cấu hình ElevenLabs. Key không cần gửi vào chat.

## Định dạng podcast

Hội thoại phát liền mạch một lần, chỉ có khoảng nghỉ tự nhiên 0,45 giây giữa các lượt thoại. Không lặp lại nội dung, không luyện nói, không chia PART hoặc chèn hướng dẫn học. Màn hình hiển thị chữ Hán, pinyin, bản dịch Việt. Không hiển thị tên nhân vật, số câu hoặc thanh tiến độ. Ngọc và Quân trong JSON chỉ dùng để ghép đúng Voice ID.


AI được hướng dẫn viết tình huống đời thường có vấn đề, diễn biến và cách giải quyết; mức HSK là mục tiêu do AI tuân theo, chưa có bộ kiểm định từ vựng HSK. Pinyin được AI tạo theo ngữ cảnh và có thể sửa trong JSON. Nên xem lại trước khi đăng.

Tổng thời lượng là ước lượng cho một lần phát; AI nhắm khoảng 210 chữ Hán mỗi phút. Kịch bản 600 chữ cũ không còn tương đương 10 phút khi bỏ lặp; muốn podcast 10 phút cần nội dung dài hơn, khoảng 2.000–2.200 chữ Hán tùy giọng. Tool hiện dùng thiết kế chữ riêng, chưa tạo ảnh nhân vật hoặc hoạt hình, chưa có tô sáng từng từ hay tự đăng YouTube.

## Kết quả

Mỗi lần xuất tạo thư mục riêng trong `outputs`:

- `video.mp4`: 720p hoặc 1080p, H.264/AAC, 24 fps.
- `lesson.json`: title_zh, title_vi, speakers; lines gồm speaker/zh/pinyin/vi; vocabulary gồm zh/pinyin/vi.
- `chinese.srt`: chữ Hán cho toàn bộ podcast.
- `hanzi_pinyin_vietnamese.srt`: chữ Hán, pinyin và nghĩa Việt cho toàn bộ podcast.
- `thumbnail.png`, `description.txt`, `chapters.txt`, `manifest.json`.
- `assets`: audio và ảnh trung gian. Mỗi lượt thoại chỉ phát một lần.


## Key, dữ liệu và credit

Gemini nhận chủ đề để viết bài. ElevenLabs nhận **chữ Hán** để tạo giọng, không đọc pinyin hoặc bản dịch Việt. Model mặc định `eleven_multilingual_v2`; có thể chọn Flash v2.5 hoặc Turbo v2.5. Tốc độ từ 0.7 đến 1.2.

App tự nạp cấu hình từ `.env` trong thư mục dự án khi mở. Khi sửa trong app, key, hai Voice ID, model, tốc độ, thư mục xuất và lựa chọn bài học tự lưu sau 0,7 giây; cũng lưu khi xuất video hoặc đóng app. Có nút **Lưu cấu hình ngay** trong tab ElevenLabs. Key không ghi vào kịch bản hay manifest. `.env` được bỏ qua bởi Git. Có thể cấu hình ban đầu bằng biến môi trường `GEMINI_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_1`, `ELEVENLABS_VOICE_2`.

Gemini và ElevenLabs có thể tính phí/trừ quota theo tài khoản. Tool không tự gửi lại yêu cầu ElevenLabs khi gặp lỗi để tránh tính phí trùng. Nếu timeout, kiểm tra lịch sử sử dụng trước khi thử lại. Voice ID phải khả dụng với tài khoản/API key của bạn.

- 401/403: kiểm tra key/quyền dùng API và giọng.
- 404: kiểm tra model hoặc Voice ID.
- 429: kiểm tra quota và giới hạn yêu cầu.
- Dừng tác vụ: mã hóa dừng nhanh; yêu cầu API đang chạy có thể đợi hết timeout và vẫn có thể tính phí. File `.partial` chưa hoàn tất.

## Kiểm tra

Chạy `.venv\Scripts\python.exe -m unittest -v`.

Đã kiểm tra font chữ Trung, pinyin và tiếng Việt; giao diện; cấu trúc yêu cầu Gemini/ElevenLabs với phản hồi giả lập; pipeline MP4 dùng audio im lặng giả lập, thời lượng phát một lần và giải mã FFmpeg. **Chưa gọi ElevenLabs hoặc Gemini bằng key thật**, nên chưa đánh giá chất lượng phát âm thực tế.

Tài liệu: https://elevenlabs.io/docs/api-reference/text-to-speech/convert và https://ai.google.dev/api/generate-content.

## Cân bằng giọng

Mỗi lượt thoại được chuẩn hóa trên máy bằng FFmpeg loudnorm (mục tiêu -16 LUFS, đỉnh tối đa -1,5 dBTP) trước khi ghép. Hai giọng nhỏ/lớn khác nhau sẽ được cân bằng gần nhau; không cần gọi lại ElevenLabs cho bước chuẩn hóa. Các WAV dùng hậu tố `_balanced_v1` để tránh dùng lại bản chưa cân bằng.


## File trong repo

Repo chỉ chứa mã nguồn, bài mẫu, kiểm thử và icon app. API key (`.env`), môi trường `.venv`, log, video xuất, ảnh kênh và kịch bản riêng được giữ trên máy, không đưa lên GitHub. Có thể tham khảo `.env.example`; cấu hình key trong giao diện app.