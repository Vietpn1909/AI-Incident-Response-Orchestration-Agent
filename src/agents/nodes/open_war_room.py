"""Node `open_war_room` — mở Jira Issue làm không gian xử lý sự cố.

CHỦ SỞ HỮU: Việt · dùng contract ③ (`src/services/jira/`)

Luật quan trọng nhất của node này: **gọi `find_open_incident()` TRƯỚC
`create_incident()`**. Agent poll vài giây một lần, mà một sự cố kéo dài hàng
chục phút — không có bước chống trùng thì mỗi vòng poll lại mở một issue mới và
war room biến thành bãi rác đúng lúc người trực cần nó nhất.

Node chỉ tạo issue và post bối cảnh. Nó không chẩn đoán (việc của `hypothesize`)
và tuyệt đối không đề xuất hành động (việc của `propose_remediation`, sau đó
Agent dừng chờ người duyệt).
"""

from __future__ import annotations

import logging

from src.agents.state import IncidentAgentState
from src.config import get_settings
from src.models.incident import IncidentSignal
from src.services.jira import FakeJiraClient, JiraApiError, JiraClient, RealJiraClient

logger = logging.getLogger(__name__)


def build_jira_client() -> JiraClient:
    """Chọn bản cài đặt Jira theo cấu hình.

    Thiếu cấu hình Jira thì dùng `FakeJiraClient` thay vì nổ: Việt phát triển
    Agent trên máy không có Jira workspace, và đây cũng là đường lùi nếu Jira
    gặp sự cố đúng hôm demo. Có log rõ ràng để không ai tưởng nhầm là đang ghi
    lên Jira thật.

    Tách thành hàm riêng để test monkeypatch được.
    """
    settings = get_settings()
    if not (settings.jira_base_url and settings.jira_email and settings.jira_api_token):
        logger.warning("Chưa cấu hình Jira — dùng FakeJiraClient, incident CHỈ nằm trong bộ nhớ")
        return FakeJiraClient(verbose=False)

    return RealJiraClient(
        base_url=settings.jira_base_url,
        email=settings.jira_email,
        api_token=settings.jira_api_token,
        project_key=settings.jira_project_key,
    )


def open_war_room_node(state: IncidentAgentState) -> dict:
    """Mở war room cho tín hiệu chính, hoặc dùng lại issue đang mở.

    Returns:
        `{"jira_key": ...}`. Chuỗi rỗng nghĩa là không mở được — kèm `error`.
    """
    signal = state.get("signal")
    if signal is None:
        return {"jira_key": ""}

    client = build_jira_client()

    try:
        existing = client.find_open_incident(signal.affected_service)
        if existing:
            # Sự cố vẫn đang diễn ra, chỉ cập nhật thêm vào issue cũ.
            client.add_comment(existing, _context_comment(signal))
            logger.info("open_war_room: %s đã có incident mở %s, không tạo trùng", signal.affected_service, existing)
            return {"jira_key": existing}

        jira_key = client.create_incident(signal)
        client.add_comment(jira_key, _context_comment(signal))
        logger.warning("open_war_room: mở %s cho %s", jira_key, signal.affected_service)
        return {"jira_key": jira_key}

    except JiraApiError as error:
        # Không mở được war room thì dừng vòng này, nhưng KHÔNG được im lặng —
        # sự cố vẫn đang xảy ra, chỉ là chưa ai được báo.
        logger.error("open_war_room: Jira từ chối — %s", error)
        return {"jira_key": "", "error": f"Không mở được war room: {error}"}


def _context_comment(signal: IncidentSignal) -> str:
    """Bối cảnh ban đầu, dạng text để đọc thẳng trên Jira.

    Mỗi bằng chứng kèm câu PromQL đã dùng — người trực copy vào Prometheus là
    kiểm chứng lại được ngay, không phải tin lời Agent. Đây là yêu cầu "chẩn
    đoán có bằng chứng" của đề bài, áp dụng từ comment đầu tiên.
    """
    dong = [
        f"Agent phát hiện bất thường ở *{signal.affected_service}*.",
        "",
        f"- Mức độ: {signal.severity.value}",
        f"- Vượt ngưỡng liên tục: {signal.breached_for_seconds:.0f}s",
        f"- {signal.metric_name}: {signal.metric_value:.2f} (ngưỡng {signal.threshold:.2f})",
        "",
        "Bằng chứng số:",
    ]

    for evidence in signal.evidence:
        lech = ""
        if evidence.deviation_ratio is not None:
            lech = f", lệch {evidence.deviation_ratio:.1f}x so baseline {evidence.baseline:.2f}"
        dong.append(f"- {evidence.name} = {evidence.value:.4g}{evidence.unit}{lech}")
        if evidence.promql:
            dong.append(f"  PromQL: {' '.join(evidence.promql.split())}")

    dong += ["", "_Chưa có đề xuất khắc phục. Agent đang thu thập bối cảnh._"]
    return "\n".join(dong)
