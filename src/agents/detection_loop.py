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
from src.agents.war_room_registry import WarRoomRegistry
from src.services.incident_alert import IncidentAlerter
from src.services.jira import JiraClient
from src.services.meeting_room import DailyRoomClient
from src.services.prometheus import PrometheusClient

logger = logging.getLogger(__name__)


@dataclass
class CycleResult:
    """Kết quả một vòng quét."""

    detected: int = 0
    opened: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    #: `{jira key: URL phòng họp}` của các war room vừa mở mới ở vòng này. Rỗng
    #: là bình thường: chưa cấu hình `DAILY_API_KEY`, hoặc sự cố dưới mức P2.
    meeting_rooms: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    @property
    def quiet(self) -> bool:
        """Không phát hiện gì và không lỗi — trạng thái bình thường."""
        return self.detected == 0 and self.error is None


def run_cycle(
    prometheus_client: PrometheusClient,
    jira: JiraClient,
    *,
    room: DailyRoomClient | None = None,
    alerter: IncidentAlerter | None = None,
    registry: WarRoomRegistry | None = None,
) -> CycleResult:
    """Một vòng: đọc Prometheus → phân loại → mở hoặc cập nhật war room.

    Lỗi Prometheus được bắt trong node `detect` và trả về ở `CycleResult.error`
    thay vì ném ra: Agent chạy vòng lặp dài, một lần Prometheus chớp tắt không
    được làm chết cả tiến trình. Nhưng nó **được log ở mức error** — Agent mù mà
    im lặng là tình huống nguy hiểm nhất.

    Graph được dựng lại mỗi vòng. Compile tốn không đáng kể so với 16 câu PromQL
    của một vòng quét (~2,2s đo ngày 02/08), và đổi lại thì hàm này không giữ
    trạng thái gì giữa các vòng — quan trọng khi client bị thay giữa chừng lúc
    test.

    ⚠️ `registry` là ngoại lệ **có chủ đích** của câu "không giữ trạng thái gì
    giữa các vòng" ở trên. Trạng thái đó không nằm trong hàm này mà nằm ở object
    người gọi đưa vào — `run_cycle()` chỉ đọc ghi lên nó. Không có nó thì mỗi
    vòng poll lại mở một phòng họp mới và gửi lại một mail cảnh báo; xem
    `war_room_registry.py` để biết vì sao không thể suy ra từ state của graph.

    Args:
        prometheus_client: Nguồn tín hiệu.
        jira: Lớp quản lý vòng đời incident.
        room: Client mở phòng họp. `None` — mặc định — là tắt tính năng; giữ
            chữ ký cũ chạy y nguyên cho mọi caller và test đã có.
        alerter: Client gửi mail báo sự cố. `None` là tắt.
        registry: Trí nhớ xuyên vòng quét, do người gọi sở hữu.
    """
    agent = build_incident_graph(
        prometheus_client, jira, room=room, alerter=alerter, registry=registry
    )
    state = agent.invoke({})

    return CycleResult(
        detected=len(state.get("signals") or []),
        opened=list(state.get("opened") or []),
        updated=list(state.get("updated") or []),
        meeting_rooms=dict(state.get("meeting_rooms") or {}),
        error=state.get("error"),
    )
