# Contract ① — Metric & PromQL

**Đường ghép:** Trung (expose metric) → Việt (query metric)
**Trạng thái:** Chốt 2026-07-28 · **Sửa 2026-07-29** sau khi Việt verify trên Prometheus thật — 4 lỗi, xem [spike/README.md](../../spike/README.md). Đổi tiếp phải qua PR có cả hai người review.

> 🔴 **Bản đầu của file này có một lỗi làm ngưỡng P1 và P2 không bao giờ kích hoạt được.** Việt phát hiện bằng đo thật: instrumentator để mặc định chỉ có 4 bucket nên `histogram_quantile` kẹp p95 về 1.0, mà P2 = p95 > 2s. Agent sẽ phân loại mọi sự cố nặng thành P3, và query vẫn trả số nên không có gì để lần theo. Đã sửa bằng cách chỉ định bucket tường minh.

Đây là contract dễ vỡ nhất mà không báo lỗi. Nếu Trung đặt tên metric là `payment_latency_seconds` mà Việt query `http_request_duration_seconds`, Prometheus trả về **kết quả rỗng chứ không phải lỗi** — Agent im lặng không phát hiện gì, và không có exception nào để lần theo.

## Trung phải đảm bảo

Cả hai service dùng `prometheus-fastapi-instrumentator`, không đo tay:

```python
from prometheus_fastapi_instrumentator import Instrumentator, metrics

app = FastAPI()

# ⚠️ PHẢI chỉ định bucket. Mặc định chỉ có (0.1, 0.5, 1, +Inf) và
# histogram_quantile KẸP p95 về 1.0 — ngưỡng P1/P2 chết cứng.
LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, float("inf"))

# should_instrument_requests_inprogress mặc định False, không bật thì
# http_requests_inprogress rỗng.
instrumentator = Instrumentator(
    should_instrument_requests_inprogress=True,
    inprogress_labels=True,
)
instrumentator.add(metrics.default(latency_lowr_buckets=LATENCY_BUCKETS))
instrumentator.instrument(app).expose(app)      # tạo ra /metrics
```

| Yêu cầu | Giá trị bắt buộc |
|---|---|
| Bucket latency | `(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, inf)` — **không để mặc định** |
| `scrape_interval` | **5s**, không phải 15s mặc định. Quy tắc "vượt ngưỡng liên tục ≥ 30s" cần nhiều điểm dữ liệu trong 30 giây đó |
| Đường dẫn metric | `/metrics` |
| Tên service trong Prometheus | `service-thanh-toan`, `service-dat-hang` (đúng chính tả, có gạch ngang) |
| Port | `service-thanh-toan` = `8001`, `service-dat-hang` = `8002` |

Tên `service` đến từ `prometheus.yml` (Trung viết), qua `job_name` hoặc label tĩnh:

```yaml
scrape_configs:
  - job_name: service-thanh-toan
    static_configs:
      - targets: ["service-thanh-toan:8001"]
        labels:
          service: service-thanh-toan
  - job_name: service-dat-hang
    static_configs:
      - targets: ["service-dat-hang:8002"]
        labels:
          service: service-dat-hang
```

## Metric có sẵn từ instrumentator

| Metric | Loại | Label dùng đến |
|---|---|---|
| `http_request_duration_seconds_bucket` | Histogram | `service`, `handler`, `le` |
| `http_requests_total` | Counter | `service`, `handler`, `status` |
| `http_requests_inprogress` | Gauge | `service`, `handler` |

## Metric Trung phải thêm tay

Hai cái này instrumentator không có, nhưng Agent cần để chẩn đoán ra **nguyên nhân gốc** là pool cạn thay vì chỉ nói "chậm":

```python
from prometheus_client import Gauge

# KHÔNG khai label "service" — prometheus.yml đã gắn. Khai cả hai chỗ thì
# Prometheus đổi tên label của app thành `exported_service`.
db_pool_in_use = Gauge("db_pool_connections_in_use", "Số connection đang dùng")
db_pool_size   = Gauge("db_pool_size", "Kích thước pool tối đa")
```

Không có 2 metric này thì Agent chỉ kết luận được "latency cao", không chứng minh được vì sao — mà "chẩn đoán có bằng chứng" là ràng buộc bắt buộc của đề bài.

## Việt query bằng những câu này

Đã verify trên Prometheus thật. Định nghĩa dùng chung ở [`src/services/prometheus.py`](../../src/services/prometheus.py) — import từ đó, đừng chép lại.

⚠️ **Mọi câu query đều phải lọc `handler!="/metrics"`.** Prometheus tự scrape endpoint đó mỗi 5s, request rất nhanh nên không lọc thì nó kéo avg latency sai **40 lần** lúc rảnh.

```promql
# p95 latency theo service — tín hiệu chính để phát hiện sự cố
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket{handler!="/metrics"}[1m])) by (le, service)
)

# tỷ lệ lỗi 5xx. Vế `or ... * 0` là CỐ Ý: thiếu nó thì service khoẻ trả RỖNG
# thay vì 0, Agent không phân biệt được "không lỗi" với "mất metric".
(
  sum by (service) (rate(http_requests_total{handler!="/metrics", status=~"5.."}[1m]))
  or
  sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m])) * 0
)
/ sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m]))

# mức dùng pool hiện tại
db_pool_connections_in_use / db_pool_size

# đỉnh mức dùng pool 5 phút qua — DÙNG BẢN NÀY khi làm bằng chứng cho Hypothesis.
# Gauge là giá trị tức thời: query instant lúc tải vừa dứt trả 0 dù ngay trước
# đó đã cạn kiệt, bằng chứng sẽ nói ngược sự thật.
max_over_time((db_pool_connections_in_use / db_pool_size)[5m:5s])

# baseline: p95 trung bình 30 phút trước
avg_over_time((
  histogram_quantile(0.95,
    sum(rate(http_request_duration_seconds_bucket{handler!="/metrics"}[1m])) by (le, service)
  )
)[30m:1m])
```

*Ghi chú:* instrumentator gom status thành `2xx`/`5xx` chứ không giữ `500`. Regex `5..` vẫn khớp `5xx` nên đúng — **đừng "sửa" thành `status="500"`**, sẽ không khớp gì cả.

## Ngưỡng và severity

Ngưỡng là code Python trong `detect` / `classify_severity`, không phải cấu hình Prometheus (xem [ADR-0002](../adr/0002-khong-dung-alertmanager.md)).

| Severity | Điều kiện |
|---|---|
| P1 | p95 > 10s **hoặc** tỷ lệ lỗi > 50% **hoặc** ≥ 2 service bị ảnh hưởng |
| P2 | p95 > 2s hoặc tỷ lệ lỗi > 10% |
| P3 | p95 > 1s hoặc tỷ lệ lỗi > 1% |
| P4 | Lệch baseline nhưng chưa vượt ngưỡng cứng |

Hai quy tắc bắt buộc kèm theo, nếu thiếu thì lúc load test Agent sẽ mở hàng loạt incident trùng:

- **Xác nhận kéo dài** — chỉ tính là incident khi vượt ngưỡng **liên tục ≥ 30s**, không phản ứng với một điểm dữ liệu đơn lẻ
- **Chống trùng** — trước khi mở war room, kiểm tra service đó đã có incident đang mở chưa

## Cách hai người tự verify không cần chờ nhau

**Trung** (xong là báo Việt):
```bash
curl -s localhost:8001/metrics | grep -E "http_request_duration_seconds_bucket|db_pool"
```
Phải thấy cả `http_request_duration_seconds_bucket` và `db_pool_connections_in_use`.

**Việt** (làm được ngay, không cần service của Trung): dựng Prometheus + 1 FastAPI dummy có instrumentator, gán label `service` tuỳ ý, rồi chạy các câu PromQL trên. Khi service thật của Trung xuất hiện, query không phải sửa gì vì tên metric và label đã chốt ở đây.
