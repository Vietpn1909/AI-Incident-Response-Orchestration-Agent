"""Client query Prometheus — nguồn tín hiệu phát hiện sự cố.

CHỦ SỞ HỮU: Việt

Các câu PromQL dưới đây là [contract ①](../../docs/contracts/01-metrics.md), đã
chốt với Trung và **đã được Việt verify trên Prometheus thật** (2026-07-29, xem
[spike/README.md](../../spike/README.md)). Bản này đã sửa 4 lỗi Việt tìm ra.

**Đừng đổi tên metric hay label** — Trung expose đúng những tên này, lệch một
chữ là Prometheus trả kết quả rỗng chứ không báo lỗi, và Agent im lặng không
phát hiện gì.

Việt làm: các chỗ có TODO(Việt).
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# PromQL — contract ①, đã chốt. Dùng nguyên văn.
# ---------------------------------------------------------------------------

# ⚠️ Mọi câu query đều lọc `handler!="/metrics"`. Prometheus tự scrape endpoint
# đó mỗi 5s và request rất nhanh, không lọc thì nó kéo avg latency sai 40 lần
# lúc rảnh. Việt đo được và ghi ở spike/README.md.

# ⚠️ NaN — đọc trước khi sửa bất kỳ câu nào ở dưới.
#
# Không có request nào trong cửa sổ `[1m]` thì `rate` = 0, và mọi câu có phép
# chia thành 0/0 = `NaN`. Prometheus không báo lỗi, query vẫn "chạy", vẫn trả
# ra một con số.
#
# NaN nguy hiểm hơn kết quả rỗng vì nó hỏng im lặng:
#   - `NaN > x` VÀ `NaN < x` đều là False, nên mọi so sánh ngưỡng rơi tọt qua
#     → Agent bỏ lọt sự cố mà không có dấu hiệu gì
#   - `MetricEvidence.deviation_ratio` thành NaN
#   - Pydantic serialize NaN thành `null`, nên bằng chứng số biến mất khỏi
#     war-room view của Long mà không báo gì
#
# Vì vậy mọi câu có phép chia đều gắn `and on(service) (_HAS_TRAFFIC)`. Vế này
# bỏ hẳn series khi service không có request, nên câu trả **rỗng** thay vì NaN
# — và rỗng là trạng thái duy nhất `PrometheusClient.query()` phải xử lý.
#
# Đo được 2026-07-30 trên Prometheus thật, xem spike/README.md.

#: Điều kiện "service có request trong phút vừa rồi".
#:
#: Chỉ dùng làm bộ lọc chống NaN, không dùng trực tiếp làm tín hiệu.
_HAS_TRAFFIC = """
sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m])) > 0
"""

_P95_LATENCY_RAW = """
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket{handler!="/metrics"}[1m])) by (le, service)
)
"""

#: p95 latency theo service — tín hiệu chính để phát hiện sự cố.
P95_LATENCY = f"""
({_P95_LATENCY_RAW})
and on(service) ({_HAS_TRAFFIC})
"""

#: Tỷ lệ lỗi 5xx theo service (0.0 – 1.0).
#:
#: Vế `or ... * 0` là cố ý: không có vế đó thì khi service khoẻ, không series
#: nào khớp `status=~"5.."` nên tử số rỗng và cả phép chia trả RỖNG — Agent
#: không phân biệt được "không có lỗi" với "mất metric / service chết", hai
#: tình huống cần xử lý ngược nhau.
#:
#: Vế `or ... * 0` xử lý trường hợp rỗng, vế `and on(service)` xử lý trường hợp
#: NaN. Cần cả hai, chúng không thay được nhau.
_ERROR_RATE_RAW = """
(
  sum by (service) (rate(http_requests_total{handler!="/metrics", status=~"5.."}[1m]))
  or
  sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m])) * 0
)
/ sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m]))
"""

ERROR_RATE = f"""
({_ERROR_RATE_RAW})
and on(service) ({_HAS_TRAFFIC})
"""

#: Mức sử dụng connection pool (0.0 – 1.0) — bằng chứng cho nguyên nhân gốc.
POOL_SATURATION = "db_pool_connections_in_use / db_pool_size"

#: Đỉnh mức dùng pool trong 5 phút qua.
#:
#: Dùng bản này khi lấy làm bằng chứng cho `Hypothesis`, KHÔNG dùng
#: `POOL_SATURATION`: gauge là giá trị tức thời, query instant lúc tải vừa dứt
#: trả 0 dù ngay trước đó đã cạn kiệt — bằng chứng sẽ nói ngược sự thật.
POOL_SATURATION_PEAK_5M = f"max_over_time(({POOL_SATURATION})[5m:5s])"

#: p95 trung bình 30 phút trước — dùng làm baseline để so lệch.
#:
#: Kế thừa bộ lọc chống NaN từ `P95_LATENCY`, nên chỉ lấy trung bình trên những
#: phút thực sự có request. Không có bộ lọc đó thì chỉ cần MỘT phút im lặng
#: trong 30 phút là cả câu trả NaN — mà mức P4 ("lệch baseline nhưng chưa vượt
#: ngưỡng cứng") hoàn toàn dựa vào con số này.
#:
#: Đi kèm là một ràng buộc kịch bản, không phải lỗi code: baseline chỉ có nghĩa
#: khi TRƯỚC lúc tăng tải đã có traffic nền. Chạy load test từ trạng thái im
#: lìm thì baseline ≈ p95 hiện tại và độ lệch ra 1.0x.
P95_BASELINE_30M = f"avg_over_time(({P95_LATENCY})[30m:1m])"

#: Số request xác thực thất bại mỗi giây — tín hiệu của UC-3 (burst tấn công).
#:
#: ⚠️ `ERROR_RATE` KHÔNG bắt được UC-3 vì nó chỉ khớp `status=~"5.."`, còn 401
#: là 4xx. Đây là tín hiệu riêng, và severity của UC-3 dựa trên **số lượng
#: tuyệt đối** chứ không phải tỷ lệ — nếu kẻ tấn công là nguồn traffic duy nhất
#: thì tỷ lệ lỗi là 100% ngay từ request đầu, chưa nói được gì về mức nghiêm
#: trọng. Xem docs/use-cases.md UC-3.
AUTH_FAILURE_RATE = """
sum by (service) (rate(http_requests_total{handler="/login", status=~"4.."}[1m]))
"""

_AVG_LATENCY_RAW = """
sum(rate(http_request_duration_seconds_sum{handler!="/metrics"}[1m])) by (service)
  / sum(rate(http_request_duration_seconds_count{handler!="/metrics"}[1m])) by (service)
"""

#: avg latency — dùng để đối chiếu, không dùng làm ngưỡng (p95 nhạy hơn).
AVG_LATENCY = f"""
({_AVG_LATENCY_RAW})
and on(service) ({_HAS_TRAFFIC})
"""


@dataclass
class MetricSample:
    """Một giá trị metric đọc về, cho một service."""

    service: str
    value: float


class PrometheusClient:
    """Đọc metric từ Prometheus HTTP API.

    Không dùng Alertmanager — logic ngưỡng nằm trong `rules.py`.
    Xem [ADR-0002](../../docs/adr/0002-khong-dung-alertmanager.md).
    """

    def __init__(self, base_url: str = "http://localhost:9090", timeout: float = 10.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def query(self, promql: str) -> list[MetricSample]:
        """Chạy một câu PromQL tức thời, trả giá trị theo từng service.

        TODO(Việt):
          1. GET {base}/api/v1/query?query=<promql>  (dùng httpx, đã có trong deps)
          2. Response dạng:
                 {"status":"success","data":{"result":[
                     {"metric":{"service":"service-thanh-toan"},"value":[ts,"5.1"]}
                 ]}}
          3. Trả [MetricSample(service=..., value=float(...))]
          4. `result` rỗng KHÔNG phải lỗi — nghĩa là chưa có dữ liệu, hoặc
             (nguy hiểm hơn) tên metric bị lệch. Log warning để dễ phát hiện,
             đừng raise.

        Xong là thế nào:
            client = PrometheusClient()
            print(client.query(P95_LATENCY))
            # -> [MetricSample(service='service-thanh-toan', value=0.02)]
        """
        raise NotImplementedError("TODO(Việt): xem docstring")

    def query_range(self, promql: str, minutes: int = 30) -> list[MetricSample]:
        """Giá trị trung bình trong `minutes` phút qua — dùng tính baseline.

        TODO(Việt): gọi /api/v1/query_range, hoặc đơn giản hơn là dùng
        `avg_over_time(...)` trong chính câu query rồi gọi `query()`.
        Cách thứ hai ít code hơn, khuyến nghị dùng.
        """
        raise NotImplementedError("TODO(Việt): xem docstring")
