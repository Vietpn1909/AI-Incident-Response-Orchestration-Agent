"""Test contract ③ — hành vi mà Việt phụ thuộc vào, đặc biệt là cổng HITL.

Test quan trọng nhất trong file này là `test_agent_khong_the_tu_duyet`. Nó đảm
bảo ràng buộc bắt buộc của đề bài được thực thi ở tầng interface: Agent viết sai
luồng sẽ fail ở CI, không phải fail lúc demo.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.models.incident import (
    ActionItem,
    Hypothesis,
    IncidentSignal,
    IncidentState,
    MetricEvidence,
    Postmortem,
    RemediationProposal,
    Severity,
)
from src.services.jira import FakeJiraClient, JiraClient

NOW = datetime(2026, 7, 28, 14, 32, 4, tzinfo=UTC)


@pytest.fixture
def client() -> FakeJiraClient:
    return FakeJiraClient(verbose=False)


@pytest.fixture
def signal() -> IncidentSignal:
    return IncidentSignal(
        affected_service="service-thanh-toan",
        severity=Severity.P2,
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


def test_fake_client_thoa_man_protocol(client: FakeJiraClient):
    """FakeJiraClient phải dùng được ở mọi chỗ nhận JiraClient."""
    assert isinstance(client, JiraClient)


def test_create_incident_mo_war_room(client: FakeJiraClient, signal: IncidentSignal):
    jira_key = client.create_incident(signal)

    incident = client.get_incident(jira_key)
    assert incident is not None
    assert incident.state == IncidentState.OPEN
    assert incident.severity == Severity.P2
    assert "service-thanh-toan" in incident.affected_services
    assert incident.timeline, "phải có mốc timeline đầu tiên"


def test_post_proposal_chuyen_sang_cho_duyet(client: FakeJiraClient, signal: IncidentSignal):
    jira_key = client.create_incident(signal)
    client.post_proposal(
        jira_key,
        RemediationProposal(action="rollback", target="service-thanh-toan", params={"to_version": "v1.4.1"}),
    )

    incident = client.get_incident(jira_key)
    assert incident.state == IncidentState.AWAITING_APPROVAL
    assert incident.awaiting_human is True


def test_changelog_ghi_dung_ai_da_transition(client: FakeJiraClient, signal: IncidentSignal):
    """Client phải ghi lại *ai* chuyển trạng thái — đây là dữ liệu mà cổng HITL dựa vào."""
    jira_key = client.create_incident(signal)
    client.post_proposal(jira_key, RemediationProposal(action="rollback", target="service-thanh-toan"))

    assert client.get_transition_author(jira_key, IncidentState.REMEDIATING) is None

    client.transition(jira_key, IncidentState.REMEDIATING)
    assert client.get_transition_author(jira_key, IncidentState.REMEDIATING) == client.AGENT_ACCOUNT_ID


def test_nguoi_duyet_duoc_ghi_nhan_la_nguoi(client: FakeJiraClient, signal: IncidentSignal):
    jira_key = client.create_incident(signal)
    client.post_proposal(jira_key, RemediationProposal(action="rollback", target="service-thanh-toan"))

    client.approve_as_human(jira_key)

    assert client.get_incident(jira_key).state == IncidentState.REMEDIATING
    assert client.get_transition_author(jira_key, IncidentState.REMEDIATING) == client.HUMAN_ACCOUNT_ID


def test_find_open_incident_chong_mo_trung(client: FakeJiraClient, signal: IncidentSignal):
    """Không có bước này thì lúc load test Agent tạo hàng loạt issue giống nhau."""
    assert client.find_open_incident("service-thanh-toan") is None

    jira_key = client.create_incident(signal)
    assert client.find_open_incident("service-thanh-toan") == jira_key

    client.transition(jira_key, IncidentState.RESOLVED)
    assert client.find_open_incident("service-thanh-toan") is None


def test_link_issues_hai_chieu(client: FakeJiraClient, signal: IncidentSignal):
    first = client.create_incident(signal)
    second = client.create_incident(
        signal.model_copy(update={"affected_service": "service-dat-hang", "severity": Severity.P3})
    )

    client.link_issues(first, second)

    assert second in client.get_incident(first).related_incidents
    assert first in client.get_incident(second).related_incidents


def test_hypothesis_luu_kem_bang_chung(client: FakeJiraClient, signal: IncidentSignal):
    jira_key = client.create_incident(signal)
    client.post_hypothesis(
        jira_key,
        Hypothesis(
            statement="Pool DB cạn kiệt do tải tăng",
            confidence=0.86,
            evidence=[MetricEvidence(name="db_pool in_use/size", value=1.0, baseline=0.35)],
        ),
    )

    incident = client.get_incident(jira_key)
    assert incident.state == IncidentState.INVESTIGATING
    assert incident.hypotheses[0].evidence


def test_postmortem_va_action_item(client: FakeJiraClient, signal: IncidentSignal):
    jira_key = client.create_incident(signal)
    items = [ActionItem(title="Thêm index cho payments(order_id)", owner="Trung")]

    keys = client.create_subtasks(jira_key, items)
    client.attach_postmortem(
        jira_key,
        Postmortem(summary="Pool cạn do tải", root_cause="Pool 5 connection", impact="27 phút", action_items=items),
    )
    client.transition(jira_key, IncidentState.RESOLVED)

    incident = client.get_incident(jira_key)
    assert keys == [f"{jira_key}-1"]
    assert items[0].jira_key == f"{jira_key}-1"
    assert incident.postmortem is not None
    assert incident.resolved_at is not None
    assert incident.is_open is False


def test_list_incidents_moi_nhat_truoc(client: FakeJiraClient, signal: IncidentSignal):
    older = client.create_incident(signal.model_copy(update={"detected_at": NOW - timedelta(hours=1)}))
    newer = client.create_incident(signal.model_copy(update={"affected_service": "service-dat-hang"}))

    keys = [incident.jira_key for incident in client.list_incidents()]
    assert keys.index(newer) < keys.index(older)
