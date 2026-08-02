"""Test quy ước map sang Jira team-managed.

Các giá trị ở đây đã kiểm chứng trên site Jira thật ngày 2026-07-29 — label
tạo và đọc lại được, JQL tìm theo label ra đúng issue.
"""

from src.models.incident import IncidentState, Severity
from src.services.jira import (
    FALLBACK_STATUS,
    INCIDENT_LABEL,
    JIRA_STATUS,
    jira_status_for,
    jql_open_incidents,
    labels_for,
    service_from_labels,
    severity_from_labels,
    state_from_jira_status,
    status_candidates,
)


def test_labels_for_gan_du_ba_label():
    labels = labels_for(Severity.P2, "service-thanh-toan")
    assert labels == [INCIDENT_LABEL, "severity-P2", "service-service-thanh-toan"]


def test_doc_nguoc_severity_va_service_tu_label():
    """Đúng bộ label Jira trả về trong test thật (thứ tự bị sắp lại)."""
    labels = ["incident", "service-service-thanh-toan", "severity-P2"]

    assert severity_from_labels(labels) is Severity.P2
    assert service_from_labels(labels) == "service-thanh-toan"


def test_label_khong_hop_le_thi_tra_none():
    assert severity_from_labels(["incident", "severity-P9"]) is None
    assert severity_from_labels([]) is None
    assert service_from_labels(["incident"]) is None


def test_moi_incident_state_deu_co_status_tuong_ung():
    """Thiếu một state là Agent sẽ KeyError giữa lúc xử lý incident."""
    for state in IncidentState:
        assert state in JIRA_STATUS, f"thiếu map cho {state}"


def test_map_status_hai_chieu_khop_nhau():
    for state in IncidentState:
        assert state_from_jira_status(jira_status_for(state)) is state


def test_status_khong_biet_thi_tra_none():
    """Issue do người tạo tay có thể ở status bất kỳ — Agent phải bỏ qua, không crash."""
    assert state_from_jira_status("Blocked") is None


def test_jql_chong_mo_trung_loc_dung():
    jql = jql_open_incidents("KAN", "service-thanh-toan")

    assert "project = KAN" in jql
    assert 'labels = "incident"' in jql
    assert 'labels = "service-service-thanh-toan"' in jql
    assert f'status != "{jira_status_for(IncidentState.RESOLVED)}"' in jql


def test_jql_khong_loc_service_van_hop_le():
    jql = jql_open_incidents("KAN")

    assert "service-" not in jql
    assert 'labels = "incident"' in jql


def test_status_dau_tien_cua_board_phai_la_open():
    """Jira đặt mọi issue mới ở status đầu tiên của board — mặc định là `Idea`.

    Map `Idea` vào trạng thái khác thì incident vừa tạo đã hiện sai ngay. Bug
    này đã gặp thật ngày 2026-07-29: issue mới tạo báo là "Remediating".
    """
    assert FALLBACK_STATUS[IncidentState.OPEN] == "Idea"


def test_nhan_ca_ten_moi_lan_ten_mac_dinh():
    """Code phải chạy đúng cả trước lẫn sau khi đội đổi tên cột board.

    Không có điều này thì lúc đổi tên sẽ có một khoảng thời gian hỏng: code
    dùng tên mới nhưng board còn tên cũ, mọi transition đều fail.
    """
    assert state_from_jira_status("Awaiting Approval") is IncidentState.AWAITING_APPROVAL
    assert state_from_jira_status("In Review") is IncidentState.AWAITING_APPROVAL
    assert state_from_jira_status("Remediating") is IncidentState.REMEDIATING
    assert state_from_jira_status("To Do") is IncidentState.REMEDIATING


def test_status_candidates_uu_tien_ten_moi():
    """Thử tên mong muốn trước — sau khi đổi tên board thì dùng ngay tên đó."""
    for state in IncidentState:
        preferred, fallback = status_candidates(state)
        assert preferred == JIRA_STATUS[state]
        assert fallback == FALLBACK_STATUS[state]


def test_moi_state_deu_co_ca_hai_ten():
    for state in IncidentState:
        assert state in JIRA_STATUS, f"thiếu tên mong muốn cho {state}"
        assert state in FALLBACK_STATUS, f"thiếu tên mặc định cho {state}"
