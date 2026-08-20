"""Test node `verify` — đo lại sau khắc phục.

Test quan trọng nhất là `test_khong_do_duoc_thi_khong_ket_luan`: nó chốt rằng
"không đo được" khác "đã hồi phục". Nhầm hai cái đó là ghi "đã hồi phục" lên war
room khi thật ra Prometheus đang chết, và người trực đọc thấy vậy là đi ngủ.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from src.agents.nodes.verify import verify
from src.models.incident import IncidentSignal, MetricEvidence, Severity
from src.services.prometheus import PrometheusClient, PrometheusError

SERVICE = "service-thanh-toan"


def _client() -> PrometheusClient:
    """Client trỏ vào cổng chết — mọi test đều giả `detect_incidents` nên không gọi mạng."""
    return PrometheusClient("http://127.0.0.1:1")


def _signal(muc: Severity, gia_tri: float = 4.4) -> IncidentSignal:
    return IncidentSignal(
        affected_service=SERVICE,
        severity=muc,
        detected_at=datetime.now(UTC),
        metric_name="http_request_duration_seconds p95",
        metric_value=gia_tri,
        threshold=2.0,
        breached_for_seconds=60.0,
        evidence=[MetricEvidence(name="p95", value=gia_tri)],
    )


def test_khong_con_tin_hieu_thi_bao_da_hoi_phuc():
    with patch("src.agents.nodes.verify.detect_incidents", return_value=[]):
        kq = verify(_client(), SERVICE)

    assert kq is not None
    assert kq.hoi_phuc is True
    assert kq.te_hon is False
    assert "ĐÃ HỒI PHỤC" in kq.ket_luan


def test_service_khac_con_su_co_thi_service_nay_van_hoi_phuc():
    """Chỉ xét đúng service đang kiểm, không xét cả hệ thống.

    Sự cố lan truyền thì service nạn nhân có thể hồi phục trước service gốc, hoặc
    ngược lại. Trộn chung là báo sai cho cả hai.
    """
    khac = _signal(Severity.P1).model_copy(update={"affected_service": "service-dat-hang"})
    with patch("src.agents.nodes.verify.detect_incidents", return_value=[khac]):
        kq = verify(_client(), SERVICE)

    assert kq is not None
    assert kq.hoi_phuc is True


def test_con_tin_hieu_thi_bao_chua_do_va_nhac_chan_doan_lai():
    """Đúng bước 4 trong runbook Agent tự viết: đừng rollback tiếp, chẩn đoán lại.

    Đây cũng là chỗ duy nhất kiểm được câu Agent tự nhận trong phần rủi ro —
    "nếu rollback không làm sự cố hết thì kết luận ban đầu đã sai".
    """
    with patch("src.agents.nodes.verify.detect_incidents", return_value=[_signal(Severity.P2)]):
        kq = verify(_client(), SERVICE, muc_luc_phat_hien=Severity.P2)

    assert kq is not None
    assert kq.hoi_phuc is False
    assert kq.te_hon is False
    assert "CHƯA ĐỠ" in kq.ket_luan
    assert "chẩn đoán lại" in kq.ket_luan
    assert kq.con_lai is not None


def test_nang_muc_sau_khac_phuc_thi_bao_te_hon():
    """Hành động khắc phục có thể làm tình hình xấu đi — phải nói ra, không im."""
    with patch("src.agents.nodes.verify.detect_incidents", return_value=[_signal(Severity.P1)]):
        kq = verify(_client(), SERVICE, muc_luc_phat_hien=Severity.P3)

    assert kq is not None
    assert kq.te_hon is True
    assert "TỆ HƠN" in kq.ket_luan
    assert "Đừng thi hành thêm" in kq.ket_luan


def test_do_ma_muc_nhe_hon_thi_khong_goi_la_te_hon():
    with patch("src.agents.nodes.verify.detect_incidents", return_value=[_signal(Severity.P3)]):
        kq = verify(_client(), SERVICE, muc_luc_phat_hien=Severity.P1)

    assert kq is not None
    assert kq.hoi_phuc is False
    assert kq.te_hon is False


def test_khong_do_duoc_thi_khong_ket_luan():
    """Prometheus lỗi → trả `None`, KHÔNG được coi như đã hồi phục.

    "Không đo được" và "đã hồi phục" là hai chuyện khác nhau. Nhầm là ghi "đã hồi
    phục" lên war room khi thật ra Agent đang mù — và người trực đọc thấy vậy thì
    đi ngủ trong lúc sự cố vẫn diễn ra.
    """
    with patch(
        "src.agents.nodes.verify.detect_incidents",
        side_effect=PrometheusError("connection refused"),
    ):
        assert verify(_client(), SERVICE) is None


def test_dung_lai_dung_duong_phat_hien():
    """`verify` phải gọi `detect_incidents`, không viết truy vấn riêng.

    Một truy vấn riêng sẽ là bản sao lặng lẽ lệch đi khi ai sửa ngưỡng ở
    `rules.py` — cùng loại lỗi với `_NODE_CHAIN` cắm cứng lệch khỏi graph.
    """
    with patch("src.agents.nodes.verify.detect_incidents", return_value=[]) as goi:
        verify(_client(), SERVICE)

    goi.assert_called_once()


@pytest.mark.parametrize(
    "truoc,sau,te_hon",
    [
        (Severity.P4, Severity.P1, True),
        (Severity.P3, Severity.P2, True),
        (Severity.P2, Severity.P2, False),
        (Severity.P1, Severity.P1, False),
        (Severity.P1, Severity.P4, False),
    ],
)
def test_bang_so_muc_do(truoc: Severity, sau: Severity, te_hon: bool):
    with patch("src.agents.nodes.verify.detect_incidents", return_value=[_signal(sau)]):
        kq = verify(_client(), SERVICE, muc_luc_phat_hien=truoc)

    assert kq is not None
    assert kq.te_hon is te_hon
