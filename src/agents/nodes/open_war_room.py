"""Node `open_war_room` — mở Jira issue cho một tín hiệu sự cố.

CHỦ SỞ HỮU: Việt. File này Đức viết hộ ngày 02/08 lúc Việt vắng.

Luật quan trọng nhất ở đây: **gọi `find_open_incident()` TRƯỚC
`create_incident()`**. Thiếu bước đó thì lúc load test, mỗi vòng poll của Agent
lại mở một issue mới cho cùng một sự cố — sau 5 phút war room có hàng chục issue
giống hệt nhau và trở thành rác.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.models.incident import IncidentSignal
from src.services.jira import JiraClient
from src.services.status_updater import ts

logger = logging.getLogger(__name__)


@dataclass
class WarRoomResult:
    """Kết quả mở war room.

    `created=False` nghĩa là service đã có incident đang mở và Agent chỉ cập
    nhật vào issue cũ — đây là đường đi **bình thường** khi Agent poll liên tục
    trong lúc sự cố còn kéo dài, không phải lỗi.
    """

    jira_key: str
    created: bool


def open_war_room(jira: JiraClient, signal: IncidentSignal) -> WarRoomResult:
    """Mở war room, hoặc cập nhật vào issue đang mở nếu đã có.

    Args:
        jira: `FakeJiraClient` khi phát triển, `RealJiraClient` khi chạy thật —
            code này không phân biệt, đó là mục đích của contract ③.
        signal: Tín hiệu từ [`detect`](detect.py).

    Returns:
        `WarRoomResult` — key của issue, và có phải vừa tạo mới không.

    ⚠️ **Hàm này KHÔNG còn tự post bằng chứng lúc tạo issue.** Việc đó chuyển
    sang `status_detected()` do `incident_graph.open_war_rooms()` gọi, để tránh
    hai comment cùng nội dung trên một war room.

    Hệ quả: gọi `open_war_room()` trực tiếp — trong script, test, hay một node
    mới — sẽ tạo ra issue KHÔNG có dòng bằng chứng nào, và không có gì báo lỗi.
    Ai gọi ngoài graph thì phải tự post `status_detected(signal)` kèm theo.
    """
    service = signal.affected_service

    # ⚠️ Bước chống mở trùng. Phải đứng trước create_incident().
    existing = jira.find_open_incident(service)
    if existing:
        logger.info("%s đã có incident đang mở (%s) — cập nhật thay vì mở mới", service, existing)
        # Agent auto-comment: cập nhật tín hiệu vẫn còn (cùng format status_updater)
        jira.add_comment(
            existing,
            f"🔄 [{ts(signal.detected_at)}] TÍN HIỆU VẪN CÒN\n\n"
            f"Metric: {signal.metric_name} = {signal.metric_value:.3f} "
            f"(ngưỡng {signal.threshold:.3f})\n"
            f"Vượt ngưỡng liên tục: {signal.breached_for_seconds:.0f}s\n\n"
            f"Agent tiếp tục theo dõi.",
        )
        return WarRoomResult(jira_key=existing, created=False)

    jira_key = jira.create_incident(signal)
    logger.info("Mở war room %s cho %s (%s)", jira_key, service, signal.severity.value)

    # KHÔNG post "Bối cảnh" ở đây nữa — status_detected() trong incident_graph.py
    # đã post đầy đủ metric evidence ngay sau khi tạo issue.

    return WarRoomResult(jira_key=jira_key, created=True)
