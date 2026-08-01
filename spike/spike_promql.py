"""Kiểm tra các câu PromQL đang được ship có thật sự chạy trên Prometheus.

Ban đầu script này là spike verify giả định kỹ thuật trước khi viết Agent
(2026-07-29). Nay nó giữ vai trò lâu dài hơn: **bắn thẳng các hằng trong
[`src/services/prometheus.py`](../src/services/prometheus.py) vào Prometheus
thật** và báo lỗi nếu câu nào không trả về số dùng được.

Vì sao cần: PromQL sai không ném exception. Prometheus trả kết quả rỗng, hoặc
tệ hơn là trả `NaN`, và Agent im lặng không phát hiện gì. Hai lỗi đã bắt được
theo đúng cách này:

- Bucket mặc định của instrumentator làm `histogram_quantile` kẹp p95 về 1.0,
  khiến ngưỡng P1/P2 không bao giờ kích hoạt (2026-07-29)
- `P95_BASELINE_30M` trả `NaN` khi service có khoảng lặng không request, khiến
  mức P4 không bao giờ kích hoạt (2026-07-30)

Cả hai đều "chạy được" và trả ra số. Vì vậy script coi **rỗng và `NaN` đều là
FAIL**, không coi chúng là 0.

Script KHÔNG giữ bản sao của câu query. Hai bản sao là hai chỗ để sai lệch
nhau — nguồn duy nhất là `src/services/prometheus.py`.

    cd spike && docker compose up -d --build
    python spike/loadgen.py --concurrency 150 --seconds 90
    python spike/spike_promql.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

# Chạy được bằng `python spike/spike_promql.py` từ gốc repo: thêm gốc repo vào
# sys.path để import được `src`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services import prometheus as promql  # noqa: E402

PROMETHEUS_URL = "http://localhost:9090"
SERVICE = "service-thanh-toan"

#: Các hằng được kiểm tra, theo thứ tự Agent dùng đến.
CHECKED = [
    ("P95_LATENCY", promql.P95_LATENCY, " s"),
    ("ERROR_RATE", promql.ERROR_RATE, ""),
    ("POOL_SATURATION", promql.POOL_SATURATION, ""),
    ("POOL_SATURATION_PEAK_5M", promql.POOL_SATURATION_PEAK_5M, ""),
    ("P95_BASELINE_30M", promql.P95_BASELINE_30M, " s"),
    ("AVG_LATENCY", promql.AVG_LATENCY, " s"),
]


class PrometheusQuerier:
    """Client tối thiểu cho Prometheus HTTP API.

    Đây là bản chạy được của `PrometheusClient.query()` trong
    `src/services/prometheus.py` — chuyển sang đó khi cài đặt `TODO(Việt)`.
    """

    def __init__(self, base_url: str = PROMETHEUS_URL, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def query(self, promql_expr: str) -> list[dict]:
        """Chạy PromQL instant query.

        Raises:
            RuntimeError: khi Prometheus trả status != success — sai cú pháp
                PromQL rơi vào đây, và phải nổ to chứ không được nuốt.
        """
        response = httpx.get(
            f"{self._base_url}/api/v1/query",
            params={"query": promql_expr},
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("status") != "success":
            raise RuntimeError(f"Prometheus từ chối query: {payload.get('error', payload)}")

        return payload["data"]["result"]

    def scalar_for_service(self, promql_expr: str, service: str) -> float | None:
        """Giá trị của một service. None nghĩa là query không trả series nào."""
        for series in self.query(promql_expr):
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
    """In một dòng kết quả. True nếu query cho số dùng được.

    Rỗng và NaN đều là FAIL. NaN là kết quả của 0/0 khi không có traffic, và nó
    nguy hiểm hơn rỗng: mọi so sánh ngưỡng với NaN đều trả False nên Agent bỏ
    lọt sự cố mà không có dấu hiệu gì.
    """
    if value is None:
        print(f"  ✗ {label:.<28} KHÔNG CÓ DỮ LIỆU (query trả rỗng)")
        return False
    if value != value:  # NaN
        print(f"  ✗ {label:.<28} NaN — xem chú thích trong prometheus.py")
        return False
    print(f"  ✓ {label:.<28} {value:.4f}{unit}")
    return True


def main() -> int:
    # Console Windows mặc định cp1252, không in được tiếng Việt và sẽ nổ
    # UnicodeEncodeError giữa chừng. Ép UTF-8 để chạy được trên cả Windows lẫn CI.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    querier = PrometheusQuerier()

    print(f"Prometheus: {PROMETHEUS_URL}")
    print(f"Service   : {SERVICE}")
    print("Nguồn query: src/services/prometheus.py\n")

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

    # Không có request nào thì các câu có phép chia trả RỖNG — đúng như thiết
    # kế, không phải hỏng. Phải có traffic mới phán xét được, nếu không script
    # sẽ báo lỗi giả mỗi lần chạy trên stack vừa dựng.
    print("2. Có traffic để đo không")
    request_rate = querier.scalar_for_service(
        'sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m]))',
        SERVICE,
    )
    if not request_rate:
        print("  ⚠️ Service không nhận request nào trong 1 phút qua.")
        print("     Các câu có phép chia sẽ trả rỗng — đó là ĐÚNG, không phải lỗi.")
        print("     Sinh tải rồi chạy lại:")
        print("       python spike/loadgen.py --concurrency 150 --seconds 90")
        return 2
    print(f"  ✓ {request_rate:.1f} request/s\n")

    print("3. Các câu PromQL đang được ship")
    values: dict[str, float | None] = {}
    passed = []
    for name, expr, unit in CHECKED:
        value = querier.scalar_for_service(expr, SERVICE)
        values[name] = value
        passed.append(_check(name, value, unit))

    print("\n4. Tiêu chí xong của START-HERE")
    avg_latency = values["AVG_LATENCY"]
    if avg_latency is not None and avg_latency == avg_latency:
        print(f"  avg latency = {avg_latency:.3f} s")
    else:
        print("  ✗ không tính được avg latency")

    p95, baseline = values["P95_LATENCY"], values["P95_BASELINE_30M"]
    if p95 is not None and baseline:
        ratio = p95 / baseline
        print(f"\n5. So baseline: p95 lệch {ratio:.1f}x")
        if ratio < 1.5:
            print("   ⚠️ Độ lệch quá thấp để làm bằng chứng. Baseline chỉ có nghĩa khi")
            print("      TRƯỚC lúc tăng tải đã có traffic nền — cần warm-up trong load test.")

    print()
    if all(passed):
        print("KẾT LUẬN: mọi câu query đang ship đều trả số dùng được.")
        return 0
    print("KẾT LUẬN: CÓ QUERY HỎNG — sửa src/services/prometheus.py trước khi viết node.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
