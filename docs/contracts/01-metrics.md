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

Hai quy tắc áp cho **mọi** câu:

1. ⚠️ **Lọc `handler!="/metrics"`.** Prometheus tự scrape endpoint đó mỗi 5s, request rất nhanh nên không lọc thì nó kéo avg latency sai **40 lần** lúc rảnh.
2. ⚠️ **Câu nào có phép chia thì phải gắn `and on(service) (_HAS_TRAFFIC)`** — xem mục cảnh báo NaN bên dưới.

```promql
# Bộ lọc dùng chung: "service có request trong phút vừa rồi".
# Gắn vào mọi câu có phép chia để câu đó trả RỖNG thay vì NaN lúc không tải.
_HAS_TRAFFIC:
  sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m])) > 0

# p95 latency theo service — tín hiệu chính để phát hiện sự cố
(
  histogram_quantile(0.95,
    sum(rate(http_request_duration_seconds_bucket{handler!="/metrics"}[1m])) by (le, service)
  )
)
and on(service) (_HAS_TRAFFIC)

# tỷ lệ lỗi 5xx. Vế `or ... * 0` là CỐ Ý: thiếu nó thì service khoẻ trả RỖNG
# thay vì 0, Agent không phân biệt được "không lỗi" với "mất metric".
# `or ... * 0` chống RỖNG, `and on(service)` chống NaN — cần cả hai.
(
  (
    sum by (service) (rate(http_requests_total{handler!="/metrics", status=~"5.."}[1m]))
    or
    sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m])) * 0
  )
  / sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m]))
)
and on(service) (_HAS_TRAFFIC)

# mức dùng pool hiện tại — gauge/gauge, không sinh NaN nên không cần bộ lọc
db_pool_connections_in_use / db_pool_size

# đỉnh mức dùng pool 5 phút qua — DÙNG BẢN NÀY khi làm bằng chứng cho Hypothesis.
# Gauge là giá trị tức thời: query instant lúc tải vừa dứt trả 0 dù ngay trước
# đó đã cạn kiệt, bằng chứng sẽ nói ngược sự thật.
max_over_time((db_pool_connections_in_use / db_pool_size)[5m:5s])

# baseline: mức p95 "thường ngày" trong 30 phút qua.
# KHÔNG dùng avg_over_time — cửa sổ 30 phút bao gồm cả lúc đang có sự cố, nên
# trung bình bị chính sự cố kéo lên. Xem mục cảnh báo bên dưới.
quantile_over_time(0.1, (<câu p95 ở trên>)[30m:1m])
```

*Ghi chú:* instrumentator gom status thành `2xx`/`5xx` chứ không giữ `500`. Regex `5..` vẫn khớp `5xx` nên đúng — **đừng "sửa" thành `status="500"`**, sẽ không khớp gì cả.

### 🔴 Vì sao mọi câu có phép chia phải lọc theo traffic

**Sửa 2026-07-30.** Không có request nào trong cửa sổ `[1m]` thì `rate` = 0, và mọi câu có phép chia thành 0/0 = **`NaN`**. Prometheus không báo lỗi — query vẫn "chạy", vẫn trả ra một con số.

Đây là cùng loại lỗi với bucket mặc định, và cũng nguy hiểm y như vậy vì nó hỏng im lặng:

- `NaN > x` **và** `NaN < x` đều là `False`, nên mọi so sánh ngưỡng rơi tọt qua → Agent bỏ lọt sự cố mà không có dấu hiệu gì. Riêng mức **P4 hoàn toàn không kích hoạt được** vì nó dựa trọn vào độ lệch baseline
- `MetricEvidence.deviation_ratio` thành `NaN`
- Pydantic serialize `NaN` thành `null`, nên bằng chứng số biến mất khỏi war-room view của Long mà không báo gì

Bốn câu bị ảnh hưởng: **p95 latency, tỷ lệ lỗi, avg latency, và baseline**. Câu pool không bị vì nó là gauge chia gauge, cả hai luôn có giá trị.

Vế `and on(service) (_HAS_TRAFFIC)` bỏ hẳn series khi service không có request, nên câu trả **rỗng** thay vì `NaN`. Nhờ đó `PrometheusClient.query()` chỉ phải xử lý **một** trạng thái "không có dữ liệu" thay vì hai.

Phát hiện khi Việt bắn các hằng đang được ship trong `src/services/prometheus.py` vào Prometheus thật, lúc service đứng im: câu baseline trả `NaN` với toàn bộ điểm mẫu trong cửa sổ 30 phút đều `NaN`; sau khi sửa baseline thì lộ tiếp ba câu instant cũng `NaN` theo cùng cơ chế. Sau khi gắn bộ lọc: lúc rảnh cả bốn trả rỗng, dưới tải cả sáu trả số đúng (p95 1.95s, lỗi 2.1%, pool 1.00, baseline 1.46s, avg 1.53s).

### 🔴 Vì sao baseline dùng phân vị, không dùng trung bình

**Sửa 2026-07-30.** Cửa sổ 30 phút của baseline **bao gồm cả khoảng đang xảy ra sự cố**. Dùng `avg_over_time` thì trung bình bị chính sự cố kéo lên: sự cố càng kéo dài, baseline càng cao và độ lệch càng teo — bằng chứng yếu dần đúng lúc sự cố nghiêm trọng nhất.

Đo trên Prometheus thật, 4 phút traffic nền rồi tăng tải, p95 giữ nguyên 1.95s suốt:

| Thời điểm | p95 | `avg_over_time` | lệch | `quantile 0.1` | lệch |
|---|---|---|---|---|---|
| Bình thường | 0.181 s | 0.181 s | 1.0x | 0.181 s | 1.0x |
| +60s | 1.950 s | 0.531 s | 3.7x | 0.179 s | **10.9x** |
| +170s | 1.950 s | 0.936 s | **2.1x** | 0.180 s | **10.9x** |

Trung bình tụt từ 3.7x xuống 2.1x chỉ sau 2 phút. Phân vị đứng yên.

Chọn `0.1` thay vì trung vị `0.5`: trung vị bị nhiễm khi sự cố chiếm quá nửa cửa sổ (~15 phút), còn `0.1` chịu được tới ~27 phút. Kịch bản demo có bước **chờ người duyệt trên Jira** — thời gian chờ đó không đoán trước được, nên lấy biên an toàn rộng hơn.

**Ràng buộc kịch bản kèm theo — việc của Trung:** đổi sang phân vị vẫn không tạo ra baseline từ hư không. Load test cần **traffic nền trước khi tăng tải** — `PROFILE_DEMO` trong [`demo/loadtest.py`](../../demo/loadtest.py) đã có bậc đầu `(5, 20)`, chỉ cần **kéo dài bậc đó lên vài phút** để cửa sổ 30 phút có đủ dữ liệu "bình thường". Chạy từ trạng thái im lìm thì không có mức thường ngày nào để so, dù dùng phân vị hay trung bình. `spike/spike_promql.py` cảnh báo khi độ lệch dưới 1.5x.

## Ngưỡng và severity

Ngưỡng là code Python trong `detect` / `classify_severity`, không phải cấu hình Prometheus (xem [ADR-0002](../adr/0002-khong-dung-alertmanager.md)).

| Severity | Điều kiện |
|---|---|
| P1 | p95 > 10s **hoặc** tỷ lệ lỗi > 50% **hoặc** ≥ 2 service bị ảnh hưởng |
| P2 | p95 > 2s hoặc tỷ lệ lỗi > 10% |
| P3 | p95 > 1s hoặc tỷ lệ lỗi > 1% |
| P4 | Lệch baseline nhưng chưa vượt ngưỡng cứng |

### "≥ 2 service bị ảnh hưởng" nghĩa là gì — chốt 2026-08-03

Đếm **số service cùng hỏng trong một vòng quét**, không phải số phần tử trong `affected_services` của một incident.

Ghi lại vì chỗ này đã gây tranh cãi một lần. `fixtures/incidents.json` bản đầu có INC-12 (P2) và INC-13 (P3) nối với nhau — hai service cùng hỏng mà không cái nào P1, tức hiểu theo nghĩa thứ hai. Nhưng hiểu như vậy thì vế "≥ 2 service" **không bao giờ đúng**: mỗi incident luôn chỉ có một service, vì `open_war_room` mở một issue cho mỗi service rồi `link_incidents` nối chúng lại. Cả một mức severity trở thành code chết — đúng loại lỗi mà bucket mặc định và ngưỡng P2 đã gây ra hai lần trước đó.

Fixture viết trước khi có luật lan truyền nên đã sửa fixture cho khớp luật, không sửa luật cho khớp fixture. INC-12 và INC-13 giờ đều là P1.

Thực thi ở [`escalate_spreading()`](../../src/agents/nodes/classify_severity.py), gọi trong `run_cycle()` **trước** `open_war_room` — severity đi vào tiêu đề issue lúc tạo, nâng sau khi tạo thì tiêu đề mang mức sai.

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
