"""Contract ④ — Endpoint incident & status page.

Đường ghép: Đức (implement) → Long (tiêu thụ).

Đọc dữ liệu từ Jira thật qua `JiraClient` khi đã cấu hình đủ JIRA_BASE_URL /
JIRA_EMAIL / JIRA_API_TOKEN. Thiếu cấu hình (máy chưa có token, CI) thì
fallback về fixture JSON trong `src/api/fixtures/` — **hình dạng response
không đổi** giữa hai đường, nên UI của Long không phải sửa gì.

Long chỉ cần quan tâm: gọi endpoint nào, nhận về JSON hình gì.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.api.webhooks import build_jira_client
from src.config import get_settings
from src.models.incident import Incident, ServiceHealth, ServiceStatus, StatusPage
from src.services.jira import JiraApiError, JiraClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["incidents"])

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Danh sách service cố định cho status page công khai. Chưa có nguồn cấu hình
# tập trung nào liệt kê service động (Prometheus targets không lộ qua API
# này) — 2 tên này được chốt ở docs/contracts/01-metrics.md mục "Trung phải
# đảm bảo". Giữ đúng 2 tên đã dùng trong fixture làm danh sách cố định.
KNOWN_SERVICES = ("service-thanh-toan", "service-dat-hang")

# P1/P2 → down, P3/P4 → degraded, theo đúng bảng ngưỡng contract ①.
_DOWN_SEVERITIES = {"P1", "P2"}
_SEVERITY_RANK = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}


def _public_message(health: ServiceHealth, jira_key: str) -> str:
    """Câu hiển thị công khai — chung chung, không lộ tên metric/số liệu thô.

    Status page là trang công khai cho người dùng cuối, khác với war-room
    (nội bộ) — `incident.title` chứa chi tiết kỹ thuật (tên metric, ngưỡng)
    không phù hợp hiện ra đây.
    """
    if health == ServiceHealth.DOWN:
        return f"Đang gặp sự cố — xem {jira_key} để biết chi tiết"
    return f"Suy giảm hiệu năng — xem {jira_key} để biết chi tiết"


def _get_jira_client() -> JiraClient | None:
    """`RealJiraClient` nếu đã cấu hình đủ Jira, None nếu chưa (dùng fixture).

    Không cache client instance — tạo mới mỗi lần gọi, giống cách
    `build_jira_client()` bên webhooks.py đang làm. Hai endpoint này không đủ
    tải để việc mở lại `httpx.Client` mỗi request thành vấn đề hiệu năng.
    """
    settings = get_settings()
    if settings.jira_base_url and settings.jira_email and settings.jira_api_token:
        return build_jira_client()
    logger.warning(
        "Thiếu JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN trong cấu hình — "
        "dùng dữ liệu fixture trong src/api/fixtures/ thay vì Jira thật."
    )
    return None


def _jira_error_response(exc: JiraApiError) -> HTTPException:
    """Đổi lỗi gọi Jira thành HTTP có nghĩa, không để lộ traceback 500 trống rỗng."""
    if exc.status_code in (401, 403):
        return HTTPException(502, "Jira từ chối xác thực — kiểm tra JIRA_EMAIL/JIRA_API_TOKEN.")
    if exc.status_code == 429:
        return HTTPException(502, "Jira rate limit — thử lại sau ít phút.")
    return HTTPException(502, f"Không đọc được dữ liệu từ Jira: {exc}")


def _load_incidents_fixture() -> list[Incident]:
    raw = json.loads((FIXTURES_DIR / "incidents.json").read_text(encoding="utf-8"))
    return [Incident.model_validate(item) for item in raw]


def _load_incidents(only_open: bool) -> list[Incident]:
    """Danh sách incident — Jira thật nếu đã cấu hình, fixture nếu chưa.

    Không còn `@lru_cache`: dữ liệu Jira đổi liên tục (Agent tạo issue mới,
    người duyệt chuyển trạng thái), cache cứng sẽ làm war room không bao giờ
    thấy incident mới cho tới khi restart process.
    """
    client = _get_jira_client()
    if client is not None:
        return client.list_incidents(only_open=only_open)
    incidents = _load_incidents_fixture()
    if only_open:
        incidents = [incident for incident in incidents if incident.is_open]
    return incidents


def _health_for(open_incidents: list[Incident], service: str) -> tuple[ServiceHealth, str, str | None]:
    """Suy ra health/message/active_incident của một service từ incident đang mở.

    Nhiều incident cùng ảnh hưởng một service thì lấy incident severity nặng
    nhất — cùng tinh thần `StatusPage.overall_health` (lấy mức xấu nhất).
    """
    affecting = [incident for incident in open_incidents if service in incident.affected_services]
    if not affecting:
        return ServiceHealth.OPERATIONAL, "Hoạt động bình thường", None

    worst = min(affecting, key=lambda incident: _SEVERITY_RANK.get(incident.severity.value, 99))
    health = ServiceHealth.DOWN if worst.severity.value in _DOWN_SEVERITIES else ServiceHealth.DEGRADED
    return health, _public_message(health, worst.jira_key), worst.jira_key


def _load_status_page() -> StatusPage:
    """Status page — suy ra từ incident đang mở trên Jira nếu đã cấu hình.

    Danh sách service CỐ ĐỊNH (xem `KNOWN_SERVICES` ở trên) — chỉ
    health/message/active_incident của từng service là suy ra động từ Jira.
    """
    client = _get_jira_client()
    if client is None:
        raw = json.loads((FIXTURES_DIR / "status.json").read_text(encoding="utf-8"))
        return StatusPage.model_validate(raw)

    open_incidents = client.list_incidents(only_open=True)
    services = []
    for name in KNOWN_SERVICES:
        health, message, active_incident = _health_for(open_incidents, name)
        services.append(ServiceStatus(name=name, health=health, message=message, active_incident=active_incident))

    return StatusPage(
        updated_at=datetime.now().astimezone(),
        services=services,
        active_incidents=open_incidents,
    )


@router.get("/incidents", response_model=list[Incident])
async def list_incidents(only_open: bool = False) -> list[Incident]:
    """Danh sách incident cho war-room view (nội bộ, vai trò on-call/IC).

    Args:
        only_open: True để chỉ lấy incident chưa Resolved.
    """
    try:
        incidents = _load_incidents(only_open)
    except JiraApiError as exc:
        logger.error("Jira lỗi khi lấy danh sách incident: %s", exc)
        raise _jira_error_response(exc) from exc
    return sorted(incidents, key=lambda incident: incident.detected_at, reverse=True)


@router.get("/incidents/{jira_key}", response_model=Incident)
async def get_incident(jira_key: str) -> Incident:
    """Chi tiết một incident: giả thuyết, bằng chứng, timeline, postmortem."""
    client = _get_jira_client()
    if client is not None:
        try:
            incident = client.get_incident(jira_key)
        except JiraApiError as exc:
            logger.error("Jira lỗi khi đọc %s: %s", jira_key, exc)
            raise _jira_error_response(exc) from exc
        if incident is None:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy incident {jira_key}")
        return incident

    for incident in _load_incidents_fixture():
        if incident.jira_key == jira_key:
            return incident
    raise HTTPException(status_code=404, detail=f"Không tìm thấy incident {jira_key}")


@router.get("/status", response_model=StatusPage)
async def status_page() -> StatusPage:
    """Dữ liệu status page công khai — không cần đăng nhập."""
    try:
        return _load_status_page()
    except JiraApiError as exc:
        logger.error("Jira lỗi khi dựng status page: %s", exc)
        raise _jira_error_response(exc) from exc
