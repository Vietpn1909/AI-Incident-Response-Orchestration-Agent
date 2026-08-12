"""Test Agent tự mở phòng họp và gọi người vào bằng mail khi có sự cố.

Không gọi Daily lẫn SMTP thật: room client và mailer đều là `unittest.mock`,
Jira là `FakeJiraClient`.

`detect_incidents` bị monkeypatch thay vì dựng Prometheus giả bằng
`httpx.MockTransport` như `test_detection.py`: thứ cần điều khiển ở đây là
**severity**, mà đi qua đường Prometheus thì severity là kết quả của cả bộ luật.
Muốn có đúng một tín hiệu P3 phải dò ra bộ số nào rơi vào P3 — test sẽ đỏ mỗi
lần ai chỉnh ngưỡng trong `rules.py`, vì một lý do chẳng liên quan gì tới phòng
họp.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.agents.incident_graph import MUC_CAN_HOP, _tao_phong_hop, build_incident_graph
from src.agents.war_room_registry import WarRoomRegistry
from src.models.incident import IncidentSignal, MetricEvidence, Severity
from src.services.email_client import EmailResult
from src.services.incident_alert import IncidentAlerter
from src.services.jira import FakeJiraClient
from src.services.meeting_room import MeetingRoom

PHONG = MeetingRoom(url="https://ai20k.daily.co/warroom-inc-1-a7f3", name="warroom-inc-1-a7f3")


def _signal(severity: Severity = Severity.P1, service: str = "service-thanh-toan") -> IncidentSignal:
    return IncidentSignal(
        affected_service=service,
        severity=severity,
        detected_at=datetime.now(UTC),
        metric_name="http_request_duration_seconds p95",
        metric_value=12.3,
        threshold=10.0,
        breached_for_seconds=45.0,
        evidence=[MetricEvidence(name="p95", value=12.3, unit="s", promql="...")],
    )


def _room(ket_qua: MeetingRoom | None = PHONG) -> MagicMock:
    """Room client giả. `ket_qua=None` mô phỏng Daily hỏng — `create()` trả None."""
    room = MagicMock()
    room.create.return_value = ket_qua
    return room


def _alerter(thanh_cong: bool = True) -> IncidentAlerter:
    """Alerter thật, nhưng mailer là mock — để kiểm cả nội dung mail gửi đi."""
    mailer = MagicMock()
    mailer.send.return_value = EmailResult(
        success=thanh_cong,
        recipients=["oncall@ai20k.vn"],
        subject="",
        error="" if thanh_cong else "SMTP từ chối",
    )
    return IncidentAlerter(mailer=mailer, recipients=["oncall@ai20k.vn"])


@pytest.fixture
def tin_hieu_co_dinh(monkeypatch: pytest.MonkeyPatch):
    """Ép node `detect` trả về đúng danh sách tín hiệu mà test chỉ định.

    Gọi lại được nhiều lần để mô phỏng tình hình đổi giữa các vòng quét — đó là
    cách dựng lại ca INC-1 ở `test_war_room_p3_duoc_nang_len_p1_thi_van_co_phong`.
    """

    def dat(*signals: IncidentSignal) -> None:
        monkeypatch.setattr(
            "src.agents.incident_graph.detect_incidents",
            lambda _client: list(signals),
        )

    return dat


# ────────────────────────────────────── mức nào thì mở phòng


def test_p1_thi_mo_phong_va_ghi_url_vao_state(tin_hieu_co_dinh):
    tin_hieu_co_dinh(_signal(Severity.P1))
    jira = FakeJiraClient(verbose=False)
    room = _room()

    state = build_incident_graph(None, jira, room=room).invoke({})

    room.create.assert_called_once()
    (jira_key,) = state["opened"]
    assert state["meeting_rooms"] == {jira_key: PHONG.url}


def test_p2_cung_mo_phong(tin_hieu_co_dinh):
    tin_hieu_co_dinh(_signal(Severity.P2))
    room = _room()

    state = build_incident_graph(None, FakeJiraClient(verbose=False), room=room).invoke({})

    room.create.assert_called_once()
    assert state["meeting_rooms"]


def test_p3_thi_khong_mo_phong(tin_hieu_co_dinh):
    """Gọi người vào họp khẩn cho một sự cố P3 là làm phiền, không phải ứng phó."""
    tin_hieu_co_dinh(_signal(Severity.P3))
    room = _room()

    state = build_incident_graph(None, FakeJiraClient(verbose=False), room=room).invoke({})

    room.create.assert_not_called()
    assert state["meeting_rooms"] == {}
    # Nhưng war room vẫn phải mở — P3 vẫn là sự cố.
    assert state["opened"]


def test_hang_so_muc_can_hop_dung_p1_p2():
    """Đây là công tắc một dòng khi demo không đẩy tải lên nổi P2."""
    assert MUC_CAN_HOP == {Severity.P1, Severity.P2}


# ────────────────────────────────────── một sự cố, một phòng


def test_nhieu_service_cung_su_co_thi_dung_chung_mot_phong(tin_hieu_co_dinh):
    """Sự cố lan truyền có nhiều war room nhưng chỉ MỘT lỗi gốc.

    Mở cho mỗi issue một phòng riêng thì người trực bị chia thành hai nhóm nói
    chuyện tách nhau — tệ hơn cả việc không có phòng nào.
    """
    tin_hieu_co_dinh(
        _signal(Severity.P1, "service-thanh-toan"),
        _signal(Severity.P1, "service-dat-hang"),
    )
    jira = FakeJiraClient(verbose=False)
    room = _room()

    state = build_incident_graph(None, jira, room=room).invoke({})

    # Hai war room, nhưng CHỈ MỘT lần gọi Daily.
    assert len(state["opened"]) == 2
    room.create.assert_called_once()
    assert len(state["meeting_rooms"]) == 2
    assert set(state["meeting_rooms"].values()) == {PHONG.url}


def test_vong_sau_khong_mo_them_phong_khi_co_registry(tin_hieu_co_dinh):
    """Agent poll 10 giây một vòng, bản free chỉ cho 5 phòng đồng thời.

    Không nhớ xuyên vòng thì chưa tới một phút đã hết hạn mức.
    """
    tin_hieu_co_dinh(_signal(Severity.P1))
    jira = FakeJiraClient(verbose=False)
    room = _room()
    registry = WarRoomRegistry()

    build_incident_graph(None, jira, room=room, registry=registry).invoke({})
    room.create.reset_mock()
    state = build_incident_graph(None, jira, room=room, registry=registry).invoke({})

    room.create.assert_not_called()
    # Đã có phòng từ vòng trước nên KHÔNG báo lại — tránh log lặp mỗi 10 giây.
    assert state["meeting_rooms"] == {}


def test_khong_co_registry_thi_moi_vong_mo_lai_phong(tin_hieu_co_dinh):
    """Tài liệu hoá vì sao `run_agent.py` BẮT BUỘC phải giữ một registry.

    Test này mô tả hành vi **không mong muốn** xảy ra khi quên truyền registry.
    Nó đỏ nghĩa là ai đó vừa lén thêm state toàn cục vào `build_incident_graph`
    — mà đó chính là thứ `detection_loop.py` cố ý tránh.
    """
    tin_hieu_co_dinh(_signal(Severity.P1))
    jira = FakeJiraClient(verbose=False)
    room = _room()

    build_incident_graph(None, jira, room=room).invoke({})
    build_incident_graph(None, jira, room=room).invoke({})

    assert room.create.call_count == 2


def test_war_room_p3_duoc_nang_len_p1_thi_van_co_phong(tin_hieu_co_dinh):
    """Hồi quy cho lỗi đo thật trên demo stack ngày 12/08.

    Vòng 1: chỉ `service-dat-hang` vượt ngưỡng → một service thì không lan
    truyền → P3 → không mở phòng.
    Vòng 2: `service-thanh-toan` vượt theo → đủ 2 service → luật nâng CẢ HAI lên
    P1.

    Trước bản vá, war room của vòng 1 không còn `created=True` nên nó trượt
    vĩnh viễn: trượt vì P3 ở vòng 1, trượt vì "không phải issue mới" ở vòng 2 —
    hai lý do khác nhau nên đọc từng điều kiện riêng lẻ không thấy.

    Hệ quả thật: với sự cố lan truyền — kịch bản nặng nhất — war room ĐẦU TIÊN
    là cái duy nhất không có link họp.
    """
    jira = FakeJiraClient(verbose=False)
    room = _room()
    registry = WarRoomRegistry()

    # Vòng 1 — một mình service-dat-hang, mức P3.
    tin_hieu_co_dinh(_signal(Severity.P3, "service-dat-hang"))
    vong1 = build_incident_graph(None, jira, room=room, registry=registry).invoke({})
    (key_dat_hang,) = vong1["opened"]
    room.create.assert_not_called()

    # Vòng 2 — lan sang service-thanh-toan, cả hai thành P1.
    tin_hieu_co_dinh(
        _signal(Severity.P1, "service-dat-hang"),
        _signal(Severity.P1, "service-thanh-toan"),
    )
    vong2 = build_incident_graph(None, jira, room=room, registry=registry).invoke({})

    # Một phòng cho cả cụm, và war room từ vòng 1 PHẢI nằm trong đó.
    room.create.assert_called_once()
    assert key_dat_hang in vong2["meeting_rooms"]
    assert len(vong2["meeting_rooms"]) == 2
    assert set(vong2["meeting_rooms"].values()) == {PHONG.url}


# ────────────────────────────────────── hỏng thì không được sập


def test_daily_hong_thi_war_room_van_mo_binh_thuong(tin_hieu_co_dinh):
    """`create()` trả `None` → mất link họp, KHÔNG mất war room."""
    tin_hieu_co_dinh(_signal(Severity.P1))
    jira = FakeJiraClient(verbose=False)

    state = build_incident_graph(None, jira, room=_room(None)).invoke({})

    assert state["meeting_rooms"] == {}
    assert state["opened"]
    assert len(jira.list_incidents()) == 1


def test_create_nem_exception_thi_khong_lam_sap_vong_quet(tin_hieu_co_dinh):
    """`room` là tham số — người gọi có thể truyền client không nuốt lỗi giùm."""
    tin_hieu_co_dinh(_signal(Severity.P1))
    jira = FakeJiraClient(verbose=False)
    room = MagicMock()
    room.create.side_effect = RuntimeError("Daily sập")

    state = build_incident_graph(None, jira, room=room).invoke({})

    assert state["meeting_rooms"] == {}
    assert state["opened"]


def test_khong_truyen_room_thi_graph_chay_y_nhu_cu(tin_hieu_co_dinh):
    """`room=None` là mặc định — mọi caller và test đã có phải chạy y nguyên."""
    tin_hieu_co_dinh(_signal(Severity.P1))
    jira = FakeJiraClient(verbose=False)

    state = build_incident_graph(None, jira).invoke({})

    assert state["meeting_rooms"] == {}
    assert state["opened"]
    assert len(jira.list_incidents()) == 1


# ────────────────────────────────────── mail gọi người vào


def test_p1_thi_gui_mail_kem_link_phong_hop(tin_hieu_co_dinh):
    tin_hieu_co_dinh(_signal(Severity.P1))
    alerter = _alerter()

    build_incident_graph(
        None, FakeJiraClient(verbose=False), room=_room(), alerter=alerter
    ).invoke({})

    alerter.mailer.send.assert_called_once()
    goi = alerter.mailer.send.call_args[1]
    assert goi["to"] == ["oncall@ai20k.vn"]
    # Thứ khiến mail này có ích: bấm vào là vào họp được.
    assert PHONG.url in goi["body_html"]


def test_p3_thi_khong_gui_mail(tin_hieu_co_dinh):
    """Đánh thức người trực lúc 2 giờ sáng cho một sự cố P3 là cách nhanh nhất
    để lần sau không ai đọc mail của Agent nữa."""
    tin_hieu_co_dinh(_signal(Severity.P3))
    alerter = _alerter()

    build_incident_graph(
        None, FakeJiraClient(verbose=False), room=_room(), alerter=alerter
    ).invoke({})

    alerter.mailer.send.assert_not_called()


def test_moi_war_room_chi_gui_dung_mot_mail(tin_hieu_co_dinh):
    """Không nhớ thì người trực nhận một mail mỗi 10 giây suốt cả sự cố."""
    tin_hieu_co_dinh(_signal(Severity.P1))
    jira = FakeJiraClient(verbose=False)
    alerter = _alerter()
    registry = WarRoomRegistry()

    for _ in range(4):
        build_incident_graph(
            None, jira, room=_room(), alerter=alerter, registry=registry
        ).invoke({})

    assert alerter.mailer.send.call_count == 1


def test_khong_co_phong_van_gui_mail_bao_su_co(tin_hieu_co_dinh):
    """Daily hỏng không phải lý do nuốt luôn cảnh báo.

    Người trực vẫn cần biết có sự cố; họ vào war room trên Jira để phối hợp.
    """
    tin_hieu_co_dinh(_signal(Severity.P1))
    alerter = _alerter()

    build_incident_graph(
        None, FakeJiraClient(verbose=False), room=None, alerter=alerter
    ).invoke({})

    alerter.mailer.send.assert_called_once()
    body = alerter.mailer.send.call_args[1]["body_html"]
    assert "Chưa mở được phòng họp" in body


def test_gui_mail_that_bai_thi_vong_sau_thu_lai(tin_hieu_co_dinh):
    """Mất một cảnh báo tệ hơn nhiều so với gửi lặp một lần.

    Nên chỉ đánh dấu "đã báo" SAU KHI gửi thành công.
    """
    tin_hieu_co_dinh(_signal(Severity.P1))
    jira = FakeJiraClient(verbose=False)
    alerter = _alerter(thanh_cong=False)
    registry = WarRoomRegistry()

    build_incident_graph(None, jira, alerter=alerter, registry=registry).invoke({})
    build_incident_graph(None, jira, alerter=alerter, registry=registry).invoke({})

    assert alerter.mailer.send.call_count == 2
    assert registry.da_bao_mail == set()


def test_mailer_nem_exception_thi_khong_lam_sap_vong_quet(tin_hieu_co_dinh):
    tin_hieu_co_dinh(_signal(Severity.P1))
    jira = FakeJiraClient(verbose=False)
    alerter = _alerter()
    alerter.mailer.send.side_effect = RuntimeError("SMTP sập")

    state = build_incident_graph(None, jira, alerter=alerter).invoke({})

    assert state["opened"]
    assert len(jira.list_incidents()) == 1


def test_khong_truyen_alerter_thi_khong_gui_gi(tin_hieu_co_dinh):
    tin_hieu_co_dinh(_signal(Severity.P1))
    jira = FakeJiraClient(verbose=False)

    state = build_incident_graph(None, jira, room=_room()).invoke({})

    assert state["opened"]


def test_ca_cum_deu_duoc_bao_mail(tin_hieu_co_dinh):
    """Mỗi war room một mail, nhưng tất cả trỏ về CÙNG một phòng."""
    tin_hieu_co_dinh(
        _signal(Severity.P1, "service-thanh-toan"),
        _signal(Severity.P1, "service-dat-hang"),
    )
    alerter = _alerter()

    build_incident_graph(
        None, FakeJiraClient(verbose=False), room=_room(), alerter=alerter
    ).invoke({})

    assert alerter.mailer.send.call_count == 2
    for goi in alerter.mailer.send.call_args_list:
        assert PHONG.url in goi[1]["body_html"]


# ────────────────────────────────────── _tao_phong_hop gọi thẳng
#
# Hàm là module-level chính vì mấy test này: không phải dựng cả graph mới tới
# được nó.


def test_tao_phong_hop_tra_url_va_log_info(caplog):
    """Có phòng mà mất log thì coi như không có — không ai biết đường nào vào."""
    with caplog.at_level("INFO"):
        url = _tao_phong_hop(_room(), "INC-1", _signal())

    assert url == PHONG.url
    assert PHONG.url in caplog.text
    assert "INC-1" in caplog.text


def test_tao_phong_hop_nuot_loi_va_tra_none(caplog):
    room = MagicMock()
    room.create.side_effect = RuntimeError("Daily sập")

    with caplog.at_level("WARNING"):
        assert _tao_phong_hop(room, "INC-1", _signal()) is None

    assert "INC-1" in caplog.text
