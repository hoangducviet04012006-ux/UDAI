# Cải tiến hội thoại chatbot BaoHanhAI

Ngày: 28/10/2026. Cập nhật trên adapter, router, nguồn hướng dẫn và cơ chế xác minh hiện có; không tạo chatbot hoặc bộ biến môi trường mới. Giữ thay đổi chưa commit; không push/merge, không reset/seed database đang dùng.

## Trải nghiệm

- Lời mở đầu: “Bạn cần tra tiến độ, hỏi về bảo hành hay hướng dẫn sử dụng?”. Khách và nhân viên có bộ gợi ý phù hợp; gợi ý ẩn sau lần chọn/gửi đầu tiên.
- Khách hỏi tiến độ chưa xác minh: mở form ngay trong chat, giữ câu hỏi. Xác minh thành công hiển thị thẻ mã phiếu/trạng thái và tự tiếp tục câu hỏi, không yêu cầu gửi lại. Mã bí mật chỉ nhập ô riêng, được xóa khỏi ô ngay khi gửi; không đưa vào tin nhắn/URL/minh chứng.
- Nhân viên chọn Hỏi về phiếu này: có sẵn thẻ phiếu được backend kiểm tra quyền. Đổi phiếu hoặc hội thoại mới xóa transcript cũ.
- Hỏi trạng thái chỉ nhận trạng thái và phần chưa biết cần thiết. Hỏi hạn bảo hành dùng ngày hiện tại Việt Nam và hạn đã lưu. Lịch sử chỉ được đưa vào khi hỏi lịch sử/tóm tắt.
- Có Đang trả lời…, Hủy chờ, Thử lại. Giữ câu nhập khi lỗi/hủy. Enter gửi, Shift+Enter xuống dòng, Escape đóng. Bộ đếm hội thoại và lần gửi loại phản hồi cũ sau hủy, hội thoại mới, đổi tài khoản.
- Cửa sổ vẫn dùng textContent cho mọi nội dung động. CSS di động giảm phần trống, giới hạn chiều cao form theo viewport, ẩn nút nổi khi mở chat/phiếu/hộp thao tác và dành khoảng trống cuối nội dung nghiệp vụ.

## AI diễn đạt và dữ liệu gửi đi

Dùng OpenAICompatibleProvider hiện có, bổ sung compose_support, verify_support và hỗ trợ history ở plan_support. Luồng:

1. Xác thực phiên, kiểm tra trung tâm/vai trò/phiếu được giao hoặc mã khách còn hiệu lực; đọc dữ liệu hiện tại trước khi gọi mô hình.
2. Lọc câu hỏi, lấy lịch sử ngắn đã lọc trong phiên; hiểu ý định và trọng tâm hỏi.
3. Backend tự lấy đoạn hướng dẫn đã duyệt hoặc tạo evidence từ các trường cấu trúc cho phép.
4. Mô hình diễn đạt tiếng Việt, xưng mình/bạn, khoảng 2–5 câu; chỉ trả phần liên quan BaoHanhAI/bảo hành.
5. Backend kiểm tra cấu trúc, mã nguồn căn cứ, số/ngày, HTML/URL/JSON, mẫu bí mật, tên riêng không có trong nguồn và một số mâu thuẫn trạng thái/điều kiện. Thêm lượt kiểm chứng ngữ nghĩa so candidate với evidence hiện tại.
6. Kiểm tra lại phiên/quyền và đọc lại phiếu. Dữ kiện vừa đổi thì dùng câu ngắn theo dữ kiện mới. Câu mô hình không được nguồn hỗ trợ thì dùng câu dữ kiện xác thực, nói rõ giới hạn. Lỗi kết nối/timeout trả lỗi để thử lại, không đổi sang mô phỏng.

Dữ liệu trong prompt: câu hỏi đã lọc; tối đa ba cặp hội thoại; intent; một đoạn hướng dẫn hoặc các dữ kiện tối thiểu cho trọng tâm hỏi. Ví dụ câu tiến độ chỉ có mô tả trạng thái hiện tại và việc chưa có ngày hẹn được xác nhận; câu hạn bảo hành chỉ có ngày hết hạn và kết quả đối chiếu ngày hiện tại. Lịch sử tối đa sáu mốc cấu trúc, không có ghi chú.

Không đưa bản ghi khách hàng/tài khoản, tên khách/KTV, số điện thoại/email/địa chỉ từ phiếu, serial, mã phiếu, token đăng nhập, capability phiên, mã tra cứu hoặc ghi chú nội bộ vào evidence. Câu hỏi được lọc điện thoại/email/dãy dài, các thông tin cá nhân biết từ phiếu, mã/serial và mẫu khai báo danh tính; nội dung tự do vẫn là dữ liệu không đáng tin. Thẻ mã phiếu và căn cứ hiển thị do backend dựng riêng, không cần gửi mã cho mô hình. Mô hình không có công cụ SQL, shell, URL, gửi tin hay sửa nghiệp vụ.

Kiểm chứng ngữ nghĩa bằng mô hình là lớp hạn chế sai sót, không phải bằng chứng tuyệt đối về tính đúng. Phân quyền độc lập ở backend, dữ liệu tối thiểu và kiểm tra lại dữ liệu vẫn là các ràng buộc bắt buộc. Chất lượng diễn đạt/kiểm chứng của dịch vụ thật chưa được đánh giá khi chưa có khóa.

## Ngữ cảnh và giới hạn

Lịch sử ở RAM theo khóa phiên đã băm, tối đa sáu tin và 3.000 ký tự, mỗi tin tối đa 700 ký tự; còn cắt theo CHATBOT_MAX_CONTEXT_CHARS sau khi trừ câu hỏi/evidence. TTL 30 phút, tối đa 2.000 ngữ cảnh trong tiến trình. Không ghi transcript vào database; ChatMessage vẫn chỉ ghi băm request_id chống gửi lặp. ChatSession tiếp tục giữ thông tin phiên/ràng buộc quyền và ý định rút gọn để tương thích.

Ngữ cảnh xóa khi đóng, xác minh lại/thất bại, đổi phiếu, gặp 401/403/404, hội thoại mới hoặc đổi tài khoản. Mỗi lượt vẫn đọc dữ liệu mới và kiểm tra quyền; lịch sử không cấp quyền và không phải nguồn trạng thái hiện tại. Kiểm tra lại sau khi mô hình trả lời chặn trường hợp mất quyền/đóng phiên/thu hồi mã trong lúc chờ.

Hủy chờ dùng AbortController ở client và /cancel ràng buộc phiên/request_id ở backend. Lượt đã hủy không được thêm vào lịch sử hay ghi kết quả thành công. Lệnh HTTP đang chạy tới AI có thể tiếp tục đến timeout của nó; hủy không bảo đảm nhà cung cấp hủy tính phí. Tổng thời gian ba bước AI chia cùng ngân sách tối đa min(AI_TIMEOUT_SECONDS, 30 giây), tối đa 100 + 450 + 30 token đầu ra. Các giới hạn đầu vào 1.500 ký tự, tối đa 20 lượt, rate limit và thử sai mã được giữ nguyên. RAM/cancel/rate limit hiện phù hợp một tiến trình; chưa triển khai shared store cho nhiều worker.

## Cấu hình

Đã kiểm tra local chỉ hiển thị tên chế độ/có khóa hay chưa, không in khóa: CHATBOT_PROVIDER=mock, chưa có AI_API_KEY/OPENAI_API_KEY, timeout 30 giây.

AI thật dùng cấu hình đã có: CHATBOT_PROVIDER=openai_compatible và AI_API_KEY hoặc OPENAI_API_KEY; AI_MODEL/AI_BASE_URL theo dịch vụ đang dùng. Không gửi khóa vào chat. CHATBOT_MAX_CONTEXT_CHARS hiện được áp dụng cùng CHATBOT_MAX_TURNS. Không thêm server/dependency; tiếp tục chạy start.bat. Mô phỏng ghi rõ Chế độ mô phỏng, có quy tắc cho không dấu/viết tắt/lỗi gõ phổ biến nhưng chỉ dùng thử giao diện, không đại diện khả năng hiểu ngôn ngữ của AI thật.

## Kiểm thử

```powershell
backend/.venv/Scripts/python.exe -W ignore tests/test_support_chatbot.py
backend/.venv/Scripts/python.exe -W ignore tests/test_refactored_workflow.py
node --check frontend/support.js
```

Kết quả: 20/20 nhóm chatbot PASS, 36/36 ca hồi quy nghiệp vụ PASS, cú pháp JS PASS. Database chatbot được tạo trong thư mục temp với DATABASE_URL đặt trước import; hồi quy dùng database/test_temporary.db. Không chạy migration/reset/seed trên database đang dùng trong lần cải tiến này.

Các ca mới: câu không dấu/tt/bh/dc/lỗi gõ và nối tiếp; câu hỏi tiến độ không kể toàn bộ lịch sử; prompt dữ kiện tối thiểu không chứa PII/serial/mã/token; lịch sử có giới hạn và xóa khi đổi phiếu; mô hình bịa sửa xong/ngày hẹn/giấy tờ/miễn phí/HTML/JSON/tên riêng bị bỏ; verifier từ chối; lỗi kết nối bước diễn đạt trả 502; trạng thái đổi trong lúc diễn đạt dùng dữ liệu mới; hủy trong lúc diễn đạt không commit và không vào ngữ cảnh mới. Quyền khách, hai KTV, quản lý, tiếp nhận, trung tâm khác, mã sai/đổi/thu hồi/hết hạn, đóng/đổi phiên và hai luồng nghiệp vụ tiếp tục đạt.

Phân biệt phương pháp: compose/verify/planner trong test được giả lập có kiểm tra payload; không gọi mô hình thật. Trình duyệt dùng server riêng cổng 8093 và dataset giả tự tạo. Tùy chọn --ui-faults chỉ nằm trong tests/run_support_server.py, mô phỏng lần lỗi kết nối và độ trễ bốn giây cho câu tiến độ; không có trong ứng dụng sản phẩm.

Đã kiểm tra trực tiếp bằng trình duyệt: lời mở đầu/gợi ý thu gọn; lỗi giữ câu nhập và thử lại; hủy rồi hội thoại mới; phản hồi đến trễ không trộn vào hội thoại mới; nhân viên mở ngữ cảnh phiếu; cấp mã thử và xác minh trong khung chat; tự tiếp tục câu hỏi và thẻ phiếu. Mã thử chỉ giữ trong bộ nhớ công cụ khi chuyển giữa hai form, xóa sau sử dụng, không in vào output hoặc ảnh.

Ảnh desktop (mô phỏng, không phải bằng chứng AI thật): screenshots/support_natural_verified.png và screenshots/support_natural_desktop.png.

Chưa xác minh: AI thật và chất lượng diễn đạt/entailment thực tế; kiểm thử điện thoại của bản cập nhật này vì API viewport không thay đổi kích thước trang (DOM vẫn báo 1280×720 dù yêu cầu 390×844); nhiều worker; trình đọc màn hình; các trình duyệt khác. Ảnh support_mobile.png thuộc bản đầu, không dùng làm minh chứng responsive bản cập nhật.

## File lần cải tiến

- backend/app/services/ai_error_classifier.py: dùng adapter hiện có để hiểu ý định với history, diễn đạt và kiểm chứng.
- backend/app/routers/chatbot.py: chọn evidence tối thiểu, kiểm tra lại quyền/dữ liệu, card, needs_verification, hủy và history trong phiên.
- backend/app/services/support_conversation.py: mới, quản lý RAM có giới hạn, lọc dữ liệu và kiểm tra đầu ra.
- frontend/support.js, frontend/support.css: trải nghiệm xác minh/tiếp tục/hủy/thử lại/card và bố cục.
- tests/test_support_chatbot.py, tests/run_support_server.py: kiểm thử mở rộng và lỗi/độ trễ giả lập cho UI.
- backend/app/config.py, backend/.env.example: chú thích cập nhật cho cấu hình đang được dùng, không đổi .env thật.
- README.md, docs/evidence/BAO_CAO_CHATBOT.md và báo cáo này: hướng dẫn và phân biệt tài liệu bản đầu với bản mới.
- Hai ảnh support_natural_verified.png, support_natural_desktop.png.

Không thêm migration/model/schema nghiệp vụ trong lần cải tiến. Không commit/push/merge, không thay đổi mật khẩu dữ liệu đang dùng.
