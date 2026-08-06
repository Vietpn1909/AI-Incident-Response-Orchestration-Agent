"""Test node `link_incidents` — nối các war room của một sự cố lan truyền.

`classify_severity` đã nâng cả hai incident lên P1, nhưng nâng mức chỉ nói
"nặng hơn", không nói "hai cái này là một vụ". Trước node này,
`related_incidents` trên Jira luôn rỗng — trong khi war-room view của Long đã
có sẵn chỗ hiển thị và cho bấm chuyển qua lại.

Test quan trọng nhất là `test_khong_noi_lai_cap_da_noi`: Agent poll vài giây
một lần trong khi sự cố kéo dài hàng chục phút, và `RealJiraClient.link_issues()`
POST thẳng lên Jira — không chặn thì issue đầy link trùng.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.agents.nodes.link_incidents import link_incidents
from src.models.incident import IncidentSignal, Severity
from src.services.jira import FakeJiraClient

NOW = datetime(2026, 8, 6, 14, 0, 0, tzinfo=UTC)


def _signal(service: str) -> IncidentSignal:
    return IncidentSignal(
        affected_service=service,
        severity=Severity.P1,
        detected_at=NOW,
        metric_name="http_request_duration_seconds p95",
        metric_value=3.0,
        threshold=2.0,
        breached_for_seconds=60.0,
    )


@pytest.fixture
def jira() -> FakeJiraClient:
    return FakeJiraClient(verbose=False)


def _mo_war_rooms(jira: FakeJiraClient, *services: str) -> dict[str, str]:
    return {service: jira.create_incident(_signal(service)) for service in services}


def test_mot_service_thi_khong_co_gi_de_noi(jira: FakeJiraClient):
    war_rooms = _mo_war_rooms(jira, "service-thanh-toan")

    ket_qua = link_incidents(jira, war_rooms)

    assert ket_qua.linked == []


def test_khong_co_war_room_nao_thi_khong_no(jira: FakeJiraClient):
    assert link_incidents(jira, {}).linked == []


def test_hai_service_thi_noi_lai(jira: FakeJiraClient):
    war_rooms = _mo_war_rooms(jira, "service-thanh-toan", "service-dat-hang")

    ket_qua = link_incidents(jira, war_rooms)

    assert len(ket_qua.linked) == 1
    thanh_toan = jira.get_incident(war_rooms["service-thanh-toan"])
    dat_hang = jira.get_incident(war_rooms["service-dat-hang"])
    assert dat_hang.jira_key in thanh_toan.related_incidents
    assert thanh_toan.jira_key in dat_hang.related_incidents


def test_khong_noi_lai_cap_da_noi(jira: FakeJiraClient):
    """Agent poll liên tục trong lúc sự cố kéo dài — không chặn thì đầy link trùng.

    Cùng loại rác mà `find_open_incident()` chặn ở `open_war_room`.
    """
    war_rooms = _mo_war_rooms(jira, "service-thanh-toan", "service-dat-hang")

    lan_dau = link_incidents(jira, war_rooms)
    lan_hai = link_incidents(jira, war_rooms)
    lan_ba = link_incidents(jira, war_rooms)

    assert len(lan_dau.linked) == 1
    assert lan_hai.linked == [] and lan_ba.linked == []
    assert len(lan_hai.skipped) == 1

    # Quan hệ vẫn còn nguyên, chỉ là không nối thêm lần nữa.
    thanh_toan = jira.get_incident(war_rooms["service-thanh-toan"])
    assert thanh_toan.related_incidents == [war_rooms["service-dat-hang"]]


def test_ba_service_thi_noi_tung_cap(jira: FakeJiraClient):
    war_rooms = _mo_war_rooms(jira, "svc-a", "svc-b", "svc-c")

    ket_qua = link_incidents(jira, war_rooms)

    assert len(ket_qua.linked) == 3  # C(3,2)
    for key in war_rooms.values():
        assert len(jira.get_incident(key).related_incidents) == 2


def test_su_co_lan_dan_van_noi_duoc(jira: FakeJiraClient):
    """A hỏng trước, B hỏng sau vài phút — đây là hình thái lan truyền thật.

    Nếu node chỉ nhìn war room MỚI mở thì mỗi vòng chỉ có đúng một cái, và hai
    issue không bao giờ gặp nhau để nối. Đó là lý do state có `all_war_rooms`
    riêng, không dùng `war_rooms`.
    """
    som = _mo_war_rooms(jira, "service-thanh-toan")
    assert link_incidents(jira, som).linked == []

    # Vài vòng sau, service thứ hai mới hỏng. `all_war_rooms` mang theo cả issue
    # cũ, nên vòng này nối được.
    muon = som | _mo_war_rooms(jira, "service-dat-hang")

    assert len(link_incidents(jira, muon).linked) == 1


def test_khong_doc_duoc_quan_he_cu_van_noi(jira: FakeJiraClient, monkeypatch):
    """Jira đáp 429 lúc đọc thì hệ quả xấu nhất là một link trùng.

    Ném lỗi ra ngoài thì mất cả vòng quét của những incident khác — đánh đổi
    rõ ràng về phía nào.
    """
    war_rooms = _mo_war_rooms(jira, "service-thanh-toan", "service-dat-hang")

    def _no(jira_key: str):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(jira, "get_incident", _no)

    assert len(link_incidents(jira, war_rooms).linked) == 1
