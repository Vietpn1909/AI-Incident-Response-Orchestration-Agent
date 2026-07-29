"""Rule engine — phát hiện vượt ngưỡng và phân loại severity.

CHỦ SỞ HỮU: Việt

Đây là chỗ quyết định "có phải sự cố không" và "nghiêm trọng mức nào". Chạy
TRƯỚC LLM, và sinh ra bằng chứng số mà LLM chỉ diễn giải lại.

**Nguyên tắc không được đảo:** rule engine tìm bằng chứng, LLM viết thành lời.
Đề bài yêu cầu "chẩn đoán có bằng chứng" — một kết luận không truy vết được về
số liệu cụ thể thì không được tính.

Ngưỡng dưới đây là [contract ①](../../docs/contracts/01-metrics.md), đã chốt.
"""

from __future__ import annotations

from src.models.incident import IncidentSignal, MetricEvidence, Severity

# ---------------------------------------------------------------------------
# Ngưỡng — contract ①
# ---------------------------------------------------------------------------

P95_THRESHOLD_SECONDS = 2.0
ERROR_RATE_THRESHOLD = 0.10

#: Chỉ tính là incident khi vượt ngưỡng LIÊN TỤC ít nhất bấy nhiêu giây.
#: Thiếu quy tắc này thì một spike đơn lẻ lúc load test cũng mở incident.
SUSTAINED_SECONDS = 30.0


def classify_severity(
    p95: float,
    error_rate: float,
    affected_service_count: int = 1,
) -> Severity:
    """Phân loại P1–P4 theo contract ①.

    | Severity | Điều kiện |
    |---|---|
    | P1 | p95 > 10s **hoặc** lỗi > 50% **hoặc** ≥ 2 service bị ảnh hưởng |
    | P2 | p95 > 2s hoặc lỗi > 10% |
    | P3 | p95 > 1s hoặc lỗi > 1% |
    | P4 | lệch baseline nhưng chưa vượt ngưỡng cứng |

    TODO(Việt): cài đặt bảng trên. Đây là rule thuần, KHÔNG dùng LLM —
    phân loại phải tất định để đo được độ chính xác trong `eval/`.
    """
    raise NotImplementedError("TODO(Việt): xem docstring")


def detect(
    p95_now: float,
    p95_baseline: float,
    error_rate: float,
    pool_saturation: float,
    service: str,
    breached_for_seconds: float,
) -> IncidentSignal | None:
    """Quyết định có phải incident không. Trả `None` nếu bình thường.

    TODO(Việt):
      1. Nếu `breached_for_seconds < SUSTAINED_SECONDS` → trả None
         (chưa đủ lâu, có thể chỉ là spike)
      2. Nếu p95 và error_rate đều dưới ngưỡng → trả None
      3. Ngược lại dựng `IncidentSignal`, và **bắt buộc kèm evidence**:
             MetricEvidence(name="http_request_duration_seconds p95",
                            value=p95_now, baseline=p95_baseline, unit="s",
                            promql=prometheus.P95_LATENCY)
         Thêm evidence cho pool_saturation — đây là thứ chứng minh nguyên
         nhân GỐC (pool cạn), không chỉ chứng minh triệu chứng (chậm).
      4. `severity=classify_severity(...)`

    Lưu ý: hàm này KHÔNG gọi Jira. Việc chống mở trùng do node
    `open_war_room` làm, bằng `jira.find_open_incident(service)`.

    Xong là thế nào: test với p95=5.1, baseline=0.2, error=0.12,
    pool=1.0, breached=45 → trả IncidentSignal severity P2, có ≥2 evidence.
    """
    raise NotImplementedError("TODO(Việt): xem docstring")


def is_spreading(signals: list[IncidentSignal], within_seconds: float = 60.0) -> bool:
    """Có dấu hiệu sự cố lan sang service khác không?

    TODO(Việt): trả True khi có ≥2 service bị ảnh hưởng và thời điểm phát hiện
    cách nhau dưới `within_seconds`. Khi True, node `link_incidents` gọi
    `jira.link_issues()` để nối 2 incident.

    Gợi ý về ngưỡng: trong test thật, `service-dat-hang` suy giảm chậm hơn
    `service-thanh-toan` khoảng 30 giây — 60s là biên an toàn.
    """
    raise NotImplementedError("TODO(Việt): xem docstring")


__all__ = [
    "ERROR_RATE_THRESHOLD",
    "P95_THRESHOLD_SECONDS",
    "SUSTAINED_SECONDS",
    "MetricEvidence",
    "classify_severity",
    "detect",
    "is_spreading",
]
