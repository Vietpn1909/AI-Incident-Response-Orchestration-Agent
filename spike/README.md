# Spike — verify giả định Prometheus/PromQL trước khi viết Agent

**Người làm:** Việt · **Ngày:** 2026-07-29, cập nhật 2026-07-30 · **Trạng thái:** Đã chạy, có kết quả

> `spike_promql.py` nay bắn thẳng các hằng trong [`src/services/prometheus.py`](../src/services/prometheus.py) vào Prometheus, không giữ bản sao câu query nữa. Nhờ vậy nó thành **kiểm tra hồi quy cho code đang chạy thật**, và chính nó đã bắt được lỗi thứ 5 dưới đây.

Việc tuần này của Việt theo [START-HERE](../docs/START-HERE.md#việt--agent-phát-hiện--chẩn-đoán) là verify giả định kỹ thuật cốt lõi *trước* khi kiến trúc phụ thuộc vào nó. Đây là kết quả.

## Chạy lại

```bash
cd spike && docker compose up -d --build
```

```bash
python spike/spike_promql.py
```

Chưa có traffic thì script dừng ở bước 2 và thoát với mã 2 — các câu có phép chia trả rỗng, đó là đúng thiết kế chứ không phải hỏng. Sinh tải trước:

```bash
python spike/loadgen.py --concurrency 150 --seconds 90
```

`http://localhost:9090/targets` phải thấy `service-thanh-toan` UP. Dọn: `docker compose down`.

## Kết luận ngắn

**Kiến trúc không phải đổi.** Các câu PromQL của [contract ①](../docs/contracts/01-metrics.md) chạy được, trả số dùng được, và phân biệt rõ lúc rảnh với lúc nghẽn. Agent query được từ Python.

**Nhưng contract ① có 5 chỗ phải sửa trước khi viết node `detect`.** Hai trong số đó làm cả ba mức severity P1, P2 và P4 không bao giờ kích hoạt được — và không lỗi nào ném exception, query vẫn trả ra số.

## Số đo được

| Đại lượng | Lúc rảnh | Lúc nghẽn (150 request đồng thời) |
|---|---|---|
| p95 latency | 0.095 s | **1.95 s** |
| avg latency | 0.083 s | 1.56 s |
| Tỷ lệ lỗi 5xx | *(rỗng)* | 2.1 % |
| Mức dùng pool | 0.00 | **1.00** — cạn kiệt |
| Lệch so baseline 30m | 1.0x | **4.0x** |

Nút cổ chai là thật, không phải số giả: pool 5 connection × truy vấn 80ms → trần khoảng 62 req/s. Bắn 150 request đồng thời thì đo được đúng 61 req/s và phần dư xếp hàng, latency tăng 20 lần. Đây chính là cơ chế ADR-0003 mô tả, thu nhỏ lại.

## Năm vấn đề của contract ①

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

### 5. 🔴 Mọi câu có phép chia trả `NaN` khi service không có request

*(Tìm ra 2026-07-30, sau khi 4 lỗi trên đã được sửa và merge.)*

Không có request nào trong cửa sổ `[1m]` thì `rate` = 0, và phép chia thành 0/0 = `NaN`. Query vẫn "chạy", vẫn trả ra số — không có exception nào.

Bốn câu bị: **p95 latency, tỷ lệ lỗi, avg latency, baseline**. Câu pool không bị vì là gauge chia gauge.

Nguy hiểm hơn kết quả rỗng, vì `NaN > x` **và** `NaN < x` đều là `False`:

- Mọi so sánh ngưỡng rơi tọt qua → Agent bỏ lọt sự cố mà không có dấu hiệu gì
- Mức **P4 hoàn toàn không kích hoạt được**, nó dựa trọn vào độ lệch baseline
- `MetricEvidence.deviation_ratio` thành `NaN`
- Pydantic serialize `NaN` thành `null` → bằng chứng số biến mất khỏi war-room view của Long

Câu baseline nặng nhất: chỉ cần **một** phút im lặng trong 30 phút là cả cửa sổ trả `NaN`, tức gần như luôn luôn trong lúc phát triển.

**Sửa** — gắn bộ lọc traffic vào mọi câu có phép chia, để câu trả **rỗng** thay vì `NaN`. Nhờ đó `PrometheusClient.query()` chỉ phải xử lý một trạng thái "không có dữ liệu" thay vì hai:

```promql
_HAS_TRAFFIC = sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m])) > 0

(<câu gốc>) and on(service) (_HAS_TRAFFIC)
```

Kiểm chứng sau khi sửa — lúc rảnh cả bốn câu trả rỗng (đúng thiết kế), dưới tải cả sáu trả số:

```
P95_LATENCY ............ 1.9496 s
ERROR_RATE ............. 0.0208
POOL_SATURATION ........ 1.0000
POOL_SATURATION_PEAK_5M  1.0000
P95_BASELINE_30M ....... 1.4618 s
AVG_LATENCY ............ 1.5250 s
```

**Ràng buộc kịch bản kèm theo — việc của Trung:** sửa query không tạo ra baseline từ hư không. Load test cần **pha warm-up** trước khi tăng tải. Chạy từ trạng thái im lìm thì baseline ≈ p95 hiện tại: đo được độ lệch chỉ **1.3x**, so với **4.0x** khi có traffic nền. `spike_promql.py` cảnh báo khi độ lệch dưới 1.5x.

## Ba điểm nhỏ khác

- **`http_requests_inprogress` phải bật tay.** `should_instrument_requests_inprogress` mặc định là `False`; contract ① có liệt kê metric này nhưng không nói phải bật. Không bật thì query trả rỗng, im lặng.
- **Gauge pool là giá trị tức thời.** Query instant lúc tải vừa dứt trả 0 dù ngay trước đó đã cạn. Khi lấy làm bằng chứng cho `Hypothesis`, dùng `max_over_time((db_pool_connections_in_use / db_pool_size)[5m:5s])` — đã verify, trả về `1`.
- **`scrape_interval` phải là 5s, không phải 15s mặc định.** Quy tắc "vượt ngưỡng liên tục ≥ 30s" cần vài điểm dữ liệu trong 30 giây đó. 5s cho 6 điểm.

## Việc kế tiếp

Bốn vấn đề đầu đã sửa và merge (`3b5b6eb`). Vấn đề 5 sửa ngày 2026-07-30. Còn lại:

1. Báo Trung thêm **pha warm-up** vào script load test — không có nó thì "so baseline" vô nghĩa, và đây là việc duy nhất trong danh sách cần người khác làm
2. Cài `PrometheusClient.query()` trong `src/services/prometheus.py` — chuyển thẳng từ `PrometheusQuerier` ở [spike_promql.py](spike_promql.py)
3. Cài 3 hàm trong `src/services/rules.py`, và **xử lý danh sách rỗng tường minh** — sau khi sửa vấn đề 5, "không có dữ liệu" luôn về dưới dạng rỗng, không bao giờ là `NaN`
4. Viết node `detect` + `classify_severity`

## File trong thư mục này

| File | Vai trò |
|---|---|
| [docker-compose.yml](docker-compose.yml) | Prometheus + service dummy |
| [prometheus.yml](prometheus.yml) | Scrape config — chép được sang stack thật của Trung |
| [dummy_service/app.py](dummy_service/app.py) | Service giả, pool 5 mô phỏng bằng `Semaphore`, expose đủ metric contract ① |
| [loadgen.py](loadgen.py) | Sinh tải cho spike (không thay k6/Locust của Trung) |
| [spike_promql.py](spike_promql.py) | Kiểm tra hồi quy: bắn các hằng trong `src/services/prometheus.py` vào Prometheus. Rỗng và `NaN` đều tính là FAIL. Exit 2 nếu chưa có traffic để đo |
