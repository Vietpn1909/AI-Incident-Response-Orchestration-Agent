# ADR-0003: Tạo sự cố bằng load test thật, không fault injection giả

- **Trạng thái:** Đã chấp nhận
- **Ngày:** 2026-07-28
- **Người quyết định:** Trương Công Thái Đức (lead) + Trung (Backend)

## Bối cảnh

Để demo được Agent ứng phó sự cố, cần có sự cố. Câu hỏi là tạo ra nó bằng cách nào.

Cách nhanh nhất là code một endpoint `POST /admin/inject-fault` rồi trong service thêm `await asyncio.sleep(5)` hoặc `raise HTTPException(500)` khi cờ được bật. Nhưng như vậy thì latency trong biểu đồ là **hằng số do mình gán**, không phải hệ quả của bất cứ điều gì — và Agent "chẩn đoán nguyên nhân" cho một sự cố mà nguyên nhân là `if fault_enabled` thì phần chẩn đoán trở thành trình diễn rỗng.

## Các phương án đã xét

| Phương án | Đánh giá |
|---|---|
| **Fault injection bằng cờ** (`sleep`, `raise`) | Nhanh nhất, điều khiển chính xác thời điểm. Nhưng không có nguyên nhân thật để chẩn đoán, không có hiệu ứng lan truyền tự nhiên, biểu đồ latency là bậc thang chứ không tăng dần |
| **Toxiproxy / chaos tooling** | Tạo được độ trễ mạng, packet loss thật ở tầng network. Nhưng thêm một công cụ phải học, và nguyên nhân vẫn là "có người bật toxic" chứ không phải một điểm yếu trong hệ thống |
| **Load test thật vào hệ thống có nút cổ chai cố ý** | Sự cố là **hệ quả** của tải + thiết kế. Có nguyên nhân thật để tìm, có hiệu ứng dây chuyền tự nhiên, latency tăng dần theo tải nên biểu đồ thuyết phục. Đổi lại: mất công dựng nút cổ chai và cần thời gian chạy tải |

## Quyết định

Dựng **2 service nhỏ phụ thuộc nhau** với nút cổ chai cố ý, rồi tạo sự cố bằng **load test tăng dần**:

- `service-thanh-toan` — `POST /pay`, ghi Postgres thật
- `service-dat-hang` — `POST /orders`, **gọi chéo** sang `service-thanh-toan`
- **Connection pool Postgres giới hạn ở 5** — khi tải cao, request phải xếp hàng chờ connection → latency tăng do nghẽn thật
- Thêm một truy vấn chưa tối ưu (thiếu index) để độ chậm lộ rõ hơn khi tải tăng
- Bảng `orders` / `payments` seed vài nghìn dòng bằng Faker để truy vấn có "trọng lượng"
- **k6 hoặc Locust** tăng tải dần 1.000 → 100.000 request

## Hệ quả

**Tích cực**

- **Có nguyên nhân thật để chẩn đoán.** Chuỗi nhân quả là: tải tăng → pool 5 connection cạn → request xếp hàng → p95 tăng → timeout. Agent tìm ra chuỗi này là chẩn đoán thật, và bằng chứng là số liệu thật.
- **Hiệu ứng lan truyền tự nhiên.** `service-dat-hang` timeout theo vì phụ thuộc `service-thanh-toan` — không cần code thêm gì để mô phỏng. Đây chính là yêu cầu "cảnh báo khi sự cố lan sang dịch vụ khác", và nó xảy ra miễn phí.
- **Biểu đồ thuyết phục.** Latency tăng dần theo tải, không phải nhảy bậc — nhìn là tin.
- Ràng buộc "chẩn đoán có bằng chứng" được thoả một cách thực chất chứ không phải hình thức.

**Tiêu cực & rủi ro**

- **Mất công hơn.** Phải dựng service, seed dữ liệu, viết script tải, và tinh chỉnh để sự cố xảy ra ở mức tải hợp lý.
- **Kém tất định.** Sự cố phụ thuộc máy chạy demo. Trên laptop mạnh có thể phải tải cao hơn mới nghẽn. Giảm thiểu: chốt sẵn mức tải đã kiểm chứng trên máy sẽ dùng để demo, và **quay video dự phòng** trước Demo Day.
- **Demo mất thời gian.** Chạy tải tăng dần cần vài phút. Giảm thiểu: script có sẵn profile `demo` rút gọn, và video demo dùng bản đã tăng tốc.
- Chạy tải lớn trên máy cá nhân có thể nóng máy / ảnh hưởng thao tác khác trong lúc demo.

## Ghi chú khi làm

- Trung cần **đo và ghi lại mức tải làm p95 vượt 2s** trên máy demo, đưa số đó vào `README` của script. Không có số này thì hôm demo phải mò.
- Giữ nguyên phương án fault injection như **đường lùi**: nếu đến tuần 5 mà load test còn bấp bênh, một cờ `SLOW_MODE` để dựng lại nhanh trạng thái sự cố cho video vẫn tốt hơn là không demo được. Đây là phương án dự phòng, không phải phương án chính.
