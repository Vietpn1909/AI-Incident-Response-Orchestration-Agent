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

VN_TZ = timezone(timedelta(hours=7))  # Việt Nam không có DST, luôn UTC+7

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
.luoi { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; }
.svc {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 20px;
  transition: border-color 0.15s, background 0.25s ease;
}
.svc.co-su-co { border-color: var(--p1); background: linear-gradient(180deg, var(--p1-soft) 0%, var(--bg-1) 55%); }
.svc.suy-giam { border-color: var(--p2); background: linear-gradient(180deg, var(--p2-soft) 0%, var(--bg-1) 55%); }
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
    """Định dạng một chuỗi ISO 8601 (UTC) sang giờ Việt Nam, kiểu vi-VN."""
    dt = datetime.fromisoformat(iso).astimezone(VN_TZ)
    return dt.strftime("%H:%M:%S %d/%m/%Y")


def pill(chu: str, bien: str) -> str:
    """Nhãn tròn trạng thái. `bien` là ok / warn / bad / info."""
    return f'<span class="pill {bien}"><span class="cham"></span>{e(chu)}</span>'


#: `ServiceHealth` → biến thể pill. Giữ ánh xạ ở một chỗ thay vì rải if/else.
_BIEN_PILL = {"operational": "ok", "degraded": "warn", "down": "bad", "maintenance": "info"}


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
        '<div class="o-so">'
        '<div class="nhan">Prometheus scrape được không</div>'
        f'<div class="cau">{"Đang phản hồi" if song else "Không phản hồi"}</div>'
        f'<div class="tech"><span class="arrow">↳</span>up = {e(format(gia_tri, "g"))} '
        "— trạng thái tại lúc hỏi, không phải uptime %</div>"
        "</div>"
    )


def the_service(svc: dict, incident: dict | None, bang_up: dict[str, float] | None) -> str:
    """Một thẻ dịch vụ, HTML thuần."""
    suc_khoe = str(svc.get("health", ""))
    _, cau = labels.health(suc_khoe)
    lop = {"down": " co-su-co", "degraded": " suy-giam"}.get(suc_khoe, "")

    # Backend đặt `message` = đúng câu trạng thái khi dịch vụ bình thường, nên
    # in cả hai là lặp y nguyên chữ ngay dưới cái nhãn vừa đọc. Chỉ hiện khi nó
    # nói thêm được điều gì.
    tin = str(svc.get("message", "")).strip()
    tin_html = f'<div class="tin">{e(tin)}</div>' if tin and tin != cau else ""

    ma_su_co = ""
    if svc.get("active_incident"):
        ma_su_co = (
            f'<div class="ma-phieu">Mã sự cố đang xử lý: '
            f'<span class="inline-code">{e(svc["active_incident"])}</span></div>'
        )
    return (
        f'<div class="svc{lop}">'
        f'<div class="dau"><span class="ten">{e(labels.service(svc["name"]))}</span>'
        f'{pill(cau, _BIEN_PILL.get(suc_khoe, "info"))}</div>'
        f'<div class="tech"><span class="arrow">↳</span>{e(svc["name"])}</div>'
        f"{tin_html}"
        f"{ma_su_co}"
        f"{khoi_chi_so(incident)}"
        f"{khoi_up(svc['name'], bang_up)}"
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
        f'<div class="hang">{pill(nhan, bien)}'
        '<span class="tech" style="margin:0">Trang công khai · không cần đăng nhập</span></div>'
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
st.set_page_config(page_title="Trạng thái dịch vụ", page_icon="P035", layout="wide")
st.markdown(theme.CSS_KHUNG, unsafe_allow_html=True)

theme_hien = _tham_so("theme", "dark")
if theme_hien not in ("dark", "light"):
    theme_hien = "dark"

loi = ""
data: dict = {}
try:
    data = load_status()
except requests.RequestException as error:
    loi = str(error)

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
    services = data.get("services") or []
    active_incidents = data.get("active_incidents") or []
    bang_up = load_up()

    if not services:
        luoi = '<div class="note">Chưa có dịch vụ nào được theo dõi.</div>'
    else:
        luoi = '<div class="luoi">' + "".join(
            the_service(svc, incident_cua(svc, active_incidents), bang_up) for svc in services
        ) + "</div>"

    # Giữ lại nhưng gấp và đặt tên rõ là dành cho người trực. Đây là trang công
    # khai nên "để tham khảo khi code" đọc ra như trang chưa làm xong.
    ghi_chu_prom = ""
    if bang_up is None:
        ghi_chu_prom = (
            f'<p class="hint">Không hỏi được Prometheus tại '
            f'<span class="inline-code">{e(PROM_URL)}</span> nên các thẻ không hiện ô '
            "<code>up</code> — bình thường khi trang chạy ngoài máy có Prometheus. "
            "Phần còn lại đọc từ API nên vẫn đủ.</p>"
        )
    import json as _json  # noqa: PLC0415 — chỉ dùng đúng ở khối dữ liệu thô

    than = (
        '<div class="wrap">'
        + khoi_mo_dau(services)
        + luoi
        + '<div class="chan">'
        + f'<span>Cập nhật lúc {e(fmt_time_vn(data["updated_at"]))}</span>'
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
</head>
<body>
<div class="app">
<header class="header">
  <div class="brand"><div class="brand-mark">W</div>
  <div class="brand-text">Trạng thái <em>hệ thống</em></div></div>
  <div class="header-right">
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
</script>
</body>
</html>
"""

# Cùng lý do và cùng đường lùi như war_room.py.
if hasattr(st, "iframe"):
    st.iframe(TRANG, height="stretch")
else:
    import streamlit.components.v1 as components  # noqa: PLC0415

    components.html(TRANG, height=900, scrolling=False)
