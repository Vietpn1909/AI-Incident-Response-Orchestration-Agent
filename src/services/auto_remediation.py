"""Auto-remediation khi timeout — Agent tự sửa nếu không ai phản hồi.

CHỦ SỞ HỮU: Việt. Nhãn `fixed-by-agent` do Long thêm ngày 18/08 ở hai hàm thi hành.

## Vì sao có module này

Sự cố xảy ra vào đêm, không ai trực → issue nằm ở `Awaiting Approval` mãi mà
không được duyệt. 30 phút trôi qua mà hệ thống không cải thiện và không có phản
hồi từ người → Agent tự thi hành.

## MỐI QUAN HỆ VỚI HITL

Module này **CỐ Ý bypass** cổng HITL (`hitl.assert_human_approved()`). Đây là
**ngoại lệ có điều kiện**, KHÔNG phải xoá bỏ HITL:

- HITL vẫn là đường đi chính (webhook + poll_jira_approvals)
- Module này chỉ can thiệp khi HITL đã **hết thời gian chờ** (mặc định 30 phút)
- Mặc định **TẮT** — phải bật `AUTO_REMEDIATION_ENABLED=1` trong `.env`
- Comment trên Jira ghi rõ "tự thi hành do hết thời chờ", phân biệt với human

## Nguyên tắc cách ly

- KHÔNG import `hitl.py`
- KHÔNG sửa `remediation.py`, `executors.py`, `incident_graph.py`, `webhooks.py`
- Gọi `remediation.execute()` y hệt webhook, chỉ khác `approved_by`
- Tích hợp vào `run_agent.py` bằng 1 hàm gọi trong loop

## Chính sách theo mức độ

| Mức   | Hành vi khi timeout                                  |
|-------|------------------------------------------------------|
| P3/P4 | Thi hành **đúng hành động đã đề xuất** (đề xuất gốc)|
| P1/P2 | Ép **rollback** bất kể đề xuất ban đầu là gì        |

Vế thứ ba, thêm 18/08: P3/P4 sau khi Agent tự thi hành mà **đo lại vẫn chưa đỡ**
→ rollback dự phòng. Xem `should_fallback_rollback()`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.config import get_settings
from src.models.incident import IncidentSignal, IncidentState, Severity
from src.services import deploys, runbooks
from src.services.jira.mapping import FIXED_BY_AGENT_LABEL
from src.services.remediation import RemediationResult, execute

logger = logging.getLogger(__name__)

#: Giá trị `approved_by` khi Agent tự duyệt do timeout. Dùng chuỗi cố định để
#: phân biệt rõ với human accountId (dạng `712020:xxxx`) trong mọi audit trail.
AUTO_APPROVED_BY = "AUTO_TIMEOUT_AGENT"

#: Comment marker — tương tự `REMEDIATION_MARKER` trong `remediation.py` nhưng
#: khác chữ, để phân biệt auto-fix với human-approved fix khi đọc Jira.
AUTO_MARKER = "Tự thi hành do hết thời chờ"

#: Comment marker của **rollback dự phòng** (vế 3). Phải khác `AUTO_MARKER`:
#: người đọc Jira cần phân biệt được ba đường đã đi tới production — người duyệt,
#: Agent tự thi hành lần đầu, và Agent rollback vì lần đầu không ăn. Ba đường đó
#: dẫn tới ba kết luận khác nhau khi viết postmortem.
FALLBACK_MARKER = "Rollback dự phòng — auto-fix không làm sự cố hết"

#: Chờ bấy nhiêu phút sau khi tự thi hành mới ĐO LẠI để xét rollback dự phòng.
#:
#: Bắt buộc phải chờ, không phải để cho lịch sự: cửa sổ PromQL `[1m]` mà
#: `rules.py` dùng còn chứa nguyên phần dữ liệu lúc đang hỏng, nên đo ngay sau
#: khi thi hành thì gần như luôn ra "chưa đỡ" — rồi Agent rollback một hành động
#: thật ra đang có tác dụng. Cùng lập luận với ghi chú ở `run_agent.py` chỗ gọi
#: `_verify_da_thi_hanh()`.
#:
#: Là hằng module chứ không phải biến môi trường, giống `NGUONG_TREO_PHUT` của
#: `escalate`: đây là hệ quả của độ dài cửa sổ PromQL, không phải thứ để người
#: vận hành chỉnh theo khẩu vị.
NGUONG_CHO_DO_LAI_PHUT = 5


def resolve_rollback_version(
    service: str,
    proposal_params: dict | None = None,
) -> str | None:
    """Rollback `service` thì về phiên bản nào — chỗ DUY NHẤT trả lời câu này.

    Dùng chung cho cả hai đường tự rollback (P1/P2 hết thời chờ, và rollback dự
    phòng khi auto-fix không ăn). Một bản thứ hai của phép chọn này là chỗ để hai
    đường lặng lẽ lệch nhau.

    Args:
        service: Service sẽ bị rollback. **Phải** đúng là service sẽ nhận lệnh
            thi hành — tra lịch sử của service A rồi rollback service B là hạ
            service B về một phiên bản chưa từng tồn tại của nó.
        proposal_params: `params` của đề xuất gốc, CHỈ truyền khi đề xuất đó vốn
            đã là `rollback` cho đúng `service` này. Khi đó `to_version` trong
            nó do `runbooks` tính từ nghi phạm thật (deploy trùng thời gian với
            sự cố), chính xác hơn phép đoán ở dưới.

    Returns:
        Phiên bản đích, hoặc `None` khi không xác định được.

        `None` nghĩa là **không được rollback**. Không có đường lùi kiểu điền
        chuỗi "phiên bản trước": chuỗi đó đi thẳng vào comment Jira và vào
        `params` của lệnh thi hành, mà một mệnh lệnh rollback không nói rõ về
        đâu thì không thi hành được và cũng không kiểm chứng được. Cùng lập luận
        đã ghi trong `runbooks.phien_ban_truoc()`.
    """
    if proposal_params:
        to_version = proposal_params.get("to_version")
        if to_version:
            return str(to_version)

    history = deploys.recent_deploys(service)
    if not history:
        # `recent_deploys()` cố ý gộp "chưa deploy lần nào" với "không đọc được
        # bảng" — xem docstring của nó. Với chỗ này hai thứ đó như nhau: không
        # có bằng chứng thì không có phiên bản đích.
        logger.warning(
            "%s: không có lịch sử deploy — không xác định được phiên bản để rollback về",
            service,
        )
        return None

    # `recent_deploys()` sắp xếp mới nhất trước, nên `history[0]` là bản ĐANG
    # chạy, tức nghi phạm — đích rollback là bản ngay TRƯỚC nó.
    ve_phien_ban = runbooks.phien_ban_truoc(history, history[0])
    if ve_phien_ban is None:
        logger.warning(
            "%s: chỉ có đúng một bản deploy (%s) — không có phiên bản nào trước đó để lùi về",
            service,
            history[0].version,
        )
    return ve_phien_ban


@dataclass(frozen=True)
class AutoRemediationPolicy:
    """Chính sách auto-fix khi timeout, đọc từ `.env`."""

    enabled: bool
    timeout_minutes: int

    @staticmethod
    def from_settings() -> AutoRemediationPolicy:
        """Đọc cấu hình từ `Settings`. Gọi mỗi lần kiểm để env thay đổi được."""
        settings = get_settings()
        return AutoRemediationPolicy(
            enabled=settings.auto_remediation_enabled,
            timeout_minutes=settings.auto_remediation_timeout_minutes,
        )


@dataclass(frozen=True)
class AutoRemediationDecision:
    """Quyết định auto-fix cho một issue cụ thể."""

    jira_key: str
    action: str
    target: str
    params: dict
    reason: str
    #: `True` nếu hành động bị ép rollback (P1/P2), khác với đề xuất gốc.
    forced_rollback: bool


def _danh_dau_agent_da_fix(jira, jira_key: str) -> None:  # jira: JiraClient
    """Gắn nhãn `fixed-by-agent` lên issue, nuốt lỗi nếu Jira không nhận.

    Nuốt lỗi y như `add_comment()` và `transition()` ngay dưới đây, và cùng lý
    do: hành động khắc phục đã chạy xong trên production rồi. Mất một cái nhãn
    thì tệ nhất là thiếu một dòng trong bảng thống kê; ném exception ra thì
    người gọi tưởng việc khắc phục hỏng.

    Chỉ gọi khi thi hành THÀNH CÔNG — nhãn "được Agent khắc phục" trên một hành
    động thất bại là nhãn nói dối, và nó đi thẳng vào số liệu báo cáo.
    """
    try:
        jira.add_label(jira_key, FIXED_BY_AGENT_LABEL)
    except Exception as error:
        logger.warning(
            "%s: không gắn được nhãn %s (%s)", jira_key, FIXED_BY_AGENT_LABEL, error
        )


def _is_human_responded(
    jira,  # JiraClient
    jira_key: str,
) -> bool:
    """Kiểm tra xem đã có phản hồi từ human chưa.

    "Phản hồi" = issue đã được chuyển sang `Remediating` bởi bất kỳ ai (bao gồm
    cả webhook). Nếu đã có → HITL đã xử lý, không cần auto-fix.
    """
    try:
        author = jira.get_transition_author(jira_key, IncidentState.REMEDIATING)
        return author is not None
    except Exception:
        # Lỗi đọc Jira: an toàn hơn là coi như đã có phản hồi → không auto-fix.
        return True


def should_auto_remediate(
    jira,  # JiraClient
    jira_key: str,
    severity: Severity,
    proposal_action: str,
    proposal_target: str,
    proposal_params: dict | None = None,
    deploy_service: str | None = None,
) -> AutoRemediationDecision | None:
    """Quyết định có nên auto-fix issue này không.

    Returns:
        `AutoRemediationDecision` nếu nên auto-fix.
        `None` nếu KHÔNG nên (feature tắt, chưa đủ thời gian, đã có human, hoặc
        P1/P2 mà **không xác định được phiên bản để rollback về** — xem
        `resolve_rollback_version()`).
    """
    policy = AutoRemediationPolicy.from_settings()
    if not policy.enabled:
        return None

    # Đã có human phản hồi → HITL đã xử lý, không cần auto.
    if _is_human_responded(jira, jira_key):
        return None

    # Đọc thời điểm chuyển sang Awaiting Approval — mốc bắt đầu đếm timeout.
    try:
        awaiting_since = jira.get_transition_time(
            jira_key, IncidentState.AWAITING_APPROVAL
        )
    except Exception:
        return None

    if awaiting_since is None:
        return None

    now = datetime.now(UTC)
    elapsed = now - awaiting_since
    timeout = timedelta(minutes=policy.timeout_minutes)

    if elapsed < timeout:
        return None

    elapsed_minutes = int(elapsed.total_seconds() / 60)

    # Quyết định hành động theo mức độ.
    if severity in (Severity.P1, Severity.P2):
        # P1/P2: ép rollback bất kể đề xuất ban đầu.
        #
        # MỘT service duy nhất cho cả hai việc: tra lịch sử deploy và nhận lệnh
        # thi hành. Trước 18/08 lịch sử tra theo `deploy_service` còn lệnh lại
        # gửi tới `proposal_target` — hai giá trị này khác nhau được, và khi khác
        # thì Agent hạ service A xuống một phiên bản của service B.
        service = deploy_service or proposal_target

        # Chỉ tin `to_version` của đề xuất gốc khi đề xuất đó nói về ĐÚNG service
        # sắp bị rollback, vì cùng lý do trên.
        params_de_xuat = (
            proposal_params
            if proposal_action == "rollback" and proposal_target == service
            else None
        )
        to_version = resolve_rollback_version(service, params_de_xuat)
        if to_version is None:
            # Không biết lùi về đâu thì KHÔNG ra quyết định rollback. Thà để issue
            # nằm chờ người — người còn tra được lịch sử deploy bằng tay, chứ một
            # lệnh "rollback về phiên bản trước" thì không ai thi hành nổi.
            logger.error(
                "%s: %s hết thời chờ nhưng không xác định được phiên bản rollback cho %s — "
                "KHÔNG tự thi hành, để nguyên chờ người duyệt",
                jira_key,
                severity.value,
                service,
            )
            return None

        return AutoRemediationDecision(
            jira_key=jira_key,
            action="rollback",
            target=service,
            params={"to_version": to_version},
            reason=(
                f"Sự cố {severity.value} đã chờ {elapsed_minutes} phút "
                f"mà không có phản hồi. Tự rollback về {to_version}."
            ),
            forced_rollback=True,
        )
    else:
        # P3/P4: dùng đúng hành động đã đề xuất.
        return AutoRemediationDecision(
            jira_key=jira_key,
            action=proposal_action,
            target=proposal_target,
            params=proposal_params or {},
            reason=(
                f"Sự cố {severity.value} đã chờ {elapsed_minutes} phút "
                f"mà không có phản hồi. Tự thi hành: {proposal_action} → {proposal_target}."
            ),
            forced_rollback=False,
        )


def execute_auto_remediation(
    jira,  # JiraClient
    decision: AutoRemediationDecision,
) -> RemediationResult:
    """Thi hành auto-fix và post comment lên Jira.

    Gọi `remediation.execute()` với `approved_by=AUTO_APPROVED_BY`.
    Comment lên Jira ghi rõ lý do tự thi hành.

    KHÔNG gọi `hitl.assert_human_approved()` — đây là bypass có chủ đích.
    """
    logger.warning(
        "AUTO-REMEDIATION: %s — %s → %s (lý do: %s)",
        decision.jira_key,
        decision.action,
        decision.target,
        decision.reason,
    )

    result = execute(
        decision.action,
        decision.target,
        approved_by=AUTO_APPROVED_BY,
        params=decision.params,
    )

    if result.succeeded:
        _danh_dau_agent_da_fix(jira, decision.jira_key)

    # Post comment lên Jira — phân biệt rõ với human-approved.
    comment = (
        f"⚠️ **{AUTO_MARKER}**\n\n"
        f"{decision.reason}\n\n"
        f"---\n\n"
        f"{result.as_comment()}\n\n"
        f"---\n\n"
        f"🔒 Hành vi này mặc định **TẮT**. Bật bằng `AUTO_REMEDIATION_ENABLED=1` "
        f"trong `.env`. Để tắt lại, xoá biến hoặc đặt về `0`."
    )
    try:
        jira.add_comment(decision.jira_key, comment)
    except Exception as error:
        logger.warning(
            "%s: không post được comment auto-remediation (%s)",
            decision.jira_key,
            error,
        )

    if result.succeeded:
        _sinh_postmortem_va_dong(jira, decision.jira_key)

    return result


def _sinh_postmortem_va_dong(jira, jira_key: str) -> None:  # jira: JiraClient
    """Sau auto-fix THÀNH CÔNG: sinh postmortem rồi chuyển thẳng `Resolved`.

    ## Vì sao KHÔNG dừng ở `Remediating` như bản cũ

    Đo ngày 24/08 trên KAN-106: bản cũ chỉ `transition(REMEDIATING)` rồi dừng,
    để lại HAI lỗi cùng lúc trên một phiếu:

    1. **Bỏ dở.** Agent đã tự thi hành xong — rollback thành công — nhưng phiếu
       kẹt ở `Remediating`, không ai đóng. Webhook HITL bình thường thì sau khi
       thi hành xong đi tiếp: postmortem → `Resolved`. Auto-fix cũng phải khép
       vòng như vậy, nếu không "tự xử lý" chỉ đúng một nửa.

    2. **Tự đá vào cổng HITL.** Chuyển sang `Remediating` bằng tài khoản Agent
       kích hoạt đúng Jira Automation rule đang rình trạng thái đó → rule gọi
       webhook → `assert_human_approved()` thấy người chuyển là Agent → TỪ CHỐI,
       và dán một comment "TỪ CHỐI THỰC THI" ngay cạnh comment "đã rollback thành
       công". Hai câu chọi nhau trên cùng một phiếu.

    Chuyển THẲNG sang `Resolved` gỡ cả hai: rule `Remediating` không còn bắn, và
    rule `Resolved` (nếu có) tự bỏ qua vì `postmortem` đã tồn tại — cùng guard
    mà `POST /webhooks/jira/resolved` đang dùng.

    ⚠️ Postmortem phải sinh TRƯỚC khi chuyển `Resolved`: nó tính duration theo
    trạng thái hiện tại, chuyển trước thì `resolved_at` đổi và duration sai —
    cùng lý do webhook ghi ở "Bước 7".

    Mọi lỗi đều nuốt: rollback đã chạy rồi, một postmortem hỏng hay một
    transition trượt không đáng phá cả vòng quét. Tệ nhất là phiếu nằm chờ người
    kéo tay sang Resolved — vẫn tốt hơn kẹt ở Remediating kèm comment mâu thuẫn.
    """
    from src.services.postmortem_generator import generate_postmortem  # noqa: PLC0415

    try:
        incident = jira.get_incident(jira_key)
        if incident is not None:
            # Đóng dấu thời điểm phục hồi NGAY, trước khi sinh báo cáo.
            #
            # `get_incident()` đọc `resolved_at` từ trường `resolutiondate` của
            # Jira, mà lúc này phiếu vẫn còn ở `Awaiting Approval` — nên nó là
            # `None`. Hệ quả: mọi ô thời gian trong postmortem của đường
            # auto-fix đều rỗng ("Chưa resolved" cho cả tổng thời gian gián
            # đoạn lẫn MTTR), dù rollback vừa chạy xong và giờ phục hồi là
            # **bây giờ**. Đường HITL không dính lỗi này vì người duyệt kéo
            # phiếu sang Resolved trước, rồi webhook mới chạy.
            #
            # Không đảo thứ tự (chuyển Jira trước rồi mới sinh) vì `transition`
            # sang `Resolved` bằng tài khoản Agent sẽ kích hoạt Jira Automation
            # — xem phần đầu docstring hàm này.
            incident.state = IncidentState.RESOLVED
            incident.resolved_at = datetime.now(UTC)
            postmortem = generate_postmortem(incident, jira=jira)
            incident.postmortem = postmortem
            jira.attach_postmortem(jira_key, postmortem)
            _gui_mail_postmortem(incident)
    except Exception as error:
        logger.warning("%s: không sinh được postmortem sau auto-fix (%s)", jira_key, error)

    try:
        jira.transition(jira_key, IncidentState.RESOLVED)
    except Exception as error:
        logger.warning(
            "%s: không chuyển được sang Resolved sau auto-fix — kéo tay trên Jira (%s)",
            jira_key,
            error,
        )


def _gui_mail_postmortem(incident) -> None:  # incident: Incident
    """Gửi mail postmortem sau auto-fix — cùng nội dung như luồng người-duyệt.

    Vì sao cần tách riêng thay vì để `POST /webhooks/jira/resolved` lo: khi
    auto-fix chuyển thẳng `Resolved`, rule webhook đó CÓ bắn, nhưng guard
    "postmortem đã tồn tại → bỏ qua" của nó chặn lại (đúng, để không gửi trùng).
    Hệ quả không lường trước: đường auto-fix mất luôn mail postmortem. Đo ngày
    24/08 trên KAN-112 — phiếu tự đóng, có postmortem trên Jira, nhưng KHÔNG ai
    nhận được mail.

    Mail là **đường phát hành duy nhất** tới người không mở Jira. Auto-fix là
    lúc CẦN mail nhất: không ai đang ngồi xem, nên bản tóm tắt gửi tới hộp thư là
    thứ duy nhất báo cho họ Agent vừa tự làm gì.

    Nuốt mọi lỗi: mail là việc phụ, hỏng không được phá chuỗi auto-fix. Thiếu
    SMTP thì bỏ qua — postmortem đã nằm trên Jira rồi.
    """
    from src.services.email_client import Attachment, GmailClient  # noqa: PLC0415
    from src.services.postmortem_report import (  # noqa: PLC0415
        build_detailed_report,
        build_email_body,
    )

    settings = get_settings()
    if not settings.smtp_email or not settings.smtp_app_password:
        logger.info("%s: bỏ mail postmortem — SMTP chưa cấu hình", incident.jira_key)
        return
    recipients = [r.strip() for r in settings.postmortem_recipients.split(",") if r.strip()]
    if not recipients:
        logger.info("%s: bỏ mail postmortem — POSTMORTEM_RECIPIENTS trống", incident.jira_key)
        return

    try:
        jira_base_url = settings.jira_base_url
        email_body = build_email_body(incident, jira_base_url=jira_base_url)
        report_html = build_detailed_report(incident, jira_base_url=jira_base_url)
        services_str = ", ".join(incident.affected_services)
        GmailClient(settings.smtp_email, settings.smtp_app_password).send(
            to=recipients,
            subject=(
                f"[Postmortem — Auto] {incident.severity.value} — "
                f"{services_str} — {incident.jira_key}"
            ),
            body_html=email_body,
            attachments=[
                Attachment(
                    filename=f"postmortem_{incident.jira_key}.html",
                    content=report_html.encode("utf-8"),
                    mime_type="text/html",
                )
            ],
        )
        logger.info(
            "%s: đã gửi mail postmortem (auto-fix) tới %s",
            incident.jira_key, ", ".join(recipients),
        )
    except Exception as error:
        logger.warning("%s: không gửi được mail postmortem sau auto-fix (%s)",
                       incident.jira_key, error)


# ---------------------------------------------------------------------------
# Vế 3 — rollback dự phòng khi auto-fix không ăn
#
# Hai vế trên khép lại ở chỗ "đã thi hành". Vế này khép chỗ "thi hành xong mà sự
# cố vẫn còn": Agent đã tự quyết một lần rồi, nên nó cũng phải tự chịu trách
# nhiệm dọn lại phần nó vừa làm thay vì để nguyên hiện trạng cho người sáng hôm
# sau. Khác với hai vế trên, vế này KHÔNG đếm thời gian chờ người — nó đếm thời
# gian chờ **số đo**, xem `NGUONG_CHO_DO_LAI_PHUT`.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AutoFixRecord:
    """Dấu vết một lần Agent TỰ thi hành — đầu vào để xét rollback dự phòng.

    Vì sao cần bản ghi riêng chứ không đọc lại `incident.proposal`: với P1/P2
    hành động thật sự đã chạy là `rollback` bị ép, còn `proposal.action` vẫn là
    đề xuất gốc (`scale_up`, `restart`, ...). Tin vào `proposal` là rollback lần
    thứ hai một issue vừa rollback xong.

    Giữ trong tiến trình `run_agent.py`, cùng chỗ với `already_executed` và
    `da_verify`. Agent restart là mất — chấp nhận được: mất bản ghi thì cùng lắm
    là không rollback dự phòng, còn nhớ nhầm thì thi hành nhầm lên production.
    """

    jira_key: str
    #: Hành động ĐÃ CHẠY, không phải hành động đã đề xuất.
    action: str
    #: Service đã nhận lệnh — cũng là service sẽ bị rollback nếu tới bước đó.
    target: str
    #: Lúc thi hành xong, mốc để đếm `NGUONG_CHO_DO_LAI_PHUT`.
    at: datetime


@dataclass(frozen=True)
class FallbackRollbackDecision:
    """Quyết định rollback dự phòng cho một issue."""

    jira_key: str
    target: str
    #: Phiên bản đích, `None` khi **không xác định được**.
    #:
    #: Vẫn trả về quyết định thay vì nuốt luôn, vì "có nên rollback" và "rollback
    #: về đâu" là hai câu hỏi khác nhau. Câu đầu đã trả lời là CÓ; câu sau không
    #: trả lời được thì người trực phải biết — họ là người duy nhất tra được
    #: lịch sử deploy bằng tay lúc 3 giờ sáng.
    to_version: str | None
    #: Hành động auto-fix đã thử mà không ăn — để comment nói rõ đã thử gì.
    attempted_action: str
    #: Tín hiệu còn lại lúc đo lại, để comment nêu chỉ số vẫn vượt bao nhiêu.
    con_lai: IncidentSignal | None


def ready_to_remeasure(auto_fix: AutoFixRecord, bay_gio: datetime | None = None) -> bool:
    """Đã đủ `NGUONG_CHO_DO_LAI_PHUT` kể từ lúc tự thi hành chưa.

    Tách thành hàm riêng vì `run_agent.py` cần nó **trước** khi đo: đo sớm rồi
    bỏ kết quả đi thì vẫn đã post một comment "chưa đỡ" sai lên war room.
    """
    moc = bay_gio or datetime.now(UTC)
    return moc - auto_fix.at >= timedelta(minutes=NGUONG_CHO_DO_LAI_PHUT)


def should_fallback_rollback(
    auto_fix: AutoFixRecord | None,
    *,
    hoi_phuc: bool,
    te_hon: bool,
    con_lai: IncidentSignal | None = None,
    da_rollback_du_phong: bool = False,
    bay_gio: datetime | None = None,
) -> FallbackRollbackDecision | None:
    """Sau khi đo lại, có nên rollback về phiên bản cũ không.

    Args:
        auto_fix: Bản ghi lần Agent tự thi hành. `None` nghĩa là issue này do
            **người** duyệt — không thuộc phạm vi vế này. Agent chỉ tự dọn phần
            nó tự quyết; hành động do người duyệt thì người đó theo tới cùng.
        hoi_phuc, te_hon, con_lai: kết quả `verify()` đo lại.
        da_rollback_du_phong: issue này đã rollback dự phòng rồi. Mỗi issue đúng
            một lần — không thì Agent rollback vòng này qua vòng khác trong khi
            nguyên nhân nằm ở chỗ khác.
        bay_gio: mốc thời gian, để test không phải chờ thật.

    Returns:
        `FallbackRollbackDecision` (có thể mang `to_version=None`) khi nên
        rollback, `None` khi không.
    """
    if auto_fix is None or da_rollback_du_phong:
        return None

    if auto_fix.action == "rollback":
        # P1/P2 đã bị ép rollback ở vế 1 rồi. Rollback tiếp là lùi thêm một
        # phiên bản nữa mà không có bằng chứng nào nói phiên bản đó lành hơn.
        logger.info(
            "%s: auto-fix vốn đã là rollback — không rollback lần hai",
            auto_fix.jira_key,
        )
        return None

    if not ready_to_remeasure(auto_fix, bay_gio):
        return None

    if hoi_phuc:
        return None

    if te_hon:
        # `verify.py` vừa ghi thẳng lên war room: "Đừng thi hành thêm hành động
        # nào cho tới khi có người xem — hành động vừa rồi có thể đang làm tình
        # hình xấu đi". Rollback ngay sau câu đó là Agent tự mâu thuẫn với chính
        # nó, và là lúc tệ nhất để thêm một thay đổi nữa lên production.
        logger.warning(
            "%s: đo lại TỆ HƠN — KHÔNG rollback dự phòng, chờ người vào",
            auto_fix.jira_key,
        )
        return None

    to_version = resolve_rollback_version(auto_fix.target)
    return FallbackRollbackDecision(
        jira_key=auto_fix.jira_key,
        target=auto_fix.target,
        to_version=to_version,
        attempted_action=auto_fix.action,
        con_lai=con_lai,
    )


def _mo_ta_do_lai(con_lai: IncidentSignal | None) -> str:
    """Một dòng nói chỉ số đo lại vẫn vượt ngưỡng bao nhiêu.

    Người đọc comment cần con số để tự phán xét, không phải chỉ chữ "chưa đỡ".
    """
    if con_lai is None:
        return "Đo lại: vẫn còn tín hiệu sự cố."
    return (
        f"Đo lại: `{con_lai.metric_name}` = {con_lai.metric_value:.3f} "
        f"(ngưỡng {con_lai.threshold:.3f}), vượt liên tục "
        f"{con_lai.breached_for_seconds:.0f}s."
    )


def execute_fallback_rollback(
    jira,  # JiraClient
    decision: FallbackRollbackDecision,
) -> RemediationResult | None:
    """Thi hành rollback dự phòng và post comment lên Jira.

    Returns:
        `RemediationResult` khi đã thi hành, `None` khi **không xác định được
        phiên bản đích** — lúc đó hàm chỉ post comment nói rõ vì sao không làm
        được. Người gọi dựa vào `None` để biết là chưa có gì thay đổi trên
        production, nên không cần đo lại lần nữa.
    """
    do_lai = _mo_ta_do_lai(decision.con_lai)

    if decision.to_version is None:
        logger.error(
            "%s: cần rollback dự phòng nhưng không biết %s lùi về phiên bản nào",
            decision.jira_key,
            decision.target,
        )
        comment = (
            f"🔁 **{FALLBACK_MARKER} — nhưng KHÔNG rollback được**\n\n"
            f"Agent đã tự thi hành `{decision.attempted_action}` → "
            f"`{decision.target}` (không ai duyệt trong thời hạn), đo lại vẫn "
            f"chưa đỡ.\n\n"
            f"{do_lai}\n\n"
            f"Không có lịch sử deploy của `{decision.target}` nên **không xác "
            f"định được phiên bản để lùi về**. Agent dừng ở đây thay vì đoán: "
            f"một lệnh rollback không nói rõ về đâu thì không thi hành được và "
            f"cũng không kiểm chứng được.\n\n"
            f"👉 Cần người vào tra lịch sử deploy rồi tự quyết."
        )
        try:
            jira.add_comment(decision.jira_key, comment)
        except Exception as error:
            logger.warning(
                "%s: không post được comment rollback dự phòng (%s)",
                decision.jira_key,
                error,
            )
        return None

    logger.warning(
        "FALLBACK-ROLLBACK: %s — %s không ăn, rollback %s về %s",
        decision.jira_key,
        decision.attempted_action,
        decision.target,
        decision.to_version,
    )

    result = execute(
        "rollback",
        decision.target,
        approved_by=AUTO_APPROVED_BY,
        params={"to_version": decision.to_version},
    )

    # Cùng nhãn với lần tự thi hành đầu: rollback dự phòng vẫn là Agent tự quyết.
    if result.succeeded:
        _danh_dau_agent_da_fix(jira, decision.jira_key)

    comment = (
        f"🔁 **{FALLBACK_MARKER}**\n\n"
        f"Agent đã tự thi hành `{decision.attempted_action}` → "
        f"`{decision.target}` vì hết thời chờ duyệt, nhưng sự cố vẫn còn.\n\n"
        f"{do_lai}\n\n"
        f"Nên Agent lùi `{decision.target}` về `{decision.to_version}` — đưa hệ "
        f"thống về trạng thái trước khi nó tự can thiệp.\n\n"
        f"---\n\n"
        f"{result.as_comment()}\n\n"
        f"---\n\n"
        f"Đây là lần rollback dự phòng **duy nhất** cho issue này: đo lại lần nữa "
        f"mà vẫn chưa đỡ thì chẩn đoán ban đầu sai, và Agent không có căn cứ nào "
        f"để thi hành tiếp. 👉 Cần người vào xem."
    )
    try:
        jira.add_comment(decision.jira_key, comment)
    except Exception as error:
        logger.warning(
            "%s: không post được comment rollback dự phòng (%s)",
            decision.jira_key,
            error,
        )

    return result
