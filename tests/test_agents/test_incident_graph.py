"""Test node `open_war_room` và graph nối ba node đầu.

Dùng `FakeJiraClient` nên không gọi mạng. Điều đáng test nhất ở đây là luật
chống mở trùng: Agent poll vài giây một lần trong khi sự cố kéo dài hàng chục
phút, thiếu luật đó thì war room thành bãi rác đúng lúc cần dùng nhất.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.agents import incident_graph
from src.agents.nodes import detect as detect_module
from src.agents.nodes import open_war_room as war_room_module
from src.agents.nodes.detect import BreachTracker
from src.agents.nodes.open_war_room import open_war_room_node
from src.models.incident import IncidentSignal, MetricEvidence, Severity
from src.services.jira import FakeJiraClient
from src.services.prometheus import MetricSample

NOW = datetime(2026, 8, 1, 14, 32, 4, tzinfo=UTC)


def _signal(service: str = "service-thanh-toan", severity: Severity = Severity.P2) -> IncidentSignal:
    return IncidentSignal(
        affected_service=service,
        severity=severity,
        detected_at=NOW,
        metric_name="http_request_duration_seconds p95",
        metric_value=5.1,
        threshold=2.0,
        breached_for_seconds=45.0,
        evidence=[
            MetricEvidence(
                name="http_request_duration_seconds p95",
                value=5.1,
                baseline=0.2,
                unit="s",
                promql="histogram_quantile(0.95, ...)",
            )
        ],
    )


@pytest.fixture
def jira(monkeypatch) -> FakeJiraClient:
    client = FakeJiraClient(verbose=False)
    monkeypatch.setattr(war_room_module, "build_jira_client", lambda: client)
    return client


# ------------------------------------------------------------- open_war_room


def test_khong_co_tin_hieu_thi_khong_tao_issue(jira: FakeJiraClient):
    assert open_war_room_node({"signal": None}) == {"jira_key": ""}
    assert jira.list_incidents() == []


def test_mo_war_room_va_post_boi_canh(jira: FakeJiraClient):
    result = open_war_room_node({"signal": _signal()})

    incident = jira.get_incident(result["jira_key"])
    assert incident is not None
    assert incident.severity == Severity.P2
    assert "service-thanh-toan" in incident.affected_services


def test_khong_mo_trung_khi_incident_van_dang_mo(jira: FakeJiraClient):
    """Luật quan trọng nhất của node: find_open_incident() TRƯỚC create_incident()."""
    lan_dau = open_war_room_node({"signal": _signal()})
    lan_hai = open_war_room_node({"signal": _signal()})
    lan_ba = open_war_room_node({"signal": _signal()})

    assert lan_dau["jira_key"] == lan_hai["jira_key"] == lan_ba["jira_key"]
    assert len(jira.list_incidents()) == 1


def test_van_cap_nhat_boi_canh_vao_issue_cu(jira: FakeJiraClient):
    """Không tạo trùng, nhưng cũng không được im lặng bỏ qua vòng poll."""
    key = open_war_room_node({"signal": _signal()})["jira_key"]
    truoc = len(jira.get_incident(key).timeline)

    open_war_room_node({"signal": _signal()})

    assert len(jira.get_incident(key).timeline) > truoc


def test_hai_service_khac_nhau_thi_mo_hai_war_room(jira: FakeJiraClient):
    """Chống trùng theo service, không phải chặn mọi issue mới."""
    open_war_room_node({"signal": _signal("service-thanh-toan")})
    open_war_room_node({"signal": _signal("service-dat-hang")})

    assert len(jira.list_incidents()) == 2


def test_boi_canh_kem_promql_de_nguoi_truc_kiem_chung_lai(jira: FakeJiraClient):
    """Ràng buộc đề bài: chẩn đoán phải truy vết được về số liệu cụ thể."""
    key = open_war_room_node({"signal": _signal()})["jira_key"]

    comment = jira.get_incident(key).timeline[-1].detail
    assert "PromQL:" in comment
    assert "lệch 25.5x" in comment


# -------------------------------------------------------------------- graph


class FakePrometheus:
    def __init__(self, values: dict[str, float] | None) -> None:
        self._values = values

    def query(self, promql: str) -> list[MetricSample]:
        if self._values is None:
            return []
        if "quantile_over_time" in promql:
            key = "baseline"
        elif "histogram_quantile" in promql:
            key = "p95"
        elif "status=~" in promql:
            key = "error"
        else:
            key = "pool"
        return [MetricSample(service="service-thanh-toan", value=self._values[key])]


@pytest.fixture(autouse=True)
def _reset_tracker():
    detect_module._tracker = BreachTracker()


def test_graph_khoe_manh_thi_dung_som_khong_mo_war_room(monkeypatch, jira: FakeJiraClient):
    monkeypatch.setattr(
        detect_module,
        "_client",
        lambda: FakePrometheus({"p95": 0.18, "baseline": 0.18, "error": 0.0, "pool": 0.2}),
    )

    result = incident_graph.incident_agent.invoke({})

    assert result["signals"] == []
    assert result.get("signal") is None
    assert jira.list_incidents() == []


def test_graph_chay_tron_ba_node_khi_co_su_co(monkeypatch, jira: FakeJiraClient):
    monkeypatch.setattr(
        detect_module,
        "_client",
        lambda: FakePrometheus({"p95": 5.1, "baseline": 0.2, "error": 0.12, "pool": 1.0}),
    )
    # Vòng poll đầu chỉ đặt mốc vượt ngưỡng; kéo lùi để đủ 30 giây xác nhận.
    incident_graph.incident_agent.invoke({})
    detect_module._tracker._since["service-thanh-toan"] -= timedelta(seconds=45)

    result = incident_graph.incident_agent.invoke({})

    assert result["signal"].severity == Severity.P2
    assert result["jira_key"]
    assert len(jira.list_incidents()) == 1


def test_graph_dung_khi_khong_doc_duoc_prometheus(monkeypatch, jira: FakeJiraClient):
    """Không biết tình hình thì không mở war room, nhưng phải giữ lại lỗi."""

    class DeadPrometheus:
        def query(self, promql: str):
            from src.services.prometheus import PrometheusError

            raise PrometheusError("Không gọi được Prometheus")

    monkeypatch.setattr(detect_module, "_client", lambda: DeadPrometheus())

    result = incident_graph.incident_agent.invoke({})

    assert "Không gọi được Prometheus" in result["error"]
    assert jira.list_incidents() == []
