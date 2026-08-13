# Kết quả bộ 30 test case incident

- Sinh lúc: `2026-08-13T16:35:47.754519+00:00`
- Dataset SHA-256: `9e17ed1135392df2f30947deb5d31b6583f8bb2a1026180035ded4eedc1d4ea1`
- Phạm vi recall: snapshot → Prometheus client giả → node detect thật → FakeJira; không gọi LLM/Jira thật/Docker.

## Chỉ số chính

| Chỉ số | Kết quả | Cách tính |
|---|---:|---|
| Recall incident | **93.33%** | TP / (TP + FN) |
| Precision incident | 93.33% | TP / (TP + FP) |
| Tỷ lệ báo nhầm | 6.67% | FP / (FP + TN) |
| Đúng severity | 100.00% | severity đúng / incident đã bắt được |
| Top-1 nguyên nhân gốc (rule baseline) | 46.67% | đúng nguyên nhân / 15 incident thật |
| Đủ bằng chứng metric | 93.33% | đủ evidence / 15 incident thật |
| Từ chối case nhiễu | 80.00% | noisy không mở incident / 5 |

## Confusion matrix

- TP=14, FN=1, FP=1, TN=14.
- Recall chỉ đo khả năng không bỏ lọt incident; phải đọc cùng precision và tỷ lệ báo nhầm.

## Đối chiếu với rule trực tiếp

| Đường chạy | Recall | Precision | Báo nhầm |
|---|---:|---:|---:|
| Pipeline phát hiện → Jira | 93.33% | 93.33% | 6.67% |
| Gọi rule trực tiếp | 93.33% | 93.33% | 6.67% |

Hai đường phải khớp. Nếu rule bắt được nhưng pipeline không mở Jira thì lỗi nằm ở wiring/collector, không phải threshold.

## Recall theo họ sự cố

| Họ | TP | FN | Recall |
|---|---:|---:|---:|
| UC-1 | 5 | 0 | 100.00% |
| UC-2 | 4 | 0 | 100.00% |
| UC-3 | 3 | 0 | 100.00% |
| UC-4 | 1 | 0 | 100.00% |
| dependency | 1 | 0 | 100.00% |
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

## Giới hạn

Các snapshot được nhóm thiết kế từ pattern trong nguồn tham khảo, không phải dữ liệu thô tải từ Cloudflare/AWS/OpenTelemetry. FakeJira chứng minh pipeline đã quyết định mở issue nhưng không chứng minh kết nối Jira Cloud thật. Cần chạy thêm một tập live end-to-end đại diện để đo MTTD, log reasoning và độ dao động của LLM.
