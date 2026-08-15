"""`POST /webhooks/jira` — mảnh nối cuối cùng của luồng HITL.

Đây là bước 8 trong kịch bản demo: on-call bấm duyệt trên Jira → Jira
Automation gọi endpoint này → backend **xác minh có người thật phê duyệt** →
mới thi hành hành động khắc phục.

Ba lớp kiểm tra, theo thứ tự:

1. **Shared secret** — chặn người ngoài gọi endpoint này. Không có secret thì
   bất kỳ ai biết URL đều kích được remediation.
2. **`hitl.assert_human_approved()`** — hỏi Jira changelog ai đã chuyển issue
   sang `Remediating`. Nếu là account Agent → từ chối. Đây là ràng buộc bắt
   buộc của đề bài.
3. **`remediation.execute()`** — chỉ nhận hành động trong danh sách cho phép.

Khi bị từ chối ở lớp 2, backend còn **post comment cảnh báo lên chính issue đó**
— để trạng thái `Remediating` trên Jira không khiến người xem tưởng hành động đã
được thi hành.
"""

from __future__ import annotations

import hmac
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request, status

from src.config import get_settings
from src.models.incident import Incident, IncidentState
from src.services.email_client import Attachment, GmailClient
from src.services.hitl import ApprovalError, assert_human_approved
from src.services.jira import JiraApiError, JiraClient, RealJiraClient
from src.services.postmortem_generator import generate_postmortem
from src.services.postmortem_report import build_detailed_report, build_email_body
from src.services.remediation import UnsupportedActionError, execute, is_already_remediated
from src.services.status_updater import status_approved

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


def build_jira_client() -> JiraClient:
    """Tạo `RealJiraClient` từ cấu hình.

    Tách thành hàm riêng để test ghi đè được bằng `app.dependency_overrides`
    hoặc monkeypatch, không cần gọi Jira thật.
    """
    settings = get_settings()
    return RealJiraClient(
        base_url=settings.jira_base_url,
        email=settings.jira_email,
        api_token=settings.jira_api_token,
        project_key=settings.jira_project_key,
    )


def _issue_key_from(payload: dict[str, Any]) -> str | None:
    """Rút issue key ra khỏi payload Jira.

    Jira Automation gửi nhiều hình dạng tuỳ cấu hình body: nguyên `Issue data`
    (`{"issue": {"key": ...}}`), hoặc custom JSON. Nhận cả ba dạng phổ biến để
    không phải cấu hình Jira thật chính xác mới chạy được.
    """
    issue = payload.get("issue")
    if isinstance(issue, dict) and issue.get("key"):
        return str(issue["key"])
    for field in ("issueKey", "key"):
        if payload.get(field):
            return str(payload[field])
    return None


@router.post("/jira")
async def jira_webhook(
    request: Request,
    x_webhook_secret: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Nhận trigger từ Jira Automation sau khi issue chuyển sang `Remediating`."""
    settings = get_settings()

    # ---- Lớp 1: shared secret ----
    if not settings.jira_webhook_secret:
        # Không cấu hình secret thì từ chối hẳn, chứ không chạy ở chế độ mở.
        # Endpoint này kích được hành động production nên không có đường "tạm bỏ qua".
        logger.error("JIRA_WEBHOOK_SECRET chưa cấu hình — từ chối mọi webhook")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Webhook chưa được cấu hình secret. Đặt JIRA_WEBHOOK_SECRET trước khi dùng.",
        )
    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, settings.jira_webhook_secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sai hoặc thiếu X-Webhook-Secret")

    payload = await request.json()
    jira_key = _issue_key_from(payload)
    if not jira_key:
        raise HTTPException(
            422,
            "Không tìm thấy issue key trong payload (cần issue.key, issueKey hoặc key)",
        )

    client = build_jira_client()

    # ---- Lớp 2: cổng phê duyệt HITL ----
    try:
        approved_by = assert_human_approved(
            client, jira_key, agent_account_id=settings.jira_agent_account_id
        )
    except JiraApiError as exc:
        # Không để lỗi Jira thành HTTP 500 trống rỗng — lúc demo sẽ không biết
        # tắc ở token, ở issue không tồn tại, hay ở Jira đang down.
        logger.error("Jira lỗi khi kiểm phê duyệt %s: %s", jira_key, exc)
        raise _jira_http_error(jira_key, exc) from exc
    except ApprovalError as exc:
        logger.warning("Từ chối remediation cho %s: %s", jira_key, exc)
        # Cảnh báo ngay trên war room, để trạng thái Remediating không gây hiểu nhầm
        # là hành động đã được thi hành.
        _try_comment(
            client,
            jira_key,
            f"⚠️ TỪ CHỐI THỰC THI. {exc}\n\n"
            "Issue đang ở trạng thái Remediating nhưng KHÔNG có hành động nào được "
            "thi hành. Cần người có quyền phê duyệt thực hiện lại bước chuyển trạng thái.",
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    # ---- Lớp 2½: idempotency — kiểm tra xem bên kia đã thi hành chưa ----
    #
    # Webhook (Render) và poll_jira_approvals (agent loop) chạy trên hai tiến
    # trình khác nhau. Không có bước này thì 1 lần duyệt → 2 lần execute,
    # gây 2 lần remediation thật + 4 comment + 2 postmortem + 2 email.
    #
    # Jira comment là chỗ nhớ chung duy nhất cả hai cùng nhìn thấy.
    if is_already_remediated(client, jira_key):
        logger.info("%s: đã được thi hành bởi đường khác — bỏ qua", jira_key)
        return {
            "jira_key": jira_key,
            "already_done": True,
            "detail": "Remediation đã được thi hành (phát hiện qua comment marker). Bỏ qua để tránh trùng.",
        }

    # ---- Lớp 3: thi hành ----
    try:
        incident = client.get_incident(jira_key)
    except JiraApiError as exc:
        logger.error("Jira lỗi khi đọc %s: %s", jira_key, exc)
        raise _jira_http_error(jira_key, exc) from exc
    proposal = incident.proposal if incident else None
    if proposal is None:
        # `proposal` có thể vẫn None nếu comment mang JSON bị hỏng/không parse được
        # (xem except ValidationError trong RealJiraClient.get_incident), hoặc issue
        # được tạo trước khi tính năng này tồn tại. Cho phép Jira Automation truyền
        # hành động trong payload làm đường lùi, và đây cũng là đường để test không
        # phụ thuộc đường đọc.
        action = payload.get("action")
        target = payload.get("target")
        params = payload.get("params") or {}
        if not (action and target):
            raise HTTPException(
                422,
                f"{jira_key} không có đề xuất khắc phục đọc lại được, và payload cũng "
                "không có 'action' + 'target'.",
            )
    else:
        action, target, params = proposal.action, proposal.target, proposal.params

    # Agent auto-comment: PHÊ DUYỆT + ĐANG THỰC THI
    _try_comment(client, jira_key, status_approved(approved_by))

    try:
        result = execute(action, target, approved_by=approved_by, params=params)
    except UnsupportedActionError as exc:
        _try_comment(client, jira_key, f"⚠️ Không thi hành được: {exc}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    _try_comment(client, jira_key, result.as_comment())

    # ---- Bước 6: Sinh postmortem + gửi email ----
    # Chạy SAU remediation thành công. Lỗi ở đây không được phá webhook
    # response: remediation đã thi hành, rollback lại thì tệ hơn.
    postmortem_sent = False
    if result.succeeded:
        postmortem_sent = _try_send_postmortem(client, jira_key)

        # ---- Bước 7: Đóng incident — chuyển sang Resolved ----
        # Phải chạy SAU postmortem: postmortem cần incident ở trạng thái hiện tại
        # để tính duration đúng. Chuyển trước thì `resolved_at` đổi và duration sai.
        #
        # Lỗi transition không được phá webhook: remediation đã thi hành, postmortem
        # đã gửi — tệ nhất là ticket kẹt ở Remediating trên board, người trực
        # kéo tay sang Resolved là xong.
        try:
            client.transition(jira_key, IncidentState.RESOLVED)
        except Exception:
            logger.exception(
                "%s: không chuyển được sang Resolved — kéo tay trên Jira board",
                jira_key,
            )

    return {
        "jira_key": jira_key,
        "approved_by": approved_by,
        "action": result.action,
        "target": result.target,
        "succeeded": result.succeeded,
        "simulated": result.simulated,
        "postmortem_sent": postmortem_sent,
    }


def _jira_http_error(jira_key: str, exc: JiraApiError) -> HTTPException:
    """Đổi lỗi Jira thành HTTP có nghĩa, kèm gợi ý chỗ cần kiểm.

    Không có hàm này thì mọi lỗi Jira đều thành 500 giống nhau: token sai, issue
    không tồn tại, Jira rate limit, Jira down — cùng một thông báo trống rỗng.
    """
    code = exc.status_code
    if code == 404:
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Không tìm thấy issue {jira_key} trên Jira.",
        )
    if code in (401, 403):
        return HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Jira từ chối xác thực — kiểm JIRA_EMAIL và JIRA_API_TOKEN trên Render. "
            "Token phải là của account Agent.",
        )
    if code == 429:
        return HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Jira rate limit. Thử lại sau ít phút.",
        )
    return HTTPException(status.HTTP_502_BAD_GATEWAY, f"Jira lỗi: {exc}")


def _try_comment(client: JiraClient, jira_key: str, body: str) -> None:
    """Post comment, nhưng lỗi Jira không được làm sập luồng chính.

    Comment là để người đọc; nếu Jira lỗi lúc này thì hành động khắc phục đã
    thi hành rồi, ném exception ra sẽ khiến Jira Automation retry và thi hành lần hai.
    """
    try:
        client.add_comment(jira_key, body)
    except Exception:
        logger.exception("Không post được comment lên %s", jira_key)


def _try_send_postmortem(client: JiraClient, jira_key: str) -> bool:
    """Sinh postmortem từ dữ liệu thật và gửi email — việc phụ, không phá webhook.

    Luồng:
        1. Đọc Incident đầy đủ từ Jira
        2. Sinh postmortem (summary, root cause, impact, action items)
        3. Tạo Jira sub-task cho mỗi action item
        4. Attach postmortem lên Jira issue
        5. Render email body (vắn tắt cho manager) + report HTML (chi tiết cho IT)
        6. Gửi email tới POSTMORTEM_RECIPIENTS

    Returns:
        True nếu gửi email thành công, False nếu bất kỳ bước nào lỗi.
    """
    settings = get_settings()

    # Kiểm tra config email — thiếu thì bỏ qua im lặng
    if not settings.smtp_email or not settings.smtp_app_password:
        logger.info(
            "%s: bỏ qua postmortem email — SMTP_EMAIL hoặc SMTP_APP_PASSWORD chưa cấu hình",
            jira_key,
        )
        return False

    recipients = [r.strip() for r in settings.postmortem_recipients.split(",") if r.strip()]
    if not recipients:
        logger.info("%s: bỏ qua postmortem email — POSTMORTEM_RECIPIENTS trống", jira_key)
        return False

    try:
        # 1. Đọc incident đầy đủ
        incident = client.get_incident(jira_key)
        if incident is None:
            logger.warning("%s: không đọc được incident từ Jira — bỏ qua postmortem", jira_key)
            return False

        # 2+3. Sinh postmortem + tạo sub-tasks
        postmortem = generate_postmortem(incident, jira=client)
        incident.postmortem = postmortem

        # 4. Attach postmortem lên Jira
        try:
            client.attach_postmortem(jira_key, postmortem)
        except Exception:
            logger.exception("%s: không attach được postmortem lên Jira (vẫn gửi email)", jira_key)

        # 5. Render HTML
        jira_base_url = settings.jira_base_url
        email_body = build_email_body(incident, jira_base_url=jira_base_url)
        report_html = build_detailed_report(incident, jira_base_url=jira_base_url)

        # 6. Gửi email
        gmail = GmailClient(settings.smtp_email, settings.smtp_app_password)
        services_str = ", ".join(incident.affected_services)
        result = gmail.send(
            to=recipients,
            subject=f"[Postmortem] {incident.severity.value} — {services_str} — {jira_key}",
            body_html=email_body,
            attachments=[
                Attachment(
                    filename=f"postmortem_{jira_key}.html",
                    content=report_html.encode("utf-8"),
                    mime_type="text/html",
                )
            ],
        )

        if result.success:
            logger.info("%s: %s", jira_key, result.summary())
            # Comment lên Jira để ghi nhận đã gửi postmortem
            _try_comment(
                client,
                jira_key,
                f"📧 Đã gửi báo cáo postmortem tới {', '.join(recipients)}",
            )
            return True

        logger.warning("%s: gửi postmortem email thất bại — %s", jira_key, result.error)
        return False

    except Exception:
        logger.exception("%s: lỗi không mong đợi khi sinh/gửi postmortem", jira_key)
        return False


@router.post("/jira/resolved")
async def jira_resolved_webhook(
    request: Request,
    x_webhook_secret: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Nhận trigger từ Jira khi issue chuyển thẳng sang `Resolved`.

    Luồng này xử lý trường hợp con người **không đồng ý** với đề xuất Agent và
    tự sửa bằng tay, rồi kéo ticket thẳng sang Resolved mà không qua
    Remediating. Agent vẫn cần sinh postmortem từ dữ liệu có sẵn.

    Khác với ``POST /webhooks/jira`` ở mấy điểm:

    1. **Không kiểm HITL** — con người đã tự sửa xong, không cần phê duyệt.
    2. **Không execute** — không có hành động nào cần thi hành.
    3. **Postmortem ghi rõ** — resolved thủ công, lấy thông tin từ comments con
       người viết trên ticket.

    Jira Automation rule: WHEN issue chuyển sang Resolved THEN POST tới đây.
    """
    settings = get_settings()

    # ---- Lớp 1: shared secret (giống endpoint chính) ----
    if not settings.jira_webhook_secret:
        logger.error("JIRA_WEBHOOK_SECRET chưa cấu hình — từ chối mọi webhook")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Webhook chưa được cấu hình secret.",
        )
    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, settings.jira_webhook_secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sai hoặc thiếu X-Webhook-Secret")

    payload = await request.json()
    jira_key = _issue_key_from(payload)
    if not jira_key:
        raise HTTPException(
            422,
            "Không tìm thấy issue key trong payload (cần issue.key, issueKey hoặc key)",
        )

    client = build_jira_client()

    # Xác nhận issue đã resolved (đọc state từ Jira)
    try:
        incident = client.get_incident(jira_key)
    except JiraApiError as exc:
        logger.error("Jira lỗi khi đọc %s: %s", jira_key, exc)
        raise _jira_http_error(jira_key, exc) from exc

    if incident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Không tìm thấy issue {jira_key}")

    # ---- Guard: nếu Rule #1 đã xử lý rồi, skip ----
    # Kịch bản: con người đồng ý → Rule #1 fire → execute + postmortem + auto-Resolved
    #           → Rule #2 fire (vì ticket vừa sang Resolved) → endpoint này.
    # Nếu postmortem đã có, không cần gửi lại.
    if incident.postmortem is not None:
        logger.info(
            "%s: postmortem đã tồn tại — bỏ qua (đã xử lý qua /webhooks/jira)",
            jira_key,
        )
        return {
            "jira_key": jira_key,
            "resolved_by": client.get_transition_author(jira_key, IncidentState.RESOLVED),
            "resolution": "already_handled",
            "resolution_note": None,
            "postmortem_sent": False,
        }

    # Xác định ai resolved
    resolved_by = client.get_transition_author(jira_key, IncidentState.RESOLVED)

    # Lấy ghi chú từ payload (con người có thể gửi kèm)
    resolution_note = payload.get("resolution_note", "")

    # Ghi nhận trên war room
    if resolution_note:
        _try_comment(
            client, jira_key,
            f"📝 GHI CHÚ GIẢI QUYẾT THỦ CÔNG\n\n{resolution_note}",
        )
    else:
        _try_comment(
            client, jira_key,
            "📝 Incident được giải quyết thủ công (không qua đề xuất Agent). "
            "Không có ghi chú giải quyết — postmortem sẽ ghi nhận là 'giải quyết thủ công'.",
        )

    # ---- Sinh postmortem ----
    postmortem_sent = _try_send_postmortem_manual(
        client, jira_key, incident,
        resolved_by=resolved_by or "unknown",
        resolution_note=resolution_note,
    )

    return {
        "jira_key": jira_key,
        "resolved_by": resolved_by,
        "resolution": "manual",
        "resolution_note": resolution_note or None,
        "postmortem_sent": postmortem_sent,
    }


def _try_send_postmortem_manual(
    client: JiraClient,
    jira_key: str,
    incident: Incident,
    *,
    resolved_by: str,
    resolution_note: str,
) -> bool:
    """Sinh postmortem cho incident resolved thủ công — không qua execute.

    Khác ``_try_send_postmortem()`` ở chỗ:
    - Không có ``result`` từ execute — thay bằng ghi chú thủ công.
    - ``actions_taken`` ghi rõ là giải quyết bằng tay.
    - Nếu con người có comment ghi chú thì lấy vào.

    Returns:
        True nếu gửi email thành công.
    """
    settings = get_settings()

    if not settings.smtp_email or not settings.smtp_app_password:
        logger.info(
            "%s: bỏ qua postmortem email — SMTP chưa cấu hình", jira_key,
        )
        return False

    recipients = [r.strip() for r in settings.postmortem_recipients.split(",") if r.strip()]
    if not recipients:
        logger.info("%s: bỏ qua postmortem email — POSTMORTEM_RECIPIENTS trống", jira_key)
        return False

    try:
        # Bổ sung thông tin giải quyết thủ công vào incident trước khi sinh postmortem
        from src.models.incident import TimelineEvent

        incident.timeline.append(
            TimelineEvent(
                at=incident.resolved_at or _now(),
                actor=resolved_by,
                action="resolved_manual",
                detail=resolution_note or "Resolved thủ công — không qua đề xuất Agent",
            )
        )

        postmortem = generate_postmortem(incident, jira=client)

        # Ghi đè actions_taken: vì không qua execute nên cần ghi rõ
        if resolution_note:
            postmortem.actions_taken = [
                f"Giải quyết thủ công: {resolution_note}",
            ]
        else:
            postmortem.actions_taken = [
                "Giải quyết thủ công — chi tiết chưa được ghi nhận.",
                "Đề xuất Agent không được sử dụng.",
            ]

        incident.postmortem = postmortem

        # Attach lên Jira
        try:
            client.attach_postmortem(jira_key, postmortem)
        except Exception:
            logger.exception("%s: không attach được postmortem (vẫn gửi email)", jira_key)

        # Render + gửi email
        jira_base_url = settings.jira_base_url
        email_body = build_email_body(incident, jira_base_url=jira_base_url)
        report_html = build_detailed_report(incident, jira_base_url=jira_base_url)

        gmail = GmailClient(settings.smtp_email, settings.smtp_app_password)
        services_str = ", ".join(incident.affected_services)
        result = gmail.send(
            to=recipients,
            subject=f"[Postmortem — Manual] {incident.severity.value} — {services_str} — {jira_key}",
            body_html=email_body,
            attachments=[
                Attachment(
                    filename=f"postmortem_{jira_key}.html",
                    content=report_html.encode("utf-8"),
                    mime_type="text/html",
                )
            ],
        )

        if result.success:
            logger.info("%s: %s (manual resolution)", jira_key, result.summary())
            _try_comment(
                client, jira_key,
                f"📧 Đã gửi báo cáo postmortem (manual resolution) tới {', '.join(recipients)}",
            )
            return True

        logger.warning("%s: gửi postmortem email thất bại — %s", jira_key, result.error)
        return False

    except Exception:
        logger.exception("%s: lỗi khi sinh/gửi postmortem manual", jira_key)
        return False


def _now():
    """Helper — tránh import datetime ở top-level chỉ cho một chỗ."""
    from datetime import UTC
    from datetime import datetime as dt
    return dt.now(UTC)

