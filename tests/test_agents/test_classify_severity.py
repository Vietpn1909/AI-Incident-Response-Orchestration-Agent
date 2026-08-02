"""Test nâng severity khi sự cố lan sang nhiều service.

Việc riêng của module này là thứ `rules.detect()` không thể biết: vế "≥ 2
service bị ảnh hưởng → P1" của contract ①. Xét từng tín hiệu riêng lẻ thì không
bao giờ thấy được.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.agents.nodes.classify_severity import escalate_spreading
from src.models.incident import IncidentSignal, MetricEvidence, Severity

NOW = datetime(2026, 8, 2, 14, 32, 4, tzinfo=UTC)


def _signal(
    service: str,
    *,
    at: datetime = NOW,
    p95: float = 3.0,
    error_rate: float = 0.0,
    severity: Severity = Severity.P2,
) -> IncidentSignal:
    return IncidentSignal(
        affected_service=service,
        severity=severity,
        detected_at=at,
        metric_name="http_request_duration_seconds p95",
        metric_value=p95,
        threshold=2.0,
        breached_for_seconds=60.0,
        evidence=[
            MetricEvidence(name="http_request_duration_seconds p95", value=p95, unit="s", promql="..."),
            MetricEvidence(name="tỷ lệ lỗi 5xx", value=error_rate, promql="..."),
        ],
    )


def test_khong_co_tin_hieu_thi_tra_ve_rong():
    assert escalate_spreading([]) == []


def test_mot_service_thi_giu_nguyen():
    signals = [_signal("service-thanh-toan")]

    assert escalate_spreading(signals)[0].severity == Severity.P2


def test_hai_service_cung_luc_thi_nang_len_p1():
    """Từng tín hiệu riêng lẻ đều là P2; chỉ khi nhìn cùng nhau mới thấy đang lan."""
    signals = [
        _signal("service-thanh-toan", at=NOW),
        _signal("service-dat-hang", at=NOW + timedelta(seconds=30)),
    ]

    ket_qua = escalate_spreading(signals)

    assert [signal.severity for signal in ket_qua] == [Severity.P1, Severity.P1]


def test_nang_ca_hai_chu_khong_chi_cai_nang_nhat():
    """`link_incidents` sẽ nối chúng lại — hai issue cùng vụ phải cùng mức."""
    signals = [
        _signal("service-thanh-toan", p95=3.0, severity=Severity.P2),
        _signal("service-dat-hang", at=NOW + timedelta(seconds=20), p95=1.2, severity=Severity.P3),
    ]

    assert all(signal.severity == Severity.P1 for signal in escalate_spreading(signals))


def test_hai_su_co_roi_rac_trong_ngay_khong_phai_lan_truyen():
    signals = [
        _signal("service-thanh-toan", at=NOW),
        _signal("service-dat-hang", at=NOW + timedelta(minutes=30)),
    ]

    assert [signal.severity for signal in escalate_spreading(signals)] == [Severity.P2, Severity.P2]


def test_cung_mot_service_hai_lan_khong_phai_lan_truyen():
    """Nối chúng lại chỉ tạo liên kết rác trong war room."""
    signals = [
        _signal("service-thanh-toan", at=NOW),
        _signal("service-thanh-toan", at=NOW + timedelta(seconds=10)),
    ]

    assert all(signal.severity == Severity.P2 for signal in escalate_spreading(signals))


def test_giu_nguyen_so_luong_va_thu_tu():
    """`run_cycle` mở một war room cho mỗi tín hiệu — mất một cái là mất một issue."""
    signals = [
        _signal("service-thanh-toan", at=NOW),
        _signal("service-dat-hang", at=NOW + timedelta(seconds=30)),
    ]

    ket_qua = escalate_spreading(signals)

    assert [signal.affected_service for signal in ket_qua] == [
        "service-thanh-toan",
        "service-dat-hang",
    ]


def test_khong_sua_tin_hieu_goc_tai_cho():
    """Tín hiệu là dữ liệu dùng chung — sửa ngầm thì chỗ gọi khác thấy giá trị lạ."""
    goc = _signal("service-thanh-toan", at=NOW)
    khac = _signal("service-dat-hang", at=NOW + timedelta(seconds=20))

    escalate_spreading([goc, khac])

    assert goc.severity == Severity.P2


def test_da_la_p1_thi_khong_doi_gi():
    signals = [
        _signal("service-thanh-toan", p95=12.0, severity=Severity.P1),
        _signal("service-dat-hang", at=NOW + timedelta(seconds=20), p95=12.0, severity=Severity.P1),
    ]

    assert all(signal.severity == Severity.P1 for signal in escalate_spreading(signals))
