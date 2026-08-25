"""Quy ước map model incident sang Jira team-managed project.

CHỦ SỞ HỮU: Đức. Nhóm nhãn `fixed-by-*` do Long thêm ngày 18/08 để đếm được sự cố theo người khắc phục.

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

#: Label cho **việc cần làm sau sự cố**, do postmortem sinh ra.
#:
#: Phải KHÁC `INCIDENT_LABEL`. Trước 15/08, `create_subtasks()` gắn luôn nhãn
#: `incident` cho mọi subtask nó tạo, mà JQL tìm incident lọc đúng bằng nhãn đó —
#: nên hành động khắc phục bị đếm là sự cố.
#:
#: Đo trên board ngày 15/08: 5 issue "đang mở", nhưng 3 trong đó là
#: "Thêm alert cho pool saturation > 80%", "Review max connection pool size",
#: "Review monitoring" — việc cần làm, không phải sự cố. War room hiện
#: "Đang xảy ra (5)" trong khi chỉ có 2 sự cố thật, và cả ba đều là P4 không có
#: service nào, nhìn như dữ liệu hỏng.
ACTION_ITEM_LABEL = "postmortem-action"

#: Nhãn "sự cố này do **Agent tự khắc phục**" — Agent hết thời chờ duyệt rồi tự
#: thi hành, hoặc tự rollback dự phòng sau đó.
#:
#: Vì sao cần nhãn khi comment war room đã phân biệt được ba đường: comment đọc
#: bằng mắt thì rõ, nhưng **không truy vấn được**. `eval/` và báo cáo cần một
#: con số, mà đếm thì phải có JQL — `labels = "fixed-by-agent"`.
#:
#: Rollback dự phòng KHÔNG có nhãn riêng: nó vẫn là Agent tự quyết, còn chi tiết
#: "lần thi hành đầu hay lần lùi lại" đã phân biệt được bằng `FALLBACK_MARKER`
#: trong comment. Nhãn thứ ba chỉ chia nhỏ mẫu đếm mà không ai hỏi tới.
FIXED_BY_AGENT_LABEL = "fixed-by-agent"

#: Nhãn "sự cố này khắc phục **sau khi người duyệt**" — luồng HITL bình thường,
#: dù phát hiện qua webhook Jira hay qua vòng poll của Agent. Hai đường đó cùng
#: một ý nghĩa với người đọc báo cáo, nên cùng một nhãn.
FIXED_BY_HUMAN_LABEL = "fixed-by-human"

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


def replace_severity_label(labels: list[str], severity: Severity) -> list[str]:
    """Thay label mức độ trong danh sách, giữ nguyên mọi label khác.

    Jira API ghi `labels` là **ghi đè toàn bộ** danh sách, không phải thêm vào —
    nên `set_severity()` phải dựng lại cả danh sách. Hàm này giữ hiểu biết về
    tiền tố `severity-` nằm đúng một chỗ là file này.
    """
    giu_lai = [label for label in labels if not label.startswith(_SEVERITY_PREFIX)]
    return [*giu_lai, severity_label(severity)]


def merge_label(labels: list[str], label: str) -> list[str]:
    """Thêm một nhãn vào danh sách cũ, giữ nguyên mọi nhãn khác.

    Cùng kiểu và cùng lý do với `replace_severity_label()`: Jira API ghi
    `labels` là **ghi đè toàn bộ** danh sách, không phải thêm vào. Gửi thẳng
    `["fixed-by-agent"]` là xoá sạch `incident`, `severity-*`, `service-*` —
    tức issue rơi khỏi mọi JQL đang dùng để tìm war room, kể cả bước chống mở
    trùng của `find_open_incident()`. Mất nhãn trên Jira thì không có lệnh nào
    lấy lại được, phải gõ tay từng issue.

    Không thêm trùng, vì hai đường có thể cùng gắn một nhãn cho một issue:
    webhook trên Render và vòng poll của Agent local đều chạy khi người duyệt
    bấm nút. Jira tự dedupe, nhưng danh sách trả về từ hàm này còn được đọc bởi
    `fixed_by_from_labels()` và bởi mắt người — trùng lặp ở đó chỉ gây nghi ngờ
    dữ liệu hỏng.
    """
    if label in labels:
        return list(labels)
    return [*labels, label]


def fixed_by_from_labels(labels: list[str]) -> str | None:
    """Đọc ngược: sự cố này ai khắc phục. `None` khi chưa gắn nhãn nào.

    Đối xứng với `severity_from_labels()`, và có mặt vì cùng một lý do: lần sau
    ai cần biết "ai đã fix" thì gọi hàm này, thay vì tự so chuỗi ở UI hay ở
    `eval/`. Quy ước nhãn phải nằm gọn trong file này — mỗi chỗ tự bóc tiền tố
    là một chỗ sẽ lệch khi quy ước đổi.

    Trả về **chính hằng nhãn** chứ không phải một từ vựng thứ hai kiểu
    `"agent"`/`"human"`: hai bộ tên cho cùng một khái niệm là chỗ để chúng lệch
    nhau, và người gọi so với `FIXED_BY_AGENT_LABEL` thì không phải nhớ gì thêm.

    Có CẢ HAI nhãn (Agent tự thi hành trước, sau đó người vào duyệt tiếp một đề
    xuất khác) thì trả nhãn NGƯỜI. Con số này đi vào báo cáo về mức tự động hoá,
    nên đếm thiếu cho Agent còn hơn đếm thừa: sự cố nào có người can thiệp thì
    không phải sự cố Agent tự lo trọn.
    """
    if FIXED_BY_HUMAN_LABEL in labels:
        return FIXED_BY_HUMAN_LABEL
    if FIXED_BY_AGENT_LABEL in labels:
        return FIXED_BY_AGENT_LABEL
    return None


def retitle_severity(summary: str, severity: Severity) -> str:
    """Đổi tiền tố `[P2]` đầu tiêu đề sang mức mới.

    Tiêu đề do `IncidentSignal.title` sinh, dạng `"[P2] service: metric = ..."`.
    Mức độ vì vậy nằm ở **hai chỗ** — label và tiêu đề — và `set_severity()`
    phải sửa cả hai, không thì `severity_from_labels()` với mắt người đọc board
    nói hai điều khác nhau.

    Không khớp mẫu nào thì thêm tiền tố vào đầu, chứ không bỏ qua im lặng: một
    incident đã nâng mức mà tiêu đề không nói gì là thứ dễ bị bỏ sót nhất trên
    board.
    """
    con_lai = summary
    for muc in Severity:
        tien_to = f"[{muc.value}]"
        if summary.startswith(tien_to):
            con_lai = summary[len(tien_to) :].lstrip()
            break
    return f"[{severity.value}] {con_lai}".rstrip()


def service_from_labels(labels: list[str]) -> str | None:
    """Đọc tên service ngược ra từ label."""
    for label in labels:
        if label.startswith(_SERVICE_PREFIX):
            return label[len(_SERVICE_PREFIX) :]
    return None


# ---------------------------------------------------------------------------
# Map trạng thái
# ---------------------------------------------------------------------------
# Tên trạng thái MONG MUỐN trên board — khớp đúng `IncidentState`.
#
# Đây là tên nên dùng: comment Agent post lên Jira sẽ ghi "chuyển sang trạng
# thái Remediating để phê duyệt", đọc lên có nghĩa. Với tên mặc định của Jira
# thì câu đó thành "chuyển sang trạng thái To Do để phê duyệt" — vô nghĩa, và
# đã gây nhầm lẫn hai lần khi test thật.
JIRA_STATUS: dict[IncidentState, str] = {
    IncidentState.OPEN: "Open",
    IncidentState.INVESTIGATING: "Investigating",
    IncidentState.AWAITING_APPROVAL: "Awaiting Approval",
    IncidentState.REMEDIATING: "Remediating",
    IncidentState.RESOLVED: "Resolved",
}

# Tên mặc định của board team-managed khi CHƯA đổi tên cột.
#
# Giữ bảng này để code chạy đúng cả trước lẫn sau khi đổi tên — không có
# khoảng thời gian hỏng ở giữa, và ai clone repo về mà chưa đổi tên board vẫn
# chạy được ngay. `RealJiraClient` thử tên mong muốn trước, không có thì dùng
# tên mặc định.
#
# ⚠️ `Idea` PHẢI map vào OPEN: Jira đặt mọi issue mới ở status đầu tiên của
# board. Map sai thì incident vừa tạo đã hiện sai trạng thái ngay (bug đã gặp
# thật: issue mới báo là "Remediating").
FALLBACK_STATUS: dict[IncidentState, str] = {
    IncidentState.OPEN: "Idea",
    IncidentState.INVESTIGATING: "In Progress",
    IncidentState.AWAITING_APPROVAL: "In Review",
    IncidentState.REMEDIATING: "To Do",
    IncidentState.RESOLVED: "Done",
}

_REVERSE_STATUS: dict[str, IncidentState] = {
    **{name: state for state, name in FALLBACK_STATUS.items()},
    **{name: state for state, name in JIRA_STATUS.items()},
}


def status_candidates(state: IncidentState) -> tuple[str, str]:
    """Tên mong muốn trước, tên mặc định sau.

    `RealJiraClient` thử lần lượt để không phụ thuộc board đã đổi tên hay chưa.
    """
    return JIRA_STATUS[state], FALLBACK_STATUS[state]


def jira_status_for(state: IncidentState) -> str:
    """Tên mong muốn. Dùng cho thông báo cho người đọc.

    Muốn biết tên ĐANG dùng thật trên board thì phải hỏi Jira — xem
    `status_candidates()` và cách `RealJiraClient._transition_id()` giải quyết.
    """
    return JIRA_STATUS[state]


def state_from_jira_status(status_name: str) -> IncidentState | None:
    """Tên status trên Jira → `IncidentState`. Nhận cả tên mới lẫn tên mặc định.

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
    # Loại subtask ra khỏi kết quả — thắt lưng lẫn dây đeo.
    #
    # Đổi nhãn trong `create_subtasks()` chỉ chữa cho issue tạo TỪ NAY. Những
    # subtask đã mang nhãn `incident` từ trước vẫn nằm trên board và vẫn lọt vào
    # mọi truy vấn, mà xoá issue trên Jira thì không lấy lại được.
    #
    # Điều kiện này còn đúng về mặt ngữ nghĩa: một war room là issue độc lập,
    # không bao giờ là subtask của issue khác. Nên lọc theo `issuetype` là mô tả
    # đúng thứ đang tìm, không phải mẹo vá tạm.
    clauses.append("issuetype != Subtask")
    return " AND ".join(clauses) + " ORDER BY created DESC"
