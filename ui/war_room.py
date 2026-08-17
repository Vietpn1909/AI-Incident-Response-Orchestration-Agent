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
# REDESIGN NOTE — 2025-08-16
#
# CSS dưới đây viết lại hoàn toàn theo design system trong file mẫu
# `scratch_warroom_ref.html`. Design tokens dùng CSS variables từ `:root`
# (dark theme mặc định), KHÔNG phụ thuộc `labels.MAU` cho CSS nữa.
#
# Quy tắc selector vẫn giữ: bám `data-testid`, KHÔNG bám class emotion hash.
# Thẻ container dùng `dau_the()` + `:has()` selector.
_CSS_TINH = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,300;1,6..72,400&family=JetBrains+Mono:wght@400;500&display=swap');

/* ═══ Design tokens — dark theme ═══ */
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

/* ═══ Base ═══ */
.stApp {
  background: var(--bg-0) !important;
  font-family: var(--font-body) !important;
  font-size: 13.5px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}
[data-testid="stHeader"] { background: var(--bg-1) !important; border-bottom: 1px solid var(--border); }
.block-container { padding-top: 1.2rem !important; padding-bottom: 4rem; max-width: 1560px; }

/* Scrollbar */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--bg-3); border-radius: 8px; }
::-webkit-scrollbar-thumb:hover { background: var(--border-strong); }

/* ═══ Typography — Newsreader for display, Inter for body, JetBrains Mono for code ═══ */
h1 {
  font-family: var(--font-display) !important;
  font-weight: 400 !important;
  font-size: 22px !important;
  letter-spacing: -0.01em;
}
h2, h3, h4 {
  font-family: var(--font-body) !important;
  letter-spacing: -0.02em;
}

/* ═══ Thẻ container (card) ═══ */
.p035-dau { display: none; }
[data-testid="stElementContainer"]:has(.p035-dau) { display: none; }

[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .p035-the),
[data-testid="stVerticalBlock"]:has(.p035-the):not(:has([data-testid="stVerticalBlock"] .p035-the)) {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1rem 1.1rem;
  transition: border-color 0.15s ease;
}

/* ═══ Sidebar card đang chọn ═══ */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .p035-active),
[data-testid="stVerticalBlock"]:has(.p035-active):not(:has([data-testid="stVerticalBlock"] .p035-active)) {
  border-color: var(--border-strong);
  background: var(--bg-2);
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .p035-active)::before,
[data-testid="stVerticalBlock"]:has(.p035-active):not(:has([data-testid="stVerticalBlock"] .p035-active))::before {
  content: '';
  position: absolute;
  left: 0; top: 12px; bottom: 12px;
  width: 2px;
  background: var(--accent);
  border-radius: 1px;
}

/* ═══ Neon alert card (P1 hoặc Awaiting Approval) ═══ */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .p035-neon),
[data-testid="stVerticalBlock"]:has(.p035-neon):not(:has([data-testid="stVerticalBlock"] .p035-neon)) {
  border-color: rgba(229,72,77,.45);
}
@media (prefers-reduced-motion: reduce) {
  [data-testid="stVerticalBlock"]:has(.p035-neon) {
    border-color: rgba(229,72,77,.55);
  }
}

/* ═══ Badge pill — severity, status ═══ */
.p035-pill {
  display: inline-flex; align-items: center; gap: .3rem;
  padding: 1px 8px; border-radius: 999px;
  border: 1px solid transparent;
  font-family: var(--font-mono);
  font-size: 10.5px; font-weight: 500; line-height: 1.6;
  white-space: nowrap; vertical-align: middle;
}
.p035-hang-pill { display: flex; flex-wrap: wrap; gap: .35rem; align-items: center; margin-bottom: .5rem; }

/* ═══ Section header (eyebrow + serif title) ═══ */
.p035-sec-head {
  display: flex; align-items: baseline; flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.p035-sec-eyebrow {
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: var(--accent);
  font-weight: 500;
}
.p035-sec-eyebrow.done { color: var(--ok); }
.p035-sec-title {
  font-family: var(--font-display) !important;
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.01em;
  color: var(--ink-0);
  flex: 1;
}
.p035-sec-title em {
  font-style: italic;
  font-weight: 300;
  color: var(--ink-1);
}
.p035-sec-aside {
  margin-left: auto;
  font-size: 12px;
  color: var(--ink-2);
}

/* ═══ Đầu trang sự cố (case header) ═══ */
.p035-dau-trang {
  margin-bottom: 1.2rem;
}
.p035-crumb {
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
  color: var(--ink-2);
  letter-spacing: 0.04em;
  margin-bottom: 8px;
}
.p035-crumb .sep { color: var(--ink-3); margin: 0 4px; }
.p035-status-pill {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  font-family: var(--font-body);
  text-transform: none;
  letter-spacing: 0;
}
.p035-status-pill.live {
  background: var(--p1-soft);
  color: var(--p1);
}
.p035-status-pill.live::before {
  content: '';
  width: 5px; height: 5px;
  border-radius: 50%;
  background: var(--p1);
  animation: p035-blink 1.5s ease-in-out infinite;
}
@keyframes p035-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
.p035-status-pill.done {
  background: var(--ok-soft);
  color: var(--ok);
}
.p035-case-title {
  font-family: var(--font-display) !important;
  font-size: 28px !important;
  font-weight: 400 !important;
  letter-spacing: -0.02em;
  line-height: 1.35;
  margin: 6px 0 10px !important;
  color: var(--ink-0);
}
.p035-case-title .sev {
  font-style: italic;
  font-weight: 300;
  margin-right: 6px;
}
.p035-case-title .sev.p1 { color: var(--p1); }
.p035-case-title .sev.p2 { color: var(--p2); }
.p035-case-title .sev.p3 { color: var(--p3); }
.p035-case-title .sev.done { color: var(--ok); }
.p035-case-title .service {
  font-style: italic;
  font-weight: 300;
  color: var(--ink-1);
}
.p035-case-meta {
  display: flex; flex-wrap: wrap; align-items: center;
  gap: 18px;
  padding: 12px 0;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  font-size: 12.5px;
  color: var(--ink-1);
}
.p035-case-meta .val { color: var(--ink-0); font-weight: 500; }
.p035-meta-actions { margin-left: auto; display: flex; gap: 6px; }

/* ═══ Vitals strip — 4 metric cards in a row ═══ */
.p035-vitals {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 1px;
  background: var(--border);
  border-radius: 10px;
  overflow: hidden;
  margin: 10px 0 14px;
}
.p035-vital {
  background: var(--bg-1);
  padding: 14px 16px;
}
.p035-vital.alert {
  background: linear-gradient(180deg, var(--p1-soft) 0%, var(--bg-1) 60%);
}
.p035-vital.ok-state {
  background: linear-gradient(180deg, var(--ok-soft) 0%, var(--bg-1) 60%);
}
.p035-vital-label {
  font-family: var(--font-mono);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--ink-2);
  display: flex; align-items: center; gap: 5px;
  margin-bottom: 4px;
}
.p035-vital-value {
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 400;
  letter-spacing: -0.02em;
  line-height: 1.2;
}
.p035-vital.alert .p035-vital-value { color: var(--p1); }
.p035-vital.ok-state .p035-vital-value { color: var(--ok); }
.p035-vital-unit {
  font-family: var(--font-body);
  font-size: 13px;
  color: var(--ink-1);
  margin-left: 2px;
}
.p035-vital-sub {
  font-size: 11.5px;
  color: var(--ink-2);
  margin-top: 2px;
}
.p035-delta {
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 0 5px;
  border-radius: 4px;
  margin-left: 4px;
}
.p035-delta.bad { color: var(--p1); background: var(--p1-soft); }
.p035-delta.good { color: var(--ok); background: var(--ok-soft); }

/* ═══ Reasoning timeline ═══ */
.p035-reasoning {
  padding-left: 24px;
  border-left: 1px solid var(--accent-line);
  margin-left: 4px;
  position: relative;
}
.p035-reasoning.done { border-left-color: var(--ok-line); }
.p035-reasoning-item {
  position: relative;
  padding-bottom: 20px;
}
.p035-reasoning-item::before {
  content: '';
  position: absolute;
  left: -29px; top: 5px;
  width: 9px; height: 9px;
  border-radius: 50%;
  background: var(--bg-0);
  border: 1.5px solid var(--accent);
}
.p035-reasoning.done .p035-reasoning-item::before { border-color: var(--ok); }
.p035-reasoning-item.conclusion::before {
  background: var(--accent);
  box-shadow: 0 0 0 4px var(--accent-soft);
}
.p035-reasoning.done .p035-reasoning-item.conclusion::before {
  background: var(--ok);
  box-shadow: 0 0 0 4px var(--ok-soft);
}
.p035-r-label {
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--accent);
  font-weight: 500;
  margin-bottom: 4px;
}
.p035-reasoning.done .p035-r-label { color: var(--ok); }
.p035-r-body {
  font-size: 13.5px;
  color: var(--ink-0);
  line-height: 1.6;
  margin-bottom: 6px;
}
.p035-r-body strong { font-weight: 600; }
.p035-r-evidence {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 2px 8px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-1);
  margin-right: 6px;
  margin-bottom: 4px;
}
.p035-r-evidence .val { font-weight: 500; }
.p035-r-evidence.warn .val { color: var(--p1); }
.p035-r-evidence.ok .val { color: var(--ok); }

/* ═══ Proposal card ═══ */
.p035-proposal {
  background: linear-gradient(180deg, var(--accent-soft) 0%, transparent 40%), var(--bg-1);
  border: 1px solid var(--accent-line);
  border-radius: 12px;
  overflow: hidden;
  margin: 10px 0;
}
.p035-proposal.executed {
  background: linear-gradient(180deg, var(--ok-soft) 0%, transparent 40%), var(--bg-1);
  border-color: var(--ok-line);
}
.p035-proposal-head { padding: 16px 18px 12px; }
.p035-proposal-tag {
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--accent);
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 6px;
}
.p035-proposal.executed .p035-proposal-tag { color: var(--ok); }
.p035-proposal-title {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 400;
  line-height: 1.4;
  margin-bottom: 4px;
}
.p035-proposal-title code {
  font-family: var(--font-mono);
  font-size: 13px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 6px;
  color: var(--accent);
}
.p035-proposal.executed .p035-proposal-title code { color: var(--ok); }
.p035-proposal-target {
  font-family: var(--font-mono);
  font-size: 12.5px;
  color: var(--ink-1);
}
.p035-proposal-body { padding: 0 18px 16px; }
.p035-proposal-body p {
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--ink-0);
  margin-bottom: 10px;
}
.p035-impact-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin: 10px 0 8px;
}
.p035-impact {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
}
.p035-impact .lb {
  font-size: 11px;
  color: var(--ink-2);
  margin-bottom: 3px;
}
.p035-impact .vl {
  font-size: 14px;
  font-weight: 500;
}
.p035-impact .vl small { font-size: 11.5px; color: var(--ink-1); font-weight: 400; }
.p035-confirm-strip {
  display: flex; align-items: center;
  gap: 8px;
  padding: 12px 18px;
  background: var(--bg-2);
  border-top: 1px solid var(--border);
}
.p035-confirm-strip .who {
  flex: 1;
  display: flex; align-items: center; gap: 8px;
  font-size: 12.5px;
  color: var(--ink-1);
}
.p035-confirm-strip .who strong { color: var(--ink-0); }
.p035-confirm-strip .who .a {
  width: 20px; height: 20px;
  border-radius: 50%;
  background: linear-gradient(135deg, #4A5F7A 0%, #2C3E52 100%);
  display: grid; place-items: center;
  font-size: 9px; font-weight: 600; color: #fff;
}
.p035-confirm-strip .check-icon {
  width: 20px; height: 20px;
  border-radius: 50%;
  background: var(--ok);
  display: grid; place-items: center;
  font-size: 11px; color: #fff;
}

/* ═══ Activity timeline ═══ */
.p035-activity {
  padding-left: 24px;
  border-left: 1px solid var(--border);
  margin-left: 4px;
}
.p035-act {
  display: grid;
  grid-template-columns: 70px 1fr;
  gap: 8px;
  padding-bottom: 16px;
  position: relative;
}
.p035-act::before {
  content: '';
  position: absolute;
  left: -28px; top: 5px;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--ink-3);
}
.p035-act.agent::before { background: var(--accent); }
.p035-act.human::before { background: var(--signal); }
.p035-act.system::before { background: var(--ink-3); }
.p035-act.ok-act::before { background: var(--ok); box-shadow: 0 0 0 3px var(--ok-soft); }
.p035-act-time {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-2);
}
.p035-act-text {
  font-size: 13px;
  color: var(--ink-0);
  line-height: 1.5;
}
.p035-who { font-weight: 500; }
.p035-who.agent { color: var(--accent); }
.p035-who.ok { color: var(--ok); }

/* ═══ Inline code ═══ */
.p035-inline-code {
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 1px 6px;
  background: var(--bg-3);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--accent);
}

/* ═══ Code block ═══ */
.p035-code-block {
  border: 1px solid var(--code-border);
  border-radius: 8px;
  overflow: hidden;
  margin: 8px 0;
}
.p035-code-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 14px;
  background: var(--code-head-bg);
  border-bottom: 1px solid var(--code-border);
}
.p035-code-lang {
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  color: var(--ink-2);
  letter-spacing: 0.06em;
}
.p035-code-body {
  background: var(--code-bg);
  padding: 12px 16px;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.65;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.p035-code-body .k { color: var(--code-k); }
.p035-code-body .fn { color: var(--code-fn); }
.p035-code-body .s { color: var(--code-s); }
.p035-code-body .n { color: var(--code-n); }
.p035-code-body .p { color: var(--code-p); }

/* ═══ Related incidents grid ═══ */
.p035-related-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 10px;
}
.p035-rel-card {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  transition: border-color 0.15s;
  cursor: pointer;
}
.p035-rel-card:hover { border-color: var(--border-strong); }
.p035-rel-head {
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  color: var(--ink-2);
  margin-bottom: 4px;
}
.p035-rel-sev {
  font-family: var(--font-display);
  font-style: italic;
  font-weight: 300;
  margin-right: 6px;
}
.p035-rel-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--ink-0);
  margin-bottom: 4px;
}
.p035-rel-meta { font-size: 12px; color: var(--ink-2); }

/* ═══ Checklist ═══ */
.p035-checklist-item {
  display: flex; align-items: center; gap: 10px;
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 6px;
}
.p035-check-box {
  width: 18px; height: 18px; min-width: 18px;
  border: 1.5px solid var(--border-strong);
  border-radius: 4px;
}
.p035-checklist-item.done .p035-check-box {
  background: var(--ok);
  border-color: var(--ok);
  color: #fff;
  display: grid; place-items: center;
  font-size: 11px;
}
.p035-checklist-item.done .p035-check-text {
  text-decoration: line-through;
  text-decoration-color: var(--ink-3);
  color: var(--ink-1);
}
.p035-check-text { flex: 1; font-size: 13px; }
.p035-check-assignee { font-size: 11.5px; color: var(--ink-2); }
.p035-check-tag {
  font-family: var(--font-mono);
  font-size: 10.5px;
  background: var(--bg-3);
  padding: 2px 8px;
  border-radius: 4px;
  color: var(--ink-1);
}

/* ═══ Link row ═══ */
.p035-link-row {
  display: flex; align-items: center; gap: 8px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 12.5px;
  color: var(--ink-0);
  text-decoration: none;
  transition: border-color 0.15s;
  margin: 6px 0;
}
.p035-link-row:hover { border-color: var(--border-strong); }
.p035-link-row .url {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--accent);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 360px;
}

/* ═══ Ô số (vitals grid, metric breakdown) ═══ */
.p035-luoi { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 1px; background: var(--border); border-radius: 10px; overflow: hidden; margin: .55rem 0 .35rem; }
.p035-so { background: var(--bg-1); padding: 14px 16px; }
.p035-so .nhan { font-family: var(--font-mono); font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: var(--ink-2); margin-bottom: 4px; }
.p035-so .gia-tri { font-family: var(--font-display); font-size: 28px; font-weight: 400; letter-spacing: -0.02em; line-height: 1.2; }
.p035-so .phu { font-size: 11.5px; color: var(--ink-2); margin-top: 2px; }

/* ═══ Khối log terminal ═══ */
.p035-terminal {
  background: var(--code-bg);
  border: 1px solid var(--code-border);
  border-radius: 8px;
  padding: .8rem 1rem;
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.7;
}
.p035-terminal .dong { white-space: pre-wrap; word-break: break-word; }
.p035-terminal .chinh {
  background: var(--p1-soft);
  border-left: 3px solid var(--p1);
  margin: .15rem -1rem; padding: .1rem 1rem .1rem calc(1rem - 3px);
}
.p035-terminal .ts { color: var(--ink-2); }
.p035-terminal .lv { font-weight: 700; }
.p035-terminal .src { color: var(--signal); }
.p035-terminal .msg { color: var(--ink-0); }
.p035-terminal .pat { color: var(--pending); }

/* ═══ Khối rủi ro / HITL ═══ */
.p035-hanh-dong {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 400;
  line-height: 1.4;
}
.p035-hanh-dong .mui { color: var(--ink-2); margin: 0 .3rem; }
.p035-rui-ro {
  background: var(--p2-soft); border: 1px solid rgba(245,165,36,.35);
  border-left: 3px solid var(--p2);
  border-radius: 8px; padding: .7rem .9rem; margin: .7rem 0;
  font-size: 13px; line-height: 1.6;
}
.p035-rui-ro .dau-de { color: var(--p2); font-weight: 600; display: block; margin-bottom: .15rem; }
.p035-hitl {
  background: var(--p1-soft); border: 1px solid rgba(229,72,77,.35);
  border-radius: 8px; padding: .7rem .9rem; margin: .7rem 0;
  font-size: 13px; line-height: 1.6;
}

/* ═══ Section header — eyebrow + title + aside ═══ */
.p035-sec-head {
  display: flex; align-items: baseline; gap: 12px;
  margin: 2.2rem 0 1.1rem;
}
.p035-sec-eyebrow {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-weight: 500;
  white-space: nowrap;
}
.p035-sec-title {
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.015em;
  color: var(--ink-0);
}
.p035-sec-title em {
  font-style: italic;
  font-weight: 300;
  color: var(--ink-1);
}
.p035-sec-aside {
  margin-left: auto;
  font-size: 12px;
  color: var(--ink-2);
  white-space: nowrap;
}

/* ═══ Vitals strip — 4-col grid ═══ */
.p035-vitals {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 22px;
}
.p035-vital { background: var(--bg-1); padding: 16px 18px; }
.p035-vital-label {
  font-family: var(--font-mono);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--ink-2);
  margin-bottom: 10px;
}
.p035-vital-value {
  font-family: var(--font-display);
  font-size: 30px;
  line-height: 1;
  font-weight: 400;
  letter-spacing: -0.02em;
  color: var(--ink-0);
  display: flex; align-items: baseline; gap: 6px;
  margin-bottom: 4px;
}
.p035-vital-value .unit {
  font-family: var(--font-body);
  font-size: 13px;
  color: var(--ink-1);
  font-weight: 400;
}
.p035-vital-value .delta {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 4px;
  margin-left: 4px;
}
.p035-vital-value .delta.bad { color: var(--p1); background: var(--p1-soft); }
.p035-vital-value .delta.good { color: var(--ok); background: var(--ok-soft); }
.p035-vital-sub { font-size: 11.5px; color: var(--ink-2); font-family: var(--font-mono); }
.p035-vital.alert { background: linear-gradient(180deg, var(--p1-soft) 0%, var(--bg-1) 60%); }
.p035-vital.alert .p035-vital-value { color: var(--p1); }
.p035-vital.ok { background: linear-gradient(180deg, var(--ok-soft) 0%, var(--bg-1) 60%); }
.p035-vital.ok .p035-vital-value { color: var(--ok); }

/* ═══ Reasoning timeline ═══ */
.p035-reasoning {
  padding-left: 24px;
  border-left: 1px solid var(--accent-line);
  margin-left: 4px;
  position: relative;
}
.p035-reasoning.done { border-left-color: var(--ok-line); }
.p035-reasoning-item { position: relative; padding-bottom: 20px; }
.p035-reasoning-item:last-child { padding-bottom: 0; }
.p035-reasoning-item::before {
  content: '';
  position: absolute;
  left: -29px; top: 5px;
  width: 9px; height: 9px;
  border-radius: 50%;
  background: var(--bg-0);
  border: 1.5px solid var(--accent);
}
.p035-reasoning.done .p035-reasoning-item::before { border-color: var(--ok); }
.p035-reasoning-item.conclusion::before {
  background: var(--accent);
  box-shadow: 0 0 0 4px var(--accent-soft);
}
.p035-reasoning.done .p035-reasoning-item.conclusion::before {
  background: var(--ok);
  box-shadow: 0 0 0 4px var(--ok-soft);
}
.p035-r-label {
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--accent);
  margin-bottom: 6px;
  font-weight: 500;
}
.p035-reasoning.done .p035-r-label { color: var(--ok); }
.p035-r-body { color: var(--ink-0); font-size: 13.5px; margin-bottom: 8px; }
.p035-r-body strong { font-weight: 600; }
.p035-r-evidence {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 8px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 5px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-1);
  margin-right: 6px;
  margin-bottom: 4px;
}
.p035-r-evidence .val { color: var(--ink-0); font-weight: 500; }
.p035-r-evidence.warn .val { color: var(--p1); }
.p035-r-evidence.ok .val { color: var(--ok); }

/* ═══ Activity timeline ═══ */
.p035-activity { padding-left: 24px; border-left: 1px solid var(--border); margin-left: 4px; }
.p035-act {
  position: relative;
  padding-bottom: 18px;
  display: grid;
  grid-template-columns: 60px 1fr;
  gap: 14px;
  align-items: baseline;
}
.p035-act::before {
  content: '';
  position: absolute;
  left: -28px; top: 6px;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--ink-3);
}
.p035-act.agent::before { background: var(--accent); }
.p035-act.human::before { background: var(--signal); }
.p035-act.system::before { background: var(--ink-3); }
.p035-act.ok::before { background: var(--ok); box-shadow: 0 0 0 3px var(--ok-soft); }
.p035-act .time { font-family: var(--font-mono); font-size: 11px; color: var(--ink-2); }
.p035-act .text { font-size: 13px; color: var(--ink-0); }
.p035-act .text .who { color: var(--ink-1); font-weight: 500; }
.p035-act .text .who.agent { color: var(--accent); }
.p035-act .text .who.ok { color: var(--ok); font-weight: 600; }

/* ═══ Impact grid (inside proposal) ═══ */
.p035-impact-grid {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 12px; margin: 14px 0;
}
.p035-impact {
  padding: 12px 14px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.p035-impact .lb {
  font-family: var(--font-mono);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-2);
  margin-bottom: 5px;
}
.p035-impact .vl {
  font-size: 15px; font-weight: 500;
  color: var(--ink-0);
  display: flex; align-items: baseline; gap: 4px;
}
.p035-impact .vl small { font-size: 11px; color: var(--ink-1); font-weight: 400; }

/* ═══ Confirm strip (inside proposal) ═══ */
.p035-confirm-strip {
  display: flex; align-items: center;
  padding: 14px 22px;
  background: var(--bg-2);
  border-top: 1px solid var(--border);
  border-radius: 0 0 12px 12px;
  gap: 12px;
  font-size: 12px;
  color: var(--ink-1);
}
.p035-confirm-strip strong { color: var(--ink-0); font-weight: 500; }

/* ── keep old p035-muc as alias ── */
.p035-muc { display: flex; align-items: baseline; gap: 10px; margin: 1.6rem 0 .35rem; }
.p035-muc .so {
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: var(--accent);
  font-weight: 500;
  white-space: nowrap;
}
.p035-muc .chu {
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.01em;
}
.p035-muc .chu em {
  font-style: italic;
  font-weight: 300;
  color: var(--ink-1);
}

/* ═══ Case header — breadcrumb + title + meta ═══ */
.p035-dau-trang { margin-bottom: 1.2rem; }
.p035-crumb {
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-2);
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.p035-crumb .sep { color: var(--ink-3); margin: 0 2px; }
.p035-status-pill {
  font-family: var(--font-body);
  font-size: 10.5px;
  text-transform: none;
  letter-spacing: 0;
  padding: 2px 8px;
  border-radius: 99px;
  font-weight: 500;
}
.p035-status-pill.live {
  background: var(--p1-soft);
  color: var(--p1);
}
.p035-status-pill.live::before {
  content: ''; width: 5px; height: 5px; border-radius: 50%;
  background: var(--p1); display: inline-block;
  animation: p035-blink 1.5s ease-in-out infinite;
}
.p035-status-pill.done {
  background: var(--ok-soft);
  color: var(--ok);
}
.p035-status-pill.done::before { content: '\2713'; font-size: 10px; line-height: 1; }
@keyframes p035-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: .3; }
}
.p035-case-title {
  font-family: var(--font-display);
  font-size: 34px;
  font-weight: 400;
  letter-spacing: -0.02em;
  line-height: 1.15;
  margin-bottom: 14px;
  color: var(--ink-0);
}
.p035-case-title .sev {
  font-style: italic;
  font-weight: 300;
  margin-right: 6px;
}
.p035-case-title .sev.p1 { color: var(--p1); }
.p035-case-title .sev.p2 { color: var(--p2); }
.p035-case-title .sev.p3 { color: var(--p3); }
.p035-case-title .sev.done { color: var(--ok); }
.p035-case-title .service {
  font-size: 18px;
  font-weight: 300;
  color: var(--ink-1);
}
.p035-case-meta {
  display: flex; flex-wrap: wrap; align-items: center; gap: 22px;
  padding: 14px 0;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  margin-bottom: 32px;
  font-size: 12.5px;
  color: var(--ink-1);
}
.p035-case-meta .val {
  color: var(--ink-0);
  font-weight: 500;
}

/* ═══ Sidebar branding ═══ */
.p035-sidebar-eyebrow {
  font-family: var(--font-mono);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  color: var(--accent);
  font-weight: 500;
  margin-bottom: 2px;
}
.p035-sidebar-title {
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.01em;
  margin-bottom: 8px;
}
.p035-sidebar-title em {
  font-style: italic;
  font-weight: 300;
  color: var(--ink-1);
}

/* ═══ Streamlit widgets override ═══ */
[data-testid="stButton"] > button, .stButton > button,
[data-testid="stLinkButton"] > a, .stLinkButton > a {
  border-radius: 7px;
  font-size: 12.5px;
  font-weight: 500;
  transition: all .15s ease;
}
[data-testid="stButton"] > button:hover, .stButton > button:hover,
[data-testid="stLinkButton"] > a:hover, .stLinkButton > a:hover {
  transform: translateY(-1px);
}
[data-testid="stExpander"] details {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-1);
}
[data-testid="stMetric"] {
  background: var(--bg-1); border: 1px solid var(--border);
  border-radius: 8px; padding: .85rem 1rem;
}
[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }
[data-testid="stCaptionContainer"] { line-height: 1.65; }
[data-testid="stAlert"] { border-radius: 8px; }

/* ── Buttons: Approve/Reject ── */
.p035-btn-duyet > [data-testid="stButton"] > button,
.p035-btn-duyet > [data-testid="stLinkButton"] > a {
  background-color: var(--btn-primary-bg) !important;
  border-color: var(--btn-primary-bg) !important;
  color: var(--btn-primary-fg) !important;
  font-weight: 500;
}
.p035-btn-duyet > [data-testid="stButton"] > button:hover,
.p035-btn-duyet > [data-testid="stLinkButton"] > a:hover {
  filter: brightness(1.05);
}
.p035-btn-tu-choi > [data-testid="stButton"] > button,
.p035-btn-tu-choi > [data-testid="stLinkButton"] > a {
  background: transparent !important;
  color: var(--ink-1) !important;
  border: 1px solid var(--border-strong) !important;
}
.p035-btn-tu-choi > [data-testid="stButton"] > button:hover,
.p035-btn-tu-choi > [data-testid="stLinkButton"] > a:hover {
  color: var(--ink-0) !important;
  background: var(--bg-3) !important;
}

/* ═══ Sidebar incident cards ═══ */
.p035-inc-card {
  padding: 10px 12px 10px 14px;
  border-radius: 7px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background 0.12s, border-color 0.12s;
  margin-bottom: 4px;
}
.p035-inc-card:hover { background: var(--bg-hover); }
.p035-inc-card.active {
  background: var(--bg-2);
  border-color: var(--border-strong);
  position: relative;
}
.p035-inc-card.active::before {
  content: '';
  position: absolute;
  left: 0; top: 10px; bottom: 10px;
  width: 2px;
  background: var(--accent);
  border-radius: 1px;
}
.p035-inc-row1 { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.p035-inc-sev {
  font-family: var(--font-display);
  font-style: italic;
  font-size: 15px;
  font-weight: 300;
}
.p035-inc-sev.p1 { color: var(--p1); }
.p035-inc-sev.p2 { color: var(--p2); }
.p035-inc-sev.p3 { color: var(--p3); }
.p035-inc-sev.done { color: var(--ok); }
.p035-inc-id {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--ink-2);
}
.p035-inc-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  margin-left: auto;
}
.p035-inc-dot.active { background: var(--p1); box-shadow: 0 0 0 3px var(--p1-soft); }
.p035-inc-dot.pending { background: var(--pending); }
.p035-inc-dot.resolving { background: var(--p2); }
.p035-inc-dot.resolved { background: var(--ok); }
.p035-inc-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--ink-0);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: 4px;
}
.p035-inc-meta {
  display: flex; align-items: center; gap: 10px;
  font-size: 11.5px;
  color: var(--ink-2);
}
.p035-inc-meta .dot-sep { color: var(--ink-3); }
.p035-sparkline { margin-left: auto; opacity: 0.85; }

/* ═══ Sidebar card selection button — minimal ═══ */
.p035-card-btn {
  margin-top: 4px;
}
.p035-card-btn button {
  background: transparent !important;
  border: 1px solid var(--border) !important;
  border-radius: 5px !important;
  color: var(--ink-2) !important;
  font-size: 11px !important;
  height: 24px !important;
  padding: 0 10px !important;
  min-height: 0 !important;
  transition: all 0.15s !important;
}
.p035-card-btn button:hover {
  background: var(--bg-3) !important;
  color: var(--ink-0) !important;
  border-color: var(--border-strong) !important;
}
.p035-card-btn-selected button {
  background: var(--accent-soft) !important;
  border-color: var(--accent-line) !important;
  color: var(--accent) !important;
  font-size: 11px !important;
  height: 24px !important;
  padding: 0 10px !important;
  min-height: 0 !important;
}

/* ═══ Evidence card ═══ */
.p035-evidence {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px 18px;
  margin: 8px 0;
}
.p035-evidence p {
  font-size: 13.5px;
  line-height: 1.6;
}

/* ═══ War room page title in sidebar ═══ */
.p035-sidebar-title {
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.015em;
  line-height: 1.15;
  margin-bottom: 14px;
}
.p035-sidebar-title em { font-style: italic; font-weight: 300; color: var(--ink-1); }
.p035-sidebar-eyebrow {
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--ink-2);
  margin-bottom: 8px;
}

/* ═══ Tabs ═══ */
.p035-tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border); margin-bottom: 10px; padding: 0 4px; }
.p035-tab {
  padding: 8px 12px 10px;
  font-size: 12.5px;
  color: var(--ink-1);
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  cursor: pointer;
  display: flex; align-items: center; gap: 6px;
  transition: color 0.15s;
}
.p035-tab:hover { color: var(--ink-0); }
.p035-tab.active {
  color: var(--ink-0);
  border-bottom-color: var(--accent);
}
.p035-tab .count {
  font-family: var(--font-mono);
  font-size: 10.5px;
  background: var(--bg-3);
  padding: 1px 6px;
  border-radius: 8px;
  color: var(--ink-1);
}
.p035-tab.active .count {
  background: var(--accent-soft);
  color: var(--accent);
}

/* ═══ Chart panel ═══ */
.p035-chart-panel {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 20px 12px;
  margin-bottom: 22px;
}
.p035-chart-head {
  display: flex; align-items: center; gap: 12px;
  margin-bottom: 14px;
}
.p035-chart-title {
  font-size: 13px; font-weight: 500; color: var(--ink-0);
}
.p035-chart-title .code {
  font-family: var(--font-mono);
  color: var(--accent);
  font-weight: 400;
}
.p035-chart-legend {
  margin-left: auto;
  display: flex; gap: 14px;
  font-size: 11.5px;
  color: var(--ink-1);
}
.p035-chart-legend .item { display: flex; align-items: center; gap: 6px; }
.p035-chart-legend .swatch { width: 10px; height: 2px; border-radius: 1px; }
.p035-chart-svg { width: 100%; height: 200px; }
.p035-chart-foot {
  display: flex; justify-content: space-between;
  padding-top: 8px;
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--ink-2);
}

/* ═══ Awaiting pill in sidebar ═══ */
.p035-await-pill {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10.5px;
  font-family: var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-top: 4px;
}
"""

CSS = "<style>" + _CSS_TINH + "</style>"

# `set_page_config` phải chạy trước mọi lệnh Streamlit khác.
st.set_page_config(page_title="War room", page_icon="P035", layout="wide")
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
    """Badge P1–P4 — tên đọc từ `labels.SEVERITY`, màu từ `labels.SEVERITY_MAU`.

    Giữ mã gốc ("P1") ngay trong badge: đó là chữ người trực trao đổi với nhau.
    Không dùng emoji icon — chỉ text.
    """
    _, ten, _ = labels.SEVERITY.get(muc, ("", muc, ""))
    return pill(f"{ten} · {muc}", labels.mau_severity(muc))


def pill_state(trang_thai: str) -> str:
    """Badge trạng thái — đọc từ `labels.STATE`. Không dùng emoji."""
    _, ten = labels.STATE.get(trang_thai, ("", trang_thai))
    if trang_thai == "Awaiting Approval":
        mau = labels.MAU["cam"]
    elif trang_thai == "Resolved":
        mau = labels.MAU["xanh"]
    else:
        mau = labels.MAU["nhan"]
    return pill(ten, mau)


def muc(eyebrow: str, tieu_de: str, *, aside: str = "") -> None:
    """Tiêu đề section theo reference HTML: eyebrow + serif title + aside."""
    aside_html = f'<span class="p035-sec-aside">{html.escape(aside)}</span>' if aside else ""
    st.markdown(
        f'<div class="p035-sec-head">'
        f'<span class="p035-sec-eyebrow">{html.escape(eyebrow)}</span>'
        f'<span class="p035-sec-title">{tieu_de}</span>'
        f'{aside_html}'
        f'</div>',
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
        st.markdown(f"{pill('chỉ số kích hoạt', labels.MAU['do'])} **{dong.plain}**", unsafe_allow_html=True)
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
        "ERROR = lỗi · WARNING = cảnh báo · INFO = thông tin."
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
        st.button("Làm mới", key=f"lam-moi-{jira_key}", on_click=truy_van_range.clear, use_container_width=False)

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


def khoi_bieu_do_svg(signal: dict, luc_phat_hien: str) -> None:
    """Chart panel matching reference HTML — renders inline SVG.

    Uses Prometheus data when available, falls back to a visual placeholder.
    Format: .chart-panel > .chart-head (title + legend) + SVG + .chart-foot
    """
    ten_metric = signal.get("metric_name", "metric")
    nguong = float(signal.get("threshold", 0))
    bang_chung = [ev for ev in (signal.get("evidence") or []) if ev.get("promql")]

    # Get main evidence promql
    main_ev = next(
        (ev for ev in bang_chung if ev["name"] == ten_metric),
        bang_chung[0] if bang_chung else None,
    )

    baseline = float(main_ev["baseline"]) if main_ev and main_ev.get("baseline") is not None else None

    # Try to query Prometheus
    ket_thuc = int(datetime.now(UTC).timestamp() // LAM_MOI_GIAY * LAM_MOI_GIAY)
    do_dai = CUA_SO_GIAY[CUA_SO_MAC_DINH]  # 15 min default
    bat_dau = ket_thuc - do_dai
    buoc = max(15, -(-do_dai // SO_DIEM_TOI_DA))

    data_points: list[tuple[float, float]] = []  # (timestamp, value)
    if main_ev:
        ket_qua = truy_van_range(main_ev["promql"], bat_dau, ket_thuc, buoc)
        if ket_qua["ok"] and ket_qua["chuoi"]:
            # Extract first time series
            chuoi = ket_qua["chuoi"][0]
            values = chuoi.get("values") or chuoi.get("dps") or []
            for ts_val in values:
                if isinstance(ts_val, (list, tuple)) and len(ts_val) >= 2:
                    data_points.append((float(ts_val[0]), float(ts_val[1])))

    # Convert to SVG coordinates
    rong, cao = 800, 200
    if data_points:
        timestamps = [p[0] for p in data_points]
        values = [p[1] for p in data_points]
        t_min, t_max = min(timestamps), max(timestamps)
        v_min = min(min(values), (nguong * 0.5 if nguong else 0), (baseline * 0.5 if baseline else 0))
        v_max = max(max(values), (nguong * 1.3 if nguong else max(values)), (baseline * 1.2 if baseline else max(values)))
        if v_max == v_min:
            v_max = v_min + 1

        def _x(t: float) -> float:
            return (t - t_min) / (t_max - t_min) * rong if t_max != t_min else rong / 2

        def _y(v: float) -> float:
            return cao - ((v - v_min) / (v_max - v_min) * (cao - 20) + 10)

        # Data path
        path_parts = []
        for i, (t, v) in enumerate(data_points):
            cmd = "M" if i == 0 else "L"
            path_parts.append(f"{cmd}{_x(t):.0f} {_y(v):.0f}")
        data_path = " ".join(path_parts)

        # Area fill path
        area_path = data_path + f" L{rong} {cao} L0 {cao} Z"

        # Threshold Y
        nguong_y = _y(nguong) if nguong else None

        # Baseline path
        baseline_path = ""
        if baseline is not None:
            bl_y = _y(baseline)
            baseline_path = (
                f'<line x1="0" y1="{bl_y:.0f}" x2="{rong}" y2="{bl_y:.0f}" '
                f'stroke="var(--ink-2)" stroke-width="1" stroke-dasharray="3 3" opacity="0.65"/>'
            )

        # Last point (current value dot)
        last_x, last_y = _x(data_points[-1][0]), _y(data_points[-1][1])
        breach = data_points[-1][1] >= nguong if nguong else False
        dot_color = "var(--p1)" if breach else "var(--signal)"

        # Grid lines
        grid = ""
        for frac in [0.2, 0.4, 0.6, 0.8]:
            gy = cao * frac
            grid += f'<line x1="0" y1="{gy:.0f}" x2="{rong}" y2="{gy:.0f}" stroke="var(--border)" stroke-dasharray="2 4"/>'

        # Threshold line
        threshold_line = ""
        if nguong_y is not None:
            threshold_line = (
                f'<line x1="0" y1="{nguong_y:.0f}" x2="{rong}" y2="{nguong_y:.0f}" '
                f'stroke="var(--p1)" stroke-width="1" stroke-dasharray="4 4" opacity="0.55"/>'
                f'<text x="6" y="{nguong_y - 4:.0f}" font-family="JetBrains Mono" font-size="9" '
                f'fill="var(--p1)" opacity="0.85">ngưỡng {_so_doc_duoc(nguong, "")}</text>'
            )

        # Time labels
        time_labels: list[str] = []
        n_labels = 5
        for i in range(n_labels):
            t = t_min + (t_max - t_min) * i / (n_labels - 1)
            dt = datetime.fromtimestamp(t, tz=UTC).astimezone(tz=None)
            time_labels.append(dt.strftime("%cao:%M"))
        time_labels[-1] = "Bây giờ"

        svg_content = (
            f'{grid}'
            f'{threshold_line}'
            f'{baseline_path}'
            f'<defs><linearGradient id="area-g" x1="0" x2="0" y1="0" y2="1">'
            f'<stop offset="0%" stop-color="var(--signal)" stop-opacity="0.28"/>'
            f'<stop offset="100%" stop-color="var(--signal)" stop-opacity="0"/>'
            f'</linearGradient></defs>'
            f'<path d="{area_path}" fill="url(#area-g)"/>'
            f'<path d="{data_path}" fill="none" stroke="var(--signal)" stroke-width="1.75"/>'
            f'<circle cx="{last_x:.0f}" cy="{last_y:.0f}" r="4" fill="{dot_color}"/>'
            f'<circle cx="{last_x:.0f}" cy="{last_y:.0f}" r="8" fill="{dot_color}" opacity="0.2"/>'
        )

        foot_html = "".join(f'<span>{html.escape(nhan)}</span>' for nhan in time_labels)
    else:
        # No data — render placeholder
        svg_content = (
            '<line x1="0" y1="40" x2="800" y2="40" stroke="var(--border)" stroke-dasharray="2 4"/>'
            '<line x1="0" y1="80" x2="800" y2="80" stroke="var(--border)" stroke-dasharray="2 4"/>'
            '<line x1="0" y1="120" x2="800" y2="120" stroke="var(--border)" stroke-dasharray="2 4"/>'
            '<line x1="0" y1="160" x2="800" y2="160" stroke="var(--border)" stroke-dasharray="2 4"/>'
            '<text x="400" y="105" font-family="Inter" font-size="12" fill="var(--ink-2)" '
            'text-anchor="middle">Prometheus không khả dụng</text>'
        )
        if nguong:
            svg_content += (
                f'<line x1="0" y1="100" x2="800" y2="100" '
                f'stroke="var(--p1)" stroke-width="1" stroke-dasharray="4 4" opacity="0.55"/>'
                f'<text x="6" y="96" font-family="JetBrains Mono" font-size="9" '
                f'fill="var(--p1)" opacity="0.85">ngưỡng {_so_doc_duoc(nguong, "")}</text>'
            )
        foot_html = "<span>—</span><span>—</span><span>—</span><span>—</span><span>—</span>"

    # Legend
    legend = (
        '<div class="p035-chart-legend">'
        '<span class="item"><span class="swatch" style="background: var(--signal)"></span>Giá trị</span>'
        + ('<span class="item"><span class="swatch" style="background: var(--ink-2)"></span>baseline</span>' if baseline is not None else "")
        + '<span class="item"><span class="swatch" style="background: var(--p1)"></span>ngưỡng</span>'
        + '</div>'
    )

    st.markdown(
        f'<div class="p035-chart-panel">'
        f'<div class="p035-chart-head">'
        f'<div class="p035-chart-title"><span class="code">{html.escape(ten_metric)}</span></div>'
        f'{legend}'
        f'</div>'
        f'<svg class="p035-chart-svg" viewBox="0 0 {rong} {cao}" preserveAspectRatio="none">'
        f'{svg_content}'
        f'</svg>'
        f'<div class="p035-chart-foot">{foot_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Khối lớn của trang
# ---------------------------------------------------------------------------


def _sparkline_svg(inc: dict) -> str:
    """Generate a 52×16 sparkline SVG showing trend direction.

    For active incidents: rising trend (bad). For resolved: peak-then-fall (recovered).
    Color follows severity for active, --ok for resolved.
    """
    da_xong = inc["state"] not in DANG_XAY_RA
    sev = inc["severity"]
    if da_xong:
        # Mountain shape: went up then came back down
        points = "M0 12 L8 10 L16 4 L22 2 L28 5 L36 9 L44 12 L52 13"
        color = "var(--ok)"
    elif sev == "P1":
        points = "M0 12 L6 11 L12 12 L18 10 L24 9 L30 7 L36 5 L42 4 L48 2 L52 3"
        color = "var(--p1)"
    elif sev == "P2":
        points = "M0 13 L8 13 L16 12 L24 10 L32 8 L40 6 L48 4 L52 3"
        color = "var(--p2)"
    else:
        points = "M0 10 L8 9 L16 8 L24 7 L32 6 L40 5 L48 5 L52 4"
        color = "var(--p3)"
    return (
        f'<svg width="52" height="16" viewBox="0 0 52 16" class="p035-sparkline">'
        f'<path d="{points}" fill="none" stroke="{color}" stroke-width="1.5"/>'
        f'</svg>'
    )


def the_incident(inc: dict) -> None:
    """Một thẻ trong danh sách bên trái — redesign theo reference HTML.

    Render toàn bộ card dưới dạng 1 khối HTML: inc-row1 (sev + id + status dot),
    inc-title (line-clamp 2), inc-meta (duration + sparkline SVG).
    Button giữ lại cho Streamlit rerun nhưng style tối giản.
    """
    is_selected = inc["jira_key"] == st.session_state["selected_key"]
    da_xong = inc["state"] not in DANG_XAY_RA

    # Severity class for italic serif display
    sev = inc["severity"]
    sev_class = "done" if da_xong else sev.lower()

    # Status dot class
    if inc["state"] == "Awaiting Approval":
        dot_class = "pending"
    elif inc["state"] == "Remediating":
        dot_class = "resolving"
    elif da_xong:
        dot_class = "resolved"
    else:
        dot_class = "active"

    # Duration text
    if inc.get("resolved_at"):
        thoi_luong = fmt_duration(inc["detected_at"], inc["resolved_at"])
    else:
        thoi_luong = fmt_duration(inc["detected_at"])

    # Service
    dich_vu = (inc["affected_services"] or [""])[0]
    dich_vu_vn = labels.service(dich_vu)

    # Sparkline
    spark = _sparkline_svg(inc)

    # Awaiting approval indicator
    await_html = ""
    if inc["state"] == "Awaiting Approval":
        await_html = (
            f'<div class="p035-await-pill" '
            f'style="color:{labels.MAU["cam"]};background:{_rgba(labels.MAU["cam"], 0.14)}">'
            f'Chờ duyệt</div>'
        )

    # Active class
    card_class = "p035-inc-card active" if is_selected else "p035-inc-card"

    st.markdown(
        f'<div class="{card_class}">'
        f'<div class="p035-inc-row1">'
        f'<span class="p035-inc-sev {sev_class}">{html.escape(sev)}</span>'
        f'<span class="p035-inc-id">{html.escape(inc["jira_key"])}</span>'
        f'<span class="p035-inc-dot {dot_class}"></span>'
        f'</div>'
        f'<div class="p035-inc-title">{html.escape(inc["title"])}</div>'
        f'<div class="p035-inc-meta">'
        f'<span>{html.escape(thoi_luong)}</span>'
        + (f'<span>·</span><span>{html.escape(dich_vu_vn)}</span>' if dich_vu_vn else "")
        + spark
        + '</div>'
        + await_html
        + '</div>',
        unsafe_allow_html=True,
    )
    btn_cls = "p035-card-btn-selected" if is_selected else "p035-card-btn"
    st.markdown(f'<div class="{btn_cls}">', unsafe_allow_html=True)
    if st.button(
        "Đang xem" if is_selected else "Xem →",
        key=f"sel-{inc['jira_key']}",
        type="secondary",
        use_container_width=True,
    ):
        st.session_state["selected_key"] = inc["jira_key"]
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def dau_trang_incident(incident: dict) -> None:
    """Đầu trang chi tiết — redesign: breadcrumb, serif title, meta strip."""
    da_xong_roi = bool(incident.get("resolved_at"))
    sev = incident["severity"]
    icon_s, ten_s, giai_thich = labels.SEVERITY.get(sev, ("⚪", sev, ""))
    sev_class = "done" if da_xong_roi else sev.lower()

    # Status pill
    if da_xong_roi:
        icon_st, ten_st = labels.STATE.get("Resolved", ("✅", "Đã xử lý xong"))
        status_pill = f'<span class="p035-status-pill done">{html.escape(icon_st)} {html.escape(ten_st)}</span>'
    else:
        icon_st, ten_st = labels.STATE.get(incident["state"], ("•", incident["state"]))
        status_pill = f'<span class="p035-status-pill live">{html.escape(ten_st)}</span>'

    dich_vu = " · ".join(
        f"{html.escape(labels.service(s))}" for s in incident["affected_services"]
    )

    thoi_gian_items: list[str] = []
    thoi_gian_items.append(f'Phát hiện <span class="val">{html.escape(fmt_time_vn(incident["detected_at"]))}</span>')
    if incident.get("resolved_at"):
        thoi_gian_items.append(f'Xử lý <span class="val">{html.escape(fmt_time_vn(incident["resolved_at"]))}</span>')
        thoi_gian_items.append(f'Kéo dài <span class="val">{html.escape(fmt_duration(incident["detected_at"], incident["resolved_at"]))}</span>')
    else:
        thoi_gian_items.append(f'Đang kéo dài <span class="val">{html.escape(fmt_duration(incident["detected_at"]))}</span>')

    meta_html = " · ".join(thoi_gian_items)

    st.markdown(
        '<div class="p035-dau-trang">'
        f'<div class="p035-crumb">'
        f'War Room<span class="sep">›</span>'
        f'{html.escape(incident["jira_key"])}'
        f' {status_pill}'
        f'</div>'
        f'<div class="p035-case-title">'
        f'<span class="sev {sev_class}">{html.escape(sev)}</span>'
        f'{html.escape(incident["title"])}'
        f' <span class="service">'
        f'— {html.escape(dich_vu)}'
        f'</span>'
        f'</div>'
        f'<div class="p035-case-meta">'
        f'{meta_html}'
        f'</div>'
        '</div>',
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

    # ── (a) Vitals strip
    gia_tri = float(signal["metric_value"])
    nguong = float(signal["threshold"])
    lech = gia_tri / nguong if nguong else 0
    lech_str = f"{lech:.1f}×"
    keo_dai_str = labels.keo_dai(signal["breached_for_seconds"])

    vital_1 = (
        f'<div class="p035-vital alert">'
        f'<div class="p035-vital-label">{html.escape(cau)}</div>'
        f'<div class="p035-vital-value">{html.escape(_so_doc_duoc(gia_tri, don_vi))}'
        f'<span class="delta bad">{html.escape(lech_str)}</span></div>'
        f'<div class="p035-vital-sub">Giá trị hiện tại</div>'
        f'</div>'
    )
    vital_2 = (
        f'<div class="p035-vital">'
        f'<div class="p035-vital-label">Ngưỡng cảnh báo</div>'
        f'<div class="p035-vital-value">{html.escape(_so_doc_duoc(nguong, don_vi))}</div>'
        f'<div class="p035-vital-sub">Mức bắt đầu coi là sự cố</div>'
        f'</div>'
    )
    vital_3 = (
        f'<div class="p035-vital alert">'
        f'<div class="p035-vital-label">Kéo dài</div>'
        f'<div class="p035-vital-value">{html.escape(keo_dai_str)}</div>'
        f'<div class="p035-vital-sub">Từ lúc vượt ngưỡng</div>'
        f'</div>'
    )
    baseline_ev = kich_hoat.get("baseline") if kich_hoat else None
    if baseline_ev is not None:
        bl = float(baseline_ev)
        lech_bl = f"{gia_tri / bl:.1f}×" if bl else "—"
        vital_4 = (
            f'<div class="p035-vital">'
            f'<div class="p035-vital-label">Mức thường ngày</div>'
            f'<div class="p035-vital-value">{html.escape(_so_doc_duoc(bl, don_vi))}'
            f'<span class="delta bad">{html.escape(lech_bl)}</span></div>'
            f'<div class="p035-vital-sub">Baseline đo được</div>'
            f'</div>'
        )
    else:
        vital_4 = (
            f'<div class="p035-vital">'
            f'<div class="p035-vital-label">Dịch vụ</div>'
            f'<div class="p035-vital-value" style="font-size:18px">{html.escape(signal.get("affected_service", ""))}</div>'
            f'<div class="p035-vital-sub">Dịch vụ bị ảnh hưởng</div>'
            f'</div>'
        )

    st.markdown(
        f'<div class="p035-vitals">{vital_1}{vital_2}{vital_3}{vital_4}</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"↳ `{signal['metric_name']} = {signal['metric_value']:g}` "
        f"(ngưỡng `{signal['threshold']:g}`, dịch vụ `{signal.get('affected_service', '')}`)"
    )
    if kich_hoat is not None:
        khoi_promql(kich_hoat.get("promql", ""), luc, gap=False)

    # SVG chart panel matching reference HTML
    khoi_bieu_do_svg(signal, luc)

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
    da_thuc_hien = incident["state"] == "Resolved"
    executed_class = " executed" if da_thuc_hien else ""

    st.markdown(
        f'<div class="p035-proposal{executed_class}">'
        f'<div class="p035-proposal-head">'
        f'<div class="p035-proposal-tag">{"Đã thực hiện" if da_thuc_hien else "Đề xuất của AI"}</div>'
        f'<div class="p035-proposal-title">'
        f'{html.escape(labels.action(proposal["action"]))}'
        f' <span class="mui">→</span> '
        f'<code>{html.escape(str(proposal["target"]))}</code>'
        f'</div>'
        + (f'<div class="p035-proposal-target">Tham số: {html.escape(str(proposal["params"]))}</div>' if proposal.get("params") else "")
        + '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    with st.container():
        dau_the("p035-neon" if incident["state"] == "Awaiting Approval" else "")

        # (2) Rủi ro
        if proposal.get("risk"):
            st.markdown(
                '<div class="p035-rui-ro"><span class="dau-de">Đánh đổi cần cân nhắc</span>'
                f"{html.escape(proposal['risk'])}</div>",
                unsafe_allow_html=True,
            )

        if proposal.get("requires_approval"):
            st.markdown(
                '<div class="p035-hitl"><b>AI KHÔNG tự thực hiện hành động này.</b> '
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
                st.markdown('<div class="p035-btn-duyet">', unsafe_allow_html=True)
                st.link_button("Duyệt trên Jira", phieu, type="primary", use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
            with cot_tu_choi:
                st.markdown('<div class="p035-btn-tu-choi">', unsafe_allow_html=True)
                st.link_button("Từ chối trên Jira", phieu, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
            st.caption(
                f"↳ Hai nút này **mở phiếu Jira** `{incident['jira_key']}`. Thao tác duyệt/từ chối "
                "xảy ra ở đó — trang này chỉ hiển thị, không thi hành hành động nào."
            )
        else:
            with cot_duyet:
                st.markdown('<div class="p035-btn-duyet">', unsafe_allow_html=True)
                duyet = st.button("Duyệt", type="primary", use_container_width=True, key=f"duyet-{incident['jira_key']}")
                st.markdown('</div>', unsafe_allow_html=True)
            with cot_tu_choi:
                st.markdown('<div class="p035-btn-tu-choi">', unsafe_allow_html=True)
                tu_choi = st.button("Từ chối", use_container_width=True, key=f"tu-choi-{incident['jira_key']}")
                st.markdown('</div>', unsafe_allow_html=True)
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

st.markdown(
    '<div class="p035-sidebar-eyebrow">Bảng theo dõi</div>'
    '<div class="p035-sidebar-title">Sự cố <em>của hệ thống</em></div>',
    unsafe_allow_html=True,
)

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
    cho_duyet = next((i for i in dang_xay_ra if i["state"] == "Awaiting Approval"), None)
    default = cho_duyet or (dang_xay_ra[0] if dang_xay_ra else None)
    st.session_state["selected_key"] = default["jira_key"] if default else None

col_list, col_detail = st.columns([1, 2], gap="large")

with col_list:
    # Tabs header matching reference HTML
    tab_active_cls = "p035-tab active"
    tab_resolved_cls = "p035-tab"
    st.markdown(
        f'<div class="p035-tabs">'
        f'<div class="{tab_active_cls}">Đang xảy ra <span class="count">{len(dang_xay_ra)}</span></div>'
        f'<div class="{tab_resolved_cls}">Đã xử lí <span class="count">{len(da_xong)}</span></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if not dang_xay_ra:
        st.success("Không có sự cố nào đang diễn ra.")
    for inc in dang_xay_ra:
        the_incident(inc)

    if da_xong:
        with st.expander(f"Đã xử lý ({len(da_xong)})", expanded=False):
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
            st.success("### Hệ thống đang bình thường\n\nKhông có sự cố nào đang diễn ra.")
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
                st.markdown(
                    '<div class="p035-hitl"><b>CẦN NGƯỜI DUYỆT</b> — '
                    'AI đã chẩn đoán xong và đề xuất cách sửa bên dưới. '
                    'Cần người xem xét rồi bấm duyệt trên Jira.</div>',
                    unsafe_allow_html=True,
                )

            muc("01 · Bằng chứng", "Agent <em>thấy gì</em>")
            bang_dieu_tra(incident, signal)

            muc("02 · Lập luận", "Agent <em>nghĩ vì sao</em>")
            hypotheses = incident.get("hypotheses") or []
            if hypotheses:
                da_xong_h = incident["state"] == "Resolved"
                done_cls = " done" if da_xong_h else ""
                items_html: list[str] = []
                for idx, h in enumerate(hypotheses):
                    is_last = idx == len(hypotheses) - 1
                    item_cls = "conclusion" if is_last else ""
                    # Confidence tag
                    conf = h["confidence"]
                    conf_pct = f"{conf * 100:.0f}%"
                    # Evidence tags
                    ev_tags = ""
                    for ev in (h.get("evidence") or []):
                        dong = labels.bang_chung(
                            ev["name"], ev["value"],
                            baseline=ev.get("baseline"),
                            unit=ev.get("unit", ""),
                            promql=ev.get("promql", ""),
                        )
                        warn_cls = "warn" if float(ev["value"]) > float(ev.get("baseline") or ev["value"]) else "ok"
                        ev_tags += (
                            f'<span class="p035-r-evidence {warn_cls}">'
                            f'{html.escape(dong.plain[:60])}'
                            f'</span>'
                        )
                    # Deploy tag
                    deploy_html = ""
                    deploy = h.get("related_deploy")
                    if deploy:
                        deploy_html = (
                            f'<div style="margin-top:8px;font-size:12px;color:var(--p2)">'
                            f'Trùng deploy: <code>{html.escape(deploy["version"])}</code> '
                            f'lúc {html.escape(fmt_time_vn(deploy["deployed_at"]))}'
                            f'</div>'
                        )
                    # Log tag
                    log_html = ""
                    if h.get("log_evidence"):
                        log_html = (
                            f'<div style="margin-top:4px;font-size:11px;color:var(--ink-2)">'
                            f'Kèm {len(h["log_evidence"])} dòng log gốc'
                            f'</div>'
                        )
                    items_html.append(
                        f'<div class="p035-reasoning-item {item_cls}">'
                        f'<div class="p035-r-label">Giả thuyết · {conf_pct}</div>'
                        f'<div class="p035-r-body"><strong>{html.escape(h["statement"])}</strong></div>'
                        + (f'<div class="p035-r-body">{html.escape(h.get("reasoning", ""))}</div>' if h.get("reasoning") else "")
                        + ev_tags
                        + deploy_html
                        + log_html
                        + '</div>'
                    )
                st.markdown(
                    f'<div class="p035-reasoning{done_cls}">{"".join(items_html)}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.caption("Chưa có giả thuyết — sự cố này tạo trước khi Agent biết chẩn đoán.")

            muc("03 · Đề xuất", "Agent <em>muốn làm gì</em>")
            proposal = incident.get("proposal")
            if proposal:
                the_de_xuat(incident, proposal)
            else:
                st.caption("Chưa có đề xuất khắc phục.")

            muc("04 · Diễn biến", "Timeline")
            timeline = incident.get("timeline") or []
            if timeline:
                st.caption("Đọc từ changelog Jira — Jira tự ghi khi có thao tác.")
                acts: list[str] = []
                for t in sorted(timeline, key=lambda t: t["at"]):
                    actor = (t.get("actor") or "System").lower()
                    if actor == "agent":
                        act_cls = "agent"
                    elif actor in ("system", "jira"):
                        act_cls = "system"
                    else:
                        act_cls = "human"
                    moc = _unix(t["at"])
                    hien_ts = _gio_vn(moc).strftime("%H:%M:%S") if moc else ""
                    who_cls = "agent" if actor == "agent" else ""
                    acts.append(
                        f'<div class="p035-act {act_cls}">'
                        f'<div class="time">{html.escape(hien_ts)}</div>'
                        f'<div class="text"><span class="who {who_cls}">[{html.escape(t.get("actor", "System"))}]</span> '
                        f'{html.escape(t["action"])}'
                        + (f' — {html.escape(t.get("detail", ""))}' if t.get("detail") else "")
                        + '</div></div>'
                    )
                st.markdown(
                    '<div class="p035-activity">' + ''.join(acts) + '</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.caption("Chưa có diễn biến nào.")

            postmortem = incident.get("postmortem")
            if postmortem:
                muc("05 · Báo cáo", "Postmortem")
                with st.container():
                    dau_the()
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
                muc("06 · Ngữ cảnh", "Sự cố <em>liên quan</em>")
                st.caption("Cùng một nguyên nhân lan sang dịch vụ khác.")
                for col, key in zip(st.columns(len(related)), related):
                    with col:
                        if st.button(key, key=f"related-{key}", use_container_width=True):
                            st.session_state["selected_key"] = key
                            st.rerun()
