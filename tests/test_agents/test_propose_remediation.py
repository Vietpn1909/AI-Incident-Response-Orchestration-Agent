"""Test node `propose_remediation` — chỗ Agent giao quyền cho người.

Test quan trọng nhất là `test_chuoi_phe_duyet_khep_kin_sau_khi_de_xuat`: nó
chứng minh sau khi node này chạy thì **người duyệt được, còn Agent thì không** —
tức toàn bộ lý do tồn tại của node này.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.agents.nodes.propose_remediation import propose_remediation
from src.models.incident import (
    DeployRecord,
    Hypothesis,
    IncidentSignal,
    IncidentState,
    MetricEvidence,
    Severity,
)
from src.services import hitl, remediation, runbooks
from src.services.jira import FakeJiraClient

SERVICE = "service-thanh-toan"


@pytest.fixture(autouse=True)
def khong_goi_postgres(monkeypatch: pytest.MonkeyPatch):
    """Chặn `deploys.recent_deploys()` gọi Postgres thật trong test.

    Node tự đọc lịch sử deploy nên nếu không chặn, test sẽ cố nối database và
    phụ thuộc máy đang chạy — đúng loại test "xanh đỏ theo máy" đã gặp sáng nay.
    """
    from src.agents.nodes import propose_remediation as node

    lich_su = [
        DeployRecord(service=SERVICE, version="v1.4.1", deployed_at=datetime(2026, 8, 3, tzinfo=UTC)),
        DeployRecord(service=SERVICE, version="v1.4.2", deployed_at=datetime(2026, 8, 4, 16, 26, tzinfo=UTC)),
    ]
    monkeypatch.setattr(node.deploys, "recent_deploys", lambda service, **kw: lich_su)
    return lich_su


def _signal() -> IncidentSignal:
    return IncidentSignal(
        affected_service=SERVICE,
        severity=Severity.P2,
        detected_at=datetime(2026, 8, 4, 16, 30, tzinfo=UTC),
        metric_name="http_request_duration_seconds p95",
        metric_value=3.3,
        threshold=2.0,
        breached_for_seconds=60.0,
        evidence=[MetricEvidence(name=runbooks.EVIDENCE_POOL, value=1.0)],
    )


def _hypothesis(deploy: DeployRecord | None) -> Hypothesis:
    return Hypothesis(statement="Pool cạn", confidence=0.9, related_deploy=deploy)


def _mo_war_room() -> tuple[FakeJiraClient, str, IncidentSignal]:
    jira = FakeJiraClient(verbose=False)
    signal = _signal()
    return jira, jira.create_incident(signal), signal


def test_post_de_xuat_va_chuyen_sang_cho_duyet(khong_goi_postgres):
    jira, key, signal = _mo_war_room()

    result = propose_remediation(jira, key, signal, _hypothesis(khong_goi_postgres[-1]))

    assert result.awaiting_approval is True
    assert jira.get_incident(key).state is IncidentState.AWAITING_APPROVAL
    assert result.proposal.action == "rollback"
    assert result.proposal.params["to_version"] == "v1.4.1"


def test_agent_khong_tu_chuyen_sang_remediating(khong_goi_postgres):
    """Agent chỉ được mở cổng, không được tự đi qua cổng."""
    jira, key, signal = _mo_war_room()

    propose_remediation(jira, key, signal, _hypothesis(khong_goi_postgres[-1]))

    assert jira.get_incident(key).state is not IncidentState.REMEDIATING
    assert jira.get_transition_author(key, IncidentState.REMEDIATING) is None


def test_chuoi_phe_duyet_khep_kin_sau_khi_de_xuat(khong_goi_postgres):
    """Sau node này: người duyệt được, Agent thì không. Đây là cả mục đích của node.

    Trước khi có node này, việc chuyển sang `Awaiting Approval` do
    `scripts/verify_e2e.py` làm bằng tay — nên cổng HITL đã verify chạy thật
    trên Jira nhưng chưa bao giờ nằm trong đường đi của Agent.
    """
    jira, key, signal = _mo_war_room()
    propose_remediation(jira, key, signal, _hypothesis(khong_goi_postgres[-1]))

    # 1. Chưa ai duyệt → cổng từ chối.
    with pytest.raises(hitl.ApprovalError):
        hitl.assert_human_approved(jira, key, agent_account_id=jira.AGENT_ACCOUNT_ID)

    # 2. Agent tự chuyển → cổng vẫn từ chối, vì tác giả trùng account Agent.
    jira.transition(key, IncidentState.REMEDIATING)
    with pytest.raises(hitl.ApprovalError):
        hitl.assert_human_approved(jira, key, agent_account_id=jira.AGENT_ACCOUNT_ID)

    # 3. Người bấm duyệt → qua cổng, và trả về đúng accountId của người đó.
    jira.approve_as_human(key)
    approved_by = hitl.assert_human_approved(jira, key, agent_account_id=jira.AGENT_ACCOUNT_ID)
    assert approved_by == jira.HUMAN_ACCOUNT_ID

    # 4. Đề xuất của Agent thi hành được, có ghi tên người duyệt.
    proposal = runbooks.choose(signal, _hypothesis(khong_goi_postgres[-1]), khong_goi_postgres)
    result = remediation.execute(
        proposal.action, proposal.target, approved_by=approved_by, params=proposal.params
    )
    assert result.succeeded
    assert result.approved_by == jira.HUMAN_ACCOUNT_ID
    assert "v1.4.1" in result.detail


def test_chuyen_trang_thai_hong_thi_van_post_de_xuat_va_bao_that_bai(
    khong_goi_postgres, monkeypatch: pytest.MonkeyPatch
):
    """Đề xuất vẫn phải lên war room dù không mở được cổng.

    Hỏng ở đây nghĩa là người trực đọc được đề xuất mà không có nút nào để duyệt
    — nghiêm trọng, nhưng mất đề xuất luôn thì còn tệ hơn.
    """
    jira, key, signal = _mo_war_room()

    def transition_hong(*args, **kwargs):
        raise RuntimeError('transition "Awaiting Approval" không tồn tại trên board')

    monkeypatch.setattr(jira, "transition", transition_hong)

    result = propose_remediation(jira, key, signal, _hypothesis(khong_goi_postgres[-1]))

    assert result.awaiting_approval is False
    assert result.proposal.action == "rollback"
    # Đề xuất đã nằm trên war room, đọc lại được.
    assert jira.get_incident(key).proposal is not None


def test_khong_co_deploy_thi_de_xuat_noi_pool(khong_goi_postgres):
    jira, key, signal = _mo_war_room()

    result = propose_remediation(jira, key, signal, _hypothesis(None))

    assert result.proposal.action == "increase_pool"
    assert result.awaiting_approval is True
