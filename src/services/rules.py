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

from src.models.incident import DeployRecord, Hypothesis, IncidentSignal, MetricEvidence, Severity
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

#: Số tài khoản khác nhau bị thử — ngưỡng nhận ra **dò tài khoản hàng loạt**,
#: bất kể tốc độ.
#:
#: ## Vì sao cần một ngưỡng KHÔNG theo tốc độ
#:
#: Ba ngưỡng trên đều là "bao nhiêu lần mỗi giây". Ngưỡng tức thời **luôn thua kẻ
#: biết ngưỡng**: chỉ cần giữ dưới nó là đi qua, không giới hạn thời gian.
#:
#: Đo trên case I19: `0,95/s` — ngay dưới `AUTH_FAILURE_P3 = 1.0` — nhưng duy trì
#: **24 giờ**, thành `0,95 × 86.400 = 82.080 lần thử`, nhắm **5.000 tài khoản** từ
#: 200 IP luân phiên. Bộ luật thấy "dưới 1 lần mỗi giây, bình thường".
#:
#: ## Vì sao đo DIỆN RỘNG thì không né được
#:
#: Credential stuffing được định nghĩa bằng **bề rộng**, không phải tốc độ: mục
#: đích của nó là thử nhiều tài khoản. Hạ tốc độ thì vẫn phải thử đủ số tài khoản,
#: nếu không thì tấn công vô nghĩa. Nên đây là thứ kẻ tấn công **không thể giảm**
#: mà vẫn đạt mục đích — khác hẳn tốc độ.
#:
#: ## Vì sao chọn 10
#:
#: Người quên mật khẩu thì thử lại **tài khoản của chính mình**. Một IP công ty
#: dùng chung cũng chỉ vài tài khoản. Hàng chục tài khoản khác nhau cùng đăng nhập
#: thất bại không còn là lỗi người dùng, mà là dò tài khoản.
#:
#: Đối chiếu với dữ liệu để chắc con số không vô lý: case bình thường cao nhất là
#: 6 tài khoản (N05), case tấn công thấp nhất là 12 (I12). Mốc 10 nằm giữa, nhưng
#: lý do chọn nó là lập luận ở trên chứ không phải khoảng trống trong dữ liệu —
#: chọn theo khoảng trống thì thêm một case mới là phải chọn lại.
AUTH_UNIQUE_ACCOUNTS_ATTACK = 10.0

# Ngưỡng cho UC-2 (service chết vì OOM rồi restart liên tục).

#: Số lần restart trong 10 phút để tính là crash loop.
#:
#: Một lần trong 10 phút nhiều khả năng là **deploy bình thường**, không phải sự
#: cố — báo động ở mức đó thì mỗi lần đội deploy Agent lại mở một incident. Hai
#: lần trở lên mới là hình thái "chết rồi sống lại rồi chết tiếp".
CRASHLOOP_RESTARTS = 2.0

# Ngưỡng dùng khi chẩn đoán (`correlate_deploy`, `build_hypothesis`).

#: Deploy xa hơn ngần này phút thì không coi là trùng thời gian với sự cố.
#:
#: 15 phút vì `demo/seed.py` cắm dòng "nghi phạm" ở mốc 4 phút, và một sự cố do
#: deploy gây ra thường lộ trong vòng vài phút. Nới rộng ra thì mọi sự cố đều
#: "có deploy ngay trước", và bằng chứng đó mất giá trị.
DEPLOY_WINDOW_MINUTES = 15.0

#: Mức dùng pool từ đây trở lên thì coi là cạn kiệt.
#:
#: Không đòi đúng 1.0: gauge được scrape mỗi 5s nên có thể bắt đúng nhịp một
#: connection vừa được trả về.
POOL_EXHAUSTED_RATIO = 0.95

#: p95 gấp bấy nhiêu lần baseline thì tính là bằng chứng mạnh cho chẩn đoán.
#:
#: Cao hơn `BASELINE_DEVIATION_RATIO` (2.0) dùng để *phát hiện*: phát hiện thì
#: nên nhạy, còn tính điểm tin cậy thì nên chặt.
BASELINE_DEVIATION_STRONG = 3.0

#: Đỉnh bộ nhớ đạt từ ngần này phần trần container thì coi là chạm giới hạn.
#:
#: Không đòi đúng 1.0: Docker OOM-kill process **trước** khi Prometheus kịp
#: scrape đúng mốc đỉnh, nên số ghi lại **luôn thấp hơn** trần thật. Hai lần đo
#: độc lập cho thấy sai số này không nhỏ và không ổn định:
#:
#:     máy Đức, 05/08   đỉnh 127 MB / 128 MB = 0.99
#:     máy Việt, 05/08  đỉnh 114 MB / 128 MB = 0.89
#:
#: Cùng một container, cùng cách ép OOM. Chênh lệch đến từ việc bắt trúng hay
#: trượt nhịp scrape 5s. Chốt 0.85 để chịu được cả hai; đặt 0.90 thì lần đo thứ
#: hai đã trượt.
MEMORY_NEAR_LIMIT_RATIO = 0.85

# Hình dạng nguồn của credential-stuffing (UC-3).

#: Số tài khoản khác nhau bị thử trong 1 phút để coi là quét danh sách.
#:
#: Một người quên mật khẩu thử lại tài khoản **của chính họ**, nên số này quanh
#: 1. Vượt 10 nghĩa là ai đó đang duyệt qua một danh sách. Đo trên tấn công giả
#: lập: 100 tài khoản.
STUFFING_MIN_ACCOUNTS = 10.0

#: Phần request đến từ IP nguồn lớn nhất để coi là tập trung.
#:
#: Traffic thật của người dùng trải ra nhiều IP; một nguồn chiếm quá nửa là dấu
#: hiệu tự động hoá. Đo trên tấn công giả lập: 1.0 — toàn bộ từ một nguồn.
STUFFING_TOP_SOURCE_RATIO = 0.5

#: Số điểm dữ liệu tối thiểu trong cửa sổ 30 phút để baseline đáng tin.
#:
#: Cửa sổ `[30m:1m]` mong đợi 30 điểm. Đòi đủ 30 thì Agent mù suốt nửa tiếng đầu
#: mỗi lần dựng lại stack — quá chặt cho một buổi demo. Đòi 20 (khoảng 2/3) là
#: đủ để phân vị có nghĩa mà vẫn dùng được sau ~20 phút.
#:
#: Vì sao cần: Prometheus không có volume nên `docker compose down` là mất sạch
#: lịch sử. Lúc mới chạy 2 phút, baseline tính trên 29 điểm / ~360 — Trung gặp
#: báo nhầm lúc khởi động lạnh đúng vì thế. `p95_baseline > 0` chỉ nói "có số",
#: không nói "số đó đáng tin".
BASELINE_MIN_SAMPLES = 20.0


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


def _tin_hieu_mat_do_luong(
    service: str, p95_baseline: float, breached_for_seconds: float
) -> IncidentSignal:
    """Dựng tín hiệu cho trường hợp **mất tín hiệu đo lường**.

    Mức **P1** vì đây là tình huống nguy hiểm nhất trong cả bộ: Agent không biết
    chuyện gì đang xảy ra, và cái nó không biết thì nó không báo. Sự cố khác thì
    người trực còn thấy con số xấu; ở đây họ thấy một bảng điều khiển toàn màu
    xanh.

    Câu kết luận nói ra **hai khả năng** thay vì chọn một, vì số đo không đủ để
    phân biệt: exporter chết, hay service ngừng phục vụ. Nêu đúng một nguyên nhân
    ở đây là bịa — cùng nguyên tắc với cửa chặn "nêu nguyên nhân nào thì phải có
    bằng chứng cho nguyên nhân đó" ở `hypothesize.py`.
    """
    return IncidentSignal(
        affected_service=service,
        severity=Severity.P1,
        detected_at=datetime.now(UTC),
        metric_name="http_request_duration_seconds p95 (mất tín hiệu)",
        metric_value=0.0,
        threshold=0.0,
        breached_for_seconds=breached_for_seconds,
        evidence=[
            MetricEvidence(
                name="http_request_duration_seconds p95",
                value=0.0,
                baseline=p95_baseline,
                unit="s",
                promql=prometheus.P95_LATENCY,
            ),
            MetricEvidence(
                name="up (service còn sống không)",
                value=0.0,
                promql=prometheus.SERVICE_UP,
            ),
        ],
    )


def detect(
    p95_now: float,
    p95_baseline: float,
    error_rate: float,
    pool_saturation: float,
    service: str,
    breached_for_seconds: float,
    baseline_samples: float = 0.0,
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
        baseline_samples: số điểm dữ liệu thật trong cửa sổ 30 phút. Dưới
            `BASELINE_MIN_SAMPLES` thì baseline bị coi là chưa đáng tin và cửa
            lệch baseline bị bỏ qua — ngưỡng cứng vẫn xét bình thường.
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

    # ── Đường phát hiện thứ tư: MẤT TÍN HIỆU ─────────────────────────────
    #
    # Một service đang phục vụ request thì p95 **không thể bằng 0 tuyệt đối**.
    # Đọc được đúng 0 mà lại có baseline đáng tin nghĩa là: hoặc service ngừng
    # phục vụ, hoặc đường đo đã hỏng. Cả hai đều là sự cố — không cái nào là
    # "khoẻ".
    #
    # Vì sao phải có đường riêng cho nó: cửa 2 chỉ hỏi "có vượt ngưỡng không" và
    # "có lệch baseline không". Với p95 = 0 thì cả hai đều **không**:
    #   - 0 > 1.0s  → False
    #   - 0 / 0.2   → 0, còn xa 2.0 lần
    # Nên số đo về 0 lọt qua như thể mọi thứ tốt đẹp. Bộ luật không chỉ sai — nó
    # sai **theo hướng an tâm**, tức im lặng trong lúc hệ thống đang cháy.
    #
    # Đo trên case I23 (Prometheus exporter crash, mọi metric trả 0): luật cũ
    # phân loại là bình thường. Đây là kiểu bỏ lọt tệ nhất trong cả bộ đo, vì
    # người trực không có tín hiệu nào để mà nghi.
    #
    # ⚠️ Bắt buộc kèm điều kiện baseline đáng tin. Thiếu nó thì mọi service chưa
    # có lưu lượng — lúc mới `docker compose up`, hoặc service nội bộ rảnh rỗi —
    # đều bị mở incident. Có baseline 20+ mẫu nghĩa là "trước đây nó CÓ phục vụ",
    # nên việc giờ đọc ra 0 là một thay đổi, không phải trạng thái nghỉ.
    mat_tin_hieu = (
        p95_now == 0.0
        and p95_baseline > 0
        and baseline_samples >= BASELINE_MIN_SAMPLES
    )
    if mat_tin_hieu:
        return _tin_hieu_mat_do_luong(service, p95_baseline, breached_for_seconds)

    breached_hard = p95_now > P95_P3_SECONDS or error_rate > ERROR_RATE_P3
    # "Có baseline" phải nghĩa là ĐỦ ĐIỂM ĐỂ TIN, không chỉ là "khác 0".
    #
    # Prometheus không có volume nên `docker compose down` là mất sạch lịch sử.
    # Lúc mới chạy 2 phút, `quantile_over_time(...[30m:1m])` vẫn trả về một con
    # số — tính trên 29 điểm / ~360. Chia cho nó là báo nhầm, và Trung gặp đúng
    # chuyện đó lúc khởi động lạnh.
    #
    # Chặn bằng số điểm là chặn theo CẤU TRÚC: không phụ thuộc ai nhớ chạy
    # warm-up trước khi demo.
    baseline_dung_duoc = p95_baseline > 0 and baseline_samples >= BASELINE_MIN_SAMPLES
    deviated = baseline_dung_duoc and p95_now / p95_baseline >= BASELINE_DEVIATION_RATIO
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


def detect_auth_burst(
    failures_per_second: float,
    breached_for_seconds: float,
    service: str,
    unique_source_ips: float = 0.0,
    unique_accounts: float = 0.0,
    accounts_sustained_seconds: float | None = None,
    top_source_ratio: float = 0.0,
) -> IncidentSignal | None:
    """Dựng tín hiệu UC-3 kèm bằng chứng. `None` nếu bình thường.

    Đối xứng với `detect()` và `detect_crashloop()`: `classify_auth_burst()`
    quyết định mức, hàm này gói lại thành `IncidentSignal`.

    Tên metric ghi rõ **"mỗi giây"** chứ không phải tỷ lệ phần trăm. Đây không
    phải chuyện chữ nghĩa: nếu kẻ tấn công là nguồn traffic duy nhất thì tỷ lệ
    lỗi là 100% ngay từ request đầu, chưa nói được gì về mức nghiêm trọng — nên
    UC-3 đo số tuyệt đối. Người trực đọc war room phải thấy ngay điều đó.

    ⚠️ **Ba bằng chứng hình thái thêm ngày 06/08.** Trước đó tín hiệu chỉ có
    đúng một con số (tỷ lệ thất bại), và số đó **không phân biệt được** tấn công
    với quá tải — cả hai đều làm nhiều lượt đăng nhập hỏng. Đo thật 05/08: LLM
    nhìn một bằng chứng duy nhất rồi viết "connection pool cạn" cho một vụ
    credential-stuffing, đúng cái `use-cases.md` gọi là chẩn đoán SAI.

    Hình dạng nguồn mới là thứ phân biệt:

    | | nguồn | tài khoản | nguồn lớn nhất |
    |---|---|---|---|
    | Credential-stuffing | ít | **nhiều** | gần 1.0 |
    | Người dùng gõ nhầm | nhiều | ít | thấp |
    | Service lỗi | nhiều | nhiều | thấp |

    Args:
        unique_source_ips: Số IP nguồn khác nhau trong 1 phút.
        unique_accounts: Số tài khoản khác nhau bị thử trong 1 phút.
        top_source_ratio: Phần request đến từ IP nguồn lớn nhất, 0–1.
    """
    _reject_nan(
        unique_source_ips=unique_source_ips,
        unique_accounts=unique_accounts,
        top_source_ratio=top_source_ratio,
    )

    severity = classify_auth_burst(failures_per_second, breached_for_seconds)

    # ── Đường thứ hai: DIỆN RỘNG, không theo tốc độ ──────────────────────────
    #
    # Ngưỡng tốc độ luôn thua kẻ biết ngưỡng. Case I19 giữ `0,95/s` — ngay dưới
    # `AUTH_FAILURE_P3` — suốt 24 giờ, thử 5.000 tài khoản từ 200 IP luân phiên.
    # Bộ luật thấy "dưới 1 lần mỗi giây, bình thường".
    #
    # Diện rộng thì không né được: hạ tốc độ vẫn phải thử đủ số tài khoản, nếu
    # không thì tấn công vô nghĩa.
    #
    # Vẫn phải qua cửa "đủ lâu" — một lúc đông người gõ sai cùng lúc không tính.
    # ⚠️ Đo độ bền của DIỆN RỘNG, không dùng `breached_for_seconds`.
    #
    # `breached_for_seconds` do node `detect` tính bằng `_sustained()` với sàn
    # `AUTH_FAILURE_P3`, tức chính ngưỡng tốc độ. Nên với I19 (0,95/s, dưới sàn
    # 1,0) nó bằng **0**: kẻ né ngưỡng thì theo định nghĩa "chưa từng bất thường",
    # và cửa "đủ lâu" không bao giờ mở.
    #
    # Vòng lặp đó là lý do đường diện rộng phải có thước đo thời gian RIÊNG: đo
    # xem số tài khoản đã ở mức tấn công bao lâu, chứ không đo tốc độ.
    ben_bao_lau = (
        accounts_sustained_seconds
        if accounts_sustained_seconds is not None
        else breached_for_seconds
    )
    dien_rong = (
        unique_accounts >= AUTH_UNIQUE_ACCOUNTS_ATTACK
        and ben_bao_lau >= SUSTAINED_SECONDS
    )
    if severity is None and dien_rong:
        # Mức P2: đã chắc là dò tài khoản, nhưng tốc độ thấp nên thiệt hại tức
        # thời chưa bằng burst P1. Không hạ xuống P3 vì bề rộng 10+ tài khoản là
        # bằng chứng mạnh hơn một tín hiệu "hơi bất thường".
        severity = Severity.P2

    if severity is None:
        return None

    threshold = {
        Severity.P1: AUTH_FAILURE_P1,
        Severity.P2: AUTH_FAILURE_P2,
        Severity.P3: AUTH_FAILURE_P3,
    }[severity]

    return IncidentSignal(
        affected_service=service,
        severity=severity,
        detected_at=datetime.now(UTC),
        metric_name="số request /login thất bại mỗi giây",
        metric_value=failures_per_second,
        threshold=threshold,
        breached_for_seconds=breached_for_seconds,
        evidence=[
            MetricEvidence(
                name="số request /login thất bại mỗi giây",
                value=failures_per_second,
                promql=prometheus.AUTH_FAILURE_RATE,
            ),
            MetricEvidence(
                name="số IP nguồn khác nhau (1 phút)",
                value=unique_source_ips,
                promql=prometheus.AUTH_UNIQUE_SOURCE_IPS,
            ),
            MetricEvidence(
                name="số tài khoản bị thử (1 phút)",
                value=unique_accounts,
                promql=prometheus.AUTH_UNIQUE_ACCOUNTS,
            ),
            MetricEvidence(
                name="tỷ lệ từ IP nguồn lớn nhất",
                value=top_source_ratio,
                promql=prometheus.AUTH_TOP_SOURCE_RATIO,
            ),
        ],
    )


def classify_crashloop(
    service_up: float,
    restarts: float,
    down_for_seconds: float,
    memory_ratio: float = 0.0,
) -> Severity | None:
    """Phân loại UC-2 — service chết vì OOM rồi restart. `None` nếu bình thường.

    Nhánh RIÊNG, không dùng `classify_severity()`, cùng lý do với
    `classify_auth_burst()`: hình thái khác hẳn. UC-1 là service **còn sống
    nhưng chậm**; UC-2 là service **chết rồi sống lại**. Latency và tỷ lệ lỗi
    của một process đang chết đi sống lại không nói lên điều gì — counter reset
    sau mỗi lần restart.

    Luôn trả **P1**: service không phục vụ được, không phải chỉ chậm. Đây là mức
    `docs/use-cases.md` UC-2 quy định.

    Hai đường vào, đủ một là P1:

    1. **Chết liên tục** ≥ `SUSTAINED_SECONDS` — `up` = 0 suốt khoảng đó. Cần
       ngưỡng thời gian vì một lần scrape hụt cũng làm `up` = 0 một nhịp.
    2. **Restart loop** — ≥ `CRASHLOOP_RESTARTS` lần trong 10 phút. Đường này
       bắt được cả khi service đang **sống** ở đúng lúc quét: crash loop theo
       định nghĩa là chết-sống xen kẽ, nên đòi "chết liên tục 30s" sẽ bỏ lọt.

    3. **Restart kèm bộ nhớ chạm trần** — chỉ cần ≥ 1 lần restart, nếu đỉnh bộ
       nhớ đã tới `MEMORY_NEAR_LIMIT_RATIO` phần trần container.

    ⚠️ Đường 3 thêm ngày 05/08 sau khi đo thật: Docker báo `RestartCount` = **5**
    nhưng `changes(process_start_time_seconds[10m])` chỉ thấy **1**, nên đường 2
    trượt và **Agent báo "bình thường" trong khi container vừa bị OOM-kill 5
    lần**. Process chết rồi sống lại nhanh hơn nhịp scrape 5s, nên phần lớn mốc
    khởi động không ai ghi lại.

    Vì sao không hạ `CRASHLOOP_RESTARTS` xuống 1 cho xong: một lần restart đơn
    thuần là **deploy bình thường**, hạ ngưỡng thì mỗi lần đội deploy Agent lại
    mở incident. Bộ nhớ chạm trần mới là thứ phân biệt được hai chuyện đó —
    deploy không đẩy bộ nhớ tới sát giới hạn container, OOM-kill thì có.

    Rủi ro còn lại: một service vốn chạy sát trần bộ nhớ, được deploy đúng lúc,
    sẽ bị báo nhầm. Chấp nhận được — báo nhầm một sự cố P1 vẫn tốt hơn bỏ lọt
    một container đang chết đi sống lại.

    Args:
        service_up: 1 nếu Prometheus scrape được, 0 nếu không.
        restarts: Số lần process khởi động lại trong 10 phút.
        down_for_seconds: Đã chết liên tục bao lâu. 0 nếu đang sống.
        memory_ratio: Đỉnh bộ nhớ trên trần container, 0–1. Mặc định 0 để chỗ
            gọi cũ không phải sửa; khi đó chỉ còn hai đường đầu.

    Raises:
        ValueError: khi có đầu vào là NaN — xem `classify_severity`.
    """
    _reject_nan(
        service_up=service_up,
        restarts=restarts,
        down_for_seconds=down_for_seconds,
        memory_ratio=memory_ratio,
    )

    if service_up < 1 and down_for_seconds >= SUSTAINED_SECONDS:
        return Severity.P1
    if restarts >= CRASHLOOP_RESTARTS:
        return Severity.P1
    if restarts >= 1 and memory_ratio >= MEMORY_NEAR_LIMIT_RATIO:
        return Severity.P1
    return None


def detect_crashloop(
    service_up: float,
    restarts: float,
    down_for_seconds: float,
    service: str,
    memory_ratio: float = 0.0,
    memory_peak_mb: float = 0.0,
) -> IncidentSignal | None:
    """Dựng tín hiệu UC-2 kèm bằng chứng. `None` nếu service bình thường.

    Đối xứng với `detect()` của UC-1: `classify_crashloop()` quyết định mức,
    hàm này gói lại thành `IncidentSignal` có bằng chứng số.

    Bằng chứng gồm bốn thứ, mỗi thứ trả lời một câu khác nhau:

    | Bằng chứng | Trả lời câu |
    |---|---|
    | `up` | Bây giờ có phục vụ được không? |
    | Số lần restart | Chết hẳn, hay đang chết đi sống lại? |
    | Bộ nhớ / giới hạn | **Chết vì cái gì?** |
    | Đỉnh bộ nhớ 10 phút | Bộ nhớ có leo dần tới trần không — tức có rò rỉ không? |

    ⚠️ Hai bằng chứng bộ nhớ thêm ngày 05/08 sau khi eval M3 cho UC-2 là **0/8**.
    Qwen không đoán bừa, nó trả lời "chưa xác định được nguyên nhân gốc" — hành
    vi đúng, vì hai bằng chứng đầu chỉ chứng minh *service đang chết đi sống
    lại*, không chứng minh **vì sao**. Ground truth UC-2 là "OOM-kill do rò rỉ
    bộ nhớ", mà không có số nào về bộ nhớ thì không cách nào nói ra được.

    Args:
        memory_ratio: Bộ nhớ đang dùng trên giới hạn container, 0–1.
        memory_peak_mb: Đỉnh bộ nhớ 10 phút, tính bằng MB. Quan trọng hơn giá
            trị tức thời: process vừa restart thì bộ nhớ về mức thấp, đo tức
            thời sẽ giấu mất chính cái đỉnh đã gây ra OOM-kill.
    """
    _reject_nan(memory_ratio=memory_ratio, memory_peak_mb=memory_peak_mb)

    # ⚠️ Phân loại theo ĐỈNH, không theo giá trị tức thời. Process vừa restart
    # thì bộ nhớ về mức thấp — đo tức thời sẽ giấu mất chính cái đỉnh đã gây ra
    # OOM-kill. Đo thật 05/08: tức thời 0.80 (dưới ngưỡng), đỉnh 0.89 (trên).
    # Truyền nhầm giá trị tức thời vào đây là Agent báo "bình thường" đúng lúc
    # container vừa chết 5 lần.
    tran_mb = prometheus.CONTAINER_MEMORY_LIMIT_BYTES / 1024 / 1024
    dinh_ratio = memory_peak_mb / tran_mb if tran_mb else 0.0

    severity = classify_crashloop(service_up, restarts, down_for_seconds, dinh_ratio)
    if severity is None:
        return None

    if service_up < 1:
        metric_name, metric_value, threshold = "up (service còn sống không)", service_up, 1.0
    else:
        metric_name, metric_value, threshold = (
            "số lần restart trong 10 phút",
            restarts,
            CRASHLOOP_RESTARTS,
        )

    return IncidentSignal(
        affected_service=service,
        severity=severity,
        detected_at=datetime.now(UTC),
        metric_name=metric_name,
        metric_value=metric_value,
        threshold=threshold,
        breached_for_seconds=down_for_seconds,
        evidence=[
            MetricEvidence(
                name="up (service còn sống không)",
                value=service_up,
                promql=prometheus.SERVICE_UP,
            ),
            MetricEvidence(
                name="số lần restart trong 10 phút",
                value=restarts,
                promql=prometheus.RESTART_COUNT_10M,
            ),
            MetricEvidence(
                name="bộ nhớ đang dùng / giới hạn container",
                value=memory_ratio,
                promql=prometheus.MEMORY_USAGE_RATIO,
            ),
            MetricEvidence(
                # Trần ghi thẳng vào tên, KHÔNG mượn `baseline` làm giới hạn.
                # `baseline` nghĩa là "mức thường ngày", nên war room in ra
                # "114 MB — lệch 0.9× baseline" — đọc thành thấp hơn bình
                # thường, trong khi thật ra là 89% của trần. Số đúng, câu sai.
                name=f"đỉnh bộ nhớ 10 phút (trần {tran_mb:.0f} MB)",
                value=memory_peak_mb,
                unit=" MB",
                promql=prometheus.MEMORY_PEAK_10M_MB,
            ),
        ],
    )


def correlate_deploy(
    deploys: list[DeployRecord],
    detected_at: datetime,
    within_minutes: float = DEPLOY_WINDOW_MINUTES,
) -> DeployRecord | None:
    """Lần deploy gần nhất **trước** thời điểm phát hiện, trong cửa sổ cho phép.

    Trả `None` nếu không có lần nào đủ gần. Đó là kết quả bình thường — phần
    lớn sự cố không đi kèm deploy, và ép gán một lần deploy cũ vào mọi sự cố
    làm bằng chứng mất giá trị.

    ⚠️ Hàm này tìm **trùng thời gian**, không chứng minh **nhân quả**. Cách gọi
    tên và cách `build_hypothesis()` diễn đạt kết quả phải giữ đúng ranh giới
    đó — xem chú thích ở `_cau_giai_thuyet()`.

    Args:
        deploys: Lịch sử deploy của service, thứ tự nào cũng được.
        detected_at: Thời điểm phát hiện sự cố.
        within_minutes: Deploy xa hơn ngần này thì bỏ qua.
    """
    truoc_do = [deploy for deploy in deploys if 0 <= deploy.minutes_before(detected_at) <= within_minutes]
    if not truoc_do:
        return None
    # `minutes_before` càng nhỏ càng gần thời điểm sự cố.
    return min(truoc_do, key=lambda deploy: deploy.minutes_before(detected_at))


def _phan_tram_tran(peak_mb: float) -> float:
    """Đỉnh bộ nhớ (MB) chiếm bao nhiêu phần trần container, 0–1."""
    tran_mb = prometheus.CONTAINER_MEMORY_LIMIT_BYTES / 1024 / 1024
    return peak_mb / tran_mb if tran_mb else 0.0


def _diem_tin_cay(
    evidence: list[MetricEvidence],
    related_deploy: DeployRecord | None,
) -> float:
    """Cộng điểm tin cậy theo số bằng chứng độc lập cùng chỉ về một nguyên nhân.

    Vì sao phải là **hàm của bằng chứng** chứ không phải một hằng số: contract ②
    ghi `confidence` do rule engine tính chứ không phải LLM tự nhận. Nhưng một
    con số cắm cứng cũng chẳng đo gì hơn — chỉ là người bịa thay vì máy bịa.
    Muốn con số đó có nghĩa thì mỗi phần của nó phải truy ngược được về một
    `MetricEvidence` cụ thể.

    Bảng điểm, cộng dồn rồi chặn ở 1.0:

    ⚠️ **Bảng phải phủ cả ba use case.** Bản đầu chỉ biết tên bằng chứng của
    UC-1, nên mọi giả thuyết UC-2 và UC-3 ra `confidence = 0.0` — con số đó vô
    nghĩa y như một hằng số cắm cứng, chỉ khác là sai theo hướng ngược lại. Phát
    hiện ngày 05/08 khi truy vì sao eval M3 cho UC-2 và UC-3 đều 0.

    | Bằng chứng | Điểm | Vì sao ngần đó |
    |---|---|---|
    | **UC-1** Pool cạn ≥ 95% | 0.40 | Bằng chứng **nguyên nhân gốc**, nặng nhất |
    | **UC-1** p95 lệch baseline ≥ 3× | 0.30 | Xác nhận bất thường thật, không phải dao động |
    | **UC-1** Tỷ lệ lỗi 5xx vượt ngưỡng | 0.10 | Triệu chứng kèm theo |
    | **UC-2** Đỉnh bộ nhớ chạm ≥ 90% trần | 0.40 | Bằng chứng **nguyên nhân gốc** của OOM |
    | **UC-2** Service đã chết (`up` = 0) | 0.30 | Sự cố có thật, không phải nhiễu |
    | **UC-2** Restart ≥ ngưỡng crash loop | 0.20 | Xác nhận là loop, không phải tắt hẳn |
    | **UC-3** Đăng nhập hỏng ≥ ngưỡng P1 | 0.40 | Hình thái tấn công rõ, không phải người gõ nhầm |
    | **UC-3** Đăng nhập hỏng ≥ ngưỡng P2 | 0.25 | Bất thường nhưng chưa chắc là tấn công |
    | Có deploy ngay trước | 0.20 | Chỉ là trùng thời gian, nên nhẹ |

    Một giả thuyết chỉ dựa trên "p95 cao" ra 0.30 — thấp, và **đáng thấp**.
    """
    diem = 0.0
    for item in evidence:
        # UC-1 — nghẽn tài nguyên.
        if "db_pool" in item.name and item.value >= POOL_EXHAUSTED_RATIO:
            diem += 0.40
        elif "p95" in item.name and (item.deviation_ratio or 0) >= BASELINE_DEVIATION_STRONG:
            diem += 0.30
        elif "lỗi 5xx" in item.name and item.value > ERROR_RATE_P3:
            diem += 0.10
        # UC-2 — chết vì hết bộ nhớ.
        elif "đỉnh bộ nhớ" in item.name and _phan_tram_tran(item.value) >= MEMORY_NEAR_LIMIT_RATIO:
            diem += 0.40
        elif "up (" in item.name and item.value < 1:
            diem += 0.30
        elif "restart" in item.name and item.value >= CRASHLOOP_RESTARTS:
            diem += 0.20
        # UC-3 — hình thái truy cập bất thường.
        elif "/login" in item.name:
            if item.value >= AUTH_FAILURE_P1:
                diem += 0.40
            elif item.value >= AUTH_FAILURE_P2:
                diem += 0.25

    if related_deploy is not None:
        diem += 0.20

    return min(diem, 1.0)


def _cau_giai_thuyet(
    signal: IncidentSignal,
    evidence: list[MetricEvidence],
    related_deploy: DeployRecord | None,
) -> str:
    """Câu giả thuyết do rule ghép, dùng khi LLM không viết được.

    Cũng là **khuôn mẫu** cho câu LLM viết: nó nêu nguyên nhân gốc trước, và khi
    có deploy thì nói "trùng thời gian" chứ **không** nói "vì".

    Ranh giới đó không phải chuyện chữ nghĩa. `demo/seed.py` cắm một dòng
    `v1.4.2` deploy trước 4 phút **mỗi lần chạy**, còn `pg_sleep(0.2)` trong
    `/pay` thì luôn có mặt bất kể version nào — deploy trong demo **không gây ra
    sự cố**. Viết "cạn vì deploy v1.4.2" là suy nhân quả từ tương quan: nghe
    thuyết phục, và sai. `use-cases.md` UC-1 chấm chẩn đoán đúng khi nêu được
    **pool cạn / truy vấn giữ connection lâu**, không phải khi nêu deploy.
    """

    def _tim(khoa: str) -> MetricEvidence | None:
        return next((item for item in evidence if khoa in item.name), None)

    pool = _tim("db_pool")
    bo_nho = _tim("đỉnh bộ nhớ")
    login = _tim("/login")

    # Thứ tự xét = thứ tự "cụ thể dần". Mỗi nhánh nêu NGUYÊN NHÂN GỐC của một
    # hình thái sự cố; nhánh cuối chỉ mô tả triệu chứng và là đường lùi.
    #
    # ⚠️ Bản đầu chỉ có nhánh pool, nên UC-2 và UC-3 rơi hết xuống nhánh cuối và
    # câu giả thuyết chỉ nhắc lại con số đã có trong tiêu đề. `use-cases.md`
    # chấm "nêu chung chung" là KHÔNG đạt — đó là một nửa lý do eval M3 cho
    # UC-2/UC-3 ra 0, nửa còn lại là thiếu bằng chứng bộ nhớ.
    if pool is not None and pool.value >= POOL_EXHAUSTED_RATIO:
        cau = (
            f"Connection pool của {signal.affected_service} cạn kiệt — mỗi request giữ "
            "connection lâu hơn bình thường nên số chỗ trong pool hết sạch dưới tải."
        )
    elif bo_nho is not None and _phan_tram_tran(bo_nho.value) >= MEMORY_NEAR_LIMIT_RATIO:
        tran = prometheus.CONTAINER_MEMORY_LIMIT_BYTES / 1024 / 1024
        cau = (
            f"{signal.affected_service} bị OOM-kill: bộ nhớ leo tới {bo_nho.value:.0f} MB, "
            f"chạm giới hạn {tran:.0f} MB của container, nên Docker giết process rồi "
            "khởi động lại. Bộ nhớ leo dần chứ không nhảy vọt — hình thái của rò rỉ, "
            "không phải của một request nặng bất thường."
        )
    elif login is not None and login.value >= AUTH_FAILURE_P2:
        cau = (
            f"{signal.affected_service} đang nhận {login.value:.0f} lượt đăng nhập thất bại "
            "mỗi giây — vấn đề bảo mật, không phải quá tải. Hệ thống vẫn khoẻ: "
            "latency bình thường và không có lỗi 5xx."
        )
        # Hình dạng nguồn là thứ phân biệt tấn công với người dùng gõ nhầm.
        # Chỉ nói ra khi số liệu thật sự chỉ về credential-stuffing — nhiều tài
        # khoản bị thử từ ít nguồn. Nói "credential-stuffing" mà không có hai
        # con số đó là đoán, đúng cái mình cấm LLM làm.
        nguon = _tim("IP nguồn khác nhau")
        tai_khoan = _tim("tài khoản bị thử")
        ty_le = _tim("IP nguồn lớn nhất")
        if (
            tai_khoan is not None
            and nguon is not None
            and tai_khoan.value >= STUFFING_MIN_ACCOUNTS
            and ty_le is not None
            and ty_le.value >= STUFFING_TOP_SOURCE_RATIO
        ):
            cau += (
                f" Hình thái credential-stuffing: {tai_khoan.value:.0f} tài khoản bị thử "
                f"từ {nguon.value:.0f} IP nguồn, trong đó một nguồn chiếm "
                f"{ty_le.value * 100:.0f}% số lượt — một người quên mật khẩu không tạo ra "
                "hình dạng này."
            )
    else:
        cau = (
            f"{signal.affected_service} bất thường ở {signal.metric_name} "
            f"({signal.metric_value:.2f}, ngưỡng {signal.threshold:.2f}). "
            "Chưa đủ bằng chứng để nêu nguyên nhân gốc."
        )

    if related_deploy is not None:
        phut = related_deploy.minutes_before(signal.detected_at)
        cau += (
            f" Trùng thời gian: deploy {related_deploy.version} diễn ra {phut:.0f} phút "
            "trước khi phát hiện — chưa xác minh nhân quả, nhưng đủ để rollback là "
            "hành động thử đầu tiên."
        )
    return cau


def build_hypothesis(
    signal: IncidentSignal,
    related_deploy: DeployRecord | None = None,
) -> Hypothesis:
    """Dựng giả thuyết từ bằng chứng — **không gọi LLM**.

    Đây là nửa tất định của node `hypothesize`: `evidence`, `confidence` và một
    `statement` dự phòng. Nửa còn lại (LLM viết lại `statement` và `reasoning`)
    nằm ở [`nodes/hypothesize.py`](../agents/nodes/hypothesize.py).

    Tách đôi để phần được chấm — con số và bằng chứng — test được mà không cần
    mạng, và để chỗ ràng buộc LLM nằm gọn một nơi cho người review.

    `confidence` do `_diem_tin_cay()` tính, `evidence` lấy nguyên từ tín hiệu
    (số đo thật của Prometheus, kèm câu PromQL để kiểm chứng lại).
    """
    evidence = list(signal.evidence)
    return Hypothesis(
        statement=_cau_giai_thuyet(signal, evidence, related_deploy),
        confidence=_diem_tin_cay(evidence, related_deploy),
        evidence=evidence,
        related_deploy=related_deploy,
    )


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
    "BASELINE_DEVIATION_STRONG",
    "BASELINE_MIN_SAMPLES",
    "CRASHLOOP_RESTARTS",
    "DEPLOY_WINDOW_MINUTES",
    "POOL_EXHAUSTED_RATIO",
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
    "classify_crashloop",
    "classify_severity",
    "correlate_deploy",
    "build_hypothesis",
    "detect",
    "detect_auth_burst",
    "detect_crashloop",
    "is_spreading",
]
