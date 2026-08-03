"""Test riêng cho state machine LangGraph.

Hành vi đầu-cuối đã có `test_detection.py` phủ qua `run_cycle()` — và chúng vẫn
xanh sau khi thay vòng lặp tuần tự bằng graph, đó chính là bằng chứng việc thay
không làm đổi hành vi.

File này chỉ kiểm những thứ **riêng của graph**, thứ mà `run_cycle()` gói lại
nên không nhìn thấy: đường rẽ có dừng đúng chỗ không, và node sau có thật sự
KHÔNG chạy khi đường rẽ bảo dừng.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from langgraph.graph import END

from src.agents.incident_graph import _co_dang_mo_war_room, build_incident_graph
from src.models.incident import IncidentSignal, MetricEvidence, Severity
from src.services.jira import FakeJiraClient
from src.services.prometheus import PrometheusClient


def _signal(service: str = "service-thanh-toan") -> IncidentSignal:
    return IncidentSignal(
        affected_service=service,
        severity=Severity.P2,
        detected_at=datetime.now(UTC),
        metric_name="http_request_duration_seconds p95",
        metric_value=5.1,
        threshold=2.0,
        breached_for_seconds=45.0,
        evidence=[MetricEvidence(name="p95", value=5.1, unit="s", promql="...")],
    )


def _prometheus(status: int = 200, payload: dict | None = None) -> PrometheusClient:
    """Prometheus giả trả rỗng cho mọi câu — tức mọi thứ bình thường."""
    body = payload or {"status": "success", "data": {"resultType": "vector", "result": []}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return PrometheusClient(transport=httpx.MockTransport(handler))


# ────────────────────────────────────────────────────────── đường rẽ


@pytest.mark.parametrize(
    ("state", "mong_doi"),
    [
        ({"signals": [], "error": ""}, END),
        ({"signals": None}, END),
        ({}, END),
        ({"error": "Không gọi được Prometheus", "signals": []}, END),
        # Có lỗi thì dừng kể cả khi đã kịp thu được tín hiệu — không biết tình
        # hình thì không mở incident dựa trên phỏng đoán.
        ({"error": "Prometheus chớp tắt", "signals": [_signal()]}, END),
        ({"signals": [_signal()], "error": ""}, "open_war_room"),
    ],
)
def test_duong_re_sau_classify(state, mong_doi):
    assert _co_dang_mo_war_room(state) == mong_doi


# ────────────────────────────────────────────────────────── graph chạy


def test_binh_thuong_thi_khong_cham_toi_jira():
    """Không có tín hiệu thì node `open_war_room` phải KHÔNG chạy.

    `run_cycle()` chỉ cho biết `opened` rỗng — mà rỗng cũng có thể do node đã
    chạy rồi không tạo được gì. Ở đây kiểm thẳng: Jira không hề bị gọi.
    """
    jira = FakeJiraClient(verbose=False)

    with _prometheus() as client:
        state = build_incident_graph(client, jira).invoke({})

    assert state["signals"] == []
    assert jira.list_incidents() == []
    # Node open_war_room không chạy nên hai key này chưa từng được ghi.
    assert "opened" not in state


def test_prometheus_loi_thi_giu_lai_loi_va_khong_mo_war_room():
    jira = FakeJiraClient(verbose=False)

    with _prometheus(status=500, payload={"status": "error", "error": "sập"}) as client:
        state = build_incident_graph(client, jira).invoke({})

    assert state["error"]
    assert state["signals"] == []
    assert jira.list_incidents() == []


def test_graph_co_du_ba_node():
    """Đổi tên node là đổi thứ hiện trên trace LangSmith — deliverable #4."""
    jira = FakeJiraClient(verbose=False)

    with _prometheus() as client:
        graph = build_incident_graph(client, jira)

    ten = set(graph.get_graph().nodes)
    assert {"detect", "classify_severity", "open_war_room"} <= ten


def test_khong_co_node_nao_thuc_thi_khac_phuc():
    """Ràng buộc bắt buộc của đề bài: sau `propose_remediation` là hết phần Agent.

    Việc chuyển sang `Remediating` do người duyệt làm trên Jira, backend biết
    qua webhook sau khi `hitl.assert_human_approved()` xác minh. Test này đỏ
    nghĩa là có ai đó vừa mở đường cho Agent tự thi hành.
    """
    jira = FakeJiraClient(verbose=False)

    with _prometheus() as client:
        graph = build_incident_graph(client, jira)

    ten = set(graph.get_graph().nodes)
    assert not {"execute_remediation", "remediate", "approve"} & ten
