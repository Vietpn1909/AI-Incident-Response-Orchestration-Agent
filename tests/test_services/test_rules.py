"""Test rule engine — nơi quyết định "có phải sự cố không" và "nặng mức nào".

Rule engine chạy TRƯỚC LLM và phải tất định: cùng đầu vào luôn ra cùng kết
quả, nếu không thì con số độ chính xác trong `eval/` vô nghĩa. Vì vậy test ở
đây toàn là bảng đầu vào–đầu ra, không mock gì cả.

Hai nhóm test đáng chú ý nhất:

- `test_moi_muc_severity_deu_dat_toi_duoc` — chặn đúng loại lỗi đã gặp hai lần
  trong dự án này: ngưỡng đặt sai làm cả một mức severity vĩnh viễn không kích
  hoạt được, mà không có gì báo.
- Nhóm NaN — NaN không làm chương trình chết, nó làm rule engine trả lời sai
  im lặng.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.models.incident import IncidentSignal, Severity
from src.services.rules import (
    SUSTAINED_SECONDS,
    classify_auth_burst,
    classify_severity,
    detect,
    is_spreading,
)

NOW = datetime(2026, 8, 1, 14, 32, 4, tzinfo=UTC)


def _normal(**overrides) -> dict:
    """Bộ tham số của một service hoàn toàn khoẻ, để test ghi đè từng phần."""
    return {
        "p95_now": 0.18,
        "p95_baseline": 0.18,
        "error_rate": 0.0,
        "pool_saturation": 0.2,
        "service": "service-thanh-toan",
        "breached_for_seconds": 60.0,
    } | overrides


def _signal(service: str, at: datetime) -> IncidentSignal:
    return IncidentSignal(
        affected_service=service,
        severity=Severity.P2,
        detected_at=at,
        metric_name="http_request_duration_seconds p95",
        metric_value=5.1,
        threshold=2.0,
    )


# --------------------------------------------------------------- classify_severity


@pytest.mark.parametrize(
    ("p95", "error_rate", "services", "mong_doi"),
    [
        (11.0, 0.0, 1, Severity.P1),  # p95 > 10s
        (0.2, 0.60, 1, Severity.P1),  # lỗi > 50%
        (0.2, 0.0, 2, Severity.P1),  # >= 2 service bị ảnh hưởng
        (5.1, 0.0, 1, Severity.P2),
        (0.2, 0.12, 1, Severity.P2),
        (1.5, 0.0, 1, Severity.P3),
        (0.2, 0.02, 1, Severity.P3),
        (0.2, 0.0, 1, Severity.P4),  # không ngưỡng cứng nào bị vượt
    ],
)
def test_bang_severity_cua_contract_1(p95, error_rate, services, mong_doi):
    assert classify_severity(p95, error_rate, services) == mong_doi


def test_moi_muc_severity_deu_dat_toi_duoc():
    """Không mức nào được là code chết.

    Đây là lỗi đã xảy ra hai lần: bucket mặc định làm P1/P2 không đạt tới được,
    và câu baseline trả NaN làm P4 không đạt tới được. Cả hai lần đều không có
    exception nào, chỉ là severity luôn ra sai.
    """
    dat_duoc = {
        classify_severity(11.0, 0.0),
        classify_severity(5.1, 0.0),
        classify_severity(1.5, 0.0),
        classify_severity(0.2, 0.0),
    }
    assert dat_duoc == {Severity.P1, Severity.P2, Severity.P3, Severity.P4}


def test_bien_ngat_la_lon_hon_khong_phai_lon_hon_bang():
    """Contract ① ghi `p95 > 2s`, đúng 2.0 chưa phải P2."""
    assert classify_severity(2.0, 0.0) == Severity.P3
    assert classify_severity(2.01, 0.0) == Severity.P2


def test_lan_truyen_nang_hon_du_so_lieu_nhe():
    """≥2 service là P1 kể cả khi p95 và tỷ lệ lỗi đều đẹp — theo contract ①."""
    assert classify_severity(0.19, 0.0, affected_service_count=2) == Severity.P1


# --------------------------------------------------------------------- detect


def test_chua_du_lau_thi_khong_phai_incident():
    """Một spike đơn lẻ lúc load test không được mở war room."""
    assert detect(**_normal(p95_now=9.0, breached_for_seconds=SUSTAINED_SECONDS - 1)) is None


def test_dung_ngay_moc_xac_nhan_thi_tinh():
    assert detect(**_normal(p95_now=9.0, breached_for_seconds=SUSTAINED_SECONDS)) is not None


def test_service_khoe_thi_khong_phai_incident():
    assert detect(**_normal()) is None


def test_truong_hop_mau_trong_docstring():
    """p95=5.1, baseline=0.2, lỗi=12%, pool cạn, kéo dài 45s → P2, đủ bằng chứng."""
    signal = detect(
        **_normal(p95_now=5.1, p95_baseline=0.2, error_rate=0.12, pool_saturation=1.0, breached_for_seconds=45)
    )

    assert signal is not None
    assert signal.severity == Severity.P2
    assert len(signal.evidence) >= 2
    assert signal.affected_service == "service-thanh-toan"
    assert signal.breached_for_seconds == 45


def test_bang_chung_luon_kem_promql_de_kiem_chung_lai():
    """Ràng buộc đề bài: chẩn đoán phải truy vết được về số liệu cụ thể."""
    signal = detect(**_normal(p95_now=5.1, p95_baseline=0.2, pool_saturation=1.0))

    assert all(evidence.promql for evidence in signal.evidence)


def test_luon_co_bang_chung_pool_du_pool_khong_phai_thu_kich_hoat():
    """Pool chứng minh nguyên nhân GỐC; p95 chỉ chứng minh triệu chứng."""
    signal = detect(**_normal(p95_now=5.1, pool_saturation=0.3))

    ten = [evidence.name for evidence in signal.evidence]
    assert "db_pool_connections_in_use / db_pool_size" in ten


def test_lech_baseline_nhung_chua_vuot_nguong_cung_thi_ra_p4():
    """Đường duy nhất tới P4. Thiếu nó thì P4 là mức chết trong bảng."""
    signal = detect(**_normal(p95_now=0.5, p95_baseline=0.18))

    assert signal is not None
    assert signal.severity == Severity.P4


def test_khong_co_baseline_thi_chi_xet_nguong_cung():
    """Prometheus mới dựng chưa có baseline — không được vì thế mà báo bừa."""
    assert detect(**_normal(p95_now=0.5, p95_baseline=0.0)) is None
    assert detect(**_normal(p95_now=5.1, p95_baseline=0.0)) is not None


def test_nguong_hien_thi_khop_voi_muc_severity_duoc_gan():
    """Tiêu đề Jira báo ngưỡng của chính mức đó, không phải ngưỡng thấp nhất."""
    signal = detect(**_normal(p95_now=5.1, p95_baseline=0.2))

    assert signal.severity == Severity.P2
    assert signal.threshold == 2.0
    assert "(ngưỡng 2.00)" in signal.title


def test_ty_le_loi_lam_metric_chinh_khi_no_la_thu_kich_hoat():
    signal = detect(**_normal(error_rate=0.12))

    assert signal.metric_name == "tỷ lệ lỗi 5xx"
    assert signal.metric_value == 0.12


# ------------------------------------------------------------- classify_auth_burst


@pytest.mark.parametrize(
    ("moi_giay", "mong_doi"),
    [
        (200.0, Severity.P1),
        (50.0, Severity.P1),
        (10.0, Severity.P2),
        (49.9, Severity.P2),
        (1.0, Severity.P3),
        (0.5, None),
        (0.0, None),
    ],
)
def test_bang_severity_cua_uc3(moi_giay, mong_doi):
    assert classify_auth_burst(moi_giay, breached_for_seconds=60.0) == mong_doi


def test_auth_burst_cung_can_du_lau():
    assert classify_auth_burst(200.0, breached_for_seconds=SUSTAINED_SECONDS - 1) is None


def test_uc3_khong_dung_chung_bang_voi_uc1():
    """UC-3 xảy ra khi hệ thống hoàn toàn khoẻ — latency đẹp, không lỗi 5xx.

    Nếu hai nhánh dùng chung ngưỡng thì burst 200 lần/giây sẽ bị `detect()` xếp
    P4 hoặc bỏ qua, và Agent kết luận "service quá tải" thay vì "vấn đề bảo
    mật" — theo use-cases.md UC-3 thì đó là chẩn đoán SAI.
    """
    assert detect(**_normal()) is None
    assert classify_auth_burst(200.0, breached_for_seconds=60.0) == Severity.P1


# ---------------------------------------------------------------- is_spreading


def test_hai_service_gan_nhau_la_lan_truyen():
    signals = [
        _signal("service-thanh-toan", NOW),
        _signal("service-dat-hang", NOW + timedelta(seconds=30)),
    ]
    assert is_spreading(signals) is True


def test_hai_service_cach_xa_nhau_khong_phai_lan_truyen():
    signals = [
        _signal("service-thanh-toan", NOW),
        _signal("service-dat-hang", NOW + timedelta(seconds=120)),
    ]
    assert is_spreading(signals) is False


def test_cung_mot_service_hai_lan_khong_phai_lan_truyen():
    """Nối chúng lại chỉ tạo liên kết rác trong war room."""
    signals = [
        _signal("service-thanh-toan", NOW),
        _signal("service-thanh-toan", NOW + timedelta(seconds=10)),
    ]
    assert is_spreading(signals) is False


def test_thu_tu_dau_vao_khong_anh_huong_ket_qua():
    som = _signal("service-thanh-toan", NOW)
    muon = _signal("service-dat-hang", NOW + timedelta(seconds=30))

    assert is_spreading([som, muon]) == is_spreading([muon, som]) is True


@pytest.mark.parametrize("signals", [[], [_signal("service-thanh-toan", NOW)]])
def test_it_hon_hai_tin_hieu_thi_khong_lan_truyen(signals):
    assert is_spreading(signals) is False


# ------------------------------------------------------------------------ NaN


def test_classify_severity_tu_choi_nan():
    """NaN tụt xuống P4 nếu không chặn — sự cố P1 bị xếp thành nhẹ nhất."""
    with pytest.raises(ValueError, match="NaN"):
        classify_severity(float("nan"), 0.0)


def test_detect_tu_choi_nan():
    with pytest.raises(ValueError, match="NaN"):
        detect(**_normal(p95_now=float("nan")))


def test_classify_auth_burst_tu_choi_nan():
    with pytest.raises(ValueError, match="NaN"):
        classify_auth_burst(float("nan"), breached_for_seconds=60.0)
