"""Node `detect` — đọc Prometheus, quyết định có phải sự cố không.

CHỦ SỞ HỮU: Việt. File này Đức viết hộ ngày 02/08 lúc Việt vắng, để chuỗi
end-to-end chạy được. Việt cứ sửa thoải mái, nhất là chỗ đo `breached_for_seconds`.

Node này chỉ **đọc và quyết định**, không chạm Jira. Việc mở war room là của
[`open_war_room`](open_war_room.py) — tách ra để `detect` test được mà không
cần Jira, và để chống mở trùng nằm đúng một chỗ.
"""

from __future__ import annotations

import logging

from src.models.incident import IncidentSignal
from src.services import prometheus, rules
from src.services.prometheus import PrometheusClient

logger = logging.getLogger(__name__)

#: Các cửa sổ thời gian dùng để đo "đã vượt ngưỡng liên tục bao lâu".
#:
#: `rules.detect()` cần `breached_for_seconds`, mà Agent thì poll theo chu kỳ.
#: Giữ mốc bắt đầu trong bộ nhớ là cách dễ nghĩ nhất nhưng sai ở ba điểm:
#: restart Agent là mất, chạy nhiều instance thì mỗi con một số, và test phải
#: giả lập thời gian.
#:
#: Thay vào đó hỏi thẳng Prometheus: `min_over_time(p95[30s])` mà vẫn trên
#: ngưỡng nghĩa là suốt 30 giây đó chưa lúc nào tụt xuống. Stateless, restart
#: không ảnh hưởng, và test chỉ cần một `MockTransport`.
#:
#: Thử từ cửa sổ nhỏ tới lớn rồi lấy cửa sổ lớn nhất còn thoả — cho ra con số
#: xấp xỉ nhưng có thật, đủ để ghi vào war room ("vượt liên tục 120s").
SUSTAINED_PROBE_WINDOWS = (30, 60, 120, 300)

#: Bước lấy mẫu bên trong mỗi cửa sổ. Khớp `scrape_interval: 5s` của
#: [demo/prometheus.yml](../../../demo/prometheus.yml) — lấy dày hơn scrape thì
#: chỉ đọc lại cùng một điểm dữ liệu.
_PROBE_STEP_SECONDS = 5


def _samples_by_service(client: PrometheusClient, promql: str) -> dict[str, float]:
    """Chạy một câu PromQL, trả `{service: giá trị}`.

    Rỗng không phải lỗi — service chưa nhận request nào thì không có series.
    `PrometheusClient.query()` đã log warning cho trường hợp đó.
    """
    return {sample.service: sample.value for sample in client.query(promql)}


def _sustained(client: PrometheusClient, expr: str, threshold: float) -> dict[str, float]:
    """Cửa sổ lớn nhất mà `expr` chưa lúc nào tụt xuống dưới `threshold`.

    Service không vượt ngưỡng thì không có mặt trong kết quả.

    So bằng `>` cho cả ba đường đo, kể cả đường lệch baseline mà `rules.detect()`
    so bằng `>=`. Lệch nhau đúng tại điểm bằng nhau tuyệt đối — với số thực đọc
    từ Prometheus thì gần như không xảy ra, và sai về phía thận trọng (chậm
    một nhịp scrape) chứ không phải phía báo nhầm.
    """
    sustained: dict[str, float] = {}
    for window in SUSTAINED_PROBE_WINDOWS:
        promql = f"min_over_time(({expr})[{window}s:{_PROBE_STEP_SECONDS}s])"
        for service, value in _samples_by_service(client, promql).items():
            if value > threshold:
                sustained[service] = float(window)
    return sustained


def breached_seconds_by_service(client: PrometheusClient) -> dict[str, float]:
    """Mỗi service đã ở trạng thái bất thường liên tục bao nhiêu giây.

    Phải đo **cả ba** đường mà cửa 2 của `rules.detect()` chấp nhận, rồi lấy
    cửa sổ lớn nhất trong ba:

    1. p95 vượt ngưỡng cứng P3
    2. tỷ lệ lỗi 5xx vượt ngưỡng cứng P3
    3. p95 lệch baseline từ `BASELINE_DEVIATION_RATIO` lần trở lên

    ⚠️ Bản đầu của file này chỉ đo đường 1. Hệ quả: cửa 1 (`breached_for_seconds
    >= SUSTAINED_SECONDS`) luôn thấy 0 với sự cố **không** làm chậm latency, nên
    hai đường còn lại của `rules.detect()` vĩnh viễn không với tới được — đúng
    kịch bản UC-2, container OOM rồi restart, service phun 5xx trong khi những
    request còn sống vẫn nhanh như thường. Cửa lọc "đủ lâu" phải đo đúng cái
    điều kiện mà nó đang lọc.

    Dùng ngưỡng P3 (thấp nhất) chứ không phải P2: đây chỉ là cửa "đủ lâu",
    còn việc phân loại nặng nhẹ là của `rules.classify_severity()`. Chặn ở P2
    tại đây thì P3 và P4 vĩnh viễn không đạt tới được — cùng loại lỗi Việt đã
    ghi trong docstring `rules.detect()`.
    """
    latency = _sustained(client, prometheus.P95_LATENCY, rules.P95_P3_SECONDS)
    errors = _sustained(client, prometheus.ERROR_RATE, rules.ERROR_RATE_P3)
    # Baseline 0 (chưa có lịch sử) làm phép chia trả rỗng, không phải chia cho 0
    # — Prometheus bỏ hẳn series thay vì sinh Inf. Khớp với nhánh
    # `p95_baseline > 0` trong `rules.detect()`.
    deviation = _sustained(
        client,
        f"({prometheus.P95_LATENCY}) / ({prometheus.P95_BASELINE_30M})",
        rules.BASELINE_DEVIATION_RATIO,
    )

    sustained: dict[str, float] = {}
    for source in (latency, errors, deviation):
        for service, window in source.items():
            sustained[service] = max(sustained.get(service, 0.0), window)
    return sustained


def detect_incidents(client: PrometheusClient) -> list[IncidentSignal]:
    """Quét toàn bộ service, trả tín hiệu sự cố nếu có.

    Gọi 4 + 12 câu PromQL mỗi vòng (4 metric, và 4 cửa sổ × 3 đường đo thời
    lượng), không phụ thuộc số service — Prometheus trả tất cả service trong
    một lần.

    Đo trên stack demo ngày 02/08: một vòng đầy đủ mất khoảng **2,2 giây**, gần
    hết nằm ở 4 câu đo lệch baseline — mỗi câu bọc một `quantile_over_time` cửa
    sổ 30 phút bên trong một subquery. Với `--interval 10` thì Agent bận khoảng
    22% thời gian. Hạ interval xuống dưới 5s là hai vòng chồng lên nhau, cần đo
    lại trước khi làm.

    Returns:
        Danh sách `IncidentSignal`, rỗng nghĩa là mọi thứ bình thường.

    Raises:
        PrometheusError: không gọi được Prometheus hoặc PromQL sai cú pháp.
            KHÔNG nuốt lỗi ở đây — Agent mù mà tưởng "bình thường" là tình
            huống nguy hiểm nhất.
    """
    p95 = _samples_by_service(client, prometheus.P95_LATENCY)
    if not p95:
        logger.warning(
            "Không có series p95 nào. Service chưa nhận request, hoặc tên metric "
            "lệch so với thứ demo/ expose — xem docs/contracts/01-metrics.md."
        )
        return []

    baseline = _samples_by_service(client, prometheus.P95_BASELINE_30M)
    error_rate = _samples_by_service(client, prometheus.ERROR_RATE)
    pool = _samples_by_service(client, prometheus.POOL_SATURATION_PEAK_5M)
    sustained = breached_seconds_by_service(client)

    signals: list[IncidentSignal] = []
    for service, p95_now in p95.items():
        signal = rules.detect(
            p95_now=p95_now,
            p95_baseline=baseline.get(service, 0.0),
            error_rate=error_rate.get(service, 0.0),
            # service-dat-hang không có metric pool — 0.0 là đúng, nó không
            # dùng connection pool nên không thể là nguyên nhân gốc ở đó.
            pool_saturation=pool.get(service, 0.0),
            service=service,
            breached_for_seconds=sustained.get(service, 0.0),
        )
        if signal is None:
            continue
        logger.info(
            "Phát hiện sự cố %s trên %s: %s = %.3f (ngưỡng %.3f), vượt liên tục %.0fs",
            signal.severity.value,
            service,
            signal.metric_name,
            signal.metric_value,
            signal.threshold,
            signal.breached_for_seconds,
        )
        signals.append(signal)

    return signals
