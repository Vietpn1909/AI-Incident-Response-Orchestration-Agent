"""Test cổng phê duyệt HITL — ràng buộc bắt buộc của đề bài.

`test_agent_tu_duyet_bi_tu_choi` là test quan trọng nhất trong toàn bộ repo.
Nếu nó fail, tức là Agent có thể tự thực thi hành động production và dự án không
còn thoả yêu cầu của đề bài.
"""

from datetime import UTC, datetime

import pytest

from src.models.incident import (
    IncidentSignal,
    IncidentState,
    RemediationProposal,
    Severity,
)
from src.services.hitl import ApprovalError, assert_human_approved
from src.services.jira_client import FakeJiraClient

AGENT = FakeJiraClient.AGENT_ACCOUNT_ID
HUMAN = FakeJiraClient.HUMAN_ACCOUNT_ID


@pytest.fixture
def client() -> FakeJiraClient:
    return FakeJiraClient(verbose=False)


@pytest.fixture
def jira_key(client: FakeJiraClient) -> str:
    signal = IncidentSignal(
        affected_service="service-thanh-toan",
        severity=Severity.P2,
        detected_at=datetime(2026, 7, 29, 14, 32, tzinfo=UTC),
        metric_name="http_request_duration_seconds p95",
        metric_value=5.1,
        threshold=2.0,
    )
    key = client.create_incident(signal)
    client.post_proposal(key, RemediationProposal(action="rollback", target="service-thanh-toan"))
    return key


def test_agent_tu_duyet_bi_tu_choi(client: FakeJiraClient, jira_key: str):
    """Agent tự chuyển sang Remediating → backend từ chối thực thi.

    Jira team-managed KHÔNG chặn được transition này, nên Agent chuyển được.
    Hàng rào thật là ở đây: backend đọc changelog, thấy người transition chính
    là Agent, và từ chối.
    """
    client.transition(jira_key, IncidentState.REMEDIATING)  # Jira cho phép
    assert client.get_incident(jira_key).state == IncidentState.REMEDIATING

    with pytest.raises(ApprovalError, match="chính account Agent"):
        assert_human_approved(client, jira_key, agent_account_id=AGENT)


def test_nguoi_duyet_thi_cho_qua(client: FakeJiraClient, jira_key: str):
    client.approve_as_human(jira_key)

    approver = assert_human_approved(client, jira_key, agent_account_id=AGENT)

    assert approver == HUMAN


def test_chua_ai_duyet_thi_tu_choi(client: FakeJiraClient, jira_key: str):
    with pytest.raises(ApprovalError, match="chưa được chuyển sang Remediating"):
        assert_human_approved(client, jira_key, agent_account_id=AGENT)


def test_thieu_agent_account_id_thi_fail_to(client: FakeJiraClient, jira_key: str):
    """Cấu hình sai phải fail to, không được im lặng cho qua.

    Nếu `agent_account_id` rỗng mà vẫn chạy thì không có cổng phê duyệt nào cả —
    đúng loại lỗi âm thầm nguy hiểm nhất.
    """
    client.approve_as_human(jira_key)

    with pytest.raises(ValueError, match="Thiếu jira_agent_account_id"):
        assert_human_approved(client, jira_key, agent_account_id="")


def test_approval_error_la_permission_error():
    """Để code cũ bắt PermissionError vẫn hoạt động."""
    assert issubclass(ApprovalError, PermissionError)
