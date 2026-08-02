"""Node `classify_severity` — chọn tín hiệu chính và nâng mức khi có lan truyền.

CHỦ SỞ HỮU: Việt

Thoạt nhìn node này thừa: `rules.detect()` đã gán severity rồi. Nhưng nó gán
được dựa trên **một service**, mà contract ① có một dòng không thể quyết từ góc
nhìn đó:

    P1 | p95 > 10s hoặc lỗi > 50% **hoặc ≥ 2 service bị ảnh hưởng**

Vế thứ ba chỉ nhìn thấy khi đã có đủ tín hiệu của cả vòng poll. Hai service mỗi
cái p95 = 3s, xét riêng thì cả hai là P2; xét cùng nhau thì đó là sự cố đang
lan, và theo contract là P1. Đây chính là việc của node này.

Nó cũng chọn ra **một** tín hiệu chính để mở war room, vì một sự cố lan sang
nhiều service vẫn là một sự cố — mở hai war room cho cùng một nguyên nhân thì
người trực phải đọc hai chỗ, và bước duyệt bị chia đôi.
"""

from __future__ import annotations

import logging

from src.agents.state import IncidentAgentState
from src.models.incident import IncidentSignal, Severity
from src.services import rules

logger = logging.getLogger(__name__)

#: Thứ tự nặng dần, dùng để chọn tín hiệu nghiêm trọng nhất.
_SEVERITY_ORDER = {Severity.P4: 0, Severity.P3: 1, Severity.P2: 2, Severity.P1: 3}


def classify_severity_node(state: IncidentAgentState) -> dict:
    """Chọn tín hiệu chính, nâng lên P1 nếu sự cố đang lan.

    Returns:
        `{"signal": ..., "signals": ..., "spreading": ...}`. `signal` là `None`
        khi không có gì bất thường — graph dừng ở đây, không mở war room.
    """
    signals = state.get("signals") or []
    if not signals:
        return {"signal": None, "spreading": False}

    spreading = rules.is_spreading(signals)

    if spreading:
        # Nâng TẤT CẢ, không chỉ tín hiệu chính: node `link_incidents` sẽ nối
        # các incident lại với nhau, và chúng phải cùng mức thì war room mới
        # nhất quán.
        affected = len({signal.affected_service for signal in signals})
        signals = [_escalate(signal, affected) for signal in signals]
        logger.warning(
            "classify_severity: sự cố lan sang %d service — nâng lên %s",
            affected,
            Severity.P1.value,
        )

    primary = max(signals, key=lambda signal: (_SEVERITY_ORDER[signal.severity], -signal.detected_at.timestamp()))

    return {"signal": primary, "signals": signals, "spreading": spreading}


def _escalate(signal: IncidentSignal, affected_service_count: int) -> IncidentSignal:
    """Tính lại severity của một tín hiệu khi biết có bao nhiêu service bị ảnh hưởng.

    Gọi lại `rules.classify_severity()` thay vì gán thẳng `P1`: bảng ngưỡng chỉ
    được phép nằm ở một chỗ. Nếu sau này contract đổi vế "≥ 2 service" thì sửa
    `rules.py` là xong, node này không phải đụng tới.
    """
    severity = rules.classify_severity(
        p95=_metric(signal, "http_request_duration_seconds p95"),
        error_rate=_metric(signal, "tỷ lệ lỗi 5xx"),
        affected_service_count=affected_service_count,
    )
    if severity == signal.severity:
        return signal
    return signal.model_copy(update={"severity": severity})


def _metric(signal: IncidentSignal, name: str) -> float:
    """Đọc lại một số đo từ bằng chứng của tín hiệu.

    Bằng chứng là nơi duy nhất giữ đủ số liệu — `IncidentSignal` chỉ có chỗ cho
    một metric chính. Thiếu bằng chứng thì trả 0.0, khi đó `classify_severity`
    vẫn cho ra P1 nhờ vế số service, chỉ là không nâng nhầm vì lý do khác.
    """
    for evidence in signal.evidence:
        if evidence.name == name:
            return evidence.value
    return 0.0
