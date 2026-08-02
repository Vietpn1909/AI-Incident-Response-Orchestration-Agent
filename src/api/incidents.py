"""Contract ④ — Endpoint incident & status page.

Đường ghép: Đức (implement) → Long (tiêu thụ).

Hiện các endpoint trả dữ liệu từ fixture JSON trong `src/api/fixtures/`. Nhờ
vậy Long build xong toàn bộ UI trước khi Agent và Jira tồn tại. Tuần 3 Đức đổi
`_load_*` sang đọc từ `JiraClient` — **hình dạng response không đổi**, nên UI
của Long không phải sửa gì.

Long chỉ cần quan tâm: gọi endpoint nào, nhận về JSON hình gì.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.models.incident import Incident, StatusPage

router = APIRouter(tags=["incidents"])

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@lru_cache
def _load_incidents() -> tuple[Incident, ...]:
    """Đọc incident từ fixture.

    Tuần 3 thay thân hàm bằng `jira_client.list_incidents()`.
    """
    raw = json.loads((FIXTURES_DIR / "incidents.json").read_text(encoding="utf-8"))
    return tuple(Incident.model_validate(item) for item in raw)


@lru_cache
def _load_status_page() -> StatusPage:
    """Đọc dữ liệu status page từ fixture.

    Tuần 3 thay thân hàm bằng dữ liệu suy ra từ incident đang mở trên Jira.
    """
    raw = json.loads((FIXTURES_DIR / "status.json").read_text(encoding="utf-8"))
    return StatusPage.model_validate(raw)


@router.get("/incidents", response_model=list[Incident])
async def list_incidents(only_open: bool = False) -> list[Incident]:
    """Danh sách incident cho war-room view (nội bộ, vai trò on-call/IC).

    Args:
        only_open: True để chỉ lấy incident chưa Resolved.
    """
    incidents = list(_load_incidents())
    if only_open:
        incidents = [incident for incident in incidents if incident.is_open]
    return sorted(incidents, key=lambda incident: incident.detected_at, reverse=True)


@router.get("/incidents/{jira_key}", response_model=Incident)
async def get_incident(jira_key: str) -> Incident:
    """Chi tiết một incident: giả thuyết, bằng chứng, timeline, postmortem."""
    for incident in _load_incidents():
        if incident.jira_key == jira_key:
            return incident
    raise HTTPException(status_code=404, detail=f"Không tìm thấy incident {jira_key}")


@router.get("/status", response_model=StatusPage)
async def status_page() -> StatusPage:
    """Dữ liệu status page công khai — không cần đăng nhập."""
    return _load_status_page()
