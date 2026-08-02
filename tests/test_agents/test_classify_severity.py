"""Test node `classify_severity`.

Việc riêng của node này là thứ `rules.detect()` không thể biết: vế "≥ 2 service
bị ảnh hưởng → P1" của contract ①. Xét từng tín hiệu riêng lẻ thì không bao giờ
thấy được điều đó.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.agents.nodes.classify_severity import classify_severity_node
from src.models.incident import IncidentSignal, MetricEvidence, Severity

NOW = datetime(2026, 8, 1, 14, 32, 4, tzinfo=UTC)


def _signal(service: str, *, p95: float, at: datetime, severity: Severity) -> IncidentSignal:
    return IncidentSignal(
        affected_service=service,
        severity=severity,
        detected_at=at,
        metric_name="http_request_duration_seconds p95",
        metric_value=p95,
        threshold=2.0,
        breached_for_seconds=45.0,
        evidence=[
            MetricEvidence(name="http_request_duration_seconds p95", value=p95, unit="s", promql="..."),
            MetricEvidence(name="tỷ lệ lỗi 5xx", value=0.0, promql="..."),
        ],
    )


def test_khong_co_tin_hieu_thi_khong_mo_war_room():
    assert classify_severity_node({"signals": []}) == {"signal": None, "spreading": False}


def test_state_chua_chay_detect_cung_khong_no():
    assert classify_severity_node({})["signal"] is None


def test_mot_service_thi_giu_nguyen_severity():
    signal = _signal("service-thanh-toan", p95=5.1, at=NOW, severity=Severity.P2)

    result = classify_severity_node({"signals": [signal]})

    assert result["spreading"] is False
    assert result["signal"].severity == Severity.P2


def test_hai_service_cung_luc_thi_nang_len_p1():
    """Vế thứ ba của contract ①: ≥ 2 service bị ảnh hưởng → P1.

    Từng tín hiệu riêng lẻ đều chỉ là P2. Chỉ khi nhìn cùng nhau mới thấy đây
    là sự cố đang lan.
    """
    signals = [
        _signal("service-thanh-toan", p95=3.0, at=NOW, severity=Severity.P2),
        _signal("service-dat-hang", p95=3.0, at=NOW + timedelta(seconds=30), severity=Severity.P2),
    ]

    result = classify_severity_node({"signals": signals})

    assert result["spreading"] is True
    assert [signal.severity for signal in result["signals"]] == [Severity.P1, Severity.P1]


def test_nang_ca_hai_chu_khong_chi_tin_hieu_chinh():
    """`link_incidents` sẽ nối chúng lại — hai incident cùng vụ phải cùng mức."""
    signals = [
        _signal("service-thanh-toan", p95=3.0, at=NOW, severity=Severity.P2),
        _signal("service-dat-hang", p95=1.2, at=NOW + timedelta(seconds=20), severity=Severity.P3),
    ]

    result = classify_severity_node({"signals": signals})

    assert all(signal.severity == Severity.P1 for signal in result["signals"])


def test_hai_service_cach_xa_nhau_khong_phai_lan_truyen():
    """Hai sự cố rời rạc trong ngày không được gộp thành một vụ lan truyền."""
    signals = [
        _signal("service-thanh-toan", p95=3.0, at=NOW, severity=Severity.P2),
        _signal("service-dat-hang", p95=3.0, at=NOW + timedelta(minutes=30), severity=Severity.P2),
    ]

    result = classify_severity_node({"signals": signals})

    assert result["spreading"] is False
    assert [signal.severity for signal in result["signals"]] == [Severity.P2, Severity.P2]


def test_chon_tin_hieu_nghiem_trong_nhat_lam_chinh():
    nhe = _signal("service-dat-hang", p95=1.2, at=NOW, severity=Severity.P3)
    nang = _signal("service-thanh-toan", p95=12.0, at=NOW + timedelta(minutes=30), severity=Severity.P1)

    result = classify_severity_node({"signals": [nhe, nang]})

    assert result["signal"].affected_service == "service-thanh-toan"


def test_cung_muc_thi_chon_cai_phat_hien_som_nhat():
    """Service hỏng trước nhiều khả năng là nguồn, service sau là nạn nhân."""
    som = _signal("service-thanh-toan", p95=3.0, at=NOW, severity=Severity.P2)
    muon = _signal("service-dat-hang", p95=3.0, at=NOW + timedelta(seconds=30), severity=Severity.P2)

    result = classify_severity_node({"signals": [muon, som]})

    assert result["signal"].affected_service == "service-thanh-toan"


def test_khong_sua_tin_hieu_goc_tai_cho():
    """Tín hiệu là dữ liệu dùng chung — sửa tại chỗ thì chỗ khác thấy giá trị lạ."""
    goc = _signal("service-thanh-toan", p95=3.0, at=NOW, severity=Severity.P2)
    khac = _signal("service-dat-hang", p95=3.0, at=NOW + timedelta(seconds=20), severity=Severity.P2)

    classify_severity_node({"signals": [goc, khac]})

    assert goc.severity == Severity.P2
