"""State machine LangGraph của Agent ứng phó sự cố.

CHỦ SỞ HỮU: Việt · sơ đồ ở [docs/architecture_diagram.md](../../docs/architecture_diagram.md) mục 2

Thay chỗ vòng lặp tuần tự Đức viết tạm ngày 02/08. **Ba node bên dưới giữ
nguyên chữ ký** — chúng vẫn là hàm thuần nhận dependency tường minh, graph chỉ
là lớp nối. Nhờ vậy chúng test được riêng mà không cần dựng graph, và toàn bộ
test của Đức chạy y nguyên qua đường mới.

    detect → classify_severity → (có tín hiệu?) → open_war_room → hypothesize → END
                                       └── không ──────────────────────────────→ END

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
from src.agents.nodes.escalate import escalate
from src.agents.nodes.hypothesize import hypothesize
from src.agents.nodes.open_war_room import open_war_room
from src.agents.nodes.propose_remediation import propose_remediation
from src.agents.state import IncidentAgentState
from src.models.incident import Hypothesis, RemediationProposal
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
        war_rooms: dict[str, str] = {}
        for signal in state.get("signals") or []:
            outcome = open_war_room(jira, signal)
            if outcome.created:
                opened.append(outcome.jira_key)
                war_rooms[signal.affected_service] = outcome.jira_key
            else:
                updated.append(outcome.jira_key)
        return {"opened": opened, "updated": updated, "war_rooms": war_rooms}

    def hypothesize_node(state: IncidentAgentState) -> dict:
        """Chẩn đoán nguyên nhân và post lên war room.

        Chỉ chạy cho war room **vừa mở mới**. Sự cố kéo dài thì Agent poll liên
        tục; chẩn đoán lại mỗi vòng sẽ vừa làm war room đầy comment trùng lặp
        vừa đốt quota LLM mà không thêm thông tin gì.
        """
        war_rooms = state.get("war_rooms") or {}
        if not war_rooms:
            return {}

        hypotheses: dict[str, Hypothesis] = {}
        for signal in state.get("signals") or []:
            jira_key = war_rooms.get(signal.affected_service)
            if not jira_key:
                continue
            hypothesis = hypothesize(signal)
            jira.post_hypothesis(jira_key, hypothesis)
            hypotheses[jira_key] = hypothesis
            logger.info(
                "%s: giả thuyết (tin cậy %.0f%%) — %s",
                jira_key,
                hypothesis.confidence * 100,
                hypothesis.statement,
            )
        return {"hypotheses": hypotheses}

    def propose_remediation_node(state: IncidentAgentState) -> dict:
        """Đề xuất hành động rồi chuyển war room sang chờ người duyệt.

        Chỉ chạy cho war room **đã có giả thuyết** trong vòng này. Không có giả
        thuyết thì không có `related_deploy`, mà thiếu nó thì mọi sự cố đều rơi
        vào nhánh mặc định `scale_up` — đề xuất sai còn tệ hơn không đề xuất.

        Đây là node cuối của chuỗi tự động. Sau nó graph **kết thúc** và quyền
        quyết định thuộc về người trực: họ chuyển issue sang `Remediating`, Jira
        gọi webhook, `hitl.assert_human_approved()` xác minh bằng changelog rồi
        mới tới `remediation.execute()`.
        """
        hypotheses = state.get("hypotheses") or {}
        if not hypotheses:
            return {}

        signal_theo_key = {
            war_room: signal
            for signal in state.get("signals") or []
            if (war_room := (state.get("war_rooms") or {}).get(signal.affected_service))
        }

        proposals: dict[str, RemediationProposal] = {}
        awaiting: list[str] = []
        for jira_key, hypothesis in hypotheses.items():
            signal = signal_theo_key.get(jira_key)
            if signal is None:
                continue
            outcome = propose_remediation(jira, jira_key, signal, hypothesis)
            proposals[jira_key] = outcome.proposal
            if outcome.awaiting_approval:
                awaiting.append(jira_key)
        return {"proposals": proposals, "awaiting_approval": awaiting}

    def escalate_node(state: IncidentAgentState) -> dict:
        """Nâng mức những war room treo chờ duyệt quá lâu.

        Xét `updated` — các war room **đã có từ trước** — chứ không xét cái vừa
        mở trong vòng này. Cái vừa mở thì đề xuất mới post xong vài giây, không
        thể treo quá ngưỡng; đưa nó vào chỉ tốn thêm lời gọi Jira mỗi vòng.

        Đây là node cuối. Nó **không phá cổng HITL**: không duyệt thay người,
        không hạ ràng buộc. Chỉ làm to tiếng hơn để lần sau ai mở board là thấy.
        """
        dang_theo_doi = state.get("updated") or []
        if not dang_theo_doi:
            return {}

        escalated: list[str] = []
        for jira_key in dang_theo_doi:
            if escalate(jira, jira_key).escalated:
                escalated.append(jira_key)
        return {"escalated": escalated}

    graph = StateGraph(IncidentAgentState)
    graph.add_node("detect", detect)
    graph.add_node("classify_severity", classify_severity)
    graph.add_node("open_war_room", open_war_rooms)
    graph.add_node("hypothesize", hypothesize_node)
    graph.add_node("propose_remediation", propose_remediation_node)
    graph.add_node("escalate", escalate_node)

    graph.set_entry_point("detect")
    graph.add_edge("detect", "classify_severity")
    graph.add_conditional_edges(
        "classify_severity",
        _co_dang_mo_war_room,
        {"open_war_room": "open_war_room", END: END},
    )
    graph.add_edge("open_war_room", "hypothesize")
    graph.add_edge("hypothesize", "propose_remediation")
    graph.add_edge("propose_remediation", "escalate")
    # Kết thúc ở đây là CỐ Ý, không phải chuỗi làm dở. Bước tiếp theo do **người**
    # khởi động: họ chuyển issue sang `Remediating`, Jira gọi webhook, rồi
    # `hitl.assert_human_approved()` mới cho `remediation.execute()` chạy.
    graph.add_edge("escalate", END)

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
