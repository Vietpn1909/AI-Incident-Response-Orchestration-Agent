# Contract ① — Metric & PromQL

**Đường ghép:** Trung (expose metric) → Việt (query metric)
**Trạng thái:** Chốt 2026-07-28. Đổi phải qua PR có cả hai người review.

Đây là contract dễ vỡ nhất mà không báo lỗi. Nếu Trung đặt tên metric là `payment_latency_seconds` mà Việt query `http_request_duration_seconds`, Prometheus trả về **kết quả rỗng chứ không phải lỗi** — Agent im lặng không phát hiện gì, và không có exception nào để lần theo.

## Trung phải đảm bảo

Cả hai service dùng `prometheus-fastapi-instrumentator`, không đo tay:

```python
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()
Instrumentator().instrument(app).expose(app)   # tạo ra /metrics
```

| Yêu cầu | Giá trị bắt buộc |
|---|---|
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

db_pool_in_use = Gauge("db_pool_connections_in_use", "Số connection đang dùng", ["service"])
db_pool_size   = Gauge("db_pool_size", "Kích thước pool tối đa", ["service"])
```

Không có 2 metric này thì Agent chỉ kết luận được "latency cao", không chứng minh được vì sao — mà "chẩn đoán có bằng chứng" là ràng buộc bắt buộc của đề bài.

## Việt query bằng những câu này

```promql
# p95 latency theo service — tín hiệu chính để phát hiện sự cố
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[1m])) by (le, service)
)

# tỷ lệ lỗi 5xx theo service
sum(rate(http_requests_total{status=~"5.."}[1m])) by (service)
  / sum(rate(http_requests_total[1m])) by (service)

# mức sử dụng pool — bằng chứng cho nguyên nhân gốc
db_pool_connections_in_use / db_pool_size

# baseline để so sánh: p95 trung bình 30 phút trước
avg_over_time(
  histogram_quantile(0.95,
    sum(rate(http_request_duration_seconds_bucket[1m])) by (le, service)
  )[30m:1m]
)
```

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
