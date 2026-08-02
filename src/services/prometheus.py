"""Client query Prometheus — nguồn tín hiệu phát hiện sự cố.

CHỦ SỞ HỮU: Việt

Các câu PromQL dưới đây là [contract ①](../../docs/contracts/01-metrics.md), đã
chốt với Trung và **đã được Việt verify trên Prometheus thật** (2026-07-29, xem
[spike/README.md](../../spike/README.md)). Bản này đã sửa 4 lỗi Việt tìm ra.

**Đừng đổi tên metric hay label** — Trung expose đúng những tên này, lệch một
chữ là Prometheus trả kết quả rỗng chứ không báo lỗi, và Agent im lặng không
phát hiện gì.

`PrometheusClient` đã cài đặt xong (2026-08-01), verify trên Prometheus thật.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PromQL — contract ①, đã chốt. Dùng nguyên văn.
# ---------------------------------------------------------------------------

# ⚠️ Mọi câu query đều lọc `handler!="/metrics"`. Prometheus tự scrape endpoint
# đó mỗi 5s và request rất nhanh, không lọc thì nó kéo avg latency sai 40 lần
# lúc rảnh. Việt đo được và ghi ở spike/README.md.

# ⚠️ NaN — đọc trước khi sửa bất kỳ câu nào ở dưới.
#
# Không có request nào trong cửa sổ `[1m]` thì `rate` = 0, và mọi câu có phép
# chia thành 0/0 = `NaN`. Prometheus không báo lỗi, query vẫn "chạy", vẫn trả
# ra một con số.
#
# NaN nguy hiểm hơn kết quả rỗng vì nó hỏng im lặng:
#   - `NaN > x` VÀ `NaN < x` đều là False, nên mọi so sánh ngưỡng rơi tọt qua
#     → Agent bỏ lọt sự cố mà không có dấu hiệu gì
#   - `MetricEvidence.deviation_ratio` thành NaN
#   - Pydantic serialize NaN thành `null`, nên bằng chứng số biến mất khỏi
#     war-room view của Long mà không báo gì
#
# Vì vậy mọi câu có phép chia đều gắn `and on(service) (_HAS_TRAFFIC)`. Vế này
# bỏ hẳn series khi service không có request, nên câu trả **rỗng** thay vì NaN
# — và rỗng là trạng thái duy nhất `PrometheusClient.query()` phải xử lý.
#
# Đo được 2026-07-30 trên Prometheus thật, xem spike/README.md.

#: Điều kiện "service có request trong phút vừa rồi".
#:
#: Chỉ dùng làm bộ lọc chống NaN, không dùng trực tiếp làm tín hiệu.
_HAS_TRAFFIC = """
sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m])) > 0
"""

_P95_LATENCY_RAW = """
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket{handler!="/metrics"}[1m])) by (le, service)
)
"""

#: p95 latency theo service — tín hiệu chính để phát hiện sự cố.
P95_LATENCY = f"""
({_P95_LATENCY_RAW})
and on(service) ({_HAS_TRAFFIC})
"""

#: Tỷ lệ lỗi 5xx theo service (0.0 – 1.0).
#:
#: Vế `or ... * 0` là cố ý: không có vế đó thì khi service khoẻ, không series
#: nào khớp `status=~"5.."` nên tử số rỗng và cả phép chia trả RỖNG — Agent
#: không phân biệt được "không có lỗi" với "mất metric / service chết", hai
#: tình huống cần xử lý ngược nhau.
#:
#: Vế `or ... * 0` xử lý trường hợp rỗng, vế `and on(service)` xử lý trường hợp
#: NaN. Cần cả hai, chúng không thay được nhau.
_ERROR_RATE_RAW = """
(
  sum by (service) (rate(http_requests_total{handler!="/metrics", status=~"5.."}[1m]))
  or
  sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m])) * 0
)
/ sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m]))
"""

ERROR_RATE = f"""
({_ERROR_RATE_RAW})
and on(service) ({_HAS_TRAFFIC})
"""

#: Mức sử dụng connection pool (0.0 – 1.0) — bằng chứng cho nguyên nhân gốc.
POOL_SATURATION = "db_pool_connections_in_use / db_pool_size"

#: Đỉnh mức dùng pool trong 5 phút qua.
#:
#: Dùng bản này khi lấy làm bằng chứng cho `Hypothesis`, KHÔNG dùng
#: `POOL_SATURATION`: gauge là giá trị tức thời, query instant lúc tải vừa dứt
#: trả 0 dù ngay trước đó đã cạn kiệt — bằng chứng sẽ nói ngược sự thật.
POOL_SATURATION_PEAK_5M = f"max_over_time(({POOL_SATURATION})[5m:5s])"

#: Phân vị dùng làm mức nền. Xem giải thích ở `P95_BASELINE_30M`.
_BASELINE_QUANTILE = 0.1

#: Mức p95 "thường ngày" trong 30 phút qua — dùng làm baseline để so lệch.
#:
#: ⚠️ KHÔNG dùng `avg_over_time` ở đây, dù tên gọi "baseline" nghe như trung
#: bình. Cửa sổ 30 phút **bao gồm cả khoảng thời gian đang xảy ra sự cố**, nên
#: trung bình bị chính sự cố kéo lên: sự cố càng kéo dài, baseline càng cao và
#: độ lệch càng teo — tức bằng chứng yếu dần đúng lúc sự cố nghiêm trọng nhất.
#:
#: Đo được trên Prometheus thật (2026-07-30), p95 giữ nguyên 1.95s suốt:
#:
#:     thời điểm      avg_over_time   lệch     quantile 0.1   lệch
#:     bình thường    0.181 s         1.0x     0.181 s        1.0x
#:     +60s           0.531 s         3.7x     0.179 s       10.9x
#:     +170s          0.936 s         2.1x     0.180 s       10.9x
#:
#: Phân vị thấp bỏ qua phần đuôi do sự cố tạo ra, nên nó giữ đúng nghĩa "mức
#: thường ngày". Chọn 0.1 thay vì trung vị 0.5 vì cửa sổ là 30 phút: trung vị
#: bị nhiễm khi sự cố chiếm quá nửa cửa sổ (~15 phút), còn 0.1 chịu được tới
#: ~27 phút. Kịch bản demo có bước chờ người duyệt trên Jira, thời gian chờ đó
#: không đoán trước được, nên chọn biên an toàn rộng hơn.
#:
#: Kế thừa bộ lọc chống NaN từ `P95_LATENCY`, nên chỉ tính trên những phút thực
#: sự có request.
#:
#: Vẫn còn một ràng buộc kịch bản, không phải lỗi code: baseline cần có traffic
#: nền TRƯỚC lúc tăng tải. Chạy load test từ trạng thái im lìm thì không có
#: "mức thường ngày" nào để so, dù dùng phân vị hay trung bình.
P95_BASELINE_30M = f"quantile_over_time({_BASELINE_QUANTILE}, ({P95_LATENCY})[30m:1m])"

#: Số request xác thực thất bại mỗi giây — tín hiệu của UC-3 (burst tấn công).
#:
#: ⚠️ `ERROR_RATE` KHÔNG bắt được UC-3 vì nó chỉ khớp `status=~"5.."`, còn 401
#: là 4xx. Đây là tín hiệu riêng, và severity của UC-3 dựa trên **số lượng
#: tuyệt đối** chứ không phải tỷ lệ — nếu kẻ tấn công là nguồn traffic duy nhất
#: thì tỷ lệ lỗi là 100% ngay từ request đầu, chưa nói được gì về mức nghiêm
#: trọng. Xem docs/use-cases.md UC-3.
AUTH_FAILURE_RATE = """
sum by (service) (rate(http_requests_total{handler="/login", status=~"4.."}[1m]))
"""

_AVG_LATENCY_RAW = """
sum(rate(http_request_duration_seconds_sum{handler!="/metrics"}[1m])) by (service)
  / sum(rate(http_request_duration_seconds_count{handler!="/metrics"}[1m])) by (service)
"""

#: avg latency — dùng để đối chiếu, không dùng làm ngưỡng (p95 nhạy hơn).
AVG_LATENCY = f"""
({_AVG_LATENCY_RAW})
and on(service) ({_HAS_TRAFFIC})
"""


class PrometheusError(RuntimeError):
    """Không lấy được dữ liệu từ Prometheus.

    Cố ý KHÔNG dùng cho trường hợp "query chạy được nhưng không có series nào" —
    đó là trạng thái bình thường (service chưa có request), và `query()` trả
    danh sách rỗng cho nó.

    Ném lỗi ở đây nghĩa là *không biết* tình hình service ra sao: Prometheus
    chết, sai địa chỉ, hoặc câu PromQL sai cú pháp. Nuốt lỗi và trả rỗng ở
    những tình huống đó là nguy hiểm — Agent sẽ hiểu nhầm thành "mọi thứ bình
    thường" đúng lúc nó mù hoàn toàn.
    """


@dataclass
class MetricSample:
    """Một giá trị metric đọc về, cho một service."""

    service: str
    value: float


class PrometheusClient:
    """Đọc metric từ Prometheus HTTP API.

    Không dùng Alertmanager — logic ngưỡng nằm trong `rules.py`.
    Xem [ADR-0002](../../docs/adr/0002-khong-dung-alertmanager.md).

    Đồng bộ chứ không async: mỗi vòng `detect` chỉ gọi vài query, và giữ nó
    đồng bộ thì `rules.py` cùng test không phải kéo theo event loop.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:9090",
        timeout: float = 10.0,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """
        Args:
            base_url: Địa chỉ Prometheus.
            timeout: Giây, cho mỗi request.
            transport: Chỉ dùng trong test — truyền `httpx.MockTransport` để
                chạy được mà không cần Prometheus thật. Bỏ trống khi chạy thật.
        """
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self._base, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PrometheusClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def query(self, promql: str) -> list[MetricSample]:
        """Chạy một câu PromQL tức thời, trả giá trị theo từng service.

        Returns:
            Một `MetricSample` cho mỗi service có dữ liệu. **Danh sách rỗng
            không phải lỗi** — nghĩa là chưa có dữ liệu (service không nhận
            request nào), hoặc, nguy hiểm hơn, tên metric bị lệch so với thứ
            Trung expose. Cả hai đều được log ở mức warning vì Prometheus không
            phân biệt giúp mình được.

        Raises:
            PrometheusError: khi không gọi được Prometheus, hoặc Prometheus từ
                chối câu query (sai cú pháp PromQL). Đây là "không biết tình
                hình", khác hẳn "biết là không có dữ liệu".

        Ví dụ:
            >>> client = PrometheusClient()
            >>> client.query(P95_LATENCY)
            [MetricSample(service='service-thanh-toan', value=1.94)]
        """
        payload = self._get("/api/v1/query", {"query": promql})
        return self._parse(payload, promql)

    def query_range(self, promql: str, minutes: int = 30) -> list[MetricSample]:
        """Giá trị trung bình của `promql` trong `minutes` phút qua.

        Bọc câu query trong `avg_over_time(...)` rồi gọi `query()`, thay vì gọi
        `/api/v1/query_range` — endpoint đó trả về cả chuỗi thời gian mà chỗ
        gọi lại chỉ cần một con số, nên sẽ phải tự tính trung bình lần nữa.

        ⚠️ Không dùng hàm này để tính baseline. Baseline đã có sẵn ở
        `P95_BASELINE_30M`, và nó dùng **phân vị** chứ không phải trung bình —
        trung bình bị chính sự cố kéo lên, xem chú thích ở hằng đó.
        """
        return self.query(f"avg_over_time(({promql})[{minutes}m:1m])")

    # ---------------------------------------------------------------- helpers

    def _get(self, path: str, params: dict[str, str]) -> dict:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as error:
            raise PrometheusError(f"Không gọi được Prometheus tại {self._base}: {error}") from error

        if response.status_code >= 400:
            # Prometheus trả 400 kèm mô tả lỗi cú pháp trong body, giữ lại để
            # khỏi phải mò.
            raise PrometheusError(f"GET {path} → HTTP {response.status_code}: {response.text[:400]}")

        payload = response.json()
        if payload.get("status") != "success":
            raise PrometheusError(f"Prometheus từ chối query: {payload.get('error', payload)}")
        return payload

    @staticmethod
    def _parse(payload: dict, promql: str) -> list[MetricSample]:
        result = payload["data"]["result"]
        if not result:
            logger.warning(
                "PromQL không trả series nào — service chưa có request, hoặc tên metric bị lệch. Query: %s",
                _one_line(promql),
            )
            return []

        samples: list[MetricSample] = []
        for series in result:
            service = series["metric"].get("service")
            if not service:
                # Mọi câu trong file này đều gom `by (service)`. Thiếu label này
                # thì không quy được về service nào, giữ lại chỉ tổ gán nhầm.
                logger.warning("Bỏ qua series không có label `service`: %s", series["metric"])
                continue

            value = float(series["value"][1])
            if value != value:  # NaN
                # Các câu trong file này đã chặn NaN bằng `_HAS_TRAFFIC`. Lọt
                # tới đây nghĩa là có câu chưa được chặn — bỏ mẫu đi, vì NaN
                # làm mọi so sánh ngưỡng trả False mà không báo gì.
                logger.warning(
                    "Bỏ qua giá trị NaN của %s — query thiếu bộ lọc `_HAS_TRAFFIC`? Query: %s",
                    service,
                    _one_line(promql),
                )
                continue

            samples.append(MetricSample(service=service, value=value))
        return samples


def _one_line(promql: str) -> str:
    """Ép câu PromQL nhiều dòng về một dòng để log đọc được."""
    return " ".join(promql.split())
