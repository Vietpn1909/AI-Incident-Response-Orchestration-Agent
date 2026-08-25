"""Status page công khai — trang người dùng dịch vụ xem để biết có sự cố không.

CHỦ SỞ HỮU: Long · dựng lại ngày 17/08 cho cùng hệ thiết kế với `war_room.py`

Chạy:
    streamlit run ui/status_page.py

Dữ liệu đã có sẵn, không cần chờ Agent hay Jira. Xem ui/README.md.

## Hai tầng, y như war room

Đây là trang công khai nhưng vẫn giữ nguyên tắc **dịch THÊM, không dịch THAY**:
tên dịch vụ dễ hiểu dẫn đường, dòng `↳` bên dưới giữ nguyên văn tên kỹ thuật và
tên metric. Người ngoài đọc dòng trên là đủ; người trực cần dòng dưới để đào.

## Cùng hệ thiết kế với war room, khác nhịp

Token màu, font, nút, pill đều lấy từ [theme.py](theme.py) — sửa màu ở đó là hai
trang đổi cùng nhau. Nhưng hai trang **không** giống nhau về bố cục, và đó là cố
ý: war room là bàn làm việc (header + sidebar + hai vùng cuộn), còn trang này là
một tờ thông báo — một cột, đọc từ trên xuống, không có gì để thao tác.

Trang cũng dựng thành một khối HTML rồi nhúng bằng `st.iframe`, cùng lý do với
war room: cần nút đổi theme, mà `st.markdown` bị chặn `<script>`.

## Chỉ số hiển thị lấy ở đâu

Từ `active_incidents[]` trong chính response `/api/status` — backend đã điền sẵn
(src/api/incidents.py). Với dịch vụ đang có sự cố thì lấy `signal` của incident
đó và diễn đạt qua `labels.bang_chung()`.

⚠️ Metric kích hoạt **không phải lúc nào cũng là thời gian phản hồi** — có thể
là tỷ lệ lỗi, bộ nhớ, số lần restart. Nên đừng dán nhãn cứng "Latency" cho ô đó;
tên hiển thị phải đi qua `labels.metric()` để nói đúng cái đang bất thường.

⚠️ Dịch vụ **không** có sự cố thì để trống ô chỉ số. Không có số thật thì không
điền gì — bịa một con số cho thẻ đỡ trống là phá đúng luận điểm của cả đồ án.
"""

import html
import os
import pathlib
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st

# `streamlit run ui/status_page.py` đặt thư mục ui/ vào sys.path, không đặt thư
# mục gốc repo — xem chú thích cùng chỗ trong war_room.py.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ui import labels, theme  # noqa: E402

API = os.getenv("API_URL", "https://p-035-incident-agent.onrender.com")
# Chỉ dùng để hỏi metric `up`. Không với tới được thì bỏ qua phần đó, trang vẫn
# chạy — Prometheus chỉ có bản local trong buổi demo.
PROM_URL = os.getenv("PROM_URL", "http://localhost:9090")

#: Địa chỉ API và Prometheus dành cho TRÌNH DUYỆT người xem, khác hai biến trên.
#:
#: `API` / `PROM_URL` là địa chỉ tiến trình Streamlit tự gọi — `localhost`, đi
#: thẳng, không vòng ra internet. Nhưng từ 23/08 trang tự cập nhật theo kiểu SPA:
#: chính trình duyệt người xem đi hỏi số mới, và `localhost` với họ là máy của
#: HỌ. Nên phải có địa chỉ công khai riêng.
#:
#: Trống thì lùi về địa chỉ nội bộ — đúng cho máy chạy local, và khi đó phần tự
#: cập nhật tự tắt thay vì hỏng ngầm (xem `_TU_CAP_NHAT_DUOC`).
API_PUBLIC = os.getenv("API_PUBLIC_URL", "") or API
PROM_PUBLIC = os.getenv("PROM_PUBLIC_URL", "") or PROM_URL

VN_TZ = timezone(timedelta(hours=7))  # Việt Nam không có DST, luôn UTC+7

#: Danh sách dịch vụ trang này theo dõi — NGUỒN DUY NHẤT cho cả lưới thẻ lẫn
#: lưới biểu đồ. Khớp `KNOWN_SERVICES` (src/api/incidents.py) và `scrape_configs`
#: (demo/prometheus.yml).
#:
#: ⚠️ Cố ý KHÔNG chỉ đi theo `services[]` mà `/api/status` trả về. API và UI là
#: HAI service Render deploy riêng, nên bản API đang chạy hoàn toàn có thể còn
#: cũ hơn UI: thêm service ở backend xong, trang vẫn thiếu thẻ cho tới lượt
#: deploy sau — mà không có lỗi nào báo ra. Đó đúng là chuyện đã xảy ra ngày
#: 22/08 với kho-hàng và vận-chuyển.
#:
#: Dịch vụ nào API chưa trả về thì vẫn có thẻ, nhưng ghi rõ `HEALTH_CHUA_CO`.
#: Không mặc định "bình thường": hiện xanh cho một dịch vụ mình không biết gì
#: là kiểu sai tệ nhất một status page có thể mắc.
SERVICES_THEO_DOI: tuple[str, ...] = (
    "service-thanh-toan",
    "service-dat-hang",
    "service-kho-hang",
    "service-van-chuyen",
)

#: Giá trị `health` UI tự đặt, KHÔNG thuộc contract ④ — xem `labels.HEALTH`.
HEALTH_CHUA_CO = "chua-co-du-lieu"

#: Nhịp trang tự lấy số mới, tính bằng giây. Đổi bằng `POLL_SECONDS` trong môi
#: trường, không phải sửa file.
#:
#: ## Vì sao 2 chứ không phải 1
#:
#: Nhịp poll của trang là mắt xích NHỎ NHẤT trong chuỗi. Đường đi thật của một
#: sự cố từ lúc xảy ra tới lúc hiện lên màn hình:
#:
#:   dịch vụ chậm đi
#:     → Prometheus scrape ................. tối đa  5s  (demo/prometheus.yml)
#:     → phải vượt ngưỡng liên tục ......... ít nhất 30s (contract ①)
#:     → Agent quét thấy .................... tối đa 10s  (run_agent DEFAULT_INTERVAL)
#:     → đệm /api/status .................... tối đa  3s  (_TTL_STATUS_GIAY)
#:     → trang poll ......................... tối đa  Ns  ← chỗ này
#:
#: Tổng đã là ~48 giây trước khi tới `N`. Đặt `N = 1` thay vì `5` rút tổng từ
#: ~53s xuống ~49s — tức 8%, mà đổi lại là gấp 5 lần số request.
#:
#: 2 giây là điểm cân: vẫn dưới nhịp scrape 5 giây nên không bao giờ phải chờ
#: thêm trọn một vòng scrape, mà lưu lượng chỉ bằng một nửa so với 1 giây. Dưới
#: 3 giây thì mắt người đọc là "tức thời", nên nhanh hơn nữa không ai nhận ra.
#:
#: Muốn trang nhạy hơn thật thì phải rút `--interval` của Agent (10s), không
#: phải rút nhịp này — đó mới là mắt xích lớn.
#:
#: Chặn dưới 1 giây: 0 là vòng lặp quay không nghỉ.
TU_CAP_NHAT_GIAY = max(1, int(os.getenv("POLL_SECONDS", "2")))

#: Nhịp riêng cho biểu đồ, thưa hơn hẳn.
#:
#: Prometheus `scrape_interval: 5s` (demo/prometheus.yml), nên hỏi lại nhanh hơn
#: 5 giây là **không thể** có điểm dữ liệu mới — chỉ tốn băng thông và CPU vẽ
#: lại. Mỗi lượt là 3 câu `query_range` trả về 30 phút dữ liệu cho 4 dịch vụ;
#: bắn mỗi giây qua tunnel là hàng trăm KB/giây cho mỗi người xem, đổi lấy đúng
#: không có gì.
CHART_MOI_GIAY = 5

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
#
# Token, reset, nút, pill, dòng `↳` lấy từ ui/theme.py. Dưới đây chỉ là phần
# riêng của trang này: lưới thẻ dịch vụ và khối mở đầu.

_CSS = (
    theme.TOKENS_CSS
    + theme.RESET_CSS
    + theme.CHUNG_CSS
    + """
body { overflow-y: auto; }

.app { min-height: 100vh; display: flex; flex-direction: column; }
.header { grid-template-columns: 1fr auto; }
.wrap { width: 100%; max-width: 1080px; margin: 0 auto; padding: 44px 44px 72px; flex: 1; }

/* ═══ Mở đầu ═══ */
.mo-dau { margin-bottom: 36px; }
.mo-dau .sec-eyebrow { display: block; margin-bottom: 12px; }
.mo-dau h1 {
  font-family: var(--font-display);
  font-size: 38px; font-weight: 400;
  letter-spacing: -0.02em; line-height: 1.15;
  color: var(--ink-0);
  margin-bottom: 14px;
}
.mo-dau h1 em { font-style: italic; font-weight: 300; color: var(--ink-1); }
.mo-dau .dan { color: var(--ink-1); font-size: 13.5px; max-width: 640px; }
.mo-dau .hang { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }

/* ═══ Lưới thẻ dịch vụ ═══ */
/* `minmax(320px, ...)` xếp 4 thẻ thành 3 + 1 lẻ loi ở khổ 1080px. 360px đẩy
   xuống 2 cột, thành 2×2 cân, và cùng nhịp với lưới biểu đồ bên dưới.

   `min(360px, 100%)` chứ không phải `360px` trần: `minmax` với cận dưới cố
   định KHÔNG chịu co, nên trên màn 375px cả lưới tràn ngang 99px và trang có
   thanh cuộn ngang. `min()` cho nó rơi về đúng bề ngang khung. */
.luoi { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(360px, 100%), 1fr)); gap: 14px; }
.svc {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 20px;
  transition: border-color 0.15s, background 0.25s ease;
}
.svc.co-su-co { border-color: var(--p1); background: linear-gradient(180deg, var(--p1-soft) 0%, var(--bg-1) 55%); }
.svc.suy-giam { border-color: var(--p2); background: linear-gradient(180deg, var(--p2-soft) 0%, var(--bg-1) 55%); }
/* Dịch vụ đang theo dõi mà API chưa trả về — viền đứt để nhìn là biết thẻ này
   nói "chưa biết", không phải "đã kiểm tra và thấy ổn". */
.svc.chua-ro { border-style: dashed; }
.svc .dau { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 4px; }
.svc .ten {
  font-family: var(--font-display);
  font-size: 21px; font-weight: 400; letter-spacing: -0.015em;
  color: var(--ink-0);
}
.svc .tin { font-size: 13px; color: var(--ink-0); margin-top: 12px; }
.svc .ma-phieu { margin-top: 8px; font-size: 12.5px; color: var(--ink-1); }

/* Ô số trong thẻ — cùng ngôn ngữ với dải vitals của war room, thu nhỏ lại */
.o-so {
  margin-top: 14px; padding-top: 14px;
  border-top: 1px solid var(--border);
}
.o-so .nhan {
  font-family: var(--font-mono);
  font-size: 10px; text-transform: uppercase; letter-spacing: 0.12em;
  color: var(--ink-2); margin-bottom: 8px;
}
.o-so .cau { font-size: 13px; color: var(--ink-0); font-weight: 500; }
.o-so .keo-dai { font-size: 12px; color: var(--ink-1); margin-top: 6px; }
.o-so .con-so {
  font-family: var(--font-display);
  font-size: 26px; font-weight: 400; letter-spacing: -0.02em;
  line-height: 1; margin-bottom: 6px;
  display: flex; align-items: baseline; gap: 6px;
}
.o-so .con-so.bad { color: var(--p1); }
.o-so .con-so .dv { font-family: var(--font-body); font-size: 12.5px; color: var(--ink-1); }

/* ═══ Nút chuyển sang War Room ═══ */
.btn-war-room {
  display: inline-flex; align-items: center; gap: 8px;
  margin-top: 14px; padding: 10px 18px;
  background: var(--p1);
  color: #fff; font-size: 13px; font-weight: 600;
  border: none; border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  text-decoration: none;
  font-family: var(--font-body);
  letter-spacing: 0.01em;
  width: 100%;
  justify-content: center;
}
.btn-war-room:hover {
  filter: brightness(1.15);
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(229, 72, 77, 0.35);
}
.btn-war-room:active { transform: translateY(0); }
.btn-war-room svg { flex-shrink: 0; }

/* ═══ Ô biểu đồ, nằm trong chính thẻ dịch vụ ═══ */
/*
 * Trước 23/08 biểu đồ nằm ở một khối riêng dưới cuối trang. Nghĩa là muốn biết
 * "Kho hàng đang thế nào" phải đọc thẻ ở trên, rồi cuộn xuống tìm đúng ô biểu
 * đồ mang cùng tên — hai lần tra cứu cho một câu hỏi, và tra bằng MẮT nên rất
 * dễ đọc nhầm sang ô bên cạnh. Giờ biểu đồ là một ô `.o-so` như mọi ô số khác
 * trong thẻ, xếp ngay dưới ô `up` của cùng dịch vụ đó.
 */
.o-so-chart .tech { margin-top: 10px; }

/* ⚠️ `height` đặt thẳng lên canvas KHÔNG giữ được. Chart.js chạy
   `responsive: true` + `maintainAspectRatio: false` sẽ tự ghi đè `style` của
   canvas theo kích thước THẺ CHA mỗi lần resize; cha lại là ô tự co theo nội
   dung, nên hai bên đẩy nhau và canvas phình dần. Đo ngày 22/08: bốn ô cùng bề
   ngang mà cao 327 / 446 / 327 / 446 px, lưới so le hẳn.

   Cách Chart.js khuyến nghị: một khung `position: relative` có chiều cao CỐ
   ĐỊNH, canvas trải tuyệt đối bên trong. Cha không còn co theo con nên vòng
   phản hồi đứt. */
.o-so-chart .khung-chart {
  position: relative;
  height: 210px;
  margin-top: 4px;
}
.o-so-chart .khung-chart canvas {
  position: absolute;
  inset: 0;
  width: 100% !important;
  height: 100% !important;
}
.o-so-chart .khong-co {
  text-align: center;
  padding: 28px 0;
  color: var(--ink-2);
  font-size: 12.5px;
}

/* ═══ Chân trang ═══ */
.chan {
  margin-top: 36px; padding-top: 18px;
  border-top: 1px solid var(--border);
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
  font-family: var(--font-mono); font-size: 11.5px; color: var(--ink-2);
}
.chan .day { margin-left: auto; }
.tho {
  background: var(--code-bg);
  border: 1px solid var(--code-border);
  border-radius: 8px;
  padding: 14px 16px;
  margin-top: 10px;
  font-family: var(--font-mono); font-size: 11.5px; line-height: 1.6;
  color: var(--ink-1);
  max-height: 340px; overflow: auto;
  white-space: pre-wrap; word-break: break-word;
}
"""
)


# ---------------------------------------------------------------------------
# Tiện ích
# ---------------------------------------------------------------------------


def e(gia_tri: object) -> str:
    """Thoát HTML. Mọi chuỗi từ API đều phải đi qua đây trước khi vào trang."""
    return html.escape(str(gia_tri), quote=True)


def fmt_time_vn(iso: str) -> str:
    """Định dạng một chuỗi ISO 8601 (UTC) sang giờ Việt Nam, kiểu vi-VN.

    Chuỗi rỗng hay sai định dạng thì trả `"—"`. Một cái gạch ở chân trang là
    chuyện nhỏ; `ValueError` ở đây thì chết cả trang.
    """
    try:
        dt = datetime.fromisoformat(iso).astimezone(VN_TZ)
    except (TypeError, ValueError):
        return "—"
    return dt.strftime("%H:%M:%S %d/%m/%Y")


def pill(chu: str, bien: str) -> str:
    """Nhãn tròn trạng thái. `bien` là ok / warn / bad / info."""
    return f'<span class="pill {bien}"><span class="cham"></span>{e(chu)}</span>'


#: `ServiceHealth` → biến thể pill. Giữ ánh xạ ở một chỗ thay vì rải if/else.
_BIEN_PILL = {
    "operational": "ok",
    "degraded": "warn",
    "down": "bad",
    "maintenance": "info",
    HEALTH_CHUA_CO: "info",
}


@st.cache_data(ttl=10, show_spinner=False)
def load_status() -> dict:
    """Đọc /api/status. Cache 10s để không gọi API mỗi lần Streamlit vẽ lại."""
    response = requests.get(f"{API}/api/status", timeout=60)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=15, show_spinner=False)
def load_up() -> dict[str, float] | None:
    """Metric `up` của từng service, hỏi thẳng Prometheus. None nếu không với tới.

    ⚠️ Cố ý chỉ dùng đúng chữ `up` — một metric trần, không bộ lọc, không đơn vị.
    **Không** chép câu `P95_LATENCY` từ `src/services/prometheus.py` sang đây:
    câu đó là f-string nhiều dòng ghép với bộ lọc `_HAS_TRAFFIC`, chép sang là
    tạo một bản sao lặng lẽ lệch đi khi backend sửa, mà không có gì báo.

    `up` nói được đúng một điều — Prometheus scrape được dịch vụ hay không. Đó
    KHÔNG phải uptime phần trăm: tính uptime cần chuỗi thời gian và một khoảng
    tham chiếu, mà trang này không có. Nên nhãn hiển thị cũng nói đúng chừng ấy.

    ⚠️ Timeout 1 giây: `localhost` phân giải cả `::1` lẫn `127.0.0.1` và urllib3
    thử từng cái với trọn timeout, nên để 2 giây là chờ thật 4 giây khi không có
    Prometheus — mà đó là đường chạy thường xuyên nhất. Đo ngày 17/08.
    """
    try:
        phan_hoi = requests.get(f"{PROM_URL}/api/v1/query", params={"query": "up"}, timeout=1)
        phan_hoi.raise_for_status()
        goi = phan_hoi.json()
    except (requests.RequestException, ValueError):
        return None
    if not isinstance(goi, dict) or goi.get("status") != "success":
        return None

    ket_qua: dict[str, float] = {}
    for series in (goi.get("data") or {}).get("result", []):
        nhan = series.get("metric") or {}
        ten = nhan.get("service") or nhan.get("job")
        try:
            # Endpoint instant: `value` số ít, dạng [timestamp, "giá trị"].
            gia_tri = float(series["value"][1])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if ten:
            ket_qua[str(ten)] = gia_tri
    return ket_qua


#: Các chỉ số vẽ lên biểu đồ. Mỗi tuple: (tên hiển thị, PromQL, đơn vị, màu,
#: id trục y). Câu PromQL lấy nguyên văn theo docs/contracts/01-metrics.md.
#:
#: ⚠️ Ba chỉ số này KHÁC ĐƠN VỊ và lệch biên độ tới hai bậc mười: p95 quanh
#: 0,2–5 (giây), tỷ lệ lỗi 0–100 (%), lưu lượng 0–50 (req/s). Vẽ chung MỘT trục
#: y thì đường nào nhỏ hơn bị ép sát đáy thành một vạch phẳng — nhìn y hệt
#: "không có dữ liệu" trong khi dữ liệu vẫn có. Nên mỗi chỉ số mang `truc` riêng.
PROM_METRICS: list[tuple[str, str, str, str, str]] = [
    (
        "P95 Latency",
        "histogram_quantile(0.95, sum by (le, service) "
        '(rate(http_request_duration_seconds_bucket{handler!="/metrics"}[1m])))',
        "giây",
        "#3B82F6",
        "y",
    ),
    (
        "Error Rate 5xx",
        # Vế `or ... * 0` là CỐ Ý, chép đúng contract ① — thiếu nó thì dịch vụ
        # KHOẺ không có series 5xx nào, phép chia trả RỖNG, và biểu đồ mất hẳn
        # đường "tỷ lệ lỗi" thay vì vẽ một đường 0. Nhìn ra y như hỏng.
        # Vế NaN (mẫu số 0 khi chưa có lưu lượng) thì JS đã đổi thành khoảng
        # trống, nên ở đây không cần `and on(service) (_HAS_TRAFFIC)`.
        "("
        'sum by (service) (rate(http_requests_total{handler!="/metrics", status=~"5.."}[1m]))'
        " or "
        'sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m])) * 0'
        ")"
        ' / sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m]))',
        "%",
        "#E5484D",
        "y1",
    ),
    (
        "Request/s",
        'sum by (service) (rate(http_requests_total{handler!="/metrics"}[1m]))',
        "req/s",
        "#10B981",
        "y2",
    ),
]

#: Cửa sổ thời gian và độ mịn của biểu đồ.
CHART_PHUT = 30
CHART_STEP_GIAY = 15


@st.cache_data(ttl=15, show_spinner=False)
def load_prom_range() -> dict[str, list[dict]] | None:
    """Chuỗi thời gian cho biểu đồ, gom theo tên dịch vụ.

    Trả `{tên service: [{name, unit, color, truc, values}, ...]}` — mỗi dịch vụ
    trong `SERVICES_THEO_DOI` luôn có một khoá. Danh sách rỗng nghĩa là
    Prometheus chạy được nhưng chưa có series nào cho dịch vụ đó: thường vì dịch
    vụ chưa nhận request nào ngoài `/metrics`, mà `/metrics` thì bị lọc ra.

    Trả `None` chỉ khi **không câu nào** hỏi được — tức không với tới Prometheus.

    ⚠️ Trước đây một câu hỏng là `return None` cho cả ba, nên chỉ cần
    `histogram_quantile` sai cú pháp là mất sạch biểu đồ của cả bốn dịch vụ. Giữ
    phần hỏi được thay vì vứt hết.
    """
    ket_thuc = time.time()
    bat_dau = ket_thuc - CHART_PHUT * 60

    theo_service: dict[str, list[dict]] = {ten: [] for ten in SERVICES_THEO_DOI}
    hoi_duoc = 0

    for ten_hien, promql, don_vi, mau, truc in PROM_METRICS:
        try:
            phan_hoi = requests.get(
                f"{PROM_URL}/api/v1/query_range",
                params={
                    "query": promql,
                    "start": bat_dau,
                    "end": ket_thuc,
                    "step": CHART_STEP_GIAY,
                },
                timeout=3,
            )
            phan_hoi.raise_for_status()
            goi = phan_hoi.json()
        except (requests.RequestException, ValueError):
            continue
        if not isinstance(goi, dict) or goi.get("status") != "success":
            continue
        hoi_duoc += 1

        for chuoi in (goi.get("data") or {}).get("result", []):
            nhan = chuoi.get("metric") or {}
            ten_svc = nhan.get("service") or nhan.get("job")
            if ten_svc not in theo_service:
                continue
            theo_service[ten_svc].append(
                {
                    "name": ten_hien,
                    "unit": don_vi,
                    "color": mau,
                    "truc": truc,
                    "values": chuoi.get("values") or [],
                }
            )

    return theo_service if hoi_duoc else None


def gop_services(tu_api: list[dict]) -> list[dict]:
    """Danh sách thẻ sẽ vẽ: `SERVICES_THEO_DOI` là khung, dữ liệu API lấp vào.

    Ba việc trong một hàm, đều cố ý:

    1. **Thứ tự thẻ do UI quyết**, không theo thứ tự API trả về — trang không
       đảo chỗ mỗi lần backend đổi cách sắp xếp.
    2. **Dịch vụ API chưa trả về vẫn có thẻ**, gắn `HEALTH_CHUA_CO`. Đây là cả
       lý do hàm này tồn tại: trước đó lưới đi thẳng theo `services[]` của API,
       nên thêm dịch vụ ở backend mà chưa deploy lại là trang thiếu thẻ, im
       lặng, không lỗi.
    3. **Dịch vụ API trả về mà UI chưa biết tên** vẫn hiện, xếp cuối — thà hiện
       một tên kỹ thuật chưa kịp dịch còn hơn giấu mất một dịch vụ.
    """
    con_lai = {str(svc["name"]): svc for svc in tu_api if svc.get("name")}
    ket_qua: list[dict] = []
    for ten in SERVICES_THEO_DOI:
        ket_qua.append(
            con_lai.pop(ten, None)
            or {"name": ten, "health": HEALTH_CHUA_CO, "message": "", "active_incident": None}
        )
    ket_qua.extend(con_lai.values())
    return ket_qua


def incident_cua(svc: dict, danh_sach: list[dict]) -> dict | None:
    """Incident đang ảnh hưởng dịch vụ này, lấy từ `active_incidents[]`."""
    ma = svc.get("active_incident")
    if ma:
        trung = next((inc for inc in danh_sach if inc.get("jira_key") == ma), None)
        if trung:
            return trung
    return next(
        (inc for inc in danh_sach if svc["name"] in (inc.get("affected_services") or [])), None
    )


# ---------------------------------------------------------------------------
# Mảnh giao diện
# ---------------------------------------------------------------------------


def khoi_chi_so(incident: dict | None) -> str:
    """Ô "chỉ số đang bất thường" của một thẻ. Chuỗi rỗng nếu không có số thật."""
    signal = (incident or {}).get("signal")
    if not signal:
        return ""

    # Lấy đúng bằng chứng của chỉ số đã kích hoạt: nó mới có baseline/unit/promql.
    ev = next(
        (e_ for e_ in (signal.get("evidence") or []) if e_.get("name") == signal.get("metric_name")),
        None,
    ) or {}
    dong = labels.bang_chung(
        signal["metric_name"],
        signal["metric_value"],
        baseline=ev.get("baseline"),
        unit=ev.get("unit", ""),
        promql=ev.get("promql", ""),
    )
    cau, don_vi = labels.metric(signal["metric_name"])
    gia_tri = float(signal["metric_value"])
    so = f"{gia_tri * 100:.0f}" if don_vi == "%" else f"{gia_tri:.3g}"

    keo_dai = ""
    if signal.get("breached_for_seconds"):
        keo_dai = (
            f'<div class="keo-dai">Đã kéo dài '
            f'{e(labels.keo_dai(signal["breached_for_seconds"]))}</div>'
        )
    return (
        '<div class="o-so">'
        '<div class="nhan">Chỉ số đang bất thường</div>'
        f'<div class="con-so bad">{e(so)}<span class="dv">{e(don_vi or "")}</span></div>'
        f'<div class="cau">{e(cau)}</div>'
        f'<div class="tech"><span class="arrow">↳</span>{e(dong.raw)} · ngưỡng '
        f'{e(format(float(signal["threshold"]), "g"))}</div>'
        f"{keo_dai}</div>"
    )


def khoi_up(ten_service: str, bang_up: dict[str, float] | None) -> str:
    """Ô `up`. Rỗng khi không hỏi được Prometheus — bỏ qua chứ không đoán."""
    if bang_up is None or ten_service not in bang_up:
        return ""
    gia_tri = bang_up[ten_service]
    song = gia_tri >= 1
    return (
        '<div class="o-so" data-o="up">'
        '<div class="nhan">Prometheus scrape được không</div>'
        f'<div class="cau">{"Đang phản hồi" if song else "Không phản hồi"}</div>'
        f'<div class="tech"><span class="arrow">↳</span>up = {e(format(gia_tri, "g"))} '
        "— trạng thái tại lúc hỏi, không phải uptime %</div>"
        "</div>"
    )


def the_service(
    svc: dict,
    incident: dict | None,
    bang_up: dict[str, float] | None,
    chi_so: int = 0,
    chuoi: list[dict] | None = None,
) -> str:
    """Một thẻ dịch vụ, HTML thuần.

    Thứ tự các ô trong thẻ đi từ "cần biết" xuống "muốn đào": trạng thái → chỉ
    số đang bất thường → Prometheus có scrape được không → biểu đồ 30 phút →
    nút sang war room.
    """
    suc_khoe = str(svc.get("health", ""))
    _, cau = labels.health(suc_khoe)
    lop = {"down": " co-su-co", "degraded": " suy-giam", HEALTH_CHUA_CO: " chua-ro"}.get(
        suc_khoe, ""
    )

    # Backend đặt `message` = đúng câu trạng thái khi dịch vụ bình thường, nên
    # in cả hai là lặp y nguyên chữ ngay dưới cái nhãn vừa đọc. Chỉ hiện khi nó
    # nói thêm được điều gì.
    tin = str(svc.get("message", "")).strip()
    tin_html = f'<div class="tin">{e(tin)}</div>' if tin and tin != cau else ""
    if suc_khoe == HEALTH_CHUA_CO:
        # Nói thẳng là chưa biết, và nói vì sao — người xem không phải đoán xem
        # thẻ trống nghĩa là "ổn" hay "hỏng".
        tin_html = (
            '<div class="tin"><strong>Không có nghĩa là dịch vụ đang hỏng.</strong> '
            "Dịch vụ vẫn chạy — ô <code>up</code> ngay bên dưới là bằng chứng. Chỉ là "
            f"bản API tại <span class=\"inline-code\">{e(API)}</span> chưa liệt kê dịch "
            "vụ này trong <code>/api/status</code>, nên trang chưa có trạng thái "
            "sức khoẻ để hiển thị. Đây là hai nguồn khác nhau: thẻ trạng thái đọc từ "
            "API, còn các ô số đọc thẳng từ Prometheus.</div>"
        )

    ma_su_co = ""
    nut_war_room = ""
    if svc.get("active_incident"):
        ma = svc["active_incident"]
        ma_su_co = (
            f'<div class="ma-phieu">Mã sự cố đang xử lý: '
            f'<span class="inline-code">{e(ma)}</span></div>'
        )
        # Nút CTA nổi bật: chuyển sang War Room với đúng incident đang xử lý.
        # War room nằm ở `ui/pages/war_room.py` — Streamlit multi-page phục vụ
        # nó tại `/war_room` cùng origin. JS dựng URL từ `data-war-key`.
        nut_war_room = (
            f'<button class="btn-war-room" type="button" '
            f'data-war-key="{e(ma)}" '
            f'title="Mở War Room — xem chi tiết sự cố {e(ma)}">'
            f'{theme.ICON["set"]}Xem chi tiết sự cố'
            f'{theme.ICON["mui_ten"]}</button>'
        )
    # `data-svc` + `data-hinh` là hợp đồng với phần JS tự cập nhật.
    #
    # `data-hinh` ghi lại HÌNH DẠNG thẻ lúc server dựng: có khối sự cố không, có
    # ô chỉ số không, có ô `up` không, có biểu đồ không. JS so hình dạng mới với
    # chuỗi này; **khác nhau thì tải lại cả trang** thay vì cố vá DOM.
    #
    # Vì sao cần cửa đó: cập nhật tại chỗ chỉ an toàn khi thay GIÁ TRỊ. Khi một
    # dịch vụ vừa có sự cố (thẻ mọc thêm ô chỉ số + nút war room) thì phải dựng
    # markup mới — mà dựng markup ở hai nơi, Python một bản JS một bản, là cách
    # chắc chắn để hai bên lệch nhau rồi trang hiện sai. Tải lại là chậm hơn vài
    # trăm mili giây, nhưng luôn đúng.
    hinh = ",".join([
        f"inc:{int(bool(svc.get('active_incident')))}",
        f"sig:{int(bool(khoi_chi_so(incident)))}",
        f"tin:{int(bool(tin_html))}",
        f"up:{int(bool(khoi_up(svc['name'], bang_up)))}",
        f"chart:{0 if chuoi is None else (1 if chuoi else 2)}",
    ])
    return (
        f'<div class="svc{lop}" data-svc="{e(str(svc["name"]))}" data-hinh="{e(hinh)}">'
        f'<div class="dau"><span class="ten">{e(labels.service(svc["name"]))}</span>'
        f'{pill(cau, _BIEN_PILL.get(suc_khoe, "info"))}</div>'
        f'<div class="tech"><span class="arrow">↳</span>{e(svc["name"])}</div>'
        f"{tin_html}"
        f"{ma_su_co}"
        f"{khoi_chi_so(incident)}"
        f"{khoi_up(svc['name'], bang_up)}"
        f"{khoi_bieu_do(chi_so, str(svc['name']), chuoi)}"
        f"{nut_war_room}"
        "</div>"
    )


def khoi_bieu_do(chi_so: int, ten_service: str, chuoi: list[dict] | None) -> str:
    """Ô biểu đồ của MỘT dịch vụ, để xếp vào chính thẻ của dịch vụ đó.

    `chuoi is None` nghĩa là không hỏi được Prometheus — trả chuỗi rỗng, đúng
    quy ước của `khoi_up()`: không có số thì không dựng ô, chứ không dựng một ô
    trống rồi để người xem đoán. Lý do chung nằm ở `ghi_chu_prom` cuối trang.

    `chuoi == []` thì khác hẳn: Prometheus CHẠY, nhưng chưa có series nào cho
    dịch vụ này. Đó là thông tin thật và đáng nói ra.

    `id` của canvas là chỉ số thẻ, tên dịch vụ đi kèm ở `data-service` để JS tra
    dữ liệu. JS cố ý KHÔNG giữ mảng tên riêng: hai danh sách song song lệch nhau
    một phần tử là biểu đồ dán số của dịch vụ này vào tên dịch vụ khác — sai mà
    nhìn vẫn rất bình thường.
    """
    if chuoi is None:
        return ""

    than = (
        '<div class="khung-chart">'
        f'<canvas id="chart-{chi_so}" data-service="{e(ten_service)}"></canvas></div>'
        if chuoi
        else f'<div class="khong-co">Prometheus không có số đo nào cho dịch vụ này '
        f"trong {CHART_PHUT} phút gần nhất. Thường là vì nó chưa nhận request nào "
        "ngoài lần scrape <code>/metrics</code> — mà mọi câu PromQL ở đây đều lọc "
        "<code>/metrics</code> ra. Bắn tải bằng <code>python demo/loadtest.py</code> "
        "là có.</div>"
    )
    return (
        '<div class="o-so o-so-chart">'
        f'<div class="nhan">Số đo {CHART_PHUT} phút gần nhất</div>'
        f"{than}"
        '<div class="tech"><span class="arrow">↳</span>p95 thời gian phản hồi · tỷ lệ '
        "lỗi 5xx · lưu lượng — mỗi chỉ số một trục riêng vì khác đơn vị</div>"
        "</div>"
    )


def khoi_mo_dau(services: list[dict]) -> str:
    """Câu trả lời cho câu hỏi duy nhất người ngoài mang tới trang này."""
    co_su_co = any(s.get("health") == "down" for s in services)
    suy_giam = any(s.get("health") == "degraded" for s in services)
    bao_tri = any(s.get("health") == "maintenance" for s in services)

    # Thứ tự ưu tiên khớp StatusPage.overall_health (src/models/incident.py):
    # down > degraded > maintenance > operational.
    if co_su_co:
        tieu_de, bien, nhan = "Một số dịch vụ <em>đang gặp sự cố</em>", "bad", "Đang có sự cố"
    elif suy_giam:
        tieu_de, bien, nhan = "Một số dịch vụ <em>chậm hơn bình thường</em>", "warn", "Suy giảm"
    elif bao_tri:
        tieu_de, bien, nhan = "Một số dịch vụ <em>đang bảo trì</em>", "info", "Bảo trì"
    else:
        tieu_de, bien, nhan = "Tất cả dịch vụ <em>hoạt động bình thường</em>", "ok", "Bình thường"

    return (
        '<div class="mo-dau">'
        '<span class="sec-eyebrow">Trạng thái dịch vụ</span>'
        f'<div class="hang"><h1>{tieu_de}</h1></div>'
        f'<div class="hang">{pill(nhan, bien)}</div>'
        '<p class="dan">Cập nhật tự động từ số liệu đo được của hệ thống. '
        "Mỗi dịch vụ kèm chỉ số đang bất thường và tên metric gốc, để người trực "
        "kiểm chứng lại được.</p>"
        "</div>"
    )


def _tham_so(ten: str, mac_dinh: str = "") -> str:
    """Đọc query param của tab cha. Chạy ngoài `streamlit run` thì trả mặc định."""
    try:
        gia_tri = st.query_params.get(ten)
    except Exception:  # noqa: BLE001 — bare mode không có script run context
        return mac_dinh
    return str(gia_tri) if gia_tri else mac_dinh


# ---------------------------------------------------------------------------
# Trang
# ---------------------------------------------------------------------------

# `set_page_config` phải chạy trước mọi lệnh Streamlit khác.
st.set_page_config(
    page_title="Trạng thái dịch vụ",
    page_icon="P035",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(theme.CSS_KHUNG, unsafe_allow_html=True)

# Ẩn thanh điều hướng multi-page của Streamlit trên trang CÔNG KHAI.
#
# Từ 22/08 war room nằm ở `ui/pages/war_room.py`, nên Streamlit tự liệt kê nó ở
# sidebar của trang này — tức trang cho khách hàng tự quảng cáo trang nội bộ, nơi
# có số đo, log, đề xuất khắc phục và TÊN NGƯỜI DUYỆT.
#
# ⚠️ Đây là che, KHÔNG phải phân quyền. War room không có xác thực, nên ai biết
# `/war_room` là vào được. Ghi ra để không ai đọc đoạn này rồi tưởng đã an toàn —
# muốn an toàn thật thì cần đăng nhập, chưa có. Xem `docs/demo-runbook.md`.
#
# Nút "Xem chi tiết sự cố" thì GIỮ: nó là chủ ý, để người trực không phải nhớ hai
# địa chỉ.
st.markdown(
    """<style>
    [data-testid="stSidebarNav"] { display: none; }
    [data-testid="stSidebar"] { display: none; }
    [data-testid="collapsedControl"] { display: none; }
    </style>""",
    unsafe_allow_html=True,
)

theme_hien = _tham_so("theme", "dark")
if theme_hien not in ("dark", "light"):
    theme_hien = "dark"

loi = ""
data: dict = {}
try:
    data = load_status()
except requests.RequestException as error:
    loi = str(error)

# ⚠️ Phải có giá trị TRƯỚC khi rẽ nhánh. `TRANG` bên dưới là một f-string có
# tham chiếu `{bieu_do_json}`, nên nhánh lỗi mà không đặt biến này là cả trang
# chết bằng `NameError` ngay lúc dựng chuỗi — người dùng thấy MÀN HÌNH TRẮNG,
# không đọc được chính câu "không gọi được API" mà nhánh đó vừa soạn ra. Mà
# nhánh lỗi lại là nhánh hay gặp nhất: Render free tier ngủ sau 15 phút.
bieu_do_json = "null"
cau_hinh_js = "null"

if loi:
    than = (
        '<div class="wrap"><div class="mo-dau">'
        '<span class="sec-eyebrow">Trạng thái dịch vụ</span>'
        "<h1>Không gọi được <em>API</em></h1></div>"
        f'<div class="note err">{e(loi)}</div>'
        '<p class="hint">Render free tier ngủ sau 15 phút — lần gọi đầu có thể mất khoảng 50 '
        "giây. Nhấn <strong>Làm mới</strong> trên đầu trang để thử lại.</p></div>"
    )
else:
    # Khung thẻ lấy từ `SERVICES_THEO_DOI`, không lấy thẳng `data["services"]` —
    # xem `gop_services()`.
    services = gop_services(data.get("services") or [])
    active_incidents = data.get("active_incidents") or []
    bang_up = load_up()
    # Phải hỏi TRƯỚC khi dựng lưới: từ 23/08 biểu đồ nằm trong chính thẻ dịch
    # vụ, nên `the_service()` cần chuỗi số đo ngay lúc dựng.
    prom_data = load_prom_range()

    if not services:
        luoi = '<div class="note">Chưa có dịch vụ nào được theo dõi.</div>'
    else:
        luoi = (
            '<div class="luoi">'
            + "".join(
                the_service(
                    svc,
                    incident_cua(svc, active_incidents),
                    bang_up,
                    chi_so,
                    None if prom_data is None else (prom_data.get(str(svc["name"])) or []),
                )
                for chi_so, svc in enumerate(services)
            )
            + "</div>"
        )

    # Giữ lại nhưng gấp và đặt tên rõ là dành cho người trực. Đây là trang công
    # khai nên "để tham khảo khi code" đọc ra như trang chưa làm xong.
    ghi_chu_prom = ""
    if bang_up is None or prom_data is None:
        ghi_chu_prom = (
            f'<p class="hint">Không hỏi được Prometheus tại '
            f'<span class="inline-code">{e(PROM_URL)}</span> nên các thẻ không hiện ô '
            "<code>up</code> và không có biểu đồ — bình thường khi trang chạy ngoài "
            "máy có Prometheus. Phần còn lại đọc từ API nên vẫn đủ.</p>"
        )
    import json as _json  # noqa: PLC0415 — chỉ dùng đúng ở khối dữ liệu thô

    # `_json.dumps` chứ không phải str(dict): dict Python in ra `None`/`True`,
    # không phải `null`/`true`, và JS nuốt không nổi.
    bieu_do_json = _json.dumps(prom_data, ensure_ascii=False) if prom_data else "null"

    # Mọi thứ phần JS tự cập nhật cần biết. Gom vào MỘT gói thay vì rải hằng số
    # trong JS: hằng số rải rác là cách để nó lệch khỏi Python lúc nào không hay.
    cau_hinh_js = _json.dumps(
        {
            "api": API_PUBLIC,
            "prom": PROM_PUBLIC,
            "chartPhut": CHART_PHUT,
            "chartStep": CHART_STEP_GIAY,
            "chartMoiGiay": CHART_MOI_GIAY,
            "healthChuaCo": HEALTH_CHUA_CO,
            # Câu tiếng Việt của từng `health`, lấy thẳng từ labels để JS không
            # giữ bản dịch riêng.
            "health": {ma: cau for ma, (_icon, cau) in labels.HEALTH.items()},
            "pill": _BIEN_PILL,
            "lopThe": {"down": " co-su-co", "degraded": " suy-giam", HEALTH_CHUA_CO: " chua-ro"},
            "metrics": [
                {"name": ten, "promql": q, "unit": dv, "color": mau, "truc": tr}
                for ten, q, dv, mau, tr in PROM_METRICS
            ],
        },
        ensure_ascii=False,
    )

    than = (
        '<div class="wrap">'
        + khoi_mo_dau(services)
        + luoi
        + '<div class="chan">'
        + f'<span id="chan-luc">Cập nhật lúc {e(fmt_time_vn(str(data.get("updated_at", ""))))}</span>'
        + f'<span class="day">{e(API)}</span>'
        + "</div>"
        + '<details class="more"><summary>Dữ liệu thô (dành cho người trực)</summary>'
        + ghi_chu_prom
        + f'<div class="tho">{e(_json.dumps(data, ensure_ascii=False, indent=2))}</div>'
        + "</details>"
        + "</div>"
    )

TRANG = f"""<!DOCTYPE html>
<html lang="vi" data-theme="{theme_hien}">
<head>
<meta charset="UTF-8">
{theme.FONTS_LINK}
<style>{_CSS}</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
</head>
<body>
<div class="app">
<header class="header">
  <div class="brand"><div class="brand-mark">W</div>
  <div class="brand-text">Trạng thái <em>hệ thống</em></div></div>
  <div class="header-right">
    <button class="hbtn" type="button" id="btn-war-room-nav"
      title="Mở War Room">{theme.ICON["set"]}War Room</button>
    <button class="hbtn primary" type="button" id="btn-reload"
      title="Tải lại số liệu từ API">{theme.ICON["lam_moi"]}Làm mới</button>
    {theme.NUT_THEME}
  </div>
</header>
{than}
</div>
<script>
{theme.JS_THEME}
document.getElementById('btn-reload').addEventListener('click', function () {{ taiLai(); }});

// ═══════════════ Tự cập nhật tại chỗ, không tải lại trang ═══════════════
//
// Trước 24/08 bộ đếm gọi thẳng `taiLai()` — tải lại CẢ trang mỗi 30 giây. Đúng
// số liệu nhưng nháy màn hình và mất vị trí cuộn, tức trang càng tự làm mới thì
// càng khó đọc.
//
// Làm được kiểu SPA là nhờ một thay đổi ở hạ tầng: từ khi có `api-035` và
// `prom-035` trên tunnel, **trình duyệt người xem tự gọi API và Prometheus
// được**. Trước đó chỉ tiến trình Streamlit gọi được (qua localhost), nên không
// có đường nào lấy số mới ngoài việc dựng lại cả trang.
var CAU_HINH = {cau_hinh_js};

function _e(t) {{
  var d = document.createElement('div');
  d.textContent = (t === null || t === undefined) ? '' : String(t);
  return d.innerHTML;
}}

var _MAY_NOI_BO = ['localhost', '127.0.0.1', '::1', '[::1]'];

// ⚠️ Ghi vào DOM chỉ khi giá trị THẬT SỰ đổi.
//
// Ở nhịp 1 giây, gán đè vô điều kiện gây một lỗi rất khó quy trách nhiệm: mỗi
// lần gán `innerHTML`/`textContent` là trình duyệt **dựng lại node đó**, và
// vùng người dùng đang bôi đen bên trong bị xoá. Người xem thử chọn `up = 1`
// để chép ra thì cứ mỗi giây lại mất vùng chọn — họ sẽ nghĩ chuột hỏng, không
// nghĩ tại trang.
//
// Kèm theo là layout/paint lặp vô ích mỗi giây trên thứ không đổi.
function _datChu(el, chu) {{
  if (el && el.textContent !== chu) el.textContent = chu;
}}
function _datHtml(el, html) {{
  if (el && el.innerHTML !== html) el.innerHTML = html;
}}
function _datLop(el, lop) {{
  if (el && el.className !== lop) el.className = lop;
}}

function _laNoiBo(u) {{
  var h;
  try {{ h = new URL(u, location.href).hostname; }} catch (err) {{ return false; }}
  return _MAY_NOI_BO.indexOf(h) !== -1;
}}

// Trang đã lên tên miền công khai mà API/Prometheus vẫn là `localhost` thì
// `localhost` với người xem là MÁY CỦA HỌ — fetch sẽ hỏng. Phát hiện sớm rồi
// lùi về tải lại trang, thay vì để nó hỏng ngầm mỗi 30 giây.
function _tuCapNhatDuoc() {{
  if (!CAU_HINH) return false;
  if (_MAY_NOI_BO.indexOf(location.hostname) !== -1) return true;
  return !_laNoiBo(CAU_HINH.api) && !_laNoiBo(CAU_HINH.prom);
}}

function _incidentCua(svc, ds) {{
  var i;
  if (svc.active_incident) {{
    for (i = 0; i < ds.length; i++) {{
      if (ds[i].jira_key === svc.active_incident) return ds[i];
    }}
  }}
  for (i = 0; i < ds.length; i++) {{
    var a = ds[i].affected_services || [];
    if (a.indexOf(svc.name) !== -1) return ds[i];
  }}
  return null;
}}

function _layJson(url) {{
  return fetch(url, {{ cache: 'no-store' }}).then(function (r) {{
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }});
}}

function _layUp() {{
  return _layJson(CAU_HINH.prom + '/api/v1/query?query=' + encodeURIComponent('up'))
    .then(function (g) {{
      var ra = {{}};
      (((g || {{}}).data || {{}}).result || []).forEach(function (chuoi) {{
        var nhan = chuoi.metric || {{}};
        var ten = nhan.service || nhan.job;
        if (ten) ra[ten] = parseFloat(chuoi.value[1]);
      }});
      return ra;
    }});
}}

function _layChuoi() {{
  var ketThuc = Math.floor(Date.now() / 1000);
  var batDau = ketThuc - CAU_HINH.chartPhut * 60;

  // Gieo sẵn khoá cho mọi dịch vụ đang hiện: "có khoá nhưng mảng rỗng" nghĩa là
  // Prometheus chạy mà chưa có series — khác hẳn "không hỏi được Prometheus".
  // Đúng quy ước `load_prom_range()` bên Python.
  var theoSvc = {{}};
  Array.prototype.forEach.call(document.querySelectorAll('.svc[data-svc]'), function (el) {{
    theoSvc[el.getAttribute('data-svc')] = [];
  }});

  var viec = CAU_HINH.metrics.map(function (m) {{
    var u = CAU_HINH.prom + '/api/v1/query_range?query=' + encodeURIComponent(m.promql)
      + '&start=' + batDau + '&end=' + ketThuc + '&step=' + CAU_HINH.chartStep;
    return _layJson(u).then(function (g) {{
      (((g || {{}}).data || {{}}).result || []).forEach(function (chuoi) {{
        var nhan = chuoi.metric || {{}};
        var ten = nhan.service || nhan.job;
        if (!ten || !(ten in theoSvc)) return;
        theoSvc[ten].push({{
          name: m.name, unit: m.unit, color: m.color, truc: m.truc,
          values: chuoi.values || []
        }});
      }});
      return true;
    }}).catch(function () {{ return false; }});
  }});

  return Promise.all(viec).then(function (ketQua) {{
    // Không câu nào hỏi được = không với tới Prometheus.
    return ketQua.some(Boolean) ? theoSvc : null;
  }});
}}

function _hinhMoi(svc, inc, bangUp, chuoi) {{
  var cauHealth = CAU_HINH.health[svc.health] || '';
  var tin = String(svc.message || '').trim();
  var coTin = (svc.health === CAU_HINH.healthChuaCo) || (tin && tin !== cauHealth);
  var mangChuoi = chuoi ? chuoi[svc.name] : undefined;
  return [
    'inc:' + (svc.active_incident ? 1 : 0),
    'sig:' + ((inc && inc.signal) ? 1 : 0),
    'tin:' + (coTin ? 1 : 0),
    'up:' + ((bangUp && bangUp[svc.name] !== undefined) ? 1 : 0),
    'chart:' + (!chuoi ? 0 : (mangChuoi && mangChuoi.length ? 1 : 2))
  ].join(',');
}}

function _veThe(el, svc, bangUp) {{
  _datLop(el, ('svc' + (CAU_HINH.lopThe[svc.health] || '')).trim());

  var pill = el.querySelector('.dau .pill');
  if (pill) {{
    _datLop(pill, 'pill ' + (CAU_HINH.pill[svc.health] || 'info'));
    _datHtml(pill, '<span class="cham"></span>' + _e(CAU_HINH.health[svc.health] || svc.health));
  }}

  var tinEl = el.querySelector('.tin');
  if (tinEl && svc.health !== CAU_HINH.healthChuaCo) {{
    _datChu(tinEl, String(svc.message || '').trim());
  }}

  if (svc.active_incident) {{
    _datChu(el.querySelector('.ma-phieu .inline-code'), svc.active_incident);
    var nut = el.querySelector('.btn-war-room');
    if (nut && nut.getAttribute('data-war-key') !== svc.active_incident) {{
      nut.setAttribute('data-war-key', svc.active_incident);
    }}
  }}

  var oUp = el.querySelector('.o-so[data-o="up"]');
  if (oUp && bangUp && bangUp[svc.name] !== undefined) {{
    var v = bangUp[svc.name];
    _datChu(oUp.querySelector('.cau'), v >= 1 ? 'Đang phản hồi' : 'Không phản hồi');
    _datHtml(
      oUp.querySelector('.tech'),
      '<span class="arrow">↳</span>up = ' + _e(v)
        + ' — trạng thái tại lúc hỏi, không phải uptime %'
    );
  }}
}}

function _veChanTrang(luc) {{
  var el = document.getElementById('chan-luc');
  if (!el || !luc) return;
  var d = new Date(luc);
  if (isNaN(d.getTime())) return;
  var o = {{ timeZone: 'Asia/Ho_Chi_Minh', hour12: false }};
  var gio = d.toLocaleTimeString('vi-VN', Object.assign({{
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  }}, o));
  var ngay = d.toLocaleDateString('vi-VN', Object.assign({{
    day: '2-digit', month: '2-digit', year: 'numeric'
  }}, o));
  _datChu(el, 'Cập nhật lúc ' + gio + ' ' + ngay);
}}

// Trả `true` nếu đã cập nhật xong tại chỗ, `false` nếu phải tải lại cả trang.
var _chuoiCu = null;
var _chuoiLuc = 0;
var _chuoiDaVe = null;

// Biểu đồ đi theo nhịp riêng — xem `CHART_MOI_GIAY`. Giữa hai lượt thì dùng lại
// bộ dữ liệu cũ, vì Prometheus cũng chưa có gì mới để trả.
function _chuoiTheoNhip() {{
  var bay_gio = Date.now();
  if (_chuoiCu !== null && bay_gio - _chuoiLuc < CAU_HINH.chartMoiGiay * 1000) {{
    return Promise.resolve(_chuoiCu);
  }}
  return _layChuoi().then(function (c) {{
    _chuoiCu = c;
    _chuoiLuc = bay_gio;
    return c;
  }});
}}

function capNhat() {{
  if (!_tuCapNhatDuoc()) return Promise.resolve(false);

  return Promise.all([
    _layJson(CAU_HINH.api + '/api/status'),
    _layUp().catch(function () {{ return null; }}),
    _chuoiTheoNhip()
  ]).then(function (kq) {{
    var data = kq[0], bangUp = kq[1], chuoi = kq[2];
    var ds = data.active_incidents || [];
    var theo = {{}};
    (data.services || []).forEach(function (s) {{ theo[s.name] = s; }});

    var the = document.querySelectorAll('.svc[data-svc]');
    for (var i = 0; i < the.length; i++) {{
      var el = the[i];
      var svc = theo[el.getAttribute('data-svc')];
      // Dịch vụ biến mất khỏi API → cấu trúc trang đổi, không vá được.
      if (!svc) return false;

      // Không cần đụng tới ô "chỉ số đang bất thường": `signal.metric_value` và
      // `breached_for_seconds` là số ĐÓNG BĂNG lúc phát hiện, không đổi theo
      // thời gian. Nên nó không bao giờ cũ, và JS không phải dựng lại một ô đi
      // qua `labels.bang_chung()` — tức không có bản dịch thứ hai để lệch khỏi
      // Python. Sự cố xuất hiện hay biến mất thì `data-hinh` bắt được ngay dưới.

      var inc = _incidentCua(svc, ds);
      if (_hinhMoi(svc, inc, bangUp, chuoi) !== el.getAttribute('data-hinh')) return false;
    }}

    for (var j = 0; j < the.length; j++) {{
      _veThe(the[j], theo[the[j].getAttribute('data-svc')], bangUp);
    }}
    // Chỉ vẽ lại khi vừa lấy được bộ dữ liệu MỚI; giữa hai nhịp biểu đồ thì
    // `chuoi` là bộ cũ, vẽ lại chỉ tốn CPU.
    if (chuoi && chuoi !== _chuoiDaVe && window.__datChuoi) {{
      _chuoiDaVe = chuoi;
      window.__datChuoi(chuoi);
    }}
    _veChanTrang(data.updated_at);
    return true;
  }}).catch(function () {{
    return false;
  }});
}}

// ═══ Tự cập nhật mỗi giây ═══
//
// Không đếm ngược, không nút bật/tắt, không nháy màn hình: `capNhat()` chỉ thay
// giá trị trong DOM đang có. Người xem không nhận ra nó vừa chạy, và đó là điều
// mong muốn — status page phải luôn đúng "bây giờ" mà không đòi ai chú ý.
//
// `taiLai()` (tải lại cả trang) chỉ còn là ĐƯỜNG LÙI: khi cấu trúc trang phải
// đổi — dịch vụ vừa có sự cố, vừa mất ô `up`, vừa có biểu đồ — hoặc khi trình
// duyệt không với tới được API. Xem `capNhat()`.
(function () {{
  var NHIP = {TU_CAP_NHAT_GIAY} * 1000;
  var dangChay = false;

  function mot_vong() {{
    // Bỏ lượt nếu lượt trước chưa xong. Mạng chậm hơn nhịp gọi thì hàng đợi
    // request sẽ phình vô hạn — kiểu hỏng chỉ lộ ra trên máy người khác.
    if (dangChay) return;
    dangChay = true;
    capNhat().then(function (xong) {{
      dangChay = false;
      if (!xong) taiLai();
    }}).catch(function () {{
      dangChay = false;
    }});
  }}

  setInterval(mot_vong, NHIP);

  // Trình duyệt bóp `setInterval` lại khi tab bị ẩn — đo được: 206 giây thực tế
  // mà bộ đếm chỉ tick khoảng 26 lần. Tab ẩn thì không hỏi cũng đúng, nhưng lúc
  // người ta QUAY LẠI phải cập nhật ngay, đừng bắt chờ hết nhịp.
  document.addEventListener('visibilitychange', function () {{
    if (document.visibilityState === 'visible') mot_vong();
  }});
}})();

// ═══ Nút War Room trên header ═══
document.getElementById('btn-war-room-nav').addEventListener('click', function () {{
  try {{
    var u = new URL(window.parent.location.href);
    u.pathname = u.pathname.replace(/[/]$/, '') + '/war_room';
    u.search = '';
    window.parent.history.replaceState({{}}, '', u.toString());
    window.parent.location.reload();
  }} catch (err) {{
    window.open('/war_room', '_blank');
  }}
}});

// ═══ Nút "Xem chi tiết sự cố" → chuyển sang War Room ═══
// War room nằm cùng Streamlit app tại `/war_room` (multi-page). JS dựng URL
// tương đối từ origin của parent, không cần biến `WAR_ROOM_URL`.
document.querySelectorAll('.btn-war-room').forEach(function (nut) {{
  nut.addEventListener('click', function () {{
    var key = nut.getAttribute('data-war-key');
    if (!key) return;
    var duong = '/war_room?key=' + encodeURIComponent(key);
    var w = window.open(duong, '_blank');
    if (!w) {{
      try {{ window.top.location.href = duong; }} catch (err) {{ window.location.href = duong; }}
    }}
  }});
}});

// ═══ Biểu đồ Prometheus realtime ═══
//
// Dữ liệu nhúng sẵn dưới dạng JSON — trang trong iframe `srcdoc` không gọi
// thẳng Prometheus được (khác origin, không có CORS), nên Python hỏi hộ.
(function () {{
  var chartData = {bieu_do_json};
  var canvases = document.querySelectorAll('.svc canvas[data-service]');
  if (!chartData || !canvases.length) return;

  // Cho phần tự cập nhật thay dữ liệu rồi vẽ lại bằng CHÍNH đường dựng ban đầu —
  // không có bản dựng biểu đồ thứ hai để lệch khỏi bản này.
  window.__datChuoi = function (moi) {{ chartData = moi; veLai(); }};

  // Chart.js tải từ CDN. Mất mạng thì `Chart` không tồn tại và `new Chart(...)`
  // ném TypeError — im lặng trong console, còn trên trang là bốn ô trắng không
  // ai hiểu vì sao. Nói ra một câu thay vì để trống.
  if (typeof Chart === 'undefined') {{
    Array.prototype.forEach.call(canvases, function (canvas) {{
      var hop = document.createElement('div');
      hop.className = 'khong-co';
      hop.textContent = 'Không tải được thư viện biểu đồ (chart.js qua CDN) — máy này '
        + 'đang không ra được internet. Số liệu ở các thẻ phía trên vẫn đúng.';
      // Thay cả `.khung-chart` chứ không chỉ canvas: khung có `height` cố định,
      // để lại là một khoảng trống 220px dưới câu thông báo.
      var khung = canvas.closest('.khung-chart') || canvas;
      khung.parentNode.replaceChild(hop, khung);
    }});
    return;
  }}

  // Trục nào nằm bên nào. `y` (giây) bên trái, hai trục còn lại bên phải.
  var BEN = {{ y: 'left', y1: 'right', y2: 'right' }};

  function mauTheme() {{
    var toi = document.documentElement.getAttribute('data-theme') === 'dark';
    return {{
      toi: toi,
      luoi: toi ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
      chu: toi ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.5)'
    }};
  }}

  function veLai(buocDungLai) {{
    var mau = mauTheme();

    Array.prototype.forEach.call(canvases, function (canvas) {{
      // Tên dịch vụ đọc từ chính thẻ canvas, không từ một mảng cứng trong JS —
      // hai danh sách song song là chỗ chắc chắn sẽ lệch nhau.
      var metrics = chartData[canvas.getAttribute('data-service')];
      if (!metrics || !metrics.length) return;

      var cu = Chart.getChart(canvas);

      var datasets = metrics.map(function (m) {{
        var data = m.values.map(function (v) {{
          var val = parseFloat(v[1]);
          // Prometheus trả "NaN" khi mẫu số bằng 0 (dịch vụ chưa có lưu lượng).
          // `null` + `spanGaps` để đường đứt quãng chứ không rơi xuống 0 — vẽ 0
          // ở đây là bịa ra một khoảng "hoàn toàn không lỗi" chưa từng đo được.
          if (m.unit === '%' && !isNaN(val)) val = val * 100;
          return {{ x: v[0] * 1000, y: isNaN(val) ? null : val }};
        }});
        return {{
          label: m.name + ' (' + m.unit + ')',
          data: data,
          borderColor: m.color,
          backgroundColor: m.color,
          yAxisID: m.truc,
          borderWidth: 1.5,
          pointRadius: 0,
          pointHitRadius: 6,
          // Ba đường chồng nhau mà cùng tô nền thì che nhau hết. Chỉ vẽ nét.
          fill: false,
          tension: 0.3,
          spanGaps: true
        }};
      }});

      var scales = {{
        x: {{
          type: 'linear',
          grid: {{ color: mau.luoi }},
          ticks: {{
            color: mau.chu,
            font: {{ family: 'JetBrains Mono, monospace', size: 10 }},
            maxTicksLimit: 6,
            callback: function (val) {{
              var d = new Date(val);
              return d.toLocaleTimeString('vi-VN', {{ hour: '2-digit', minute: '2-digit' }});
            }}
          }}
        }}
      }};
      // Mỗi chỉ số một trục riêng, tô đúng màu đường của nó để không phải đoán
      // trục nào của đường nào. Chỉ trục trái kẻ lưới ngang — ba lớp lưới chồng
      // lên nhau thì không đọc được gì.
      metrics.forEach(function (m) {{
        scales[m.truc] = {{
          type: 'linear',
          position: BEN[m.truc] || 'left',
          beginAtZero: true,
          grid: {{ color: mau.luoi, drawOnChartArea: m.truc === 'y' }},
          title: {{
            display: true,
            text: m.unit,
            color: m.color,
            font: {{ family: 'JetBrains Mono, monospace', size: 9 }}
          }},
          ticks: {{
            color: m.color,
            maxTicksLimit: 5,
            font: {{ family: 'JetBrains Mono, monospace', size: 9 }}
          }}
        }};
      }});

      // ⚠️ Cùng bộ đường thì THAY SỐ LIỆU tại chỗ, đừng dựng lại biểu đồ.
      //
      // `destroy()` + `new Chart()` mỗi lượt sẽ vứt luôn trạng thái tương tác:
      // ai đang rê chuột đọc tooltip thì cứ mỗi nhịp lại mất, và với 4 biểu đồ
      // thì đó cũng là 4 lần cấp phát canvas vô ích. Đổi màu theo theme mới cần
      // dựng lại — lúc đó `buocDungLai` bật lên.
      if (cu && !buocDungLai
          && cu.data.datasets.length === datasets.length
          && cu.data.datasets.every(function (ds, k) {{ return ds.label === datasets[k].label; }})) {{
        for (var k = 0; k < datasets.length; k++) {{
          cu.data.datasets[k].data = datasets[k].data;
        }}
        cu.update('none');
        return;
      }}
      if (cu) cu.destroy();

      new Chart(canvas.getContext('2d'), {{
        type: 'line',
        data: {{ datasets: datasets }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          interaction: {{ mode: 'index', intersect: false }},
          plugins: {{
            legend: {{
              position: 'top',
              labels: {{
                usePointStyle: true,
                pointStyle: 'circle',
                padding: 16,
                color: mau.chu,
                font: {{ family: 'Inter, sans-serif', size: 11 }}
              }}
            }},
            tooltip: {{
              backgroundColor: mau.toi ? '#1a1d23' : '#fff',
              titleColor: mau.toi ? '#eee' : '#333',
              bodyColor: mau.toi ? '#ccc' : '#555',
              borderColor: mau.toi ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
              borderWidth: 1,
              padding: 10,
              titleFont: {{ family: 'Inter, sans-serif', size: 11 }},
              bodyFont: {{ family: 'JetBrains Mono, monospace', size: 11 }},
              callbacks: {{
                title: function (items) {{
                  if (!items.length) return '';
                  var d = new Date(items[0].parsed.x);
                  return d.toLocaleTimeString('vi-VN', {{ hour: '2-digit', minute: '2-digit', second: '2-digit' }});
                }},
                label: function (ctx) {{
                  var v = ctx.parsed.y;
                  if (v == null) return ctx.dataset.label + ': chưa có số đo';
                  return ctx.dataset.label + ': ' + v.toFixed(3);
                }}
              }}
            }}
          }},
          scales: scales
        }}
      }});
    }});
  }}

  veLai();

  // Nút đổi theme chỉ LẬT `data-theme` chứ không tải lại trang (xem
  // `theme.JS_THEME`). Mọi thứ khác đổi màu theo biến CSS, riêng canvas thì
  // không: màu trục, chú giải, lưới đã nướng cứng vào lúc dựng biểu đồ. Không
  // vẽ lại thì chuyển sang nền sáng xong, chữ trên biểu đồ vẫn là màu của nền
  // tối — mờ tới mức gần như không đọc được.
  new MutationObserver(function () {{ veLai(true); }}).observe(document.documentElement, {{
    attributes: true,
    attributeFilter: ['data-theme']
  }});
}})();
</script>
</body>
</html>
"""

# Cùng lý do và cùng đường lùi như war_room.py.
if hasattr(st, "iframe"):
    st.iframe(TRANG, height="stretch")
else:
    import streamlit.components.v1 as components  # noqa: PLC0415

    # `scrolling=True` vì từ 22/08 trang dài hơn một khung nhìn (thêm khối biểu
    # đồ). Chiều cao giữ 900 chứ không đẩy lên 2400: CSS_KHUNG ép iframe về
    # 100vh nên số này chỉ có nghĩa ở bản Streamlit cũ chưa có `st.iframe`.
    components.html(TRANG, height=900, scrolling=True)
