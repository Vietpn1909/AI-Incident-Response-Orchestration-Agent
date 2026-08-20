"""Test cho `planned_events` — việc đã lên lịch GIẢI THÍCH, không bịt miệng.

Test quan trọng nhất trong file này không phải mấy test làm điểm lên, mà là nhóm
"KHÔNG được bỏ qua": pentest không giải thích được service chết, và không việc
nào giải thích được chuyện Agent đang mù.

Bộ đo hiện tại **không thể** bắt lỗi đó — nó không có case nào "sự cố thật xảy ra
trong lúc đang có việc lên lịch". Nên nếu chỉ chạy theo điểm thì sẽ xây sai mà vẫn
thấy điểm lên. Mấy test dưới đây là chỗ duy nhất giữ ranh giới ấy.
"""

from __future__ import annotations

import pytest

from src.services.planned_events import giai_thich_duoc

PENTEST = "Pentest đã được phê duyệt bởi CISO, IP 10.0.5.100 đã whitelist"
CHAOS = "Chaos engineering experiment FIS-2026-08-15 đã được phê duyệt"
LOAD_TEST = "Bài thử tải pre-production đã được phê duyệt"


# ── Giải thích ĐÚNG phạm vi thì bỏ qua ──────────────────────────────────────


@pytest.mark.parametrize(
    "viec,detector",
    [
        (PENTEST, "auth"),
        (LOAD_TEST, "auth"),
        (CHAOS, "crashloop"),
        ("blue-green deploy v1.8.0 — old pod shutdown + new pod startup", "crashloop"),
        ("CDN route shift sang ap-southeast-2", "latency"),
        ("Batch job báo cáo cuối ngày", "latency"),
    ],
)
def test_dung_pham_vi_thi_bo_qua(viec: str, detector: str):
    assert giai_thich_duoc(viec, detector, "p95") is True


# ── Ngoài phạm vi thì VẪN báo động ──────────────────────────────────────────


@pytest.mark.parametrize(
    "viec,detector",
    [
        (PENTEST, "crashloop"),   # pentest không làm container restart
        (PENTEST, "latency"),     # cũng không làm pool cạn
        (CHAOS, "auth"),          # chaos không làm đăng nhập sai tăng
        (LOAD_TEST, "crashloop"),
    ],
)
def test_ngoai_pham_vi_thi_van_bao_dong(viec: str, detector: str):
    """Một việc đã lên lịch chỉ giải thích được thứ nó GÂY RA ĐƯỢC.

    Đây là chỗ khác nhau giữa "giải thích" và "bịt miệng". Bịt miệng theo cửa sổ
    thời gian là cách tạo ra loại sự cố tệ nhất: hệ thống cháy trong lúc mọi báo
    động bị tắt vì "đang có việc đã lên lịch".
    """
    assert giai_thich_duoc(viec, detector, "p95") is False


# ── Hai thứ KHÔNG BAO GIỜ được bỏ qua ───────────────────────────────────────


def test_khong_bao_gio_bo_qua_mat_tin_hieu():
    """Mất tín hiệu là lúc Agent đang mù.

    Bỏ qua nó nghĩa là bỏ qua chính khả năng mình đang không thấy gì — và không
    việc đã lên lịch nào biện minh được cho điều đó.
    """
    assert giai_thich_duoc(
        CHAOS, "latency", "http_request_duration_seconds p95 (mất tín hiệu)"
    ) is False


def test_khong_bao_gio_bo_qua_service_chet():
    """Không việc nào làm service ngừng phục vụ mà vẫn gọi là bình thường."""
    assert giai_thich_duoc(CHAOS, "crashloop", "up (service còn sống không)") is False


# ── Không có việc nào thì không bỏ qua gì ───────────────────────────────────


@pytest.mark.parametrize("viec", [None, "", "   "])
def test_khong_co_viec_thi_khong_bo_qua(viec):
    assert giai_thich_duoc(viec, "auth", "p95") is False


def test_detector_la_gi_khong_biet_thi_khong_bo_qua():
    """Detector mới thêm mà quên khai phạm vi → mặc định VẪN báo động.

    Mặc định phải nghiêng về báo động, không nghiêng về im lặng.
    """
    assert giai_thich_duoc(PENTEST, "detector-moi-nao-do", "p95") is False
