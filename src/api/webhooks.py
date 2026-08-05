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
from src.services.hitl import ApprovalError, assert_human_approved
from src.services.jira import JiraApiError, JiraClient, RealJiraClient
from src.services.remediation import UnsupportedActionError, execute

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

    try:
        result = execute(action, target, approved_by=approved_by, params=params)
    except UnsupportedActionError as exc:
        _try_comment(client, jira_key, f"⚠️ Không thi hành được: {exc}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    _try_comment(client, jira_key, result.as_comment())

    return {
        "jira_key": jira_key,
        "approved_by": approved_by,
        "action": result.action,
        "target": result.target,
        "succeeded": result.succeeded,
        "simulated": result.simulated,
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
