"""Node `detect` — đọc Prometheus, quyết định có phải sự cố không.

CHỦ SỞ HỮU: Việt. File này Đức viết hộ ngày 02/08 lúc Việt vắng, để chuỗi
end-to-end chạy được. Việt cứ sửa thoải mái, nhất là chỗ đo `breached_for_seconds`.

Node này chỉ **đọc và quyết định**, không chạm Jira. Việc mở war room là của
[`open_war_room`](open_war_room.py) — tách ra để `detect` test được mà không
cần Jira, và để chống mở trùng nằm đúng một chỗ.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from src.config import get_settings
from src.models.incident import IncidentSignal
from src.services import deploys, planned_events, prometheus, rules
from src.services.prometheus import PrometheusClient

logger = logging.getLogger(__name__)

#: Các cửa sổ thời gian dùng để đo "đã vượt ngưỡng liên tục bao lâu".
#:
#: `rules.detect()` cần `breached_for_seconds`, mà Agent thì poll theo chu kỳ.
#: Giữ mốc bắt đầu trong bộ nhớ là cách dễ nghĩ nhất nhưng sai ở ba điểm:
#: restart Agent là mất, chạy nhiều instance thì mỗi con một số, và test phải
#: giả lập thời gian.
#:
#: Thay vào đó hỏi thẳng Prometheus: `min_over_time(p95[30s])` mà vẫn trên
#: ngưỡng nghĩa là suốt 30 giây đó chưa lúc nào tụt xuống. Stateless, restart
#: không ảnh hưởng, và test chỉ cần một `MockTransport`.
#:
#: Thử từ cửa sổ nhỏ tới lớn rồi lấy cửa sổ lớn nhất còn thoả — cho ra con số
#: xấp xỉ nhưng có thật, đủ để ghi vào war room ("vượt liên tục 120s").
SUSTAINED_PROBE_WINDOWS = (30, 60, 120, 300)

#: Bước lấy mẫu bên trong mỗi cửa sổ. Khớp `scrape_interval: 5s` của
#: [demo/prometheus.yml](../../../demo/prometheus.yml) — lấy dày hơn scrape thì
#: chỉ đọc lại cùng một điểm dữ liệu.
_PROBE_STEP_SECONDS = 5


def _samples_by_service(client: PrometheusClient, promql: str) -> dict[str, float]:
    """Chạy một câu PromQL, trả `{service: giá trị}`.

    Rỗng không phải lỗi — service chưa nhận request nào thì không có series.
    `PrometheusClient.query()` đã log warning cho trường hợp đó.
    """
    return {sample.service: sample.value for sample in client.query(promql)}


def _sustained(client: PrometheusClient, expr: str, threshold: float) -> dict[str, float]:
    """Cửa sổ lớn nhất mà `expr` chưa lúc nào tụt xuống dưới `threshold`.

    Service không vượt ngưỡng thì không có mặt trong kết quả.

    So bằng `>` cho cả ba đường đo, kể cả đường lệch baseline mà `rules.detect()`
    so bằng `>=`. Lệch nhau đúng tại điểm bằng nhau tuyệt đối — với số thực đọc
    từ Prometheus thì gần như không xảy ra, và sai về phía thận trọng (chậm
    một nhịp scrape) chứ không phải phía báo nhầm.
    """
    sustained: dict[str, float] = {}
    for window in SUSTAINED_PROBE_WINDOWS:
        promql = f"min_over_time(({expr})[{window}s:{_PROBE_STEP_SECONDS}s])"
        for service, value in _samples_by_service(client, promql).items():
            if value > threshold:
                sustained[service] = float(window)
    return sustained


def breached_seconds_by_service(client: PrometheusClient) -> dict[str, float]:
    """Mỗi service đã ở trạng thái bất thường liên tục bao nhiêu giây.

    Phải đo **cả ba** đường mà cửa 2 của `rules.detect()` chấp nhận, rồi lấy
    cửa sổ lớn nhất trong ba:

    1. p95 vượt ngưỡng cứng P3
    2. tỷ lệ lỗi 5xx vượt ngưỡng cứng P3
    3. p95 lệch baseline từ `BASELINE_DEVIATION_RATIO` lần trở lên

    ⚠️ Bản đầu của file này chỉ đo đường 1. Hệ quả: cửa 1 (`breached_for_seconds
    >= SUSTAINED_SECONDS`) luôn thấy 0 với sự cố **không** làm chậm latency, nên
    hai đường còn lại của `rules.detect()` vĩnh viễn không với tới được — đúng
    kịch bản UC-2, container OOM rồi restart, service phun 5xx trong khi những
    request còn sống vẫn nhanh như thường. Cửa lọc "đủ lâu" phải đo đúng cái
    điều kiện mà nó đang lọc.

    Dùng ngưỡng P3 (thấp nhất) chứ không phải P2: đây chỉ là cửa "đủ lâu",
    còn việc phân loại nặng nhẹ là của `rules.classify_severity()`. Chặn ở P2
    tại đây thì P3 và P4 vĩnh viễn không đạt tới được — cùng loại lỗi Việt đã
    ghi trong docstring `rules.detect()`.
    """
    latency = _sustained(client, prometheus.P95_LATENCY, rules.P95_P3_SECONDS)
    errors = _sustained(client, prometheus.ERROR_RATE, rules.ERROR_RATE_P3)
    # Baseline 0 (chưa có lịch sử) làm phép chia trả rỗng, không phải chia cho 0
    # — Prometheus bỏ hẳn series thay vì sinh Inf. Khớp với nhánh
    # `p95_baseline > 0` trong `rules.detect()`.
    # ⚠️ Kèm điều kiện đủ điểm, giống `rules.detect()`. Không kèm thì cửa "đủ
    # lâu" vẫn đếm thời gian cho một baseline dựng trên vài điểm — Agent im lặng
    # ở `rules.detect()` nhưng lại báo "đã bất thường 300s" trong log, hai chỗ
    # nói khác nhau về cùng một sự việc.
    deviation = _sustained(
        client,
        f"(({prometheus.P95_LATENCY}) / ({prometheus.P95_BASELINE_30M}))"
        f" and on(service) (({prometheus.BASELINE_SAMPLE_COUNT_30M}) >= {rules.BASELINE_MIN_SAMPLES})",
        rules.BASELINE_DEVIATION_RATIO,
    )

    sustained: dict[str, float] = {}
    for source in (latency, errors, deviation):
        for service, window in source.items():
            sustained[service] = max(sustained.get(service, 0.0), window)
    return sustained


def _one_per_service(*sources: dict[str, IncidentSignal]) -> list[IncidentSignal]:
    """Gộp các nhánh phát hiện, mỗi service lấy đúng MỘT tín hiệu.

    Thứ tự tham số là thứ tự ưu tiên — nguồn đứng trước thắng.

    Vì sao mỗi service chỉ một: `open_war_room` chống mở trùng theo service, nên
    tín hiệu thứ hai của cùng service không tạo issue mới mà chỉ comment vào
    issue đã có. Tiêu đề và severity của issue lấy từ tín hiệu **đến trước** —
    tức là ngẫu nhiên. Người trực đọc war room sẽ thấy một nhan đề không khớp
    với nội dung bên trong.

    Ưu tiên hiện tại: **UC-2 (chết) → UC-3 (bảo mật) → UC-1 (chậm)**.

    UC-3 phải đứng trước UC-1, không phải vì nó nặng hơn mà vì `use-cases.md`
    ghi rõ: kết luận "service quá tải" cho một vụ credential-stuffing là chẩn
    đoán **SAI**. Một cuộc tấn công cũng làm latency tăng, nên nếu để UC-1
    thắng thì Agent sẽ chẩn đoán đúng triệu chứng mà sai nguyên nhân — đúng cái
    mà phép đo trong `eval/` dùng để chấm.
    """
    signals: list[IncidentSignal] = []
    da_co: set[str] = set()
    for source in sources:
        for service, signal in source.items():
            if service in da_co:
                continue
            da_co.add(service)
            signals.append(signal)
    return signals


def _detect_crashloops(client: PrometheusClient) -> dict[str, IncidentSignal]:
    """Quét UC-2 — service chết vì OOM rồi restart. Trả `{service: tín hiệu}`.

    Năm câu hỏi Prometheus, không phụ thuộc service có nhận request hay không:
    service còn sống không, đã chết liên tục bao lâu, khởi động lại mấy lần
    trong 10 phút, đang dùng bao nhiêu phần bộ nhớ, và đỉnh bộ nhớ là bao nhiêu.

    Phần "chết liên tục bao lâu" dùng lại `_sustained()` với biểu thức đảo
    `1 - up`: `min_over_time` của nó còn trên 0.5 nghĩa là suốt cửa sổ đó chưa
    lúc nào service sống lại.

    ⚠️ Hai câu về bộ nhớ thêm ngày 05/08. Không có chúng thì Agent chứng minh
    được service *đang chết đi sống lại* nhưng không nói được **vì sao** — và
    eval M3 cho UC-2 ra 0/8 đúng vì lý do đó, chứ không phải vì LLM kém.
    """
    up = _samples_by_service(client, prometheus.SERVICE_UP)
    restarts = _samples_by_service(client, prometheus.RESTART_COUNT_10M)
    down_for = _sustained(client, prometheus.SERVICE_DOWN, 0.5)
    memory_ratio = _samples_by_service(client, prometheus.MEMORY_USAGE_RATIO)
    memory_peak = _samples_by_service(client, prometheus.MEMORY_PEAK_10M_MB)
    # Dự báo xu hướng — chỗ duy nhất trong bộ luật nhìn về phía trước.
    memory_forecast = _samples_by_service(client, prometheus.MEMORY_FORECAST_1H_RATIO)

    found: dict[str, IncidentSignal] = {}
    for service in set(up) | set(restarts):
        signal = rules.detect_crashloop(
            service_up=up.get(service, 0.0),
            restarts=restarts.get(service, 0.0),
            down_for_seconds=down_for.get(service, 0.0),
            service=service,
            memory_ratio=memory_ratio.get(service, 0.0),
            memory_peak_mb=memory_peak.get(service, 0.0),
            memory_forecast_ratio=memory_forecast.get(service, 0.0),
        )
        if signal is None:
            continue
        found[service] = signal
        logger.warning(
            "UC-2 trên %s: up=%.0f, %.0f lần restart trong 10 phút, chết liên tục %.0fs",
            service,
            up.get(service, 0.0),
            restarts.get(service, 0.0),
            down_for.get(service, 0.0),
        )
    return found


def _detect_auth_bursts(client: PrometheusClient) -> dict[str, IncidentSignal]:
    """Quét UC-3 — burst đăng nhập thất bại. Trả `{service: tín hiệu}`.

    `ERROR_RATE` **không** bắt được UC này: nó chỉ khớp `status=~"5.."`, còn 401
    là 4xx. Đây là tín hiệu riêng, và ngưỡng của nó là **số tuyệt đối mỗi giây**
    chứ không phải tỷ lệ — nếu kẻ tấn công là nguồn traffic duy nhất thì tỷ lệ
    lỗi là 100% ngay từ request đầu, chưa nói được gì về mức nghiêm trọng.

    Đo "đã bất thường liên tục bao lâu" bằng `_sustained()` với sàn P3, giống
    cách UC-1 làm — một người gõ nhầm mật khẩu vài lần không được mở incident.
    """
    rate = _samples_by_service(client, prometheus.AUTH_FAILURE_RATE)
    if not rate:
        # Chưa ai gọi `/login` lần nào. Bình thường, không phải lỗi.
        return {}

    sustained = _sustained(client, prometheus.AUTH_FAILURE_RATE, rules.AUTH_FAILURE_P3)

    # Ba metric hình dạng nguồn — thứ phân biệt tấn công với quá tải. Thiếu
    # chúng thì tín hiệu chỉ có một con số, và LLM không có gì để phân biệt.
    nguon = _samples_by_service(client, prometheus.AUTH_UNIQUE_SOURCE_IPS)
    tai_khoan = _samples_by_service(client, prometheus.AUTH_UNIQUE_ACCOUNTS)
    ty_le_nguon = _samples_by_service(client, prometheus.AUTH_TOP_SOURCE_RATIO)

    # Độ bền của DIỆN RỘNG — thước đo riêng, không dùng sàn tốc độ.
    #
    # `sustained` ở trên đo bằng sàn `AUTH_FAILURE_P3`, nên kẻ giữ tốc độ dưới
    # ngưỡng sẽ có `breached_for_seconds = 0` và cửa "đủ lâu" không bao giờ mở.
    # Đo ngày 20/08 trên case I19: 0,95/s suốt 24 giờ, 5.000 tài khoản — sàn tốc
    # độ cho 0 giây, tức "chưa từng bất thường".
    #
    # Đo độ bền của chính thứ nhận ra tấn công: số tài khoản đã ở mức dò hàng loạt
    # bao lâu.
    ben_dien_rong = _sustained(
        client, prometheus.AUTH_UNIQUE_ACCOUNTS, rules.AUTH_UNIQUE_ACCOUNTS_ATTACK
    )

    found: dict[str, IncidentSignal] = {}
    for service, failures in rate.items():
        signal = rules.detect_auth_burst(
            failures_per_second=failures,
            breached_for_seconds=sustained.get(service, 0.0),
            service=service,
            unique_source_ips=nguon.get(service, 0.0),
            unique_accounts=tai_khoan.get(service, 0.0),
            top_source_ratio=ty_le_nguon.get(service, 0.0),
            accounts_sustained_seconds=ben_dien_rong.get(service, 0.0),
        )
        if signal is None:
            continue
        found[service] = signal
        logger.warning(
            "UC-3 trên %s: %.1f lượt /login thất bại mỗi giây, liên tục %.0fs "
            "— %.0f tài khoản từ %.0f IP nguồn, nguồn lớn nhất chiếm %.0f%%",
            service,
            failures,
            sustained.get(service, 0.0),
            tai_khoan.get(service, 0.0),
            nguon.get(service, 0.0),
            ty_le_nguon.get(service, 0.0) * 100,
        )
    return found



def _viec_da_len_lich(service: str) -> str | None:
    """Việc đã lên lịch mà Agent THẬT biết được, lấy từ lịch sử deploy.

    ⚠️ Chỉ có DEPLOY. Không có pentest, load test đã phê duyệt, hay đổi route
    CDN — lúc chạy thật **không tồn tại nguồn nào** cho những thứ đó. Bộ đo
    trong `eval/` đọc chúng từ trường `context` do người viết case đặt tay, nên
    tỷ lệ báo nhầm trong báo cáo tốt hơn thực tế nếu không nói rõ.

    Đo ngày 21/08 trên 25 case bình thường/nhiễu:

        không lọc gì                        báo nhầm 28%  (7 case)
        lọc bằng lịch sử deploy (hàm này)   báo nhầm 20%  (5 case)
        lọc bằng cả `context` của bộ đo     báo nhầm 16%  (4 case)

    Muốn xuống 16% thật thì cần một nguồn cửa sổ bảo trì có thể đọc lúc chạy —
    ví dụ issue Jira mang nhãn bảo trì kèm khoảng thời gian. Chưa có. Ghi ra để
    người sau biết đây là chỗ còn thiếu, không phải chỗ đã xong.

    Returns:
        Mô tả việc đã lên lịch, hoặc `None` nếu không có deploy nào đủ gần.
    """
    # Không có DATABASE_URL thì không có nguồn nào — thoát trước khi mở event
    # loop. Không có bước này thì mỗi tín hiệu tốn một `asyncio.run()` cộng một
    # lần thử kết nối Postgres: đo được +12,6 giây trên toàn bộ test suite
    # (3,9s → 16,5s), và ở production là một round-trip DB vô ích mỗi vòng quét.
    if not get_settings().database_url:
        return None

    try:
        history = deploys.recent_deploys(service)
    except Exception:  # nguồn deploy hỏng không được làm sập vòng quét
        logger.warning("%s: không đọc được lịch sử deploy — bỏ qua bước lọc", service)
        return None

    gan = rules.correlate_deploy(history, datetime.now(UTC))
    if gan is None:
        return None

    # ⚠️ CỐ Ý KHÔNG trả `change_note`. Ghi chú thay đổi là văn bản tự do tả một
    # thay đổi CODE, không phải tuyên bố "việc này đang chạy". Đưa nó vào bộ khớp
    # từ khoá là mời báo-nhầm-ngược: tín hiệu thật bị bịt miệng.
    #
    # Đo ngày 21/08 với đúng ghi chú trong `demo/seed.py`: note của `v1.4.2` là
    # "Gộp batch job đối soát... Batch chạy mỗi 5 phút" — chứa chữ "batch", khớp
    # phạm vi latency, và sẽ **bỏ qua cả UC-1 lẫn UC-4**. Chưa nổ chỉ vì `v1.4.3`
    # mới hơn nên `correlate_deploy` chọn nó. Đó là may, không phải đúng.
    #
    # Một lần deploy giải thích được **đúng một thứ**: container bị thay nên
    # restart. Không giải thích latency, không giải thích pool, không giải thích
    # đăng nhập sai. Nên trả về đúng chữ "deploy" và để `_PHAM_VI` quyết định.
    return f"deploy {gan.version}"


def _bo_tin_hieu_da_co_giai_thich(
    signals: list[IncidentSignal],
    detector_theo_service: dict[str, str],
    nguon: Callable[[str], str | None] | None = None,
) -> list[IncidentSignal]:
    """Bỏ những tín hiệu đã có việc lên lịch giải thích được.

    Lọc MỘT LẦN ở cuối, không bọc từng nhánh — giống `eval/case_suite.py`. Bộ
    luật vẫn chạy nguyên vẹn và vẫn dựng đủ bằng chứng, nên log vẫn ghi được
    Agent đã thấy gì, kể cả khi quyết định không báo động.
    """
    con_lai: list[IncidentSignal] = []
    for signal in signals:
        service = signal.affected_service
        viec = (nguon or _viec_da_len_lich)(service)
        detector = detector_theo_service.get(service, "latency")

        # Deploy giải thích được VÀI lần restart — thay pod là "old shutdown +
        # new startup" = 2 lần. Nhiều hơn thế là vòng crash thật, deploy không
        # giải thích được. Không có cửa này thì UC-2 im lặng suốt 15 phút sau mỗi
        # lần deploy, vì `_PHAM_VI["crashloop"]` có từ khoá "deploy".
        la_restart = "restart" in signal.metric_name.lower()
        if la_restart and signal.metric_value > rules.CRASHLOOP_RESTARTS:
            logger.info(
                "%s: %.0f lần restart — nhiều hơn mức một lần deploy giải thích được (%.0f), vẫn báo động",
                service, signal.metric_value, rules.CRASHLOOP_RESTARTS,
            )
            con_lai.append(signal)
            continue

        if planned_events.giai_thich_duoc(viec, detector, signal.metric_name):
            logger.info(
                "%s: KHÔNG mở war room — %s đã được giải thích bởi %r",
                service, signal.metric_name, viec,
            )
            continue
        con_lai.append(signal)
    return con_lai


def detect_incidents(
    client: PrometheusClient,
    *,
    nguon_viec_da_len_lich: Callable[[str], str | None] | None = None,
) -> list[IncidentSignal]:
    """Quét toàn bộ service, trả tín hiệu sự cố nếu có.

    Gọi 4 + 12 câu PromQL mỗi vòng (4 metric, và 4 cửa sổ × 3 đường đo thời
    lượng), không phụ thuộc số service — Prometheus trả tất cả service trong
    một lần.

    Đo trên stack demo ngày 02/08: một vòng đầy đủ mất khoảng **2,2 giây**, gần
    hết nằm ở 4 câu đo lệch baseline — mỗi câu bọc một `quantile_over_time` cửa
    sổ 30 phút bên trong một subquery. Với `--interval 10` thì Agent bận khoảng
    22% thời gian. Hạ interval xuống dưới 5s là hai vòng chồng lên nhau, cần đo
    lại trước khi làm.

    Args:
        client: Nguồn số đo.
        nguon_viec_da_len_lich: Hàm `service -> mô tả việc đã lên lịch`, để bỏ
            những tín hiệu đã có lời giải thích. Bỏ trống thì dùng lịch sử
            deploy (`_viec_da_len_lich`).

            Có tham số này để `detect` **vẫn thuần**: bộ đo truyền thẳng bối cảnh
            của case, không cần Postgres, và hai đường (qua node này / gọi luật
            trực tiếp) **không thể lệch nhau** — chính chỗ lệch đó đã làm báo cáo
            công bố 16% báo nhầm trong khi Agent thật là 28%.

    Returns:
        Danh sách `IncidentSignal`, rỗng nghĩa là mọi thứ bình thường.

    Raises:
        PrometheusError: không gọi được Prometheus hoặc PromQL sai cú pháp.
            KHÔNG nuốt lỗi ở đây — Agent mù mà tưởng "bình thường" là tình
            huống nguy hiểm nhất.
    """
    # ⚠️ UC-2 và UC-3 phải quét TRƯỚC chỗ return sớm bên dưới.
    #
    # UC-2: service chết thì không nhận request nào, nên không có series p95 —
    # đúng điều kiện làm hàm này thoát sớm. Đặt sau thì sự cố nặng nhất lại là
    # sự cố duy nhất không phát hiện được (đã xác nhận khi chạy OOM thật).
    #
    # UC-3: burst đăng nhập thất bại có thể là traffic DUY NHẤT đến service, mà
    # `/login` trả 401 nên không sinh series p95 nào (bộ lọc `_HAS_TRAFFIC` chỉ
    # đếm request, nhưng nếu attack là toàn bộ traffic thì handler khác im lìm).
    crashloop = _detect_crashloops(client)
    auth_burst = _detect_auth_bursts(client)

    p95 = _samples_by_service(client, prometheus.P95_LATENCY)
    if not p95:
        if not (crashloop or auth_burst):
            logger.warning(
                "Không có series p95 nào. Service chưa nhận request, hoặc tên metric "
                "lệch so với thứ demo/ expose — xem docs/contracts/01-metrics.md."
            )
        return _bo_tin_hieu_da_co_giai_thich(
            _one_per_service(crashloop, auth_burst),
            {**dict.fromkeys(auth_burst, "auth"), **dict.fromkeys(crashloop, "crashloop")},
            nguon_viec_da_len_lich,
        )

    baseline = _samples_by_service(client, prometheus.P95_BASELINE_30M)
    # Đếm điểm dữ liệu thật trong cửa sổ baseline. Prometheus không có volume
    # nên khởi động lạnh là mất sạch lịch sử, và `quantile_over_time` vẫn trả
    # về một con số tính trên vài điểm — `rules.detect()` cần biết để không tin.
    baseline_samples = _samples_by_service(client, prometheus.BASELINE_SAMPLE_COUNT_30M)
    error_rate = _samples_by_service(client, prometheus.ERROR_RATE)
    pool = _samples_by_service(client, prometheus.POOL_SATURATION_PEAK_5M)
    sustained = breached_seconds_by_service(client)

    signals: list[IncidentSignal] = _one_per_service(crashloop, auth_burst)
    da_co = {signal.affected_service for signal in signals}

    for service, p95_now in p95.items():
        # Service đã có tín hiệu UC-2 hoặc UC-3 thì bỏ qua đường UC-1 cho chính
        # nó. Xem `_one_per_service()` để biết vì sao.
        if service in da_co:
            continue

        signal = rules.detect(
            p95_now=p95_now,
            p95_baseline=baseline.get(service, 0.0),
            error_rate=error_rate.get(service, 0.0),
            # service-dat-hang không có metric pool — 0.0 là đúng, nó không
            # dùng connection pool nên không thể là nguyên nhân gốc ở đó.
            pool_saturation=pool.get(service, 0.0),
            service=service,
            breached_for_seconds=sustained.get(service, 0.0),
            baseline_samples=baseline_samples.get(service, 0.0),
        )
        if signal is None:
            continue
        logger.info(
            "Phát hiện sự cố %s trên %s: %s = %.3f (ngưỡng %.3f), vượt liên tục %.0fs",
            signal.severity.value,
            service,
            signal.metric_name,
            signal.metric_value,
            signal.threshold,
            signal.breached_for_seconds,
        )
        signals.append(signal)

    # Nhãn đường phát hiện cho từng service, để `planned_events` biết một việc đã
    # lên lịch có nằm trong PHẠM VI giải thích được tín hiệu này hay không.
    # Deploy giải thích được container restart, KHÔNG giải thích được pool cạn.
    detector_theo_service = {
        **dict.fromkeys(p95, "latency"),
        **dict.fromkeys(auth_burst, "auth"),
        **dict.fromkeys(crashloop, "crashloop"),
    }
    return _bo_tin_hieu_da_co_giai_thich(signals, detector_theo_service, nguon_viec_da_len_lich)
