"""War-room view — trang theo dõi và xử lý sự cố.

CHỦ SỞ HỮU: Long · Đức sửa phần diễn đạt ngày 06/08 (xem WORKLOG cùng ngày)

Chạy:
    streamlit run ui/war_room.py

## Trang này phục vụ HAI người cùng lúc

Đó là ràng buộc thiết kế quan trọng nhất ở đây, và nó quyết định mọi lựa chọn
diễn đạt bên dưới:

- **Người xem không biết tech** (ban giám khảo, quản lý) cần biết chuyện gì đang
  xảy ra với khách hàng, trong vài giây, không cần ai giải thích.
- **Người trực** cần **tên metric gốc và câu PromQL nguyên văn** để copy vào
  Prometheus mà đào tiếp.

Nên nguyên tắc là **dịch THÊM, không dịch THAY**: mỗi dòng bằng chứng có hai
tầng — câu tiếng Việt dẫn đường, dòng kỹ thuật `↳` ngay dưới bằng chữ nhỏ.
Không gấp lại, vì người trực cần thấy ngay.

⚠️ Đừng "tối giản" bằng cách bỏ dòng `↳`. Dịch mất thông tin thì tệ hơn không
dịch: người trực mất đường đào, mà đó là người duy nhất thật sự sửa được sự cố.
Bảng dịch ở [labels.py](labels.py), có test khoá điều này lại.

## Biểu đồ diễn biến lấy số ở đâu

`bieu_do_realtime()` gọi thẳng `GET {PROM_URL}/api/v1/query_range` với **đúng
câu PromQL trong `MetricEvidence.promql` của chính sự cố đang xem**. Không có
"metric mặc định" nào vẽ chung được: mỗi sự cố do một chỉ số khác nhau kích
hoạt, vẽ nhầm chỉ số là minh hoạ cho một câu chuyện khác.

⚠️ Không lấy được dữ liệu thì **không vẽ gì**, kèm câu nói rõ vì sao. Tuyệt đối
không nội suy, không sinh số, không hardcode một mảng cho biểu đồ đỡ trống. Cả
trang này dựng trên luận điểm "chẩn đoán CÓ BẰNG CHỨNG" — một đường bịa phá đúng
thứ nó đang cố chứng minh. Cùng lý do với đoạn cảnh báo dài trong
`link_prometheus()` bên dưới.

⚠️ Cũng đừng gọi `src/services/prometheus.py::query_range()` cho tiện: hàm đó
bọc `avg_over_time(...)` rồi gọi endpoint **instant**, trả về MỘT con số trung
bình mỗi service chứ không phải chuỗi thời gian — vẽ ra đường thẳng. Đằng nào
`ui/` cũng không được import `src/`.
"""

import html
import os
import pathlib
import sys
import urllib.parse
from datetime import UTC, datetime, timedelta, timezone

import plotly.graph_objects as go
import requests
import streamlit as st

# `streamlit run ui/war_room.py` đặt **thư mục ui/** vào sys.path, KHÔNG đặt thư
# mục gốc repo — nên `from ui import labels` sẽ ném ModuleNotFoundError khi chạy
# thật, dù pytest import được bình thường (pytest tự thêm rootdir).
#
# Đo được ngày 06/08: mô phỏng lại sys.path của streamlit thì đúng là
# `ModuleNotFoundError: No module named 'ui'`. Loại lỗi "test xanh mà chạy thật
# vỡ" — cùng họ với vụ `.env` làm test đỏ theo máy hôm 05/08.
#
# Cùng cách `scripts/run_agent.py` đang làm.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ui import labels  # noqa: E402

API = os.getenv("API_URL", "https://p-035-incident-agent.onrender.com")
# Prometheus chỉ chạy local trong buổi demo; không có bản deploy công khai.
PROM_URL = os.getenv("PROM_URL", "http://localhost:9090")
# Chỉ để dựng link "mở phiếu Jira". Không bắt buộc — thiếu thì nút duyệt nói rõ
# phải thao tác ở đâu, chứ KHÔNG giả vờ đã thi hành.
JIRA_URL = os.getenv("JIRA_BASE_URL", "").rstrip("/")

VN_TZ = timezone(timedelta(hours=7))  # Việt Nam không có DST, luôn UTC+7

#: Trạng thái nghĩa là sự cố còn đang diễn ra.
DANG_XAY_RA = ("Open", "Investigating", "Awaiting Approval", "Remediating")

#: Biểu đồ tự vẽ lại mỗi ngần này giây, và cũng là TTL cache của query_range.
#: Prometheus trong demo scrape 5s/lần (demo/prometheus.yml) nên 15s là đủ mới
#: mà không hỏi lại quá dày.
LAM_MOI_GIAY = 15

#: Các khoảng thời gian xem được. Cửa sổ LUÔN kết thúc ở hiện tại.
CUA_SO_GIAY: dict[str, int] = {
    "15 phút": 15 * 60,
    "1 giờ": 60 * 60,
    "6 giờ": 6 * 60 * 60,
    "24 giờ": 24 * 60 * 60,
}
CUA_SO_MAC_DINH = "1 giờ"

#: Trần số điểm mỗi đường — dùng để tính `step`. Nhiều hơn thì Prometheus trả
#: chậm mà mắt cũng không phân biệt được.
SO_DIEM_TOI_DA = 360

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
#
# Quy tắc chọn selector ở đây, vì đã sập một lần khi nâng Streamlit:
#
# 1. CHỈ bám `data-testid` mà Streamlit đặt tên (`stElementContainer`,
#    `stVerticalBlock`, `stExpander`, `stMetric`, `stButton`...), tuyệt đối
#    không bám class kiểu `st-emotion-cache-1r6slb0` — nó đổi mỗi lần build.
# 2. `ui/requirements.txt` cố tình không ghim version Streamlit, nên mọi thứ ở
#    đây phải là *trang trí*: CSS hỏng thì trang xấu đi chứ vẫn đọc được.
#
# ⚠️ Streamlit 1.60 KHÔNG còn `data-testid="stVerticalBlockBorderWrapper"` —
# lớp bọc của `st.container(border=True)` bây giờ chỉ có class hash do emotion
# sinh, không bám được. Nên "thẻ" ở đây tự vẽ lấy: hàm `dau_the()` nhét một
# `<span class="p035-the">` vô hình vào đầu container, rồi CSS chọn đúng khối
# chứa nó.
#
# Mỗi quy tắc thẻ viết bằng HAI selector, cố ý:
#   1. `:has(> [data-testid="stElementContainer"] .p035-the)` — khớp khi marker
#      nằm ngay trong khối, đúng cấu trúc hiện tại.
#   2. `:has(.p035-the):not(:has([data-testid="stVerticalBlock"] .p035-the))` —
#      "khối trong cùng có chứa marker". Còn đúng kể cả khi bản Streamlit sau
#      chèn thêm một lớp bọc vào giữa, mà vẫn không quét trúng các khối cha.
# Thiếu vế `:not(...)` là mọi container cha cũng khớp và cả trang biến thành một
# cái thẻ khổng lồ — đó là lý do không dùng `:has()` trần.
_CSS_TINH = """
.stApp {
  background:
    radial-gradient(1100px 520px at 12% -18%, rgba(56,189,248,.10), transparent 60%),
    radial-gradient(900px 420px at 96% -6%, rgba(239,68,68,.07), transparent 55%),
    var(--p035-nen);
}
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2.4rem; padding-bottom: 4rem; max-width: 1560px; }

h1 { font-weight: 760; letter-spacing: -.03em; }
h2, h3, h4 { letter-spacing: -.02em; }

/* ---- Thẻ (xem chú thích dài bên trên) ---- */
.p035-dau { display: none; }
[data-testid="stElementContainer"]:has(.p035-dau) { display: none; }

[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .p035-the),
[data-testid="stVerticalBlock"]:has(.p035-the):not(:has([data-testid="stVerticalBlock"] .p035-the)) {
  background: var(--p035-the);
  border: 1px solid var(--p035-vien);
  border-radius: 14px;
  padding: 1.05rem 1.2rem;
}

/* Đang chờ duyệt hoặc P1 còn đang diễn ra → viền đỏ neon, thở nhẹ.
   Chỉ dành cho thứ cần người làm gì đó NGAY; dùng rộng ra là mất tác dụng. */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .p035-neon),
[data-testid="stVerticalBlock"]:has(.p035-neon):not(:has([data-testid="stVerticalBlock"] .p035-neon)) {
  border-color: rgba(239,68,68,.62);
  animation: p035-tho 2.6s ease-in-out infinite;
}
@keyframes p035-tho {
  0%, 100% { box-shadow: 0 0 0 1px rgba(239,68,68,.20), 0 0 14px rgba(239,68,68,.18), 0 0 44px rgba(239,68,68,.10); }
  50%      { box-shadow: 0 0 0 1px rgba(239,68,68,.42), 0 0 26px rgba(239,68,68,.36), 0 0 72px rgba(239,68,68,.20); }
}
@media (prefers-reduced-motion: reduce) {
  [data-testid="stVerticalBlock"]:has(.p035-neon) {
    animation: none;
    box-shadow: 0 0 0 1px rgba(239,68,68,.34), 0 0 22px rgba(239,68,68,.28);
  }
}

/* ---- Badge pill ---- */
.p035-pill {
  display: inline-flex; align-items: center; gap: .35rem;
  padding: .16rem .62rem; border-radius: 999px;
  border: 1px solid transparent;
  font-size: .76rem; font-weight: 650; line-height: 1.55;
  white-space: nowrap; vertical-align: middle;
}
.p035-hang-pill { display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; margin-bottom: .55rem; }

/* ---- Đầu trang sự cố ---- */
.p035-dau-trang {
  background: var(--p035-the);
  border: 1px solid var(--p035-vien);
  border-radius: 16px;
  padding: 1.1rem 1.25rem;
  margin-bottom: .9rem;
}
.p035-dau-trang .ma { font-size: .82rem; color: var(--p035-mo); letter-spacing: .06em; font-weight: 650; }
.p035-dau-trang .tieu-de { font-size: 1.22rem; font-weight: 700; line-height: 1.45; margin: .35rem 0 .5rem; }
.p035-dau-trang .meta { font-size: .82rem; color: var(--p035-mo); line-height: 1.85; }
.p035-dau-trang code { font-size: .78rem; }

/* ---- Tiêu đề mục ---- */
.p035-muc { display: flex; align-items: center; gap: .6rem; margin: 1.6rem 0 .35rem; }
.p035-muc .so {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 1.65rem; height: 1.65rem; border-radius: 8px;
  background: rgba(56,189,248,.13); border: 1px solid rgba(56,189,248,.32);
  color: var(--p035-nhan); font-size: .9rem; font-weight: 700;
}
.p035-muc .chu { font-size: 1.08rem; font-weight: 700; letter-spacing: -.01em; }

/* ---- Ô số (metric breakdown) ---- */
.p035-luoi { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: .6rem; margin: .55rem 0 .35rem; }
.p035-so { background: rgba(2,6,23,.55); border: 1px solid var(--p035-vien); border-radius: 12px; padding: .65rem .8rem; }
.p035-so .nhan { font-size: .68rem; letter-spacing: .08em; text-transform: uppercase; color: var(--p035-mo); font-weight: 650; }
.p035-so .gia-tri { font-size: 1.35rem; font-weight: 700; line-height: 1.5; font-variant-numeric: tabular-nums; }
.p035-so .phu { font-size: .74rem; color: var(--p035-mo); line-height: 1.4; }

/* ---- Khối log dạng terminal ---- */
.p035-terminal {
  background: #000000;
  border: 1px solid var(--p035-vien);
  border-radius: 12px;
  padding: .8rem 1rem;
  overflow-x: auto;
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: .78rem;
  line-height: 1.7;
}
.p035-terminal .dong { white-space: pre-wrap; word-break: break-word; }
.p035-terminal .chinh {
  background: rgba(239,68,68,.10);
  border-left: 3px solid var(--p035-do);
  margin: .15rem -1rem; padding: .1rem 1rem .1rem calc(1rem - 3px);
}
.p035-terminal .ts { color: #64748b; }
.p035-terminal .lv { font-weight: 700; }
.p035-terminal .src { color: #7dd3fc; }
.p035-terminal .msg { color: #cbd5e1; }
.p035-terminal .pat { color: var(--p035-tim); }

/* ---- Khối rủi ro / HITL trong thẻ đề xuất ---- */
.p035-hanh-dong { font-size: 1.1rem; font-weight: 700; line-height: 1.6; }
.p035-hanh-dong .mui { color: var(--p035-mo); margin: 0 .3rem; }
.p035-rui-ro {
  background: rgba(245,158,11,.10); border: 1px solid rgba(245,158,11,.42);
  border-left: 4px solid var(--p035-cam);
  border-radius: 10px; padding: .7rem .9rem; margin: .7rem 0;
  font-size: .9rem; line-height: 1.6;
}
.p035-rui-ro .dau-de { color: #fcd34d; font-weight: 700; display: block; margin-bottom: .15rem; }
.p035-hitl {
  background: rgba(239,68,68,.10); border: 1px solid rgba(239,68,68,.42);
  border-radius: 10px; padding: .7rem .9rem; margin: .7rem 0;
  font-size: .9rem; line-height: 1.6;
}

/* ---- Widget Streamlit ---- */
[data-testid="stButton"] > button, .stButton > button,
[data-testid="stLinkButton"] > a, .stLinkButton > a {
  border-radius: 10px;
  transition: transform .12s ease, box-shadow .12s ease, border-color .12s ease;
}
[data-testid="stButton"] > button:hover, .stButton > button:hover,
[data-testid="stLinkButton"] > a:hover, .stLinkButton > a:hover {
  transform: translateY(-1px);
  border-color: var(--p035-nhan);
  box-shadow: 0 6px 18px rgba(56,189,248,.20);
}
[data-testid="stExpander"] details {
  border: 1px solid var(--p035-vien);
  border-radius: 12px;
  background: rgba(2,6,23,.35);
}
[data-testid="stMetric"] {
  background: rgba(2,6,23,.55); border: 1px solid var(--p035-vien);
  border-radius: 12px; padding: .7rem .9rem;
}
[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }
[data-testid="stCaptionContainer"] { line-height: 1.65; }
[data-testid="stAlert"] { border-radius: 12px; }
"""

CSS = "<style>:root{" + "".join(f"--p035-{t}:{m};" for t, m in labels.MAU.items()) + "}" + _CSS_TINH + "</style>"

# `set_page_config` phải chạy trước mọi lệnh Streamlit khác.
st.set_page_config(page_title="War room", page_icon="🚨", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Định dạng
# ---------------------------------------------------------------------------


def fmt_time_vn(iso: str) -> str:
    """Định dạng một chuỗi ISO 8601 (UTC) sang giờ Việt Nam, kiểu vi-VN."""
    dt = datetime.fromisoformat(iso).astimezone(VN_TZ)
    return dt.strftime("%H:%M:%S %d/%m/%Y")


def fmt_duration(start_iso: str, end_iso: str | None = None) -> str:
    """Khoảng thời gian từ `start_iso` tới `end_iso` (hoặc tới hiện tại nếu None).

    "4 phút 20 giây" — thêm "X giờ" phía trước nếu >= 1 giờ.
    """
    start = datetime.fromisoformat(start_iso)
    end = datetime.fromisoformat(end_iso) if end_iso else datetime.now(VN_TZ)
    seconds = max(int((end - start).total_seconds()), 0)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    prefix = f"{hours} giờ " if hours else ""
    return f"{prefix}{minutes} phút {secs} giây"


def link_prometheus(promql: str, luc: str | None) -> str | None:
    """Đường dẫn mở thẳng Prometheus, chạy sẵn câu này TẠI thời điểm sự cố.

    Vì sao phải có mốc thời gian: PromQL trong bằng chứng là truy vấn **tức
    thời** — nó trả giá trị *lúc hỏi*, không phải lúc sự cố. Dán câu đó vào
    Prometheus sau khi sự cố qua thì kết quả **rỗng**, vì cửa sổ `[1m]` không còn
    lưu lượng nào.

    Đo ngày 12/08 trên KAN-23: war room ghi `p95 = 4.42560`; chạy lại câu đó 5
    phút sau khi tắt tải ra rỗng, còn chạy kèm `time=<lúc phát hiện>` ra đúng
    `4.42560`. Cùng một câu, khác nhau ở chỗ hỏi lúc nào.

    Mời người ta kiểm chứng mà đưa câu ra kết quả rỗng thì còn tệ hơn không mời:
    họ sẽ kết luận con số là bịa, trong khi nó đúng.
    """
    if not (promql and luc):
        return None
    try:
        moc = datetime.fromisoformat(luc.replace("Z", "+00:00"))
    except ValueError:
        return None

    # ⚠️ Mốc giờ phải ghi theo UTC, KHÔNG theo giờ Việt Nam.
    #
    # Giao diện Prometheus 3.x đọc/ghi tham số này bằng `moment.utc(t).format(
    # "YYYY-MM-DD HH:mm:ss")` — tức chuỗi luôn được hiểu là UTC, không có vùng
    # giờ đi kèm. Đo ngày 12/08: ghi giờ Việt Nam (`16:53:28`) thì Prometheus
    # hiểu thành 16:53:28 UTC, tức 23:53 giờ VN — một thời điểm ở TƯƠNG LAI chưa
    # có dữ liệu, và trang hiện "Empty query result".
    #
    # Lỗi này im lặng theo cách xấu nhất: câu lệnh vẫn hiện đúng, không có thông
    # báo lỗi nào, chỉ kết quả rỗng — nhìn hệt như số liệu trong war room là bịa.
    dinh_dang = moc.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")

    tham_so = urllib.parse.urlencode(
        {
            "g0.expr": promql,
            # "1" hoặc "table" đều được; giao diện 3.x nhận cả hai.
            "g0.tab": "table",
            "g0.moment_input": dinh_dang,
            "g0.end_input": dinh_dang,
        }
    )
    # `/graph` bị chuyển hướng 302 sang `/query` ở bản 3.x, và chuyển hướng có
    # giữ nguyên query string — nhưng trỏ thẳng `/query` thì bớt được một chặng.
    return f"{PROM_URL}/query?{tham_so}"


def _unix(iso: str | None) -> float | None:
    """Chuỗi ISO → unix timestamp. None nếu không đọc được, không ném lỗi."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _gio_vn(moc: float) -> datetime:
    """Unix timestamp → giờ Việt Nam, **bỏ tzinfo**.

    Bỏ tzinfo là cố ý: plotly.js dựng trục thời gian từ chuỗi ISO và xử lý phần
    bù múi giờ không nhất quán giữa các bản, nên đưa vào giờ VN dạng "trần" là
    chắc chắn nhất — trục đọc ra đúng cái giờ ghi trong `fmt_time_vn()`.

    Khác hẳn `link_prometheus()`: ở đó **bắt buộc** phải quy về UTC vì Prometheus
    hiểu tham số của nó theo UTC. Hai chỗ ngược nhau, đừng "thống nhất" lại.
    """
    return datetime.fromtimestamp(moc, VN_TZ).replace(tzinfo=None)


def _gio_vn_ngan(moc: float) -> str:
    return _gio_vn(moc).strftime("%H:%M:%S %d/%m")


def _so_doc_duoc(gia_tri: float, don_vi: str) -> str:
    """Một con số kèm đơn vị, cùng quy ước với `labels.bang_chung()`.

    Metric tỷ lệ hiện cả hai dạng: phần trăm cho người xem, giá trị thô trong
    ngoặc cho người trực — vì thô mới là con số Prometheus trả về.
    """
    if don_vi == "%":
        return f"{gia_tri * 100:.0f}% (= {gia_tri:g})"
    if don_vi.strip():
        return f"{gia_tri:.3g} {don_vi.strip()}"
    return f"{gia_tri:.3g}"


def _nhan_truc_y(ten_metric: str) -> str:
    """Nhãn trục y — câu tiếng Việt + đơn vị, đều lấy từ `labels.metric()`."""
    cau, don_vi = labels.metric(ten_metric)
    if don_vi == "%":
        # Câu PromQL trả về tỷ lệ 0–1. Giữ nguyên thang đó trên trục để người
        # trực dán câu vào Prometheus là thấy đúng con số đang nhìn.
        return f"{cau} (tỷ lệ 0–1)"
    return f"{cau} ({don_vi.strip()})" if don_vi.strip() else cau


def _lech(gia_tri: float, moc: float | None) -> str | None:
    """`"4.6×"`. Trả None khi không tính được — để chỗ gọi bỏ hẳn ô, không in "None"."""
    if not moc:
        return None
    return f"{gia_tri / moc:.1f}×"


def _rgba(ma: str, dam: float) -> str:
    """`("#ef4444", 0.14)` → `"rgba(239,68,68,0.14)"`.

    Ghép ở Python thay vì dùng `color-mix()` của CSS: `color-mix()` chỉ có ở
    trình duyệt rất mới, mà hỏng nó là badge mất cả nền lẫn viền.
    """
    ma = ma.lstrip("#")
    r, g, b = (int(ma[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{dam})"


# ---------------------------------------------------------------------------
# Mảnh giao diện dùng lại
# ---------------------------------------------------------------------------


def _dat_co(khoa: str, gia_tri: bool) -> None:
    """Callback `on_click` — đặt một cờ trong session_state.

    Dùng callback chứ KHÔNG đặt cờ rồi gọi `st.rerun()`: nút nằm trong
    `@st.fragment`, mà `st.rerun(scope="fragment")` chỉ hợp lệ khi đang ở giữa
    một lần chạy lại của chính fragment đó — bấm nút lúc cả trang đang chạy lại
    thì nó ném `StreamlitAPIException` và vỡ nguyên khối biểu đồ (bắt được khi
    chạy AppTest). Callback chạy TRƯỚC lần vẽ kế tiếp nên cờ đã đúng sẵn, không
    cần rerun tay ở cả hai đường.
    """
    st.session_state[khoa] = gia_tri


def dau_the(*lop: str) -> None:
    """Đánh dấu container đang mở là một "thẻ" để CSS bắt được.

    Xem chú thích dài ở khối CSS: Streamlit 1.60 không còn testid cho lớp bọc
    của `st.container(border=True)`, nên thẻ tự vẽ bằng `:has()`. Span này ẩn
    hoàn toàn, chỉ để CSS có chỗ bám.
    """
    ten = " ".join(("p035-dau", "p035-the", *(x for x in lop if x)))
    st.markdown(f'<span class="{ten}"></span>', unsafe_allow_html=True)


def pill(chu: str, mau: str, *, icon: str = "") -> str:
    """Badge bo tròn. Trả về chuỗi HTML để ghép vào khối khác."""
    noi_dung = f"{icon} {chu}".strip()
    style = f"color:{mau};background:{_rgba(mau, 0.14)};border-color:{_rgba(mau, 0.45)}"
    return f'<span class="p035-pill" style="{style}">{html.escape(noi_dung)}</span>'


def pill_severity(muc: str) -> str:
    """Badge P1–P4 — icon/tên đọc từ `labels.SEVERITY`, màu từ `labels.SEVERITY_MAU`.

    Giữ mã gốc ("P1") ngay trong badge: đó là chữ người trực trao đổi với nhau.
    """
    icon, ten, _ = labels.SEVERITY.get(muc, ("⚪", muc, ""))
    return pill(f"{ten} · {muc}", labels.mau_severity(muc), icon=icon)


def pill_state(trang_thai: str) -> str:
    """Badge trạng thái — đọc từ `labels.STATE`."""
    icon, ten = labels.STATE.get(trang_thai, ("•", trang_thai))
    if trang_thai == "Awaiting Approval":
        mau = labels.MAU["cam"]
    elif trang_thai == "Resolved":
        mau = labels.MAU["xanh"]
    else:
        mau = labels.MAU["nhan"]
    return pill(ten, mau, icon=icon)


def muc(so: str, tieu_de: str) -> None:
    """Tiêu đề một mục lớn, có chip số dẫn mắt."""
    st.markdown(
        f'<div class="p035-muc"><span class="so">{html.escape(so)}</span>'
        f'<span class="chu">{html.escape(tieu_de)}</span></div>',
        unsafe_allow_html=True,
    )


def khoi_promql(promql: str, luc_phat_hien: str | None, *, gap: bool = True) -> None:
    """PromQL trong `st.code()` (bấm là copy) + link mở Prometheus đúng thời điểm.

    `gap=False` cho chỉ số kích hoạt của sự cố: người trực cần nó ngay, không
    phải bấm mở. Các bằng chứng phụ thì gấp lại cho đỡ rối.
    """
    if not promql:
        return

    def _ve() -> None:
        st.code(promql, language="promql")
        link = link_prometheus(promql, luc_phat_hien)
        if link:
            st.markdown(f"[▶ Mở Prometheus và chạy câu này tại lúc xảy ra sự cố]({link})")
            st.caption(
                "Câu này đo **tại thời điểm hỏi**. Bấm link để hỏi đúng lúc sự cố "
                "— dán tay vào Prometheus sau khi sự cố qua sẽ ra rỗng, không phải "
                "vì số liệu sai mà vì đang hỏi nhầm thời điểm."
            )

    if gap:
        with st.expander("PromQL để kiểm chứng lại", expanded=False):
            _ve()
    else:
        _ve()


def ve_bang_chung(evidence: list[dict], luc_phat_hien: str | None = None) -> None:
    """Vẽ danh sách bằng chứng hai tầng: câu tiếng Việt + dòng kỹ thuật.

    Dòng kỹ thuật giữ nguyên văn tên metric, và PromQL nằm trong `st.code()` để
    người trực bấm copy được — đó là cả mục đích của nó.
    """
    for ev in evidence:
        dong = labels.bang_chung(
            ev["name"],
            ev["value"],
            baseline=ev.get("baseline"),
            unit=ev.get("unit", ""),
            promql=ev.get("promql", ""),
        )
        st.markdown(f"**•** {dong.plain}")
        st.caption(f"↳ `{dong.raw}`")
        khoi_promql(dong.promql, luc_phat_hien)


def o_so(nhan: str, gia_tri: str, *, phu: str = "", mau: str = "") -> str:
    """Một ô số trong lưới metric breakdown. Trả về chuỗi HTML."""
    style = f' style="color:{mau}"' if mau else ""
    phu_html = f'<div class="phu">{html.escape(phu)}</div>' if phu else ""
    return (
        '<div class="p035-so">'
        f'<div class="nhan">{html.escape(nhan)}</div>'
        f'<div class="gia-tri"{style}>{html.escape(gia_tri)}</div>'
        f"{phu_html}</div>"
    )


def the_bang_chung(ev: dict, signal: dict | None, luc_phat_hien: str | None) -> None:
    """Một thẻ metric: câu tiếng Việt, lưới số, dòng `↳`, PromQL.

    Chuỗi hiển thị dựng bằng `labels.bang_chung()` — nó đã xử lý sẵn tỷ lệ %,
    đơn vị, và **không bao giờ in ra chữ "None"** khi metric không có baseline.
    """
    dong = labels.bang_chung(
        ev["name"],
        ev["value"],
        baseline=ev.get("baseline"),
        unit=ev.get("unit", ""),
        promql=ev.get("promql", ""),
    )
    _, don_vi = labels.metric(ev["name"])
    gia_tri = float(ev["value"])
    baseline = ev.get("baseline")
    la_kich_hoat = bool(signal) and ev["name"] == signal.get("metric_name")

    if la_kich_hoat:
        st.markdown(f"{pill('chỉ số kích hoạt', labels.MAU['do'], icon='⚡')} **{dong.plain}**", unsafe_allow_html=True)
    else:
        st.markdown(f"**{dong.plain}**")

    o = [o_so("Giá trị hiện tại", _so_doc_duoc(gia_tri, don_vi), mau=labels.MAU["do"] if la_kich_hoat else "")]
    if la_kich_hoat and signal is not None:
        nguong = float(signal["threshold"])
        o.append(o_so("Ngưỡng cảnh báo", _so_doc_duoc(nguong, don_vi), phu="mức bắt đầu coi là sự cố"))
        lech = _lech(gia_tri, nguong)
        if lech:
            o.append(o_so("Mức lệch", lech, phu="so với ngưỡng cảnh báo"))
    if baseline is not None:
        o.append(o_so("Mức thường ngày", _so_doc_duoc(float(baseline), don_vi), phu="baseline đo được"))
        lech_nen = _lech(gia_tri, float(baseline))
        if lech_nen:
            o.append(o_so("Lệch so với thường ngày", lech_nen, phu="cùng chỉ số, lúc bình thường"))

    st.markdown(f'<div class="p035-luoi">{"".join(o)}</div>', unsafe_allow_html=True)
    # Dòng `↳` — KHÔNG gấp vào expander. Người trực cần thấy ngay.
    st.caption(f"↳ `{dong.raw}`")
    # Gấp lại ở đây kể cả với chỉ số kích hoạt: khối (a) bên trên đã mở sẵn câu
    # của nó rồi, bày hai lần cùng một câu chỉ làm loãng.
    khoi_promql(dong.promql, luc_phat_hien)


def khoi_log(hypotheses: list[dict]) -> None:
    """Evidence log — khối terminal đen, tô màu theo `LogEvidence.level`.

    Dữ liệu nằm ở `hypotheses[].log_evidence[]`. Không có log thì **ẩn hẳn**,
    không dựng khung rỗng: khung rỗng đọc ra như trang chưa làm xong.

    ⚠️ Log là dữ liệu từ ngoài (do chính service ghi ra) nên mọi phần nội dung
    đều phải qua `html.escape()` trước khi nhét vào HTML.
    """
    dong_log = [lg for h in hypotheses for lg in (h.get("log_evidence") or [])]
    if not dong_log:
        return

    st.markdown("**Log gốc quanh lúc sự cố**")
    st.caption(
        "Do chính dịch vụ ghi ra, Agent chỉ cắt đoạn quanh thời điểm sự cố chứ không viết lại. "
        "🔴 `ERROR` = lỗi · 🟡 `WARNING` = cảnh báo · 🟢 `INFO` = thông tin."
    )

    dong_html: list[str] = []
    da_danh_dau = False
    for lg in dong_log:
        mucdo = (lg.get("level") or "INFO").upper()
        # Dòng lỗi chính = dòng ERROR đầu tiên. Đó là chỗ mắt cần rơi vào trước.
        chinh = mucdo == "ERROR" and not da_danh_dau
        da_danh_dau = da_danh_dau or chinh
        mau = labels.mau_log(mucdo)
        ts = lg.get("timestamp") or ""
        moc = _unix(ts)
        hien_ts = _gio_vn(moc).strftime("%H:%M:%S") if moc else (ts or "—")
        mau_nen = lg.get("pattern") or ""
        dong_html.append(
            f'<div class="dong{" chinh" if chinh else ""}">'
            f'<span class="ts">[{html.escape(hien_ts)}]</span> '
            f'<span class="lv" style="color:{mau}">[{html.escape(mucdo)}]</span> '
            f'<span class="src">{html.escape(str(lg.get("source", "")))}:</span> '
            f'<span class="msg">{html.escape(str(lg.get("message", "")))}</span>'
            + (f' <span class="pat">⟨{html.escape(mau_nen)}⟩</span>' if mau_nen else "")
            + "</div>"
        )
    st.markdown('<div class="p035-terminal">' + "".join(dong_html) + "</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Biểu đồ diễn biến — số liệu lấy thẳng từ Prometheus, không có nguồn nào khác
# ---------------------------------------------------------------------------


@st.cache_data(ttl=LAM_MOI_GIAY, show_spinner=False)
def truy_van_range(promql: str, bat_dau: int, ket_thuc: int, buoc: int) -> dict:
    """Gọi `GET {PROM_URL}/api/v1/query_range` và trả về các chuỗi thời gian.

    ⚠️ Endpoint **range** trả `data.result[].values` — số nhiều, dạng
    `[[timestamp, "giá trị"], ...]`. Endpoint instant (`/api/v1/query`) trả
    `data.result[].value` — số ít, MỘT điểm. Đọc nhầm sang `value` là biểu đồ ra
    một chấm hoặc một đường phẳng, mà không có lỗi nào báo ra.

    Trả về `{"ok": bool, "loi": str | None, "chuoi": [...]}` thay vì ném lỗi:
    chỗ gọi cần phân biệt "không với tới được Prometheus" (bình thường khi UI
    trỏ sang bản trên Render) với "hỏi được nhưng không có dữ liệu" — hai câu
    giải thích cho người xem khác hẳn nhau.
    """
    try:
        phan_hoi = requests.get(
            f"{PROM_URL}/api/v1/query_range",
            params={"query": promql, "start": bat_dau, "end": ket_thuc, "step": f"{buoc}s"},
            timeout=10,
        )
        phan_hoi.raise_for_status()
        goi = phan_hoi.json()
    except requests.RequestException as loi:
        return {"ok": False, "loi": str(loi), "chuoi": []}
    except ValueError as loi:  # trả về không phải JSON
        return {"ok": False, "loi": f"phản hồi không đọc được: {loi}", "chuoi": []}

    if goi.get("status") != "success":
        return {"ok": False, "loi": str(goi.get("error") or "Prometheus từ chối câu truy vấn"), "chuoi": []}

    chuoi: list[dict] = []
    for series in (goi.get("data") or {}).get("result", []):
        diem: list[tuple[float, float]] = []
        for cap in series.get("values", []):
            try:
                moc, gia_tri = float(cap[0]), float(cap[1])
            except (TypeError, ValueError, IndexError):
                continue  # "NaN" / "+Inf" / dòng hỏng — bỏ điểm đó, không đoán thay
            if gia_tri != gia_tri:  # NaN
                continue
            diem.append((moc, gia_tri))
        if diem:
            chuoi.append({"nhan": _ten_chuoi(series.get("metric") or {}), "diem": diem})
    return {"ok": True, "loi": None, "chuoi": chuoi}


def _ten_chuoi(nhan_metric: dict) -> str:
    """Tên một đường trong biểu đồ, lấy từ nhãn Prometheus trả về."""
    for khoa in ("service", "job", "instance", "__name__"):
        if nhan_metric.get(khoa):
            return str(nhan_metric[khoa])
    return ", ".join(f"{k}={v}" for k, v in sorted(nhan_metric.items())) or "giá trị"


def _khoang_vuot(diem: list[tuple[float, float]], nguong: float, vuot_len: bool) -> list[tuple[float, float]]:
    """Các đoạn liên tiếp mà giá trị nằm sai phía của ngưỡng."""
    khoang: list[tuple[float, float]] = []
    dau: float | None = None
    cuoi: float | None = None
    for moc, gia_tri in diem:
        if (gia_tri >= nguong) if vuot_len else (gia_tri <= nguong):
            if dau is None:
                dau = moc
            cuoi = moc
        elif dau is not None and cuoi is not None:
            khoang.append((dau, cuoi))
            dau = None
    if dau is not None and cuoi is not None:
        khoang.append((dau, cuoi))
    return khoang


#: Màu cho các đường không phải service đang bị ảnh hưởng.
_MAU_PHU = ("#818cf8", "#2dd4bf", "#f472b6", "#facc15")


def dung_bieu_do(
    chuoi: list[dict],
    *,
    ten_metric: str,
    nguong: float | None,
    baseline: float | None,
    vuot_len: bool,
    phat_hien: float | None,
    bat_dau: int,
    ket_thuc: int,
    buoc: int,
    dich_vu_chinh: str,
) -> go.Figure:
    """Dựng figure từ các chuỗi ĐÃ lấy được. Hàm này không tự sinh điểm nào."""
    _, don_vi = labels.metric(ten_metric)
    fig = go.Figure()

    # Service bị ảnh hưởng vẽ đậm và xếp trước; các service khác vẫn hiện đủ,
    # chỉ mờ đi — không giấu dữ liệu, chỉ sắp thứ tự đọc.
    xep = sorted(chuoi, key=lambda c: c["nhan"] != dich_vu_chinh)
    for i, duong in enumerate(xep):
        chinh = duong["nhan"] == dich_vu_chinh or len(xep) == 1
        ten_dep = labels.service(duong["nhan"])
        fig.add_trace(
            go.Scatter(
                x=[_gio_vn(moc) for moc, _ in duong["diem"]],
                y=[gia_tri for _, gia_tri in duong["diem"]],
                mode="lines",
                name=ten_dep if ten_dep == duong["nhan"] else f"{ten_dep} ({duong['nhan']})",
                # `shape="linear"`: không làm mượt. Spline vẽ đẹp hơn nhưng bịa
                # ra đoạn cong giữa hai điểm đo — đúng thứ trang này không làm.
                line={"width": 2.6 if chinh else 1.4, "color": labels.MAU["nhan"] if chinh else _MAU_PHU[i % len(_MAU_PHU)], "shape": "linear"},
                opacity=1.0 if chinh else 0.55,
                hovertemplate="%{y:.4g}<br>%{x|%H:%M:%S %d/%m}<extra>%{fullData.name}</extra>",
            )
        )

    if nguong is not None:
        vuot_x: list[datetime] = []
        vuot_y: list[float] = []
        for duong in xep:
            for moc, gia_tri in duong["diem"]:
                if (gia_tri >= nguong) if vuot_len else (gia_tri <= nguong):
                    vuot_x.append(_gio_vn(moc))
                    vuot_y.append(gia_tri)
        if vuot_x:
            fig.add_trace(
                go.Scatter(
                    x=vuot_x,
                    y=vuot_y,
                    mode="markers",
                    name="Điểm vượt ngưỡng",
                    marker={"size": 6, "color": labels.MAU["do"], "line": {"width": 1, "color": "#fecaca"}},
                    hovertemplate="Vượt ngưỡng: %{y:.4g}<br>%{x|%H:%M:%S}<extra></extra>",
                )
            )
            dinh = (max if vuot_len else min)(range(len(vuot_y)), key=lambda i: vuot_y[i])
            fig.add_annotation(
                x=vuot_x[dinh],
                y=vuot_y[dinh],
                text=f"Đột biến · {_so_doc_duoc(vuot_y[dinh], don_vi)}",
                showarrow=True,
                arrowhead=2,
                arrowsize=1,
                arrowcolor=labels.MAU["do"],
                ax=0,
                ay=-40,
                font={"color": "#fecaca", "size": 11},
                bgcolor="rgba(69,10,10,.85)",
                bordercolor=labels.MAU["do"],
                borderwidth=1,
                borderpad=3,
            )

        # Tô nhạt các đoạn đang vượt ngưỡng, tính trên đường chính.
        for t0, t1 in _khoang_vuot(xep[0]["diem"], nguong, vuot_len)[:20]:
            fig.add_vrect(
                x0=_gio_vn(t0).isoformat(),
                x1=_gio_vn(t1 + buoc).isoformat(),
                fillcolor="rgba(239,68,68,.11)",
                line_width=0,
                layer="below",
            )

        fig.add_hline(
            y=nguong,
            line={"color": labels.MAU["do"], "width": 1.6, "dash": "dash"},
            annotation_text=f"Ngưỡng cảnh báo {_so_doc_duoc(nguong, don_vi)}",
            annotation_position="top left",
            annotation_font_color="#fca5a5",
            annotation_font_size=11,
        )

    # Chỉ vẽ khi thật sự có baseline. Không có thì không nói gì về baseline —
    # cùng nguyên tắc với `labels.bang_chung()`.
    if baseline is not None:
        fig.add_hline(
            y=baseline,
            line={"color": labels.MAU["mo"], "width": 1.3, "dash": "dot"},
            annotation_text=f"Mức thường ngày {_so_doc_duoc(baseline, don_vi)}",
            annotation_position="bottom left",
            annotation_font_color="#cbd5e1",
            annotation_font_size=11,
        )

    if phat_hien is not None and bat_dau <= phat_hien <= ket_thuc:
        fig.add_vline(
            x=_gio_vn(phat_hien).isoformat(),
            line={"color": labels.MAU["cam"], "width": 1.6, "dash": "dot"},
            annotation_text="AI phát hiện",
            annotation_position="top right",
            annotation_font_color="#fcd34d",
            annotation_font_size=11,
        )

    # Trục y phải chứa cả ngưỡng lẫn baseline, nếu không hai đường đó nằm ngoài
    # khung và người xem tưởng chỉ số chưa vượt gì cả.
    tat_ca = [gia_tri for duong in xep for _, gia_tri in duong["diem"]]
    tat_ca += [x for x in (nguong, baseline) if x is not None]
    thap, cao = min(tat_ca), max(tat_ca)
    bien = (cao - thap) * 0.18 if cao > thap else (abs(cao) * 0.2 or 1.0)
    duoi = thap - bien
    if thap >= 0 and duoi < 0:
        duoi = 0.0  # chỉ số vốn không âm thì đừng kéo trục xuống dưới 0

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 10, "r": 10, "t": 46, "b": 10},
        height=340,
        hovermode="x unified",
        font={"color": "#cbd5e1", "size": 12},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.03, "xanchor": "left", "x": 0, "bgcolor": "rgba(0,0,0,0)"},
        xaxis={
            "gridcolor": "rgba(148,163,184,.10)",
            "linecolor": "rgba(148,163,184,.22)",
            "range": [_gio_vn(bat_dau).isoformat(), _gio_vn(ket_thuc).isoformat()],
            "title": None,
        },
        yaxis={
            "gridcolor": "rgba(148,163,184,.10)",
            "linecolor": "rgba(148,163,184,.22)",
            "title": {"text": _nhan_truc_y(ten_metric), "font": {"size": 11, "color": labels.MAU["mo"]}},
            "range": [duoi, cao + bien],
        },
    )
    return fig


@st.fragment(run_every=LAM_MOI_GIAY)
def bieu_do_realtime(jira_key: str, signal: dict, luc_phat_hien: str, dich_vu_chinh: str) -> None:
    """Biểu đồ diễn biến của đúng chỉ số đã kích hoạt sự cố này.

    Cửa sổ **luôn kết thúc ở hiện tại** và tự vẽ lại mỗi `LAM_MOI_GIAY` giây
    (`st.fragment`) — chỉ khối này chạy lại, không rerun cả trang.

    ⚠️ Chốt trung thực: cửa sổ luôn bám hiện tại nghĩa là với sự cố cũ, mốc phát
    hiện có thể đã trôi ra ngoài khung. Khi đó phải nói thẳng ra, kèm nút mở
    rộng khoảng xem. Im lặng hiện một đường phẳng rồi để người xem tưởng đó là
    lúc sự cố thì còn tệ hơn không vẽ.
    """
    bang_chung = [ev for ev in (signal.get("evidence") or []) if ev.get("promql")]
    if not bang_chung:
        st.caption(
            "Không vẽ được biểu đồ: bằng chứng của sự cố này không kèm câu PromQL nào nên "
            "không biết phải hỏi Prometheus câu gì. Các con số bên dưới vẫn là số đo thật."
        )
        return

    ten_kich_hoat = signal.get("metric_name", "")
    mac_dinh = next((i for i, ev in enumerate(bang_chung) if ev["name"] == ten_kich_hoat), 0)
    if len(bang_chung) > 1:
        # Nhãn giữ cả hai tầng: câu tiếng Việt cho người xem, tên gốc cho người trực.
        chon = st.selectbox(
            "Chỉ số muốn xem",
            range(len(bang_chung)),
            index=mac_dinh,
            format_func=lambda i: f"{labels.metric(bang_chung[i]['name'])[0]}  ·  {bang_chung[i]['name']}",
            key=f"chon-metric-{jira_key}",
        )
    else:
        chon = 0
    ev = bang_chung[chon]

    khoa_mo_rong = f"mo-rong-{jira_key}"
    cot_chon, cot_nut = st.columns([3, 1])
    with cot_chon:
        nhan_cua_so = st.radio(
            "Khoảng thời gian (luôn tính tới bây giờ)",
            list(CUA_SO_GIAY),
            index=list(CUA_SO_GIAY).index(CUA_SO_MAC_DINH),
            horizontal=True,
            key=f"cua-so-{jira_key}",
        )
    with cot_nut:
        st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
        # `on_click` xoá cache trước khi khối này vẽ lại — xem `_dat_co()`.
        st.button("🔄 Làm mới", key=f"lam-moi-{jira_key}", on_click=truy_van_range.clear, use_container_width=True)

    # Làm tròn mốc kết thúc xuống bội số `LAM_MOI_GIAY` để cache còn dùng được:
    # để nguyên giây hiện tại thì mỗi lần vẽ là một khoá cache mới.
    ket_thuc = int(datetime.now(UTC).timestamp() // LAM_MOI_GIAY * LAM_MOI_GIAY)
    phat_hien = _unix(luc_phat_hien)

    mo_rong = bool(st.session_state.get(khoa_mo_rong)) and phat_hien is not None
    if mo_rong and phat_hien is not None:
        do_dai = max(int(ket_thuc - phat_hien) + 300, CUA_SO_GIAY[nhan_cua_so])
    else:
        do_dai = CUA_SO_GIAY[nhan_cua_so]
    bat_dau = ket_thuc - do_dai
    buoc = max(15, -(-do_dai // SO_DIEM_TOI_DA))

    if mo_rong:
        st.caption(
            f"Đang mở rộng khoảng xem để chứa mốc phát hiện ({fmt_time_vn(luc_phat_hien)}) — "
            f"tổng {fmt_duration(luc_phat_hien)} tính tới bây giờ."
        )
        st.button("↩ Về khoảng mặc định", key=f"thu-lai-{jira_key}", on_click=_dat_co, args=(khoa_mo_rong, False))
    elif phat_hien is not None and phat_hien < bat_dau:
        st.warning(
            f"⚠️ **Mốc AI phát hiện sự cố ({fmt_time_vn(luc_phat_hien)}) nằm ngoài khoảng đang xem.** "
            f"Đường bên dưới là {nhan_cua_so} gần đây nhất — **không phải** diễn biến lúc xảy ra sự cố."
        )
        st.button(
            "⤺ Mở rộng khoảng xem tới lúc xảy ra sự cố",
            key=f"nhay-{jira_key}",
            on_click=_dat_co,
            args=(khoa_mo_rong, True),
        )

    ket_qua = truy_van_range(ev["promql"], bat_dau, ket_thuc, buoc)

    if not ket_qua["ok"]:
        st.info(
            "**Biểu đồ cần Prometheus chạy local** (mặc định `http://localhost:9090`). "
            "Không với tới được nên không vẽ gì — phần còn lại của trang vẫn dùng bình thường. "
            "Đây là chuyện bình thường khi UI đang trỏ sang backend trên Render: Prometheus "
            "không có bản deploy công khai."
        )
        st.caption(f"↳ `{PROM_URL}` — {ket_qua['loi']}")
        return

    if not ket_qua["chuoi"]:
        st.info(
            "**Prometheus trả về rỗng cho khoảng đang xem.** Không có điểm dữ liệu nào, nên "
            "không vẽ gì cả — thường là do sự cố xảy ra ngoài thời gian Prometheus còn lưu, "
            "hoặc dịch vụ chưa có lưu lượng trong khoảng này."
        )
        st.caption("↳ câu đã hỏi (copy được, dán thẳng vào Prometheus):")
        st.code(ev["promql"], language="promql")
        return

    la_kich_hoat = ev["name"] == ten_kich_hoat
    nguong = float(signal["threshold"]) if la_kich_hoat else None
    baseline = float(ev["baseline"]) if ev.get("baseline") is not None else None
    # Hướng vượt suy ra từ chính dữ liệu: `up` vượt ngưỡng khi TỤT xuống 0, còn
    # p95 hay tỷ lệ lỗi thì vượt khi tăng lên. Đoán theo tên metric là sai sớm.
    vuot_len = la_kich_hoat and float(signal["metric_value"]) >= float(signal["threshold"])

    fig = dung_bieu_do(
        ket_qua["chuoi"],
        ten_metric=ev["name"],
        nguong=nguong,
        baseline=baseline,
        vuot_len=vuot_len,
        phat_hien=phat_hien,
        bat_dau=bat_dau,
        ket_thuc=ket_thuc,
        buoc=buoc,
        dich_vu_chinh=dich_vu_chinh,
    )
    st.plotly_chart(fig, config={"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]})

    if not la_kich_hoat:
        st.caption(
            "Không vẽ đường ngưỡng ở đây: ngưỡng trong tín hiệu là ngưỡng của chỉ số **kích hoạt** "
            f"(`{ten_kich_hoat}`), không áp cho chỉ số đang xem."
        )
    st.caption(
        f"↳ `query_range` trên `{PROM_URL}` · bước {buoc}s · "
        f"{_gio_vn_ngan(bat_dau)} → {_gio_vn_ngan(ket_thuc)} (giờ VN) · tự làm mới mỗi {LAM_MOI_GIAY} giây"
    )


# ---------------------------------------------------------------------------
# Khối lớn của trang
# ---------------------------------------------------------------------------


def the_incident(inc: dict) -> None:
    """Một thẻ trong danh sách bên trái."""
    is_selected = inc["jira_key"] == st.session_state["selected_key"]
    # Neon chỉ dành cho thứ đang cháy. Sự cố đã đóng thì dù từng là P1 cũng
    # không phát sáng — cùng lý do với đoạn "đã đóng thì trạng thái đứng trước
    # mức nghiêm trọng" ở phần chi tiết: đỏ rực trên một sự cố đã xử lý xong làm
    # người xem hiểu ngược mất một hai giây, đủ để hoảng.
    khan = inc["state"] in DANG_XAY_RA and (inc["state"] == "Awaiting Approval" or inc["severity"] == "P1")
    with st.container():
        dau_the("p035-neon" if khan else "")
        st.markdown(
            f'<div class="p035-hang-pill">{pill_severity(inc["severity"])}{pill_state(inc["state"])}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"**{inc['jira_key']}**")
        if inc.get("resolved_at"):
            st.caption(f"Đã kéo dài {fmt_duration(inc['detected_at'], inc['resolved_at'])}")
        else:
            st.caption(f"Đang kéo dài {fmt_duration(inc['detected_at'])}")
        if inc["state"] == "Awaiting Approval":
            st.error("⏸ **CẦN NGƯỜI DUYỆT**")
        if st.button(
            "📂 Đang xem" if is_selected else "Xem chi tiết",
            key=f"sel-{inc['jira_key']}",
            type="primary" if is_selected else "secondary",
            use_container_width=True,
        ):
            st.session_state["selected_key"] = inc["jira_key"]
            st.rerun()


def dau_trang_incident(incident: dict) -> None:
    """Đầu trang chi tiết: hậu quả với người dùng trước, số liệu sau."""
    # Sự cố ĐÃ ĐÓNG thì trạng thái phải đứng trước mức nghiêm trọng.
    #
    # Bản cũ luôn dựng "🔴 Nghiêm trọng — nhiều khách hàng bị ảnh hưởng (P1)" ở
    # dòng to nhất, kể cả khi sự cố đã xử lý xong từ lâu. Người xem đọc dòng to
    # màu đỏ trước rồi mới thấy dòng "Đã xử lý xong" nhỏ hơn bên dưới — tức hiểu
    # ngược trong khoảng một hai giây, đủ để hoảng.
    da_xong_roi = bool(incident.get("resolved_at"))
    if da_xong_roi:
        hang = pill_state(incident["state"]) + pill_severity(incident["severity"])
        ghi_chu = f"Mức lúc xảy ra: {html.escape(labels.severity(incident['severity']))}"
    else:
        hang = pill_severity(incident["severity"]) + pill_state(incident["state"])
        _, _, giai_thich = labels.SEVERITY.get(incident["severity"], ("", "", ""))
        ghi_chu = html.escape(giai_thich)

    dich_vu = " · ".join(
        f"{html.escape(labels.service(s))} (<code>{html.escape(s)}</code>)" for s in incident["affected_services"]
    )
    thoi_gian = f"Phát hiện {fmt_time_vn(incident['detected_at'])}"
    if incident.get("resolved_at"):
        thoi_gian += f" · Đã xử lý {fmt_time_vn(incident['resolved_at'])}"
        thoi_gian += f" · Kéo dài {fmt_duration(incident['detected_at'], incident['resolved_at'])}"
    else:
        thoi_gian += f" · Đang kéo dài {fmt_duration(incident['detected_at'])}"

    st.markdown(
        '<div class="p035-dau-trang">'
        f'<div class="p035-hang-pill">{hang}</div>'
        f'<div class="ma">{html.escape(incident["jira_key"])}</div>'
        f'<div class="tieu-de">{html.escape(incident["title"])}</div>'
        f'<div class="meta">{ghi_chu}<br>Dịch vụ ảnh hưởng: {dich_vu}<br>{html.escape(thoi_gian)}</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def bang_dieu_tra(incident: dict, signal: dict | None) -> None:
    """Investigation panel — ba tầng: lỗi gì, số liệu, log gốc."""
    hypotheses = incident.get("hypotheses") or []
    luc = incident["detected_at"]

    if not signal:
        st.caption("Chưa có tín hiệu gốc — sự cố này tạo trước khi Agent lưu lại tín hiệu.")
        khoi_log(hypotheses)
        return

    cau, don_vi = labels.metric(signal["metric_name"])
    kich_hoat = next(
        (ev for ev in (signal.get("evidence") or []) if ev["name"] == signal["metric_name"]),
        None,
    )

    # ── (a) Lỗi gì
    with st.container():
        dau_the()
        st.markdown(f"#### ⚠️ {html.escape(cau)} vượt ngưỡng")
        st.markdown(
            f"**{cau}** đang ở mức **{_so_doc_duoc(float(signal['metric_value']), don_vi)}**, "
            f"trong khi ngưỡng cảnh báo là **{_so_doc_duoc(float(signal['threshold']), don_vi)}**."
        )
        # Dòng `↳` giữ nguyên văn tên metric — người trực grep đúng chữ này.
        st.caption(
            f"↳ `{signal['metric_name']} = {signal['metric_value']:g}` "
            f"(ngưỡng `{signal['threshold']:g}`, dịch vụ `{signal.get('affected_service', '')}`)"
        )
        st.info(f"⏱ Đã kéo dài {labels.keo_dai(signal['breached_for_seconds'])}")
        if kich_hoat is not None:
            khoi_promql(kich_hoat.get("promql", ""), luc, gap=False)

        st.markdown("**Diễn biến chỉ số theo thời gian**")
        bieu_do_realtime(
            incident["jira_key"],
            signal,
            luc,
            signal.get("affected_service") or (incident["affected_services"] or [""])[0],
        )

    # ── (b) Metric breakdown
    st.markdown("##### Số liệu chi tiết")
    bang_chung = signal.get("evidence") or []
    if bang_chung:
        for ev in bang_chung:
            with st.container():
                dau_the()
                the_bang_chung(ev, signal, luc)
    else:
        st.caption("Tín hiệu này không kèm bằng chứng số nào ngoài chỉ số kích hoạt bên trên.")

    # ── (c) Evidence log
    khoi_log(hypotheses)


def the_de_xuat(incident: dict, proposal: dict) -> None:
    """AI Agent Recommendation — hành động, rủi ro, và chỗ duyệt thật."""
    with st.container():
        dau_the("p035-neon" if incident["state"] == "Awaiting Approval" else "")

        # (1) Hành động
        st.markdown(
            '<div class="p035-hanh-dong">🛠 '
            f"{html.escape(labels.action(proposal['action']))}"
            '<span class="mui">→</span>'
            f"<code>{html.escape(str(proposal['target']))}</code></div>",
            unsafe_allow_html=True,
        )
        if proposal.get("params"):
            st.caption(f"↳ tham số: `{proposal['params']}`")

        # (2) Rủi ro
        if proposal.get("risk"):
            st.markdown(
                '<div class="p035-rui-ro"><span class="dau-de">⚠️ Đánh đổi cần cân nhắc</span>'
                f"{html.escape(proposal['risk'])}</div>",
                unsafe_allow_html=True,
            )

        if proposal.get("requires_approval"):
            st.markdown(
                '<div class="p035-hitl">🔒 <b>AI KHÔNG tự thực hiện hành động này.</b> '
                "Phải có người xem xét rồi duyệt — đây là điểm human-in-the-loop của hệ thống. "
                "Agent chỉ được phép đề xuất và chờ.</div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("Hành động này không cần duyệt.")

        # (3) Hai nút — việc duyệt thật diễn ra trên Jira, ở đây tuyệt đối không
        # được hiện "đã duyệt thành công": trang này không gọi hành động nào cả.
        cot_duyet, cot_tu_choi = st.columns(2)
        if JIRA_URL:
            phieu = f"{JIRA_URL}/browse/{incident['jira_key']}"
            with cot_duyet:
                st.link_button("✅ Duyệt trên Jira", phieu, type="primary", use_container_width=True)
            with cot_tu_choi:
                st.link_button("✖ Từ chối trên Jira", phieu, use_container_width=True)
            st.caption(
                f"↳ Hai nút này **mở phiếu Jira** `{incident['jira_key']}`. Thao tác duyệt/từ chối "
                "xảy ra ở đó — trang này chỉ hiển thị, không thi hành hành động nào."
            )
        else:
            with cot_duyet:
                duyet = st.button("✅ Duyệt", type="primary", use_container_width=True, key=f"duyet-{incident['jira_key']}")
            with cot_tu_choi:
                tu_choi = st.button("✖ Từ chối", use_container_width=True, key=f"tu-choi-{incident['jira_key']}")
            if duyet or tu_choi:
                st.warning(
                    "**Trang này không thi hành hành động.** Việc duyệt/từ chối diễn ra trên phiếu "
                    f"Jira `{incident['jira_key']}`: chuyển trạng thái ở đó, webhook của Jira mới gọi "
                    "Agent thực hiện. Không có gì vừa được chạy."
                )
            st.caption(
                "↳ Chưa đặt `JIRA_BASE_URL` trong môi trường nên không dựng được link thẳng tới phiếu."
            )

        if proposal.get("runbook"):
            with st.expander("Các bước thực hiện và cách kiểm đã hết chưa"):
                st.markdown(proposal["runbook"])


# ---------------------------------------------------------------------------
# Trang
# ---------------------------------------------------------------------------

st.title("🚨 War Room — sự cố đang xảy ra")
st.markdown(
    """
**Trang này theo dõi sự cố của hệ thống.**
AI tự phát hiện sự cố từ số liệu đo được, tìm nguyên nhân **kèm bằng chứng**,
rồi đề xuất cách sửa. **Nó không tự sửa** — mọi hành động ảnh hưởng hệ thống
thật đều phải có người duyệt.
"""
)
# Nói rõ đang đọc môi trường nào. Runbook demo đã vấp đúng chỗ này: quên
# `API_URL=http://localhost:8000` là màn hình hiện dữ liệu của Render.
st.caption(f"↳ API `{API}` · Prometheus `{PROM_URL}`")


@st.cache_data(ttl=10)
def load_incidents(only_open: bool = False) -> list[dict]:
    response = requests.get(f"{API}/api/incidents", params={"only_open": only_open}, timeout=60)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=10)
def load_incident(jira_key: str) -> dict:
    response = requests.get(f"{API}/api/incidents/{jira_key}", timeout=60)
    response.raise_for_status()
    return response.json()


try:
    incidents = load_incidents(only_open=False)
except requests.RequestException as error:
    st.error(f"Không gọi được API: {error}")
    st.caption("Render free tier ngủ sau 15 phút — lần gọi đầu có thể mất ~50 giây. Thử tải lại trang.")
    st.stop()

incidents = sorted(incidents, key=lambda i: i["detected_at"], reverse=True)
dang_xay_ra = [i for i in incidents if i["state"] in DANG_XAY_RA]
da_xong = [i for i in incidents if i["state"] not in DANG_XAY_RA]

if "selected_key" not in st.session_state:
    # Ưu tiên cái đang chờ duyệt: đó là cái duy nhất cần người làm gì ngay.
    cho_duyet = next((i for i in dang_xay_ra if i["state"] == "Awaiting Approval"), None)
    # KHÔNG rơi về `incidents[0]` khi mọi thứ đã xử lý xong.
    #
    # Bản cũ chọn sự cố gần nhất kể cả khi nó đã đóng, nên trang mở ra tự mâu
    # thuẫn: cột trái ghi "✅ Không có sự cố nào đang diễn ra" trong khi cột phải
    # dựng nguyên chuông đỏ "🔴 Nghiêm trọng — nhiều khách hàng bị ảnh hưởng
    # (P1)". Ai nhìn vào cũng đọc cái to màu đỏ trước.
    #
    # Đây là màn hình MỞ ĐẦU của buổi demo, lúc chưa có sự cố nào — nên nó phải
    # nói được đúng một điều: hệ thống đang bình thường.
    default = cho_duyet or (dang_xay_ra[0] if dang_xay_ra else None)
    st.session_state["selected_key"] = default["jira_key"] if default else None

col_list, col_detail = st.columns([1, 2], gap="large")

with col_list:
    # Tách "đang xảy ra" khỏi "đã xong", và gấp phần đã xong lại.
    #
    # Trước 06/08 trang này đổ cả 9 incident vào một danh sách, mà 8 cái là sự
    # cố cũ đã xử lý xong — nhìn vào chỉ thấy một bức tường những dòng gần giống
    # hệt nhau. Thứ người xem cần biết là "bây giờ có gì đang cháy".
    st.markdown(f"### Đang xảy ra ({len(dang_xay_ra)})")
    if not dang_xay_ra:
        st.success("✅ Không có sự cố nào đang diễn ra.")
    for inc in dang_xay_ra:
        the_incident(inc)

    if da_xong:
        with st.expander(f"Đã xử lý xong ({len(da_xong)})", expanded=False):
            for inc in da_xong:
                the_incident(inc)

with col_detail:
    selected_key = st.session_state["selected_key"]
    if not selected_key:
        if dang_xay_ra:
            st.info("Chọn một sự cố bên trái để xem chi tiết.")
        else:
            # Không có gì đang cháy. Nói thẳng điều đó, và nói AI vẫn đang trực —
            # màn hình trống dễ bị hiểu là hệ thống hỏng hoặc chưa chạy.
            st.success("### ✅ Hệ thống đang bình thường\n\nKhông có sự cố nào đang diễn ra.")
            st.markdown(
                "**AI vẫn đang theo dõi liên tục.** Cứ vài giây nó đọc lại số liệu đo "
                "của từng dịch vụ. Khi một chỉ số vượt ngưỡng **và giữ nguyên đủ lâu** "
                "để loại trừ nhiễu, nó sẽ tự mở một phiếu sự cố ở cột bên trái."
            )
            st.markdown("Ba thứ nó canh:")
            st.markdown(
                "- **Thời gian khách phải chờ** — chậm hơn ngưỡng, hoặc chậm bất thường "
                "so với chính nó lúc bình thường\n"
                "- **Tỷ lệ request lỗi**\n"
                "- **Dịch vụ còn sống không** — chết rồi bật lại liên tục"
            )
            if da_xong:
                st.caption(
                    f"Có {len(da_xong)} sự cố đã xử lý xong. Mở mục "
                    f'"Đã xử lý xong" bên trái để xem lại.'
                )
    else:
        try:
            incident = load_incident(selected_key)
        except requests.RequestException as error:
            st.error(f"Không gọi được API: {error}")
            incident = None

        if incident:
            signal = incident.get("signal")

            dau_trang_incident(incident)

            if incident["state"] == "Awaiting Approval":
                st.error(
                    "### ⏸ ĐANG CHỜ NGƯỜI DUYỆT\n\n"
                    "AI đã chẩn đoán xong và đề xuất cách sửa bên dưới, nhưng **nó không tự "
                    "thực hiện**. Cần một người xem xét rồi bấm duyệt trên Jira."
                )

            # ── ① Tín hiệu phát hiện: bằng chứng gốc, trước mọi suy luận.
            muc("①", "AI thấy gì")
            bang_dieu_tra(incident, signal)

            # ── ② Giả thuyết: chỗ phân biệt TRIỆU CHỨNG với NGUYÊN NHÂN.
            muc("②", "AI nghĩ vì sao")
            hypotheses = incident.get("hypotheses") or []
            if hypotheses:
                for h in hypotheses:
                    with st.container():
                        dau_the()
                        st.markdown(f"**{h['statement']}**")
                        st.progress(
                            h["confidence"],
                            text=f"Độ tin cậy {h['confidence'] * 100:.0f}% — do luật tính theo bằng chứng, không phải AI tự nhận",
                        )
                        if h.get("reasoning"):
                            st.caption(h["reasoning"])
                        if h.get("evidence"):
                            st.markdown("**Dựa trên:**")
                            ve_bang_chung(h["evidence"], incident["detected_at"])
                        if h.get("log_evidence"):
                            st.caption(
                                f"↳ kèm {len(h['log_evidence'])} dòng log gốc — xem khối "
                                'log đen ở mục ① "AI thấy gì".'
                            )
                        deploy = h.get("related_deploy")
                        if deploy:
                            st.warning(
                                f"🚀 **Trùng thời gian với một lần deploy:** phiên bản "
                                f"`{deploy['version']}` lên lúc {fmt_time_vn(deploy['deployed_at'])} "
                                f"bởi {deploy['deployed_by']}. Trùng thời gian **chưa phải** bằng "
                                "chứng nhân quả, nhưng đủ để thử hạ phiên bản trước."
                            )
            else:
                st.caption("Chưa có giả thuyết — sự cố này tạo trước khi Agent biết chẩn đoán.")

            # ── ③ Đề xuất: luôn phải qua người duyệt.
            muc("③", "AI đề xuất làm gì")
            proposal = incident.get("proposal")
            if proposal:
                the_de_xuat(incident, proposal)
            else:
                st.caption("Chưa có đề xuất khắc phục.")

            # ── Timeline: dữ liệu Jira tự ghi, Agent không giả mạo được.
            with st.expander("🕒 Diễn biến theo thời gian", expanded=False):
                timeline = incident.get("timeline") or []
                if timeline:
                    st.caption("Đọc từ changelog Jira — Jira tự ghi khi có thao tác.")
                    for t in sorted(timeline, key=lambda t: t["at"]):
                        st.write(
                            f"`{fmt_time_vn(t['at'])}` **[{t['actor']}]** {t['action']}"
                            f" — {t.get('detail', '')}"
                        )
                else:
                    st.caption("Chưa có diễn biến nào.")

            postmortem = incident.get("postmortem")
            if postmortem:
                with st.expander("📋 Báo cáo sau sự cố", expanded=False):
                    st.write(f"**Tóm tắt:** {postmortem['summary']}")
                    st.write(f"**Nguyên nhân gốc:** {postmortem['root_cause']}")
                    st.write(f"**Tác động:** {postmortem['impact']}")
                    if postmortem.get("actions_taken"):
                        st.markdown("**Đã xử lý:**")
                        for a in postmortem["actions_taken"]:
                            st.write(f"- {a}")
                    if postmortem.get("action_items"):
                        st.markdown("**Việc cần làm tiếp:**")
                        for item in postmortem["action_items"]:
                            st.write(f"- {item['title']} — {item.get('owner', '')} ({item.get('jira_key', '')})")

            related = incident.get("related_incidents") or []
            if related:
                st.markdown("#### 🔗 Sự cố liên quan")
                st.caption("Cùng một nguyên nhân lan sang dịch vụ khác.")
                for col, key in zip(st.columns(len(related)), related):
                    with col:
                        if st.button(key, key=f"related-{key}", use_container_width=True):
                            st.session_state["selected_key"] = key
                            st.rerun()
