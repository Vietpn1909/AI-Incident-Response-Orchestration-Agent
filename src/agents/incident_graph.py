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

from src.agents.nodes.analyze_logs import analyze_logs
from src.agents.nodes.classify_severity import escalate_spreading
from src.agents.nodes.detect import detect_incidents
from src.agents.nodes.escalate import escalate
from src.agents.nodes.hypothesize import hypothesize
from src.agents.nodes.link_incidents import link_incidents
from src.agents.nodes.open_war_room import open_war_room
from src.agents.nodes.propose_remediation import propose_remediation
from src.agents.state import IncidentAgentState
from src.models.incident import Hypothesis, IncidentSignal, RemediationProposal
from src.services import rules
from src.services.jira import JiraClient
from src.services.prometheus import PrometheusClient, PrometheusError
from src.services.status_updater import (
    status_detected,
    status_logs_collected,
)

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
        all_war_rooms: dict[str, str] = {}
        for signal in state.get("signals") or []:
            outcome = open_war_room(jira, signal)
            all_war_rooms[signal.affected_service] = outcome.jira_key
            if outcome.created:
                opened.append(outcome.jira_key)
                war_rooms[signal.affected_service] = outcome.jira_key
                # Agent auto-comment: status PHÁT HIỆN
                try:
                    jira.add_comment(outcome.jira_key, status_detected(signal))
                except Exception as err:
                    logger.warning("%s: không post được status detected (%s)", outcome.jira_key, err)
            else:
                updated.append(outcome.jira_key)
        return {
            "opened": opened,
            "updated": updated,
            "war_rooms": war_rooms,
            "all_war_rooms": all_war_rooms,
        }

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
            hypothesis = _chan_doan_mot_issue(jira, jira_key, signal)
            if hypothesis is not None:
                hypotheses[jira_key] = hypothesis
        return {"hypotheses": hypotheses}

    def analyze_logs_node(state: IncidentAgentState) -> dict:
        """Thu thập và bổ sung bằng chứng log cho các giả thuyết vừa dựng."""
        hypotheses = state.get("hypotheses") or {}
        if not hypotheses:
            return {}

        signal_theo_service = {
            signal.affected_service: signal
            for signal in state.get("signals") or []
        }

        updated_hypotheses = dict(hypotheses)
        for jira_key, hypothesis in hypotheses.items():
            service = None
            for s_name, k in (state.get("war_rooms") or {}).items():
                if k == jira_key:
                    service = s_name
                    break
            if not service:
                continue

            signal = signal_theo_service.get(service)
            if not signal:
                continue

            try:
                res = analyze_logs(signal, hypothesis)
                updated_hypotheses[jira_key] = res.hypothesis

                # THỨ TỰ QUAN TRỌNG: post "THU THẬP LOG" TRƯỚC, rồi mới post
                # kết luận rút ra từ log.
                #
                # Comment trên Jira xếp theo thời gian post, nên đảo hai lời gọi
                # này là war room đọc ngược nhân quả. Đo trên KAN-21: comment
                # "CHẨN ĐOÁN NGUYÊN NHÂN" nêu kết luận từ log nằm TRÊN comment
                # "THU THẬP LOG" đã tìm ra nó — người trực đọc thấy kết luận đến
                # trước bằng chứng sinh ra nó, đúng thứ làm mất lòng tin vào một
                # chuỗi suy luận tự động.
                try:
                    sample_logs = res.hypothesis.log_evidence[:5] if res.hypothesis.log_evidence else None
                    jira.add_comment(
                        jira_key,
                        status_logs_collected(
                            signal, res.logs_collected, res.logs_relevant,
                            sample_logs=sample_logs,
                        ),
                    )
                except Exception as err:
                    logger.warning("%s: không post được status logs_collected (%s)", jira_key, err)

                _post_lai_neu_log_doi_ket_luan(jira, jira_key, hypothesis, res.hypothesis)
            except Exception as error:
                logger.error("%s: lỗi khi thu thập/phân tích log (%s)", jira_key, error)

        return {"hypotheses": updated_hypotheses}

    def link_incidents_node(state: IncidentAgentState) -> dict:
        """Nối các war room lại khi sự cố lan sang service khác.

        Chỉ chạy khi `classify_severity` đã xác định có lan truyền — xem
        `_co_lan_truyen()`. Nối bừa hai sự cố rời rạc trong ngày còn tệ hơn
        không nối: người trực sẽ đi tìm quan hệ nhân quả không tồn tại.
        """
        try:
            ket_qua = link_incidents(jira, state.get("all_war_rooms") or {})
        except Exception as error:
            # Nối là việc phụ. Mất nó không nghiêm trọng bằng mất cả vòng quét —
            # cùng lý do với `_xet_nang_muc()`.
            logger.error("Không nối được các war room (%s)", error)
            return {"linked": []}
        return {"linked": ket_qua.linked}

    def propose_remediation_node(state: IncidentAgentState) -> dict:
        """Đề xuất hành động rồi chuyển war room sang chờ người duyệt.

        Chỉ chạy cho war room **đã có giả thuyết** trong vòng này. Không có giả
        thuyết thì không có `related_deploy`, mà thiếu me thì mọi sự cố đều rơi
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
            # status_proposed() format đã được dùng bên trong post_proposal()
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

        escalated = [key for key in dang_theo_doi if _xet_nang_muc(jira, key)]
        return {"escalated": escalated}

    graph = StateGraph(IncidentAgentState)
    graph.add_node("detect", detect)
    graph.add_node("classify_severity", classify_severity)
    graph.add_node("open_war_room", open_war_rooms)
    graph.add_node("hypothesize", hypothesize_node)
    graph.add_node("analyze_logs", analyze_logs_node)
    graph.add_node("link_incidents", link_incidents_node)
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
    graph.add_edge("hypothesize", "analyze_logs")
    # Nhánh rẽ theo đúng sơ đồ ở docs/architecture_diagram.md mục 2: từ analyze_logs tới link_incidents hoặc propose_remediation
    graph.add_conditional_edges(
        "analyze_logs",
        _co_lan_truyen,
        {"link_incidents": "link_incidents", "propose_remediation": "propose_remediation"},
    )
    graph.add_edge("link_incidents", "propose_remediation")
    graph.add_edge("propose_remediation", "escalate")
    # Kết thúc ở đây là CỐ Ý, không phải chuỗi làm dở. Bước tiếp theo do **người**
    # khởi động: họ chuyển issue sang `Remediating`, Jira gọi webhook, rồi
    # `hitl.assert_human_approved()` mới cho `remediation.execute()` chạy.
    graph.add_edge("escalate", END)


    return graph.compile()


def _co_lan_truyen(state: IncidentAgentState) -> str:
    """Có đáng nối các war room lại không.

    Bỏ qua khi chỉ một service dính: `link_incidents` tự trả rỗng trong trường
    hợp đó, nhưng đi thẳng thì tiết kiệm được vài lời gọi `get_incident()` mỗi
    vòng quét — mà Agent poll vài giây một lần.
    """
    if not state.get("spreading"):
        return "propose_remediation"
    return "link_incidents"


def _chan_doan_mot_issue(jira: JiraClient, jira_key: str, signal: IncidentSignal) -> Hypothesis | None:
    """Chẩn đoán một incident và post lên war room, nuốt lỗi của riêng issue đó.

    Cùng lý do với `_xet_nang_muc()`: `run_cycle()` không bọc gì và
    `run_agent.py` chỉ bắt `KeyboardInterrupt`, nên một lần Jira đáp 429 ở giữa
    vòng lặp sẽ **giết cả tiến trình Agent** — kể cả khi những incident khác vẫn
    xử lý bình thường được.

    Khác một điểm so với nâng mức: ở đây bọc **riêng phần post lên Jira**, không
    bọc phần chẩn đoán. `hypothesize()` đã tự chịu lỗi LLM và lỗi đọc
    `deploy_history` bên trong nó, và giả thuyết vẫn có giá trị kể cả khi không
    post lên được — nên vẫn trả về để `propose_remediation` dùng tiếp.
    """
    try:
        hypothesis = hypothesize(signal)
    except Exception as error:
        logger.error("%s: không chẩn đoán được (%s)", jira_key, error)
        return None

    logger.info(
        "%s: giả thuyết (tin cậy %.0f%%) — %s",
        jira_key,
        hypothesis.confidence * 100,
        hypothesis.statement,
    )

    # post_hypothesis chuyển state sang INVESTIGATING + lưu dữ liệu JSON.
    # Comment text bên trong đã dùng status_diagnosed() format.
    try:
        jira.post_hypothesis(jira_key, hypothesis)
    except Exception as error:
        logger.error("%s: không post được giả thuyết lên Jira (%s)", jira_key, error)

    return hypothesis


def _post_lai_neu_log_doi_ket_luan(
    jira: JiraClient,
    jira_key: str,
    truoc: Hypothesis,
    sau: Hypothesis,
) -> bool:
    """Post lại giả thuyết lên Jira khi log đã đổi kết luận. Trả về có post hay không.

    Vì sao cần: `hypothesize_node` post giả thuyết lên Jira NGAY, tức bản chưa
    đọc log. `analyze_logs` chạy sau đó và có thể thay hẳn kết luận, nhưng trước
    bản vá này nó chỉ cập nhật state trong bộ nhớ — kết luận từ log không bao giờ
    lên tới war room.

    Đo ngày 11/08 trên KAN-13: node đã tự nêu đúng cơ chế lan truyền
    ("timeout HTTP khi service-dat-hang gọi service-thanh-toan") và ghi ra log
    tiến trình, nhưng Jira chỉ có bản của bộ luật — "nguyên nhân gốc chưa xác
    định", tin cậy 40%. Người trực đọc war room sẽ thấy Agent bó tay đúng ở
    incident mà nó chẩn đoán được, và đó lại là năng lực đắt nhất của nó.

    Chỉ post khi `statement` THỰC SỰ đổi. Log thường chỉ bổ sung bằng chứng cho
    kết luận cũ; post lại mọi lần sẽ nhân đôi comment trên mọi war room và làm
    người trực khó thấy đâu là kết luận cuối.
    """
    if sau.statement == truoc.statement:
        return False

    logger.info(
        "%s: log đổi kết luận, post lại lên war room (tin cậy %.0f%% → %.0f%%)",
        jira_key,
        truoc.confidence * 100,
        sau.confidence * 100,
    )
    try:
        jira.post_hypothesis(jira_key, sau)
    except Exception as error:
        # Cùng lý do như `_chan_doan()`: mất một comment còn hơn mất cả vòng quét.
        logger.error("%s: không post được kết luận từ log lên Jira (%s)", jira_key, error)
        return False
    return True


def _xet_nang_muc(jira: JiraClient, jira_key: str) -> bool:
    """Xét nâng mức một issue, nuốt lỗi để không làm sập cả vòng quét.

    Tách ra khỏi node để test gọi được trực tiếp: node là closure bên trong
    `build_incident_graph()`, mà muốn graph chạy tới nó thì phải dựng cả một sự
    cố giả qua Prometheus — test dài mà lại nghiệm thu vòng vo.

    Vì sao cần bọc lỗi: từ 05/08 `RealJiraClient.get_incident()` chỉ trả `None`
    khi Jira đáp 404, còn 401/429/500 thì **raise** (Long sửa, và sửa đúng —
    trước đó lỗi xác thực bị hiểu thành "không tìm thấy issue"). Nhưng
    `escalate()` gọi `get_incident()` mà không bọc, `run_cycle()` cũng không
    bọc, và `run_agent.py` chỉ bắt `KeyboardInterrupt` — nên một lần Jira đáp
    429 sẽ **giết cả tiến trình Agent**.

    Nâng mức là việc phụ. Mất nó không nghiêm trọng bằng mất toàn bộ vòng quét
    của những incident khác, nên nuốt lỗi — nhưng log ở mức error.
    """
    try:
        return escalate(jira, jira_key).escalated
    except Exception as error:
        logger.error("%s: không xét được việc nâng mức (%s)", jira_key, error)
        return False


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
