"""Node `escalate` — nâng mức khi đề xuất treo quá lâu không ai duyệt.

CHỦ SỞ HỮU: Đức

## Vấn đề node này giải

Cổng HITL là điểm mạnh của thiết kế: không hành động production nào chạy mà
không có người duyệt. Nhưng nó cũng là một **điểm chết đơn lẻ** — người trực đi
ngủ, không thấy thông báo, hoặc đang xử lý việc khác, thì đề xuất nằm im trong
`Awaiting Approval` trong khi sự cố vẫn đang diễn ra và người dùng vẫn đang chịu.

Node này **không tự phá cổng**. Nó không duyệt thay người, không hạ ràng buộc.
Nó chỉ làm to tiếng hơn: nâng severity và ghi rõ đã treo bao lâu.

## Giới hạn phải nói ra

Sơ đồ kiến trúc ghi *"tăng severity, thông báo"*. Phần **thông báo** hiện chưa
làm được: đội không có PagerDuty, Slack webhook, hay bất cứ kênh gọi người nào.
Nâng severity trên Jira chỉ có tác dụng nếu có người đang xem board.

Không giả vờ node này gọi được người dậy. Nó nâng mức để lần sau ai mở board là
thấy ngay, và ghi mốc thời gian vào war room để phần postmortem đo được **thời
gian chờ duyệt** — một con số đáng đưa vào `eval/`.

## Vì sao đọc thời điểm từ Jira changelog

Agent tự ghi nhớ lúc nó transition thì restart là mất, nhiều instance thì mỗi
con một số. Quan trọng hơn: **người trực có thể tự chuyển trạng thái trên UI**
mà Agent không hề biết. Changelog là nguồn duy nhất biết hết mọi thay đổi — cùng
lý do cổng HITL dựa vào nó.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from src.models.incident import IncidentState, Severity
from src.services.jira import JiraClient
from src.services.status_updater import status_escalated, ts

logger = logging.getLogger(__name__)

#: Treo bao lâu thì nâng mức. 10 phút chọn theo thời lượng buổi demo và theo
#: `SUSTAINED_SECONDS = 30` của `rules.py`: đủ dài để người trực kịp đọc và cân
#: nhắc, đủ ngắn để trong một buổi demo 15 phút vẫn thấy được nó kích hoạt.
NGUONG_TREO_PHUT = 10.0

#: Bậc nâng. P4 → P3 → P2 → P1, mỗi lần một bậc chứ không nhảy thẳng lên P1:
#: nhảy thẳng thì mọi thứ treo đều thành P1 và mức độ mất hết ý nghĩa phân loại.
_NANG_MOT_BAC = {
    Severity.P4: Severity.P3,
    Severity.P3: Severity.P2,
    Severity.P2: Severity.P1,
}


@dataclass
class EscalationResult:
    """Kết quả xét một war room đang chờ duyệt."""

    jira_key: str
    #: Đã chờ bao nhiêu phút. `None` nghĩa là không đọc được mốc thời gian.
    cho_bao_lau_phut: float | None
    #: Có nâng mức lần này không.
    escalated: bool
    tu: Severity | None = None
    den: Severity | None = None


def escalate(
    jira: JiraClient,
    jira_key: str,
    *,
    nguong_phut: float = NGUONG_TREO_PHUT,
    bay_gio: datetime | None = None,
) -> EscalationResult:
    """Xét một war room đang chờ duyệt, nâng mức nếu treo quá ngưỡng.

    Args:
        jira: `FakeJiraClient` khi phát triển, `RealJiraClient` khi chạy thật.
        jira_key: War room đang ở `Awaiting Approval`.
        nguong_phut: Treo lâu hơn ngần này thì nâng.
        bay_gio: Mốc "hiện tại", truyền vào để test không phải giả lập thời gian.

    Returns:
        `EscalationResult`. `escalated=False` là đường đi **bình thường** — phần
        lớn vòng quét thì đề xuất vừa mới post hoặc đã được duyệt rồi.
    """
    moc = bay_gio or datetime.now(UTC)

    incident = jira.get_incident(jira_key)
    if incident is None:
        logger.warning("%s: không đọc lại được incident, bỏ qua lần xét nâng mức", jira_key)
        return EscalationResult(jira_key=jira_key, cho_bao_lau_phut=None, escalated=False)

    # Đã đi khỏi Awaiting Approval nghĩa là có người xử lý — không còn treo.
    if incident.state is not IncidentState.AWAITING_APPROVAL:
        return EscalationResult(jira_key=jira_key, cho_bao_lau_phut=None, escalated=False)

    tu_luc = jira.get_transition_time(jira_key, IncidentState.AWAITING_APPROVAL)
    if tu_luc is None:
        # Issue đang ở Awaiting Approval mà changelog không có mốc chuyển sang đó
        # là bất thường — có thể issue được tạo trực tiếp ở trạng thái này.
        logger.warning(
            "%s: đang chờ duyệt nhưng changelog không có mốc chuyển sang Awaiting Approval — "
            "không tính được đã treo bao lâu",
            jira_key,
        )
        return EscalationResult(jira_key=jira_key, cho_bao_lau_phut=None, escalated=False)

    cho_phut = (moc - tu_luc).total_seconds() / 60
    if cho_phut < nguong_phut:
        return EscalationResult(jira_key=jira_key, cho_bao_lau_phut=cho_phut, escalated=False)

    # ⚠️ Chốt mức cũ vào biến TRƯỚC khi gọi `set_severity()`.
    #
    # `FakeJiraClient` sửa thẳng vào object `Incident` mà nó đang giữ, còn
    # `RealJiraClient` thì `get_incident()` trả về object mới đọc từ API. Nên đọc
    # `incident.severity` sau khi set sẽ ra mức MỚI trên bản giả và mức CŨ trên
    # bản thật — cùng một dòng code, hai kết quả khác nhau.
    #
    # Bản đầu mắc đúng lỗi này: comment post lên war room ghi "Nâng mức P2 → P2".
    muc_cu = incident.severity
    muc_moi = _NANG_MOT_BAC.get(muc_cu)
    if muc_moi is None:
        # Đã P1, không nâng được nữa. Vẫn nhắc lại vào war room: sự cố nặng nhất
        # mà treo càng lâu càng cần ai đó thấy.
        jira.add_comment(
            jira_key,
            f"⏰ [{ts()}] VẪN CHỜ DUYỆT\n\n"
            f"Đề xuất khắc phục đã chờ duyệt {cho_phut:.0f} phút "
            f"(ngưỡng {nguong_phut:.0f} phút).\n"
            f"Mức đã là {muc_cu.value} — không nâng được nữa.\n\n"
            "Agent KHÔNG tự thi hành hành động khắc phục.",
        )
        logger.warning("%s: chờ duyệt %.0f phút, đã ở mức %s", jira_key, cho_phut, muc_cu.value)
        return EscalationResult(jira_key=jira_key, cho_bao_lau_phut=cho_phut, escalated=False)

    jira.set_severity(jira_key, muc_moi)
    # Agent auto-comment: status NÂNG MỨC
    jira.add_comment(jira_key, status_escalated(muc_cu, muc_moi, cho_phut, nguong_phut))
    logger.warning(
        "%s: chờ duyệt %.0f phút, nâng %s → %s",
        jira_key,
        cho_phut,
        muc_cu.value,
        muc_moi.value,
    )
    return EscalationResult(
        jira_key=jira_key,
        cho_bao_lau_phut=cho_phut,
        escalated=True,
        tu=muc_cu,
        den=muc_moi,
    )
