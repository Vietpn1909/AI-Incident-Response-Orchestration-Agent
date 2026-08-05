"""Nâng severity khi sự cố lan sang nhiều service.

CHỦ SỞ HỮU: Việt

`rules.detect()` đã gán severity cho từng tín hiệu, nhưng nó chỉ nhìn được
**một** service. Bảng severity của [contract ①](../../../docs/contracts/01-metrics.md)
có một vế không quyết được từ góc nhìn đó:

    P1 | p95 > 10s **hoặc** lỗi > 50% **hoặc** ≥ 2 service bị ảnh hưởng

Vế thứ ba chỉ thấy khi đã có đủ tín hiệu của cả vòng quét. Hai service mỗi cái
p95 = 3s, xét riêng thì cả hai là P2; xét cùng nhau thì đó là sự cố đang lan,
và theo contract là P1.

Module này **không** gộp các tín hiệu lại thành một. Mỗi service vẫn có war room
riêng — đúng như `src/api/fixtures/incidents.json` mô tả (INC-12 và INC-13 là
hai issue nối với nhau, không phải một issue hai service). Việc nối do
`link_incidents` làm sau.
"""

from __future__ import annotations

import logging

from src.models.incident import IncidentSignal
from src.services import rules

logger = logging.getLogger(__name__)


def escalate_spreading(signals: list[IncidentSignal], within_seconds: float = 60.0) -> list[IncidentSignal]:
    """Tính lại severity khi phát hiện sự cố lan sang service khác.

    Args:
        signals: Tín hiệu của một vòng quét, từ `detect_incidents()`.
        within_seconds: Hai service phát hiện cách nhau trong khoảng này thì
            tính là cùng một vụ. Mặc định 60s — trong test thật
            `service-dat-hang` suy giảm chậm hơn `service-thanh-toan` khoảng
            30 giây, nên đây là biên an toàn gấp đôi.

    Returns:
        Danh sách mới, cùng thứ tự. Không sửa tại chỗ — tín hiệu là dữ liệu
        dùng chung, sửa ngầm thì chỗ gọi khác thấy giá trị lạ mà không hiểu vì
        sao.
    """
    if not rules.is_spreading(signals, within_seconds=within_seconds):
        return signals

    affected = len({signal.affected_service for signal in signals})
    logger.warning(
        "Sự cố lan sang %d service — tính lại severity theo contract ①",
        affected,
    )
    return [_with_service_count(signal, affected) for signal in signals]


def _with_service_count(signal: IncidentSignal, affected_service_count: int) -> IncidentSignal:
    """Gán lại severity cho một tín hiệu khi đã biết có bao nhiêu service dính.

    Gọi lại `rules.classify_severity()` thay vì gán thẳng `P1`: bảng ngưỡng chỉ
    được nằm ở một chỗ. Contract đổi vế "≥ 2 service" thì sửa `rules.py` là
    xong, file này không phải đụng tới.
    """
    severity = rules.classify_severity(
        p95=_evidence_value(signal, "http_request_duration_seconds p95"),
        error_rate=_evidence_value(signal, "tỷ lệ lỗi 5xx"),
        affected_service_count=affected_service_count,
    )
    if severity == signal.severity:
        return signal

    logger.info("%s: %s → %s", signal.affected_service, signal.severity.value, severity.value)
    return signal.model_copy(update={"severity": severity})


def _evidence_value(signal: IncidentSignal, name: str) -> float:
    """Đọc lại một số đo từ bằng chứng của tín hiệu.

    `IncidentSignal` chỉ có chỗ cho một metric chính, nên số liệu đầy đủ nằm ở
    `evidence`. Thiếu bằng chứng thì trả 0.0 — khi đó `classify_severity()` vẫn
    cho ra P1 nhờ vế số service, chỉ là không nâng nhầm vì lý do khác.
    """
    for evidence in signal.evidence:
        if evidence.name == name:
            return evidence.value
    return 0.0
