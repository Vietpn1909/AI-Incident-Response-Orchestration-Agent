# `eval/` — Đo đạc chất lượng Agent

**Chủ sở hữu: Trung** · Deliverable **#10**

Mentor đã nhấn mạnh chính chỗ này: *"khi làm bài toán AI, vấn đề đo đạc như thế nào — cần phải clear, cần đo đạc cụ thể"*. Đây là câu trả lời.

## Hai họ metric — đừng lẫn vào nhau

### Họ A — metric của sự cố (hệ thống)

Đo được sẵn qua Prometheus, chỉ cần ghi lại có hệ thống:

| Metric | Bình thường | Lúc sự cố | Lấy từ |
|---|---|---|---|
| p95 latency | ~0.2s | > 2s | PromQL `P95_LATENCY` |
| Tỷ lệ lỗi 5xx | < 0.1% | > 10% | PromQL `ERROR_RATE` |
| Pool sử dụng | ~35% | 100% | PromQL `POOL_SATURATION` |
| Tỷ lệ timeout | 0% | tăng | đếm 504 ở `service-dat-hang` |

⚠️ **Không đo "độ mất gói tin".** Đó là metric tầng mạng; hệ thống này là HTTP giữa các container nên không có mất gói để đo. Tương đương ở tầng HTTP là **tỷ lệ timeout** và **connection error** — đo được thật. Bịa số packet loss là làm sai số liệu.

### Họ B — metric chất lượng Agent (đây mới là "đo AI")

Đo được **chính xác** vì mình tự tạo sự cố nên biết trước đáp án đúng:

| Metric | Định nghĩa | Cách lấy |
|---|---|---|
| **MTTD** | Từ lúc sự cố bắt đầu → Agent mở war room | `t(p95 vượt ngưỡng)` từ Prometheus, `t(issue created)` từ Jira |
| **Time to first hypothesis** | Từ lúc phát hiện → có giả thuyết đầu tiên | timestamp comment trên Jira |
| **Độ chính xác severity** | % phân loại đúng / N lần chạy | so với nhãn đã biết trước |
| **Độ chính xác nguyên nhân (top-1)** | % lần giả thuyết #1 đúng | ground truth: pool cạn / OOM / auth burst |
| **Tính đầy đủ bằng chứng** | % giả thuyết có ≥1 `MetricEvidence` kèm PromQL | đọc từ model, tự động được |
| **Tỷ lệ báo động sai** | Số incident mở khi hệ thống bình thường | chạy tải thấp 30 phút, đếm |
| **Tỷ lệ trùng** | Số issue mở cho 1 sự cố thật (phải = **1**) | đếm trên Jira |
| **Tỷ lệ chặn HITL** | % hành động production bị chặn khi Agent tự duyệt (phải = **100%**) | đã có test tự động |

⚠️ **MTTR phải báo tách hai phần**: thời gian Agent xử lý, và thời gian người duyệt. Gộp lại thì con số phản ánh tốc độ bấm chuột của người demo, không phản ánh chất lượng Agent.

## Cách chạy

1. Bật demo stack: `docker compose -f docker-compose.demo.yml up`
2. Bật Agent
3. Chạy `python demo/loadtest.py` — **10 lần cho mỗi use case**
4. Ghi ground truth từng lần vào `eval/runs.csv`: UC nào, severity đúng là gì, nguyên nhân đúng là gì
5. Tính bảng họ B, xuất `eval/results/report.md`

Cần ≥10 lần/UC để tỷ lệ phần trăm có nghĩa. 2–3 lần thì con số không nói được gì.

## Giới hạn phải ghi rõ trong báo cáo

Không được im lặng bỏ qua, vì mentor sẽ hỏi:

> Kiểm chứng trên **2 service**, chưa kiểm chứng ở quy mô hàng chục service. Cơ chế phát hiện dựa trên PromQL nên về nguyên tắc mở rộng được (thêm service chỉ là thêm target scrape), nhưng chưa đo ở quy mô lớn.

Nói thẳng giới hạn đáng tin hơn là để người chấm tự phát hiện.

## Use case đo trên

Đã chốt **3 UC** — xem [docs/use-cases.md](../docs/use-cases.md):

| UC | Ground truth để đối chiếu | Severity đúng |
|---|---|---|
| **UC-1** Cạn pool | Pool giới hạn 5 bị chiếm hết + truy vấn thiếu index. Nói "service chậm" **không tính** — đó là triệu chứng | P2 |
| **UC-1a** Lan truyền | `service-dat-hang` suy giảm **do phụ thuộc**, không độc lập | P1 (≥2 service) |
| **UC-2** OOM restart | Container bị OOM-kill vì vượt limit 128MB | P1 |
| **UC-3** Burst xác thực | Vấn đề **bảo mật**, không phải quá tải. Kết luận "quá tải" là **SAI** | P1 hoặc P2 |

**Số lần chạy:** 10 lần UC-1 · 8 lần UC-2 và UC-3 = **26 lần**. UC-1 nhiều hơn vì nó xuất hiện trong video demo. Ghi rõ `n` trong báo cáo — số liệu có `n=8` và nói thẳng đáng tin hơn số liệu không ghi `n`.

UC-3 là phép thử khó nhất: hệ thống **hoàn toàn khoẻ** về mọi chỉ số hiệu năng, nên nếu Agent kết luận "quá tải" thì lộ ra rule engine chỉ khớp mẫu chứ không thực sự chẩn đoán.
