# Kết quả đánh giá — 50 test case

- Sinh lúc: `2026-08-21T15:25:53.392879+00:00`
- Dataset SHA-256: `226eedfa8c574271ef1ead62d2d5c26d0f6631015e77c786654574e2bcfd35ed`
- Phạm vi: snapshot → Prometheus client giả → node detect thật → FakeJira; không gọi LLM/Jira thật/Docker.

## 1. Confusion Matrix

- TP=21, FN=4, FP=5, TN=20.

> **Tỷ lệ báo nhầm ở đây là con số Agent THẬT đạt được**, không phải con số
> tốt nhất có thể. Bộ đo chỉ cho phép lọc bằng nguồn Agent biết được lúc
> chạy — tức lịch sử deploy. Đo ngày 21/08 bốn cách:
>
> | Lọc bằng | FP | Báo nhầm |
> |---|---:|---:|
> | không lọc gì | 7 | 28% |
> | lịch sử deploy — **Agent thật làm được** | 5 | **20%** |
> | thêm nguồn cửa sổ bảo trì — **chưa tồn tại** | 2 | 8% |
>
> Muốn xuống 8% cần một nguồn đọc được lúc chạy cho *pentest đã phê duyệt*,
> *load test*, *đổi route CDN* — ví dụ issue Jira mang nhãn bảo trì kèm khoảng
> thời gian. Chưa có ai làm.
>
> Trước 21/08 báo cáo ghi **16%**: nó lọc bằng `maintenance_event` (nguồn Agent
> KHÔNG có) và bỏ qua `deploy` (nguồn Agent CÓ), trong khi `detect_incidents()`
> thật thì không lọc gì cả. Con số đó là tính chất của bộ đo, không phải của
> sản phẩm.

## 2. Bộ chỉ số phát hiện (Detection Metrics)

| Chỉ số | Kết quả | Khoảng tin cậy 95% | Công thức | Ý nghĩa |
|---|---:|:---:|---|---|
| **Recall** | **84.00%** | 70%–98% | TP/(TP+FN) | Khả năng không bỏ lọt incident |
| **Precision** | **80.77%** | 66%–96% | TP/(TP+FP) | Tỷ lệ alert đúng |
| **F1 Score** | **82.35%** | — | 2·P·R/(P+R) | Cân bằng Precision-Recall |
| **F2 Score** | **83.33%** | — | 5·P·R/(4P+R) | Thiên Recall — phù hợp incident detection |
| **Accuracy** | **82.00%** | 71%–93% | (TP+TN)/All | Tổng thể đúng bao nhiêu |
| **Specificity** | **80.00%** | 64%–96% | TN/(TN+FP) | Khả năng nhận diện normal |
| **False Alarm Rate** | **20.00%** | 4%–36% | FP/(FP+TN) | Tỷ lệ báo nhầm |
| **MCC** | **+0.6405** | — | Matthews Correlation | Chỉ số tổng hợp (-1..+1) |

> ⚠️ **Cỡ mẫu 50 case khiến mọi con số trên có sai số lớn.**
> Recall 84.00% thật ra là "đâu đó trong 70%–98%" — khoảng rộng vài chục
> điểm phần trăm, nên **không phân biệt được** với một con số cao hơn 10–15 điểm.
>
> Hệ quả: đừng trích một phần trăm đơn lẻ ra khỏi ngữ cảnh, và đừng coi một
> cải thiện dưới ~15 điểm là tiến bộ đo được. Giá trị của bộ đo này nằm ở
> **phần phân tích từng case bỏ lọt** ở mục 3.2.2 — mỗi lỗ hổng nêu rõ vì sao
> mù và cần gì để vá. Phần đó không phụ thuộc cỡ mẫu.

## 3. Chỉ số chất lượng chẩn đoán

| Chỉ số | Kết quả | Ý nghĩa |
|---|---:|---|
| Severity Accuracy | **80.95%** | Phân loại mức độ đúng (P1-P4) |
| Root Cause Accuracy | 28.00% | Xác định đúng nguyên nhân gốc |
| Evidence Coverage | 84.00% | Đủ bằng chứng metric |
| Noisy Rejection | 60.00% | Chặn đúng case nhiễu |

## 4. Severity Confusion Matrix

| Actual \ Predicted | P1 | P2 | P3 | P4 |
|---|---|---|---|---|
| **P1** | 8 | 3 | 0 | 0 |
| **P2** | 0 | 5 | 1 | 0 |
| **P3** | 0 | 0 | 2 | 0 |
| **P4** | 0 | 0 | 0 | 2 |

## 5. Đối chiếu Pipeline vs Rule trực tiếp

| Đường chạy | Recall | Precision | F1 | Báo nhầm |
|---|---:|---:|---:|---:|
| Pipeline (detect → Jira) | 84.00% | 80.77% | 82.35% | 20.00% |
| Rule trực tiếp | 84.00% | 80.77% | 82.35% | 20.00% |

Hai đường phải khớp. Nếu lệch thì lỗi nằm ở wiring/collector.

## 6. Số đếm theo họ sự cố

| Họ | Bắt được | Bỏ lọt | Báo nhầm | Bắt / tổng sự cố |
|---|---:|---:|---:|:---:|
| UC-1 | 7 | 1 | 2 | **7/8** |
| UC-2 | 5 | 0 | 1 | **5/5** |
| UC-3 | 5 | 0 | 2 | **5/5** |
| UC-4 | 2 | 1 | 0 | **2/3** |
| dependency | 2 | 1 | 0 | **2/3** |
| deployment | 0 | 1 | 0 | **0/1** |

> Cố ý **không** in phần trăm ở bảng này. Họ nhỏ nhất có 1 case sự cố, họ
> lớn nhất có 8 — phần trăm trên mẫu đó gây hiểu sai nhiều hơn là cho biết
> thêm. `0/1` tự nó đã nói rõ mẫu bé tới đâu.

## 7. Kết quả từng case

| ID | Nhóm | Họ | Kết quả | Severity | Nguyên nhân gốc |
|---|---|---|---:|---:|---:|
| N01 | normal | UC-1 | TN | — | — |
| N02 | normal | UC-1 | TN | — | — |
| N03 | normal | UC-1 | TN | — | — |
| N04 | normal | UC-3 | TN | — | — |
| N05 | normal | UC-3 | TN | — | — |
| N06 | normal | UC-2 | TN | — | — |
| N07 | normal | UC-2 | TN | — | — |
| N08 | normal | UC-1 | TN | — | — |
| N09 | normal | UC-1 | TN | — | — |
| N10 | normal | UC-4 | TN | — | — |
| I01 | incident | UC-1 | TP | P2 | đúng |
| I02 | incident | UC-1 | TP | P3 | đúng |
| I03 | incident | UC-1 | TP | P1 | sai |
| I04 | incident | UC-1 | TP | P2 | sai |
| I05 | incident | UC-1 | TP | P4 | đúng |
| I06 | incident | UC-2 | TP | P1 | sai |
| I07 | incident | UC-2 | TP | P1 | sai |
| I08 | incident | UC-2 | TP | P1 | đúng |
| I09 | incident | UC-2 | TP | P1 | đúng |
| I10 | incident | UC-3 | TP | P1 | đúng |
| I11 | incident | UC-3 | TP | P2 | đúng |
| I12 | incident | UC-3 | TP | P3 | sai |
| I13 | incident | UC-4 | TP | P1 | sai |
| I14 | incident | dependency | TP | P2 | sai |
| I15 | incident | deployment | FN | — | sai |
| A01 | noisy | UC-1 | TN | — | — |
| A02 | noisy | UC-3 | TN | — | — |
| A03 | noisy | UC-2 | TN | — | — |
| A04 | noisy | deployment | TN | — | — |
| A05 | noisy | UC-3 | FP | P2 | — |
| N11 | normal | UC-4 | TN | — | — |
| N12 | normal | UC-2 | TN | — | — |
| N13 | normal | UC-2 | TN | — | — |
| N14 | normal | UC-1 | FP | P3 | — |
| N15 | normal | UC-3 | TN | — | — |
| I16 | incident | UC-4 | FN | — | sai |
| I17 | incident | UC-1 | TP | P3 | sai |
| I18 | incident | UC-2 | TP | P2 | sai |
| I19 | incident | UC-3 | TP | P2 | sai |
| I20 | incident | UC-3 | TP | P2 | sai |
| I21 | incident | dependency | TP | P2 | sai |
| I22 | incident | dependency | FN | — | sai |
| I23 | incident | UC-1 | TP | P1 | sai |
| I24 | incident | UC-4 | TP | P4 | sai |
| I25 | incident | UC-1 | FN | — | sai |
| A06 | noisy | UC-3 | FP | P2 | — |
| A07 | noisy | UC-4 | TN | — | — |
| A08 | noisy | UC-2 | FP | P1 | — |
| A09 | noisy | UC-2 | TN | — | — |
| A10 | noisy | UC-1 | FP | P4 | — |

## 8. Top error để cải thiện tiếp

- `I03` — Độ trễ P1 nhưng pool chỉ sát ngưỡng: TP, top-1 nguyên nhân sai.
- `I04` — Lỗi 5xx tăng dù latency thấp: TP, top-1 nguyên nhân sai.
- `I06` — Service chết liên tục hơn 30 giây: TP, top-1 nguyên nhân sai.
- `I07` — Crash loop hai lần nhưng chưa có bằng chứng OOM: TP, top-1 nguyên nhân sai.
- `I12` — Auth burst nhỏ nhưng kéo dài ở mức P3: TP, top-1 nguyên nhân sai.
- `I13` — Deploy thiếu migration làm 100% payment lỗi: TP, top-1 nguyên nhân sai.
- `I14` — Payment service unreachable từ service phụ thuộc: TP, top-1 nguyên nhân sai.
- `I15` — Lỗi xác thực backend bị metric tổng hợp che khuất: FN, top-1 nguyên nhân sai.
- `A05` — Load test đăng nhập đã được phê duyệt nhưng vượt ngưỡng: FP.
- `N14` — Health check prober thay đổi: error_rate 3% nhưng toàn từ synthetic checks: FP.
- `I16` — Silent data corruption: service trả 200 OK nhưng ghi sai DB, metric hoàn toàn xanh: FN, top-1 nguyên nhân sai.
- `I17` — Partial outage 1 pod: 5% request timeout 30s nhưng p95 tổng hợp bình thường: TP, top-1 nguyên nhân sai.
- `I18` — Memory leak chậm: tăng 5%/giờ, hiện 84% — chưa trigger rule nhưng sẽ OOM trong 3 giờ: TP, top-1 nguyên nhân sai.
- `I19` — Evasive credential stuffing: 0.95/s suốt 24h — ngay dưới mọi ngưỡng detection: TP, top-1 nguyên nhân sai.
- `I20` — DDoS làm cover cho credential stuffing: latency alert che khuất auth attack: TP, top-1 nguyên nhân sai.
- `I21` — Thundering herd: sau recovery, 100% client reconnect đồng thời gây pool cạn lần 2: TP, top-1 nguyên nhân sai.
- `I22` — Supply chain attack: dependency gửi data ra ngoài, metric hoàn toàn bình thường: FN, top-1 nguyên nhân sai.
- `I23` — Monitoring blind spot: Prometheus exporter crash, metric trả 0 — service thật ra đang chết: TP, top-1 nguyên nhân sai.
- `I24` — Config drift tích lũy: 10 deploy nhỏ mỗi cái +10% latency, tổng = 2.5× baseline: TP, top-1 nguyên nhân sai.
- `I25` — Race condition: double-charge khi 2 request trùng idempotency key, không lỗi 5xx: FN, top-1 nguyên nhân sai.
- `A06` — Pentest hợp pháp: 30 auth failures/s từ pentester đã được approve: FP.
- `A08` — Chaos engineering đã lên lịch: 3 lần restart có chủ đích trong maintenance window: FP.
- `A10` — CDN traffic shift: p95 tăng 3× do route change nhưng vẫn dưới ngưỡng cứng: FP.

## Giới hạn

Các snapshot được nhóm thiết kế từ pattern trong nguồn tham khảo, không phải dữ liệu thô tải từ Cloudflare/AWS/OpenTelemetry. FakeJira chứng minh pipeline đã quyết định mở issue nhưng không chứng minh kết nối Jira Cloud thật. Cần chạy thêm một tập live end-to-end đại diện để đo MTTD, log reasoning và độ dao động của LLM.
