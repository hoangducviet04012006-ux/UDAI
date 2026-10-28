# Bàn giao chatbot hỗ trợ BaoHanhAI

> Báo cáo bản đầu. Các phần về trả lời mẫu và chỉ lưu ý định đã được thay thế bởi [cập nhật hội thoại tự nhiên](BAO_CAO_CHATBOT_HOI_THOAI.md).

Ngày kiểm tra: 28/10/2026. Thay đổi để nguyên chưa commit; không push/merge, reset/seed hoặc đổi mật khẩu database đang dùng.

## Chức năng đã triển khai

- Trang khách hàng `/support` tách khỏi giao diện quản trị, hỏi hướng dẫn không cần đăng nhập.
- Nút Hỗ trợ góc phải, không tự mở/phát âm thanh; tiêu đề Trợ lý bảo hành, bốn gợi ý, đóng/mở, hội thoại mới, sao chép, thử lại, trạng thái chờ/lỗi. Enter gửi, Shift+Enter xuống dòng, Escape đóng; nội dung động hiển thị bằng textContent.
- Tra cứu trạng thái, hạn bảo hành, mốc xử lý; tóm tắt trích xuất mốc xử lý của phiếu và soạn bản nháp thông báo theo dữ liệu hiện tại. Không cam kết thời hạn/kết quả. Không gửi thông báo ra ngoài.
- Nhân viên mở chi tiết phiếu → Hỏi về phiếu này. Quầy tiếp nhận/quản lý cấp hoặc đổi mã tra cứu ngay trong chi tiết phiếu sau khi tiếp nhận và giao riêng cho khách; mã chỉ hiện một lần. Có nút thu hồi. Không tự gửi mã qua SMS/OTP.
- Khách nhập mã phiếu + mã bí mật tại ô xác minh riêng; không đưa mã vào URL hoặc nội dung hội thoại. Mã ngẫu nhiên 256 bit, lưu SHA-256, hiệu lực truy cập 30 ngày; đổi/thu hồi làm phiên khách đã xác minh mất quyền ở lần tra cứu kế tiếp. Đây là thời hạn mã truy cập, không phải thời hạn bảo hành.

## Skill và code tận dụng

Đã kiểm tra skill cá nhân, workspace và thư mục cha, tìm thấy và đọc:
- `D:/Nhom06/.agents/skills/langchain-rag/SKILL.md`
- `D:/Nhom06/.agents/skills/rag-implementation/SKILL.md`

Áp dụng nguồn tài liệu cho phép rõ ràng, chia theo mục, metadata/căn cứ, truy hồi mục phù hợp và tách truy hồi khỏi trả lời. Bản đầu chọn mục theo ý định ngữ nghĩa, không xây thêm vector database hoặc cài bộ dependency LangChain nặng; không tuyên bố đang dùng LangGraph/vector search.

Tận dụng cấu hình Settings, OpenAICompatibleProvider (thêm phương thức hiểu ý định hội thoại), sanitize_pii, xác thực/thu hồi token hiện tại, apply_ticket_scope_filter, nhãn trạng thái, model ChatSession và ChatMessage đã có. Chỉ thêm bảng ticket_lookup_credentials cho mã truy cập khách. Các chức năng AI phân loại/tóm tắt/soạn tin cũ vẫn giữ nguyên API; chatbot dùng bản tóm tắt trích xuất và mẫu thông báo an toàn, không gọi các API AI cũ vốn có phạm vi dữ liệu rộng hơn.

## Kiến thức và giới hạn phạm vi

Nguồn duy nhất được nạp là `docs/SUPPORT_KNOWLEDGE.md`, chia năm mục: cách sử dụng, tiếp nhận, quy trình, chính sách, mô tả lỗi. Nội dung đối chiếu trực tiếp với warranty_rules.py, crud/warranty_tickets.py, ticket_view.py và giao diện hiện hành. Báo cáo BAO_CAO_NGHIEP_VU_PHIEU_BAO_HANH.md còn có mô tả WAITING_RETURN cũ nên không được nạp. Không quét mã nguồn, .env, backup hoặc log vào kho kiến thức.

Không có tài liệu chính sách đầy đủ được xác nhận về phí/thời gian sửa/đổi mới: chatbot nói chưa có thông tin. Trạng thái, KTV, lịch sử, hạn bảo hành luôn đọc database trong request đã kiểm tra quyền; không gửi hồ sơ phiếu, ghi chú lỗi/chẩn đoán, khách hàng hay mã bí mật vào mô hình.

AI thật chỉ trả một schema đóng gồm ý định và mục hướng dẫn. Backend kiểm tra schema rồi tự dựng câu trả lời từ tài liệu hoặc các trường dữ liệu cho phép; không hiển thị văn bản tự do của mô hình. Không có tool chạy SQL/shell/URL hoặc sửa nghiệp vụ. Yêu cầu lộ bí mật/giả vai trò không thể mở rộng quyền dù mô hình phân loại sai. Câu ngoài phạm vi có câu trả lời đúng mẫu yêu cầu. Câu hỗn hợp thông thường chỉ trả phần hỗ trợ; ý định trước được lưu để hiểu câu nối tiếp. Mô tả lỗi và ghi chú lịch sử tự do không được dùng như chỉ dẫn hoặc nội dung trả cho khách.

Mô phỏng dùng bộ quy tắc có trạng thái và mẫu cố định, có giới hạn hiểu ngôn ngữ. Chế độ AI thật dùng mô hình hiểu ngữ nghĩa, không dùng bộ lọc từ khóa làm cơ chế duy nhất. Không xem các test giả lập AI là bằng chứng chất lượng hiểu ngôn ngữ của mô hình thật.

## Quyền và phiên

- Danh tính đọc từ bearer token và database, không nhận role/user_id từ payload; schema từ chối trường lạ.
- Quản lý/tiếp nhận: đúng trung tâm; KTV: đúng trung tâm và phiếu được giao; tài khoản không có trung tâm bị từ chối. Không truy vấn toàn bộ khách hàng/tài khoản.
- Khách chỉ được xem đúng phiếu đã xác minh, không được xem các phiếu khác cùng số điện thoại/serial/khách hàng. Đầu ra công khai chỉ có thiết bị, trạng thái, mốc xử lý, hạn bảo hành, bản nháp thông báo; không có số điện thoại/tên khách, serial, ghi chú nội bộ hoặc KTV.
- Hội thoại có capability ngẫu nhiên, lưu dạng băm rút gọn 120 bit ở session_code, ràng buộc cả người dùng và phiên đăng nhập cụ thể; hết hiệu lực sau 30 phút hoặc khi đóng. Token nhân viên được xác minh lại ở mỗi request và sau khi gọi AI; đăng xuất, khóa tài khoản, đổi tài khoản không tái dùng ngữ cảnh cũ.
- Capability chỉ giữ trong bộ nhớ trình duyệt; nội dung hội thoại không lưu database. ChatMessage chỉ lưu băm request_id phục vụ chống gửi lặp; ChatSession lưu ý định rút gọn. Cache-Control no-store áp dụng API chatbot.
- 1.500 ký tự/câu, tối đa 20 lượt (hoặc CHATBOT_MAX_TURNS thấp hơn), ngữ cảnh chỉ là ý định trước, timeout AI tối đa 30 giây/client 35 giây; 20 yêu cầu/phút/IP, xác minh 5 lần/5 phút/IP, cấp mã 10 lần/phút/IP. Có khóa chống gửi đồng thời và request_id chống gửi lặp. Lỗi AI không tiêu thụ lượt thành công.

## Cấu hình và khởi động

Local hiện tại: CHATBOT_ENABLED=True, CHATBOT_PROVIDER=mock, chưa có khóa AI. Giao diện ghi Chế độ mô phỏng.

AI thật: cấu hình local `CHATBOT_PROVIDER=openai_compatible`, `AI_API_KEY` hoặc `OPENAI_API_KEY`, cùng `AI_MODEL`, `AI_BASE_URL` phù hợp dịch vụ đang dùng; tùy chọn `AI_TIMEOUT_SECONDS`. Thiếu khóa trả 503 nêu đúng biến; timeout trả 504; kết nối/đầu ra không hợp lệ trả 502. Không tự fallback mô phỏng. Không gửi khóa vào chat.

Vẫn chạy cả hệ thống bằng start.bat; router và static dùng chung FastAPI, không thêm server riêng. start.bat kiểm tra thêm httpx vốn đã có trong requirements.txt. Mở `/support` trên cùng host/cổng của hệ thống, mặc định `http://127.0.0.1:8000/support`.

Trước khi thêm bảng mã truy cập trên SQLite đã có dữ liệu, launcher/lifespan tự sao lưu bằng SQLite online backup API vào thư mục backup cạnh database, bao gồm dữ liệu WAL đã commit. Nếu sao lưu lỗi, startup không tiếp tục thêm schema hỗ trợ. Không chạy migration trên database thật trong phiên làm việc này. File PostgreSQL có DDL bổ sung; sao lưu/triển khai PostgreSQL chưa thực hiện.

Các biến embedding/vector/KB_DIR/prompt còn trong Settings từ nền tảng trước chưa được bản này sử dụng; không thể tắt xác minh bằng CHATBOT_REQUIRE_OWNER_VERIFICATION.

## Kiểm thử và minh chứng

Lệnh chạy từ gốc dự án:

```powershell
backend/.venv/Scripts/python.exe -W ignore tests/test_support_chatbot.py
backend/.venv/Scripts/python.exe -W ignore tests/test_refactored_workflow.py
node --check frontend/support.js
```

Kết quả: 13/13 nhóm chatbot PASS, 36/36 ca hồi quy nghiệp vụ PASS, kiểm tra cú pháp JS PASS.

13 nhóm bao phủ: phạm vi/ngoài phạm vi/hỗn hợp/nối tiếp; chính sách chưa biết; chưa xác minh/mã sai/đổi/thu hồi/hết hạn; cách ly phiên khách và phiếu khác; quản lý/tiếp nhận/hai KTV/trung tâm khác/không có trung tâm; injection trực tiếp và dữ liệu độc hại; tra cứu/tóm tắt/bản nháp không đổi dữ liệu nghiệp vụ; dữ liệu mới được đọc lại; thiếu khóa/lỗi/timeout/schema AI sai (mock lỗi); đổi tài khoản/đăng xuất/đóng phiên; độ dài/rate limit/gửi lặp; gửi đồng thời và đóng khi AI đang chạy; sao lưu schema với dữ liệu thử. Bộ 36 ca xác nhận cả luồng sửa chữa và từ chối rồi trả máy còn hoạt động.

Database chatbot nằm trong thư mục temp hệ điều hành, DATABASE_URL được đặt trước khi import app. Bộ hồi quy dùng database/test_temporary.db riêng. Server trình duyệt kiểm thử dùng dataset tự tạo ở temp, cổng 8093, không copy database thật hoặc backup thật. Tài khoản kiểm thử chỉ tồn tại trong dataset này.

Đã kiểm tra trực tiếp bằng trình duyệt: hướng dẫn công khai; câu nối tiếp “bao lâu?” bằng Enter; từ chối bóng đá; tra cứu chưa xác minh; hội thoại mới; mở chi tiết phiếu và Hỏi về phiếu này; tra cứu đúng phiếu/KTV; đăng xuất xóa ngữ cảnh; màn hình 390×844 không tràn ngang. Đã sửa lỗi gắn nút vào vùng DOM bị render lại và lỗi style làm tràn khung chat trên điện thoại.

Ảnh (không chứa mã tra cứu bí mật):
- screenshots/support_public.png
- screenshots/support_staff.png
- screenshots/support_mobile.png

Chưa xác minh: kết nối/hiểu ngôn ngữ với AI thật do chưa có khóa; PostgreSQL; nhiều worker/process; trình đọc màn hình; clipboard trên các trình duyệt khác; bấm cấp/nhập mã thật xuyên suốt bằng trình duyệt (đã kiểm bằng API). Không chạy start.bat trên database thật để tránh tự migration dữ liệu đang dùng. Rate limit, khóa đồng thời và danh sách thu hồi token hiện có thuộc một tiến trình; nếu triển khai nhiều worker cần shared store/DB atomic locking trước khi mở rộng.

## File của lần triển khai này

Tạo mới:
- backend/app/routers/chatbot.py
- backend/app/services/support_schema.py
- frontend/support.html
- frontend/support.js
- frontend/support.css
- docs/SUPPORT_KNOWLEDGE.md
- docs/evidence/BAO_CAO_CHATBOT.md
- docs/evidence/screenshots/support_public.png
- docs/evidence/screenshots/support_staff.png
- docs/evidence/screenshots/support_mobile.png
- tests/test_support_chatbot.py
- tests/run_support_server.py

Sửa bổ sung, giữ thay đổi chưa commit đã có:
- backend/app/main.py (router, trang công khai, cache, backup trước schema)
- backend/app/models.py (TicketLookupCredential)
- backend/app/services/ai_error_classifier.py (plan_support trong adapter hiện có)
- backend/app/config.py (chú thích các biến nền tảng chưa dùng)
- backend/app/launcher.py (backup trước bước chuẩn bị schema)
- frontend/index.html (nạp CSS/JS hỗ trợ)
- frontend/app.js (xóa ngữ cảnh khi xóa phiên)
- database/postgres_schema.sql (DDL bổ sung)
- .env.example, backend/.env.example (hướng dẫn cấu hình)
- start.bat (kiểm tra dependency httpx)
- README.md (cách dùng và liên kết bàn giao)

Không gộp các thay đổi có sẵn khác vào danh sách triển khai chatbot.
