"""Test node `escalate` — nâng mức khi đề xuất treo không ai duyệt.

Test quan trọng nhất là `test_khong_bao_gio_tu_duyet_thay_nguoi`: `escalate` tồn
tại vì cổng HITL là điểm chết đơn lẻ, nên nó là chỗ dễ bị "sửa" thành tự duyệt
sau X phút nhất. Test đó chốt lại rằng nâng mức KHÔNG kèm quyền thi hành.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.agents.nodes.escalate import NGUONG_TREO_PHUT, escalate
from src.models.incident import IncidentSignal, IncidentState, MetricEvidence, Severity
from src.services import hitl
from src.services.jira import FakeJiraClient

LUC = datetime(2026, 8, 4, 22, 0, tzinfo=UTC)


def _cho_duyet(severity: Severity = Severity.P2) -> tuple[FakeJiraClient, str]:
    """War room đã ở `Awaiting Approval`, như sau khi `propose_remediation` chạy."""
    jira = FakeJiraClient(verbose=False)
    key = jira.create_incident(
        IncidentSignal(
            affected_service="service-thanh-toan",
            severity=severity,
            detected_at=LUC,
            metric_name="http_request_duration_seconds p95",
            metric_value=3.3,
            threshold=2.0,
            breached_for_seconds=60.0,
            evidence=[MetricEvidence(name="db_pool_connections_in_use / db_pool_size", value=1.0)],
        )
    )
    jira.transition(key, IncidentState.AWAITING_APPROVAL)
    return jira, key


def _sau(phut: float) -> datetime:
    """Mốc "hiện tại" cách lúc chuyển sang chờ duyệt `phut` phút.

    Lấy mốc thật mà `FakeJiraClient` ghi rồi cộng thêm, chứ không dùng `LUC`:
    fake ghi `datetime.now()` lúc `transition()`, nên hardcode giờ sẽ ra một
    khoảng chờ vô nghĩa.
    """
    return datetime.now(UTC) + timedelta(minutes=phut)


def test_chua_qua_nguong_thi_khong_nang():
    jira, key = _cho_duyet()

    result = escalate(jira, key, bay_gio=_sau(NGUONG_TREO_PHUT - 1))

    assert result.escalated is False
    assert jira.get_incident(key).severity is Severity.P2


def test_qua_nguong_thi_nang_mot_bac_va_ghi_vao_war_room():
    jira, key = _cho_duyet(Severity.P3)

    result = escalate(jira, key, bay_gio=_sau(NGUONG_TREO_PHUT + 5))

    assert result.escalated is True
    assert (result.tu, result.den) == (Severity.P3, Severity.P2)
    incident = jira.get_incident(key)
    assert incident.severity is Severity.P2
    # Tiêu đề mang tiền tố [P3] cũng phải đổi, không thì board hiện mức cũ.
    assert incident.title.startswith("[P2]")
    assert any("chờ duyệt" in event.detail or "nâng mức" in event.action for event in incident.timeline)


def test_nang_tung_bac_chu_khong_nhay_thang_len_p1():
    """Nhảy thẳng thì mọi thứ treo đều thành P1 và mức độ mất ý nghĩa phân loại."""
    jira, key = _cho_duyet(Severity.P4)

    result = escalate(jira, key, bay_gio=_sau(NGUONG_TREO_PHUT * 10))

    assert result.den is Severity.P3


def test_da_p1_thi_khong_nang_nua_nhung_van_nhac_lai():
    jira, key = _cho_duyet(Severity.P1)

    result = escalate(jira, key, bay_gio=_sau(NGUONG_TREO_PHUT + 1))

    assert result.escalated is False
    assert jira.get_incident(key).severity is Severity.P1
    # Vẫn phải nhắc: sự cố nặng nhất mà treo càng lâu càng cần ai đó thấy.
    assert any("không nâng được nữa" in event.detail for event in jira.get_incident(key).timeline)


def test_da_co_nguoi_xu_ly_thi_khong_nang():
    """Đi khỏi `Awaiting Approval` nghĩa là có người bấm — không còn treo."""
    jira, key = _cho_duyet()
    jira.approve_as_human(key)

    result = escalate(jira, key, bay_gio=_sau(NGUONG_TREO_PHUT * 5))

    assert result.escalated is False
    assert jira.get_incident(key).severity is Severity.P2


def test_khong_doc_duoc_moc_thoi_gian_thi_khong_doan():
    """Không biết treo bao lâu thì không nâng, chứ không đoán bừa."""
    jira, key = _cho_duyet()
    monkey = {(key, IncidentState.AWAITING_APPROVAL): None}
    jira.get_transition_time = lambda k, s: monkey.get((k, s))  # type: ignore[method-assign]

    result = escalate(jira, key, bay_gio=_sau(NGUONG_TREO_PHUT * 5))

    assert result.escalated is False
    assert result.cho_bao_lau_phut is None


def test_khong_bao_gio_tu_duyet_thay_nguoi():
    """Nâng mức KHÔNG kèm quyền thi hành. Đây là cả lý do node này an toàn.

    `escalate` sinh ra vì cổng HITL là điểm chết đơn lẻ — người trực đi ngủ thì
    đề xuất nằm im trong khi sự cố vẫn diễn ra. Nên nó là chỗ dễ bị "cải tiến"
    thành tự duyệt sau X phút nhất. Test này chốt: treo bao lâu cũng vậy, cổng
    vẫn từ chối cho tới khi có người thật bấm.
    """
    jira, key = _cho_duyet(Severity.P3)

    for _ in range(5):
        escalate(jira, key, bay_gio=_sau(NGUONG_TREO_PHUT * 100))

    # Nâng tới P1 rồi, nhưng vẫn ở Awaiting Approval và cổng vẫn khoá.
    assert jira.get_incident(key).state is IncidentState.AWAITING_APPROVAL
    with pytest.raises(hitl.ApprovalError):
        hitl.assert_human_approved(jira, key, agent_account_id=jira.AGENT_ACCOUNT_ID)

    # Và Agent không hề tự chuyển sang Remediating.
    assert jira.get_transition_author(key, IncidentState.REMEDIATING) is None


def test_incident_khong_ton_tai_thi_khong_no():
    jira = FakeJiraClient(verbose=False)

    result = escalate(jira, "KAN-999", bay_gio=LUC)

    assert result.escalated is False


def test_loi_jira_o_mot_issue_khong_lam_sap_ca_vong_quet():
    """Một issue lỗi không được làm mất vòng quét của những issue khác.

    Từ 05/08 `RealJiraClient.get_incident()` chỉ trả `None` khi Jira đáp 404,
    còn 401/429/500 thì raise. `escalate()` không bọc lỗi, `run_cycle()` cũng
    không, và `run_agent.py` chỉ bắt KeyboardInterrupt — nên trước bản vá này,
    một lần Jira đáp 429 sẽ giết cả tiến trình Agent.
    """
    from src.agents.incident_graph import _xet_nang_muc

    jira, key = _cho_duyet()
    goc = jira.get_incident

    def get_incident_hong(k: str):
        if k == "KAN-LOI":
            raise RuntimeError("Jira 429 Too Many Requests")
        return goc(k)

    jira.get_incident = get_incident_hong  # type: ignore[method-assign]

    # Issue lỗi: không ném ra ngoài, chỉ trả False.
    assert _xet_nang_muc(jira, "KAN-LOI") is False
    # Issue lành trong cùng vòng vẫn được xét bình thường.
    assert _xet_nang_muc(jira, key) is False  # chưa quá ngưỡng nên không nâng
