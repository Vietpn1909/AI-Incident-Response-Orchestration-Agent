# Kết quả bộ 30 test case incident

- Sinh lúc: `2026-08-15T03:49:50.389319+00:00`
- Dataset SHA-256: `e6f14ef6755fb10b207462560654a6c93b1d99adff2d9a751064e640527355be`
- Phạm vi recall: snapshot → Prometheus client giả → node detect thật → FakeJira; không gọi LLM/Jira thật/Docker.

## Chỉ số chính

| Chỉ số | Kết quả | Cách tính |
|---|---:|---|
| Recall incident | **72.00%** | TP / (TP + FN) |
| Precision incident | 72.00% | TP / (TP + FP) |
| Tỷ lệ báo nhầm | 28.00% | FP / (FP + TN) |
| Đúng severity | 88.89% | severity đúng / incident đã bắt được |
| Top-1 nguyên nhân gốc (rule baseline) | 28.00% | đúng nguyên nhân / 15 incident thật |
| Đủ bằng chứng metric | 72.00% | đủ evidence / 15 incident thật |
| Từ chối case nhiễu | 50.00% | noisy không mở incident / 5 |

## Confusion matrix

- TP=18, FN=7, FP=7, TN=18.
- Recall chỉ đo khả năng không bỏ lọt incident; phải đọc cùng precision và tỷ lệ báo nhầm.

## Đối chiếu với rule trực tiếp

| Đường chạy | Recall | Precision | Báo nhầm |
|---|---:|---:|---:|
| Pipeline phát hiện → Jira | 72.00% | 72.00% | 28.00% |
| Gọi rule trực tiếp | 72.00% | 72.00% | 28.00% |

Hai đường phải khớp. Nếu rule bắt được nhưng pipeline không mở Jira thì lỗi nằm ở wiring/collector, không phải threshold.

## Recall theo họ sự cố

| Họ | TP | FN | Recall |
|---|---:|---:|---:|
| UC-1 | 6 | 2 | 75.00% |
| UC-2 | 4 | 1 | 80.00% |
| UC-3 | 4 | 1 | 80.00% |
| UC-4 | 2 | 1 | 66.67% |
| dependency | 2 | 1 | 66.67% |
| deployment | 0 | 1 | 0.00% |

## Kết quả từng case

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
| N12 | normal | UC-2 | FP | P1 | — |
| N13 | normal | UC-2 | TN | — | — |
| N14 | normal | UC-1 | FP | P3 | — |
| N15 | normal | UC-3 | TN | — | — |
| I16 | incident | UC-4 | FN | — | sai |
| I17 | incident | UC-1 | TP | P3 | sai |
| I18 | incident | UC-2 | FN | — | sai |
| I19 | incident | UC-3 | FN | — | sai |
| I20 | incident | UC-3 | TP | P2 | sai |
| I21 | incident | dependency | TP | P2 | sai |
| I22 | incident | dependency | FN | — | sai |
| I23 | incident | UC-1 | FN | — | sai |
| I24 | incident | UC-4 | TP | P4 | sai |
| I25 | incident | UC-1 | FN | — | sai |
| A06 | noisy | UC-3 | FP | P2 | — |
| A07 | noisy | UC-4 | FP | P2 | — |
| A08 | noisy | UC-2 | FP | P1 | — |
| A09 | noisy | UC-2 | TN | — | — |
| A10 | noisy | UC-1 | FP | P4 | — |

## Top error để cải thiện tiếp

- `I03` — Độ trễ P1 nhưng pool chỉ sát ngưỡng: TP, top-1 nguyên nhân sai.
- `I04` — Lỗi 5xx tăng dù latency thấp: TP, top-1 nguyên nhân sai.
- `I06` — Service chết liên tục hơn 30 giây: TP, top-1 nguyên nhân sai.
- `I07` — Crash loop hai lần nhưng chưa có bằng chứng OOM: TP, top-1 nguyên nhân sai.
- `I12` — Auth burst nhỏ nhưng kéo dài ở mức P3: TP, top-1 nguyên nhân sai.
- `I13` — Deploy thiếu migration làm 100% payment lỗi: TP, top-1 nguyên nhân sai.
- `I14` — Payment service unreachable từ service phụ thuộc: TP, top-1 nguyên nhân sai.
- `I15` — Lỗi xác thực backend bị metric tổng hợp che khuất: FN, top-1 nguyên nhân sai.
- `A05` — Load test đăng nhập đã được phê duyệt nhưng vượt ngưỡng: FP.
- `N12` — Blue-green deploy: 2 restarts (= ngưỡng crashloop) nhưng là deploy có chủ đích: FP.
- `N14` — Health check prober thay đổi: error_rate 3% nhưng toàn từ synthetic checks: FP.
- `I16` — Silent data corruption: service trả 200 OK nhưng ghi sai DB, metric hoàn toàn xanh: FN, top-1 nguyên nhân sai.
- `I17` — Partial outage 1 pod: 5% request timeout 30s nhưng p95 tổng hợp bình thường: TP, top-1 nguyên nhân sai.
- `I18` — Memory leak chậm: tăng 5%/giờ, hiện 84% — chưa trigger rule nhưng sẽ OOM trong 3 giờ: FN, top-1 nguyên nhân sai.
- `I19` — Evasive credential stuffing: 0.95/s suốt 24h — ngay dưới mọi ngưỡng detection: FN, top-1 nguyên nhân sai.
- `I20` — DDoS làm cover cho credential stuffing: latency alert che khuất auth attack: TP, top-1 nguyên nhân sai.
- `I21` — Thundering herd: sau recovery, 100% client reconnect đồng thời gây pool cạn lần 2: TP, top-1 nguyên nhân sai.
- `I22` — Supply chain attack: dependency gửi data ra ngoài, metric hoàn toàn bình thường: FN, top-1 nguyên nhân sai.
- `I23` — Monitoring blind spot: Prometheus exporter crash, metric trả 0 — service thật ra đang chết: FN, top-1 nguyên nhân sai.
- `I24` — Config drift tích lũy: 10 deploy nhỏ mỗi cái +10% latency, tổng = 2.5× baseline: TP, top-1 nguyên nhân sai.
- `I25` — Race condition: double-charge khi 2 request trùng idempotency key, không lỗi 5xx: FN, top-1 nguyên nhân sai.
- `A06` — Pentest hợp pháp: 30 auth failures/s từ pentester đã được approve: FP.
- `A07` — Canary tự rollback: p95=3s trong 35s nhưng canary đã tự kill trước impact lan rộng: FP.
- `A08` — Chaos engineering đã lên lịch: 3 lần restart có chủ đích trong maintenance window: FP.
- `A10` — CDN traffic shift: p95 tăng 3× do route change nhưng vẫn dưới ngưỡng cứng: FP.

## Giới hạn

Các snapshot được nhóm thiết kế từ pattern trong nguồn tham khảo, không phải dữ liệu thô tải từ Cloudflare/AWS/OpenTelemetry. FakeJira chứng minh pipeline đã quyết định mở issue nhưng không chứng minh kết nối Jira Cloud thật. Cần chạy thêm một tập live end-to-end đại diện để đo MTTD, log reasoning và độ dao động của LLM.
