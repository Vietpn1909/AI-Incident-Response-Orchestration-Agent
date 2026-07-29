"""Spike: verify giả định kỹ thuật cốt lõi của Agent trước khi viết Agent.

Giả định cần verify (nếu sai thì kiến trúc phải đổi — biết bây giờ tốt hơn
biết tuần 3):

1. `prometheus-fastapi-instrumentator` thật sự sinh ra các metric mà
   [contract ①](../docs/contracts/01-metrics.md) đã chốt tên
2. Label `service` gắn được từ `prometheus.yml`, service không phải sửa code
3. Bốn câu PromQL của contract ① chạy được và trả về **số dùng được**, không
   phải kết quả rỗng
4. Query được từ Python qua Prometheus HTTP API

Điểm 3 là điểm dễ hỏng nhất mà không báo lỗi: Prometheus trả kết quả rỗng chứ
không phải exception, nên Agent sẽ im lặng không phát hiện gì. Vì vậy script
này coi **kết quả rỗng là FAIL**, không phải là "0".

    python spike/spike_promql.py

`PrometheusQuerier` bên dưới là hạt giống của `src/services/prometheus.py` —
node `detect` sẽ dùng đúng hai method này.
"""

from __future__ import annotations

import sys

import httpx

PROMETHEUS_URL = "http://localhost:9090"
SERVICE = "service-thanh-toan"

# Chép nguyên văn từ contract ① — không sửa ở đây. Lệch một ký tự là Agent
# query ra rỗng mà không có gì để lần theo.
P95_LATENCY = """
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[1m])) by (le, service)
)
"""

ERROR_RATE = """
sum(rate(http_requests_total{status=~"5.."}[1m])) by (service)
  / sum(rate(http_requests_total[1m])) by (service)
"""

POOL_USAGE = "db_pool_connections_in_use / db_pool_size"

BASELINE_P95 = """
avg_over_time(
  histogram_quantile(0.95,
    sum(rate(http_request_duration_seconds_bucket[1m])) by (le, service)
  )[30m:1m]
)
"""

# Tiêu chí "xong" của START-HERE: in ra được avg latency của dummy service.
AVG_LATENCY = """
sum(rate(http_request_duration_seconds_sum[1m])) by (service)
  / sum(rate(http_request_duration_seconds_count[1m])) by (service)
"""

# ---------------------------------------------------------------------------
# Bản đề xuất sửa contract ① — lý do ở spike/README.md, số liệu do script này in
# ---------------------------------------------------------------------------

# Sửa 1: `sum(...{status=~"5.."})` không sinh series nào khi service khoẻ, nên
# cả phép chia trả RỖNG thay vì 0. Agent không phân biệt được "không có lỗi"
# với "mất metric". Cộng thêm một vế `* 0` để luôn có series, giữ label service.
FIXED_ERROR_RATE = """
(
  sum by (service) (rate(http_requests_total{handler!="/metrics", status=~"5.."}[1m]))
  or
  sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m])) * 0
)
/ sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m]))
"""

# Sửa 2: Prometheus tự scrape `/metrics` mỗi 5s, và request đó rất nhanh nên
# nó kéo tụt mọi con số tổng hợp. Phải loại handler đó ra khỏi mọi câu query.
FIXED_P95_LATENCY = """
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket{handler!="/metrics"}[1m])) by (le, service)
)
"""

FIXED_AVG_LATENCY = """
sum(rate(http_request_duration_seconds_sum{handler!="/metrics"}[1m])) by (service)
  / sum(rate(http_request_duration_seconds_count{handler!="/metrics"}[1m])) by (service)
"""


class PrometheusQuerier:
    """Client tối thiểu cho Prometheus HTTP API.

    Chỉ cần hai thao tác: chạy một câu PromQL instant, và lấy ra một con số cho
    một service cụ thể. Node `detect` không cần gì hơn.
    """

    def __init__(self, base_url: str = PROMETHEUS_URL, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def query(self, promql: str) -> list[dict]:
        """Chạy PromQL instant query.

        Returns:
            Danh sách series, mỗi phần tử có `metric` (dict label) và `value`.

        Raises:
            RuntimeError: khi Prometheus trả status != success — sai cú pháp
                PromQL rơi vào đây, và phải nổ to chứ không được nuốt.
        """
        response = httpx.get(
            f"{self._base_url}/api/v1/query",
            params={"query": promql},
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("status") != "success":
            raise RuntimeError(f"Prometheus từ chối query: {payload.get('error', payload)}")

        return payload["data"]["result"]

    def scalar_for_service(self, promql: str, service: str) -> float | None:
        """Lấy giá trị của một service từ câu query.

        Returns:
            Giá trị float, hoặc None nếu query không trả series nào cho service
            đó — **None nghĩa là contract đang vỡ**, không phải nghĩa là 0.
        """
        for series in self.query(promql):
            if series["metric"].get("service") == service:
                return float(series["value"][1])
        return None

    def targets_up(self) -> list[str]:
        """Danh sách label `service` của các target đang UP."""
        response = httpx.get(
            f"{self._base_url}/api/v1/targets",
            params={"state": "active"},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return [
            target["labels"].get("service", target["labels"].get("job", "?"))
            for target in response.json()["data"]["activeTargets"]
            if target["health"] == "up"
        ]


def _check(label: str, value: float | None, unit: str = "") -> bool:
    """In một dòng kết quả. Trả về True nếu query có số dùng được.

    NaN cũng là FAIL: nó là kết quả của 0/0 khi không có traffic nào trong cửa
    sổ 1 phút. Agent phải phân biệt được với giá trị 0 thật.
    """
    if value is None:
        print(f"  ✗ {label:.<42} KHÔNG CÓ DỮ LIỆU (query trả rỗng)")
        return False
    if value != value:  # NaN
        print(f"  ✗ {label:.<42} NaN (không có request nào trong 1 phút qua)")
        return False
    print(f"  ✓ {label:.<42} {value:.4f}{unit}")
    return True


def main() -> int:
    # Console Windows mặc định là cp1252, không in được tiếng Việt và sẽ nổ
    # UnicodeEncodeError giữa chừng. Ép UTF-8 để script chạy được trên cả
    # Windows lẫn Linux (CI).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    querier = PrometheusQuerier()

    print(f"Prometheus: {PROMETHEUS_URL}")
    print(f"Service   : {SERVICE}\n")

    print("1. Target đang UP")
    try:
        up = querier.targets_up()
    except httpx.HTTPError as error:
        print(f"  ✗ Không gọi được Prometheus: {error}")
        print("    Đã chạy `cd spike && docker compose up -d` chưa?")
        return 1

    if SERVICE not in up:
        print(f"  ✗ {SERVICE} không nằm trong target UP: {up or 'không có target nào'}")
        return 1
    print(f"  ✓ {', '.join(up)}\n")

    print("2. Bốn câu PromQL của contract ① — nguyên văn")
    contract = {
        "p95 latency": (querier.scalar_for_service(P95_LATENCY, SERVICE), " s"),
        "tỷ lệ lỗi 5xx": (querier.scalar_for_service(ERROR_RATE, SERVICE), ""),
        "mức dùng pool": (querier.scalar_for_service(POOL_USAGE, SERVICE), ""),
        "baseline p95 (30m)": (querier.scalar_for_service(BASELINE_P95, SERVICE), " s"),
    }
    # Ép sang list trước: `all()` trên generator sẽ dừng ở FAIL đầu tiên và
    # nuốt mất kết quả của các query sau.
    checks = [_check(label, value, unit) for label, (value, unit) in contract.items()]
    ok = all(checks)

    print("\n3. Bản đề xuất sửa (loại handler /metrics, tỷ lệ lỗi luôn có series)")
    fixed_p95 = querier.scalar_for_service(FIXED_P95_LATENCY, SERVICE)
    fixed_error = querier.scalar_for_service(FIXED_ERROR_RATE, SERVICE)
    fixed_avg = querier.scalar_for_service(FIXED_AVG_LATENCY, SERVICE)
    fixed_ok = all(
        [
            _check("p95 latency (đã sửa)", fixed_p95, " s"),
            _check("tỷ lệ lỗi 5xx (đã sửa)", fixed_error, ""),
            _check("avg latency (đã sửa)", fixed_avg, " s"),
        ]
    )

    print("\n4. Tiêu chí xong của START-HERE")
    avg_latency = querier.scalar_for_service(AVG_LATENCY, SERVICE)
    if avg_latency is None:
        print("  ✗ không tính được avg latency")
        return 1
    print(f"  avg latency = {avg_latency:.3f} s   (nguyên văn contract ①)")
    if fixed_avg is not None:
        print(f"  avg latency = {fixed_avg:.3f} s   (loại /metrics — con số thật của /pay)")

    p95, baseline = contract["p95 latency"][0], contract["baseline p95 (30m)"][0]
    if p95 is not None and baseline:
        print(f"\n5. So baseline: p95 lệch {p95 / baseline:.1f}x so với baseline 30 phút")

    print()
    if ok:
        print("KẾT LUẬN: contract ① nguyên văn chạy được, dùng cho Agent.")
    elif fixed_ok:
        print("KẾT LUẬN: contract ① nguyên văn CÓ QUERY TRẢ RỖNG, bản sửa chạy đủ.")
        print("          → mở PR sửa contract ① trước khi viết node detect.")
    else:
        print("KẾT LUẬN: cả hai bản đều thiếu dữ liệu — kiểm tra lại stack.")
    return 0 if (ok or fixed_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
