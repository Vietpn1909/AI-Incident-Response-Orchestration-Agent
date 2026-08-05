# Báo cáo đánh giá Agent xử lý sự cố

Ngày đo: **05/08/2026** · Người thực hiện: **Phạm Đức Trung**

Mô hình: **Qwen Plus** (`qwen-plus`, temperature `0.2`) · Jira: **FakeJira**

Hệ thống thử nghiệm: 2 service demo, PostgreSQL và Prometheus (chu kỳ scrape 5 giây).

## 1. Phương pháp

Ground truth được lấy từ `docs/use-cases.md`, tài liệu đã chốt ngày 30/07 trước khi viết luật và Agent. Cách chấm top-1:

| Use case | Ground truth khóa trước | Severity mong đợi |
|---|---|---|
| UC-1 | Connection pool giới hạn 5 bị chiếm hết, hoặc truy vấn chậm giữ connection | P2 |
| UC-2 | Container bị OOM-kill do rò rỉ bộ nhớ vượt giới hạn 128 MB | P1 |
| UC-3 | Burst đăng nhập thất bại là vấn đề bảo mật/truy cập bất thường, không phải quá tải | P1 hoặc P2 |

Mỗi UC được tái hiện bằng tải thật và telemetry thật một lần để chụp `IncidentSignal`. Sau đó giữ nguyên snapshot đó và gọi Qwen 10 lần cho UC-1, 8 lần cho UC-2 và 8 lần cho UC-3. Vì vậy đây là **26 lượt suy luận độc lập trên 3 snapshot telemetry**, không phải 26 lần dựng lại sự cố vật lý. Từng câu trả lời được chấm theo ground truth trên và lưu trong `eval/runs.csv`.

## 2. Kết quả chính

### Phát hiện sự cố

| UC | Tín hiệu thật quan sát được | Agent phân loại | Kết quả |
|---|---|---|---|
| UC-1 | p95 = **4,529 giây**, ngưỡng 2 giây | P2 | Đúng |
| UC-2 | Docker restart từ 0 lên 3; Agent bắt tín hiệu 2 restart/10 phút | P1 | Đúng |
| UC-3 | 12.000 request đăng nhập sai trong 60 giây; đỉnh xấp xỉ 200 request/giây | P1 | Đúng |

Độ chính xác severity trên ba lần tái hiện là **3/3 (100%)**. Cả ba incident đều mang theo ít nhất một `MetricEvidence` và câu PromQL, nên độ đầy đủ bằng chứng ở mức incident là **3/3 (100%)**.

### Độ chính xác chẩn đoán nguyên nhân M3 (top-1)

| UC | Đúng / số lượt | Độ chính xác | Confidence quan sát | Nhận xét |
|---|---:|---:|---:|---|
| UC-1 | 10/10 | **100%** | 0,70 | Qwen nêu đúng connection pool cạn |
| UC-2 | 0/8 | **0%** | 0,00 | Chỉ thấy restart và `up=1`, không có metric memory/OOM |
| UC-3 | 0/8 | **0%** | 0,00 | Chỉ thấy tỷ lệ login thất bại; Agent không đủ bằng chứng để kết luận tấn công |
| **Tổng** | **10/26** | **38,46%** | — | Chưa đạt mục tiêu chẩn đoán tổng quát |

Qwen không đoán bừa ở UC-2 và UC-3 mà trả lời “chưa xác định được nguyên nhân gốc”. Điều này an toàn hơn một kết luận sai, nhưng theo tiêu chí M3 vẫn phải chấm **sai** vì top-1 không khớp ground truth.

Thời gian gọi LLM trung bình là **2,854 giây** (nhanh nhất 1,964 giây, chậm nhất 5,013 giây). Trung bình theo UC: UC-1 3,309 giây; UC-2 2,356 giây; UC-3 2,784 giây.

### Thời gian phát hiện, báo nhầm và chống mở trùng

| Chỉ số | Cách đo | Kết quả |
|---|---|---|
| Thời gian phát hiện UC-1 | Từ scrape đầu tiên có p95 > 2 giây đến lúc FakeJira mở incident | **33,434 giây** |
| Báo nhầm | Tải nhẹ 10 phút sau khi baseline đã ổn định | **0 incident / 75 vòng poll (0%)** |
| Chống mở trùng | Giữ UC-1 trong 5 phút, xét 30 vòng poll đầu | **1 incident**: 1 lần mở + 29 lần cập nhật |

Toàn bộ phép thử chống trùng kéo dài 300 giây có 36 vòng poll và vẫn chỉ tạo một incident (1 lần mở, 35 lần cập nhật).

## 3. Phát hiện ngoài dự kiến

Lần chạy tải nhẹ đầu tiên khi Prometheus chưa có baseline ổn định đã mở **1 incident giả**: baseline p95 tạm thời là 0,095 giây trong khi p95 bình thường nằm ở bucket 0,475 giây. Sau khi làm ấm baseline, chạy lại đủ 10 phút cho kết quả 0 incident. Vì vậy kết quả chính thức là 0% sau warm-up, nhưng hệ thống hiện vẫn có rủi ro báo nhầm lúc khởi động lạnh.

## 4. Kết luận và việc cần cải thiện

- Luồng phát hiện, phân loại severity, tạo incident và chống mở trùng hoạt động với cả ba UC.
- UC-1 đã có đủ telemetry để chẩn đoán đúng ổn định.
- UC-2 cần thu thêm container memory, memory limit và sự kiện OOM-kill; nếu chỉ có restart thì không thể chứng minh nguyên nhân OOM.
- UC-3 cần thêm ngữ cảnh bảo mật như IP nguồn, số tài khoản bị thử, phân bố request và mẫu credential-stuffing; một metric 401 đơn lẻ chưa đủ kết luận tấn công.
- Cần thêm cơ chế warm-up hoặc ngưỡng sàn cho baseline để tránh báo nhầm sau khi Prometheus khởi động lại.
- MTTD hiện dùng FakeJira nên chưa bao gồm độ trễ mạng/API Jira thật. Kết quả mới được kiểm chứng trên 2 service, chưa đại diện cho hệ thống hàng chục service.

## 5. Tệp bằng chứng

- `eval/runs.csv`: 26 lượt chẩn đoán và ground truth tương ứng.
- `eval/results/uc1-live.json`, `uc2-live.json`, `uc3-live.json`: incident và telemetry thật.
- `eval/results/false-alarm-warm.json`: phép thử báo nhầm chính thức.
- `eval/results/false-alarm.json`: lần khởi động lạnh có báo nhầm.
- `eval/results/uc1-dedup-5m.json`: phép thử chống mở trùng 5 phút.
