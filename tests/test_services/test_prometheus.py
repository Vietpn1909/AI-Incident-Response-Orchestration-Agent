"""Test `PrometheusClient` — phần parse response và phân biệt các trạng thái lỗi.

Không cần Prometheus thật: dùng `httpx.MockTransport` để giả response, nhờ vậy
test chạy được trong CI. Phần verify với Prometheus thật nằm ở
`spike/spike_promql.py`, chạy tay khi có docker.

Điều các test này bảo vệ là ranh giới quan trọng nhất của client:

    danh sách rỗng  = "biết là không có dữ liệu"   -> bình thường
    PrometheusError = "không biết tình hình ra sao" -> phải nổ to

Lẫn hai thứ đó là Agent hiểu Prometheus chết thành "mọi thứ bình thường".
"""

from __future__ import annotations

import httpx
import pytest

from src.services.prometheus import (
    P95_LATENCY,
    MetricSample,
    PrometheusClient,
    PrometheusError,
)


def _client(handler) -> PrometheusClient:
    """Dựng client với transport giả."""
    return PrometheusClient(base_url="http://prometheus:9090", transport=httpx.MockTransport(handler))


def _success(result: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"status": "success", "data": {"resultType": "vector", "result": result}})


def _series(service: str, value: str) -> dict:
    return {"metric": {"service": service, "job": service}, "value": [1785000000.0, value]}


def test_query_tra_ve_mot_sample_moi_service():
    client = _client(
        lambda request: _success([_series("service-thanh-toan", "1.95"), _series("service-dat-hang", "0.42")])
    )

    samples = client.query(P95_LATENCY)

    assert samples == [
        MetricSample(service="service-thanh-toan", value=1.95),
        MetricSample(service="service-dat-hang", value=0.42),
    ]


def test_query_gui_dung_promql_len_prometheus():
    """Câu query phải đi nguyên văn — lệch một ký tự là Prometheus trả rỗng."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query"] = request.url.params["query"]
        seen["path"] = request.url.path
        return _success([])

    _client(handler).query(P95_LATENCY)

    assert seen["path"] == "/api/v1/query"
    assert seen["query"] == P95_LATENCY


def test_ket_qua_rong_khong_phai_loi():
    """Service không có request là trạng thái bình thường, không được raise.

    Đây là hệ quả trực tiếp của bộ lọc `_HAS_TRAFFIC`: lúc không có traffic,
    query trả rỗng thay vì NaN.
    """
    assert _client(lambda request: _success([])).query(P95_LATENCY) == []


def test_bo_qua_gia_tri_nan():
    """NaN phải bị loại, không được lọt tới rule engine.

    `NaN > x` và `NaN < x` đều là False, nên một mẫu NaN lọt qua sẽ làm mọi so
    sánh ngưỡng im lặng rơi tọt — Agent bỏ lọt sự cố mà không có dấu hiệu gì.
    """
    client = _client(lambda request: _success([_series("service-thanh-toan", "NaN")]))

    assert client.query(P95_LATENCY) == []


def test_bo_qua_series_thieu_label_service():
    """Không có label `service` thì không quy được về đâu, giữ lại chỉ tổ gán nhầm."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"result": [{"metric": {"job": "x"}, "value": [1785000000.0, "1.0"]}]},
            },
        )

    assert _client(handler).query(P95_LATENCY) == []


def test_prometheus_chet_thi_raise_chu_khong_tra_rong():
    """Ranh giới quan trọng nhất: không biết tình hình KHÁC biết là không có gì."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(PrometheusError, match="Không gọi được Prometheus"):
        _client(handler).query(P95_LATENCY)


def test_promql_sai_cu_phap_thi_raise():
    """Sai cú pháp là bug trong code mình, phải nổ to chứ không nuốt."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"status": "error", "errorType": "bad_data", "error": "invalid parameter"},
        )

    with pytest.raises(PrometheusError, match="HTTP 400"):
        _client(handler).query("histogram_quantile(")


def test_status_error_du_http_200_van_raise():
    """Prometheus có thể trả 200 kèm status=error — không được coi là thành công."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "error", "error": "query timed out"})

    with pytest.raises(PrometheusError, match="query timed out"):
        _client(handler).query(P95_LATENCY)


def test_query_range_boc_avg_over_time_quanh_cau_goc():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query"] = request.url.params["query"]
        return _success([_series("service-thanh-toan", "0.18")])

    samples = _client(handler).query_range("up", minutes=15)

    assert seen["query"] == "avg_over_time((up)[15m:1m])"
    assert samples == [MetricSample(service="service-thanh-toan", value=0.18)]
