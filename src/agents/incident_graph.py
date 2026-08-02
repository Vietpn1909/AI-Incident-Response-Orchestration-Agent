"""Graph của Agent ứng phó sự cố — sơ đồ ở docs/architecture_diagram.md mục 2.

CHỦ SỞ HỮU: Việt

Tách riêng khỏi `graph.py` (agent mẫu của template, phục vụ `/api/v1/chat`) —
hai thứ khác nhau hoàn toàn, gộp chung chỉ làm rối.

**Trạng thái hiện tại: ba node đầu.**

    detect → classify_severity → (có tín hiệu?) → open_war_room → END
                                        └── không ──────────────→ END

Graph chạy được với vài node đầu và mở rộng dần, đúng hướng dẫn ở
`nodes/README.md`. Các node còn lại (`gather_context`, `correlate_deploy`,
`hypothesize`, `link_incidents`, `propose_remediation`) nối thêm vào sau
`open_war_room` khi viết xong.

**Graph sẽ dừng ở `propose_remediation`, không có node thực thi.** Việc chuyển
sang `Remediating` do người duyệt làm trên Jira, và backend biết được qua
webhook — xem `src/api/webhooks.py` và `src/services/hitl.py`. Nếu có ai thêm
một node gọi `transition(..., REMEDIATING)` vào đây thì đó là dấu hiệu đang phá
ràng buộc bắt buộc của đề bài.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.agents.nodes.classify_severity import classify_severity_node
from src.agents.nodes.detect import detect_node
from src.agents.nodes.open_war_room import open_war_room_node
from src.agents.state import IncidentAgentState


def route_after_classify(state: IncidentAgentState) -> str:
    """Có đáng mở war room không.

    Dừng khi không có tín hiệu nào — đó là kết quả bình thường của phần lớn
    vòng poll, không phải lỗi.
    """
    if state.get("error"):
        return END
    if state.get("signal") is None:
        return END
    return "open_war_room"


def build_incident_graph():
    """Dựng và compile graph."""
    graph = StateGraph(IncidentAgentState)

    graph.add_node("detect", detect_node)
    graph.add_node("classify_severity", classify_severity_node)
    graph.add_node("open_war_room", open_war_room_node)

    graph.set_entry_point("detect")
    graph.add_edge("detect", "classify_severity")
    graph.add_conditional_edges(
        "classify_severity",
        route_after_classify,
        {"open_war_room": "open_war_room", END: END},
    )
    graph.add_edge("open_war_room", END)

    return graph.compile()


#: Compile sẵn một lần lúc import — dựng lại mỗi vòng poll là phí.
incident_agent = build_incident_graph()
