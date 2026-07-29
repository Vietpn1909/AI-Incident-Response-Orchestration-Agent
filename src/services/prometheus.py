"""Client query Prometheus — nguồn tín hiệu phát hiện sự cố.

CHỦ SỞ HỮU: Việt

Các câu PromQL dưới đây là [contract ①](../../docs/contracts/01-metrics.md), đã
chốt với Trung. **Đừng đổi tên metric hay label** — Trung expose đúng những tên
này, lệch một chữ là Prometheus trả kết quả rỗng chứ không báo lỗi, và Agent im
lặng không phát hiện gì.

Việt làm: các chỗ có TODO(Việt).
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# PromQL — contract ①, đã chốt. Dùng nguyên văn.
# ---------------------------------------------------------------------------

#: p95 latency theo service — tín hiệu chính để phát hiện sự cố.
P95_LATENCY = (
    "histogram_quantile(0.95, "
    "sum(rate(http_request_duration_seconds_bucket[1m])) by (le, service))"
)

#: Tỷ lệ lỗi 5xx theo service (0.0 – 1.0).
ERROR_RATE = (
    'sum(rate(http_requests_total{status=~"5.."}[1m])) by (service) '
    "/ sum(rate(http_requests_total[1m])) by (service)"
)

#: Mức sử dụng connection pool (0.0 – 1.0) — bằng chứng cho nguyên nhân gốc.
POOL_SATURATION = "db_pool_connections_in_use / db_pool_size"

#: p95 trung bình 30 phút trước — dùng làm baseline để so lệch.
P95_BASELINE_30M = f"avg_over_time(({P95_LATENCY})[30m:1m])"


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
