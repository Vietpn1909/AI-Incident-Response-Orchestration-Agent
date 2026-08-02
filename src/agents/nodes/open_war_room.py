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
    """
    service = signal.affected_service

    # ⚠️ Bước chống mở trùng. Phải đứng trước create_incident().
    existing = jira.find_open_incident(service)
    if existing:
        logger.info("%s đã có incident đang mở (%s) — cập nhật thay vì mở mới", service, existing)
        jira.add_comment(
            existing,
            f"Tín hiệu vẫn còn: {signal.metric_name} = {signal.metric_value:.3f} "
            f"(ngưỡng {signal.threshold:.3f}), đã vượt liên tục "
            f"{signal.breached_for_seconds:.0f}s.",
        )
        return WarRoomResult(jira_key=existing, created=False)

    jira_key = jira.create_incident(signal)
    logger.info("Mở war room %s cho %s (%s)", jira_key, service, signal.severity.value)

    if signal.evidence:
        lines = ["Bối cảnh thu thập được lúc phát hiện:"]
        for item in signal.evidence:
            ratio = item.deviation_ratio
            deviation = f" — lệch {ratio:.1f}× baseline" if ratio else ""
            lines.append(f"- {item.name}: {item.value:g}{item.unit}{deviation}")
        jira.add_comment(jira_key, "\n\n".join(lines))

    return WarRoomResult(jira_key=jira_key, created=True)
