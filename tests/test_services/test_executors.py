"""Test cho `executors.py` — chỗ DUY NHẤT trong repo thật sự chạm vào hệ thống.

Mọi test ở đây đều giả `subprocess.run`. Không test nào được phép chạy `docker`
thật: bộ test phải chạy được trên máy không có Docker, và một test lỡ tay khởi
động lại container giữa buổi demo thì tệ hơn nhiều so với việc thiếu test.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.services import executors


@pytest.fixture(autouse=True)
def tat_theo_mac_dinh(monkeypatch: pytest.MonkeyPatch):
    """Mỗi test tự bật nếu cần. Không test nào thừa hưởng biến của máy đang chạy."""
    monkeypatch.delenv(executors._BIEN_BAT, raising=False)


def _docker_ok() -> MagicMock:
    return MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))


# ── Lớp 2: tắt theo mặc định ────────────────────────────────────────────────


def test_mac_dinh_khong_thi_hanh_that():
    """Không bật biến thì tuyệt đối không chạm docker."""
    with patch("subprocess.run", _docker_ok()) as chay:
        assert executors.thi_hanh_that("rollback", "service-thanh-toan") is None
    chay.assert_not_called()


@pytest.mark.parametrize("gia_tri", ["", "0", "true", "yes", "TRUE", " 1 x"])
def test_chi_dung_chu_1_moi_bat(monkeypatch: pytest.MonkeyPatch, gia_tri: str):
    """Chỉ đúng chuỗi "1" mới bật — "true"/"yes" KHÔNG tính.

    Bật nhầm vì gõ `REMEDIATION_REAL=true` rồi tưởng đang mô phỏng là kiểu nhầm
    dẫn tới hành động thật ngoài ý muốn.
    """
    monkeypatch.setenv(executors._BIEN_BAT, gia_tri)
    with patch("subprocess.run", _docker_ok()) as chay:
        assert executors.thi_hanh_that("rollback", "service-thanh-toan") is None
    chay.assert_not_called()


# ── Lớp 3: danh sách trắng theo CẶP ─────────────────────────────────────────


@pytest.mark.parametrize(
    "action,target",
    [
        ("rollback", "service-dat-hang"),  # đúng hành động, SAI đối tượng
        ("rollback", "prod-payments"),  # tên lạ do LLM sinh ra
        ("restart", "service-thanh-toan"),  # đúng đối tượng, SAI hành động
        ("scale_up", "service-thanh-toan"),
        ("block_ip", "service-thanh-toan"),
    ],
)
def test_ngoai_danh_sach_trang_thi_khong_cham_docker(
    monkeypatch: pytest.MonkeyPatch, action: str, target: str
):
    """Danh sách trắng theo CẶP, không theo hành động.

    Đây là lớp chặn quan trọng nhất: `target` đi ra từ đề xuất mà LLM có phần
    tham gia, nên không được tin. Không khớp cặp thì rơi về mô phỏng.
    """
    monkeypatch.setenv(executors._BIEN_BAT, "1")
    with patch("subprocess.run", _docker_ok()) as chay:
        assert executors.thi_hanh_that(action, target) is None
    chay.assert_not_called()


def test_dung_cap_thi_moi_chay(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(executors._BIEN_BAT, "1")
    with patch("subprocess.run", _docker_ok()) as chay:
        ket_qua = executors.thi_hanh_that("rollback", "service-thanh-toan")

    assert ket_qua is not None
    thanh_cong, mo_ta = ket_qua
    assert thanh_cong is True
    assert "v1.4.2" in mo_ta
    chay.assert_called_once()


# ── Lớp 4: lệnh cố định, không dựng chuỗi shell ─────────────────────────────


def test_lenh_khong_dung_shell_va_khong_noi_target_vao(monkeypatch: pytest.MonkeyPatch):
    """`target` chỉ để TRA bảng, không bao giờ nối vào dòng lệnh.

    Nếu nó lọt vào lệnh thì một `target` do LLM sinh ra sẽ thành đầu vào của
    shell — đúng loại lỗ hổng mà một Agent tự chạy lệnh phải đóng từ đầu.
    """
    monkeypatch.setenv(executors._BIEN_BAT, "1")
    with patch("subprocess.run", _docker_ok()) as chay:
        executors.thi_hanh_that("rollback", "service-thanh-toan")

    args, kwargs = chay.call_args
    lenh = args[0]
    assert isinstance(lenh, list), "phải truyền list, không truyền chuỗi"
    assert kwargs.get("shell") is not True
    assert lenh[:2] == ["docker", "compose"]
    assert kwargs["env"]["SIMULATE_MISSING_MIGRATION"] == "0"
    assert kwargs["timeout"] == executors._TIMEOUT_GIAY


# ── Hỏng thì báo, không ném ─────────────────────────────────────────────────


def test_docker_tra_ma_loi_thi_bao_that_bai(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(executors._BIEN_BAT, "1")
    hong = MagicMock(return_value=MagicMock(returncode=1, stdout="", stderr="no such service"))
    with patch("subprocess.run", hong):
        thanh_cong, mo_ta = executors.thi_hanh_that("rollback", "service-thanh-toan")

    assert thanh_cong is False
    assert "no such service" in mo_ta


@pytest.mark.parametrize(
    "loi",
    [subprocess.TimeoutExpired(cmd="docker", timeout=90), FileNotFoundError("docker")],
)
def test_docker_khong_chay_duoc_thi_khong_nem_ra_ngoai(
    monkeypatch: pytest.MonkeyPatch, loi: Exception
):
    """Ném ra ngoài sẽ thành HTTP 500 trống rỗng trên webhook.

    Người trực khi đó chỉ biết "có gì đó sai", không biết là hết giờ chờ, thiếu
    docker, hay hành động đã chạy một nửa.
    """
    monkeypatch.setenv(executors._BIEN_BAT, "1")
    with patch("subprocess.run", MagicMock(side_effect=loi)):
        thanh_cong, mo_ta = executors.thi_hanh_that("rollback", "service-thanh-toan")

    assert thanh_cong is False
    assert mo_ta


# ── Nối với lớp chính sách ──────────────────────────────────────────────────


def test_execute_van_bat_buoc_co_nguoi_duyet(monkeypatch: pytest.MonkeyPatch):
    """Lớp 1 không được nới ra vì có thi hành thật.

    Bật thi hành thật mà quên cổng HITL thì Agent tự khởi động lại được service —
    đúng thứ cả đề bài cấm.
    """
    from src.services import remediation

    monkeypatch.setenv(executors._BIEN_BAT, "1")
    with patch("subprocess.run", _docker_ok()) as chay, pytest.raises(ValueError):
        remediation.execute("rollback", "service-thanh-toan", approved_by="")
    chay.assert_not_called()


def test_execute_bao_simulated_false_khi_chay_that(monkeypatch: pytest.MonkeyPatch):
    """War room phải phân biệt được "đã mô phỏng" với "đã làm thật"."""
    from src.services import remediation

    monkeypatch.setenv(executors._BIEN_BAT, "1")
    with patch("subprocess.run", _docker_ok()):
        ket_qua = remediation.execute(
            "rollback", "service-thanh-toan", approved_by="712020:nguoi-that"
        )

    assert ket_qua.simulated is False
    assert ket_qua.succeeded is True
    assert "(mô phỏng)" not in ket_qua.as_comment()


def test_execute_van_mo_phong_khi_chua_bat():
    from src.services import remediation

    with patch("subprocess.run", _docker_ok()) as chay:
        ket_qua = remediation.execute(
            "rollback", "service-thanh-toan", approved_by="712020:nguoi-that"
        )

    assert ket_qua.simulated is True
    assert "(mô phỏng)" in ket_qua.as_comment()
    chay.assert_not_called()
