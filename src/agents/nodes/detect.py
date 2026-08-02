"""Node `detect` — query PromQL, so baseline, quyết định có phải sự cố không.

CHỦ SỞ HỮU: Việt

Node đầu tiên của graph. Nó không tự nghĩ ra gì cả: lấy số từ Prometheus
(`services/prometheus.py`), đưa qua rule engine (`services/rules.py`), và trả
về danh sách tín hiệu. Mọi ngưỡng nằm ở `rules.py`, không nằm ở đây.

**Không hardcode danh sách service.** Prometheus trả về mỗi service một series,
nên service nào đang có traffic thì tự xuất hiện. Service không nhận request
nào sẽ không có trong kết quả — đúng ngữ nghĩa "rỗng = không có dữ liệu" mà
`PrometheusClient` đã chốt. Thêm service mới chỉ cần sửa `prometheus.yml`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from src.agents.state import IncidentAgentState
from src.config import get_settings
from src.models.incident import IncidentSignal
from src.services import prometheus, rules
from src.services.prometheus import PrometheusClient, PrometheusError

logger = logging.getLogger(__name__)


class BreachTracker:
    """Nhớ mỗi service đã vượt ngưỡng liên tục bao lâu.

    Vì sao cần một object có trạng thái: quy tắc "chỉ tính là incident khi vượt
    ngưỡng liên tục ≥ 30s" bắc qua **nhiều vòng poll**, mà state của LangGraph
    chỉ sống trong một lần chạy graph. Không có nó thì `breached_for_seconds`
    luôn là 0 và quy tắc chống nhiễu quan trọng nhất trở thành vô hiệu — lúc
    load test Agent sẽ mở hàng loạt incident trùng nhau.

    Cách dùng: gọi `update()` mỗi vòng poll cho mọi service đang quan sát.
    """

    def __init__(self) -> None:
        #: service -> thời điểm bắt đầu vượt ngưỡng liên tục
        self._since: dict[str, datetime] = {}

    def update(self, service: str, *, breaching: bool, now: datetime | None = None) -> float:
        """Cập nhật và trả về số giây đã vượt ngưỡng liên tục.

        Args:
            service: Tên service.
            breaching: Vòng poll này service có vượt ngưỡng không.
            now: Thời điểm hiện tại, để test bơm vào được.

        Returns:
            Số giây kể từ lúc bắt đầu vượt ngưỡng. `0.0` nếu đang bình thường,
            hoặc nếu vừa mới vượt ở vòng này.
        """
        moment = now or datetime.now(UTC)

        if not breaching:
            # Hồi phục thì xoá mốc: lần vượt ngưỡng sau phải đếm lại từ đầu,
            # nếu không thì hai sự cố cách nhau một tiếng bị cộng dồn thành một.
            self._since.pop(service, None)
            return 0.0

        started = self._since.setdefault(service, moment)
        return (moment - started).total_seconds()

    def forget(self, service: str) -> None:
        """Quên mốc của một service — dùng sau khi incident đã được xử lý xong."""
        self._since.pop(service, None)

    def tracked_services(self) -> set[str]:
        """Các service đang có mốc vượt ngưỡng."""
        return set(self._since)


#: Tracker dùng chung cho vòng poll của Agent. Đặt ở module vì nó phải sống lâu
#: hơn một lần chạy graph.
_tracker = BreachTracker()


def _by_service(samples: list[prometheus.MetricSample]) -> dict[str, float]:
    return {sample.service: sample.value for sample in samples}


def detect_node(state: IncidentAgentState) -> dict:
    """Query Prometheus, chạy rule engine, trả về mọi tín hiệu sự cố.

    Returns:
        `{"signals": [...]}`. Danh sách rỗng nghĩa là **đã kiểm tra và mọi thứ
        bình thường**. Nếu không query được Prometheus thì trả `{"error": ...}`
        thay vì danh sách rỗng — hai tình huống đó phải phân biệt được, xem
        `PrometheusError`.
    """
    client = _client()

    try:
        p95_now = _by_service(client.query(prometheus.P95_LATENCY))
        baseline = _by_service(client.query(prometheus.P95_BASELINE_30M))
        error_rate = _by_service(client.query(prometheus.ERROR_RATE))
        pool = _by_service(client.query(prometheus.POOL_SATURATION_PEAK_5M))
    except PrometheusError as error:
        # Không biết tình hình ra sao. Trả rỗng ở đây là nói dối rằng mọi thứ ổn.
        logger.error("detect: không đọc được metric — %s", error)
        return {"error": str(error), "signals": []}

    signals: list[IncidentSignal] = []
    for service, p95 in p95_now.items():
        breaching = _is_breaching(p95, baseline.get(service, 0.0), error_rate.get(service, 0.0))
        breached_for = _tracker.update(service, breaching=breaching)

        signal = rules.detect(
            p95_now=p95,
            p95_baseline=baseline.get(service, 0.0),
            error_rate=error_rate.get(service, 0.0),
            pool_saturation=pool.get(service, 0.0),
            service=service,
            breached_for_seconds=breached_for,
        )
        if signal is not None:
            signals.append(signal)
            logger.warning(
                "detect: %s vượt ngưỡng %.0fs — p95=%.2fs, lỗi=%.1f%%, pool=%.0f%%",
                service,
                breached_for,
                p95,
                error_rate.get(service, 0.0) * 100,
                pool.get(service, 0.0) * 100,
            )

    # Service đã hồi phục cũng phải được cập nhật, nếu không mốc vượt ngưỡng cũ
    # nằm lại mãi và lần sau vừa chớm vượt đã bị tính là đã kéo dài hàng giờ.
    for service in _tracker.tracked_services() - set(p95_now):
        _tracker.forget(service)

    return {"signals": signals}


def _is_breaching(p95: float, p95_baseline: float, error_rate: float) -> bool:
    """Vòng poll này service có bất thường không.

    Dùng đúng điều kiện của `rules.detect()`, chỉ khác là không xét thời gian —
    vì đây chính là thứ dùng để *đo* thời gian. Hai chỗ phải khớp nhau, lệch là
    tracker đếm một đằng còn rule engine kết luận một nẻo.
    """
    breached_hard = p95 > rules.P95_P3_SECONDS or error_rate > rules.ERROR_RATE_P3
    deviated = p95_baseline > 0 and p95 / p95_baseline >= rules.BASELINE_DEVIATION_RATIO
    return breached_hard or deviated


def _client() -> PrometheusClient:
    """Tạo client theo cấu hình. Tách thành hàm riêng để test thay được."""
    return PrometheusClient(base_url=get_settings().prometheus_url)
