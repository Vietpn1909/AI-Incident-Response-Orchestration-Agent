"""Design token dùng chung cho hai trang trong `ui/`.

CHỦ SỞ HỮU: Long · tách ra ngày 17/08 khi dựng lại `status_page.py` cho khớp
tông với `war_room.py`.

## Vì sao có file này

Trước ngày 17/08, bảng màu nằm ở `labels.MAU` kèm ghi chú *"để ở đây vì `ui/`
chỉ được phép import `ui.labels` — không có module thứ ba để chứa theme"*. Ghi
chú đó không còn đúng: `ui/` bị cấm import `src/`, chứ import lẫn nhau trong
`ui/` thì vẫn được, y như `from ui import labels` mà cả hai trang đang làm.

Và cái giá của việc không có module thứ ba đã hiện ra: war room dựng lại theo
`scratch_warroom_ref.html` với một bộ token, status page giữ bộ cũ (xanh cyan
`#38bdf8`, bo góc 14px, gradient), nên hai trang của cùng một sản phẩm nhìn như
hai sản phẩm. Chép bộ token sang trang thứ hai chỉ dời vấn đề: lần sau sửa màu
là lại lệch, mà lệch màu thì không có test nào bắt được.

## Cái gì thuộc về đây, cái gì không

Ở đây: **token và mảnh dùng chung** — biến màu hai theme, reset, font, icon,
nút, pill, dòng `↳`. Không ở đây: CSS của riêng từng trang. War room có sidebar
cuộn riêng và khối reasoning; status page có lưới thẻ dịch vụ. Nhồi cả hai vào
đây thì file này thành bãi chứa, mà đó chính là thứ khiến người ta ngại sửa.

⚠️ `labels.py` lấy màu từ `PALETTE` ở đây. Đừng gõ lại mã hex trong `labels.py`
— hai chỗ cùng một màu là hai chỗ sẽ lệch nhau.
"""

from __future__ import annotations

#: Bảng màu dark, tên tiếng Việt. Đây là **dữ liệu màu** cho code Python dùng
#: (vd. `labels.mau_severity()`), còn CSS thì dùng biến trong `TOKENS_CSS` để
#: đổi theo theme được — mã hex cứng không đổi theo light/dark.
PALETTE: dict[str, str] = {
    "nen": "#0A0D12",
    "the": "#10151C",
    "the2": "#171E27",
    "vien": "#1F2A37",
    "vien_dam": "#2D3A4A",
    "chu": "#E6EBF2",
    "mo": "#8593A6",
    "mo2": "#556377",
    "mo3": "#3B4757",
    "nhan": "#D4A056",
    "do": "#E5484D",
    "cam": "#F5A524",
    "xanh": "#52B788",
    "tim": "#9C6ADE",
    "xanh_duong": "#4493F8",
    "tin_hieu": "#6BB6C7",
}

#: Thẻ `<link>` Google Fonts. Ba họ chữ, mỗi họ một việc — serif cho tiêu đề,
#: sans cho thân, mono cho code và nhãn kỹ thuật.
FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    "family=Inter:wght@400;500;600;700&"
    "family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,500;0,6..72,600;"
    "1,6..72,300;1,6..72,400&"
    'family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">'
)

#: Biến màu hai theme. Dark là mặc định, light nằm dưới `[data-theme="light"]`.
TOKENS_CSS = """
/* ═══════════════ DARK THEME (default) ═══════════════ */
:root {
  --bg-0: #0A0D12;
  --bg-1: #10151C;
  --bg-2: #171E27;
  --bg-3: #1F2A37;
  --bg-hover: #1A222D;
  --border: #1F2A37;
  --border-strong: #2D3A4A;
  --ink-0: #E6EBF2;
  --ink-1: #8593A6;
  --ink-2: #556377;
  --ink-3: #3B4757;
  --accent: #D4A056;
  --accent-soft: rgba(212, 160, 86, 0.12);
  --accent-line: rgba(212, 160, 86, 0.35);
  --p1: #E5484D;
  --p1-soft: rgba(229, 72, 77, 0.14);
  --p2: #F5A524;
  --p2-soft: rgba(245, 165, 36, 0.14);
  --p3: #4493F8;
  --p3-soft: rgba(68, 147, 248, 0.14);
  --ok: #52B788;
  --ok-soft: rgba(82, 183, 136, 0.14);
  --ok-line: rgba(82, 183, 136, 0.35);
  --signal: #6BB6C7;
  --pending: #9C6ADE;

  --btn-primary-bg: #E6EBF2;
  --btn-primary-fg: #0A0D12;

  --code-bg: #06090D;
  --code-head-bg: #0D1218;
  --code-border: #1A2028;
  --code-k: #C792EA;
  --code-fn: #D4A056;
  --code-s: #A3D5AA;
  --code-n: #6BB6C7;
  --code-cm: #556377;
  --code-p: #8593A6;

  --font-display: 'Newsreader', Georgia, serif;
  --font-body: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, 'SF Mono', monospace;
}

/* ═══════════════ LIGHT THEME ═══════════════ */
[data-theme="light"] {
  --bg-0: #F0F2F5;
  --bg-1: #FFFFFF;
  --bg-2: #F6F8FB;
  --bg-3: #EAEEF3;
  --bg-hover: #F1F4F8;
  --border: #E1E5EC;
  --border-strong: #C7CDD6;
  --ink-0: #0F1620;
  --ink-1: #4C5766;
  --ink-2: #6C7684;
  --ink-3: #A2AAB6;
  --accent: #A16A25;
  --accent-soft: rgba(161, 106, 37, 0.08);
  --accent-line: rgba(161, 106, 37, 0.35);
  --p1: #C8353B;
  --p1-soft: rgba(200, 53, 59, 0.08);
  --p2: #B77813;
  --p2-soft: rgba(183, 120, 19, 0.08);
  --p3: #2465C6;
  --p3-soft: rgba(36, 101, 198, 0.08);
  --ok: #1E7F4E;
  --ok-soft: rgba(30, 127, 78, 0.10);
  --ok-line: rgba(30, 127, 78, 0.35);
  --signal: #2B7185;
  --pending: #6541A2;

  --btn-primary-bg: #0F1620;
  --btn-primary-fg: #FFFFFF;

  --code-bg: #F8FAFC;
  --code-head-bg: #EEF2F7;
  --code-border: #E1E5EC;
  --code-k: #7A3EBE;
  --code-fn: #A16A25;
  --code-s: #2E7D32;
  --code-n: #1F6580;
  --code-cm: #8993A2;
  --code-p: #6C7684;
}
"""

#: Reset + nền + thanh cuộn. Giống hệt nhau ở hai trang.
RESET_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }

/* ⚠️ Dòng này chặn một loại lỗi đã cắn hai lần trong cùng một ngày (17/08).
 *
 * `[hidden] { display: none }` là quy tắc của TRÌNH DUYỆT, mà CSS của trang thì
 * luôn thắng CSS trình duyệt. Nên bất kỳ selector nào của ta khai `display:` —
 * `.incident { display: block }`, `.dang-tai { display: grid }` — đều **vô hiệu
 * hoá** thuộc tính `hidden` trên chính phần tử đó. JS đặt `el.hidden = true`
 * vẫn chạy đúng, `el.hidden` đọc ra `true`, mà phần tử vẫn nằm nguyên trên màn
 * hình. Lần một: ô tìm kiếm không lọc được thẻ nào. Lần hai: màn chờ che kín
 * trang ngay khi mở, trông như trang treo.
 *
 * Cả hai lần đều lọt qua bản kiểm vì bản kiểm đọc `el.hidden` thay vì
 * `getComputedStyle(el).display`. Kiểm CSS thì phải nhìn style tính toán.
 */
[hidden] { display: none !important; }
body {
  background: var(--bg-0);
  color: var(--ink-0);
  font-family: var(--font-body);
  font-size: 13.5px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  transition: background 0.25s ease, color 0.25s ease;
}
button { font-family: inherit; cursor: pointer; border: none; background: none; color: inherit; }
input { font-family: inherit; }
::selection { background: var(--accent-soft); color: var(--ink-0); }

::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--bg-3); border-radius: 10px; border: 2px solid var(--bg-0); }
::-webkit-scrollbar-thumb:hover { background: var(--border-strong); }
"""

#: Header 52px, nút, dòng `↳`, ghi chú. Hai trang dùng chung hình dạng này để
#: người xem nhận ra ngay là cùng một hệ thống.
CHUNG_CSS = """
.header {
  display: grid;
  align-items: center;
  background: var(--bg-1);
  border-bottom: 1px solid var(--border);
  padding: 0 16px 0 20px;
  height: 52px;
  transition: background 0.25s ease, border-color 0.25s ease;
}
.brand { display: flex; align-items: center; gap: 10px; }
.brand-mark {
  width: 22px; height: 22px;
  background: linear-gradient(135deg, var(--accent) 0%, #7A5122 100%);
  border-radius: 5px;
  display: grid; place-items: center;
  color: #fff;
  font-family: var(--font-display);
  font-weight: 500; font-style: italic; font-size: 14px;
}
.brand-text {
  font-family: var(--font-display);
  font-weight: 400; font-size: 17px; letter-spacing: -0.01em;
}
.brand-text em { font-style: italic; color: var(--ink-1); font-weight: 300; }

.header-right { display: flex; align-items: center; gap: 6px; }
.hbtn {
  height: 30px; padding: 0 12px;
  border-radius: 6px;
  color: var(--ink-1);
  font-size: 12.5px;
  display: flex; align-items: center; gap: 6px;
  transition: all 0.15s;
  white-space: nowrap;
  text-decoration: none;
}
.hbtn:hover { background: var(--bg-3); color: var(--ink-0); }
.hbtn.primary { background: var(--btn-primary-bg); color: var(--btn-primary-fg); font-weight: 500; }
.hbtn.primary:hover { filter: brightness(1.05); }
.hbtn:disabled { opacity: 0.4; cursor: not-allowed; }
.hbtn:disabled:hover { background: none; color: var(--ink-1); }

.icon-btn {
  width: 30px; height: 30px;
  border-radius: 6px;
  display: grid; place-items: center;
  color: var(--ink-1);
  transition: all 0.15s;
  position: relative;
}
.icon-btn:hover { background: var(--bg-3); color: var(--ink-0); }
.icon-btn .icon-sun, .icon-btn .icon-moon {
  position: absolute;
  transition: opacity 0.25s, transform 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}
[data-theme="dark"] .icon-btn .icon-sun { opacity: 0; transform: rotate(180deg) scale(0.6); }
[data-theme="dark"] .icon-btn .icon-moon { opacity: 1; transform: rotate(0) scale(1); }
[data-theme="light"] .icon-btn .icon-sun { opacity: 1; transform: rotate(0) scale(1); }
[data-theme="light"] .icon-btn .icon-moon { opacity: 0; transform: rotate(-180deg) scale(0.6); }

.btn {
  height: 34px; padding: 0 16px;
  border-radius: 7px;
  font-size: 12.5px; font-weight: 500;
  display: inline-flex; align-items: center; gap: 8px;
  transition: all 0.15s;
  border: 1px solid transparent;
  text-decoration: none;
}
.btn.ghost { color: var(--ink-1); border-color: var(--border-strong); }
.btn.ghost:hover { color: var(--ink-0); background: var(--bg-3); }
.btn.approve { background: var(--btn-primary-bg); color: var(--btn-primary-fg); }
.btn.approve:hover { filter: brightness(1.05); }
.btn.small { height: 28px; padding: 0 10px; font-size: 12px; }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn:disabled:hover { background: none; color: var(--ink-1); filter: none; }

/* Dòng kỹ thuật đi kèm mỗi câu dịch — nguyên tắc "dịch THÊM, không dịch THAY".
   Cả hai trang đều phải có, xem docstring của war_room.py và status_page.py. */
.tech {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--ink-2);
  margin-top: 4px;
  word-break: break-word;
}
.tech .arrow { color: var(--ink-3); margin-right: 4px; }
.tech code { font-family: inherit; }

.inline-code {
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 1px 6px;
  background: var(--bg-3);
  border-radius: 4px;
  color: var(--accent);
  border: 1px solid var(--border);
}

.note {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 18px;
  font-size: 12.5px;
  color: var(--ink-1);
}
.note strong { color: var(--ink-0); font-weight: 600; }
.note.err {
  background: linear-gradient(180deg, var(--p1-soft) 0%, transparent 60%), var(--bg-1);
  border-color: var(--p1);
  color: var(--ink-0);
}
.hint { font-size: 11.5px; color: var(--ink-2); margin-top: 10px; }

/* Nhãn tròn trạng thái */
.pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 11.5px; font-weight: 500;
  white-space: nowrap;
  border: 1px solid transparent;
}
.pill .cham { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.pill.ok { color: var(--ok); background: var(--ok-soft); border-color: var(--ok-line); }
.pill.warn { color: var(--p2); background: var(--p2-soft); }
.pill.bad { color: var(--p1); background: var(--p1-soft); }
.pill.info { color: var(--signal); background: rgba(107, 182, 199, 0.14); }
.pill.bad .cham { animation: blink 1.5s ease-in-out infinite; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

/* Mục nhỏ có đánh số, dùng chung cách đặt eyebrow + tiêu đề serif */
.sec-eyebrow {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-weight: 500;
}
.sec-title {
  font-family: var(--font-display);
  font-size: 22px; font-weight: 400;
  letter-spacing: -0.015em;
  color: var(--ink-0);
}
.sec-title em { font-style: italic; font-weight: 300; color: var(--ink-1); }

details.more { margin-top: 10px; }
details.more > summary {
  cursor: pointer;
  list-style: none;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-2);
  padding: 4px 0;
  transition: color 0.15s;
}
details.more > summary::-webkit-details-marker { display: none; }
details.more > summary::before { content: '+ '; }
details.more[open] > summary::before { content: '− '; }
details.more > summary:hover { color: var(--ink-0); }
"""

#: CSS cho phần vỏ Streamlit bên ngoài iframe. Mục tiêu duy nhất: biến mất, để
#: iframe chiếm trọn cửa sổ. Bám `data-testid` do Streamlit đặt tên, KHÔNG bám
#: class hash sinh tự động (`st-emotion-cache-...`) vì `ui/requirements.txt` cố
#: tình không ghim version Streamlit.
CSS_KHUNG = """
<style>
html, body, .stApp, [data-testid="stAppViewContainer"] {
  height: 100%; overflow: hidden; background: #0A0D12;
}
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], [data-testid="stSidebarCollapsedControl"], footer {
  display: none !important;
}
.block-container, [data-testid="stMainBlockContainer"], [data-testid="stAppViewBlockContainer"] {
  padding: 0 !important;
  max-width: 100% !important;
}
[data-testid="stVerticalBlock"] { gap: 0 !important; }
[data-testid="stElementContainer"] { margin: 0 !important; }
/* Iframe của st.iframe — ép chiếm trọn khung nhìn. Thiếu dòng này thì nó giữ
   đúng chiều cao truyền vào `height=` và trang có thanh cuộn kép. */
.stApp iframe {
  height: 100vh !important;
  width: 100% !important;
  border: none !important;
  display: block !important;
}
</style>
"""


def svg(duong: str, *, co: int = 14, to: str = "2", fill: str = "none") -> str:
    """Một icon SVG nội tuyến. Không dùng thư viện icon — xem `ICON` bên dưới."""
    return (
        f'<svg width="{co}" height="{co}" viewBox="0 0 24 24" fill="{fill}" '
        f'stroke="currentColor" stroke-width="{to}" stroke-linecap="round" '
        f'stroke-linejoin="round">{duong}</svg>'
    )


#: Icon dùng chung. Tất cả là SVG nội tuyến: không gọi ra ngoài, đổi màu theo
#: `currentColor` nên tự đúng ở cả hai theme, và không có emoji trong UI.
ICON: dict[str, str] = {
    "lich": svg('<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>'),
    "dong_ho": svg('<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>'),
    "tia": svg('<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>'),
    "check": svg('<path d="M20 6 9 17l-5-5"/>'),
    "hop": svg(
        '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 '
        '1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>'
    ),
    "tep": svg('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>'),
    "sach": svg('<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>'),
    "mui_ten": svg('<path d="M5 12h14M12 5l7 7-7 7"/>', co=12, to="2.5"),
    "set": svg('<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>', co=11, to="2.5"),
    "tim": svg('<circle cx="11" cy="11" r="7"/><path d="m21 21-4.35-4.35"/>'),
    "chep": svg(
        '<rect x="9" y="9" width="13" height="13" rx="2"/>'
        '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
        co=12,
    ),
    "ngoai": svg(
        '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'
        '<polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>'
    ),
    "lam_moi": svg('<path d="M21 12a9 9 0 1 1-3-6.7"/><polyline points="21 3 21 9 15 9"/>'),
    "tim_mach": svg('<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>'),
    "may_chu": svg(
        '<rect x="2" y="3" width="20" height="7" rx="2"/><rect x="2" y="14" width="20" height="7" rx="2"/>'
        '<line x1="6" y1="6.5" x2="6.01" y2="6.5"/><line x1="6" y1="17.5" x2="6.01" y2="17.5"/>'
    ),
    "cham": '<svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="6"/></svg>',
    "trang": svg(
        '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 '
        '17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
        co=15,
        to="1.8",
    ),
    "toi": svg('<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>', co=15, to="1.8"),
}

#: Nút đổi theme — hai SVG chồng lên nhau, CSS lo phần chuyển. Giống hệt ở hai
#: trang nên đóng gói luôn ở đây.
NUT_THEME = (
    '<button class="icon-btn" type="button" id="theme-toggle" aria-label="Đổi theme">'
    f'<span class="icon-moon">{ICON["toi"]}</span>'
    f'<span class="icon-sun">{ICON["trang"]}</span></button>'
)

#: JS đổi theme + ghi trạng thái vào URL của tab cha.
#:
#: ⚠️ `window.parent.location.href = ...` **không** dùng được: iframe của
#: Streamlit chạy sandbox không có `allow-top-navigation`, gán thẳng là
#: `SecurityError` (đo ngày 17/08). `history.replaceState` và `location.reload`
#: thì được — xem chú thích dài trong `war_room.py::_JS`.
JS_THEME = """
var root = document.documentElement;
function dongBoUrl(khoa, giaTri) {
  try {
    var u = new URL(window.parent.location.href);
    u.searchParams.set('theme', root.getAttribute('data-theme'));
    if (khoa) { u.searchParams.set(khoa, giaTri); }
    window.parent.history.replaceState({}, '', u.toString());
    return u.toString();
  } catch (err) { return null; }
}
function taiLai() {
  dongBoUrl();
  try { window.parent.location.reload(); return true; } catch (err) { return false; }
}
document.getElementById('theme-toggle').addEventListener('click', function () {
  root.setAttribute('data-theme', root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
  dongBoUrl();
});
"""
