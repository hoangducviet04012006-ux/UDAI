# BÁO CÁO ĐỢT 6 — CHUẨN HOÁ UX THEO LUỒNG NGHIỆP VỤ (BaoHanhAI)

> **Trạng thái:** ĐÃ THỰC HIỆN XONG — có kiểm chứng regression đầy đủ (68/68 mục kiểm Đợt 6 PASS).
> **Ngày thực hiện:** 28/09/2026 · Kiểm tra bằng đọc code + chạy hệ thống thật (server + API + CSDL thật).
> **Phạm vi thay đổi:** chỉ lớp giao diện (`frontend/index.html`, `frontend/app.js`, `frontend/styles.css`) + tài liệu này.
> **Không thay đổi:** `backend/**`, `tests/**`, `database/**`, `dev.ps1`, `Makefile`, `docker-compose.yml`, API contract,
> BR1–BR4, máy trạng thái phiếu, AI-01. **Không** làm chatbot trong đợt này.
> **Bộ kiểm chứng:** đặt ngoài repository (theo nếp các đợt trước) tại `d:\Nhom06\`.

---

## 1. Mục tiêu

Đợt 6 **không thêm chức năng mới, không sửa nghiệp vụ**. Mục tiêu là *kể lại* toàn bộ hệ thống bằng
**luồng công việc của nhân viên bảo hành**, để người không biết gì về CSDL/API vẫn dùng được.

| # | Mục tiêu | Cách tiếp cận |
|---|---|---|
| 1 | Không lộ "bảng dữ liệu" | Đổi tên màn/nút/cột từ tên thực thể DB sang việc nhân viên làm: `Sản phẩm` → **Danh mục máy**, `Thiết bị` → **Máy đã đăng ký**, `Phân tích lỗi AI` → **Hỗ trợ xác định lỗi** |
| 2 | Menu theo thứ tự công việc | 4 tab việc hằng ngày (Tổng quan → Phiếu bảo hành → Tra cứu → Xác định lỗi) đứng trước, có vạch phân cách, rồi mới tới sổ/danh mục nội bộ |
| 3 | Mỗi màn tự nói mình để làm gì | Thêm 1 câu mô tả dưới tiêu đề + tooltip cho **cả 7** nút điều hướng |
| 4 | Đúng từ ngữ nghiệp vụ | `dòng máy` thay `sản phẩm`; `gợi ý loại lỗi` thay `phân tích`; `số máy đang quản lý` thay `số thiết bị đang quản lý`; tách `tình trạng theo dõi` khỏi `tình trạng bảo hành` |
| 5 | Tách 2 ý dễ lẫn | Cột gộp "Trạng thái hồ sơ" → **Tình trạng bảo hành** (theo hạn) + **Tình trạng theo dõi** (còn/ngừng theo dõi), có tooltip phân biệt |
| 6 | Giảm nhiễu thị giác | Quy tắc nghiệp vụ (BR1–BR4) thu gọn trong `<details>` và đẩy xuống **sau** bảng việc đang làm |

## 2. Baseline Đợt 5 (phải giữ nguyên) và kết quả sau Đợt 6

| Hạng mục | Baseline Đợt 5 | Sau Đợt 6 | Kết luận |
|---|---|---|---|
| `node --check frontend/app.js` | PASS | **PASS** | giữ |
| `.\dev.ps1 check` (minh chứng KT2 + KT3) | 24/24 | **24/24** (KT2 12/12 · KT3 12/12) | giữ |
| `check_dot3_ui.py` (ngôn ngữ + id/handler) | 49/49 | **49/49** | giữ |
| `verify_dot5_ui.py` (Đợt 5, đã cập nhật theo nhãn Đợt 6) | 43/43 | **43/43** | giữ |
| `test_dot5_display.js` (lớp hiển thị) | 26/26 | **26/26** | giữ |
| `verify_dot4_e2e.py` (E2E UI → API → CSDL → UI) | 76 PASS / 0 FAIL | **76 PASS / 0 FAIL** | giữ |
| `verify_dot6_ux.py` (mới của Đợt 6) | — | **68 OK / 0 BAD** | mới |

## 3. Vấn đề phát hiện (audit Đợt 6)

| # | Phát hiện | Mức độ |
|---|---|---|
| A1 | Menu trộn lẫn việc hằng ngày với sổ/danh mục; nhãn tab đặt theo tên bảng dữ liệu (`Sản phẩm`, `Thiết bị`, `Phân tích lỗi AI`) | **Cao** |
| A2 | Không nút điều hướng nào có tooltip giải thích nó dùng khi nào | Trung bình |
| B1 | Màn Tổng quan chỉ là lưới số liệu + bảng phiếu: nhân viên mới không biết bắt đầu từ đâu | **Cao** |
| B2 | Bảng quy tắc nghiệp vụ (BR1–BR4) chiếm chỗ ngay trên màn, lấn át việc đang xử lý | Trung bình |
| C1 | Khối tiếp nhận là form dài 1 màn; nhãn bước nói theo thuật ngữ, chưa nói "máy của ai" / "việc gì" | **Cao** |
| C2 | Chưa nói rõ **máy đã có trong hệ thống** thì chọn nhanh thế nào, máy mới thì đăng ký ra sao | Trung bình |
| D1 | 6 nút lọc theo mã trạng thái chưa dịch & không xếp theo thứ tự quy trình; ô tìm kiếm không nói tìm được gì | Trung bình |
| E1 | Màn Tra cứu chưa giải thích **số sê-ri là gì**; khách không mang máy thì tra thế nào | Trung bình |
| F1 | Bảng Khách hàng chỉ có cột "Mã": thiếu cột đếm nghiệp vụ (đang gửi bao nhiêu máy / có bao nhiêu phiếu) | Trung bình |
| G1 | Danh mục gọi là "sản phẩm" trong khi nhân viên gọi là "dòng máy" | Trung bình |
| G2 | Cột "Trạng thái hồ sơ" gộp 2 nghĩa (còn bảo hành? · còn theo dõi?) thành 1 chữ, dễ hiểu sai | **Cao** |
| G3 | Bảng máy đã đăng ký thiếu cột nghiệp vụ (ngày mua, hạn bảo hành, dòng máy) | Trung bình |
| H1 | `app.js` còn chuỗi hiển thị mang thuật ngữ "phân tích" (nguồn phân tích, lý do phân tích, "chưa có phiếu nào để phân tích") | **Cao** |
| H2 | Không có bộ kiểm nào bảo vệ *thứ tự menu + nhãn nghiệp vụ + tooltip*, cũng chưa có kiểm chứng luồng nghiệp vụ end-to-end bằng API thật | **Cao** |


## 4. Điều hướng: 7 tab theo luồng nghiệp vụ, có thứ tự + tooltip

`frontend/index.html` dòng 51–62 (menu ngang) và 72–84 (menu màn hình nhỏ).

Thứ tự **cố định** cho cả 2 menu — 4 việc hằng ngày, vạch phân cách `.nav-sep`, rồi 3 màn sổ/danh mục:

`Tổng quan` → `Phiếu bảo hành` → `Tra cứu bảo hành` → `Hỗ trợ xác định lỗi` │ `Khách hàng` → `Danh mục máy` → `Máy đã đăng ký`

| Mục kiểm | Nội dung | Kết quả |
|---|---|---|
| A1 | Menu ngang đủ 7 mục **đúng thứ tự** trên | PASS (`['dashboard','tickets','lookup','ai','customers','products','devices']`) |
| A2 | Menu màn hình nhỏ cũng đủ 7 mục, cùng thứ tự | PASS |
| A3 | Mỗi nút điều hướng có `title` giải thích | PASS (7/7 nút) |
| A4 | Luôn có nút hành động chính "Tiếp nhận máy mới" ở thanh trên | PASS |
| A5 | Nhãn tab dùng ngôn ngữ nghiệp vụ | PASS |
| A6 | Không còn nhãn tab cũ `Sản phẩm` / `Thiết bị` / `Phân tích lỗi AI` | PASS |

CSS mới phục vụ việc này (`frontend/styles.css`): `.nav-tab-btn`, `.nav-tab-btn.active`, `.nav-sep`
(vạch chia nhóm tab) và `details > summary` (cho khối quy tắc nghiệp vụ thu gọn).

## 5. Tab "Tổng quan": màn hình bắt đầu + quy trình 4 bước

Màn Tổng quan được viết lại thành **điểm bắt đầu của ca làm việc**, không còn chỉ là bảng điều khiển số liệu.

| Mục kiểm | Nội dung | Kết quả |
|---|---|---|
| B1 | Tiêu đề nói rõ màn đang làm gì ("Tổng quan hoạt động") | PASS |
| B2 | Có mô tả ngắn ý nghĩa số liệu ("Tình hình tiếp nhận và xử lý bảo hành") | PASS |
| B3 | Có khối "Thao tác nhanh" | PASS |
| B4 | Nêu đúng quy trình 4 bước: tiếp nhận máy → xác định loại lỗi → cập nhật tình trạng → trả máy cho khách | PASS |
| B5 | 4 nút thao tác nhanh **đúng thứ tự quy trình** (`receive` → `ticket` → `ai` → `lookup`) | PASS |
| B6 | 4 nút có nhãn đánh số + tooltip | PASS |
| B7 | Có ô tra cứu nhanh ngay trên Tổng quan (`dash-lookup-input`, placeholder "Tra cứu nhanh: nhập số sê-ri hoặc mã phiếu…") | PASS |
| B8 | Có bảng "Phiếu đang xử lý" + lối đi tiếp "Xem tất cả phiếu" | PASS |
| B9 | Quy tắc nghiệp vụ thu gọn trong `<details>` và **đặt sau** bảng phiếu đang xử lý (vị trí 12671 > 12278 ký tự) | PASS |

## 6. Tab "Phiếu bảo hành": khối tiếp nhận 2 bước gọi đúng việc

Khối tiếp nhận nằm **trước** danh sách phiếu (việc chính làm trước) và đặt tên theo việc, không theo thực thể.

| Mục kiểm | Nội dung | Kết quả |
|---|---|---|
| C1 | Khối tiếp nhận đứng trước danh sách phiếu | PASS |
| C2 | Tiêu đề khối + chú thích "Chỉ 2 bước" | PASS |
| C3 | Nhãn bước 1 nói rõ đối tượng: "Bước 1: Máy của khách" | PASS |
| C4 | Nhãn bước 1 ở trạng thái xong: "Bước 1: Máy của khách (xong)" | PASS |
| C5 | Nhãn bước 2 nói rõ việc sẽ làm: "Bước 2: Ghi nhận lỗi & tạo phiếu" | PASS |
| C6 | Nút hành động bước 2 rõ nghĩa | PASS |
| C7 | Nút lưu máy mới ở bước 1 rõ nghĩa ("Lưu thiết bị & tiếp tục") | PASS |
| C8 | Bước 1 hướng dẫn "máy đã có / máy chưa có" + chọn nhanh máy đang có | PASS |
| C9 | Bước 2 nói trước phiếu mới sẽ ở trạng thái nào | PASS |

## 7. Danh sách phiếu: lọc theo trạng thái nghiệp vụ

| Mục kiểm | Nội dung | Kết quả |
|---|---|---|
| D1 | Tiêu đề + mô tả cách làm việc với phiếu | PASS |
| D2 | 6 nút lọc **đúng thứ tự quy trình, đúng tên tiếng Việt**: Tất cả · Đã tiếp nhận · Đang kiểm tra · Đang sửa chữa · Hoàn tất · Từ chối | PASS |
| D3 | Bảng phiếu đủ cột nghiệp vụ (mã phiếu, thiết bị (số sê-ri), khách hàng, trạng thái, ngày tiếp nhận, nhân viên phụ trách, loại lỗi) | PASS |
| D4 | Ô tìm kiếm nói rõ tìm được gì ("Tìm theo mã phiếu / số sê-ri / tên khách hàng") | PASS |

## 8. Tab "Tra cứu bảo hành": một ô nhập cho cả số sê-ri và mã phiếu

| Mục kiểm | Nội dung | Kết quả |
|---|---|---|
| E1 | Có tiêu đề tab | PASS |
| E2 | Giải thích số sê-ri là gì ("in trên tem của máy") | PASS |
| E3 | Nhắc cách tra khi khách không mang máy ("Nếu khách không mang máy, hãy tra theo mã phiếu") | PASS |
| E4 | Có gợi ý chọn nhanh máy đang quản lý ("Thiết bị đang quản lý:") | PASS |
| E5 | Có nút "Tra cứu" + "Xoá kết quả" | PASS |

## 9. Tab "Khách hàng": sổ khách hàng

| Mục kiểm | Nội dung | Kết quả |
|---|---|---|
| F1 | Tiêu đề + mô tả sổ khách hàng | PASS |
| F2 | Cột đếm nghiệp vụ "Số thiết bị" / "Số phiếu"; **không** còn cột mã kỹ thuật | PASS |
| F3 | Có nút thêm khách hàng | PASS |

## 10. Tab "Danh mục máy" + "Máy đã đăng ký": khai báo dòng máy và sổ máy

| Mục kiểm | Nội dung | Kết quả |
|---|---|---|
| G1 | Tiêu đề + mô tả nói rõ khi nào dùng "Danh mục máy" | PASS |
| G2 | Cột danh mục dùng ngôn ngữ nghiệp vụ: Tên máy · Thương hiệu · Nhóm sản phẩm · Thời hạn bảo hành mặc định · **Số máy đang quản lý** | PASS |
| G3 | Nút "Thêm dòng máy" + ô tìm kiếm nói rõ tìm được gì | PASS |
| G4 | Modal khai báo dùng từ "dòng máy" (Tên máy (dòng máy) · Thời hạn bảo hành (tháng) · **Lưu dòng máy**) | PASS |
| G5 | Tiêu đề + mô tả sổ máy ("Mỗi dòng là một máy theo số sê-ri") | PASS |
| G6 | Bảng máy đã đăng ký đủ **8 cột**: Số sê-ri · Dòng máy · Khách hàng · Ngày mua · Hết hạn bảo hành · Tình trạng bảo hành · Tình trạng theo dõi · Thao tác | PASS |
| G7 | Tách rõ 2 cột tình trạng bằng tooltip: "…không phải tình trạng bảo hành" và "…tính theo hạn bảo hành ở cột bên trái" | PASS |
| G8 | Có lối đi sang Tra cứu (không bắt nhớ quy trình) | PASS |
| G9 | Không còn cột mã kỹ thuật trong bảng khách hàng / danh mục máy | PASS |


## 11. Soát chuỗi hiển thị trong `app.js` (nhóm H)

| Mục kiểm | Nội dung | Kết quả |
|---|---|---|
| H1 | Mã chạy dùng "gợi ý loại lỗi", **không còn** "phân tích" trong chuỗi hiển thị | PASS — đếm được **10** chỗ "gợi ý loại lỗi" |
| H2 | Nhãn dữ liệu hệ thống đã đổi sang "dữ liệu trong hệ thống" (không còn "cơ sở dữ liệu") | PASS |
| H3 | Mã kỹ thuật (CSDL · AI-01 · BR1–BR4 · KT2–KT3) chỉ còn ở 2 chỗ **hợp lệ**: hàm làm sạch thẻ `stripTechTags()` và khoá của bảng dịch chuỗi seed (phải khớp nguyên văn chuỗi backend trả về) | PASS |
| H4 | Không còn "Độ tin cậy" / "Mã kết quả" / số dạng `0.xx` (`toFixed(2)`) trong chuỗi hiển thị | PASS |
| H5 | Không còn câu kỹ thuật "kiểm tra backend đã chạy chưa" / "Không kết nối được máy chủ" | PASS |
| H6 | Nút trên tab hỗ trợ dùng nhãn mới: **Gợi ý loại lỗi** · **Xác nhận loại lỗi** · **Không dùng gợi ý** | PASS |
| H7 | Giao diện nhắc rõ kết quả gợi ý **chỉ được ghi vào phiếu sau khi** nhân viên xác nhận | PASS |

Các sửa còn lại của đợt này trong `frontend/app.js` (đều là **chuỗi/hiển thị**, không đổi luồng gọi API):

| Vị trí | Trước | Sau |
|---|---|---|
| bảng nhãn trường dữ liệu (dòng 467) | `provider: "nguồn phân tích"` | `provider: "nguồn gợi ý"` |
| comment chuẩn hoá kết quả | "lý do phân tích" | "lý do gợi ý" |
| comment đầu màn (dòng 2543) | `MÀN HÌNH: PHÂN TÍCH LỖI` | `MÀN HÌNH: GỢI Ý LOẠI LỖI` |
| 2 doc-comment của hàm chuẩn hoá | "phân tích" | "gợi ý loại lỗi" |
| trạng thái rỗng (dòng 2570) | "Chưa có phiếu bảo hành nào **để phân tích**." | "Chưa có phiếu bảo hành nào **để gợi ý loại lỗi**." |

## 12. Bảng đối chiếu nhãn Trước → Sau

| # | Trước Đợt 6 | Sau Đợt 6 | Nơi áp dụng |
|---|---|---|---|
| 1 | tab `Sản phẩm` | **Danh mục máy** | menu + tiêu đề màn |
| 2 | tab `Thiết bị` | **Máy đã đăng ký** | menu + tiêu đề màn |
| 3 | tab `Phân tích lỗi AI` | **Hỗ trợ xác định lỗi** | menu + nút thao tác nhanh số 3 |
| 4 | modal/nút lưu theo từ "sản phẩm" | "dòng máy" (`Thêm dòng máy` · `Tên máy (dòng máy)` · **`Lưu dòng máy`**) | tab Danh mục máy |
| 5 | cột `Số thiết bị đang quản lý` | **`Số máy đang quản lý`** | bảng Danh mục máy |
| 6 | 1 cột `Trạng thái hồ sơ` | **2 cột**: `Tình trạng bảo hành` + `Tình trạng theo dõi` (có tooltip phân biệt) | bảng Máy đã đăng ký |
| 7 | nhãn 2 bước wizard theo thuật ngữ (không còn trong file) | **`Bước 1: Máy của khách`** / **`Bước 2: Ghi nhận lỗi & tạo phiếu`** (+ trạng thái "(xong)") | khối Tiếp nhận máy mới |
| 8 | "phân tích" trong chuỗi hiển thị | **"gợi ý (loại lỗi)"** | `app.js` (10 chỗ) |
| 9 | bảng số liệu + quy tắc BR chiếm chỗ | số liệu → **quy trình 4 bước + 4 nút thao tác nhanh + ô tra cứu nhanh**, quy tắc BR thu gọn `<details>` đặt cuối | tab Tổng quan |

**Không đổi:** mọi tên hàm, id phần tử, endpoint API, payload, thứ tự gọi API, cách tính hạn bảo hành và các điều kiện chặn (BR1–BR4, máy trạng thái).

## 13. Bộ kiểm chứng Đợt 6 (đặt ngoài repository tại `d:\Nhom06\`)

| Script | Vai trò | Kết quả |
|---|---|---|
| `verify_dot6_ux.py` | **Bộ kiểm chính của Đợt 6**: tải file thật + trang `/` qua HTTP, kiểm 9 nhóm A–I (68 mục) | **68 OK / 0 BAD** |
| `dot6_audit_strings.js` | Rà **mọi** chuỗi literal trong `index.html` + `app.js` xem có lộ thuật ngữ kỹ thuật | `index.html`: PASS; `app.js`: 83 chuỗi cần rà lại — xem mục 16 |
| `dot6_dot4_alignment.js` | Đối chiếu nhãn Đợt 6 với bộ kiểm Đợt 4 (phải có / phải không còn) | **Tất cả `[OK]`** (17 phải có · 14 phải không còn · 16 hàm phải có · 9 mục phải không còn) |
| `dot6_probe.js` | Công cụ tra cứu phụ trợ khi rà chuỗi (chỉ đọc) | công cụ, không tính điểm |
| `verify_dot5_ui.py` | **Đã cập nhật**: thêm kỳ vọng nhãn mới (`Lưu dòng máy`, `Tình trạng theo dõi`, `Bước 1: Máy của khách`, `Bước 2: Ghi nhận lỗi`) | **43/43 PASS** |
| `verify_dot4_e2e.py` | **Đã cập nhật**: tên bước wizard + `Số máy đang quản lý` (E2E vẫn kiểm đủ 76 mục) | **76 PASS / 0 FAIL** |

Cách chạy lại (server phải đang chạy ở `127.0.0.1:8014`):

```powershell
cd D:\Nhom06\BaoHanhAI_Project
.\dev.ps1 run                                                  # bật server (cửa sổ khác)
node --check frontend\app.js                                   # PASS
.\dev.ps1 check                                                # 24/24
py -3.12 D:\Nhom06\check_dot3_ui.py                            # 49/49
py -3.12 D:\Nhom06\verify_dot5_ui.py                           # 43/43
node D:\Nhom06\test_dot5_display.js                            # 26/26
py -3.12 D:\Nhom06\verify_dot4_e2e.py                          # 76 PASS
py -3.12 D:\Nhom06\verify_dot6_ux.py                           # 68 OK / 0 BAD
node D:\Nhom06\dot6_dot4_alignment.js                          # tất cả [OK]
```

Nhóm A–I của `verify_dot6_ux.py`: **A** điều hướng (6) · **B** Tổng quan (9) · **C** khối tiếp nhận (9) ·
**D** danh sách phiếu (4) · **E** tra cứu (5) · **F** khách hàng (3) · **G** danh mục máy/máy đã đăng ký (9) ·
**H** soát chuỗi trong `app.js` (7) · **I** luồng nghiệp vụ end-to-end bằng API thật (13).

## 14. Regression — nhật ký chạy lại

| Hạng mục | Kết quả thực tế | Nhật ký |
|---|---|---|
| `node --check frontend/app.js` | exit **0** (PASS) | `out_node_check2.txt` |
| `.\dev.ps1 check` | **24/24 PASS** (KT2 12/12 · KT3 12/12), exit **0** | `out_dev_check2.txt` |
| `check_dot3_ui.py` | **49 PASS / 0 FAIL**, exit **0** | `out_dot3.txt` |
| `verify_dot5_ui.py` | **43 PASS / 0 FAIL**, exit **0** | `out_dot5.txt` |
| `test_dot5_display.js` | **26 PASS / 0 FAIL**, exit **0** | `out_dot5display.txt` |
| `verify_dot4_e2e.py` | **76 PASS / 0 FAIL**, exit **0** | `out_dot4.txt` |
| `verify_dot6_ux.py` | **68 OK / 0 BAD**, exit **0** | `out_dot6b.txt` |
| `dot6_dot4_alignment.js` | tất cả `[OK]` | `out_dot6_align.txt` |
| `dot6_audit_strings.js` | `index.html` PASS | `out_dot6_audit.txt` |

Server kiểm tra trước khi chạy: `GET /health` trả **200** tại `http://127.0.0.1:8014/health`.



## 15. E2E: luồng nghiệp vụ thật bằng API (nhóm I — 13 mục)

Chạy trên server + CSDL thật, đi đúng chuỗi việc của nhân viên và **đối chiếu với nhãn trên giao diện**:

| Mục | Việc đã chạy | Kết quả |
|---|---|---|
| I1 | Bước 1 — thêm khách hàng (nút "Lưu khách hàng") | HTTP **201** |
| I2 | Reload: khách vừa tạo hiện trong sổ khách hàng | PASS |
| I3 | Tab "Danh mục máy" có dòng máy sẵn để chọn khi đăng ký máy | PASS (danh mục có sẵn nhiều dòng máy) |
| I4 | Bước 1 wizard — đăng ký máy mới theo số sê-ri ("Lưu thiết bị & tiếp tục") | HTTP **201** |
| I5 | Tra cứu số sê-ri ra card bảo hành + hạn do backend tính | hạn **2027-02-10** (mua 10/02/2026 + 12 tháng) |
| I6 | Bước 2 wizard — tạo phiếu ở trạng thái "Đã tiếp nhận" | HTTP **201** · `RECEIVED` |
| I7 | Nút "Chuyển sang Đang kiểm tra" chạy đúng quy trình | HTTP **200** |
| I8 | Nút "Gợi ý loại lỗi" trả về gợi ý cho phiếu đang mở | HTTP **201** |
| I8b | **Sau khi gợi ý: phiếu VẪN CHƯA có loại lỗi** (chờ nhân viên xác nhận) | PASS — bất biến AI-01 |
| I9 | Nút "Xác nhận loại lỗi" ghi loại lỗi vào phiếu | PASS — loại lỗi đã ghi |
| I10 | Quy trình 4 bước: Đang kiểm tra → Đang sửa chữa → Hoàn tất | HTTP **200 / 200** |
| I11 | Ô tra cứu dùng chung tra được bằng **mã phiếu** (sau khi hoàn tất) | PASS — mở đúng card phiếu vừa hoàn tất |
| I12 | Tổng quan cập nhật theo luồng vừa chạy | PASS — số phiếu và số hoàn tất tăng đúng theo phiếu vừa tạo |

## 16. Cố ý không làm & giới hạn

| # | Nội dung | Lý do |
|---|---|---|
| 1 | **Không** sửa backend/CSDL/seed/API, không thêm chức năng, **không làm chatbot** | Đợt 6 chỉ chuẩn hoá lớp hiển thị; giữ nguyên hợp đồng API và giữ 24/24 minh chứng KT2+KT3 |
| 2 | Vẫn giữ tên endpoint `/api/v1/products`, `/api/v1/product-instances` | Chỉ đổi **nhãn hiển thị**; đổi đường dẫn API là phá vỡ đối chiếu KT2/KT3 và `tests/**` |
| 3 | 83 chuỗi `[REVIEW]` trong `app.js` do `dot6_audit_strings.js` báo | Đã rà từng chuỗi: **tất cả** là định danh kỹ thuật trong code (đường dẫn `/api/...`, id phần tử như `wiz-serial`, thuộc tính `role`/`serial`/`json` dùng trong hàm/template) hoặc **khoá bảng dịch** (`FIELD_LABELS`, bảng khôi phục dấu, `DISPLAY_TEXT_MAP`). Không chuỗi nào là nhãn người dùng nhìn thấy ⇒ không sửa |
| 4 | Không ẩn/đổi dữ liệu mẫu, không sửa nội dung bản ghi seed | Ngoài phạm vi đợt này (đã xử lý ở Đợt 5 ở mức hiển thị) |
| 5 | Không phân trang/lọc nâng cao, không thiết kế lại visual | Ngoài phạm vi đợt này |
| 6 | Đoạn mã hiển thị dùng từ "kiểm thử" chỉ tồn tại dưới dạng **khoá từ điển** (bảng khôi phục dấu / nhãn trường), không phải câu hiển thị | Kiểm lại bằng H1–H5: mã chạy không còn câu kỹ thuật nào lộ ra giao diện |

## 17. Danh sách file thay đổi

| File | Trước → Sau | Nội dung |
|---|---|---|
| `frontend/index.html` | 894 → **918 dòng** | Menu 7 tab theo thứ tự nghiệp vụ + vạch phân cách + tooltip; Tổng quan có quy trình 4 bước, 4 nút thao tác nhanh, ô tra cứu nhanh, quy tắc BR thu gọn đặt cuối; nhãn 2 bước wizard; lọc phiếu theo thứ tự quy trình; cột đếm cho sổ khách hàng; bảng máy đã đăng ký 8 cột (tách 2 cột tình trạng) |
| `frontend/app.js` | 3.006 → **3.021 dòng** | Chuỗi hiển thị chuyển từ "phân tích" sang **"gợi ý loại lỗi"** (10 chỗ), "nguồn gợi ý", trạng thái rỗng của màn hỗ trợ, tên màn trong comment; giữ nguyên toàn bộ luồng gọi API |
| `frontend/styles.css` | 242 → **252 dòng** | Thêm `.nav-tab-btn` (+`.active`), `.nav-sep` và style `details > summary` cho khối thu gọn |
| `docs/BAO_CAO_DOT_6_UX.md` | **Mới** | Tài liệu này |
| `backend/**`, `tests/**`, `database/**`, `dev.ps1`, `Makefile`, `docker-compose.yml`, `frontend/README.md` | **Không đổi** | — |
| Ngoài repo (`d:\Nhom06\`): `verify_dot6_ux.py` (mới), `dot6_audit_strings.js`, `dot6_dot4_alignment.js`, `dot6_probe.js` (mới) | — | Bộ kiểm chứng Đợt 6 |
| Ngoài repo (`d:\Nhom06\`): `verify_dot5_ui.py`, `verify_dot4_e2e.py` | — | Cập nhật kỳ vọng nhãn sang Đợt 6 (số lượng mục kiểm không đổi: 43 và 76) |

### Tổng kết số lỗi

| Loại | Số lượng |
|---|---|
| Vấn đề phát hiện trong audit (mục 3) | **14** (A1–A2, B1–B2, C1–C2, D1, E1, F1, G1–G3, H1–H2) |
| Đã sửa trong frontend (mục 4–12) | **14/14** |
| Hạng mục cố ý không làm / ngoài phạm vi | **6** (mục 16) |
| Mục kiểm Đợt 6 đã chạy và PASS | **68/68** |

---

**Kết luận:** ĐỢT 6 HOÀN THÀNH — toàn bộ màn hình dữ liệu/kỹ thuật đã được kể lại thành **luồng công việc của nhân viên bảo hành**
(menu theo thứ tự công việc, mỗi màn nói rõ mình để làm gì, nhãn dùng từ ngữ nghiệp vụ, không còn thuật ngữ CSDL/API/AI nội bộ).
Regression **không suy giảm**: `node --check` PASS · **24/24** minh chứng KT2+KT3 · **49/49** UI Đợt 3 · **43/43** UI Đợt 5 ·
**26/26** lớp hiển thị · **76/76** E2E Đợt 4 · **68/68** bộ kiểm Đợt 6, kèm 13 mục E2E luồng nghiệp vụ thật.

