"""Quy ước map model incident sang Jira team-managed project.

Vì sao không dùng custom field: đã thử tạo global custom field qua REST API
(`POST /rest/api/3/field`) — tạo được, nhưng **không xuất hiện trên createmeta
của team-managed project**. Team-managed quản lý field riêng và không nhận
global custom field. Kiểm chứng ngày 2026-07-29 trên site thật.

Thay bằng **label**, đã verify hoạt động đầy đủ:

    labels đọc lại : ['incident', 'service-service-thanh-toan', 'severity-P2']
    JQL theo label : tìm thấy 1 issue

Label đủ cho mọi thứ cần: gắn dữ liệu vào issue, và tìm lại bằng JQL —
`labels = "severity-P2"`. `root_cause_confidence` không cần lên Jira, nó nằm
trong comment cùng bằng chứng số.
"""

from __future__ import annotations

from src.models.incident import IncidentState, Severity

# Label đánh dấu issue do Agent tạo — để JQL lọc khỏi issue thường của đội.
INCIDENT_LABEL = "incident"

_SEVERITY_PREFIX = "severity-"
_SERVICE_PREFIX = "service-"


def severity_label(severity: Severity) -> str:
    """`Severity.P2` → `"severity-P2"`."""
    return f"{_SEVERITY_PREFIX}{severity.value}"


def service_label(service: str) -> str:
    """`"service-thanh-toan"` → `"service-service-thanh-toan"`.

    Label Jira không cho khoảng trắng, nên tên service phải dùng gạch ngang —
    contract ① đã quy định như vậy.
    """
    return f"{_SERVICE_PREFIX}{service}"


def labels_for(severity: Severity, affected_service: str) -> list[str]:
    """Bộ label gắn khi tạo incident issue."""
    return [INCIDENT_LABEL, severity_label(severity), service_label(affected_service)]


def severity_from_labels(labels: list[str]) -> Severity | None:
    """Đọc severity ngược ra từ label. None nếu không có label nào khớp."""
    for label in labels:
        if label.startswith(_SEVERITY_PREFIX):
            try:
                return Severity(label[len(_SEVERITY_PREFIX) :])
            except ValueError:
                continue
    return None


def service_from_labels(labels: list[str]) -> str | None:
    """Đọc tên service ngược ra từ label."""
    for label in labels:
        if label.startswith(_SERVICE_PREFIX):
            return label[len(_SERVICE_PREFIX) :]
    return None


# ---------------------------------------------------------------------------
# Map trạng thái
# ---------------------------------------------------------------------------
# Team-managed project của đội hiện có sẵn 5 status: Idea, To Do, In Progress,
# In Review, Done. Map dưới đây dùng ĐÚNG tên đang có nên code chạy được ngay.
#
# ⚠️ `Idea` PHẢI map vào OPEN, vì Jira đặt mọi issue mới ở status đầu tiên của
# board — tức `Idea`. Map nó vào trạng thái khác thì incident vừa tạo đã hiện
# sai ngay (bug đã gặp: issue mới báo là "Remediating").
#
# 🔧 KHUYẾN NGHỊ đổi tên 5 cột trên board thành đúng tên IncidentState. Không
# chỉ để demo đẹp — với tên hiện tại, `REMEDIATING → "To Do"` đọc lên vô nghĩa
# và người xem board sẽ hiểu sai trạng thái thật của incident. Sau khi đổi tên,
# sửa đúng dict này là xong, không phải sửa chỗ nào khác:
#
#     IncidentState.OPEN:              "Open"
#     IncidentState.INVESTIGATING:     "Investigating"
#     IncidentState.AWAITING_APPROVAL: "Awaiting Approval"
#     IncidentState.REMEDIATING:       "Remediating"
#     IncidentState.RESOLVED:          "Resolved"
JIRA_STATUS: dict[IncidentState, str] = {
    IncidentState.OPEN: "Idea",
    IncidentState.INVESTIGATING: "In Progress",
    IncidentState.AWAITING_APPROVAL: "In Review",
    IncidentState.REMEDIATING: "To Do",
    IncidentState.RESOLVED: "Done",
}

_REVERSE_STATUS: dict[str, IncidentState] = {v: k for k, v in JIRA_STATUS.items()}


def jira_status_for(state: IncidentState) -> str:
    """`IncidentState.AWAITING_APPROVAL` → tên status trên Jira."""
    return JIRA_STATUS[state]


def state_from_jira_status(status_name: str) -> IncidentState | None:
    """Tên status trên Jira → `IncidentState`. None nếu không nằm trong map.

    Trả None thay vì raise, vì issue do người tạo tay có thể ở status bất kỳ và
    Agent phải bỏ qua chúng chứ không được crash.
    """
    return _REVERSE_STATUS.get(status_name)


def jql_open_incidents(project_key: str, affected_service: str | None = None) -> str:
    """JQL tìm incident đang mở — dùng cho chống mở trùng.

    Args:
        project_key: vd. "KAN".
        affected_service: lọc theo service nếu có.
    """
    clauses = [f"project = {project_key}", f'labels = "{INCIDENT_LABEL}"']
    if affected_service:
        clauses.append(f'labels = "{service_label(affected_service)}"')
    clauses.append(f'status != "{jira_status_for(IncidentState.RESOLVED)}"')
    return " AND ".join(clauses) + " ORDER BY created DESC"
