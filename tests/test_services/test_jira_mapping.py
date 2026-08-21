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


# ─────────────────── khối JSON máy đọc trong comment

def test_adf_khong_payload_thi_chi_co_paragraph():
    from src.services.jira.real import _adf

    doc = _adf("dòng một\n\ndòng hai")

    assert [n["type"] for n in doc["content"]] == ["paragraph", "paragraph"]


def test_adf_co_payload_thi_them_code_block():
    from src.services.jira.real import _adf, _extract_payloads

    doc = _adf("người đọc thấy dòng này", {"p035": "proposal", "data": {"action": "rollback"}})

    assert doc["content"][-1]["type"] == "codeBlock"
    assert _extract_payloads(doc) == [{"p035": "proposal", "data": {"action": "rollback"}}]


def test_bo_qua_code_block_khong_phai_cua_minh():
    """Comment người gõ tay có thể chứa code block bất kỳ — không được làm vỡ."""
    from src.services.jira.real import _extract_payloads

    doc = {
        "type": "doc",
        "content": [
            {"type": "codeBlock", "content": [{"text": "SELECT * FROM payments"}]},
            {"type": "codeBlock", "content": [{"text": '{"khac": "khong-phai-cua-minh"}'}]},
            {"type": "codeBlock", "content": [{"text": '{"p035": "proposal", "data": {}}'}]},
        ],
    }

    assert _extract_payloads(doc) == [{"p035": "proposal", "data": {}}]


def test_proposal_di_qua_adf_roi_ve_van_nguyen_ven():
    """Vòng tròn ghi rồi đọc lại — đây là thứ webhook dựa vào để biết thi hành gì."""
    from src.models.incident import RemediationProposal
    from src.services.jira.real import _adf, _extract_payloads

    goc = RemediationProposal(
        action="rollback",
        target="service-thanh-toan",
        params={"to_version": "v1.4.1"},
        runbook="1. Xác nhận artifact  2. Rollback",
        risk="Mất tính năng mới",
    )

    doc = _adf("đề xuất", {"p035": "proposal", "data": goc.model_dump(mode="json")})
    doc_lai = RemediationProposal.model_validate(_extract_payloads(doc)[0]["data"])

    assert doc_lai == goc
    assert doc_lai.requires_approval is True


def test_jql_loai_subtask_khoi_danh_sach_incident():
    """Việc cần làm SAU sự cố không được đếm là sự cố.

    Trước 15/08, `create_subtasks()` gắn nhãn `incident` cho mọi subtask nó tạo,
    mà JQL tìm incident lọc đúng bằng nhãn đó. Đo trên board thật: 5 issue "đang
    mở" nhưng 3 trong đó là "Thêm alert cho pool saturation > 80%", "Review max
    connection pool size", "Review monitoring" — đều là việc cần làm.

    War room hiện "Đang xảy ra (5)" trong khi chỉ có 2 sự cố thật, và cả ba đều
    là P4 không có service nào, nhìn hệt dữ liệu hỏng.

    Sau vá, đo lại trên chính board đó: 5 → 2 đang mở, 34 → 31 tổng.
    """
    from src.services.jira.mapping import jql_open_incidents

    assert "issuetype != Subtask" in jql_open_incidents("KAN")
    assert "issuetype != Subtask" in jql_open_incidents("KAN", "service-thanh-toan")


def test_action_item_mang_nhan_khac_incident():
    """Hai nhãn phải KHÁC nhau, nếu không cả bản vá vô nghĩa."""
    from src.services.jira.mapping import ACTION_ITEM_LABEL, INCIDENT_LABEL

    assert ACTION_ITEM_LABEL != INCIDENT_LABEL


def test_create_subtasks_khong_gan_nhan_incident():
    """Chốt tại nguồn: subtask sinh ra phải mang nhãn action item.

    Test trên JQL ở trên chỉ chặn hậu quả. Test này chặn nguyên nhân — nếu ai đó
    đổi lại nhãn trong `create_subtasks()`, board lại bẩn dần mà JQL che mất.
    """
    import inspect

    from src.services.jira import real

    nguon = inspect.getsource(real.RealJiraClient.create_subtasks)
    assert "ACTION_ITEM_LABEL" in nguon
    assert "[INCIDENT_LABEL]" not in nguon


def test_postmortem_ghi_len_jira_phai_doc_lai_duoc():
    """`attach_postmortem` phải kèm khối JSON, không chỉ chữ cho người đọc.

    Lỗi thật, phát hiện lúc chạy thử demo 21/08: KAN-52 đã xử lý xong nhưng nút
    "Postmortems" trên war room vẫn xám. Nguyên nhân — `attach_postmortem()` chỉ
    gọi `add_comment()`, nên postmortem lên Jira dưới dạng văn bản; `get_incident()`
    dựng lại Incident từ Jira nên `incident.postmortem` luôn `None`.

    Toàn bộ test cũ vẫn xanh vì client giả (`jira/client.py`) có gán
    `incident.postmortem = postmortem` trong `attach_postmortem`. Chỉ đường THẬT
    hỏng. Test này đo đúng đường thật: nhặt body đã POST rồi dựng lại `Postmortem`.

    Cùng loại lỗi với `proposal` (xem chú thích trong `get_incident`), lặp lại.
    """
    from src.models.incident import Postmortem
    from src.services.jira.real import RealJiraClient, _extract_payloads

    pm = Postmortem(
        summary="tóm tắt",
        root_cause="pool cạn",
        impact="13% khách chờ quá 2s",
        actions_taken=["rollback v1.4.3 → v1.4.2"],
    )

    da_post: list[dict] = []
    client = RealJiraClient.__new__(RealJiraClient)
    client._call = lambda method, path, body=None: da_post.append(body) or {}  # type: ignore[method-assign]

    client.attach_postmortem("KAN-52", pm)

    assert da_post, "attach_postmortem không POST gì lên Jira"
    payloads = [p for b in da_post for p in _extract_payloads(b.get("body"))]
    khoi = [p for p in payloads if p.get("p035") == "postmortem"]
    assert khoi, "comment thiếu khối JSON — get_incident() sẽ không dựng lại được"

    doc_lai = Postmortem.model_validate(khoi[0]["data"])
    assert doc_lai.summary == pm.summary
    assert doc_lai.root_cause == pm.root_cause
    assert doc_lai.actions_taken == pm.actions_taken


def test_get_incident_co_nhanh_dung_lai_postmortem():
    """`get_incident` phải xử lý payload `postmortem`, không chỉ ghi ra được.

    Ghi được mà không đọc lại thì khối JSON chỉ là rác trong comment.
    """
    import inspect

    from src.services.jira import real

    nguon = inspect.getsource(real.RealJiraClient.get_incident)
    assert '"postmortem"' in nguon
    assert "incident.postmortem" in nguon
