"""Test UC-2 — service chết vì OOM rồi restart liên tục.

Điều đáng test nhất ở đây không phải bảng ngưỡng, mà là **UC-2 không dùng chung
đường với UC-1**. Đức đo ngày 02/08: ép OOM làm `RestartCount` lên 7, container
chết và sống lại thật, nhưng `http_requests_total{status=~"5.."}` **bằng 0 tuyệt
đối** — process chết giữa request nên không kịp ghi metric, counter reset sau
mỗi lần restart.

Nghĩa là sự cố nặng nhất lại là sự cố để lại ít dấu vết nhất trong metric của
chính service. Nếu hai UC dùng chung `rules.detect()` thì UC-2 vĩnh viễn không
phát hiện được.
"""

from __future__ import annotations

import pytest

from src.models.incident import Severity
from src.services import rules
from src.services.rules import (
    CRASHLOOP_RESTARTS,
    SUSTAINED_SECONDS,
    classify_crashloop,
    detect,
    detect_crashloop,
)


def _khoe_manh() -> dict:
    """Bộ số của một service hoàn toàn bình thường."""
    return {"service_up": 1.0, "restarts": 0.0, "down_for_seconds": 0.0}


# ------------------------------------------------------------ classify_crashloop


def test_binh_thuong_thi_khong_bao_gi():
    assert classify_crashloop(**_khoe_manh()) is None


def test_chet_du_lau_thi_p1():
    """Service không phục vụ được, không phải chỉ chậm — use-cases.md UC-2."""
    assert classify_crashloop(service_up=0.0, restarts=0.0, down_for_seconds=SUSTAINED_SECONDS) == Severity.P1


def test_mot_lan_scrape_hut_khong_phai_su_co():
    """`up` = 0 một nhịp là chuyện thường, chưa đủ lâu thì chưa tính."""
    assert classify_crashloop(service_up=0.0, restarts=0.0, down_for_seconds=5.0) is None


def test_restart_loop_bao_ke_ca_khi_service_dang_song():
    """Crash loop theo định nghĩa là chết-sống xen kẽ.

    Đòi "chết liên tục 30s" sẽ bỏ lọt, vì đúng lúc Agent quét thì service có thể
    vừa sống lại.
    """
    assert classify_crashloop(service_up=1.0, restarts=3.0, down_for_seconds=0.0) == Severity.P1


def test_mot_lan_restart_la_deploy_khong_phai_su_co():
    """Báo động ở mức này thì mỗi lần đội deploy Agent lại mở một incident."""
    assert classify_crashloop(service_up=1.0, restarts=1.0, down_for_seconds=0.0) is None


def test_dung_nguong_restart_thi_bao():
    assert classify_crashloop(service_up=1.0, restarts=CRASHLOOP_RESTARTS, down_for_seconds=0.0) == Severity.P1


def test_tu_choi_nan():
    with pytest.raises(ValueError, match="NaN"):
        classify_crashloop(service_up=float("nan"), restarts=0.0, down_for_seconds=0.0)


# -------------------------------------------------------------- detect_crashloop


def test_service_khoe_thi_khong_sinh_tin_hieu():
    assert detect_crashloop(**_khoe_manh(), service="service-thanh-toan") is None


def test_tin_hieu_kem_ca_hai_bang_chung():
    """`up` trả lời "bây giờ có phục vụ được không", số restart trả lời "chết
    hẳn hay đang chết đi sống lại" — người trực cần cả hai."""
    signal = detect_crashloop(service_up=0.0, restarts=7.0, down_for_seconds=45.0, service="service-thanh-toan")

    ten = [evidence.name for evidence in signal.evidence]
    assert "up (service còn sống không)" in ten
    assert "số lần restart trong 10 phút" in ten
    assert all(evidence.promql for evidence in signal.evidence)


def test_dang_chet_thi_metric_chinh_la_up():
    signal = detect_crashloop(service_up=0.0, restarts=7.0, down_for_seconds=45.0, service="service-thanh-toan")

    assert signal.severity == Severity.P1
    assert signal.metric_value == 0.0
    assert "up" in signal.metric_name


def test_dang_song_nhung_loop_thi_metric_chinh_la_so_lan_restart():
    signal = detect_crashloop(service_up=1.0, restarts=4.0, down_for_seconds=0.0, service="service-thanh-toan")

    assert signal.metric_name == "số lần restart trong 10 phút"
    assert signal.metric_value == 4.0
    assert signal.threshold == CRASHLOOP_RESTARTS


# ------------------------------------------------------- UC-2 khác đường UC-1


def test_uc2_khong_bat_duoc_bang_duong_cua_uc1():
    """Bộ số Đức đo thật khi ép OOM: 7 lần restart, KHÔNG có lỗi 5xx nào.

    `rules.detect()` nhìn vào bộ số này thấy một service hoàn toàn khoẻ. Đó
    chính là lý do UC-2 phải có nhánh riêng — không phải để cho gọn code.
    """
    uc1 = detect(
        p95_now=0.048,  # server-side vẫn nhanh
        p95_baseline=0.048,
        error_rate=0.0,  # process chết giữa request, không kịp ghi metric
        pool_saturation=0.2,
        service="service-thanh-toan",
        breached_for_seconds=600.0,
    )
    uc2 = classify_crashloop(service_up=0.0, restarts=7.0, down_for_seconds=45.0)

    assert uc1 is None, "UC-1 không thể thấy gì — đúng như đo được"
    assert uc2 == Severity.P1


def test_ba_uc_ba_hinh_thai_khac_nhau():
    """Ba nhánh phải phân biệt được nhau, không phải ba biến thể của một rule."""
    from src.services.rules import classify_auth_burst

    # UC-2: chết, nhưng không chậm và không lỗi 5xx
    assert classify_crashloop(service_up=0.0, restarts=7.0, down_for_seconds=45.0) == Severity.P1
    assert classify_auth_burst(0.0, breached_for_seconds=600.0) is None

    # UC-3: hệ thống hoàn toàn khoẻ, chỉ hình thái truy cập bất thường
    assert classify_auth_burst(200.0, breached_for_seconds=60.0) == Severity.P1
    assert classify_crashloop(**_khoe_manh()) is None


# ───────────────────────── bằng chứng bộ nhớ — vì sao eval M3 cho UC-2 ra 0/8


def test_bang_chung_kem_ca_bo_nho():
    """Không có số về bộ nhớ thì Agent chứng minh được service đang chết đi sống
    lại, nhưng KHÔNG nói được vì sao — mà ground truth UC-2 là "OOM-kill do rò
    rỉ bộ nhớ".

    Qwen trả lời "chưa xác định được nguyên nhân gốc" là hành vi ĐÚNG với dữ
    liệu nó được đưa. Lỗi ở phía mình, không phải phía LLM.
    """
    signal = detect_crashloop(
        service_up=0.0,
        restarts=7.0,
        down_for_seconds=45.0,
        service="service-thanh-toan",
        memory_ratio=0.99,
        memory_peak_mb=127.0,
    )

    ten = [item.name for item in signal.evidence]
    assert "bộ nhớ đang dùng / giới hạn container" in ten
    assert any("đỉnh bộ nhớ" in name for name in ten)
    assert all(item.promql for item in signal.evidence)


def test_ten_bang_chung_bo_nho_mang_theo_tran():
    """Trần ghi trong TÊN, không mượn `baseline`.

    `baseline` nghĩa là "mức thường ngày", nên war room in ra "114 MB — lệch
    0.9× baseline" — đọc thành thấp hơn bình thường, trong khi thật ra là 89%
    của trần. Số đúng, câu sai.
    """
    signal = detect_crashloop(
        service_up=0.0,
        restarts=7.0,
        down_for_seconds=45.0,
        service="service-thanh-toan",
        memory_ratio=0.99,
        memory_peak_mb=127.0,
    )

    dinh = next(item for item in signal.evidence if "đỉnh bộ nhớ" in item.name)
    assert "128 MB" in dinh.name
    assert dinh.baseline is None, "không mượn baseline làm giới hạn"
    assert dinh.value == 127.0


def test_thieu_metric_bo_nho_van_bao_duoc_su_co():
    """Prometheus chưa kịp scrape thì vẫn phải phát hiện được crash loop —
    chỉ là chẩn đoán yếu hơn, không phải im lặng."""
    signal = detect_crashloop(service_up=0.0, restarts=7.0, down_for_seconds=45.0, service="service-thanh-toan")

    assert signal is not None
    assert signal.severity == Severity.P1


def test_prometheus_dem_thieu_restart_van_phai_phat_hien_duoc():
    """Đo thật 05/08: Docker báo RestartCount = 5, Prometheus chỉ thấy 1.

    Process chết rồi sống lại nhanh hơn nhịp scrape 5s nên phần lớn mốc khởi
    động không ai ghi lại. Chỉ dựa vào số lần restart thì Agent báo "bình
    thường" đúng lúc container vừa bị OOM-kill 5 lần — đã xảy ra.

    Bộ nhớ chạm trần là thứ phân biệt được "OOM loop" với "deploy bình thường",
    nên nó cứu được đường phát hiện khi số restart đếm thiếu.
    """
    signal = detect_crashloop(
        service_up=1.0,
        restarts=1.0,  # Prometheus đếm thiếu
        down_for_seconds=0.0,
        service="service-thanh-toan",
        memory_ratio=0.80,
        memory_peak_mb=114.379,  # 89% của trần 128 MB
    )

    assert signal is not None
    assert signal.severity == Severity.P1


def test_mot_lan_restart_ma_bo_nho_thap_van_la_deploy():
    """Không được hạ ngưỡng restart xuống 1 cho xong — deploy sẽ thành incident."""
    assert (
        detect_crashloop(
            service_up=1.0,
            restarts=1.0,
            down_for_seconds=0.0,
            service="service-thanh-toan",
            memory_ratio=0.30,
            memory_peak_mb=40.0,
        )
        is None
    )


def test_phan_loai_theo_dinh_khong_theo_gia_tri_tuc_thoi():
    """Process vừa restart thì bộ nhớ về mức thấp — đo tức thời giấu mất đỉnh.

    Đo thật: tức thời 0.80 (dưới ngưỡng), đỉnh 0.89 (trên ngưỡng).
    """
    signal = detect_crashloop(
        service_up=1.0,
        restarts=1.0,
        down_for_seconds=0.0,
        service="service-thanh-toan",
        memory_ratio=0.801,
        memory_peak_mb=114.379,
    )

    assert signal is not None, "phân loại theo tức thời thì bỏ lọt sự cố này"


# ─────────────────────────── dự báo xu hướng: SẼ chết, chưa chết


def test_bo_nho_tang_dan_thi_bao_truoc_khi_chet():
    """Rò rỉ chậm phải bắt được TRƯỚC lúc OOM, không phải sau.

    Case I18 trong bộ đo: 84% trong khi ngưỡng 85%, tăng ~6%/giờ → 1 giờ nữa qua
    ngưỡng, 3 giờ nữa OOM. Luật cũ đọc 0,84 rồi kết luận bình thường — đúng theo
    cách nó được viết, và bỏ lọt một sự cố **đã biết trước giờ xảy ra**.
    """
    signal = rules.detect_crashloop(
        service_up=1.0,
        restarts=0.0,
        down_for_seconds=0.0,
        service="service-dat-hang",
        memory_ratio=0.84,
        memory_forecast_ratio=0.90,
    )

    assert signal is not None
    assert signal.severity is Severity.P2
    assert "dự báo" in signal.metric_name


def test_du_bao_mot_minh_khong_du_de_bao_dong():
    """`predict_linear` ngoại suy tuyến tính nên tải nhích rồi tụt vẫn cho dốc.

    Đòi thêm "hiện tại đã dùng kha khá": 20% bộ nhớ mà dự báo lên 90% cũng chỉ là
    một đường thẳng vẽ qua nhiễu, không phải rò rỉ.
    """
    assert (
        rules.detect_crashloop(
            service_up=1.0,
            restarts=0.0,
            down_for_seconds=0.0,
            service="service-dat-hang",
            memory_ratio=0.20,
            memory_forecast_ratio=0.95,
        )
        is None
    )


def test_du_bao_phang_thi_khong_bao_dong():
    """Bộ nhớ cao nhưng ổn định không phải sự cố — nhiều service vốn dùng nhiều."""
    assert (
        rules.detect_crashloop(
            service_up=1.0,
            restarts=0.0,
            down_for_seconds=0.0,
            service="service-dat-hang",
            memory_ratio=0.78,
            memory_forecast_ratio=0.78,
        )
        is None
    )


def test_tin_hieu_du_bao_khong_mang_ten_restart():
    """Tên chỉ số phải là "dự báo", không mượn tên "số lần restart".

    Hai lẽ. Một: `restarts` ở đây bằng 0, nên "0 lần restart (ngưỡng 2)" là câu
    vô nghĩa với người trực. Hai: `planned_events._PHAM_VI["crashloop"]` có từ
    khoá "deploy", nên tín hiệu này sẽ bị một lần deploy gần đó bịt miệng — dù
    deploy KHÔNG giải thích được rò rỉ bộ nhớ.
    """
    from src.services import planned_events

    signal = rules.detect_crashloop(
        service_up=1.0,
        restarts=0.0,
        down_for_seconds=0.0,
        service="service-dat-hang",
        memory_ratio=0.84,
        memory_forecast_ratio=0.90,
    )
    assert signal is not None
    assert "restart" not in signal.metric_name.lower()
    assert not planned_events.giai_thich_duoc(
        "deploy v1.4.3", "crashloop", signal.metric_name
    ), "deploy không được bịt miệng tín hiệu dự báo rò rỉ bộ nhớ"


def test_bang_chung_du_bao_truy_nguoc_duoc_bang_promql():
    """Người trực phải dán được câu PromQL ra đúng con số trên war room."""
    signal = rules.detect_crashloop(
        service_up=1.0,
        restarts=0.0,
        down_for_seconds=0.0,
        service="service-dat-hang",
        memory_ratio=0.84,
        memory_forecast_ratio=0.90,
    )
    assert signal is not None
    bang_chung = next(e for e in signal.evidence if "dự báo" in e.name)
    assert bang_chung.value == 0.90
    assert "predict_linear" in (bang_chung.promql or "")
