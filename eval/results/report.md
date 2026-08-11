# Báo cáo đánh giá Agent xử lý sự cố

Ngày đo: **05–06/08/2026** · Người thực hiện: **Phạm Đức Trung**

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

Mỗi lượt còn ghi `statement_origin`: `llm` khi câu Qwen được Agent chấp nhận, `rule` khi Agent giữ câu do luật ghép vì Qwen lỗi, bịa nguyên nhân hoặc phủ định bằng chứng. Đây là metadata do `hypothesize_with_origin()` trả trực tiếp, **không** suy đoán bằng việc `reasoning` rỗng.

## 2. Kết quả chính

### Phát hiện sự cố

| UC | Tín hiệu thật quan sát được | Agent phân loại | Kết quả |
|---|---|---|---|
| UC-1 | p95 = **4,529 giây**, ngưỡng 2 giây | P2 | Đúng |
| UC-2 | Docker OOM-kill và restart; đỉnh bộ nhớ **125,9/128 MB** | P1 | Đúng |
| UC-3 | 12.000 request đăng nhập sai trong 60 giây; lúc mở incident là **180,3 request/giây**, 1 IP thử 100 tài khoản | P1 | Đúng |

Độ chính xác severity trên ba lần tái hiện là **3/3 (100%)**. Cả ba incident đều mang theo ít nhất một `MetricEvidence` và câu PromQL, nên độ đầy đủ bằng chứng ở mức incident là **3/3 (100%)**.

### Độ chính xác chẩn đoán nguyên nhân M3 (top-1)

| UC | Đúng / số lượt | Độ chính xác | Câu cuối: LLM / luật | Nhận xét |
|---|---:|---:|---:|---|
| UC-1 | 10/10 | **100%** | 10 / 0 | Qwen nêu đúng connection pool cạn |
| UC-2 | 8/8 | **100%** | 1 / 7 | Chốt giữ kết luận OOM khi Qwen phủ định evidence |
| UC-3 | 3/8 | **37,5%** | 8 / 0 | 5 lượt Qwen gọi đây là quá tải, trái ground truth bảo mật |
| **Tổng** | **21/26** | **80,77%** | 19 / 7 | Không được diễn đạt thành “LLM đạt 80,77%” |

Nguồn câu cho thấy con số Agent và năng lực LLM là hai việc khác nhau. Trong 19 câu Qwen được chấp nhận, 14 câu đúng (**73,68%**); 7 câu do luật giữ lại đều đúng. UC-2 đạt 8/8 nhờ chốt chống phủ định: Qwen chỉ viết được 1 câu đúng, 7 lần còn lại Agent bỏ câu “không có/chưa xác định nguyên nhân” và giữ câu OOM do luật. Ở UC-3, telemetry mới đã đủ (1 IP, 100 tài khoản, tỷ lệ nguồn lớn nhất 100%) nhưng 5/8 câu Qwen vẫn gọi tình huống là “quá tải”; chốt hiện tại chưa bắt dạng sai này, nên không thể báo cáo M3 gần 100%.

Thời gian gọi LLM trung bình là **3,088 giây** (nhanh nhất 2,193 giây, chậm nhất 5,030 giây). Trung bình theo UC: UC-1 3,351 giây; UC-2 3,144 giây; UC-3 2,703 giây.

### Thời gian phát hiện, báo nhầm và chống mở trùng

| Chỉ số | Cách đo | Kết quả |
|---|---|---|
| Thời gian phát hiện UC-1 | Từ scrape đầu tiên có p95 > 2 giây đến lúc FakeJira mở incident | **33,434 giây** |
| Báo nhầm | Tải nhẹ 10 phút sau khi baseline đã ổn định | **0 incident / 75 vòng poll (0%)** |
| Chống mở trùng | Giữ UC-1 trong 5 phút, xét 30 vòng poll đầu | **1 incident**: 1 lần mở + 29 lần cập nhật |

Toàn bộ phép thử chống trùng kéo dài 300 giây có 36 vòng poll và vẫn chỉ tạo một incident (1 lần mở, 35 lần cập nhật).

## 3. Phát hiện ngoài dự kiến

Lần chạy tải nhẹ đầu tiên khi Prometheus chưa có baseline ổn định đã mở **1 incident giả**: baseline p95 tạm thời là 0,095 giây trong khi p95 bình thường nằm ở bucket 0,475 giây. Sau khi làm ấm baseline, chạy lại đủ 10 phút cho kết quả 0 incident. Từ lần đo này, Agent chỉ dùng baseline khi có ít nhất 20 mẫu và Compose giữ lịch sử Prometheus trong named volume; lần dựng hoàn toàn mới vẫn cần warm-up khoảng 30 phút.

## 4. Kết luận và việc cần cải thiện

- Luồng phát hiện, phân loại severity, tạo incident và chống mở trùng hoạt động với cả ba UC.
- UC-1 đã có đủ telemetry để chẩn đoán đúng ổn định.
- UC-2 đạt 8/8 sau khi thêm chốt không cho LLM phủ định một kết luận đã có bằng chứng. Tuy nhiên 7/8 câu đúng đến từ luật, nên đây là cải thiện độ an toàn của **Agent**, không phải bằng chứng Qwen tự chẩn đoán OOM tốt hơn.
- UC-3 đã có đủ telemetry nguồn nhưng chỉ đạt 3/8. Cần bổ sung chốt cho trường hợp Qwen gọi credential-stuffing là “quá tải”, hoặc siết prompt/contract để câu cuối phải phân loại rõ bảo mật so với hiệu năng.
- Prometheus có named volume để giữ baseline qua `docker compose down`; cần chạy warm-up khoảng 30 phút sau lần xoá volume hoặc dựng mới hoàn toàn.
- MTTD hiện dùng FakeJira nên chưa bao gồm độ trễ mạng/API Jira thật. Kết quả mới được kiểm chứng trên 2 service, chưa đại diện cho hệ thống hàng chục service.

## 5. Tệp bằng chứng

- `eval/runs.csv`: 26 lượt chẩn đoán và ground truth tương ứng.
- `eval/results/uc1-live.json`, `uc2-live.json`, `uc3-live.json`: incident và telemetry thật.
- `eval/results/false-alarm-warm.json`: phép thử báo nhầm chính thức.
- `eval/results/false-alarm.json`: lần khởi động lạnh có báo nhầm.
- `eval/results/uc1-dedup-5m.json`: phép thử chống mở trùng 5 phút.
