"""Test phần TẤT ĐỊNH của chẩn đoán — `correlate_deploy` và `build_hypothesis`.

Không có LLM ở đây. Đó là chủ đích: contract ② chốt `evidence` và `confidence`
do rule engine sinh, nên chúng phải kiểm được mà không cần mạng, không cần key,
và cho ra cùng kết quả mỗi lần chạy.

`eval/` chấm độ chính xác chẩn đoán qua chính hai thứ này — nếu chúng phụ thuộc
LLM thì con số phần trăm dao động giữa các lần chạy và không đo được gì.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.models.incident import DeployRecord, IncidentSignal, MetricEvidence, Severity
from src.services.rules import (
    DEPLOY_WINDOW_MINUTES,
    build_hypothesis,
    correlate_deploy,
)

NOW = datetime(2026, 8, 3, 16, 13, 0, tzinfo=UTC)


def _deploy(version: str, phut_truoc: float) -> DeployRecord:
    return DeployRecord(
        service="service-thanh-toan",
        version=version,
        deployed_at=NOW - timedelta(minutes=phut_truoc),
    )


def _signal(*, p95: float = 4.4, baseline: float | None = 1.19, pool: float = 1.0, loi: float = 0.0) -> IncidentSignal:
    return IncidentSignal(
        affected_service="service-thanh-toan",
        severity=Severity.P2,
        detected_at=NOW,
        metric_name="http_request_duration_seconds p95",
        metric_value=p95,
        threshold=2.0,
        breached_for_seconds=60.0,
        evidence=[
            MetricEvidence(
                name="http_request_duration_seconds p95", value=p95, baseline=baseline, unit="s", promql="..."
            ),
            MetricEvidence(name="db_pool_connections_in_use / db_pool_size", value=pool, promql="..."),
            MetricEvidence(name="tỷ lệ lỗi 5xx", value=loi, promql="..."),
        ],
    )


# ────────────────────────────────────────────────────── correlate_deploy


def test_khong_co_deploy_nao_thi_tra_none():
    assert correlate_deploy([], NOW) is None


def test_bat_duoc_nghi_pham_seed_cam_san():
    """`demo/seed.py` cắm cố ý một dòng v1.4.2 deploy trước 4 phút."""
    deploys = [_deploy("v1.4.1", phut_truoc=2880), _deploy("v1.4.2", phut_truoc=4)]

    assert correlate_deploy(deploys, NOW).version == "v1.4.2"


def test_lay_lan_gan_nhat_khi_co_nhieu_lan_trong_cua_so():
    deploys = [_deploy("v1.4.0", phut_truoc=12), _deploy("v1.4.2", phut_truoc=4), _deploy("v1.4.1", phut_truoc=8)]

    assert correlate_deploy(deploys, NOW).version == "v1.4.2"


def test_deploy_qua_cu_thi_bo_qua():
    """Nới cửa sổ ra thì mọi sự cố đều "có deploy ngay trước", bằng chứng mất giá trị."""
    assert correlate_deploy([_deploy("v1.4.1", phut_truoc=DEPLOY_WINDOW_MINUTES + 1)], NOW) is None


def test_deploy_sau_su_co_khong_tinh():
    """Deploy sau khi phát hiện thì không thể là nguyên nhân."""
    assert correlate_deploy([_deploy("v1.5.0", phut_truoc=-3)], NOW) is None


# ────────────────────────────────────────────────────── confidence


def test_confidence_la_ham_cua_bang_chung_khong_phai_hang_so():
    """Nếu là hằng số thì nó không đo gì cả — chỉ là người bịa thay vì máy bịa."""
    manh = build_hypothesis(_signal(pool=1.0, p95=4.4, baseline=1.19), _deploy("v1.4.2", 4))
    yeu = build_hypothesis(_signal(pool=0.2, p95=1.2, baseline=1.19), None)

    assert manh.confidence > yeu.confidence


def test_du_ca_bon_bang_chung_thi_gan_toi_da():
    """pool cạn 0.40 + p95 lệch mạnh 0.30 + deploy 0.20 + lỗi 5xx 0.10 = 1.00."""
    hypothesis = build_hypothesis(_signal(pool=1.0, p95=4.4, baseline=1.19, loi=0.15), _deploy("v1.4.2", 4))

    assert hypothesis.confidence == 1.0


def test_chi_co_p95_cao_thi_diem_thap():
    """Một giả thuyết chỉ dựa trên "p95 cao" ĐÁNG bị thấp."""
    hypothesis = build_hypothesis(_signal(pool=0.3, p95=4.4, baseline=1.19), None)

    assert hypothesis.confidence == 0.30


def test_mat_bang_chung_deploy_thi_mat_dung_phan_diem_cua_no():
    """DB không đọc được thì confidence tụt đúng 0.20, không phải sập về 0."""
    co_deploy = build_hypothesis(_signal(), _deploy("v1.4.2", 4))
    khong_deploy = build_hypothesis(_signal(), None)

    assert round(co_deploy.confidence - khong_deploy.confidence, 2) == 0.20


def test_confidence_khong_bao_gio_vuot_1():
    hypothesis = build_hypothesis(_signal(pool=1.0, p95=99.0, baseline=0.1, loi=0.9), _deploy("v1.4.2", 1))

    assert 0.0 <= hypothesis.confidence <= 1.0


# ────────────────────────────────────────────────────── câu giả thuyết


def test_neu_nguyen_nhan_goc_khong_phai_trieu_chung():
    """`use-cases.md` UC-1: nêu "service chậm" thì KHÔNG tính là chẩn đoán đúng."""
    hypothesis = build_hypothesis(_signal(pool=1.0), None)

    assert "pool" in hypothesis.statement.lower()


def test_khong_suy_nhan_qua_tu_trung_thoi_gian():
    """Deploy trong demo KHÔNG gây ra sự cố — seed.py cắm nó vào mỗi lần chạy,
    còn pg_sleep(0.2) thì luôn có mặt bất kể version nào.

    Viết "cạn vì deploy v1.4.2" là suy nhân quả từ tương quan: nghe thuyết
    phục, và sai.
    """
    hypothesis = build_hypothesis(_signal(), _deploy("v1.4.2", 4))

    assert "trùng thời gian" in hypothesis.statement.lower()
    assert "vì deploy" not in hypothesis.statement.lower()
    assert "do deploy" not in hypothesis.statement.lower()


def test_bang_chung_lay_nguyen_tu_tin_hieu_khong_bia_them():
    signal = _signal()
    hypothesis = build_hypothesis(signal, None)

    assert hypothesis.evidence == signal.evidence
    assert all(item.promql for item in hypothesis.evidence)


def test_giu_lai_ban_ghi_deploy_de_de_xuat_rollback_biet_ve_dau():
    hypothesis = build_hypothesis(_signal(), _deploy("v1.4.2", 4))

    assert hypothesis.related_deploy.version == "v1.4.2"


# ──────────────── ba use case, ba hình dạng bằng chứng — hồi quy eval M3 = 38%
#
# Bản đầu của `_diem_tin_cay()` và `_cau_giai_thuyet()` chỉ biết tên bằng chứng
# của UC-1, nên mọi giả thuyết UC-2 và UC-3 ra `confidence = 0.0` kèm một câu
# chỉ nhắc lại triệu chứng. `use-cases.md` chấm "nêu chung chung" là KHÔNG đạt.


def _uc2_signal(*, peak_mb: float = 127.0, ratio: float = 0.99) -> IncidentSignal:
    from src.services.rules import detect_crashloop

    return detect_crashloop(
        service_up=0.0,
        restarts=7.0,
        down_for_seconds=45.0,
        service="service-thanh-toan",
        memory_ratio=ratio,
        memory_peak_mb=peak_mb,
    )


def _uc3_signal(*, moi_giay: float = 200.0) -> IncidentSignal:
    from src.services.rules import detect_auth_burst

    return detect_auth_burst(failures_per_second=moi_giay, breached_for_seconds=60.0, service="service-thanh-toan")


def test_moi_use_case_deu_co_confidence_khac_khong():
    """Không UC nào được ra 0 — con số đó vô nghĩa y như một hằng số cắm cứng."""
    uc1 = build_hypothesis(_signal(), None)
    uc2 = build_hypothesis(_uc2_signal(), None)
    uc3 = build_hypothesis(_uc3_signal(), None)

    assert uc1.confidence > 0
    assert uc2.confidence > 0
    assert uc3.confidence > 0


def test_uc2_neu_duoc_oom_chu_khong_chi_noi_service_chet():
    """Ground truth UC-2: container bị OOM-kill vì rò rỉ bộ nhớ."""
    hypothesis = build_hypothesis(_uc2_signal(), None)

    cau = hypothesis.statement.lower()
    assert "oom" in cau
    assert "bộ nhớ" in cau
    assert "127" in cau and "128" in cau, "phải dẫn số thật, không nói chung chung"


def test_uc3_neu_duoc_van_de_bao_mat_chu_khong_phai_qua_tai():
    """`use-cases.md` UC-3: kết luận "service quá tải" là chẩn đoán SAI."""
    hypothesis = build_hypothesis(_uc3_signal(), None)

    cau = hypothesis.statement.lower()
    assert "credential-stuffing" in cau or "đăng nhập thất bại" in cau
    assert "quá tải" not in cau.replace("không phải quá tải", "")


def test_bo_nho_chua_cham_tran_thi_khong_ket_luan_oom():
    """Bộ nhớ 40% trần mà kết luận OOM là bịa — phải rơi về câu thận trọng."""
    hypothesis = build_hypothesis(_uc2_signal(peak_mb=51.0, ratio=0.40), None)

    assert "oom" not in hypothesis.statement.lower()
    assert "chưa đủ bằng chứng" in hypothesis.statement.lower()


def test_khong_du_bang_chung_thi_noi_thang_la_chua_biet():
    """Thà nói "chưa đủ bằng chứng" còn hơn đoán bừa — đó cũng là cách Qwen
    đang hành xử, và nó đúng."""
    tron = _signal(pool=0.1, p95=1.2, baseline=1.19)
    tron.evidence = [tron.evidence[0]]

    assert "chưa đủ bằng chứng" in build_hypothesis(tron, None).statement.lower()
