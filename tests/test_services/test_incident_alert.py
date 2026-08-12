"""Test `src/services/incident_alert.py`.

Chạy KHÔNG cần SMTP — mailer là `FakeEmailClient` hoặc mock.

Phần lớn file này kiểm **nội dung mail**, không phải luồng gửi. Luồng gửi đã có
`test_email_client.py` phủ. Thứ dễ hỏng ở đây là mail đi ra mà thiếu đúng cái
làm nó có ích: link để bấm vào.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from src.models.incident import IncidentSignal, MetricEvidence, Severity
from src.services.email_client import EmailResult, FakeEmailClient
from src.services.incident_alert import (
    IncidentAlerter,
    build_alert_email,
    build_alerter,
    danh_sach_nguoi_nhan,
)

URL_PHONG = "https://ai20k.daily.co/warroom-inc-1-a7f3"


def _signal(severity: Severity = Severity.P1) -> IncidentSignal:
    return IncidentSignal(
        affected_service="service-thanh-toan",
        severity=severity,
        detected_at=datetime(2026, 8, 12, 4, 48, tzinfo=UTC),
        metric_name="http_request_duration_seconds p95",
        metric_value=12.345,
        threshold=10.0,
        breached_for_seconds=45.0,
        evidence=[MetricEvidence(name="p95", value=12.345, unit="s", promql="...")],
    )


# ────────── nội dung mail ──────────


class TestBuildAlertEmail:
    def test_tieu_de_co_muc_service_va_jira_key(self):
        subject, _ = build_alert_email(_signal(Severity.P1), "INC-1")
        assert "P1" in subject
        assert "service-thanh-toan" in subject
        assert "INC-1" in subject

    def test_co_link_thi_co_nut_vao_hop(self):
        _, html = build_alert_email(_signal(), "INC-1", URL_PHONG)
        assert f'href="{URL_PHONG}"' in html
        assert "Vào phòng họp" in html

    def test_khong_co_link_thi_bao_ro_la_chua_mo_duoc(self):
        """Mail vẫn phải gửi khi Daily hỏng — nhưng đừng để người trực đi tìm
        một cái nút không tồn tại."""
        _, html = build_alert_email(_signal(), "INC-1")
        assert "Chưa mở được phòng họp" in html
        assert "href=" not in html

    def test_co_du_so_lieu_de_biet_nang_co_nao(self):
        _, html = build_alert_email(_signal(), "INC-1", URL_PHONG)
        assert "INC-1" in html
        assert "http_request_duration_seconds p95" in html
        assert "12.345" in html
        assert "10.000" in html  # ngưỡng
        assert "45s" in html

    def test_noi_ro_agent_khong_tu_thuc_thi(self):
        """Ràng buộc HITL của đề bài — người nhận mail phải biết điều đó."""
        _, html = build_alert_email(_signal(), "INC-1", URL_PHONG)
        assert "KHÔNG tự thực thi" in html

    def test_moi_muc_mot_mau(self):
        _, p1 = build_alert_email(_signal(Severity.P1), "INC-1")
        _, p2 = build_alert_email(_signal(Severity.P2), "INC-2")
        assert "#dc2626" in p1
        assert "#ea580c" in p2


# ────────── IncidentAlerter ──────────


class TestIncidentAlerter:
    def test_gui_thanh_cong_tra_true(self):
        mailer = FakeEmailClient()
        alerter = IncidentAlerter(mailer=mailer, recipients=["oncall@ai20k.vn"])

        assert alerter.bao_su_co("INC-1", _signal(), URL_PHONG) is True
        assert len(mailer.sent) == 1
        assert mailer.sent[0].recipients == ["oncall@ai20k.vn"]

    def test_khong_co_nguoi_nhan_thi_tra_false_va_khong_gui(self, caplog):
        mailer = MagicMock()
        alerter = IncidentAlerter(mailer=mailer, recipients=[])

        with caplog.at_level("WARNING"):
            assert alerter.bao_su_co("INC-1", _signal()) is False

        mailer.send.assert_not_called()
        assert "INCIDENT_ALERT_RECIPIENTS" in caplog.text

    def test_smtp_that_bai_thi_tra_false_khong_raise(self):
        """Trả `False` để người gọi KHÔNG đánh dấu đã báo, vòng sau thử lại."""
        mailer = MagicMock()
        mailer.send.return_value = EmailResult(
            success=False, recipients=["a@x.vn"], subject="", error="SMTP từ chối"
        )
        alerter = IncidentAlerter(mailer=mailer, recipients=["a@x.vn"])

        assert alerter.bao_su_co("INC-1", _signal(), URL_PHONG) is False

    def test_mailer_nem_exception_thi_nuot_loi(self):
        """`mailer` là tham số — không được tin bên kia nuốt lỗi giùm mình."""
        mailer = MagicMock()
        mailer.send.side_effect = RuntimeError("SMTP sập")
        alerter = IncidentAlerter(mailer=mailer, recipients=["a@x.vn"])

        assert alerter.bao_su_co("INC-1", _signal(), URL_PHONG) is False


# ────────── đọc cấu hình ──────────


class TestCauHinh:
    def test_chua_cau_hinh_gi_thi_khong_co_nguoi_nhan(self):
        """conftest xoá sạch biến môi trường nên đây là trạng thái mặc định."""
        assert danh_sach_nguoi_nhan() == []

    def test_doc_danh_sach_phan_cach_bang_phay(self, monkeypatch):
        from src.config import get_settings

        monkeypatch.setenv("INCIDENT_ALERT_RECIPIENTS", "a@x.vn, b@x.vn ,c@x.vn")
        get_settings.cache_clear()

        assert danh_sach_nguoi_nhan() == ["a@x.vn", "b@x.vn", "c@x.vn"]

    def test_roi_ve_postmortem_recipients_khi_chua_dat_rieng(self, monkeypatch):
        """Thà gửi cho nhóm rộng hơn còn hơn im lặng — im lặng trông y hệt
        'không có sự cố nào'."""
        from src.config import get_settings

        monkeypatch.setenv("INCIDENT_ALERT_RECIPIENTS", "")
        monkeypatch.setenv("POSTMORTEM_RECIPIENTS", "leader@x.vn")
        get_settings.cache_clear()

        assert danh_sach_nguoi_nhan() == ["leader@x.vn"]

    def test_thieu_smtp_thi_build_alerter_tra_none(self, caplog):
        """Thiếu SMTP không được làm chết Agent — chỉ là không ai được báo."""
        with caplog.at_level("WARNING"):
            assert build_alerter() is None
        assert "SMTP_EMAIL" in caplog.text

    def test_co_smtp_nhung_khong_co_nguoi_nhan_thi_tra_none(self, monkeypatch, caplog):
        from src.config import get_settings

        monkeypatch.setenv("SMTP_EMAIL", "agent@gmail.com")
        monkeypatch.setenv("SMTP_APP_PASSWORD", "xxxx-xxxx-xxxx-xxxx")
        get_settings.cache_clear()

        with caplog.at_level("WARNING"):
            assert build_alerter() is None
        assert "không có ai để báo" in caplog.text
