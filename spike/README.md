# Spike — verify giả định Prometheus/PromQL trước khi viết Agent

**Người làm:** Việt · **Ngày:** 2026-07-29 · **Trạng thái:** Đã chạy, có kết quả

Việc tuần này của Việt theo [START-HERE](../docs/START-HERE.md#việt--agent-phát-hiện--chẩn-đoán) là verify giả định kỹ thuật cốt lõi *trước* khi kiến trúc phụ thuộc vào nó. Đây là kết quả.

## Chạy lại

```bash
cd spike && docker compose up -d --build
```

```bash
python spike/spike_promql.py
```

Không có tải thì mọi con số đều ~0 và không chứng minh được gì. Sinh tải trước:

```bash
python spike/loadgen.py --concurrency 150 --seconds 90
```

`http://localhost:9090/targets` phải thấy `service-thanh-toan` UP. Dọn: `docker compose down`.

## Kết luận ngắn

**Kiến trúc không phải đổi.** Bốn câu PromQL của [contract ①](../docs/contracts/01-metrics.md) chạy được, trả số dùng được, và phân biệt rõ lúc rảnh với lúc nghẽn. Agent query được từ Python.

**Nhưng contract ① có 4 chỗ phải sửa trước khi viết node `detect`** — trong đó một chỗ làm 2 mức severity không bao giờ kích hoạt được.

## Số đo được

| Đại lượng | Lúc rảnh | Lúc nghẽn (150 request đồng thời) |
|---|---|---|
| p95 latency | 0.095 s | **1.95 s** |
| avg latency | 0.083 s | 1.56 s |
| Tỷ lệ lỗi 5xx | *(rỗng)* | 2.1 % |
| Mức dùng pool | 0.00 | **1.00** — cạn kiệt |
| Lệch so baseline 30m | 1.0x | **4.0x** |

Nút cổ chai là thật, không phải số giả: pool 5 connection × truy vấn 80ms → trần khoảng 62 req/s. Bắn 150 request đồng thời thì đo được đúng 61 req/s và phần dư xếp hàng, latency tăng 20 lần. Đây chính là cơ chế ADR-0003 mô tả, thu nhỏ lại.

## Bốn vấn đề của contract ①

### 1. 🔴 Ngưỡng P1 và P2 không bao giờ kích hoạt được

`prometheus-fastapi-instrumentator` để mặc định thì `http_request_duration_seconds` chỉ có **4 bucket**:

```
le=0.1  le=0.5  le=1.0  le=+Inf
```

`histogram_quantile` không nội suy được bên trong bucket `+Inf`, nên khi p95 thật rơi vào đó Prometheus **kẹp kết quả về 1.0** — mốc hữu hạn cao nhất. Đo được lúc chạy: 2399/2757 request ≤ 1s, p95 thật nằm trong `+Inf`, query trả về đúng `1.0000`.

Hệ quả: bảng severity của contract ① có **P1 = p95 > 10s** và **P2 = p95 > 2s**. Với bucket mặc định, p95 **không bao giờ vượt quá 1.0**, nên hai mức này chết cứng. Agent sẽ phân loại mọi sự cố nặng thành P3.

Đây đúng loại lỗi contract ① tự cảnh báo: không có exception nào, query vẫn trả số, số đó chỉ đơn giản là sai.

**Sửa** — Trung chỉ định bucket tường minh khi tạo instrumentator:

```python
LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, float("inf"))

instrumentator = Instrumentator(should_instrument_requests_inprogress=True)
instrumentator.add(metrics.default(latency_lowr_buckets=LATENCY_BUCKETS))
instrumentator.instrument(app).expose(app)
```

Sau khi sửa, cùng một câu query trả **1.95 s** thay vì bị kẹp ở 1.0 — xem [dummy_service/app.py](dummy_service/app.py).

*Ghi chú:* thư viện cũng expose sẵn `http_request_duration_highr_seconds` có 22 bucket tới 60s. Không dùng nó vì metric đó **không có label `handler`**, mà ta cần tách `/pay` khỏi `/metrics` (vấn đề 3).

### 2. 🔴 Câu tỷ lệ lỗi trả RỖNG khi service khoẻ, không phải 0

```promql
sum(rate(http_requests_total{status=~"5.."}[1m])) by (service) / sum(rate(http_requests_total[1m])) by (service)
```

Chưa có lỗi 5xx nào thì không tồn tại series nào khớp `status=~"5.."`, nên tử số rỗng và cả phép chia rỗng. Agent nhận `None`, và **không phân biệt được "service khoẻ" với "mất metric / service chết"** — hai tình huống cần xử lý ngược nhau.

**Sửa** — thêm một vế `* 0` để luôn có series, vẫn giữ label `service`:

```promql
(
  sum by (service) (rate(http_requests_total{handler!="/metrics", status=~"5.."}[1m]))
  or
  sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m])) * 0
)
/ sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m]))
```

Từ giờ rỗng nghĩa là **mất metric**, và đó là tín hiệu đáng báo động chứ không phải bình thường.

*Kiểm chứng phụ:* instrumentator gom status thành `2xx`/`5xx` chứ không giữ `500`. Regex `5..` vẫn khớp `5xx`, nên chỗ này contract ① **đúng** — nhưng đúng do may, cần ghi lại để không ai "sửa" thành `status="500"`.

### 3. 🟡 Prometheus tự scrape `/metrics` và làm nhiễu mọi số tổng hợp

Không câu query nào của contract ① lọc `handler`, nên chính request scrape của Prometheus (5s/lần, ~1ms) bị tính vào. Lúc rảnh nó kéo avg latency từ 0.083s xuống **0.002s** — sai 40 lần.

**Sửa** — thêm `handler!="/metrics"` vào mọi câu query.

### 4. 🟡 Label `service` của `db_pool_*` bị Prometheus đổi tên

Contract ① bảo Trung khai `Gauge(..., ["service"])` **và** gắn `service` trong `prometheus.yml`. Hai chỗ cùng đặt một label thì Prometheus giữ label của scrape config và đổi tên label của app thành `exported_service`:

```
db_pool_connections_in_use{service="service-thanh-toan", exported_service="service-thanh-toan", ...}
```

Phép chia `db_pool_connections_in_use / db_pool_size` **vẫn chạy** vì hai vế có label giống hệt nhau. Nhưng nó là quả mìn: ai đó viết `sum by (exported_service)` hay bỏ label ở một trong hai chỗ là kết quả đổi.

**Sửa** — bỏ `["service"]` khỏi Gauge, để `prometheus.yml` là nguồn duy nhất của label `service`, nhất quán với các metric `http_*`.

## Ba điểm nhỏ khác

- **`http_requests_inprogress` phải bật tay.** `should_instrument_requests_inprogress` mặc định là `False`; contract ① có liệt kê metric này nhưng không nói phải bật. Không bật thì query trả rỗng, im lặng.
- **Gauge pool là giá trị tức thời.** Query instant lúc tải vừa dứt trả 0 dù ngay trước đó đã cạn. Khi lấy làm bằng chứng cho `Hypothesis`, dùng `max_over_time((db_pool_connections_in_use / db_pool_size)[5m:5s])` — đã verify, trả về `1`.
- **`scrape_interval` phải là 5s, không phải 15s mặc định.** Quy tắc "vượt ngưỡng liên tục ≥ 30s" cần vài điểm dữ liệu trong 30 giây đó. 5s cho 6 điểm.

## Việc kế tiếp

1. Mở PR sửa [contract ①](../docs/contracts/01-metrics.md) với 4 điểm trên — cần Trung review vì điểm 1 và 4 đổi code service của Trung
2. Chuyển `PrometheusQuerier` trong [spike_promql.py](spike_promql.py) thành `src/services/prometheus.py`
3. Viết node `detect` + `classify_severity` dựa trên câu query **đã sửa**

## File trong thư mục này

| File | Vai trò |
|---|---|
| [docker-compose.yml](docker-compose.yml) | Prometheus + service dummy |
| [prometheus.yml](prometheus.yml) | Scrape config — chép được sang stack thật của Trung |
| [dummy_service/app.py](dummy_service/app.py) | Service giả, pool 5 mô phỏng bằng `Semaphore`, expose đủ metric contract ① |
| [loadgen.py](loadgen.py) | Sinh tải cho spike (không thay k6/Locust của Trung) |
| [spike_promql.py](spike_promql.py) | Script verify — chứa `PrometheusQuerier`, hạt giống của service thật |
