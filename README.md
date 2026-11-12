# Mandarin Studio · Podcast Trung–Việt

Tool Windows tạo kịch bản JSON và video podcast có chữ Hán, pinyin, nghĩa Việt. ChatGPT chạy trong tab Microsoft Edge bạn đang đăng nhập. ElevenLabs tạo giọng đọc.

## Luồng sử dụng hiện tại

1. **Có kịch bản JSON rồi:** bấm **Mở JSON**. Nội dung và tên nhân vật trong bài được giữ nguyên.
2. **Tạo bài mới:** nhập chủ đề, trình độ, thời lượng; chọn **Số người nói** từ 1 đến 10. Tool tự đặt nhãn `Người 1`, `Người 2`…; không cần gõ tên nhân vật.
3. Chọn giọng cho từng người bằng dropdown. Dropdown dùng tên gợi nhớ trong kho; nếu chưa đặt tên, hiển thị Voice ID. Có thể dùng cùng một giọng cho nhiều người.
4. Bấm **Tạo kịch bản JSON**. Bước này chỉ viết bài, lưu `lesson.json` và hiện bài trong trình soạn thảo; không gọi TTS, không tạo ảnh, mô tả hoặc bộ đăng. Bấm **Lưu JSON** nếu muốn lưu sang vị trí khác.
5. Khi cần video, bấm **Chọn giọng & xuất MP4…**, duyệt cách gán giọng rồi xuất. Video có SRT; bật Premium để dùng bố cục mới và tùy chọn tối đa 3 Shorts. Các đoạn Shorts lấy nguyên lượt thoại, tối đa 58 giây và không gọi thêm TTS. App không tự tạo thumbnail/bộ đăng trên máy khi xuất video.
6. **Prompt ảnh và bộ đăng:** mở tab **Ảnh & bộ đăng**, bấm **1. Viết prompt ảnh + tên video, tiêu đề, mô tả**. ChatGPT viết tên file video gợi ý, 3 tiêu đề, mô tả và prompt thumbnail; bước này **chưa tạo ảnh**. Tool hiển thị các trường để bạn sửa.
7. Chọn một tiêu đề (hoặc tự sửa), chỉnh mô tả rồi bấm **Gửi tên video, tiêu đề & mô tả lên chat để copy**. Nội dung được trình bày trong chat để bạn sao chép đăng YouTube.
8. Xem/sửa prompt ảnh rồi bấm **2. Tạo ảnh từ prompt trên ChatGPT**. Chỉ lúc này tool mới gửi yêu cầu tạo ảnh. Ảnh nằm trên Edge để bạn tự tải; không tự đăng, không tải ảnh về tool. Nếu bạn chuyển sang chat khác, tool yêu cầu quay lại chat đã viết prompt trước khi gửi tiếp, tránh gán nhầm ngữ cảnh. Tên file video chỉ là gợi ý để copy, không tự đổi tên MP4 đã xuất.

Kịch bản JSON và các trường bộ đăng được giữ riêng. Đổi sang kịch bản khác sẽ xóa bản prompt/bộ đăng cũ trong giao diện để tránh dùng nhầm. Nội dung đang sửa trong tab Ảnh & bộ đăng chỉ giữ trong phiên app; gửi/copy phần cần dùng trước khi đóng tool.

Mức HSK, pinyin, bản dịch và chất lượng giọng cần người dùng xem/nghe lại. Thời lượng là ước lượng, khoảng 210 chữ Hán/phút, không bảo đảm độ dài chính xác.

## Khởi động

Cài Python 3.12 trở lên, chạy `start.bat` để cài thư viện. Chạy `install_shortcuts.ps1` nếu cần icon Desktop/Start Menu. Icon dùng `launch.pyw`, không mở terminal. Lỗi khởi động ghi ở `startup.log`.

Tab **Cấu hình** chọn **ChatGPT Web**. Gemini API vẫn có thể chọn làm dự phòng cho phần kịch bản; nhập key/model trong cấu hình nếu dùng. Không gửi key hoặc mật khẩu vào chat.

## Ghép tab Edge đã đăng nhập

Tool không khởi chạy Chrome/Edge khác, không sao chép hồ sơ và không đọc cookie hoặc mật khẩu. Tích hợp tham khảo kiến trúc [Agent_ads](https://github.com/phuc123asd/Agent_ads), sau đó chuyển sang tiện ích cục bộ để dùng đúng tab Edge hiện tại. Nguồn worker tham khảo ở `agent_ads_chatgpt/UPSTREAM.md`.

1. Cài tiện ích một lần trong Edge: mở `edge://extensions`, bật Developer mode, chọn **Load unpacked**, chọn thư mục `edge_extension` của dự án.
2. Trong tool: **Cấu hình** → **Kết nối Edge hiện tại…** → **Sao chép mã kết nối**.
3. Trên tab ChatGPT đã đăng nhập, mở tiện ích **Mandarin Studio · ChatGPT trên Edge**, dán mã rồi bấm **Kết nối tab này**.
4. Quay lại tool, bấm **Kiểm tra kết nối Edge**. Giữ tool và tab mở trong lúc tạo bài. Chọn model trực tiếp trên ChatGPT. Không trò chuyện khác trong tab khi tool đang gửi yêu cầu.
5. Mã đổi khi khởi động lại tool: dán mã mới để ghép lại, không cần đăng nhập lại nếu phiên ChatGPT còn hiệu lực.

**Sau khi cập nhật tiện ích lên 1.2.0:** tại `edge://extensions`, bấm **Reload / Tải lại** trên tiện ích; làm mới tab ChatGPT rồi kết nối lại. Phiên bản này giữ ngữ cảnh cuộc trò chuyện giữa bước viết prompt, gửi phần chữ để copy và tạo ảnh. Chỉ bản nháp có cấu trúc cần JSON; phần chữ để copy và ảnh được hiển thị bình thường trên chat.

Tiện ích chỉ chạy trong tab được chọn và ghép với server ở `127.0.0.1:8765`. Tool không tự gửi lại khi mất kết nối hoặc timeout. Kiểm tra tab trước khi thử lại. Nếu website yêu cầu xác minh hoặc hết hạn mức, tự xử lý trên website; không bảo đảm Edge luôn tránh được các kiểm tra này.

## Kho 10 giọng

Trong tab **ElevenLabs**, nhập API key và mở **Kho 10 giọng…**. Điền những Voice ID bạn muốn dùng, tối đa 10. Tên gợi nhớ là tùy chọn, không phải tên nhân vật. Cấu hình lưu vào `.env` trên máy:

```dotenv
ELEVENLABS_VOICE_1=your_voice_id
ELEVENLABS_VOICE_1_NAME=Nữ trẻ
ELEVENLABS_VOICE_2=another_voice_id
ELEVENLABS_VOICE_2_NAME=Nam trầm
LESSON_SPEAKER_COUNT=2
VOICE_SPEED=1.0
VOICE_STABILITY=0.35
VOICE_TURN_GAP=0.2
```

Các ô tiếp theo dùng `ELEVENLABS_VOICE_3`…`ELEVENLABS_VOICE_10` và tên `_NAME` tương ứng. Không bắt buộc điền đủ 10 ô. Xem `.env.example`.

Lựa chọn dropdown lưu bằng `LESSON_VOICE_SLOT_1`…`LESSON_VOICE_SLOT_10`. Bài mới lưu cách gán vào `speaker_voices` trong JSON nếu đã chọn giọng hợp lệ. Đổi dropdown trên JSON đang mở cập nhật lựa chọn giọng trong bài mà không đổi lời thoại. Giọng đã lưu trong JSON vẫn có thể dùng dù không nằm trong kho hiện tại.

ElevenLabs nhận chữ Hán và ngữ cảnh trước/sau, không đọc pinyin hoặc bản dịch. Mặc định model `eleven_multilingual_v2`, tốc độ 1.0, độ ổn định 0.35, khoảng nghỉ 0.2 giây giữa lượt, không thêm khoảng nghỉ sau lượt cuối. Có thể chỉnh trong tab ElevenLabs. Tài liệu [Create speech](https://elevenlabs.io/docs/api-reference/text-to-speech/convert).

Mỗi lượt được chuẩn hóa bằng FFmpeg loudnorm, mục tiêu -16 LUFS và đỉnh -1.5 dBTP. Cache `.cache/audio` xét chữ Hán, giọng, model, tốc độ, độ ổn định và ngữ cảnh; thay khoảng nghỉ chỉ cần tạo lại WAV, không gọi TTS. Không tự gửi lại ElevenLabs khi timeout để tránh tính phí trùng. Voice ID phải khả dụng với tài khoản API của bạn.

## Khi xuất bị gián đoạn

Nút **Tiếp tục lần xuất bị gián đoạn…** mở thư mục có `export_job.json` và `lesson.json`, khôi phục thông số xuất gốc rồi dùng lại audio đã xong. Key chỉ lấy từ cấu hình hiện tại; không lưu trong job. Tiến độ được ghi an toàn sau mỗi lượt. Lỗi chi tiết nằm trong `export_job.json` và `task_errors.log`.

Nếu ElevenLabs mất phản hồi sau khi đã nhận yêu cầu, tool tra cứu lịch sử và chỉ tải lại khi có đúng một bản khớp chữ Hán, giọng, model, tốc độ, độ ổn định và khoảng thời gian yêu cầu. Đây là GET audio đã tạo, không gửi lại TTS. Nếu không chứng minh được bản khớp hoặc key thiếu quyền History, tác vụ dừng và giữ dữ liệu để bạn kiểm tra tài khoản; không tự tạo lại đoạn có thể đã trừ credit. Thư mục `assets` có file `.request.json` cho yêu cầu chưa xác định kết quả, không chứa API key.

## Tập cũ và file xuất

**Mở tập cũ để nâng cấp…** nạp `lesson.json`, `manifest.json`, audio trong `assets`. Giữ thông số cũ sẽ dùng lại file phù hợp; bản mới vào thư mục riêng. Audio từ phiên bản cũ có thể giữ nhịp cũ 0.45 giây và độ ổn định 0.5; đổi thông số để chuyển sang đọc có ngữ cảnh mới, có thể phải tạo lại audio.

Bài nháp mới chỉ có `lesson.json`. Xuất video có `video.mp4`, JSON, SRT, chương và audio/ảnh trung gian; Premium có preview và Shorts nếu bật. Không có tự đăng YouTube. Kịch bản theo cấu trúc `title_zh`, `title_vi`, `speakers`, `lines` (`speaker/zh/pinyin/vi`), `vocabulary`; `speaker_voices` là tùy chọn. Cho phép 1–10 người và 1–150 lượt.

`.env`, `.venv`, `.cache`, video xuất, log và kịch bản riêng được Git bỏ qua. Gemini/ElevenLabs có thể tính phí API; ChatGPT dùng hạn mức của tài khoản đã đăng nhập.

## Kiểm thử

Chạy `.venv\Scripts\python.exe -m unittest -v`. Kiểm thử dùng API và phản hồi Edge giả lập; có kiểm tra Tk dropdown, tách JSON/bộ đăng web, cache audio và pipeline MP4/Shorts bằng FFmpeg. Chưa xác nhận luồng website thật sau bản cập nhật tiện ích này.

Kiểm thử giao thức tiện ích: `node --test test_edge_extension.cjs` (Node.js 18 trở lên). Bao gồm trường hợp gửi ảnh một lần, trả ngữ cảnh chat và chặn gửi khi tab đã chuyển sang chat khác.
