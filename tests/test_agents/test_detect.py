"""Test node `detect` và `BreachTracker`.

Không cần Prometheus: thay `_client()` bằng client giả trả số cố định. Điều
đáng test ở node này không phải chuyện gọi HTTP — phần đó đã có
`test_prometheus.py` — mà là ba quyết định:

1. Quy tắc "vượt ngưỡng liên tục ≥ 30s" có thật sự bắc qua nhiều vòng poll không
2. Service hồi phục rồi hỏng lại có bị cộng dồn thời gian không
3. Prometheus chết có bị nhầm thành "mọi thứ bình thường" không
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.agents.nodes import detect as detect_module
from src.agents.nodes.detect import BreachTracker, detect_node
from src.services.prometheus import MetricSample, PrometheusError
from src.services.rules import SUSTAINED_SECONDS

NOW = datetime(2026, 8, 1, 14, 32, 4, tzinfo=UTC)


class FakePrometheus:
    """Trả giá trị cố định theo từng câu query."""

    def __init__(self, p95: dict, baseline: dict, error_rate: dict, pool: dict) -> None:
        self._by_query = {"p95": p95, "baseline": baseline, "error": error_rate, "pool": pool}

    def query(self, promql: str) -> list[MetricSample]:
        if "quantile_over_time" in promql:
            key = "baseline"
        elif "histogram_quantile" in promql:
            key = "p95"
        elif "status=~" in promql:
            key = "error"
        else:
            key = "pool"
        return [MetricSample(service=service, value=value) for service, value in self._by_query[key].items()]


class DeadPrometheus:
    def query(self, promql: str) -> list[MetricSample]:
        raise PrometheusError("Không gọi được Prometheus tại http://localhost:9090")


@pytest.fixture(autouse=True)
def _reset_tracker():
    """Tracker sống ở module nên phải dọn giữa các test, nếu không chúng dính nhau."""
    detect_module._tracker = BreachTracker()


def _dung_prometheus(monkeypatch, **kwargs) -> None:
    monkeypatch.setattr(detect_module, "_client", lambda: FakePrometheus(**kwargs))


# ------------------------------------------------------------- BreachTracker


def test_lan_dau_vuot_nguong_thi_chua_du_lau():
    tracker = BreachTracker()
    assert tracker.update("service-thanh-toan", breaching=True, now=NOW) == 0.0


def test_cong_don_qua_nhieu_vong_poll():
    """Quy tắc 30s bắc qua nhiều vòng poll — state của graph không giữ được."""
    tracker = BreachTracker()
    tracker.update("service-thanh-toan", breaching=True, now=NOW)

    sau_45s = tracker.update("service-thanh-toan", breaching=True, now=NOW + timedelta(seconds=45))

    assert sau_45s == 45.0


def test_hoi_phuc_thi_dem_lai_tu_dau():
    """Hai sự cố cách nhau một tiếng không được cộng dồn thành một."""
    tracker = BreachTracker()
    tracker.update("service-thanh-toan", breaching=True, now=NOW)
    tracker.update("service-thanh-toan", breaching=False, now=NOW + timedelta(seconds=50))

    lan_hai = tracker.update("service-thanh-toan", breaching=True, now=NOW + timedelta(hours=1))

    assert lan_hai == 0.0


def test_moi_service_dem_rieng():
    tracker = BreachTracker()
    tracker.update("service-thanh-toan", breaching=True, now=NOW)
    tracker.update("service-dat-hang", breaching=True, now=NOW + timedelta(seconds=30))

    thanh_toan = tracker.update("service-thanh-toan", breaching=True, now=NOW + timedelta(seconds=60))
    dat_hang = tracker.update("service-dat-hang", breaching=True, now=NOW + timedelta(seconds=60))

    assert (thanh_toan, dat_hang) == (60.0, 30.0)


# ---------------------------------------------------------------- detect_node


def test_moi_thu_binh_thuong_thi_khong_co_tin_hieu(monkeypatch):
    _dung_prometheus(
        monkeypatch,
        p95={"service-thanh-toan": 0.18},
        baseline={"service-thanh-toan": 0.18},
        error_rate={"service-thanh-toan": 0.0},
        pool={"service-thanh-toan": 0.2},
    )

    assert detect_node({}) == {"signals": []}


def test_vong_poll_dau_tien_chua_mo_incident(monkeypatch):
    """Vượt ngưỡng ngay lập tức vẫn phải chờ đủ 30s — chống spike đơn lẻ."""
    _dung_prometheus(
        monkeypatch,
        p95={"service-thanh-toan": 5.1},
        baseline={"service-thanh-toan": 0.2},
        error_rate={"service-thanh-toan": 0.12},
        pool={"service-thanh-toan": 1.0},
    )

    assert detect_node({})["signals"] == []


def test_vuot_nguong_du_lau_thi_sinh_tin_hieu(monkeypatch):
    _dung_prometheus(
        monkeypatch,
        p95={"service-thanh-toan": 5.1},
        baseline={"service-thanh-toan": 0.2},
        error_rate={"service-thanh-toan": 0.12},
        pool={"service-thanh-toan": 1.0},
    )
    # Vòng poll đầu chỉ đặt mốc; kéo mốc lùi lại để mô phỏng đã trôi qua 45s.
    detect_node({})
    detect_module._tracker._since["service-thanh-toan"] -= timedelta(seconds=45)

    signals = detect_node({})["signals"]

    assert len(signals) == 1
    assert signals[0].affected_service == "service-thanh-toan"
    assert signals[0].breached_for_seconds >= SUSTAINED_SECONDS
    assert signals[0].evidence, "tín hiệu phải kèm bằng chứng số"


def test_danh_sach_service_lay_tu_prometheus_khong_hardcode(monkeypatch):
    """Thêm service mới chỉ cần sửa prometheus.yml, không phải sửa code Agent."""
    _dung_prometheus(
        monkeypatch,
        p95={"service-moi-tinh": 5.1},
        baseline={"service-moi-tinh": 0.2},
        error_rate={"service-moi-tinh": 0.0},
        pool={"service-moi-tinh": 1.0},
    )
    detect_node({})
    detect_module._tracker._since["service-moi-tinh"] -= timedelta(seconds=45)

    signals = detect_node({})["signals"]

    assert [signal.affected_service for signal in signals] == ["service-moi-tinh"]


def test_prometheus_chet_thi_bao_loi_chu_khong_bao_binh_thuong(monkeypatch):
    """Trả `signals: []` mà không có `error` là nói dối rằng mọi thứ ổn."""
    monkeypatch.setattr(detect_module, "_client", lambda: DeadPrometheus())

    result = detect_node({})

    assert result["signals"] == []
    assert "Không gọi được Prometheus" in result["error"]


def test_service_bien_mat_khoi_prometheus_thi_quen_moc(monkeypatch):
    """Service ngừng nhận request thì mốc cũ phải bị xoá, không nằm lại mãi."""
    _dung_prometheus(
        monkeypatch,
        p95={"service-thanh-toan": 5.1},
        baseline={"service-thanh-toan": 0.2},
        error_rate={"service-thanh-toan": 0.0},
        pool={"service-thanh-toan": 1.0},
    )
    detect_node({})
    assert detect_module._tracker.tracked_services() == {"service-thanh-toan"}

    _dung_prometheus(monkeypatch, p95={}, baseline={}, error_rate={}, pool={})
    detect_node({})

    assert detect_module._tracker.tracked_services() == set()
