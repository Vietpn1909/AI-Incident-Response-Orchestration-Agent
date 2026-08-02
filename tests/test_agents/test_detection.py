"""Test node `detect` + `open_war_room` + vòng lặp nối chúng.

Không cần Prometheus lẫn Jira thật: Prometheus giả bằng `httpx.MockTransport`,
Jira giả bằng `FakeJiraClient`.

Test quan trọng nhất là `test_khong_mo_trung_khi_su_co_van_con` — thiếu chống
mở trùng thì lúc load test, mỗi vòng poll lại đẻ một issue mới và war room
thành rác sau vài phút.
"""

from __future__ import annotations

import json

import httpx
import pytest

from src.agents.detection_loop import run_cycle
from src.agents.nodes.detect import detect_incidents
from src.agents.nodes.open_war_room import open_war_room
from src.models.incident import IncidentState, Severity
from src.services.jira import FakeJiraClient
from src.services.prometheus import PrometheusClient

# Giá trị mô phỏng lúc nghẽn, lấy từ số Việt đo được trong spike:
# p95 1.95s, pool cạn 100%, lỗi 2.1%, baseline 0.18s.
NGHEN = {"p95": 5.1, "baseline": 0.2, "error": 0.12, "pool": 1.0}
BINH_THUONG = {"p95": 0.095, "baseline": 0.181, "error": 0.0, "pool": 0.0}


def _classify(promql: str) -> str:
    """Câu PromQL này đang hỏi metric nào.

    Nhận diện theo chuỗi đặc trưng thay vì so nguyên văn — các hằng trong
    `prometheus.py` là chuỗi nhiều dòng và bị bọc thêm khi đo thời lượng.

    Thứ tự các nhánh là phần dễ sai nhất của cả file test này, vì các hằng
    trong `prometheus.py` lồng vào nhau:

    - `P95_LATENCY` có chứa `http_requests_total` — đó là bộ lọc `_HAS_TRAFFIC`
      chống NaN, không phải câu đo tỷ lệ lỗi. Xét `http_requests_total` trước
      là nhận nhầm mọi câu p95 thành câu error.
    - `P95_BASELINE_30M` bọc một `histogram_quantile` bên trong một
      `quantile_over_time`, nên phân biệt "có chứa histogram_quantile" là nhận
      nhầm baseline thành câu đo lệch. Câu đo lệch chia p95 cho baseline nên có
      đúng hai `histogram_quantile`.

    Vì vậy đi từ đặc trưng hẹp nhất tới rộng nhất, và `http_requests_total`
    phải đứng CUỐI.
    """
    if "db_pool" in promql:
        return "pool"
    if promql.count("histogram_quantile") >= 2:
        return "deviation"
    if "quantile_over_time" in promql:
        return "baseline"
    if "histogram_quantile" in promql:
        return "p95"
    return "error"


def _prometheus(values: dict[str, float], *, service: str = "service-thanh-toan", sustained: bool = True):
    """Prometheus giả trả số cố định cho mọi câu query."""

    def handler(request: httpx.Request) -> httpx.Response:
        promql = request.url.params.get("query", "")
        kind = _classify(promql)

        if kind == "deviation":
            value = values["p95"] / values["baseline"] if values["baseline"] else 0.0
        else:
            value = values[kind]

        # Câu đo "đã bất thường liên tục bao lâu". Không sustained thì trả giá
        # trị dưới mọi ngưỡng để mọi cửa sổ đều trượt.
        if "min_over_time" in promql and not sustained:
            value = 0.0

        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [{"metric": {"service": service}, "value": [0, str(value)]}],
                },
            },
        )

    return PrometheusClient(transport=httpx.MockTransport(handler))


# ───────────────────────────────────────────────── tự canh cái fake


def test_fake_phan_loai_dung_tung_cau_promql():
    """Canh chính bộ nhận diện của fake ở trên.

    Đã sai hai lần khi viết file này: một lần nhận nhầm câu p95 thành câu error
    (vì `P95_LATENCY` chứa `http_requests_total`), một lần nhận nhầm baseline
    thành câu đo lệch. Cả hai lần test vẫn xanh — chỉ là xanh vì lý do khác.
    Fake sai kiểu đó biến toàn bộ file này thành vô nghĩa mà không ai biết, nên
    nó cần test riêng.
    """
    from src.services import prometheus as p

    assert _classify(p.P95_LATENCY) == "p95"
    assert _classify(p.ERROR_RATE) == "error"
    assert _classify(p.P95_BASELINE_30M) == "baseline"
    assert _classify(p.POOL_SATURATION_PEAK_5M) == "pool"
    assert _classify(f"({p.P95_LATENCY}) / ({p.P95_BASELINE_30M})") == "deviation"
    # Bọc trong min_over_time không được làm đổi cách nhận diện.
    assert _classify(f"min_over_time(({p.P95_LATENCY})[30s:5s])") == "p95"
    assert _classify(f"min_over_time(({p.ERROR_RATE})[30s:5s])") == "error"


# ─────────────────────────────────────────────────────────── detect


def test_binh_thuong_thi_khong_bao_gi():
    with _prometheus(BINH_THUONG, sustained=False) as client:
        assert detect_incidents(client) == []


def test_nghen_thi_sinh_tin_hieu_co_bang_chung():
    with _prometheus(NGHEN) as client:
        signals = detect_incidents(client)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.affected_service == "service-thanh-toan"
    assert signal.severity is Severity.P2
    # Ràng buộc "chẩn đoán có bằng chứng": phải kèm số liệu, và mỗi bằng chứng
    # mang theo câu PromQL để người khác kiểm chứng lại được.
    assert len(signal.evidence) >= 3
    assert all(item.promql for item in signal.evidence)


def test_vuot_nguong_nhung_chua_du_lau_thi_bo_qua():
    """Một spike đơn lẻ lúc load test không được mở incident."""
    with _prometheus(NGHEN, sustained=False) as client:
        assert detect_incidents(client) == []


def test_do_duoc_da_vuot_lien_tuc_bao_lau():
    """Lấy cửa sổ LỚN NHẤT còn thoả, không phải cửa sổ đầu tiên."""
    with _prometheus(NGHEN) as client:
        signals = detect_incidents(client)

    assert signals[0].breached_for_seconds == 300.0


def test_prometheus_tra_rong_thi_khong_crash():
    """Chưa có traffic là bình thường, không phải lỗi."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "success", "data": {"resultType": "vector", "result": []}})

    with PrometheusClient(transport=httpx.MockTransport(handler)) as client:
        assert detect_incidents(client) == []


def test_prometheus_chet_thi_nem_loi_chu_khong_im_lang():
    """Agent mù mà tưởng 'bình thường' là tình huống nguy hiểm nhất."""
    from src.services.prometheus import PrometheusError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    with PrometheusClient(transport=httpx.MockTransport(handler)) as client, pytest.raises(PrometheusError):
        detect_incidents(client)


def test_5xx_tran_nhung_latency_binh_thuong_van_bao():
    """UC-2: container OOM rồi restart — service phun 5xx, request còn sống vẫn nhanh.

    Lỗi thật đã gặp: bản đầu của `breached_seconds_by_service()` chỉ đo p95, nên
    cửa "đủ lâu" luôn thấy 0 với kịch bản này và Agent im lặng suốt sự cố.
    """
    oom = {"p95": 0.05, "baseline": 0.048, "error": 0.35, "pool": 0.2}
    with _prometheus(oom) as client:
        signals = detect_incidents(client)

    assert len(signals) == 1
    assert signals[0].severity is Severity.P2  # error_rate 35% → P2
    assert signals[0].breached_for_seconds >= 30.0


def test_lech_baseline_nhung_duoi_nguong_cung_van_bao():
    """Service vốn nhanh, chậm gấp 4 lần nhưng vẫn dưới ngưỡng cứng P3 (1.0s).

    Cùng loại lỗi: nếu chỉ đo thời lượng bằng ngưỡng cứng thì đường lệch
    baseline của `rules.detect()` không bao giờ với tới được.
    """
    cham = {"p95": 0.4, "baseline": 0.1, "error": 0.0, "pool": 0.9}
    with _prometheus(cham) as client:
        signals = detect_incidents(client)

    assert len(signals) == 1
    assert signals[0].breached_for_seconds >= 30.0


# ──────────────────────────────────────────────────── open_war_room


def test_mo_war_room_va_dinh_kem_bang_chung():
    jira = FakeJiraClient(verbose=False)
    with _prometheus(NGHEN) as client:
        signal = detect_incidents(client)[0]

    result = open_war_room(jira, signal)

    assert result.created is True
    incident = jira.get_incident(result.jira_key)
    assert incident.severity is Severity.P2
    assert any("Bối cảnh" in event.detail for event in incident.timeline)


def test_khong_mo_trung_khi_su_co_van_con():
    """Poll nhiều vòng trong lúc sự cố kéo dài chỉ được có MỘT issue.

    Thiếu `find_open_incident()` thì mỗi vòng đẻ một issue mới, sau vài phút
    war room thành rác và mất tác dụng.
    """
    jira = FakeJiraClient(verbose=False)
    with _prometheus(NGHEN) as client:
        signal = detect_incidents(client)[0]

    first = open_war_room(jira, signal)
    second = open_war_room(jira, signal)
    third = open_war_room(jira, signal)

    assert first.created is True
    assert (second.created, third.created) == (False, False)
    assert second.jira_key == third.jira_key == first.jira_key
    assert len(jira.list_incidents()) == 1


def test_incident_da_dong_thi_mo_lai_issue_moi():
    """Sự cố tái diễn sau khi đã đóng là incident MỚI, không phải cái cũ."""
    jira = FakeJiraClient(verbose=False)
    with _prometheus(NGHEN) as client:
        signal = detect_incidents(client)[0]

    first = open_war_room(jira, signal)
    jira.transition(first.jira_key, IncidentState.RESOLVED)
    second = open_war_room(jira, signal)

    assert second.created is True
    assert second.jira_key != first.jira_key


# ──────────────────────────────────────────────────────── vòng lặp


def test_vong_lap_binh_thuong_thi_yen_lang():
    jira = FakeJiraClient(verbose=False)
    with _prometheus(BINH_THUONG, sustained=False) as client:
        result = run_cycle(client, jira)

    assert result.quiet is True
    assert jira.list_incidents() == []


def test_vong_lap_mo_roi_cap_nhat():
    jira = FakeJiraClient(verbose=False)
    with _prometheus(NGHEN) as client:
        first = run_cycle(client, jira)
        second = run_cycle(client, jira)

    assert first.opened and not first.updated
    assert second.updated and not second.opened
    assert len(jira.list_incidents()) == 1


def test_vong_lap_khong_chet_khi_prometheus_loi():
    """Prometheus chớp tắt không được làm chết cả tiến trình Agent."""
    jira = FakeJiraClient(verbose=False)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=json.dumps({"status": "error"}))

    with PrometheusClient(transport=httpx.MockTransport(handler)) as client:
        result = run_cycle(client, jira)

    assert result.error is not None
    assert result.quiet is False
