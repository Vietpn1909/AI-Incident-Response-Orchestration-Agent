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

# Ngưỡng cho UC-3 (burst xác thực thất bại). Dùng SỐ TUYỆT ĐỐI request thất bại
# mỗi giây, không dùng tỷ lệ — xem docs/use-cases.md UC-3 để biết vì sao.
AUTH_FAILURE_P1 = 50.0  # nghi đang bị tấn công chủ động
AUTH_FAILURE_P2 = 10.0


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


def classify_auth_burst(failures_per_second: float, breached_for_seconds: float) -> Severity | None:
    """Phân loại UC-3 — burst xác thực thất bại. Trả `None` nếu bình thường.

    Nhánh RIÊNG, không dùng `classify_severity()`, vì UC-3 có hình thái khác
    hẳn: hệ thống hoàn toàn khoẻ (latency bình thường, không lỗi 5xx, pool
    không cạn), chỉ hình thái truy cập là bất thường.

    TODO(Việt):
      - `breached_for_seconds < SUSTAINED_SECONDS` → None
      - `>= AUTH_FAILURE_P1` → P1  (nghi tấn công chủ động)
      - `>= AUTH_FAILURE_P2` → P2
      - trên baseline nhưng dưới P2 → P3
      - còn lại → None

    Bằng chứng kèm theo phải dùng `prometheus.AUTH_FAILURE_RATE`, và giả thuyết
    phải nêu được đây là **vấn đề bảo mật**, không phải quá tải. Nếu Agent kết
    luận "service quá tải" thì SAI — xem docs/use-cases.md UC-3.
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
    "AUTH_FAILURE_P1",
    "AUTH_FAILURE_P2",
    "ERROR_RATE_THRESHOLD",
    "P95_THRESHOLD_SECONDS",
    "SUSTAINED_SECONDS",
    "MetricEvidence",
    "classify_auth_burst",
    "classify_severity",
    "detect",
    "is_spreading",
]
