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
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.api.webhooks import build_jira_client
from src.config import get_settings
from src.models.incident import (
    Incident,
    IncidentLogs,
    ServiceHealth,
    ServiceStatus,
    StatusPage,
)
from src.services.jira import JiraApiError, JiraClient
from src.services.log_collector import thu_thap_co_ly_do

logger = logging.getLogger(__name__)

router = APIRouter(tags=["incidents"])

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Danh sách service cố định cho status page công khai. Chưa có nguồn cấu hình
# tập trung nào liệt kê service động (Prometheus targets không lộ qua API
# này) — 4 tên này được chốt ở docs/contracts/01-metrics.md mục "Trung phải
# đảm bảo" và khớp `scrape_configs` trong demo/prometheus.yml.
#
# ⚠️ Thêm tên vào đây là CHƯA ĐỦ để service hiện trên status page: hằng số này
# chỉ chi phối đường Jira. Đường fixture đọc `fixtures/status.json`, nên phải
# thêm cả ở đó — `_du_service()` bên dưới là lưới an toàn cho lúc quên.
KNOWN_SERVICES = (
    "service-thanh-toan",
    "service-dat-hang",
    "service-kho-hang",
    "service-van-chuyen",
)

# Cửa sổ log quanh mốc phát hiện. 2 phút mỗi bên là đúng khoảng `analyze_logs`
# gợi ý cho LLM — giữ giống nhau để war room và Agent nhìn cùng một đoạn.
LOG_TRUOC_PHUT = 2
LOG_SAU_PHUT = 2

# Trần độ dài cửa sổ. Sự cố mở từ hôm kia mà chưa ai đóng thì `docker logs
# --since` sẽ đọc cả stream hai ngày — `collect_container_logs()` có timeout 10s
# nên nó chỉ chết lặng chứ không treo, nhưng cũng chẳng trả về gì. Cắt về 6 giờ
# gần nhất: với sự cố đang diễn ra thì thứ đáng xem là những gì ĐANG chảy ra,
# không phải mốc phát hiện đã cũ nửa ngày.
LOG_CUA_SO_TOI_DA = timedelta(hours=6)

# Trần số dòng trả cho war room. Cao hơn `MAX_LOG_LINES` (50) của Agent vì trần
# đó sinh ra để tiết kiệm token LLM — người đọc war room không tốn token nào, và
# giao diện đã gộp dòng trùng nên nhiều dòng không thành rối.
LOG_SO_DONG_TOI_DA = 200

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


def _du_service(services: list[ServiceStatus]) -> list[ServiceStatus]:
    """Bổ sung service có trong `KNOWN_SERVICES` mà danh sách truyền vào còn thiếu.

    Fixture là JSON tĩnh, rất dễ quên sửa khi thêm service mới — và thiếu ở đây
    thì UI **không có thẻ nào để vẽ**, không có lỗi nào báo ra. Đúng kiểu hỏng
    im lặng đã vấp ngày 22/08 khi thêm kho-hàng và vận-chuyển.

    Service bổ sung mặc định `operational`: không có incident nào nhắc tới nó
    thì đúng theo `_health_for()` nó là bình thường.
    """
    da_co = {svc.name for svc in services}
    return [
        *services,
        *(
            ServiceStatus(
                name=ten,
                health=ServiceHealth.OPERATIONAL,
                message="Hoạt động bình thường",
                active_incident=None,
            )
            for ten in KNOWN_SERVICES
            if ten not in da_co
        ),
    ]


def _load_status_page() -> StatusPage:
    """Status page — suy ra từ incident đang mở trên Jira nếu đã cấu hình.

    Danh sách service CỐ ĐỊNH (xem `KNOWN_SERVICES` ở trên) — chỉ
    health/message/active_incident của từng service là suy ra động từ Jira.
    """
    client = _get_jira_client()
    if client is None:
        raw = json.loads((FIXTURES_DIR / "status.json").read_text(encoding="utf-8"))
        trang = StatusPage.model_validate(raw)
        return trang.model_copy(update={"services": _du_service(trang.services)})

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


def _tim_incident(jira_key: str) -> Incident:
    """Một incident theo mã, Jira thật nếu có cấu hình. 404 nếu không thấy."""
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


@router.get("/incidents/{jira_key}", response_model=Incident)
async def get_incident(jira_key: str) -> Incident:
    """Chi tiết một incident: giả thuyết, bằng chứng, timeline, postmortem."""
    return _tim_incident(jira_key)


def _cua_so_log(incident: Incident) -> tuple[datetime, datetime, bool]:
    """Khoảng thời gian nên đọc log của một sự cố, và sự cố có còn mở không.

    Sự cố còn mở → kéo tới **bây giờ**: đó chính là chỗ "log realtime" nằm, vì
    dòng đang chảy ra lúc này mới là thứ chứng minh sự cố ĐANG diễn ra.
    Sự cố đã đóng → dừng ở `resolved_at`, cộng thêm lề để thấy cả lúc nó hồi.
    """
    bay_gio = datetime.now().astimezone()
    bat_dau = incident.detected_at - timedelta(minutes=LOG_TRUOC_PHUT)

    dang_mo = incident.resolved_at is None
    ket_thuc = bay_gio if dang_mo else incident.resolved_at + timedelta(minutes=LOG_SAU_PHUT)
    # Sự cố đã đóng nhưng mốc đóng còn ở tương lai (lệch giờ máy) thì đừng để
    # cửa sổ chạy quá hiện tại — `docker logs --until` tương lai là vô nghĩa.
    ket_thuc = min(ket_thuc, bay_gio)

    if ket_thuc - bat_dau > LOG_CUA_SO_TOI_DA:
        bat_dau = ket_thuc - LOG_CUA_SO_TOI_DA
    return bat_dau, ket_thuc, dang_mo


@router.get("/incidents/{jira_key}/logs", response_model=IncidentLogs)
async def get_incident_logs(jira_key: str) -> IncidentLogs:
    """Log thô của service bị ảnh hưởng, đọc TƯƠI theo cửa sổ của sự cố.

    Dành cho war room (nội bộ). Đây **không** phải `hypotheses[].log_evidence`:
    cái đó chỉ được lưu khi log đổi được kết luận của Agent, nên phần lớn sự cố
    không có dòng nào dù Agent đã đọc log thật.

    ⚠️ Đọc bằng `docker logs` trên chính máy chạy API. Bản deploy trên Render
    không có Docker và không thấy container demo nào, nên ở đó endpoint này
    **luôn** trả rỗng kèm `ly_do = "khong-co-docker"` — cố ý trả 200 chứ không
    502: không có log không phải lỗi, và war room cần câu giải thích để hiện ra
    chứ không cần một mã lỗi.
    """
    incident = _tim_incident(jira_key)

    service = ""
    if incident.signal is not None:
        service = incident.signal.affected_service
    elif incident.affected_services:
        service = incident.affected_services[0]

    bat_dau, ket_thuc, dang_mo = _cua_so_log(incident)
    if not service:
        return IncidentLogs(
            jira_key=jira_key,
            service="",
            start=bat_dau,
            end=ket_thuc,
            dang_mo=dang_mo,
            ly_do="khong-ro-service",
        )

    ket_qua = thu_thap_co_ly_do(
        service,
        bat_dau.isoformat(),
        ket_thuc.isoformat(),
        max_lines=LOG_SO_DONG_TOI_DA,
    )
    return IncidentLogs(
        jira_key=jira_key,
        service=service,
        start=bat_dau,
        end=ket_thuc,
        dang_mo=dang_mo,
        ly_do=ket_qua.ly_do,
        logs=ket_qua.logs,
    )


#: Bao lâu thì `/api/status` mới hỏi lại Jira.
#:
#: ## Vì sao cần đệm, và vì sao chỉ 3 giây
#:
#: Từ 24/08 status page tự cập nhật **mỗi giây** từ trình duyệt. Không có đệm
#: thì mỗi giây là một câu JQL lên Jira, nhân với số người đang mở trang — Jira
#: trả 429 rate limit rất nhanh, và lúc đó trang trắng chứ không phải chậm.
#:
#: 3 giây vì đó là mức làm Jira an toàn mà mắt không nhận ra độ trễ. Không đặt
#: cao hơn: trạng thái dịch vụ là thứ người ta mở trang này để xem, chậm vài
#: giây thì được, chậm nửa phút thì trang mất ý nghĩa.
#:
#: Đệm ở ĐÂY chứ không phải ở trình duyệt là có chủ ý: một chỗ đệm phục vụ mọi
#: người xem, nên mười người mở trang vẫn chỉ tốn ngần ấy lời gọi Jira.
_TTL_STATUS_GIAY = 3.0

#: `(mốc lấy được, dữ liệu)` của lần dựng status page gần nhất.
_dem_status: tuple[float, StatusPage] | None = None


def _status_page_co_dem() -> StatusPage:
    """`_load_status_page()` nhưng dùng lại kết quả cũ trong `_TTL_STATUS_GIAY` giây.

    Không khoá: hai request vào cùng lúc lúc đệm vừa hết thì cùng lắm gọi Jira
    hai lần. Thêm khoá vào một đường chạy chỉ đọc là đổi lấy rủi ro deadlock cho
    một khoản tiết kiệm không đáng.
    """
    global _dem_status
    bay_gio = time.monotonic()
    if _dem_status is not None and bay_gio - _dem_status[0] < _TTL_STATUS_GIAY:
        return _dem_status[1]
    trang = _load_status_page()
    _dem_status = (bay_gio, trang)
    return trang


@router.get("/status", response_model=StatusPage)
async def status_page() -> StatusPage:
    """Dữ liệu status page công khai — không cần đăng nhập."""
    try:
        return _status_page_co_dem()
    except JiraApiError as exc:
        logger.error("Jira lỗi khi dựng status page: %s", exc)
        raise _jira_error_response(exc) from exc
