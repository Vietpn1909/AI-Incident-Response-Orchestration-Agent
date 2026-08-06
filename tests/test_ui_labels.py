"""Test bảng dịch thuật ngữ cho UI.

Hai test quan trọng nhất là hai cái **canh chuỗi**:
`test_moi_ten_metric_deu_dich_duoc` và `test_moi_hanh_dong_deu_dich_duoc`. Bảng
dịch so khớp theo chuỗi con của tên `MetricEvidence` mà `rules.py` sinh ra, nên
`rules.py` đổi một chữ là bảng lặng lẽ rơi về tên thô — không sai, nhưng mất hết
công dịch và **không có gì đỏ lên**. Cùng họ với
`test_runbooks.py::test_ten_bang_chung_con_khop_voi_rules`.
"""

from __future__ import annotations

from src.models.incident import IncidentState, Severity
from src.services import remediation, rules
from ui import labels


def test_moi_ten_metric_deu_dich_duoc():
    """Gọi thẳng `rules` rồi đối chiếu, không hardcode kỳ vọng ở hai nơi."""
    uc1 = rules.detect(
        p95_now=4.417, p95_baseline=0.58, error_rate=0.0, pool_saturation=1.0,
        service="service-thanh-toan", breached_for_seconds=60.0,
    )
    uc2 = rules.detect_crashloop(
        service_up=1.0, restarts=4.0, down_for_seconds=0.0, service="service-thanh-toan",
        memory_ratio=0.89, memory_peak_mb=113.4,
    )
    uc3 = rules.detect_auth_burst(
        failures_per_second=182.8, breached_for_seconds=300.0, service="service-thanh-toan"
    )
    assert uc1 and uc2 and uc3, "bộ số trong test này đã lạc hậu so với rules.py"

    chua_dich: list[str] = []
    for signal in (uc1, uc2, uc3):
        for item in signal.evidence:
            cau, _ = labels.metric(item.name)
            if cau == item.name:
                chua_dich.append(item.name)

    assert not chua_dich, f"tên metric chưa có trong bảng dịch: {chua_dich}"


def test_moi_hanh_dong_deu_dich_duoc():
    thieu = [a for a in remediation.SUPPORTED_ACTIONS if a not in labels.ACTION]
    assert not thieu, f"hành động chưa có trong bảng dịch: {thieu}"


def test_moi_trang_thai_va_muc_do_deu_dich_duoc():
    assert not [s.value for s in IncidentState if s.value not in labels.STATE]
    assert not [s.value for s in Severity if s.value not in labels.SEVERITY]


def test_khong_bao_gio_in_baseline_none():
    """Lỗi thật trên trang: UI in ra chữ "None" khi metric không có baseline."""
    dong = labels.bang_chung("db_pool_connections_in_use / db_pool_size", 1.0, baseline=None)

    assert "None" not in dong.plain
    assert "thường" not in dong.plain


def test_giu_nguyen_van_ten_metric_va_promql_cho_nguoi_truc():
    """Dịch THÊM, không dịch THAY — mất đường đào là mất người sửa được sự cố."""
    promql = 'histogram_quantile(0.95, sum by (service, le) (rate(...{handler!="/metrics"}[1m])))'
    dong = labels.bang_chung(
        "http_request_duration_seconds p95", 4.417, baseline=0.58, unit="s", promql=promql
    )

    assert "Thời gian khách phải chờ" in dong.plain
    assert "4.42 giây" in dong.plain or "4.417 giây" in dong.plain
    assert "lệch 7.6 lần" in dong.plain
    # Tầng cho người trực: tên gốc nguyên văn và PromQL không bị sửa một ký tự.
    assert dong.raw == "http_request_duration_seconds p95 = 4.417s"
    assert dong.promql == promql


def test_ty_le_hien_thanh_phan_tram():
    dong = labels.bang_chung("tỷ lệ lỗi 5xx", 0.12)

    assert "12%" in dong.plain
    assert dong.raw == "tỷ lệ lỗi 5xx = 0.12"


def test_ten_la_thi_hien_tho_chu_khong_dich_sai():
    """Thà hiện tên thô còn hơn hiện sai — người trực vẫn đọc được."""
    cau, don_vi = labels.metric("một_metric_hoan_toan_moi")

    assert cau == "một_metric_hoan_toan_moi"
    assert don_vi == ""


def test_giu_ma_goc_ben_canh_cau_dich():
    """Người trực gõ đúng chữ trong ngoặc khi thi hành, nên không được bỏ."""
    assert "(increase_pool)" in labels.action("increase_pool")
    assert "(P2)" in labels.severity("P2")


def test_keo_dai_noi_ro_khong_phai_nhap_nhay():
    """Trả lời câu "sao không phải báo động giả?" mà không ai hỏi ra miệng."""
    assert "1 phút" in labels.keo_dai(60.0)
    assert "không phải nhấp nháy" in labels.keo_dai(60.0)
    assert "30 giây" in labels.keo_dai(30.0)
    assert "2.0 giờ" in labels.keo_dai(7200.0)


def test_dinh_bo_nho_khong_bi_nham_voi_bo_nho_dang_dung():
    """Thứ tự trong `_METRIC` có ý nghĩa — hai metric bộ nhớ phải dịch khác nhau."""
    dinh, _ = labels.metric("đỉnh bộ nhớ 10 phút (trần 128 MB)")
    dang_dung, _ = labels.metric("bộ nhớ đang dùng / giới hạn container")

    assert dinh != dang_dung
    assert "nhiều nhất" in dinh


def test_ten_dich_vu_va_suc_khoe_deu_dich_duoc():
    """Khớp tên service trong contract ① và 4 giá trị health của contract ④."""
    assert labels.service("service-thanh-toan") == "Thanh toán"
    assert labels.service("service-dat-hang") == "Đặt hàng"
    # Service lạ hiện tên gốc, không được nuốt mất.
    assert labels.service("service-moi-nao-do") == "service-moi-nao-do"

    for tinh_trang in ("operational", "degraded", "down", "maintenance"):
        icon, cau = labels.health(tinh_trang)
        assert icon and cau and cau != tinh_trang
