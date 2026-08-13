"""Status page công khai — trang người dùng dịch vụ xem để biết có sự cố không.

CHỦ SỞ HỮU: Long

Chạy:
    streamlit run ui/status_page.py

Dữ liệu đã có sẵn, không cần chờ Agent hay Jira. Xem ui/README.md.

## Hai tầng, y như war room

Đây là trang công khai nhưng vẫn giữ nguyên tắc **dịch THÊM, không dịch THAY**:
tên dịch vụ dễ hiểu dẫn đường, dòng `↳` bên dưới giữ nguyên văn tên kỹ thuật và
tên metric. Người ngoài đọc dòng trên là đủ; người trực cần dòng dưới để đào.

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
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st

# `streamlit run ui/status_page.py` đặt thư mục ui/ vào sys.path, không đặt thư
# mục gốc repo — xem chú thích cùng chỗ trong war_room.py.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ui import labels  # noqa: E402

API = os.getenv("API_URL", "https://p-035-incident-agent.onrender.com")
# Chỉ dùng để hỏi metric `up`. Không với tới được thì bỏ qua phần đó, trang vẫn
# chạy — Prometheus chỉ có bản local trong buổi demo.
PROM_URL = os.getenv("PROM_URL", "http://localhost:9090")

VN_TZ = timezone(timedelta(hours=7))  # Việt Nam không có DST, luôn UTC+7

# Selector CSS ở đây chỉ bám `data-testid` do Streamlit đặt tên và class của
# chính trang này — không bám class hash sinh tự động (`st-emotion-cache-...`),
# vì `ui/requirements.txt` cố tình không ghim version Streamlit. Thẻ dịch vụ là
# HTML thuần nên kể cả khi CSS hỏng, nội dung vẫn hiện đủ theo thứ tự đọc được.
_CSS_TINH = """
.stApp {
  background:
    radial-gradient(1000px 480px at 50% -20%, rgba(56,189,248,.09), transparent 60%),
    var(--p035-nen);
}
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2.6rem; padding-bottom: 4rem; max-width: 1180px; }
h1 { font-weight: 760; letter-spacing: -.03em; }

.p035-svc {
  background: var(--p035-the);
  border: 1px solid var(--p035-vien);
  border-radius: 14px;
  padding: 1rem 1.1rem;
  height: 100%;
}
.p035-svc .dau { display: flex; align-items: center; justify-content: space-between; gap: .6rem; flex-wrap: wrap; }
.p035-svc .ten { font-size: 1.08rem; font-weight: 700; letter-spacing: -.01em; }
.p035-svc .kt { font-size: .76rem; color: var(--p035-mo); line-height: 1.7; }
.p035-svc .tin { font-size: .9rem; line-height: 1.6; margin: .5rem 0 .1rem; }
.p035-svc .so-lieu {
  margin-top: .75rem; padding-top: .7rem;
  border-top: 1px dashed var(--p035-vien);
}
.p035-svc .so-lieu .nhan {
  font-size: .67rem; letter-spacing: .08em; text-transform: uppercase;
  color: var(--p035-mo); font-weight: 650;
}
.p035-svc .so-lieu .cau { font-size: .95rem; font-weight: 650; line-height: 1.55; margin: .1rem 0 .15rem; }
.p035-svc code { font-size: .74rem; }

.p035-pill {
  display: inline-flex; align-items: center; gap: .35rem;
  padding: .16rem .62rem; border-radius: 999px;
  border: 1px solid transparent;
  font-size: .76rem; font-weight: 650; line-height: 1.55; white-space: nowrap;
}

[data-testid="stButton"] > button, .stButton > button {
  border-radius: 10px;
  transition: transform .12s ease, box-shadow .12s ease, border-color .12s ease;
}
[data-testid="stButton"] > button:hover, .stButton > button:hover {
  transform: translateY(-1px);
  border-color: var(--p035-nhan);
  box-shadow: 0 6px 18px rgba(56,189,248,.20);
}
[data-testid="stExpander"] details {
  border: 1px solid var(--p035-vien); border-radius: 12px; background: rgba(2,6,23,.35);
}
[data-testid="stAlert"] { border-radius: 12px; }
"""

CSS = "<style>:root{" + "".join(f"--p035-{t}:{m};" for t, m in labels.MAU.items()) + "}" + _CSS_TINH + "</style>"

st.set_page_config(page_title="Trạng thái dịch vụ", page_icon="🟢", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)


def fmt_time_vn(iso: str) -> str:
    """Định dạng một chuỗi ISO 8601 (UTC) sang giờ Việt Nam, kiểu vi-VN."""
    dt = datetime.fromisoformat(iso).astimezone(VN_TZ)
    return dt.strftime("%H:%M:%S %d/%m/%Y")


def _rgba(ma: str, dam: float) -> str:
    """`("#22c55e", 0.14)` → `"rgba(34,197,94,0.14)"` — xem chú thích trong war_room."""
    ma = ma.lstrip("#")
    r, g, b = (int(ma[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{dam})"


def pill(chu: str, mau: str, *, icon: str = "") -> str:
    """Badge bo tròn dạng HTML."""
    noi_dung = f"{icon} {chu}".strip()
    style = f"color:{mau};background:{_rgba(mau, 0.14)};border-color:{_rgba(mau, 0.45)}"
    return f'<span class="p035-pill" style="{style}">{html.escape(noi_dung)}</span>'


st.title("Trạng thái dịch vụ")
st.caption(
    "Trang công khai — ai cũng xem được, không cần đăng nhập. "
    "Cập nhật tự động từ số liệu đo được của hệ thống."
)


@st.cache_data(ttl=10)
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
    """
    try:
        phan_hoi = requests.get(f"{PROM_URL}/api/v1/query", params={"query": "up"}, timeout=3)
        phan_hoi.raise_for_status()
        goi = phan_hoi.json()
    except (requests.RequestException, ValueError):
        return None
    if goi.get("status") != "success":
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


def incident_cua(svc: dict, danh_sach: list[dict]) -> dict | None:
    """Incident đang ảnh hưởng dịch vụ này, lấy từ `active_incidents[]`."""
    ma = svc.get("active_incident")
    if ma:
        trung = next((inc for inc in danh_sach if inc.get("jira_key") == ma), None)
        if trung:
            return trung
    return next((inc for inc in danh_sach if svc["name"] in (inc.get("affected_services") or [])), None)


def khoi_chi_so(incident: dict | None) -> str:
    """Ô "chỉ số đang bất thường" của một thẻ. Chuỗi rỗng nếu không có số thật."""
    signal = (incident or {}).get("signal")
    if not signal:
        return ""

    # Lấy đúng bằng chứng của chỉ số đã kích hoạt: nó mới có baseline/unit/promql.
    ev = next(
        (e for e in (signal.get("evidence") or []) if e.get("name") == signal.get("metric_name")),
        None,
    ) or {}
    dong = labels.bang_chung(
        signal["metric_name"],
        signal["metric_value"],
        baseline=ev.get("baseline"),
        unit=ev.get("unit", ""),
        promql=ev.get("promql", ""),
    )

    ky_thuat = f"↳ <code>{html.escape(dong.raw)}</code> · ngưỡng <code>{signal['threshold']:g}</code>"
    keo_dai = ""
    if signal.get("breached_for_seconds"):
        keo_dai = f'<div class="kt">Đã kéo dài {html.escape(labels.keo_dai(signal["breached_for_seconds"]))}</div>'
    return (
        '<div class="so-lieu">'
        '<div class="nhan">Chỉ số đang bất thường</div>'
        f'<div class="cau">{html.escape(dong.plain)}</div>'
        f'<div class="kt">{ky_thuat}</div>'
        f"{keo_dai}</div>"
    )


def khoi_up(ten_service: str, bang_up: dict[str, float] | None) -> str:
    """Ô `up`. Rỗng khi không hỏi được Prometheus — bỏ qua chứ không đoán."""
    if bang_up is None or ten_service not in bang_up:
        return ""
    gia_tri = bang_up[ten_service]
    song = gia_tri >= 1
    return (
        '<div class="so-lieu">'
        '<div class="nhan">Prometheus scrape được không</div>'
        f'<div class="cau">{"Đang phản hồi" if song else "Không phản hồi"}</div>'
        f'<div class="kt">↳ <code>up = {gia_tri:g}</code> — trạng thái tại lúc hỏi, không phải uptime %</div>'
        "</div>"
    )


def the_service(svc: dict, incident: dict | None, bang_up: dict[str, float] | None) -> str:
    """Một thẻ dịch vụ, HTML thuần."""
    icon, cau = labels.health(svc["health"])
    badge = pill(cau, labels.mau_health(svc["health"]), icon=icon)
    ma_su_co = ""
    if svc.get("active_incident"):
        ma_su_co = f'<div class="kt">Mã sự cố đang xử lý: <code>{html.escape(str(svc["active_incident"]))}</code></div>'
    return (
        '<div class="p035-svc">'
        f'<div class="dau"><span class="ten">{html.escape(labels.service(svc["name"]))}</span>{badge}</div>'
        f'<div class="kt">↳ <code>{html.escape(svc["name"])}</code></div>'
        f'<div class="tin">{html.escape(svc.get("message", ""))}</div>'
        f"{ma_su_co}"
        f"{khoi_chi_so(incident)}"
        f"{khoi_up(svc['name'], bang_up)}"
        "</div>"
    )


try:
    data = load_status()
except requests.RequestException as error:
    st.error(f"Không gọi được API: {error}")
    st.caption("Render free tier ngủ sau 15 phút — lần gọi đầu có thể mất ~50 giây. Thử tải lại trang.")
    st.stop()

services = data["services"]
active_incidents = data.get("active_incidents") or []
bang_up = load_up()

has_down = any(svc["health"] == "down" for svc in services)
has_degraded = any(svc["health"] == "degraded" for svc in services)
has_maintenance = any(svc["health"] == "maintenance" for svc in services)

# Thứ tự ưu tiên khớp StatusPage.overall_health (src/models/incident.py):
# down > degraded > maintenance > operational.
if has_down:
    st.error("🔴 Một số dịch vụ đang gặp sự cố")
elif has_degraded:
    st.warning("🟡 Một số dịch vụ suy giảm")
elif has_maintenance:
    st.info("🔧 Một số dịch vụ đang bảo trì")
else:
    st.success("🟢 Tất cả dịch vụ hoạt động bình thường")

if not services:
    st.info("Chưa có dịch vụ nào được theo dõi.")
else:
    # Lưới 2–3 cột: hai dịch vụ thì hai cột cho thẻ đủ rộng, nhiều hơn thì ba.
    so_cot = 2 if len(services) <= 2 else 3
    for dau_hang in range(0, len(services), so_cot):
        hang = services[dau_hang : dau_hang + so_cot]
        for col, svc in zip(st.columns(so_cot, gap="medium"), hang):
            with col:
                st.markdown(the_service(svc, incident_cua(svc, active_incidents), bang_up), unsafe_allow_html=True)

st.caption(f"Cập nhật lúc {fmt_time_vn(data['updated_at'])}")

if st.button("🔄 Tải lại"):
    load_status.clear()
    load_up.clear()
    st.rerun()

# Giữ lại nhưng gấp và đặt tên rõ là dành cho người trực. Đây là trang công
# khai nên "để tham khảo khi code" đọc ra như trang chưa làm xong.
with st.expander("Dữ liệu thô (dành cho người trực)"):
    if bang_up is None:
        st.caption(
            f"Không hỏi được Prometheus tại `{PROM_URL}` nên các thẻ không hiện ô `up` — "
            "bình thường khi trang chạy ngoài máy có Prometheus. Phần còn lại đọc từ API nên vẫn đủ."
        )
    st.json(data)
