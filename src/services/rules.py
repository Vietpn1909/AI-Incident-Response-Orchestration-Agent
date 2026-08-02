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

from datetime import UTC, datetime

from src.models.incident import IncidentSignal, MetricEvidence, Severity
from src.services import prometheus

# ---------------------------------------------------------------------------
# Ngưỡng — contract ①
# ---------------------------------------------------------------------------

#: p95 (giây) và tỷ lệ lỗi 5xx (0.0–1.0) cho từng mức, theo bảng contract ①.
P95_P1_SECONDS = 10.0
P95_P2_SECONDS = 2.0
P95_P3_SECONDS = 1.0

ERROR_RATE_P1 = 0.50
ERROR_RATE_P2 = 0.10
ERROR_RATE_P3 = 0.01

#: Tên cũ, giữ lại vì đã nằm trong `__all__`. Chúng là ngưỡng của **P2**, không
#: phải "ngưỡng" duy nhất — đặt tên như cũ dễ khiến người đọc tưởng chỉ có một.
P95_THRESHOLD_SECONDS = P95_P2_SECONDS
ERROR_RATE_THRESHOLD = ERROR_RATE_P2

#: Chỉ tính là incident khi vượt ngưỡng LIÊN TỤC ít nhất bấy nhiêu giây.
#: Thiếu quy tắc này thì một spike đơn lẻ lúc load test cũng mở incident.
SUSTAINED_SECONDS = 30.0

#: p95 gấp bấy nhiêu lần baseline thì tính là bất thường, dù chưa vượt ngưỡng cứng.
#:
#: Đây là đường vào của mức P4 ("lệch baseline nhưng chưa vượt ngưỡng cứng").
#: Không có nó thì P4 nằm trong bảng severity mà không có cách nào đạt tới.
#: Chọn 2.0 dựa trên số đo thật: lúc bình thường độ lệch dao động quanh 1.0x,
#: lúc nghẽn lên 10.9x — 2x là biên tách bạch hai trạng thái đó mà không bắt
#: nhầm dao động thường ngày. Xem spike/README.md.
BASELINE_DEVIATION_RATIO = 2.0

# Ngưỡng cho UC-3 (burst xác thực thất bại). Dùng SỐ TUYỆT ĐỐI request thất bại
# mỗi giây, không dùng tỷ lệ — xem docs/use-cases.md UC-3 để biết vì sao.
AUTH_FAILURE_P1 = 50.0  # nghi đang bị tấn công chủ động
AUTH_FAILURE_P2 = 10.0

#: Sàn của P3. use-cases.md ghi "lệch baseline nhưng dưới 10/giây" mà không cho
#: con số, nên chốt ở 1/giây: giữ liên tục 30 giây là 30 lần đăng nhập hỏng —
#: người dùng gõ nhầm mật khẩu không tạo ra hình thái đó.
AUTH_FAILURE_P3 = 1.0


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

    Rule thuần, KHÔNG dùng LLM — phân loại phải tất định để đo được độ chính
    xác trong `eval/`. Gọi hàm này hai lần với cùng đầu vào phải ra cùng kết quả.

    P4 là mức mặc định khi không ngưỡng cứng nào bị vượt. Chỗ quyết định "có
    đáng gọi là sự cố không" là `detect()`, không phải hàm này — tới đây thì đã
    biết là có bất thường rồi, chỉ còn xếp hạng.

    Raises:
        ValueError: khi `p95` hoặc `error_rate` là NaN. Không được lặng lẽ cho
            qua: `NaN > x` luôn False nên NaN sẽ tụt xuống P4 và một sự cố P1
            bị xếp nhầm thành nhẹ nhất mà không có dấu hiệu gì. Đã có 4 câu
            PromQL trả NaN một lần rồi, xem spike/README.md.
    """
    _reject_nan(p95=p95, error_rate=error_rate)

    if p95 > P95_P1_SECONDS or error_rate > ERROR_RATE_P1 or affected_service_count >= 2:
        return Severity.P1
    if p95 > P95_P2_SECONDS or error_rate > ERROR_RATE_P2:
        return Severity.P2
    if p95 > P95_P3_SECONDS or error_rate > ERROR_RATE_P3:
        return Severity.P3
    return Severity.P4


def detect(
    p95_now: float,
    p95_baseline: float,
    error_rate: float,
    pool_saturation: float,
    service: str,
    breached_for_seconds: float,
) -> IncidentSignal | None:
    """Quyết định có phải incident không. Trả `None` nếu bình thường.

    Ba cửa, phải qua hết mới tính là sự cố:

    1. **Đủ lâu** — `breached_for_seconds >= SUSTAINED_SECONDS`. Một spike đơn
       lẻ lúc load test không được mở incident.
    2. **Đủ bất thường** — vượt ngưỡng cứng thấp nhất (mức P3), *hoặc* lệch
       baseline từ `BASELINE_DEVIATION_RATIO` lần trở lên.
    3. Còn lại thì dựng `IncidentSignal` kèm bằng chứng số.

    ⚠️ **Cửa 2 lấy ngưỡng P3, không phải P2**, dù docstring gốc của stub ghi
    "p95 và error_rate đều dưới ngưỡng" với `P95_THRESHOLD_SECONDS = 2.0`.
    Chặn ở 2.0 thì mọi tín hiệu lọt qua đều đã từ P2 trở lên, và **hai mức P3
    với P4 trong bảng contract ① vĩnh viễn không đạt tới được** — cùng loại lỗi
    với bucket mặc định hôm 29/07, chỉ khác là nằm trong Python thay vì PromQL.

    Bằng chứng luôn gồm cả `pool_saturation`, kể cả khi pool không phải thứ
    kích hoạt: nó là thứ chứng minh nguyên nhân **gốc** (pool cạn), còn p95 chỉ
    chứng minh **triệu chứng** (chậm). Đề bài yêu cầu chẩn đoán có bằng chứng.

    Hàm này KHÔNG gọi Jira. Chống mở trùng là việc của node `open_war_room`,
    bằng `jira.find_open_incident(service)`.

    Args:
        p95_now: p95 hiện tại, giây.
        p95_baseline: mức p95 thường ngày, giây. 0 nghĩa là chưa có baseline —
            khi đó bỏ qua cửa lệch baseline, chỉ xét ngưỡng cứng.
        error_rate: tỷ lệ lỗi 5xx, 0.0–1.0.
        pool_saturation: mức dùng connection pool, 0.0–1.0.
        service: tên service, khớp label `service` trong Prometheus.
        breached_for_seconds: đã vượt ngưỡng liên tục bao lâu.

    Returns:
        `IncidentSignal` kèm ít nhất 3 bằng chứng, hoặc `None` nếu bình thường.

    Raises:
        ValueError: khi có đầu vào là NaN — xem `classify_severity`.
    """
    _reject_nan(
        p95_now=p95_now,
        p95_baseline=p95_baseline,
        error_rate=error_rate,
        pool_saturation=pool_saturation,
    )

    if breached_for_seconds < SUSTAINED_SECONDS:
        return None

    breached_hard = p95_now > P95_P3_SECONDS or error_rate > ERROR_RATE_P3
    deviated = p95_baseline > 0 and p95_now / p95_baseline >= BASELINE_DEVIATION_RATIO
    if not (breached_hard or deviated):
        return None

    severity = classify_severity(p95_now, error_rate)
    metric_name, metric_value, threshold = _primary_metric(p95_now, p95_baseline, error_rate, severity)

    return IncidentSignal(
        affected_service=service,
        severity=severity,
        detected_at=datetime.now(UTC),
        metric_name=metric_name,
        metric_value=metric_value,
        threshold=threshold,
        breached_for_seconds=breached_for_seconds,
        evidence=[
            MetricEvidence(
                name="http_request_duration_seconds p95",
                value=p95_now,
                baseline=p95_baseline or None,
                unit="s",
                promql=prometheus.P95_LATENCY,
            ),
            MetricEvidence(
                name="db_pool_connections_in_use / db_pool_size",
                value=pool_saturation,
                promql=prometheus.POOL_SATURATION_PEAK_5M,
            ),
            MetricEvidence(
                name="tỷ lệ lỗi 5xx",
                value=error_rate,
                promql=prometheus.ERROR_RATE,
            ),
        ],
    )


def classify_auth_burst(failures_per_second: float, breached_for_seconds: float) -> Severity | None:
    """Phân loại UC-3 — burst xác thực thất bại. Trả `None` nếu bình thường.

    Nhánh RIÊNG, không dùng `classify_severity()`, vì UC-3 có hình thái khác
    hẳn: hệ thống hoàn toàn khoẻ (latency bình thường, không lỗi 5xx, pool
    không cạn), chỉ hình thái truy cập là bất thường.

    Bằng chứng kèm theo phải dùng `prometheus.AUTH_FAILURE_RATE`, và giả thuyết
    phải nêu được đây là **vấn đề bảo mật**, không phải quá tải. Nếu Agent kết
    luận "service quá tải" thì SAI — xem docs/use-cases.md UC-3.

    Args:
        failures_per_second: số request `/login` trả 4xx mỗi giây.
        breached_for_seconds: đã ở mức đó liên tục bao lâu.

    Raises:
        ValueError: khi `failures_per_second` là NaN — xem `classify_severity`.
    """
    _reject_nan(failures_per_second=failures_per_second)

    if breached_for_seconds < SUSTAINED_SECONDS:
        return None
    if failures_per_second >= AUTH_FAILURE_P1:
        return Severity.P1
    if failures_per_second >= AUTH_FAILURE_P2:
        return Severity.P2
    if failures_per_second >= AUTH_FAILURE_P3:
        return Severity.P3
    return None


def is_spreading(signals: list[IncidentSignal], within_seconds: float = 60.0) -> bool:
    """Có dấu hiệu sự cố lan sang service khác không?

    True khi có **hai service khác nhau** được phát hiện cách nhau không quá
    `within_seconds`. Khi True, node `link_incidents` gọi `jira.link_issues()`
    để nối 2 incident.

    Hai tín hiệu của **cùng một service** không phải lan truyền — đó chỉ là
    cùng một sự cố được phát hiện hai lần, và nối chúng lại sẽ tạo ra liên kết
    rác trong war room.

    Ngưỡng 60s: trong test thật `service-dat-hang` suy giảm chậm hơn
    `service-thanh-toan` khoảng 30 giây, nên 60s là biên an toàn gấp đôi.
    """
    ordered = sorted(signals, key=lambda signal: signal.detected_at)
    for index, earlier in enumerate(ordered):
        for later in ordered[index + 1 :]:
            if earlier.affected_service == later.affected_service:
                continue
            if (later.detected_at - earlier.detected_at).total_seconds() <= within_seconds:
                return True
    return False


# ---------------------------------------------------------------------------
# Helper nội bộ
# ---------------------------------------------------------------------------


def _reject_nan(**values: float) -> None:
    """Chặn NaN ngay cửa vào rule engine.

    NaN không làm chương trình chết mà làm nó **trả lời sai một cách im lặng**:
    `NaN > x` và `NaN < x` đều là False, nên mọi so sánh ngưỡng rơi tọt qua và
    sự cố nặng bị xếp xuống mức nhẹ nhất. `PrometheusClient` đã lọc NaN, đây là
    lớp thứ hai cho trường hợp giá trị đến từ nguồn khác (test, node tự tính).
    """
    for name, value in values.items():
        if value != value:  # NaN
            raise ValueError(
                f"`{name}` là NaN — rule engine không so sánh được. Nguồn dữ liệu hỏng, đừng nuốt lỗi này."
            )


def _primary_metric(
    p95: float,
    p95_baseline: float,
    error_rate: float,
    severity: Severity,
) -> tuple[str, float, float]:
    """Chọn metric nào đại diện cho tín hiệu, và ngưỡng nào để hiển thị.

    `IncidentSignal` chỉ có chỗ cho **một** metric, dùng làm tiêu đề Jira issue.
    Chọn metric đã kích hoạt mức severity này, và báo ngưỡng **của chính mức
    đó** — báo ngưỡng P3 cho một sự cố P2 thì tiêu đề đọc rất khó hiểu.

    Trả về `(tên, giá trị, ngưỡng)`. Bằng chứng đầy đủ vẫn nằm ở `evidence`,
    không mất gì.
    """
    p95_by_severity = {
        Severity.P1: P95_P1_SECONDS,
        Severity.P2: P95_P2_SECONDS,
        Severity.P3: P95_P3_SECONDS,
    }
    error_by_severity = {
        Severity.P1: ERROR_RATE_P1,
        Severity.P2: ERROR_RATE_P2,
        Severity.P3: ERROR_RATE_P3,
    }

    p95_threshold = p95_by_severity.get(severity)
    if p95_threshold is not None and p95 > p95_threshold:
        return "http_request_duration_seconds p95", p95, p95_threshold

    error_threshold = error_by_severity.get(severity)
    if error_threshold is not None and error_rate > error_threshold:
        return "tỷ lệ lỗi 5xx", error_rate, error_threshold

    # P4: không ngưỡng cứng nào bị vượt, tín hiệu đến từ độ lệch baseline.
    return "http_request_duration_seconds p95", p95, p95_baseline * BASELINE_DEVIATION_RATIO


__all__ = [
    "AUTH_FAILURE_P1",
    "AUTH_FAILURE_P2",
    "AUTH_FAILURE_P3",
    "BASELINE_DEVIATION_RATIO",
    "ERROR_RATE_P1",
    "ERROR_RATE_P2",
    "ERROR_RATE_P3",
    "ERROR_RATE_THRESHOLD",
    "P95_P1_SECONDS",
    "P95_P2_SECONDS",
    "P95_P3_SECONDS",
    "P95_THRESHOLD_SECONDS",
    "SUSTAINED_SECONDS",
    "MetricEvidence",
    "classify_auth_burst",
    "classify_severity",
    "detect",
    "is_spreading",
]
