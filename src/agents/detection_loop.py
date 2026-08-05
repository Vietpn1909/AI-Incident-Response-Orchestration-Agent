"""Vòng quét của Agent — chạy state machine một lượt và gói kết quả lại.

Đây là mảnh làm cho demo chạy được **không cần script tay**: bắn tải vào service
demo, và một Jira issue thật tự xuất hiện.

Từ 03/08 phần bên trong là LangGraph ([`incident_graph.py`](incident_graph.py)),
không còn là vòng lặp tuần tự. **Chữ ký `run_cycle()` và `CycleResult` giữ
nguyên** — `scripts/run_agent.py` và toàn bộ test của Đức chạy y như cũ, nhờ vậy
chúng trở thành bằng chứng việc đổi sang graph không làm đổi hành vi.

Chạy:
    python scripts/run_agent.py --fake
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.agents.incident_graph import build_incident_graph
from src.services.jira import JiraClient
from src.services.prometheus import PrometheusClient

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
    """Một vòng: đọc Prometheus → phân loại → mở hoặc cập nhật war room.

    Lỗi Prometheus được bắt trong node `detect` và trả về ở `CycleResult.error`
    thay vì ném ra: Agent chạy vòng lặp dài, một lần Prometheus chớp tắt không
    được làm chết cả tiến trình. Nhưng nó **được log ở mức error** — Agent mù mà
    im lặng là tình huống nguy hiểm nhất.

    Graph được dựng lại mỗi vòng. Compile tốn không đáng kể so với 16 câu PromQL
    của một vòng quét (~2,2s đo ngày 02/08), và đổi lại thì hàm này không giữ
    trạng thái gì giữa các vòng — quan trọng khi client bị thay giữa chừng lúc
    test.
    """
    agent = build_incident_graph(prometheus_client, jira)
    state = agent.invoke({})

    return CycleResult(
        detected=len(state.get("signals") or []),
        opened=list(state.get("opened") or []),
        updated=list(state.get("updated") or []),
        error=state.get("error"),
    )
