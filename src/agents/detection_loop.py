"""Vòng lặp phát hiện — nối `detect` với `open_war_room`.

Đây là mảnh làm cho demo chạy được **không cần script tay**: bắn tải vào service
demo, và một Jira issue thật tự xuất hiện.

Chưa phải LangGraph. Đây là vòng lặp tuần tự tối thiểu để chuỗi thông; khi Việt
dựng state machine đầy đủ thì thay chỗ này, hai node bên dưới giữ nguyên.

Chạy:
    python scripts/run_agent.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.agents.nodes.classify_severity import escalate_spreading
from src.agents.nodes.detect import detect_incidents
from src.agents.nodes.open_war_room import open_war_room
from src.services.jira import JiraClient
from src.services.prometheus import PrometheusClient, PrometheusError

logger = logging.getLogger(__name__)


@dataclass
class CycleResult:
    """Kết quả một vòng quét."""

    detected: int = 0
    opened: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def quiet(self) -> bool:
        """Không phát hiện gì và không lỗi — trạng thái bình thường."""
        return self.detected == 0 and self.error is None


def run_cycle(prometheus_client: PrometheusClient, jira: JiraClient) -> CycleResult:
    """Một vòng: đọc Prometheus → quyết định → mở hoặc cập nhật war room.

    Lỗi Prometheus được bắt và trả về trong `CycleResult.error` thay vì ném ra:
    Agent chạy vòng lặp dài, một lần Prometheus chớp tắt không được làm chết cả
    tiến trình. Nhưng nó **được log ở mức error** — Agent mù mà im lặng là tình
    huống nguy hiểm nhất.
    """
    try:
        signals = detect_incidents(prometheus_client)
    except PrometheusError as exc:
        logger.error("Không đọc được Prometheus: %s", exc)
        return CycleResult(error=str(exc))

    # Phải chạy TRƯỚC khi mở war room: vế "≥ 2 service → P1" của contract ① chỉ
    # thấy được khi nhìn cả vòng quét, mà severity thì đi vào tiêu đề issue lúc
    # tạo. Nâng sau khi đã tạo issue thì tiêu đề mang mức sai.
    signals = escalate_spreading(signals)

    result = CycleResult(detected=len(signals))
    for signal in signals:
        outcome = open_war_room(jira, signal)
        (result.opened if outcome.created else result.updated).append(outcome.jira_key)
    return result
