"""State machine LangGraph của Agent ứng phó sự cố.

CHỦ SỞ HỮU: Việt · sơ đồ ở [docs/architecture_diagram.md](../../docs/architecture_diagram.md) mục 2

Thay chỗ vòng lặp tuần tự Đức viết tạm ngày 02/08. **Ba node bên dưới giữ
nguyên chữ ký** — chúng vẫn là hàm thuần nhận dependency tường minh, graph chỉ
là lớp nối. Nhờ vậy chúng test được riêng mà không cần dựng graph, và toàn bộ
test của Đức chạy y nguyên qua đường mới.

    detect → classify_severity → (có tín hiệu?) → open_war_room → END
                                       └── không ──────────────→ END

**Vì sao đổi sang LangGraph khi vòng lặp cũ đã chạy được:**

1. `ARCHITECTURE.md` chốt Agent là state machine có cổng chờ người, không phải
   chuỗi ReAct. Bảy node còn lại nối vào đây thay vì nối vào một hàm `for`.
2. Nhánh rẽ sắp tới không biểu diễn gọn bằng `if`: `hypothesize` phải quay lại
   `propose_remediation` khi metric chưa hồi phục, và `escalate` quay lại
   `await_approval`. Đó là cạnh trong đồ thị, không phải câu lệnh tuần tự.
3. LangGraph gửi trace lên LangSmith — deliverable #4 đo bằng chính những
   trace này.

**Graph SẼ dừng ở `propose_remediation`, không có node thực thi.** Việc chuyển
issue sang `Remediating` do người duyệt làm trên Jira, backend biết qua webhook
([`src/api/webhooks.py`](../api/webhooks.py)) sau khi
[`hitl.assert_human_approved()`](../services/hitl.py) xác minh. Ai thêm một node
gọi `transition(..., REMEDIATING)` vào đây là đang phá ràng buộc bắt buộc của đề
bài.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from src.agents.nodes.classify_severity import escalate_spreading
from src.agents.nodes.detect import detect_incidents
from src.agents.nodes.open_war_room import open_war_room
from src.agents.state import IncidentAgentState
from src.services import rules
from src.services.jira import JiraClient
from src.services.prometheus import PrometheusClient, PrometheusError

logger = logging.getLogger(__name__)


def build_incident_graph(prometheus_client: PrometheusClient, jira: JiraClient):
    """Dựng và compile graph cho một cặp client cụ thể.

    Dependency đi vào bằng closure chứ không nằm trong state: `PrometheusClient`
    và `JiraClient` là kết nối mạng, nhét chúng vào state thì state hết
    serialize được — mà LangGraph cần điều đó để checkpoint và để LangSmith ghi
    lại trace.

    Args:
        prometheus_client: Nguồn tín hiệu.
        jira: `FakeJiraClient` khi phát triển, `RealJiraClient` khi chạy thật —
            graph không phân biệt, đó là mục đích của contract ③.
    """

    def detect(state: IncidentAgentState) -> dict:
        """Đọc Prometheus, chạy rule engine cho cả ba use case."""
        try:
            signals = detect_incidents(prometheus_client)
        except PrometheusError as error:
            # Không ném ra ngoài: Agent chạy vòng lặp dài, một lần Prometheus
            # chớp tắt không được làm chết cả tiến trình. Nhưng cũng KHÔNG trả
            # danh sách rỗng — rỗng nghĩa là "đã kiểm tra, mọi thứ bình thường",
            # còn đây là "không biết gì cả".
            logger.error("Không đọc được Prometheus: %s", error)
            return {"error": str(error), "signals": []}
        return {"signals": signals}

    def classify_severity(state: IncidentAgentState) -> dict:
        """Nâng severity khi sự cố lan sang ≥ 2 service.

        Phải chạy TRƯỚC `open_war_room`: severity đi vào tiêu đề issue lúc tạo,
        nâng sau khi tạo thì tiêu đề mang mức sai.
        """
        signals = state.get("signals") or []
        # Gọi `is_spreading()` riêng thay vì suy ra từ việc `escalate_spreading`
        # có trả về list mới hay không. Suy theo danh tính object thì đúng, cho
        # tới hôm ai đó sửa `escalate_spreading` luôn trả về list mới — lúc đó
        # `spreading` âm thầm thành True mãi và không test nào đỏ.
        return {
            "signals": escalate_spreading(signals),
            "spreading": rules.is_spreading(signals),
        }

    def open_war_rooms(state: IncidentAgentState) -> dict:
        """Mở war room cho từng service, hoặc cập nhật vào issue đang mở.

        Lặp bên trong node thay vì tách thành nhiều nhánh graph: mỗi service là
        một issue độc lập, không có thứ tự phụ thuộc giữa chúng, nên chia nhánh
        chỉ thêm phức tạp mà không đổi kết quả.
        """
        opened: list[str] = []
        updated: list[str] = []
        for signal in state.get("signals") or []:
            outcome = open_war_room(jira, signal)
            (opened if outcome.created else updated).append(outcome.jira_key)
        return {"opened": opened, "updated": updated}

    graph = StateGraph(IncidentAgentState)
    graph.add_node("detect", detect)
    graph.add_node("classify_severity", classify_severity)
    graph.add_node("open_war_room", open_war_rooms)

    graph.set_entry_point("detect")
    graph.add_edge("detect", "classify_severity")
    graph.add_conditional_edges(
        "classify_severity",
        _co_dang_mo_war_room,
        {"open_war_room": "open_war_room", END: END},
    )
    graph.add_edge("open_war_room", END)

    return graph.compile()


def _co_dang_mo_war_room(state: IncidentAgentState) -> str:
    """Có đáng mở war room không.

    Dừng khi không có tín hiệu nào — đó là kết quả bình thường của phần lớn
    vòng quét, không phải lỗi. Cũng dừng khi Prometheus lỗi: không biết tình
    hình thì không được mở incident dựa trên phỏng đoán.
    """
    if state.get("error"):
        return END
    if not state.get("signals"):
        return END
    return "open_war_room"
