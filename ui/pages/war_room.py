"""War-room view — trang theo dõi và xử lý sự cố.

CHỦ SỞ HỮU: Long · Đức sửa phần diễn đạt ngày 06/08 (xem WORKLOG cùng ngày)
· Dựng lại toàn bộ giao diện theo `scratch_warroom_ref.html` ngày 17/08.

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

## Vì sao cả trang là MỘT khối HTML trong `components.html`

Bản trước dựng bằng widget Streamlit rồi ép CSS. Không ra được khung của thiết
kế: header cố định 52px, sidebar 340px cuộn riêng, và chuyển giữa các sự cố
không reload. Streamlit đặt mỗi widget trong một `stElementContainer` riêng, nên
không có cách nào cho hai vùng cuộn độc lập cạnh nhau.

Nên trang dựng **toàn bộ HTML/CSS/JS ở đây** rồi nhúng một lần. Hệ quả phải
biết trước khi sửa:

- Mọi sự cố đều được render sẵn thành một `.view`, JS chỉ bật/tắt. Đổi sự cố
  **không** gọi lại API. Đổi lại: mỗi lần tải trang phải lấy chi tiết của tất cả
  sự cố (`tai_tat_ca()` gọi song song, xem ghi chú ở đó).
- Không dùng `st.button`/`st.selectbox` nữa. Thao tác nào cần dữ liệu mới thì
  phải tải lại cả trang — nút "Làm mới" trên header làm đúng việc đó, và mang
  theo `?key=&theme=` để giữ nguyên chỗ đang đứng.
- Trạng thái giao diện (theme, sự cố đang chọn, tab, ô tìm kiếm) nằm trong JS
  của iframe, **không** trong `st.session_state`.

## Số liệu: cái gì đo được, cái gì không

Trang chỉ hiện con số **đo được**. Ô nào không có nguồn thì hiện `—` kèm câu nói
rõ vì sao, tuyệt đối không điền số cho đẹp:

| Ô | Nguồn |
|---|---|
| Số P1/P2/P3 đang mở, MTTR hôm nay | tính từ `/api/incidents` |
| Trạng thái Agent trên header | `/api/v1/agent/health` — boolean, **không** có % uptime |
| Biểu đồ diễn biến | `GET {PROM_URL}/api/v1/query_range` với **đúng** câu PromQL trong `MetricEvidence.promql` của chính sự cố đang xem |
| "Ảnh hưởng" ở meta strip | tỷ lệ request bị ảnh hưởng, xem `ty_le_anh_huong()` |

⚠️ Không lấy được dữ liệu thì **không vẽ gì**, kèm câu nói rõ vì sao. Tuyệt đối
không nội suy, không sinh số, không hardcode một mảng cho biểu đồ đỡ trống. Cả
trang này dựng trên luận điểm "chẩn đoán CÓ BẰNG CHỨNG" — một đường bịa phá đúng
thứ nó đang cố chứng minh. Cùng lý do với đoạn cảnh báo dài trong
`link_prometheus()` bên dưới, và với sparkline phẳng trong `sparkline()`.

⚠️ Cũng đừng gọi `src/services/prometheus.py::query_range()` cho tiện: hàm đó
bọc `avg_over_time(...)` rồi gọi endpoint **instant**, trả về MỘT con số trung
bình mỗi service chứ không phải chuỗi thời gian — vẽ ra đường thẳng. Đằng nào
`ui/` cũng không được import `src/`.
"""

from __future__ import annotations

import html
import os
import pathlib
import re
import socket
import sys
import urllib.parse
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import requests
import streamlit as st
import streamlit.components.v1 as components

# File này nằm ở `ui/pages/war_room.py` — Streamlit multi-page tự phát hiện và
# phục vụ nó tại URL `/war_room`. `streamlit run ui/status_page.py` đặt thư mục
# `ui/` vào sys.path, nhưng từ `pages/` cần lên 3 cấp mới tới gốc repo.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from ui import labels, theme  # noqa: E402

API = os.getenv("API_URL", "https://p-035-incident-agent.onrender.com")
# Prometheus chỉ chạy local trong buổi demo; không có bản deploy công khai. Nên
# đường bình thường của trang này là "Prometheus không với tới được" — mọi ô lấy
# số từ đó phải có đường lùi tử tế, không được vỡ.
PROM_URL = os.getenv("PROM_URL", "http://localhost:9090")

#: Địa chỉ Prometheus dành cho TRÌNH DUYỆT người xem, khác `PROM_URL` ở trên.
#:
#: `PROM_URL` là địa chỉ tiến trình Streamlit tự gọi — luôn `localhost:9090`, và
#: nên giữ nguyên như vậy: hỏi số đo qua localhost là đi thẳng, không vòng ra
#: internet rồi quay lại.
#:
#: Nhưng nút "Mở trên Prometheus" thì do **trình duyệt** mở. Dùng chung
#: `PROM_URL` thì link trỏ `localhost:9090` — đúng với người ngồi tại máy chạy
#: Streamlit, và **chết với mọi người xem từ xa**, tức gần như toàn bộ người
#: dùng khi trang đã lên tên miền công khai. Mời người ta kiểm chứng bằng một
#: link không mở được còn tệ hơn không mời.
#:
#: Trống thì lùi về `PROM_URL`, giữ nguyên hành vi cũ cho máy chạy local.
PROM_PUBLIC_URL = os.getenv("PROM_PUBLIC_URL", "") or PROM_URL
# Chỉ để dựng link "mở phiếu Jira". Không bắt buộc — thiếu thì nút duyệt nói rõ
# phải thao tác ở đâu, chứ KHÔNG giả vờ đã thi hành.
JIRA_URL = os.getenv("JIRA_BASE_URL", "").rstrip("/")

VN_TZ = timezone(timedelta(hours=7))  # Việt Nam không có DST, luôn UTC+7

#: Trạng thái nghĩa là sự cố còn đang diễn ra.
DANG_XAY_RA = ("Open", "Investigating", "Awaiting Approval", "Remediating")

#: TTL cache của cả cụm dữ liệu (API + Prometheus). Prometheus trong demo scrape
#: 5s/lần (demo/prometheus.yml) nên 15s là đủ mới mà không hỏi lại quá dày.
LAM_MOI_GIAY = 15

#: Trần số điểm mỗi đường — dùng để tính `step`. Nhiều hơn thì Prometheus trả
#: chậm mà mắt cũng không phân biệt được.
SO_DIEM_TOI_DA = 360

#: Cửa sổ tối thiểu của biểu đồ. Sự cố mới mở 40 giây mà vẽ đúng 40 giây thì
#: không nhìn ra "trước đó vẫn bình thường".
CUA_SO_TOI_THIEU_GIAY = 15 * 60

#: Bucket latency mà `docs/contracts/01-metrics.md` bắt buộc Trung khai. Dùng để
#: dựng câu "bao nhiêu phần trăm request chậm hơn ngưỡng" — xem
#: `ty_le_anh_huong()`. Sai bộ này thì query trả rỗng chứ không trả số sai.
BUCKET_LATENCY = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)

#: Số giây tối đa chờ Prometheus. Ngắn hơn API vì Prometheus hoặc ở localhost
#: (vài ms) hoặc không tồn tại (nên biết ngay, đừng treo trang 10 giây).
PROM_TIMEOUT = 4


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
#
# Phần dưới đây chép nguyên từ `scratch_warroom_ref.html` — cùng token, cùng số
# đo, cùng tên class. Giữ nguyên tên class của file mẫu là cố ý: đối chiếu hai
# file khi thiết kế đổi thì chỉ cần so tên, không phải dịch qua lại.
#
# Chỉ có phần "BỔ SUNG" ở cuối là của riêng trang này — những khối mà file mẫu
# không có vì nó là mockup: dòng `↳`, khối log, ghi chú thiếu dữ liệu.

_CSS = (
    theme.TOKENS_CSS
    + theme.RESET_CSS
    + theme.CHUNG_CSS
    + """
/* Trang này cuộn bằng hai vùng riêng nên body KHÔNG được cuộn. */
body { overflow: hidden; }

.app { display: grid; grid-template-rows: 52px 1fr; height: 100vh; }

/* ═══════════════ HEADER ═══════════════ */
.header {
  display: grid;
  grid-template-columns: 340px 1fr auto;
  align-items: center;
  background: var(--bg-1);
  border-bottom: 1px solid var(--border);
  padding: 0 16px 0 20px;
  transition: background 0.25s ease, border-color 0.25s ease;
}

.header-center {
  display: flex; align-items: center; gap: 20px;
  padding: 0 20px;
  overflow: hidden;
}
.status-strip { display: flex; align-items: center; gap: 22px; }
.status-item { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--ink-1); white-space: nowrap; }
.status-item .num { color: var(--ink-0); font-weight: 500; font-variant-numeric: tabular-nums; }
.status-item .num.dim { color: var(--ink-2); font-weight: 400; }
.pulse-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--p1); position: relative;
}
.pulse-dot::after {
  content: ''; position: absolute; inset: -3px; border-radius: 50%;
  border: 1.5px solid var(--p1); opacity: 0;
  animation: pulse 2s ease-out infinite;
}
@keyframes pulse {
  0% { transform: scale(0.8); opacity: 0.8; }
  100% { transform: scale(2); opacity: 0; }
}
.calm-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--ok); }


.avatar {
  width: 28px; height: 28px; border-radius: 50%;
  background: linear-gradient(135deg, #4A5F7A 0%, #2C3E52 100%);
  display: grid; place-items: center;
  font-size: 11px; font-weight: 600;
  color: #fff;
  border: 1px solid var(--border-strong);
  margin-left: 4px;
}

/* ═══════════════ MAIN GRID ═══════════════ */
.main-grid {
  display: grid;
  grid-template-columns: 340px 1fr;
  overflow: hidden;
}

/* ═══════════════ SIDEBAR ═══════════════ */
.sidebar {
  background: var(--bg-1);
  border-right: 1px solid var(--border);
  display: grid;
  grid-template-rows: auto auto auto 1fr;
  overflow: hidden;
  transition: background 0.25s ease, border-color 0.25s ease;
}
.sb-header { padding: 18px 20px 12px; }
.sb-eyebrow {
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--ink-2);
  margin-bottom: 8px;
}
.sb-title {
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.015em;
  line-height: 1.15;
}
.sb-title em { font-style: italic; font-weight: 300; color: var(--ink-1); }

.sb-tabs {
  display: flex; gap: 4px;
  padding: 0 16px;
  border-bottom: 1px solid var(--border);
}
.sb-tab {
  padding: 8px 12px 10px;
  font-size: 12.5px;
  color: var(--ink-1);
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  display: flex; align-items: center; gap: 6px;
  transition: color 0.15s;
}
.sb-tab:hover { color: var(--ink-0); }
.sb-tab.active { color: var(--ink-0); border-bottom-color: var(--accent); }
.sb-tab .count {
  font-family: var(--font-mono);
  font-size: 10.5px;
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--bg-3);
  color: var(--ink-1);
}
.sb-tab.active .count { background: var(--accent-soft); color: var(--accent); }

.sb-search { padding: 12px 16px; position: relative; }
.sb-search input {
  width: 100%;
  height: 32px;
  padding: 0 12px 0 32px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--ink-0);
  font-size: 12.5px;
  outline: none;
  transition: border 0.15s;
}
.sb-search input::placeholder { color: var(--ink-2); }
.sb-search input:focus { border-color: var(--border-strong); }
.sb-search svg {
  position: absolute; left: 26px; top: 50%; transform: translateY(-50%);
  color: var(--ink-2);
}
.sb-search .kbd {
  position: absolute; right: 26px; top: 50%; transform: translateY(-50%);
  padding: 3px 6px; border-radius: 4px;
  background: var(--bg-3); color: var(--ink-1);
  font-family: var(--font-mono); font-size: 11px;
  border: 1px solid var(--border);
}

.sb-list { overflow-y: auto; padding: 0 8px 16px; }
.sb-panel { display: none; }
.sb-panel.active { display: block; }
.sb-empty {
  padding: 22px 14px;
  font-size: 12.5px;
  color: var(--ink-2);
  text-align: center;
}

.incident {
  display: block;
  padding: 12px 12px 12px 14px;
  border-radius: 7px;
  margin-bottom: 2px;
  position: relative;
  cursor: pointer;
  transition: background 0.12s;
  border: 1px solid transparent;
}
.incident:hover { background: var(--bg-hover); }
.incident.active { background: var(--bg-2); border-color: var(--border-strong); }
.incident.active::before {
  content: '';
  position: absolute;
  left: -8px; top: 8px; bottom: 8px; width: 2px;
  background: var(--accent);
  border-radius: 2px;
}

.inc-row1 { display: flex; align-items: baseline; gap: 8px; margin-bottom: 5px; }
.inc-sev {
  font-family: var(--font-display);
  font-style: italic;
  font-weight: 400;
  font-size: 15px;
  line-height: 1;
  min-width: 22px;
}
.inc-sev.p1 { color: var(--p1); }
.inc-sev.p2 { color: var(--p2); }
.inc-sev.p3 { color: var(--p3); }
.inc-sev.p4 { color: var(--ink-1); }
.inc-sev.done { color: var(--ok); }
.inc-id {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--ink-2);
  letter-spacing: 0.02em;
}
.inc-status-dot {
  margin-left: auto;
  width: 6px; height: 6px; border-radius: 50%;
}
.inc-status-dot.active { background: var(--p1); box-shadow: 0 0 0 3px var(--p1-soft); }
.inc-status-dot.pending { background: var(--pending); }
.inc-status-dot.resolving { background: var(--p2); }
.inc-status-dot.resolved { background: var(--ok); }

.inc-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--ink-0);
  margin-bottom: 6px;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.inc-meta {
  display: flex; align-items: center; gap: 10px;
  font-size: 11.5px;
  color: var(--ink-2);
}
.inc-spark { margin-left: auto; opacity: 0.85; }

/* ═══════════════ MAIN CONTENT ═══════════════ */
.content { overflow-y: auto; background: var(--bg-0); scroll-behavior: smooth; }
.content-inner { max-width: 100%; padding: 32px 44px 80px; }
.view { display: none; }
.view.active { display: block; }

/* Case header */
.case-crumb {
  display: flex; align-items: center; gap: 8px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-2);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.case-crumb .sep { opacity: 0.5; }
.case-crumb .status-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 2px 8px;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  font-weight: 500;
  font-size: 10px;
}
.case-crumb .status-pill.live { color: var(--p1); background: var(--p1-soft); }
.case-crumb .status-pill.live::before {
  content: ''; width: 5px; height: 5px; border-radius: 50%;
  background: var(--p1);
  animation: blink 1.5s ease-in-out infinite;
}
.case-crumb .status-pill.wait { color: var(--pending); background: rgba(156, 106, 222, 0.14); }
.case-crumb .status-pill.wait::before {
  content: ''; width: 5px; height: 5px; border-radius: 50%;
  background: var(--pending);
  animation: blink 1.5s ease-in-out infinite;
}
.case-crumb .status-pill.done { color: var(--ok); background: var(--ok-soft); }
.case-crumb .status-pill.done::before {
  content: '✓'; font-size: 10px; line-height: 1;
}
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

.case-title {
  font-family: var(--font-display);
  font-weight: 400;
  font-size: 34px;
  line-height: 1.15;
  letter-spacing: -0.02em;
  margin-bottom: 14px;
  color: var(--ink-0);
}
.case-title .sev {
  font-style: italic;
  font-weight: 300;
  margin-right: 6px;
}
.case-title .sev.p1 { color: var(--p1); }
.case-title .sev.p2 { color: var(--p2); }
.case-title .sev.p3 { color: var(--p3); }
.case-title .sev.p4 { color: var(--ink-1); }
.case-title .sev.done { color: var(--ok); }
.case-title .service {
  color: var(--ink-1);
  font-style: italic;
  font-weight: 300;
}
.case-title code {
  font-family: var(--font-mono);
  font-size: 21px;
  font-weight: 400;
  color: var(--ink-0);
  background: var(--bg-2);
  padding: 2px 8px;
  border-radius: 4px;
  vertical-align: 2px;
  border: 1px solid var(--border);
}

.case-meta {
  display: flex; flex-wrap: wrap; align-items: center; gap: 22px;
  padding: 14px 0;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  margin-bottom: 32px;
  font-size: 12.5px;
}
.meta-item { display: flex; align-items: center; gap: 8px; color: var(--ink-1); }
.meta-item svg { color: var(--ink-2); flex-shrink: 0; }
.meta-item .val { color: var(--ink-0); font-weight: 500; }
.meta-item .val.dim { color: var(--ink-2); font-weight: 400; }
.meta-actions { margin-left: auto; display: flex; gap: 6px; }

/* ═══════════════ SECTION HEADER ═══════════════ */
.section { margin-bottom: 40px; }
.sec-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 18px; }
.sec-eyebrow {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-weight: 500;
  white-space: nowrap;
}
.sec-title {
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.015em;
  color: var(--ink-0);
}
.sec-title em { font-style: italic; font-weight: 300; color: var(--ink-1); }
.sec-aside { margin-left: auto; font-size: 12px; color: var(--ink-2); text-align: right; }

/* ═══════════════ VITALS STRIP ═══════════════ */
.vitals {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 22px;
}
.vital { background: var(--bg-1); padding: 16px 18px; position: relative; }
.vital-label {
  font-family: var(--font-mono);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--ink-2);
  margin-bottom: 10px;
  display: flex; align-items: center; gap: 6px;
}
.vital-value {
  font-family: var(--font-display);
  font-size: 30px;
  line-height: 1;
  font-weight: 400;
  letter-spacing: -0.02em;
  color: var(--ink-0);
  display: flex; align-items: baseline; gap: 6px;
  margin-bottom: 4px;
}
.vital-value .unit {
  font-family: var(--font-body);
  font-size: 13px;
  color: var(--ink-1);
  font-weight: 400;
}
.vital-value .delta {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 4px;
  margin-left: 4px;
}
.vital-value .delta.bad { color: var(--p1); background: var(--p1-soft); }
.vital-value .delta.good { color: var(--ok); background: var(--ok-soft); }
.vital-sub { font-size: 11.5px; color: var(--ink-2); font-family: var(--font-mono); }
.vital.alert { background: linear-gradient(180deg, var(--p1-soft) 0%, var(--bg-1) 60%); }
.vital.alert .vital-value { color: var(--p1); }
.vital.ok { background: linear-gradient(180deg, var(--ok-soft) 0%, var(--bg-1) 60%); }
.vital.ok .vital-value { color: var(--ok); }
.vital.empty .vital-value { color: var(--ink-3); }

/* ═══════════════ CHART ═══════════════ */
.chart-panel {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 20px 12px;
}
.chart-head { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.chart-title { font-size: 13px; font-weight: 500; color: var(--ink-0); }
.chart-title .code { font-family: var(--font-mono); color: var(--accent); font-weight: 400; }
.chart-legend {
  margin-left: auto;
  display: flex; gap: 14px;
  font-size: 11.5px;
  color: var(--ink-1);
}
.chart-legend .item { display: flex; align-items: center; gap: 6px; }
.chart-legend .swatch { width: 10px; height: 2px; border-radius: 1px; }
.chart-svg { width: 100%; height: auto; display: block; font-family: var(--font-body); }
.chart-foot {
  display: flex; justify-content: space-between;
  padding-top: 8px;
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--ink-2);
}

/* ═══════════════ EVIDENCE / CODE ═══════════════ */
.evidence {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 20px;
  margin-bottom: 14px;
}
.evidence:last-child { margin-bottom: 0; }
.evidence p { color: var(--ink-0); margin-bottom: 12px; }
.evidence p:last-child { margin-bottom: 0; }

/* Toggle collapsible sections */
.toggle-section { margin-top: 8px; }
.toggle-btn {
  display: flex; align-items: center; gap: 10px;
  background: var(--bg-0); border: 1px solid var(--border);
  border-radius: 8px; cursor: pointer;
  color: var(--ink-0); font-size: 13px; font-weight: 600;
  font-family: var(--font-body);
  padding: 10px 16px; width: 100%; text-align: left;
  transition: all 0.15s ease;
}
.toggle-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--bg-1);
}
.toggle-icon {
  font-size: 10px; transition: transform 0.2s ease;
  display: inline-block;
}
.toggle-section.open .toggle-icon { transform: rotate(90deg); }
.toggle-section.open .toggle-btn {
  border-color: var(--accent);
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
}
.toggle-content {
  display: none;
  border: 1px solid var(--border); border-top: none;
  border-radius: 0 0 8px 8px;
  padding: 14px 16px;
  background: var(--bg-1);
}
.toggle-section.open .toggle-content { display: block; }

.code-block {
  background: var(--code-bg);
  border: 1px solid var(--code-border);
  border-radius: 8px;
  overflow: hidden;
  margin: 14px 0 4px;
}
.code-head {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--code-border);
  background: var(--code-head-bg);
}
.code-lang {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--code-p);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
.code-copy {
  margin-left: auto;
  font-size: 11px;
  color: var(--code-p);
  padding: 3px 8px;
  border-radius: 4px;
  transition: all 0.15s;
  display: inline-flex; align-items: center; gap: 6px;
}
.code-copy:hover { color: var(--ink-0); background: var(--bg-3); }
.code-body {
  padding: 14px 16px;
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.65;
  color: var(--ink-0);
  white-space: pre;
}
.code-body .k { color: var(--code-k); }
.code-body .fn { color: var(--code-fn); }
.code-body .s { color: var(--code-s); }
.code-body .n { color: var(--code-n); }
.code-body .cm { color: var(--code-cm); font-style: italic; }
.code-body .p { color: var(--code-p); }

.link-row {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 12px;
  color: var(--ink-1);
  text-decoration: none;
  margin-top: 12px;
  transition: border 0.15s;
}
.link-row:hover { border-color: var(--border-strong); }
.link-row .url {
  color: var(--accent);
  font-family: var(--font-mono); font-size: 11.5px;
  flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* ═══════════════ REASONING ═══════════════ */
.reasoning {
  padding-left: 24px;
  border-left: 1px solid var(--accent-line);
  margin-left: 4px;
  position: relative;
}
.reasoning.done { border-left-color: var(--ok-line); }
.reasoning-item { position: relative; padding-bottom: 20px; }
.reasoning-item:last-child { padding-bottom: 0; }
.reasoning-item::before {
  content: '';
  position: absolute;
  left: -29px; top: 5px;
  width: 9px; height: 9px;
  border-radius: 50%;
  background: var(--bg-0);
  border: 1.5px solid var(--accent);
}
.reasoning.done .reasoning-item::before { border-color: var(--ok); }
.reasoning-item.conclusion::before {
  background: var(--accent);
  box-shadow: 0 0 0 4px var(--accent-soft);
}
.reasoning.done .reasoning-item.conclusion::before {
  background: var(--ok);
  box-shadow: 0 0 0 4px var(--ok-soft);
}
.r-label {
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--accent);
  margin-bottom: 6px;
  font-weight: 500;
}
.reasoning.done .r-label { color: var(--ok); }
.r-body { color: var(--ink-0); font-size: 13.5px; margin-bottom: 8px; }
.r-body strong { font-weight: 600; color: var(--ink-0); }
.r-body.quiet { color: var(--ink-1); font-size: 13px; }
.r-evidence {
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
.r-evidence .val { color: var(--ink-0); font-weight: 500; }
.r-evidence.warn .val { color: var(--p1); }
.r-evidence.ok .val { color: var(--ok); }

/* ═══════════════ PROPOSAL ═══════════════ */
.proposal {
  background: linear-gradient(180deg, var(--accent-soft) 0%, transparent 40%), var(--bg-1);
  border: 1px solid var(--accent-line);
  border-radius: 12px;
  overflow: hidden;
}
.proposal.executed {
  background: linear-gradient(180deg, var(--ok-soft) 0%, transparent 40%), var(--bg-1);
  border-color: var(--ok-line);
}
.proposal-head { padding: 18px 22px 14px; border-bottom: 1px solid var(--border); }
.proposal-tag {
  display: inline-flex; align-items: center; gap: 6px;
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--accent);
  font-weight: 500;
  margin-bottom: 10px;
}
.proposal.executed .proposal-tag { color: var(--ok); }
.proposal-title {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 400;
  letter-spacing: -0.01em;
  color: var(--ink-0);
  margin-bottom: 6px;
}
.proposal-title code {
  font-family: var(--font-mono);
  font-size: 15px;
  padding: 2px 8px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 5px;
  color: var(--accent);
  vertical-align: 2px;
}
.proposal.executed .proposal-title code { color: var(--ok); }
.proposal-target { font-size: 12.5px; color: var(--ink-1); font-family: var(--font-mono); }

.proposal-body { padding: 18px 22px; }
.proposal-body p { color: var(--ink-0); margin-bottom: 12px; }
.proposal-body p:last-child { margin-bottom: 0; }
.impact-grid {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 12px; margin: 14px 0;
}
.impact {
  padding: 12px 14px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.impact .lb {
  font-family: var(--font-mono);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-2);
  margin-bottom: 5px;
}
.impact .vl {
  font-size: 15px; font-weight: 500;
  color: var(--ink-0);
  display: flex; align-items: baseline; gap: 4px;
}
.impact .vl small { font-size: 11px; color: var(--ink-1); font-weight: 400; }

.confirm-strip {
  display: flex; align-items: center;
  padding: 14px 22px;
  background: var(--bg-2);
  border-top: 1px solid var(--border);
  gap: 12px;
  flex-wrap: wrap;
}
.confirm-strip .who {
  font-size: 12px; color: var(--ink-1);
  display: flex; align-items: center; gap: 8px;
  flex: 1; min-width: 240px;
}
.confirm-strip .who strong { color: var(--ink-0); font-weight: 500; }
.confirm-strip .who .a {
  display: inline-grid; place-items: center;
  width: 20px; height: 20px; border-radius: 50%;
  background: linear-gradient(135deg, #4A5F7A 0%, #2C3E52 100%);
  font-size: 9px; font-weight: 600;
  color: #fff;
  flex-shrink: 0;
}
.confirm-strip .check-icon {
  width: 20px; height: 20px; border-radius: 50%;
  background: var(--ok);
  color: #fff;
  display: inline-grid; place-items: center;
  font-size: 11px;
  flex-shrink: 0;
}


/* ═══════════════ ACTIVITY TIMELINE ═══════════════ */
.activity { padding-left: 24px; border-left: 1px solid var(--border); margin-left: 4px; }
.act {
  position: relative;
  padding-bottom: 18px;
  display: grid;
  grid-template-columns: 60px 1fr;
  gap: 14px;
  align-items: baseline;
}
.act:last-child { padding-bottom: 0; }
.act::before {
  content: '';
  position: absolute;
  left: -28px; top: 6px;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--ink-3);
}
.act.agent::before { background: var(--accent); }
.act.human::before { background: var(--signal); }
.act.system::before { background: var(--ink-3); }
.act.ok::before { background: var(--ok); box-shadow: 0 0 0 3px var(--ok-soft); }
.act .time { font-family: var(--font-mono); font-size: 11px; color: var(--ink-2); }
.act .text { font-size: 13px; color: var(--ink-0); }
.act .text .who { color: var(--ink-1); font-weight: 500; }
.act .text .who.agent { color: var(--accent); }
.act .text .who.ok { color: var(--ok); font-weight: 600; }
.act .text .detail { color: var(--ink-1); }

/* ═══════════════ RELATED ═══════════════ */
.related-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.rel-card {
  padding: 14px 16px;
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}
.rel-card:hover { border-color: var(--border-strong); background: var(--bg-2); }
.rel-head {
  display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
  font-family: var(--font-mono); font-size: 10.5px; color: var(--ink-2);
  text-transform: uppercase; letter-spacing: 0.08em;
}
.rel-sev { font-family: var(--font-display); font-style: italic; }
.rel-title { font-size: 13px; color: var(--ink-0); font-weight: 500; margin-bottom: 4px; }
.rel-meta { font-size: 11.5px; color: var(--ink-2); }

/* ═══════════════ POSTMORTEM CHECKLIST ═══════════════ */
.checklist { display: flex; flex-direction: column; gap: 8px; }
.check-item {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 14px;
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 8px;
  transition: border 0.15s;
  text-decoration: none;
}
a.check-item { cursor: pointer; }
.check-item:hover { border-color: var(--border-strong); }
.check-box {
  width: 18px; height: 18px; border-radius: 5px;
  border: 1.5px solid var(--border-strong);
  display: grid; place-items: center;
  flex-shrink: 0;
  transition: all 0.15s;
}
.check-item.done .check-box {
  background: var(--ok);
  border-color: var(--ok);
  color: #fff;
}
.check-item.done .check-box::after {
  content: '✓'; font-size: 11px; font-weight: 700;
}
.check-item .text { flex: 1; font-size: 13px; color: var(--ink-0); }
.check-item.done .text { color: var(--ink-1); text-decoration: line-through; text-decoration-color: var(--ink-3); }
.check-item .tag {
  font-family: var(--font-mono);
  font-size: 10.5px;
  padding: 2px 8px;
  border-radius: 4px;
  color: var(--ink-1);
  background: var(--bg-3);
  white-space: nowrap;
}
.check-item .assignee {
  font-size: 11.5px; color: var(--ink-2); white-space: nowrap;
}

/* ═══════════════ BỔ SUNG — khối file mẫu không có ═══════════════ */
/*
 * File mẫu là mockup nên nó không có: dòng kỹ thuật `↳`, khối log gốc, và câu
 * giải thích khi thiếu dữ liệu. Ba thứ đó là ràng buộc của trang thật (xem
 * docstring đầu file), nên thêm ở đây — vẫn dùng đúng token và nhịp của mẫu.
 */

/* Dòng kỹ thuật đi kèm mỗi câu dịch — người trực grep chữ trong này */

/* Danh sách bằng chứng số phụ trong một thẻ */
.ev-row { padding: 14px 0; border-top: 1px solid var(--border); }
.ev-row:first-child { padding-top: 0; border-top: none; }
.ev-row:last-child { padding-bottom: 0; }
.ev-line { display: flex; align-items: baseline; gap: 12px; }
.ev-line .name { font-size: 13px; color: var(--ink-0); }
.ev-line .num {
  margin-left: auto; flex-shrink: 0;
  font-family: var(--font-mono); font-size: 12.5px; color: var(--ink-0);
}
.ev-line .num.bad { color: var(--p1); }


/* Ghi chú — thay cho st.caption/st.warning cũ */
.note {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 18px;
  font-size: 12.5px;
  color: var(--ink-1);
}
.note strong { color: var(--ink-0); font-weight: 600; }
.note.warn {
  background: linear-gradient(180deg, var(--accent-soft) 0%, transparent 60%), var(--bg-1);
  border-color: var(--accent-line);
  color: var(--ink-0);
}
.note.err {
  background: linear-gradient(180deg, var(--p1-soft) 0%, transparent 60%), var(--bg-1);
  border-color: var(--p1);
  color: var(--ink-0);
}
.note + .note { margin-top: 10px; }
.hint { font-size: 11.5px; color: var(--ink-2); margin-top: 10px; }

/* Khối log gốc — giữ nguyên văn ERROR/WARNING vì đó là chữ người trực grep */
.log-line { display: block; }
.log-line .lv-error { color: var(--p1); }
.log-line .lv-warn { color: var(--p2); }
.log-line .lv-info { color: var(--ok); }
/* Huy hiệu "×37" cho các dòng lặp lại liên tiếp — xem `_gop_dong_lap()` */
.log-line .lap {
  display: inline-block;
  padding: 0 6px; margin-right: 6px;
  border: 1px solid var(--border); border-radius: 4px;
  color: var(--ink-2); font-size: 11px;
}

/* Màn chờ khi đổi phiếu — đổi phiếu là tải lại trang, không có nó thì cái bấm
   trông như không ăn cho tới lúc trang mới về. */
.dang-tai {
  position: fixed; inset: 52px 0 0 340px;
  background: var(--bg-0);
  opacity: 0.92;
  display: grid; place-items: center;
  z-index: 20;
}
.dang-tai .hop {
  font-family: var(--font-mono);
  font-size: 11.5px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--ink-2);
  display: flex; align-items: center; gap: 10px;
}
.dang-tai .cham {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--accent);
  animation: blink 1.2s ease-in-out infinite;
}

/* Trang trống / trang lỗi */
.blank {
  max-width: 620px;
  padding: 64px 44px;
}
.blank h2 {
  font-family: var(--font-display);
  font-size: 30px; font-weight: 400; letter-spacing: -0.02em;
  margin-bottom: 12px;
}
.blank h2 em { font-style: italic; font-weight: 300; color: var(--ink-1); }
.blank p { color: var(--ink-1); margin-bottom: 12px; font-size: 13.5px; }
.blank ul { color: var(--ink-1); margin: 0 0 12px 18px; font-size: 13.5px; }
.blank li { margin-bottom: 4px; }
.blank strong { color: var(--ink-0); }
"""
)

# CSS cho phần vỏ Streamlit bên ngoài iframe. Mục tiêu duy nhất: biến mất, để
# iframe chiếm trọn cửa sổ. Bám `data-testid`, KHÔNG bám class emotion hash.
_CSS_KHUNG = theme.CSS_KHUNG


# ---------------------------------------------------------------------------
# Icon — SVG nội tuyến, không dùng thư viện icon
# ---------------------------------------------------------------------------

ICON = theme.ICON


# ---------------------------------------------------------------------------
# Định dạng
# ---------------------------------------------------------------------------


def e(gia_tri: Any) -> str:
    """Thoát HTML. Mọi chuỗi từ API đều phải đi qua đây trước khi vào trang."""
    return html.escape(str(gia_tri), quote=True)


def fmt_time_vn(iso: str) -> str:
    """Định dạng một chuỗi ISO 8601 (UTC) sang giờ Việt Nam, kiểu vi-VN."""
    dt = datetime.fromisoformat(iso).astimezone(VN_TZ)
    return dt.strftime("%H:%M:%S %d/%m/%Y")


def fmt_gio(iso: str) -> str:
    """Chỉ giờ:phút:giây — dùng trong timeline, nơi ngày đã rõ theo ngữ cảnh."""
    moc = _unix(iso)
    return _gio_vn(moc).strftime("%H:%M:%S") if moc else "—"


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


def fmt_duration_ngan(giay: float) -> tuple[str, str]:
    """`(số, đơn vị)` cho ô vital — tách ra để đơn vị hiện bằng font body."""
    giay = max(int(giay), 0)
    if giay < 60:
        return f"{giay}", "giây"
    if giay < 3600:
        return f"{giay / 60:.0f}", "phút"
    return f"{giay / 3600:.1f}", "giờ"


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
    # Link cho TRÌNH DUYỆT, không phải cho tiến trình này — xem `PROM_PUBLIC_URL`.
    return f"{PROM_PUBLIC_URL}/query?{tham_so}"


def _unix(iso: str | None) -> float | None:
    """Chuỗi ISO → unix timestamp. None nếu không đọc được, không ném lỗi."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def _gio_vn(moc: float) -> datetime:
    """Unix timestamp → giờ Việt Nam, **bỏ tzinfo**.

    Khác hẳn `link_prometheus()`: ở đó **bắt buộc** phải quy về UTC vì Prometheus
    hiểu tham số của nó theo UTC. Hai chỗ ngược nhau, đừng "thống nhất" lại.
    """
    return datetime.fromtimestamp(moc, VN_TZ).replace(tzinfo=None)


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


def _so_ngan(gia_tri: float, don_vi: str) -> tuple[str, str]:
    """`(số, đơn vị)` cho ô vital — chữ số dùng font serif, đơn vị dùng font body."""
    if don_vi == "%":
        return f"{gia_tri * 100:.0f}", "%"
    return f"{gia_tri:.3g}", don_vi.strip()


def _lech(gia_tri: float, moc: float | None) -> str | None:
    """`"4.6×"`. Trả None khi không tính được — để chỗ gọi bỏ hẳn ô, không in "None"."""
    if not moc:
        return None
    return f"{gia_tri / moc:.1f}×"


def _lop_severity(inc: dict) -> str:
    """Class màu cho mức độ — `done` (xanh) khi sự cố đã đóng."""
    if inc.get("state") not in DANG_XAY_RA:
        return "done"
    return str(inc.get("severity", "")).lower() or "p3"


#: Tiền tố "[P1] " mà `IncidentSignal.title` gắn vào tiêu đề Jira.
_TIEN_TO_SEV = re.compile(r"^\[(?:P[1-4])\]\s*")


def _tieu_de(inc: dict, signal: dict) -> tuple[str, str]:
    """`(câu cho người đọc, nguyên văn tiêu đề phiếu)`.

    Tiêu đề trên Jira do Agent sinh theo khuôn máy đọc — `"[P1] service-thanh-
    toan: http_request_duration_seconds p95 = 5.10 (ngưỡng 2.00)"`. Đặt nguyên
    nó vào H1 thì vừa lặp mức độ (đã có ô `P1` màu bên trái), vừa là câu không ai
    đọc được nếu không biết tên metric.

    Nên H1 dùng câu dịch, còn nguyên văn xuống dòng `↳` ngay dưới — vẫn đúng
    "dịch THÊM, không dịch THAY". Không nhận ra tên metric thì giữ nguyên văn
    chứ không bịa ra một câu khác.
    """
    tho = str(inc.get("title", ""))
    ten_metric = str(signal.get("metric_name") or "")
    if not ten_metric:
        con = _TIEN_TO_SEV.sub("", tho)
        phan = con.split(":", 1)
        ten_metric = (phan[1] if len(phan) > 1 else con).split("=")[0].strip()

    cau, _ = labels.metric(ten_metric)
    if not ten_metric or cau == ten_metric:
        return _TIEN_TO_SEV.sub("", tho), tho
    return f"{cau} vượt ngưỡng ở", tho


def _lop_cham(inc: dict) -> str:
    """Class cho chấm trạng thái trong danh sách bên trái."""
    trang_thai = inc.get("state")
    if trang_thai == "Awaiting Approval":
        return "pending"
    if trang_thai == "Remediating":
        return "resolving"
    if trang_thai not in DANG_XAY_RA:
        return "resolved"
    return "active"


# ---------------------------------------------------------------------------
# Tô màu cú pháp PromQL
# ---------------------------------------------------------------------------
#
# Tự tô thay vì kéo Prism/highlight.js: một thư viện 20KB cho đúng một ngôn ngữ
# mà chỉ cần sáu class màu là không đáng, và trang đang cố không gọi ra ngoài
# ngoài Google Fonts.

_TU_KHOA_PROMQL = frozenset(
    {
        "sum", "avg", "min", "max", "count", "count_values", "stddev", "stdvar",
        "topk", "bottomk", "quantile", "group",
        "by", "without", "on", "ignoring", "group_left", "group_right", "offset",
        "and", "or", "unless", "bool",
        "rate", "irate", "increase", "delta", "idelta", "deriv", "predict_linear",
        "histogram_quantile", "abs", "ceil", "floor", "round", "clamp_max",
        "clamp_min", "absent", "changes", "resets", "sort", "sort_desc",
        "avg_over_time", "min_over_time", "max_over_time", "sum_over_time",
        "count_over_time", "quantile_over_time", "stddev_over_time", "last_over_time",
    }
)

_TOKEN_PROMQL = re.compile(
    r"""
    (?P<cm>\#[^\n]*)                      # bình luận
  | (?P<s>"[^"\n]*"|'[^'\n]*')            # chuỗi
  | (?P<n>\d+(?:\.\d+)?(?:[smhdwy]|ms)?)  # số và khoảng thời gian: 0.95, 5m, 30s
  | (?P<id>[A-Za-z_:][A-Za-z0-9_:]*)      # định danh
  | (?P<p>[^\sA-Za-z0-9_:"'#]+)           # dấu câu
    """,
    re.VERBOSE,
)


def to_mau_promql(cau: str) -> str:
    """PromQL → HTML với các class `.k/.fn/.s/.n/.cm/.p` của khối code.

    Định danh nằm trong `_TU_KHOA_PROMQL` là `.k`, còn lại là tên metric → `.fn`
    (amber). Đúng quy ước của file mẫu: amber dành cho tên hàm/metric.
    """
    ra: list[str] = []
    vi_tri = 0
    for khop in _TOKEN_PROMQL.finditer(cau):
        if khop.start() > vi_tri:
            ra.append(e(cau[vi_tri : khop.start()]))
        vi_tri = khop.end()
        chu = khop.group()
        loai = khop.lastgroup
        if loai == "id":
            loai = "k" if chu in _TU_KHOA_PROMQL else "fn"
        ra.append(f'<span class="{loai}">{e(chu)}</span>')
    if vi_tri < len(cau):
        ra.append(e(cau[vi_tri:]))
    return "".join(ra)


def khoi_code(ngon_ngu: str, than_html: str, *, nguyen_van: str = "") -> str:
    """Khối code có đầu đề + nút sao chép. `nguyen_van` là chữ nút sẽ chép."""
    nut = ""
    if nguyen_van:
        # Nội dung chép đi qua thuộc tính data — encode URI để không phải lo
        # dấu nháy/xuống dòng phá vỡ HTML.
        ma = urllib.parse.quote(nguyen_van)
        nut = (
            f'<button class="code-copy" type="button" data-copy="{ma}">'
            f'{ICON["chep"]}<span>Sao chép</span></button>'
        )
    return (
        '<div class="code-block">'
        f'<div class="code-head"><span class="code-lang">{e(ngon_ngu)}</span>{nut}</div>'
        f'<pre class="code-body">{than_html}</pre>'
        "</div>"
    )


def hang_link(url: str, nhan: str) -> str:
    """Một dòng link mở tab mới, hiện CẢ nhãn lẫn URL đầy đủ.

    In nguyên URL ra chứ không giấu sau chữ: người xem war room cần biết mình
    sắp rời sang đâu — Jira thật, Prometheus của máy nào — trước khi bấm. Đây là
    trang mà một link trỏ sai chỗ sẽ làm hỏng cả buổi demo mà không ai kịp nhận
    ra vì sao.

    `rel="noopener"` là bắt buộc kèm `target="_blank"`: thiếu nó thì trang được
    mở giữ được tham chiếu `window.opener` tới war room.
    """
    return (
        f'<a class="link-row" href="{e(url)}" target="_blank" rel="noopener">'
        f'{ICON["ngoai"]}{e(nhan)}<span class="url">{e(url)}</span></a>'
    )


# ---------------------------------------------------------------------------
# Prometheus
# ---------------------------------------------------------------------------


def prom_song() -> bool:
    """Prometheus có với tới được không — hỏi MỘT lần, timeout ngắn.

    Không có bước này thì mỗi câu truy vấn phải chờ hết timeout của nó, và trang
    có bao nhiêu sự cố là nhân lên bấy nhiêu lần chờ. Đường bình thường của bản
    deploy là "không với tới được" (xem docstring đầu file), nên phải rẻ.

    Hai chặng, và cả hai con số đều **đo ra** chứ không chọn bừa (17/08):

    1. **Bắt tay TCP trước.** Câu hỏi thật ở đây chỉ là "có ai nghe ở cổng đó
       không", mà HTTP thì đắt hơn hẳn khi câu trả lời là không. Cổng có người
       nghe trả lời trong **0,001 giây**; cổng trống thì phải chờ hết timeout.
       Nên timeout để rất ngắn không hề rủi ro.
    2. Nối được rồi mới hỏi `/-/healthy` — để phân biệt Prometheus thật với một
       tiến trình lạ đang chiếm cổng.

    ⚠️ `localhost` phân giải thành **cả** `::1` lẫn `127.0.0.1`, và cả `requests`
    lẫn `socket` đều thử lần lượt từng địa chỉ với trọn timeout cho mỗi lần — nên
    mọi timeout ở đây thực tế **nhân đôi**. Đo được: `requests` timeout=2 mất
    4,02s; timeout=1 mất 2,01s; bắt tay TCP timeout=0,25 mất 0,5s. Đây là đường
    chạy thường xuyên nhất (bản deploy không có Prometheus theo đúng thiết kế),
    nên nửa giây đó nằm thẳng trong thời gian mở trang.
    """
    dia_chi = urllib.parse.urlparse(PROM_URL)
    may = dia_chi.hostname or "localhost"
    cong = dia_chi.port or (443 if dia_chi.scheme == "https" else 80)
    # Prometheus local trả lời tính bằng mili giây; Prometheus ở xa thì cho rộng
    # tay hơn vì còn độ trễ mạng.
    han = 0.25 if may in ("localhost", "127.0.0.1", "::1") else 1.0
    try:
        socket.create_connection((may, cong), timeout=han).close()
    except OSError:
        return False

    try:
        return requests.get(f"{PROM_URL}/-/healthy", timeout=2).status_code == 200
    except requests.RequestException:
        return False


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
            timeout=PROM_TIMEOUT,
        )
        phan_hoi.raise_for_status()
        goi = phan_hoi.json()
    except requests.RequestException as loi:
        return {"ok": False, "loi": str(loi), "chuoi": []}
    except ValueError as loi:  # trả về không phải JSON
        return {"ok": False, "loi": f"phản hồi không đọc được: {loi}", "chuoi": []}

    if not isinstance(goi, dict) or goi.get("status") != "success":
        loi = goi.get("error") if isinstance(goi, dict) else "phản hồi không đúng khuôn"
        return {"ok": False, "loi": str(loi or "Prometheus từ chối câu truy vấn"), "chuoi": []}

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


def truy_van_instant(promql: str, luc: float | None = None) -> float | None:
    """Một con số tại thời điểm `luc` (Unix giây). None khi không có dữ liệu.

    `luc = None` là hỏi "bây giờ". Nhưng với một sự cố đã qua thì **bây giờ không
    còn dữ liệu**: cửa sổ `[5m]` chỉ chứa khoảng thời gian sau khi tải đã tắt.

    Đo ngày 21/08: sự cố phát hiện 13:32, xem war room lúc 13:40 — ô "Ảnh hưởng"
    hiện "Prometheus không trả dữ liệu cho cửa sổ này". Thông báo đúng, nhưng nó
    đang hỏi sai thời điểm. Cùng loại lỗi với link kiểm chứng PromQL đã vá 12/08:
    truy vấn tức thời trả giá trị *lúc hỏi*, không phải lúc sự cố.

    Ô "Ảnh hưởng" là dòng quan trọng nhất với người không rành kỹ thuật — nó trả
    lời "bao nhiêu phần khách bị ảnh hưởng". Để nó trống là mất đúng dòng đó.
    """
    tham_so: dict[str, object] = {"query": promql}
    if luc is not None:
        tham_so["time"] = luc
    try:
        phan_hoi = requests.get(
            f"{PROM_URL}/api/v1/query", params=tham_so, timeout=PROM_TIMEOUT
        )
        phan_hoi.raise_for_status()
        goi = phan_hoi.json()
    except (requests.RequestException, ValueError):
        return None
    if not isinstance(goi, dict) or goi.get("status") != "success":
        return None
    ket_qua = (goi.get("data") or {}).get("result") or []
    if not ket_qua:
        return None
    try:
        gia_tri = float(ket_qua[0]["value"][1])
    except (TypeError, ValueError, KeyError, IndexError):
        return None
    return gia_tri if gia_tri == gia_tri else None  # loại NaN


def _ten_chuoi(nhan_metric: dict) -> str:
    """Tên một đường trong biểu đồ, lấy từ nhãn Prometheus trả về."""
    for khoa in ("service", "job", "instance", "__name__"):
        if nhan_metric.get(khoa):
            return str(nhan_metric[khoa])
    return "giá trị"


def _bang_chung_kich_hoat(signal: dict) -> dict | None:
    """Bằng chứng ứng với chính chỉ số đã kích hoạt sự cố.

    Vẽ chỉ số khác là minh hoạ cho một câu chuyện khác — xem docstring đầu file.
    """
    bang_chung = [ev for ev in (signal.get("evidence") or []) if ev.get("promql")]
    if not bang_chung:
        return None
    ten = signal.get("metric_name")
    return next((ev for ev in bang_chung if ev.get("name") == ten), bang_chung[0])


def _cua_so(inc: dict) -> tuple[int, int]:
    """Khoảng thời gian vẽ biểu đồ cho một sự cố.

    Sự cố đã đóng vẽ trọn vòng cung (trước khi vượt ngưỡng → đỉnh → về nền), sự
    cố đang mở vẽ tới hiện tại. Cả hai đệm thêm ở hai đầu để nhìn ra được mức
    "bình thường" — biểu đồ bắt đầu ngay tại lúc vượt ngưỡng thì không có gì để
    so sánh.
    """
    bat_dau = _unix(inc.get("detected_at"))
    bay_gio = datetime.now(UTC).timestamp()
    if bat_dau is None:
        bat_dau = bay_gio - CUA_SO_TOI_THIEU_GIAY
    ket_thuc = _unix(inc.get("resolved_at")) or bay_gio
    dem = max(180.0, (ket_thuc - bat_dau) * 0.25)
    bat_dau -= dem
    ket_thuc = min(ket_thuc + dem, bay_gio)
    if ket_thuc - bat_dau < CUA_SO_TOI_THIEU_GIAY:
        bat_dau = ket_thuc - CUA_SO_TOI_THIEU_GIAY
    return int(bat_dau), int(ket_thuc)


def _le_gan_nhat(nguong: float) -> str | None:
    """Nhãn `le` của bucket nhỏ nhất mà >= ngưỡng.

    `prometheus_client` ghi biên bucket bằng `floatToGoString`, tức `1.0` ra
    `"1.0"` chứ không phải `"1"`. Khớp nhãn sai thì query trả **rỗng** chứ không
    trả số sai — nên chỗ gọi chỉ cần coi rỗng là "không đo được".
    """
    for bien in BUCKET_LATENCY:
        if bien >= nguong:
            return f"{bien:g}.0" if float(bien).is_integer() else f"{bien:g}"
    return None


def ty_le_anh_huong(
    signal: dict, prom_ok: bool, luc: float | None = None
) -> tuple[str, str]:
    """Bao nhiêu phần request thực sự bị ảnh hưởng — `(giá trị, chú thích)`.

    Đây là ô "Ảnh hưởng" trên meta strip. File mẫu ghi sẵn "~12% traffic" như
    một con số trang trí; ở đây nó phải đo được, nếu không thì hiện `—`:

    - **Sự cố tỷ lệ lỗi** — chính giá trị của tín hiệu đã là tỷ lệ request lỗi,
      không cần hỏi thêm Prometheus.
    - **Sự cố latency** — tỷ lệ request chậm hơn ngưỡng, tính từ histogram:
      `1 − (bucket[le=ngưỡng] / bucket[le=+Inf])`. Dùng bucket gần nhất >= ngưỡng
      nên câu chú thích phải nói rõ mốc đó, đừng để người đọc tưởng là ngưỡng.
    - **Còn lại** (pool, bộ nhớ, số lần restart, up) — không phải đại lượng theo
      request. Nói thẳng là không đo được theo request, hơn là quy đổi bừa.
    """
    ten = str(signal.get("metric_name", ""))
    dich_vu = str(signal.get("affected_service", ""))

    if "tỷ lệ lỗi" in ten:
        try:
            ty_le = float(signal["metric_value"])
        except (KeyError, TypeError, ValueError):
            return "—", "không đọc được giá trị tín hiệu"
        return f"{ty_le * 100:.1f}%", "request trả lỗi 5xx, lúc phát hiện"

    if "http_request_duration_seconds" not in ten:
        return "—", "chỉ số này không đo theo từng request"

    if not prom_ok:
        return "—", "cần Prometheus để đo"

    try:
        nguong = float(signal["threshold"])
    except (KeyError, TypeError, ValueError):
        return "—", "tín hiệu không kèm ngưỡng"

    le = _le_gan_nhat(nguong)
    if le is None:
        return "—", "ngưỡng nằm ngoài dải bucket đang đo"

    loc = f'service="{dich_vu}",handler!="/metrics"'
    cau = (
        f'1 - (sum(rate(http_request_duration_seconds_bucket{{{loc},le="{le}"}}[5m]))'
        f' / sum(rate(http_request_duration_seconds_bucket{{{loc},le="+Inf"}}[5m])))'
        f" and (sum(rate(http_requests_total{{{loc}}}[1m])) > 0)"
    )
    ty_le = truy_van_instant(cau, luc)
    if ty_le is None:
        return "—", "Prometheus không trả dữ liệu quanh lúc phát hiện"
    khi = "quanh lúc phát hiện" if luc is not None else "5 phút gần nhất"
    return f"{max(ty_le, 0) * 100:.1f}%", f"request chậm hơn {le}s, {khi}"


# ---------------------------------------------------------------------------
# Tải dữ liệu
# ---------------------------------------------------------------------------


def _lay_json(url: str, tham_so: dict | None = None, *, timeout: int = 60) -> Any:
    """GET rồi trả JSON. **Cố ý ném lỗi** khi mã trạng thái không phải 2xx.

    Không nuốt lỗi ở tầng này. Mọi chỗ gọi đều nằm trong hàm có `@st.cache_data`,
    và chúng tự quyết định hiển thị gì khi hỏng — trang này đã ghi rõ nguyên
    tắc "ô nào không có nguồn thì hiện `—` kèm câu nói vì sao". Trả `None` ở đây
    sẽ biến một backend chết thành một war room trông như bình thường nhưng
    trống rỗng, tức là khẳng định SAI với người trực rằng không có gì xảy ra.

    Timeout 60 giây vì `/incidents/{key}/logs` gọi `docker logs` qua subprocess —
    chậm hơn hẳn các endpoint chỉ đọc Jira.
    """
    phan_hoi = requests.get(url, params=tham_so or {}, timeout=timeout)
    phan_hoi.raise_for_status()
    return phan_hoi.json()


@st.cache_data(ttl=LAM_MOI_GIAY, show_spinner=False)
def tai_danh_sach() -> dict:
    """Danh sách sự cố + sức khoẻ Agent. Hai lời gọi, luôn chạy.

    Danh sách đủ để dựng **toàn bộ** sidebar (mã, mức độ, trạng thái, tiêu đề,
    mốc giờ). Nó KHÔNG có `signal`/`hypotheses`/`proposal`/`timeline` —
    `real.py::_search()` chỉ xin vài field của Jira, phần có cấu trúc nằm trong
    description và comment nên phải hỏi từng phiếu.
    """
    ket_qua: dict[str, Any] = {
        "ds": [],
        "health": {},
        "loi": None,
        "luc": datetime.now(VN_TZ).strftime("%H:%M:%S"),
    }
    try:
        ds = _lay_json(f"{API}/api/incidents", {"only_open": False})
    except (requests.RequestException, ValueError) as loi:
        ket_qua["loi"] = str(loi)
        return ket_qua
    if not isinstance(ds, list):
        ket_qua["loi"] = "API trả về không đúng khuôn danh sách"
        return ket_qua

    ket_qua["ds"] = sorted(ds, key=lambda i: i.get("detected_at") or "", reverse=True)
    ket_qua["health"] = tai_suc_khoe()
    return ket_qua


@st.cache_data(ttl=60, show_spinner=False)
def tai_suc_khoe() -> dict:
    """Sức khoẻ Agent — cache riêng, TTL dài hơn danh sách.

    Nó chỉ đổi khi ai đó sửa biến môi trường rồi deploy lại, tức hàng giờ một
    lần, mà mỗi lượt hỏi mất ~0,8 giây. Gói chung với danh sách (TTL 15s) là trả
    0,8 giây đó bốn lần mỗi phút cho một câu trả lời không đổi.
    """
    try:
        goi = _lay_json(f"{API}/api/v1/agent/health", timeout=20)
    except (requests.RequestException, ValueError):
        return {}
    return goi if isinstance(goi, dict) else {}


@st.cache_data(ttl=120, show_spinner=False)
def tai_chi_tiet(khoa: str) -> dict:
    """Chi tiết MỘT phiếu — chỉ phiếu đang xem.

    ⚠️ Đừng "tối ưu" thành tải sẵn chi tiết của tất cả phiếu để đổi sự cố khỏi
    reload. Đã thử ngày 17/08 và **đo được là không dùng được**: 34 phiếu thật
    trên Jira mất **18,3 giây**, và tăng từ 8 lên 12 luồng không nhanh hơn một
    giây nào — bản trên Render chạy một worker nên mọi request xếp hàng ở server
    chứ không phải ở đây. Mỗi chi tiết còn là 3 lượt gọi Jira REST (issue +
    changelog + comment), nhân 34 là ~100 lượt mỗi lần mở trang, đủ để chạm rate
    limit của Jira Cloud.

    Nên trang chấp nhận đổi: bấm sang sự cố khác thì tải lại trang (~1,2 giây),
    còn mở trang lần đầu chỉ mất một lượt gọi. TTL dài hơn danh sách vì chi tiết
    của phiếu đã đóng không đổi nữa.
    """
    if not khoa:
        return {}
    try:
        goi = _lay_json(f"{API}/api/incidents/{khoa}")
    except (requests.RequestException, ValueError):
        return {}
    return goi if isinstance(goi, dict) else {}


@st.cache_data(ttl=LAM_MOI_GIAY, show_spinner=False)
def tai_log(khoa: str) -> dict:
    """Log thô của phiếu đang xem, đọc TƯƠI từ container qua `/api/incidents/{key}/logs`.

    Vì sao không dùng `hypotheses[].log_evidence` có sẵn trong phiếu: nó chỉ được
    Agent lưu lên Jira khi log **đổi được kết luận** (xem
    `_post_lai_neu_log_doi_ket_luan` trong incident_graph.py). Đối chiếu 49 phiếu
    thật ngày 23/08: 15/15 phiếu mà bộ luật đã tự nêu được nguyên nhân đều có
    ĐÚNG 0 dòng log — dù Agent đã đọc log thật, và dù chính những dòng
    `pool_in_use=5 pool_size=5` đó mới là thứ chứng minh chẩn đoán.

    TTL ngắn bằng `LAM_MOI_GIAY`: sự cố còn mở thì cửa sổ log kéo tới hiện tại,
    nên mỗi lần làm mới trang là thấy dòng mới.

    Nuốt lỗi và trả `{}`: mất khung log không đáng làm hỏng cả war room, mà
    endpoint này lại là endpoint dễ vắng mặt nhất (bản API cũ chưa có nó).
    """
    if not khoa:
        return {}
    try:
        goi = _lay_json(f"{API}/api/incidents/{khoa}/logs", timeout=30)
    except (requests.RequestException, ValueError):
        return {}
    return goi if isinstance(goi, dict) else {}


@st.cache_data(ttl=LAM_MOI_GIAY, show_spinner=False)
def prom_song_cached() -> bool:
    """`prom_song()` có cache — mỗi lần dựng trang chỉ dò đúng một lần."""
    return prom_song()


@st.cache_data(ttl=LAM_MOI_GIAY, show_spinner=False)
def tai_chuoi(khoa: str, promql: str, bat_dau: int, ket_thuc: int) -> dict:
    """Chuỗi thời gian cho biểu đồ của phiếu đang xem.

    ⚠️ Chỉ vẽ được cho phiếu **đang xem**, và đó là giới hạn có lý do chứ không
    phải thiếu sót: câu PromQL nằm trong `MetricEvidence.promql` của từng sự cố,
    mà cái đó chỉ có trong chi tiết phiếu. Sidebar không có chi tiết nên sparkline
    ở đó vẽ nét đứt phẳng.

    ⚠️ Đừng chữa bằng cách đặt một câu PromQL mặc định vẽ chung cho sidebar. Mỗi
    sự cố do một chỉ số khác nhau kích hoạt — latency, tỷ lệ lỗi, pool, bộ nhớ —
    nên một câu dùng chung là vẽ minh hoạ cho một câu chuyện khác. Cùng lý do với
    cảnh báo trong docstring đầu file và trong `status_page.py::load_up()`.

    `khoa` không dùng trong thân hàm, chỉ để cache tách theo từng phiếu.
    """
    if not promql:
        return {"ok": False, "loi": "tín hiệu không kèm câu PromQL", "chuoi": []}
    buoc = max(15, -(-(ket_thuc - bat_dau) // SO_DIEM_TOI_DA))
    return truy_van_range(promql, bat_dau, ket_thuc, buoc)


# ---------------------------------------------------------------------------
# Mảnh giao diện
# ---------------------------------------------------------------------------


def sparkline(inc: dict, chuoi: dict | None) -> str:
    """Đường 52×16 trong danh sách bên trái — hình dạng của vấn đề.

    ⚠️ Chỉ vẽ khi có dữ liệu thật. Không có thì vẽ một nét đứt phẳng mờ, KHÔNG
    vẽ đường dốc lên cho "hợp mức độ": nhìn thoáng qua sẽ tưởng là số đo, mà nó
    sẽ dốc lên cả với sự cố đã bình ổn. Cùng lý do với đoạn cảnh báo về biểu đồ
    trong docstring đầu file.
    """
    lop = _lop_severity(inc)
    mau = {"p1": "var(--p1)", "p2": "var(--p2)", "p3": "var(--p3)", "p4": "var(--ink-1)"}.get(
        lop, "var(--ok)"
    )

    diem = (chuoi or {}).get("chuoi") or []
    diem = diem[0]["diem"] if diem else []
    if len(diem) < 2:
        return (
            '<span class="inc-spark"><svg width="52" height="16" viewBox="0 0 52 16">'
            '<path d="M0 8 L52 8" fill="none" stroke="var(--ink-3)" stroke-width="1.5" '
            'stroke-dasharray="2 3"/></svg></span>'
        )

    # Lấy ~10 điểm rải đều: mắt không phân biệt được nhiều hơn ở bề rộng 52px.
    buoc = max(1, len(diem) // 10)
    mau_diem = diem[::buoc][-11:]
    gia_tri = [v for _, v in mau_diem]
    thap, cao = min(gia_tri), max(gia_tri)
    khoang = (cao - thap) or 1.0
    doan = []
    for i, (_, v) in enumerate(mau_diem):
        x = i / (len(mau_diem) - 1) * 52
        y = 14 - (v - thap) / khoang * 12
        doan.append(f"{'M' if i == 0 else 'L'}{x:.0f} {y:.0f}")
    return (
        '<span class="inc-spark"><svg width="52" height="16" viewBox="0 0 52 16">'
        f'<path d="{" ".join(doan)}" fill="none" stroke="{mau}" stroke-width="1.5"/>'
        "</svg></span>"
    )


def muc(so: int, eyebrow: str, tieu_de: str, than: str, *, aside: str = "", cuoi: bool = False) -> str:
    """Một section theo đúng mẫu: eyebrow đánh số · tiêu đề serif · aside phải.

    `tieu_de` và `aside` nhận HTML thô (để đặt `<em>`), nên chỗ gọi tự lo thoát
    phần động.
    """
    style = ' style="margin-bottom:0"' if cuoi else ""
    ben_phai = f'<span class="sec-aside">{aside}</span>' if aside else ""
    return (
        f"<section class=\"section\"{style}>"
        '<div class="sec-head">'
        f'<span class="sec-eyebrow">{so:02d} · {e(eyebrow)}</span>'
        f'<h2 class="sec-title">{tieu_de}</h2>'
        f"{ben_phai}</div>{than}</section>"
    )


def o_vital(
    nhan: str,
    so: str,
    *,
    don_vi: str = "",
    phu: str = "",
    bien: str = "",
    delta: str = "",
    delta_lop: str = "bad",
    cham: bool = False,
) -> str:
    """Một ô trong dải vitals. `bien` là "alert" / "ok" / "empty"."""
    dau_cham = ICON["cham"] if cham else ""
    don_vi_html = f'<span class="unit">{e(don_vi)}</span>' if don_vi else ""
    delta_html = f'<span class="delta {delta_lop}">{e(delta)}</span>' if delta else ""
    return (
        f'<div class="vital {bien}">'
        f'<div class="vital-label">{dau_cham}{e(nhan)}</div>'
        f'<div class="vital-value">{e(so)}{don_vi_html}{delta_html}</div>'
        f'<div class="vital-sub">{e(phu)}</div>'
        "</div>"
    )


def bang_vitals(inc: dict, signal: dict, chuoi: dict | None) -> str:
    """Bốn ô số ở đầu mục bằng chứng.

    Sự cố đang mở và sự cố đã đóng cần bốn con số khác nhau — đã đóng thì "hiện
    tại" không còn là câu hỏi, mà "mất bao lâu để dập" mới là.
    """
    cau, don_vi = labels.metric(signal.get("metric_name", ""))
    gia_tri = float(signal.get("metric_value") or 0)
    nguong = float(signal.get("threshold") or 0)
    kich_hoat = _bang_chung_kich_hoat(signal) or {}
    nen = kich_hoat.get("baseline")

    so_gt, dv_gt = _so_ngan(gia_tri, don_vi)
    so_ng, dv_ng = _so_ngan(nguong, don_vi)
    da_xong = inc.get("state") not in DANG_XAY_RA

    o: list[str] = []
    if da_xong:
        o.append(o_vital("Lúc phát hiện", so_gt, don_vi=dv_gt, phu=cau, bien="alert", cham=True))

        # "Hiện tại" chỉ có nghĩa khi hỏi được Prometheus ngay lúc này.
        diem_cuoi = ((chuoi or {}).get("chuoi") or [{}])[0].get("diem") or []
        if diem_cuoi:
            hien, dv_hien = _so_ngan(diem_cuoi[-1][1], don_vi)
            duoi_nguong = nguong and diem_cuoi[-1][1] < nguong
            o.append(
                o_vital(
                    "Hiện tại",
                    hien,
                    don_vi=dv_hien,
                    phu="đã dưới ngưỡng" if duoi_nguong else "đo lúc mở trang",
                    bien="ok" if duoi_nguong else "",
                )
            )
        else:
            o.append(o_vital("Hiện tại", "—", phu="cần Prometheus để đo", bien="empty"))

        so_pt, dv_pt = fmt_duration_ngan(float(signal.get("breached_for_seconds") or 0))
        o.append(o_vital("Vượt ngưỡng liên tục", so_pt, don_vi=dv_pt, phu="trước khi mở phiếu"))

        if inc.get("resolved_at") and inc.get("detected_at"):
            tong = (_unix(inc["resolved_at"]) or 0) - (_unix(inc["detected_at"]) or 0)
            so_kp, dv_kp = fmt_duration_ngan(tong)
            o.append(o_vital("Thời gian khắc phục", so_kp, don_vi=dv_kp, phu="phát hiện → đóng phiếu"))
        else:
            o.append(o_vital("Thời gian khắc phục", "—", phu="phiếu chưa ghi giờ đóng", bien="empty"))
        return f'<div class="vitals">{"".join(o)}</div>'

    o.append(
        o_vital("Hiện tại", so_gt, don_vi=dv_gt, phu=f"{cau} · lúc phát hiện", bien="alert", cham=True)
    )
    o.append(o_vital("Ngưỡng cảnh báo", so_ng, don_vi=dv_ng, phu="mức bắt đầu coi là sự cố"))
    lech = _lech(gia_tri, nguong)
    o.append(
        o_vital(
            "Mức lệch",
            lech or "—",
            phu="so với ngưỡng" if lech else "không có ngưỡng để so",
            delta=f"+{(gia_tri / nguong - 1) * 100:.0f}%" if nguong and gia_tri > nguong else "",
            bien="" if lech else "empty",
        )
    )
    if nen is not None:
        so_nen, dv_nen = _so_ngan(float(nen), don_vi)
        o.append(
            o_vital(
                "Mức thường ngày",
                so_nen,
                don_vi=dv_nen,
                phu="baseline đo được",
                delta=_lech(gia_tri, float(nen)) or "",
            )
        )
    else:
        o.append(
            o_vital("Mức thường ngày", "—", phu="chỉ số này không có baseline", bien="empty")
        )
    return f'<div class="vitals">{"".join(o)}</div>'


def bang_bieu_do(inc: dict, signal: dict, chuoi: dict | None) -> str:
    """Biểu đồ diễn biến — SVG dựng thẳng từ điểm dữ liệu Prometheus trả về.

    ⚠️ Không có dữ liệu thì vẽ lưới trống kèm câu nói rõ vì sao. Đừng "đỡ trống"
    bằng một mảng cứng.
    """
    ten_metric = str(signal.get("metric_name", "metric"))
    nguong = float(signal.get("threshold") or 0)
    kich_hoat = _bang_chung_kich_hoat(signal) or {}
    nen = kich_hoat.get("baseline")
    nen = float(nen) if nen is not None else None
    rong, cao = 800, 200

    dau_de = (
        f'<div class="chart-head">'
        f'<div class="chart-title"><span class="code">{e(ten_metric)}</span></div>'
        '<div class="chart-legend">'
        '<span class="item"><span class="swatch" style="background: var(--signal)"></span>đo được</span>'
        + (
            '<span class="item"><span class="swatch" style="background: var(--ink-2)"></span>thường ngày</span>'
            if nen is not None
            else ""
        )
        + (
            '<span class="item"><span class="swatch" style="background: var(--p1)"></span>ngưỡng</span>'
            if nguong
            else ""
        )
        + "</div></div>"
    )

    luoi = "".join(
        f'<line x1="0" y1="{cao * f:.0f}" x2="{rong}" y2="{cao * f:.0f}" '
        f'stroke="var(--border)" stroke-dasharray="2 4"/>'
        for f in (0.2, 0.4, 0.6, 0.8)
    )

    diem = ((chuoi or {}).get("chuoi") or [{}])[0].get("diem") or []
    if len(diem) < 2:
        vi_sao = (chuoi or {}).get("loi") or "Prometheus không với tới được"
        than = (
            f"{luoi}"
            f'<text x="{rong / 2}" y="{cao / 2 - 6}" font-family="Inter, sans-serif" font-size="12" '
            f'fill="var(--ink-2)" text-anchor="middle">Chưa vẽ được đường nào</text>'
            f'<text x="{rong / 2}" y="{cao / 2 + 14}" font-family="Inter, sans-serif" font-size="10" '
            f'fill="var(--ink-3)" text-anchor="middle">{e(str(vi_sao)[:90])}</text>'
        )
        chan = "<span>—</span>" * 5
        return (
            f'<div class="chart-panel">{dau_de}'
            f'<svg class="chart-svg" viewBox="0 0 {rong} {cao}" preserveAspectRatio="xMidYMid meet">{than}</svg>'
            f'<div class="chart-foot">{chan}</div></div>'
        )

    moc = [t for t, _ in diem]
    val = [v for _, v in diem]
    t0, t1 = min(moc), max(moc)
    mocs = [nguong] if nguong else []
    if nen is not None:
        mocs.append(nen)
    v0 = min(val + [m * 0.5 for m in mocs] or val)
    v1 = max(val + [m * 1.3 for m in mocs] or val)
    if v1 == v0:
        v1 = v0 + 1

    def _x(t: float) -> float:
        return (t - t0) / (t1 - t0) * rong if t1 != t0 else rong / 2

    def _y(v: float) -> float:
        return cao - ((v - v0) / (v1 - v0) * (cao - 20) + 10)

    duong = " ".join(
        f"{'M' if i == 0 else 'L'}{_x(t):.0f} {_y(v):.0f}" for i, (t, v) in enumerate(diem)
    )
    vung = f"{duong} L{rong} {cao} L0 {cao} Z"

    lop_nguong = ""
    if nguong:
        y = _y(nguong)
        lop_nguong = (
            f'<line x1="0" y1="{y:.0f}" x2="{rong}" y2="{y:.0f}" stroke="var(--p1)" '
            f'stroke-width="1" stroke-dasharray="4 4" opacity="0.55"/>'
            f'<text x="6" y="{y - 5:.0f}" font-family="Inter, sans-serif" font-size="9" '
            f'fill="var(--p1)" opacity="0.85">ngưỡng {nguong:g}</text>'
        )
    lop_nen = ""
    if nen is not None:
        y = _y(nen)
        lop_nen = (
            f'<line x1="0" y1="{y:.0f}" x2="{rong}" y2="{y:.0f}" stroke="var(--ink-2)" '
            f'stroke-width="1" stroke-dasharray="3 3" opacity="0.65"/>'
        )

    # Mốc "vượt ngưỡng" và "đóng phiếu" — chỉ vẽ khi nằm trong cửa sổ đang xem.
    lop_moc = ""
    for gio, chu, mau in (
        (_unix(inc.get("detected_at")), "t=0 · vượt ngưỡng", "var(--p2)"),
        (_unix(inc.get("resolved_at")), "đóng phiếu", "var(--ok)"),
    ):
        if gio is None or not (t0 < gio < t1):
            continue
        x = _x(gio)
        neo = "end" if x > rong * 0.75 else "start"
        lech_chu = -6 if neo == "end" else 6
        lop_moc += (
            f'<line x1="{x:.0f}" y1="0" x2="{x:.0f}" y2="{cao}" stroke="{mau}" '
            f'stroke-width="1" opacity="0.4" stroke-dasharray="2 3"/>'
            f'<text x="{x + lech_chu:.0f}" y="14" font-family="Inter, sans-serif" font-size="9" '
            f'fill="{mau}" text-anchor="{neo}">{e(chu)}</text>'
        )

    cuoi_x, cuoi_y = _x(diem[-1][0]), _y(diem[-1][1])
    vuot = nguong and diem[-1][1] >= nguong
    mau_cham = "var(--p1)" if vuot else "var(--ok)"
    ma_grad = f"grad-{inc.get('jira_key', 'x')}"

    nhan_gio = []
    for i in range(5):
        t = t0 + (t1 - t0) * i / 4
        nhan_gio.append(_gio_vn(t).strftime("%H:%M"))
    if not inc.get("resolved_at"):
        nhan_gio[-1] = "Bây giờ"

    than = (
        f"{luoi}{lop_nguong}{lop_nen}"
        f'<defs><linearGradient id="{ma_grad}" x1="0" x2="0" y1="0" y2="1">'
        '<stop offset="0%" stop-color="var(--signal)" stop-opacity="0.28"/>'
        '<stop offset="100%" stop-color="var(--signal)" stop-opacity="0"/>'
        "</linearGradient></defs>"
        f'<path d="{vung}" fill="url(#{ma_grad})"/>'
        f'<path d="{duong}" fill="none" stroke="var(--signal)" stroke-width="1.75"/>'
        f'{lop_moc}'
        f'<circle cx="{cuoi_x:.0f}" cy="{cuoi_y:.0f}" r="8" fill="{mau_cham}" opacity="0.2"/>'
        f'<circle cx="{cuoi_x:.0f}" cy="{cuoi_y:.0f}" r="4" fill="{mau_cham}"/>'
    )
    chan = "".join(f"<span>{e(n)}</span>" for n in nhan_gio)
    return (
        f'<div class="chart-panel">{dau_de}'
        f'<svg class="chart-svg" viewBox="0 0 {rong} {cao}" preserveAspectRatio="xMidYMid meet">{than}</svg>'
        f'<div class="chart-foot">{chan}</div></div>'
    )


def the_promql(signal: dict, luc: str | None) -> str:
    """Thẻ "câu truy vấn dựng nên chỉ số này" + link mở thẳng Prometheus."""
    kich_hoat = _bang_chung_kich_hoat(signal)
    if not kich_hoat:
        return (
            '<div class="evidence"><p>Tín hiệu này không kèm câu PromQL nào — '
            "sự cố tạo trước khi Agent lưu lại câu truy vấn.</p></div>"
        )
    cau = str(kich_hoat.get("promql", ""))
    link = link_prometheus(cau, luc)
    noi_dung = (
        khoi_code("PromQL", to_mau_promql(cau), nguyen_van=cau)
        + (hang_link(link, "Mở trên Prometheus, đúng thời điểm sự cố") if link else "")
        + '<div class="hint">Link đã gắn sẵn mốc giờ lúc phát hiện. Bỏ mốc đó ra thì '
        "câu này trả rỗng sau khi sự cố qua, vì cửa sổ đo không còn lưu lượng nào.</div>"
    )
    return (
        '<div class="evidence">'
        '<div class="toggle-section">'
        '<button class="toggle-btn" type="button" onclick="this.parentElement.classList.toggle(\'open\')">'
        '<span class="toggle-icon">▶</span> Câu truy vấn dán vào Prometheus</button>'
        f'<div class="toggle-content">{noi_dung}</div>'
        '</div></div>'
    )


def the_so_lieu(signal: dict, luc: str | None) -> str:
    """Bằng chứng số còn lại — mỗi dòng hai tầng: câu tiếng Việt + dòng `↳`.

    ⚠️ Đừng bỏ dòng `↳`. Xem docstring đầu file: người trực cần tên metric gốc,
    và đó là người duy nhất thật sự sửa được sự cố.
    """
    bang_chung = signal.get("evidence") or []
    if not bang_chung:
        return (
            '<div class="evidence"><p>Tín hiệu này không kèm bằng chứng số nào '
            "ngoài chỉ số kích hoạt ở trên.</p></div>"
        )

    ten_kich_hoat = signal.get("metric_name")
    hang: list[str] = []
    for ev in bang_chung:
        dong = labels.bang_chung(
            ev.get("name", ""),
            float(ev.get("value") or 0),
            baseline=ev.get("baseline"),
            unit=ev.get("unit", ""),
            promql=ev.get("promql", ""),
        )
        cau, don_vi = labels.metric(ev.get("name", ""))
        la_kich_hoat = ev.get("name") == ten_kich_hoat
        so = _so_doc_duoc(float(ev.get("value") or 0), don_vi)
        lop_so = "num bad" if la_kich_hoat else "num"

        chi_tiet = ""
        if ev.get("promql"):
            link = link_prometheus(ev["promql"], luc)
            chi_tiet = (
                '<details class="more"><summary>Câu truy vấn</summary>'
                + khoi_code("PromQL", to_mau_promql(ev["promql"]), nguyen_van=ev["promql"])
                + (hang_link(link, "Mở trên Prometheus") if link else "")
                + "</details>"
            )

        hang.append(
            '<div class="ev-row">'
            f'<div class="ev-line"><span class="name">{e(dong.plain)}</span>'
            f'<span class="{lop_so}">{e(so)}</span></div>'
            f'<div class="tech"><span class="arrow">↳</span>{e(dong.raw)}</div>'
            f"{chi_tiet}</div>"
        )
    return f'<div class="evidence">{"".join(hang)}</div>'


#: `ly_do` từ API → câu giải thích cho người trực. Xem `LY_DO_*` trong
#: `src/services/log_collector.py`.
#:
#: Bốn trạng thái này KHÔNG được gộp thành một câu "không có log". "Chưa có dòng
#: lỗi nào" là bằng chứng CHỐNG LẠI giả thuyết lỗi ứng dụng; "máy chạy API không
#: có Docker" là Agent đang mù. Hai câu dẫn tới hai hành động khác hẳn nhau.
_LY_DO_LOG: dict[str, str] = {
    "khong-co-docker": (
        "Máy đang chạy API không có Docker nên không đọc được log container. "
        "Bản trên Render luôn rơi vào trường hợp này — muốn xem log thì chạy API "
        "ngay tại máy có demo stack."
    ),
    "khong-co-container": (
        "Không tìm thấy container nào của dịch vụ này đang chạy. Kiểm tra "
        "<code>docker compose -f docker-compose.demo.yml ps</code>."
    ),
    "log-sach": (
        "Container có chạy và có ghi log, nhưng KHÔNG dòng nào ở mức "
        "ERROR/WARNING trong cửa sổ này. Đây là một bằng chứng, không phải thiếu "
        "bằng chứng: nó nói sự cố không đến từ lỗi ứng dụng ghi ra được."
    ),
    "ngoai-tam-log": (
        "Cửa sổ thời gian của sự cố này đã trôi khỏi phần log container còn giữ — "
        "log cũ bị đẩy ra khi container ghi tiếp. Cũng KHÔNG phải \"service không có "
        "lỗi\": không còn gì để đọc mà thôi. Phiếu đã đóng từ lâu thì gần như luôn "
        "rơi vào đây; hãy dùng bằng chứng metric và bản log Agent đã lưu."
    ),
    "khong-ro-service": (
        "Phiếu không nói rõ dịch vụ nào bị ảnh hưởng nên không biết đọc log của ai."
    ),
}


def _moc_log(ts: str) -> str:
    """Timestamp một dòng log → giờ Việt Nam dạng `HH:MM:SS`.

    ⚠️ Log của container ghi giờ **UTC không kèm ký hiệu múi giờ** (`basicConfig`
    trong demo service dùng `datefmt` không có `%z`). `_unix()` gặp chuỗi trần
    như vậy sẽ hiểu là giờ MÁY NÀY, tức +07 — và mọi dòng log hiện sai đúng 7
    tiếng, lệch ra ngoài cả cửa sổ sự cố ngay bên cạnh nó. Nên gắn `+00:00` khi
    chuỗi chưa có múi giờ, rồi mới đổi.
    """
    if not ts:
        return ""
    try:
        moc = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ts[:19]
    if moc.tzinfo is None:
        moc = moc.replace(tzinfo=UTC)
    return moc.astimezone(VN_TZ).strftime("%H:%M:%S")


def _gop_dong_lap(dong: list[dict]) -> list[tuple[dict, int]]:
    """Gộp các dòng log giống hệt nhau và LIỀN NHAU thành một, kèm số lần lặp.

    Vì sao cần: UC-1 làm `service-thanh-toan` ghi `pool_in_use=5 pool_size=5` mỗi
    request, nên cửa sổ sự cố có hàng trăm dòng y hệt. Đổ nguyên xi ra màn hình
    thì khung log dài mấy mét mà nói đúng MỘT điều — và nếu có một dòng khác
    thường xen giữa, không ai nhìn ra.

    Chỉ gộp dòng LIỀN NHAU, không gộp toàn cục: hai cụm cùng nội dung cách nhau
    mười phút là hai lần sự việc xảy ra, gộp lại là bóp méo diễn biến.
    """
    gop: list[tuple[dict, int]] = []
    for lg in dong:
        khoa = (lg.get("level"), lg.get("message"))
        if gop and (gop[-1][0].get("level"), gop[-1][0].get("message")) == khoa:
            gop[-1] = (gop[-1][0], gop[-1][1] + 1)
        else:
            gop.append((lg, 1))
    return gop


def khoi_log(
    hypotheses: list[dict],
    goi_log: dict | None = None,
    log_da_luu: list[dict] | None = None,
) -> str:
    """Log gốc — giữ **nguyên văn** ERROR/WARNING.

    Câu tiếng Việt đi ở chú thích phía trên khối, không thay chữ trong log: đó là
    chữ người trực sẽ grep.

    Hai nguồn, ưu tiên bản TƯƠI:

    1. `goi_log` — đọc thẳng từ container lúc mở phiếu (`tai_log()`). Sự cố còn
       mở thì cửa sổ kéo tới hiện tại, nên đây là log đang chảy ra lúc này.
    2. `hypotheses[].log_evidence` — ảnh chụp Agent đã lưu. Chỉ tồn tại khi log
       đổi được kết luận, nên hiếm; giữ làm đường lùi cho lúc không đọc được
       container (bản API trên Render), và cho phiếu cũ đã đóng từ lâu.
    """
    goi_log = goi_log or {}
    tuoi = [lg for lg in (goi_log.get("logs") or []) if isinstance(lg, dict)]

    # Thứ tự nguồn: log Agent đã LƯU lên Jira đứng trước log gắn kèm giả thuyết —
    # cái trước có ở mọi sự cố, cái sau chỉ có khi log đổi được kết luận.
    da_luu: list[dict] = [lg for lg in (log_da_luu or []) if isinstance(lg, dict)]
    for h in hypotheses:
        da_luu.extend(lg for lg in (h.get("log_evidence") or []) if isinstance(lg, dict))

    dong_nguon = tuoi or da_luu
    la_tuoi = bool(tuoi)

    if not dong_nguon:
        cau = _LY_DO_LOG.get(str(goi_log.get("ly_do", "")), "")
        if not cau:
            # Không có `goi_log` nghĩa là bản API đang chạy chưa có endpoint
            # `/logs`. Nói ra, thay vì im lặng để người đọc tưởng service sạch.
            cau = (
                "Chưa đọc được log cho phiếu này. Bản API đang chạy có thể chưa có "
                "<code>GET /api/incidents/{key}/logs</code>."
            )
        return (
            '<div class="evidence"><div class="toggle-section">'
            '<button class="toggle-btn" type="button" '
            "onclick=\"this.parentElement.classList.toggle('open')\">"
            '<span class="toggle-icon">▶</span> Log gốc — không có dòng nào</button>'
            f'<div class="toggle-content"><div class="hint">{cau}</div></div>'
            "</div></div>"
        )

    hang: list[str] = []
    for lg, so_lan in _gop_dong_lap(dong_nguon):
        muc_do = str(lg.get("level", "INFO")).upper()
        lop = {"ERROR": "lv-error", "WARNING": "lv-warn", "WARN": "lv-warn"}.get(muc_do, "lv-info")
        mau_pattern = f' <span class="cm">[{e(lg["pattern"])}]</span>' if lg.get("pattern") else ""
        lap = f'<span class="lap">×{so_lan}</span>' if so_lan > 1 else ""
        hang.append(
            f'<span class="log-line">{lap}<span class="cm">{e(_moc_log(str(lg.get("timestamp") or "")))}</span> '
            f'<span class="{lop}">{e(muc_do)}</span>{mau_pattern} '
            f'{e(lg.get("message", ""))}</span>'
        )

    nguon = " · ".join(sorted({str(lg.get("source", "")) for lg in dong_nguon if lg.get("source")}))
    _, ten_muc = labels.log_level("ERROR")

    if la_tuoi:
        cua_so = (
            f'{_moc_log(str(goi_log.get("start", "")))} → '
            f'{_moc_log(str(goi_log.get("end", "")))}'
        )
        duoi = (
            f'<div class="hint">Đọc thẳng từ container lúc mở trang, cửa sổ {e(cua_so)} '
            + (
                "— sự cố còn mở nên cửa sổ kéo tới hiện tại, làm mới trang là thấy dòng mới."
                if goi_log.get("dang_mo")
                else "— sự cố đã đóng nên cửa sổ dừng ở mốc khắc phục."
            )
            + f" Đã gộp {len(dong_nguon)} dòng thành {len(hang)} mục, dòng trùng liền nhau "
            "gom lại kèm số lần.</div>"
        )
        tieu_de = f"Log gốc đọc trực tiếp — dòng đỏ là mức {e(ten_muc)}"
    else:
        duoi = (
            '<div class="hint">Đây là bản Agent đã lưu lúc chẩn đoán, KHÔNG phải log '
            "hiện tại — log container của cửa sổ đó đã trôi mất, hoặc trang đang "
            "chạy ở chỗ không với tới container.</div>"
        )
        tieu_de = f"Log Agent đã lưu — dòng đỏ là mức {e(ten_muc)}"

    noi_dung_log = khoi_code(f"LOG · {nguon or 'container'}", "".join(hang))
    return (
        '<div class="evidence">'
        '<div class="toggle-section">'
        '<button class="toggle-btn" type="button" '
        "onclick=\"this.parentElement.classList.toggle('open')\">"
        f'<span class="toggle-icon">▶</span> {tieu_de}</button>'
        f'<div class="toggle-content">{noi_dung_log}{duoi}</div>'
        "</div></div>"
    )


def khoi_lap_luan(inc: dict, hypotheses: list[dict]) -> str:
    """Chuỗi suy luận của Agent — giả thuyết cuối là kết luận."""
    if not hypotheses:
        return (
            '<div class="note">Chưa có giả thuyết nào — sự cố này tạo trước khi '
            "Agent biết chẩn đoán.</div>"
        )
    da_xong = inc.get("state") not in DANG_XAY_RA
    lop_done = " done" if da_xong else ""

    khoi: list[str] = []
    for i, h in enumerate(hypotheses):
        cuoi = i == len(hypotheses) - 1
        do_tin = float(h.get("confidence") or 0)
        nhan = "Kết luận" if cuoi else f"Giả thuyết {i + 1}"

        chip: list[str] = []
        for ev in h.get("evidence") or []:
            gia_tri = float(ev.get("value") or 0)
            cau, don_vi = labels.metric(ev.get("name", ""))
            nen = ev.get("baseline")
            xau = nen is not None and nen and gia_tri > float(nen)
            lop_chip = "warn" if xau else "ok"
            chip.append(
                f'<span class="r-evidence {lop_chip}">{e(cau)} '
                f'<span class="val">{e(_so_doc_duoc(gia_tri, don_vi))}</span></span>'
            )

        # Dòng `↳` gom chung cho cả cụm chip: mỗi chip một dòng thì vỡ nhịp, mà
        # bỏ hẳn thì người trực mất tên metric gốc.
        tho = " · ".join(
            labels.bang_chung(
                ev.get("name", ""),
                float(ev.get("value") or 0),
                unit=ev.get("unit", ""),
            ).raw
            for ev in (h.get("evidence") or [])
        )
        dong_tho = f'<div class="tech"><span class="arrow">↳</span>{e(tho)}</div>' if tho else ""

        deploy = h.get("related_deploy")
        khoi_deploy = ""
        if deploy:
            khoi_deploy = (
                f'<div class="r-body quiet">Trùng một lần deploy: '
                f'<span class="inline-code">{e(deploy.get("version", ""))}</span> '
                f'lúc {e(fmt_time_vn(deploy["deployed_at"]))}'
                + (f' — {e(deploy["change_note"])}' if deploy.get("change_note") else "")
                + "</div>"
            )

        khoi.append(
            f'<div class="reasoning-item{" conclusion" if cuoi else ""}">'
            f'<div class="r-label">{e(nhan)} · độ tin cậy {do_tin * 100:.0f}%</div>'
            f'<div class="r-body"><strong>{e(h.get("statement", ""))}</strong></div>'
            + (f'<div class="r-body quiet">{e(h["reasoning"])}</div>' if h.get("reasoning") else "")
            + "".join(chip)
            + dong_tho
            + khoi_deploy
            + "</div>"
        )
    return f'<div class="reasoning{lop_done}">{"".join(khoi)}</div>'


def the_de_xuat(inc: dict, proposal: dict | None) -> str:
    """Thẻ đề xuất — hai biến thể: đang chờ duyệt, và đã thực thi.

    ⚠️ Trang này **không thi hành** gì cả. Hai nút dưới cùng mở phiếu Jira; việc
    duyệt xảy ra ở đó, webhook của Jira mới gọi Agent. Đừng đổi thành nút gọi
    API: cơ chế HITL nằm ở chỗ chuyển trạng thái trên Jira (xem ADR-0001).
    """
    if not proposal:
        return '<div class="note">Agent chưa đề xuất hành động khắc phục nào cho sự cố này.</div>'

    da_xong = inc.get("state") not in DANG_XAY_RA
    cho_duyet = inc.get("state") == "Awaiting Approval"
    lop = " executed" if da_xong else ""

    if da_xong:
        the_nhan = f'{ICON["check"]} Đã thực thi · phiếu đóng lúc {e(fmt_gio(inc.get("resolved_at") or ""))}'
    elif cho_duyet:
        the_nhan = f'{ICON["set"]} Cần bạn phê duyệt · Agent đang chờ'
    else:
        the_nhan = f'{ICON["set"]} Đề xuất của Agent'

    tham_so = ""
    if proposal.get("params"):
        cap = " · ".join(f"{k}={v}" for k, v in dict(proposal["params"]).items())
        tham_so = f'<div class="proposal-target">Tham số: {e(cap)}</div>'

    can_duyet = bool(proposal.get("requires_approval", True))
    runbook = str(proposal.get("runbook") or "")
    so_buoc = len([d for d in runbook.splitlines() if d.strip()])
    o_impact = (
        '<div class="impact-grid">'
        f'<div class="impact"><div class="lb">Hành động</div>'
        f'<div class="vl"><code class="inline-code">{e(proposal.get("action", ""))}</code></div></div>'
        f'<div class="impact"><div class="lb">Cần người duyệt</div>'
        f'<div class="vl" style="color: var(--{"ok" if can_duyet else "p2"})">'
        f'{"Bắt buộc" if can_duyet else "Không"}<small>· HITL</small></div></div>'
        f'<div class="impact"><div class="lb">Runbook</div>'
        f'<div class="vl">{f"Có <small>· {so_buoc} bước</small>" if runbook else "Chưa có"}</div></div>'
        "</div>"
    )

    rui_ro = ""
    if proposal.get("risk"):
        rui_ro = f'<p><strong>Đánh đổi cần cân nhắc:</strong> {e(proposal["risk"])}</p>'

    khoi_runbook = ""
    if runbook:
        khoi_runbook = (
            '<details class="more" data-runbook><summary>Các bước thực hiện và cách kiểm đã hết chưa</summary>'
            f'<div class="tech" style="margin-top:8px;white-space:pre-wrap">{e(runbook)}</div>'
            "</details>"
        )

    da_lam = ""
    postmortem = inc.get("postmortem") or {}
    if da_xong and postmortem.get("actions_taken"):
        muc_da_lam = "".join(f"<li>{e(x)}</li>" for x in postmortem["actions_taken"])
        da_lam = f'<p><strong>Đã làm:</strong></p><ul style="margin:0 0 12px 18px">{muc_da_lam}</ul>'

    # Dải xác nhận. Nút mở phiếu Jira — không có JIRA_BASE_URL thì nói rõ chứ
    # không dựng nút chết.
    phieu = f"{JIRA_URL}/browse/{inc['jira_key']}" if JIRA_URL else ""
    if da_xong:
        ai = f'<span class="check-icon">✓</span><span>Đã có người duyệt trên phiếu <strong>{e(inc["jira_key"])}</strong> · Agent thực thi sau khi phiếu chuyển trạng thái</span>'
        nut = (
            f'<a class="btn ghost" href="{e(phieu)}" target="_blank" rel="noopener">Xem phiếu Jira</a>'
            if phieu
            else '<button class="btn ghost" type="button" disabled>Chưa đặt JIRA_BASE_URL</button>'
        )
    else:
        ai = (
            '<span class="a">WR</span>'
            f'<span>Chờ người trực duyệt trên phiếu <strong>{e(inc["jira_key"])}</strong> · '
            "Agent sẽ không tự chạy nếu chưa được duyệt</span>"
        )
        if phieu:
            nut = (
                f'<a class="btn ghost" href="{e(phieu)}" target="_blank" rel="noopener">Từ chối trên Jira</a>'
                f'<a class="btn approve" href="{e(phieu)}" target="_blank" rel="noopener">'
                f'Duyệt trên Jira {ICON["mui_ten"]}</a>'
            )
        else:
            nut = '<button class="btn ghost" type="button" disabled>Chưa đặt JIRA_BASE_URL</button>'

    ghi_chu_hitl = (
        '<div class="hint">Trang này chỉ hiển thị, <strong>không thi hành</strong> hành động nào. '
        "Duyệt/từ chối xảy ra trên phiếu Jira; webhook của Jira mới gọi Agent.</div>"
    )

    return (
        f'<div class="proposal{lop}">'
        '<div class="proposal-head">'
        f'<div class="proposal-tag">{the_nhan}</div>'
        f'<div class="proposal-title">{e(labels.action(proposal.get("action", "")))} '
        f'<code>{e(proposal.get("target", ""))}</code></div>'
        f'<div class="proposal-target">→ {e(proposal.get("target", ""))}</div>'
        f"{tham_so}</div>"
        '<div class="proposal-body">'
        f"{rui_ro}{da_lam}{o_impact}{khoi_runbook}</div>"
        f'<div class="confirm-strip"><div class="who">{ai}</div>{nut}</div>'
        f"</div>{ghi_chu_hitl}"
    )


def khoi_dien_bien(inc: dict) -> str:
    """Dòng thời gian — đọc từ changelog Jira, Jira tự ghi khi có thao tác."""
    moc = inc.get("timeline") or []
    if not moc:
        return '<div class="note">Chưa có diễn biến nào được ghi lại trên phiếu.</div>'

    hang: list[str] = []
    for su_kien in sorted(moc, key=lambda t: t.get("at") or "", reverse=True):
        ai = str(su_kien.get("actor") or "System")
        thap = ai.lower()
        if thap == "agent":
            lop, lop_who = "agent", "agent"
        elif thap in ("system", "jira"):
            lop, lop_who = "system", ""
        else:
            lop, lop_who = "human", ""
        hanh_dong = str(su_kien.get("action", ""))
        if "resolve" in hanh_dong.lower() or "đóng" in hanh_dong.lower():
            lop, lop_who = "ok", "ok"
        chi_tiet = (
            f' <span class="detail">— {e(su_kien["detail"])}</span>' if su_kien.get("detail") else ""
        )
        hang.append(
            f'<div class="act {lop}"><div class="time">{e(fmt_gio(su_kien.get("at", "")))}</div>'
            f'<div class="text"><span class="who {lop_who}">{e(ai)}</span> {e(hanh_dong)}'
            f"{chi_tiet}</div></div>"
        )
    return (
        f'<div class="activity">{"".join(hang)}</div>'
        '<div class="hint">Đọc từ changelog của phiếu Jira — Jira tự ghi mỗi khi có thao tác, '
        "nên đây là bản ghi không sửa được từ trang này.</div>"
    )


def khoi_lien_quan(inc: dict, bang_tra: dict[str, dict]) -> str:
    """Sự cố liên quan — dấu hiệu một nguyên nhân đang lan sang dịch vụ khác."""
    khoa = inc.get("related_incidents") or []
    if not khoa:
        return ""

    the: list[str] = []
    for k in khoa:
        khac = bang_tra.get(k)
        if khac:
            lop = _lop_severity(khac)
            mau = {
                "p1": "var(--p1)", "p2": "var(--p2)", "p3": "var(--p3)", "p4": "var(--ink-1)"
            }.get(lop, "var(--ok)")
            da_xong = khac.get("state") not in DANG_XAY_RA
            trang_thai = "đã đóng" if da_xong else labels.STATE.get(khac.get("state", ""), ("", ""))[1]
            dich_vu = " · ".join(labels.service(s) for s in khac.get("affected_services") or [])
            khi = (
                fmt_duration(khac["detected_at"], khac.get("resolved_at"))
                if khac.get("detected_at")
                else ""
            )
            the.append(
                f'<div class="rel-card" data-goto="{e(k)}">'
                f'<div class="rel-head"><span class="rel-sev" style="color: {mau}">'
                f'{e(khac.get("severity", ""))}</span>'
                f'<span>{e(k)} · {e(trang_thai)}</span></div>'
                f'<div class="rel-title">{e(khac.get("title", ""))}</div>'
                f'<div class="rel-meta">{e(dich_vu)}{" · kéo dài " + e(khi) if khi else ""}</div>'
                "</div>"
            )
        else:
            phieu = f"{JIRA_URL}/browse/{k}" if JIRA_URL else ""
            noi_dung = (
                f'<div class="rel-head"><span>{e(k)}</span></div>'
                '<div class="rel-title">Không nằm trong danh sách đang tải</div>'
                '<div class="rel-meta">Phiếu có thể đã ra ngoài phạm vi truy vấn</div>'
            )
            the.append(
                f'<a class="rel-card" href="{e(phieu)}" target="_blank" rel="noopener" '
                f'style="display:block;text-decoration:none">{noi_dung}</a>'
                if phieu
                else f'<div class="rel-card">{noi_dung}</div>'
            )
    return f'<div class="related-grid">{"".join(the)}</div>'


# ---------------------------------------------------------------------------
# Một view = một sự cố
# ---------------------------------------------------------------------------


def dau_trang(inc: dict, anh_huong: tuple[str, str]) -> str:
    """Crumb · tiêu đề serif · dải meta."""
    da_xong = inc.get("state") not in DANG_XAY_RA
    cho_duyet = inc.get("state") == "Awaiting Approval"
    signal = inc.get("signal") or {}
    lop_sev = _lop_severity(inc)

    if da_xong:
        lop_pill, chu_pill = "done", labels.STATE.get("Resolved", ("", "Đã xử lý xong"))[1]
    elif cho_duyet:
        lop_pill, chu_pill = "wait", labels.STATE.get("Awaiting Approval", ("", "Chờ duyệt"))[1]
    else:
        lop_pill, chu_pill = "live", labels.STATE.get(inc.get("state", ""), ("", inc.get("state", "")))[1]

    dich_vu = [labels.service(s) for s in inc.get("affected_services") or []]
    crumb = [f'<span>{e(inc.get("jira_key", ""))}</span>']
    for phan in (inc.get("affected_services") or [])[:1]:
        crumb.append('<span class="sep">/</span>')
        crumb.append(f"<span>{e(phan)}</span>")
    if signal.get("metric_name"):
        crumb.append('<span class="sep">/</span>')
        crumb.append(f'<span>{e(signal["metric_name"])}</span>')
    crumb.append('<span class="sep">·</span>')
    crumb.append(f'<span class="status-pill {lop_pill}">{e(chu_pill)}</span>')

    # Bỏ phần icon của `labels.SEVERITY`: thiết kế không dùng emoji trong UI.
    _, ten_sev, giai_thich = labels.SEVERITY.get(
        inc.get("severity", ""), ("", inc.get("severity", ""), "")
    )
    cau_tieu_de, tieu_de_tho = _tieu_de(inc, signal)
    dich_vu_html = f' <span class="service">{e(" · ".join(dich_vu))}</span>' if dich_vu else ""

    meta: list[str] = [
        f'<div class="meta-item">{ICON["lich"]}Phát hiện '
        f'<span class="val">{e(fmt_time_vn(inc["detected_at"]))}</span></div>'
    ]
    if inc.get("resolved_at"):
        meta.append(
            f'<div class="meta-item">{ICON["check"]}Đóng lúc '
            f'<span class="val">{e(fmt_time_vn(inc["resolved_at"]))} · kéo dài '
            f'{e(fmt_duration(inc["detected_at"], inc["resolved_at"]))}</span></div>'
        )
    else:
        meta.append(
            f'<div class="meta-item">{ICON["dong_ho"]}Đang kéo dài '
            f'<span class="val">{e(fmt_duration(inc["detected_at"]))}</span></div>'
        )
    gia_tri_ah, chu_thich_ah = anh_huong
    lop_ah = "val" if gia_tri_ah != "—" else "val dim"
    meta.append(
        f'<div class="meta-item">{ICON["tia"]}Ảnh hưởng '
        f'<span class="{lop_ah}">{e(gia_tri_ah)}</span> '
        f'<span style="color: var(--ink-2)">({e(chu_thich_ah)})</span></div>'
    )
    meta.append(
        f'<div class="meta-item">{ICON["hop"]}Mức độ '
        f'<span class="val">{e(ten_sev)}</span> '
        f'<span style="color: var(--ink-2)">({e(inc.get("severity", ""))})</span></div>'
    )

    phieu = f"{JIRA_URL}/browse/{inc['jira_key']}" if JIRA_URL else ""
    hanh_dong = (
        f'<a class="btn ghost small" href="{e(phieu)}" target="_blank" rel="noopener">'
        f'{ICON["tep"]} Mở phiếu Jira</a>'
        if phieu
        else '<button class="btn ghost small" type="button" disabled '
        'title="Chưa đặt JIRA_BASE_URL trong môi trường">Mở phiếu Jira</button>'
    )
    meta.append(f'<div class="meta-actions">{hanh_dong}</div>')

    return (
        f'<div class="case-crumb">{"".join(crumb)}</div>'
        f'<h1 class="case-title"><span class="sev {lop_sev}">{e(inc.get("severity", ""))}</span>'
        f"{e(cau_tieu_de)}{dich_vu_html}</h1>"
        f'<div class="tech" style="margin:-6px 0 14px">'
        f'<span class="arrow">↳</span>{e(tieu_de_tho)}</div>'
        f'<div class="case-meta">{"".join(meta)}</div>'
        + ""
    )


def view_su_co(inc: dict, kho: dict, dang_chon: bool = False) -> str:
    """Một `.content-inner.view` đầy đủ cho một sự cố."""
    khoa = inc.get("jira_key", "")
    da_xong = inc.get("state") not in DANG_XAY_RA
    signal = inc.get("signal") or {}
    hypotheses = inc.get("hypotheses") or []
    chuoi = (kho.get("chuoi") or {}).get(khoa)
    anh_huong = (kho.get("anh_huong") or {}).get(khoa, ("—", "chưa đo"))
    luc = inc.get("detected_at")

    phan: list[str] = [dau_trang(inc, anh_huong)]
    if inc.get("state") == "Awaiting Approval":
        phan.append(
            '<div class="note warn" style="margin-bottom:32px">'
            "<strong>Cần người duyệt.</strong> Agent đã chẩn đoán xong và đề xuất cách sửa ở "
            "mục bên dưới. Nó sẽ đứng yên cho tới khi có người chuyển trạng thái phiếu Jira."
            "</div>"
        )

    so = 0
    # ── 01 · Bằng chứng / Tóm tắt
    so += 1
    than = ""
    if signal:
        than += bang_vitals(inc, signal, chuoi)
        # Dòng `↳` cho cả dải vitals: người trực cần tên metric gốc và con số
        # thô, không phải câu dịch. Đừng bỏ — xem docstring đầu file.
        gia_tri_tho = float(signal.get("metric_value") or 0)
        nguong_tho = float(signal.get("threshold") or 0)
        than += (
            '<div class="tech" style="margin:-14px 0 22px">'
            f'<span class="arrow">↳</span>{e(signal.get("metric_name", ""))} = '
            f"{e(format(gia_tri_tho, 'g'))} (ngưỡng {e(format(nguong_tho, 'g'))}, "
            f'dịch vụ {e(signal.get("affected_service", ""))})</div>'
        )
        than += bang_bieu_do(inc, signal, chuoi)
        than += '<div style="height:14px"></div>'
        than += the_promql(signal, luc)
        than += the_so_lieu(signal, luc)
    elif not than:
        than = (
            '<div class="note">Sự cố này không kèm tín hiệu gốc — nó được tạo trước khi '
            "Agent biết lưu lại tín hiệu đo được.</div>"
        )
    than += khoi_log(
        hypotheses, (kho.get("log") or {}).get(khoa), inc.get("log_evidence")
    )
    phan.append(
        muc(
            so,
            "Tóm tắt" if da_xong else "Bằng chứng",
            "<em>Chuyện gì đã xảy ra</em>" if da_xong else "Agent <em>thấy gì</em>",
            than,
            aside=f'Số liệu lúc {e(kho.get("luc", ""))}',
        )
    )

    # ── 02 · Lập luận
    so += 1
    do_tin = max((float(h.get("confidence") or 0) for h in hypotheses), default=0.0)
    aside_tin = ""
    if hypotheses:
        muc_tin = "cao" if do_tin >= 0.75 else "vừa" if do_tin >= 0.5 else "thấp"
        mau_tin = "ok" if do_tin >= 0.75 else "p2" if do_tin >= 0.5 else "p1"
        aside_tin = (
            f'Độ tin cậy · <span style="color: var(--{mau_tin})">{e(muc_tin)} ({do_tin:.2f})</span>'
        )
    phan.append(
        muc(
            so,
            "Nguyên nhân gốc" if da_xong else "Lập luận",
            "Vì sao <em>chuyện này xảy ra</em>" if da_xong else "Agent <em>nghĩ vì sao</em>",
            khoi_lap_luan(inc, hypotheses),
            aside=aside_tin,
        )
    )

    # ── 03 · Đề xuất / Cách khắc phục
    so += 1
    phan.append(
        muc(
            so,
            "Cách khắc phục" if da_xong else "Đề xuất hành động",
            "<em>Đã làm gì</em>" if da_xong else "Agent <em>muốn làm gì</em>",
            the_de_xuat(inc, inc.get("proposal")),
        )
    )

    # ── 04 · Diễn biến
    so += 1
    phan.append(muc(so, "Diễn biến", "Timeline <em>đầy đủ</em>" if da_xong else "Timeline", khoi_dien_bien(inc)))



    # ── 06 · Ngữ cảnh (chỉ khi có sự cố liên quan)
    lien_quan = khoi_lien_quan(inc, kho.get("bang_tra") or {})
    if lien_quan:
        so += 1
        phan.append(
            muc(
                so,
                "Ngữ cảnh",
                "Sự cố <em>liên quan</em>",
                lien_quan,
                aside="Cùng một nguyên nhân lan sang dịch vụ khác",
                cuoi=True,
            )
        )

    lop_hien = " active" if dang_chon else ""
    return f'<div class="content-inner view{lop_hien}" data-view="{e(khoa)}">{"".join(phan)}</div>'


# ---------------------------------------------------------------------------
# Header · sidebar · trang trống
# ---------------------------------------------------------------------------


def _mttr_hom_nay(ds: list[dict]) -> str:
    """Trung bình thời gian khắc phục của các phiếu ĐÓNG trong ngày hôm nay.

    Chỉ tính phiếu đóng hôm nay theo giờ VN. Không có phiếu nào thì trả `—`:
    lấy trung bình của tập rỗng rồi in `0ph` là nói dối theo hướng đẹp.
    """
    hom_nay = datetime.now(VN_TZ).date()
    khoang: list[float] = []
    for inc in ds:
        moc_dong = _unix(inc.get("resolved_at"))
        moc_mo = _unix(inc.get("detected_at"))
        if moc_dong is None or moc_mo is None:
            continue
        if _gio_vn(moc_dong).date() != hom_nay:
            continue
        khoang.append(moc_dong - moc_mo)
    if not khoang:
        return "—"
    tb = sum(khoang) / len(khoang)
    so, don_vi = fmt_duration_ngan(tb)
    return f"{so}{'ph' if don_vi == 'phút' else 'g' if don_vi == 'giờ' else 'gy'}"


def _trang_thai_agent(health: dict, prom_ok: bool) -> tuple[str, str, str]:
    """`(chấm, câu, tiêu đề tooltip)` cho ô Agent trên header.

    File mẫu ghi "Agent chạy 98.2%". Con số đó **không đo được**: Prometheus chỉ
    scrape hai service demo (`demo/prometheus.yml`), không scrape Agent, và
    `/api/v1/agent/health` chỉ trả boolean chứ không lưu lịch sử uptime. Nên ô
    này hiện đúng cái đo được — thành phần nào đang nối được.

    ⚠️ **Không** đọc khoá `prometheus` trong phản hồi đó để kết luận. Nó là
    Prometheus *của bản API*, mà bản trên Render trỏ `localhost:9090` theo đúng
    thiết kế nên luôn báo không với tới — dùng nó là báo động giả, đúng cái bẫy
    đã ghi trong `src/api/routes.py::agent_health`. Prometheus mà **trang này**
    quan tâm là cái nó tự hỏi được, tức tham số `prom_ok`, và nó chỉ đi vào
    tooltip vì các ô số đã tự nói khi thiếu dữ liệu.
    """
    ghi_chu_prom = (
        "Trang này nối được Prometheus." if prom_ok else "Trang này KHÔNG nối được Prometheus."
    )
    if not health:
        return (
            '<span class="calm-dot" style="background: var(--ink-3)"></span>',
            '<span class="num dim">không hỏi được</span>',
            f"Không gọi được /api/v1/agent/health. {ghi_chu_prom}",
        )
    hong: list[str] = []
    if not (health.get("jira") or {}).get("configured"):
        hong.append("Jira")
    if not (health.get("llm") or {}).get("configured"):
        hong.append("LLM")

    if health.get("ready") and not hong:
        return (
            '<span class="calm-dot"></span>',
            '<span class="num">sẵn sàng</span>',
            f"Agent nối được Jira và LLM. {ghi_chu_prom}",
        )
    if health.get("ready"):
        return (
            '<span class="calm-dot" style="background: var(--p2)"></span>',
            f'<span class="num">thiếu {e(", ".join(hong))}</span>',
            f"Agent chạy được nhưng có thành phần chưa cấu hình. {ghi_chu_prom}",
        )
    return (
        '<span class="calm-dot" style="background: var(--p1)"></span>',
        '<span class="num">chưa sẵn sàng</span>',
        f"Agent chưa cấu hình đủ để chạy. {ghi_chu_prom}",
    )


def header_html(kho: dict, inc_chon: dict) -> str:
    """Thanh trên cùng: đếm sự cố ĐANG XẢY RA theo từng mức.

    Chỉ đếm phiếu còn mở (`DANG_XAY_RA`), không đếm phiếu đã đóng. Trộn cả hai
    vào thì con số chỉ lớn dần theo thời gian và mất hẳn ý nghĩa "ngay lúc này
    có bao nhiêu việc phải lo" — mà đó là câu duy nhất thanh header cần trả lời
    cho người vừa mở trang.
    """
    ds = kho.get("ds") or []
    dang_mo = [i for i in ds if i.get("state") in DANG_XAY_RA]
    dem = {"P1": 0, "P2": 0, "P3": 0, "P4": 0}
    for inc in dang_mo:
        dem[str(inc.get("severity"))] = dem.get(str(inc.get("severity")), 0) + 1

    if dem["P1"]:
        o_p1 = f'<div class="status-item"><span class="pulse-dot"></span>{dem["P1"]} P1 đang mở</div>'
    else:
        o_p1 = '<div class="status-item"><span class="calm-dot"></span>Không có P1 nào đang mở</div>'

    cham_agent, chu_agent, tooltip = _trang_thai_agent(
        kho.get("health") or {}, bool(kho.get("prom"))
    )
    mttr = _mttr_hom_nay(ds)
    lop_mttr = "num" if mttr != "—" else "num dim"

    ma = inc_chon.get("jira_key", "phiếu đang xem")
    co_runbook = (
        ' title="Mở runbook của đề xuất trong phiếu đang xem"'
        if ((inc_chon.get("proposal") or {}).get("runbook"))
        else f' disabled title="Đề xuất của {ma} không kèm runbook"'
    )
    co_postmortem = (
        ' title="Cuộn tới mục bài học của phiếu đang xem"'
        if inc_chon.get("postmortem")
        else f' disabled title="{ma} chưa có postmortem"'
    )

    return (
        '<header class="header">'
        '<div class="brand"><div class="brand-mark">W</div>'
        '<div class="brand-text">War Room <em>/ v2</em></div></div>'
        '<div class="header-center"><div class="status-strip">'
        f"{o_p1}"
        f'<div class="status-item"><span style="color: var(--p2)">◆</span> {dem["P2"]} P2</div>'
        f'<div class="status-item"><span style="color: var(--p3)">◆</span> {dem["P3"]} P3</div>'
        f'<div class="status-item" title="Trung bình thời gian khắc phục của các phiếu đóng trong hôm nay">'
        f'MTTR hôm nay <span class="{lop_mttr}">{e(mttr)}</span></div>'
        f'<div class="status-item" title="{e(tooltip)}">{cham_agent}Agent {chu_agent}</div>'
        "</div></div>"
        '<div class="header-right">'
        # Nút quay về Status Page — nằm trước Runbooks.
        f'<button class="hbtn" type="button" id="btn-status-page" title="Quay về Status Page">'
        f'{ICON["tia"]}Status Page</button>'
        # Hai nút này thao tác lên chính phiếu đang xem, nên phiếu không có
        # runbook/postmortem thì khoá lại kèm lý do. Để bấm được mà không xảy ra
        # gì là kiểu hỏng khó chịu nhất: người dùng tưởng trang treo.
        f'<button class="hbtn" type="button" id="btn-runbook"{co_runbook}>{ICON["sach"]}Runbooks</button>'
        f'<button class="hbtn" type="button" id="btn-postmortem"{co_postmortem}>{ICON["tep"]}Postmortems</button>'
        f'<button class="hbtn primary" type="button" id="btn-reload" title="Tải lại số liệu từ API và Prometheus">{ICON["lam_moi"]}Làm mới</button>'
        '<button class="icon-btn" type="button" id="theme-toggle" aria-label="Đổi theme">'
        f'<span class="icon-moon">{ICON["toi"]}</span><span class="icon-sun">{ICON["trang"]}</span></button>'
        '<div class="avatar" title="War room — trang nội bộ cho người trực">WR</div>'
        "</div></header>"
    )


def the_incident(inc: dict, chuoi: dict | None, dang_chon: bool) -> str:
    """Một thẻ sự cố trong sidebar.

    Dòng phụ dưới tiêu đề đổi nội dung theo trạng thái: phiếu đang chờ duyệt
    hoặc đang thi hành thì hiện **trạng thái**, còn lại hiện **tên dịch vụ**. Lý
    do: hai trạng thái đó là lúc người trực phải hành động, nên chúng phải đọc
    được ngay từ sidebar mà không cần mở phiếu ra.

    Dùng `dict` thô chứ không dùng model Pydantic vì dữ liệu tới thẳng từ JSON
    của API, và sidebar chỉ có vài field — `.get()` với giá trị mặc định chịu
    được phiếu thiếu field, còn validate cả model thì một phiếu lạ làm vỡ cả
    danh sách.
    """
    khoa = inc.get("jira_key", "")
    lop_sev = _lop_severity(inc)
    thoi_luong = (
        fmt_duration(inc["detected_at"], inc.get("resolved_at")) if inc.get("detected_at") else "—"
    )
    dich_vu = " · ".join(labels.service(s) for s in inc.get("affected_services") or [])
    trang_thai = labels.STATE.get(inc.get("state", ""), ("", inc.get("state", "")))[1]
    phu = trang_thai if inc.get("state") in ("Awaiting Approval", "Remediating") else dich_vu

    # Bỏ tiền tố "[P1] ": mức độ đã nằm ngay bên trái bằng chữ serif nghiêng.
    tieu_de = _TIEN_TO_SEV.sub("", str(inc.get("title", "")))

    # Chuỗi cho ô tìm kiếm — gộp sẵn ở đây để JS chỉ phải so một thuộc tính.
    tim = " ".join(
        [khoa, str(inc.get("title", "")), str(inc.get("severity", "")), dich_vu, trang_thai]
    ).lower()

    return (
        f'<div class="incident{" active" if dang_chon else ""}" data-id="{e(khoa)}" '
        f'data-search="{e(tim)}">'
        f'<div class="inc-row1"><span class="inc-sev {lop_sev}">{e(inc.get("severity", ""))}</span>'
        f'<span class="inc-id">{e(khoa)}</span>'
        f'<span class="inc-status-dot {_lop_cham(inc)}"></span></div>'
        f'<div class="inc-title">{e(tieu_de)}</div>'
        f'<div class="inc-meta"><span>{e(thoi_luong)}</span>'
        + (f"<span>·</span><span>{e(phu)}</span>" if phu else "")
        + sparkline(inc, chuoi)
        + "</div></div>"
    )


def sidebar_html(kho: dict, dang_chon: str) -> str:
    """Sidebar hai tab: sự cố đang xảy ra và sự cố đã xong.

    Dựng **cả hai tab một lượt** rồi để CSS ẩn/hiện, thay vì dựng lại khi người
    dùng bấm. Streamlit chạy lại toàn bộ script mỗi lần có tương tác, nên "dựng
    lại khi bấm" ở đây nghĩa là gọi lại API và mất vị trí cuộn — cái giá đắt hơn
    nhiều so với vài KB HTML thừa.
    """
    ds = kho.get("ds") or []
    chuoi = kho.get("chuoi") or {}
    dang_mo = [i for i in ds if i.get("state") in DANG_XAY_RA]
    da_xong = [i for i in ds if i.get("state") not in DANG_XAY_RA]

    def _panel(ten: str, nhom: list[dict], hien: bool) -> str:
        if not nhom:
            than = '<div class="sb-empty">Không có sự cố nào ở mục này.</div>'
        else:
            than = "".join(
                the_incident(i, chuoi.get(i.get("jira_key")), i.get("jira_key") == dang_chon)
                for i in nhom
            )
        return (
            f'<div class="sb-panel{" active" if hien else ""}" data-panel="{ten}">'
            f'{than}<div class="sb-empty" data-khong-khop hidden>Không có phiếu nào khớp.</div></div>'
        )

    khoa_dang_mo = {i.get("jira_key") for i in dang_mo}
    tab_mo = dang_chon in khoa_dang_mo or not da_xong

    return (
        '<aside class="sidebar">'
        '<div class="sb-header"><div class="sb-eyebrow">Bảng theo dõi</div>'
        '<div class="sb-title">Sự cố <em>của hệ thống</em></div></div>'
        '<nav class="sb-tabs">'
        f'<button class="sb-tab{" active" if tab_mo else ""}" type="button" data-tab="active">'
        f'Đang xảy ra <span class="count">{len(dang_mo)}</span></button>'
        f'<button class="sb-tab{"" if tab_mo else " active"}" type="button" data-tab="resolved">'
        f'Đã xử lí <span class="count">{len(da_xong)}</span></button>'
        "</nav>"
        f'<div class="sb-search">{ICON["tim"]}'
        '<input type="text" placeholder="Tìm theo dịch vụ, mã phiếu, mức độ..." />'
        '<span class="kbd">⌘K</span></div>'
        f'<div class="sb-list">{_panel("active", dang_mo, tab_mo)}'
        f'{_panel("resolved", da_xong, not tab_mo)}</div>'
        "</aside>"
    )


def view_trong(kho: dict) -> str:
    """Màn hình khi không có sự cố nào — hoặc khi API không trả được.

    Màn hình trống dễ bị hiểu là hệ thống hỏng hoặc chưa chạy, nên phải nói rõ
    Agent vẫn đang trực và nó đang canh những gì.
    """
    if kho.get("loi"):
        return (
            '<div class="content-inner view active" data-view="__trong__">'
            '<div class="blank"><h2>Không gọi được <em>API</em></h2>'
            f'<div class="note err">{e(kho["loi"])}</div>'
            "<p>Render free tier ngủ sau 15 phút — lần gọi đầu có thể mất khoảng 50 giây. "
            "Nhấn <strong>Làm mới</strong> trên header để thử lại.</p>"
            f'<p class="hint">Đang gọi: <span class="inline-code">{e(API)}</span></p>'
            "</div></div>"
        )
    return (
        '<div class="content-inner view active" data-view="__trong__">'
        '<div class="blank"><h2>Hệ thống <em>đang bình thường</em></h2>'
        "<p>Không có sự cố nào đang diễn ra.</p>"
        "<p><strong>Agent vẫn đang theo dõi liên tục.</strong> Cứ vài giây nó đọc lại số liệu đo "
        "của từng dịch vụ. Khi một chỉ số vượt ngưỡng <strong>và giữ nguyên đủ lâu</strong> để "
        "loại trừ nhiễu, nó sẽ tự mở một phiếu sự cố ở cột bên trái.</p>"
        "<p>Ba thứ nó canh:</p><ul>"
        "<li><strong>Thời gian khách phải chờ</strong> — chậm hơn ngưỡng, hoặc chậm bất thường "
        "so với chính nó lúc bình thường</li>"
        "<li><strong>Tỷ lệ request lỗi</strong></li>"
        "<li><strong>Dịch vụ còn sống không</strong> — chết rồi bật lại liên tục</li>"
        "</ul></div></div>"
    )


# ---------------------------------------------------------------------------
# JS
# ---------------------------------------------------------------------------
#
# Không dùng localStorage: trạng thái giao diện sống trong runtime của trang, và
# đi theo URL của tab cha khi bấm "Làm mới" — nhờ đó tải lại vẫn đứng đúng chỗ.

_JS = """
(function () {
  var root = document.documentElement;
  var content = document.querySelector('.content');

  function viewDangMo() {
    var v = document.querySelector('.view.active');
    return v ? v.dataset.view : '';
  }

  function dongBoUrl() {
    // Ghi lại chỗ đang đứng vào URL của tab cha để nút "Làm mới" quay lại đúng
    // đây. Iframe của Streamlit cùng origin nên chạy được; bọc try cho chắc.
    try {
      var u = new URL(window.parent.location.href);
      u.searchParams.set('key', viewDangMo());
      u.searchParams.set('theme', root.getAttribute('data-theme'));
      window.parent.history.replaceState({}, '', u);
    } catch (err) { /* không đồng bộ được thì thôi, không ảnh hưởng gì */ }
  }

  // ═══ Theme ═══
  document.getElementById('theme-toggle').addEventListener('click', function () {
    root.setAttribute('data-theme', root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
    dongBoUrl();
  });

  // ═══ Tab ═══
  document.querySelectorAll('.sb-tab').forEach(function (tab) {
    tab.addEventListener('click', function () {
      document.querySelectorAll('.sb-tab').forEach(function (t) {
        t.classList.toggle('active', t === tab);
      });
      document.querySelectorAll('.sb-panel').forEach(function (p) {
        p.classList.toggle('active', p.dataset.panel === tab.dataset.tab);
      });
    });
  });

  // ═══ Chọn sự cố ═══
  // Chỉ phiếu đang xem mới được render đầy đủ (xem `tai_chi_tiet()` — tải sẵn
  // cả 34 phiếu mất 18 giây), nên đổi phiếu là tải lại trang kèm `?key=`.
  // Đánh dấu ngay + hiện màn chờ để cái bấm có phản hồi tức thì.
  function chon(key) {
    if (!key || key === viewDangMo()) { return; }
    document.querySelectorAll('.incident').forEach(function (i) {
      i.classList.toggle('active', i.dataset.id === key);
    });
    var man = document.getElementById('man-tai');
    if (man) { man.hidden = false; }
    if (!dieuHuong(key)) { if (man) { man.hidden = true; } }
  }

  // ⚠️ Phải làm đúng hai bước này, đúng thứ tự này.
  //
  // Iframe của Streamlit chạy trong sandbox `allow-forms allow-modals
  // allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts
  // allow-downloads` — **không** có `allow-top-navigation`. Nên gán
  // `window.parent.location.href` ném thẳng `SecurityError` (đo ngày 17/08,
  // đúng lỗi làm nút chọn sự cố bấm không ăn), và `target="_top"` cũng vô hiệu.
  //
  // Nhưng `allow-same-origin` cho phép chạm DOM của trang cha, mà
  // `history.replaceState()` không tính là điều hướng nên vẫn chạy, và
  // `location.reload()` cũng không bị chặn. Ghi query param trước rồi reload là
  // đường duy nhất đi được: trang tải lại và đọc `?key=` mới.
  function dieuHuong(key) {
    try {
      var u = new URL(window.parent.location.href);
      u.searchParams.set('key', key);
      u.searchParams.set('theme', root.getAttribute('data-theme'));
      window.parent.history.replaceState({}, '', u.toString());
      window.parent.location.reload();
      return true;
    } catch (err) {
      return false;
    }
  }

  document.querySelectorAll('.incident').forEach(function (inc) {
    inc.addEventListener('click', function () { chon(inc.dataset.id); });
  });

  // Thẻ "sự cố liên quan" — nhảy sang phiếu khác, đổi luôn tab nếu cần.
  document.querySelectorAll('[data-goto]').forEach(function (el) {
    el.addEventListener('click', function () {
      var key = el.dataset.goto;
      var the = document.querySelector('.incident[data-id="' + key + '"]');
      if (the) {
        var panel = the.closest('.sb-panel');
        document.querySelectorAll('.sb-tab').forEach(function (t) {
          t.classList.toggle('active', t.dataset.tab === panel.dataset.panel);
        });
        document.querySelectorAll('.sb-panel').forEach(function (p) {
          p.classList.toggle('active', p === panel);
        });
        the.scrollIntoView({ block: 'nearest' });
      }
      chon(key);
    });
  });

  // ═══ Tìm kiếm ═══
  var oTim = document.querySelector('.sb-search input');
  if (oTim) {
    oTim.addEventListener('input', function () {
      var tu = oTim.value.trim().toLowerCase();
      document.querySelectorAll('.sb-panel').forEach(function (panel) {
        var con = 0;
        panel.querySelectorAll('.incident').forEach(function (inc) {
          var khop = !tu || (inc.dataset.search || '').indexOf(tu) !== -1;
          inc.hidden = !khop;
          if (khop) { con++; }
        });
        var bao = panel.querySelector('[data-khong-khop]');
        if (bao) { bao.hidden = !(tu && con === 0); }
      });
    });
    document.addEventListener('keydown', function (ev) {
      if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === 'k') {
        ev.preventDefault();
        oTim.focus();
        oTim.select();
      }
    });
  }

  // ═══ Sao chép ═══
  // navigator.clipboard không dùng được trong iframe sandbox, nên chép bằng
  // textarea tạm — cách này chạy ở mọi trình duyệt đang nhắm tới.
  document.querySelectorAll('.code-copy').forEach(function (nut) {
    nut.addEventListener('click', function () {
      var o = document.createElement('textarea');
      o.value = decodeURIComponent(nut.dataset.copy || '');
      o.style.position = 'fixed';
      o.style.opacity = '0';
      document.body.appendChild(o);
      o.select();
      var nhan = nut.querySelector('span');
      try {
        document.execCommand('copy');
        var cu = nhan.textContent;
        nhan.textContent = 'Đã chép';
        setTimeout(function () { nhan.textContent = cu; }, 1400);
      } catch (err) {
        nhan.textContent = 'Chép thủ công';
      }
      document.body.removeChild(o);
    });
  });

  // ═══ Nút header ═══
  // Hai nút này đã bị `disabled` sẵn từ Python khi phiếu đang xem không có mục
  // tương ứng, nên ở đây không cần đường lùi "không tìm thấy thì thôi".
  document.getElementById('btn-runbook').addEventListener('click', function () {
    var rb = document.querySelector('.view.active [data-runbook]');
    if (rb) { rb.open = true; rb.scrollIntoView({ block: 'center' }); }
  });
  document.getElementById('btn-postmortem').addEventListener('click', function () {
    var muc = document.querySelectorAll('.view.active .section');
    for (var i = 0; i < muc.length; i++) {
      if (muc[i].querySelector('.checklist')) {
        muc[i].scrollIntoView({ block: 'start' });
        return;
      }
    }
  });
  document.getElementById('btn-reload').addEventListener('click', function () {
    var man = document.getElementById('man-tai');
    if (man) { man.hidden = false; }
    if (!dieuHuong(viewDangMo())) { if (man) { man.hidden = true; } }
  });

  // ═══ Nút quay về Status Page ═══
  document.getElementById('btn-status-page').addEventListener('click', function () {
    try {
      var u = new URL(window.parent.location.href);
      // Xoá path /war_room, giữ lại origin để quay về trang gốc (status_page)
      var idx = u.pathname.indexOf('/war_room');
      if (idx !== -1) u.pathname = u.pathname.substring(0, idx) + '/';
      u.search = '';
      window.parent.history.replaceState({}, '', u.toString());
      window.parent.location.reload();
    } catch (err) {
      // Fallback: mở trong cùng tab
      window.open('/', '_top');
    }
  });
})();
"""


# ---------------------------------------------------------------------------
# Trang
# ---------------------------------------------------------------------------

# `set_page_config` phải chạy trước mọi lệnh Streamlit khác.
st.set_page_config(page_title="War room", page_icon="P035", layout="wide")
st.markdown(_CSS_KHUNG, unsafe_allow_html=True)


def _tham_so(ten: str, mac_dinh: str = "") -> str:
    """Đọc query param của tab cha. Chạy ngoài `streamlit run` thì trả mặc định."""
    try:
        gia_tri = st.query_params.get(ten)
    except Exception:  # noqa: BLE001 — bare mode không có script run context
        return mac_dinh
    return str(gia_tri) if gia_tri else mac_dinh


kho = tai_danh_sach()
ds = kho.get("ds") or []

# Sự cố mở sẵn: theo URL nếu còn tồn tại, không thì ưu tiên phiếu đang chờ
# người duyệt — đó là phiếu duy nhất đang chờ một hành động của con người.
khoa_hop_le = {i.get("jira_key") for i in ds}
dang_chon = _tham_so("key")
if dang_chon not in khoa_hop_le:
    cho_duyet = next((i for i in ds if i.get("state") == "Awaiting Approval"), None)
    dang_mo = next((i for i in ds if i.get("state") in DANG_XAY_RA), None)
    # KHÔNG rơi về `ds[0]` khi mọi sự cố đã đóng.
    #
    # `ds[0]` là phiếu gần nhất KỂ CẢ đã Resolved, nên trang mở ra tự mâu thuẫn:
    # cột trái ghi "không có sự cố nào đang diễn ra" trong khi khung chính dựng
    # nguyên một phiếu P1 màu đỏ. Ai nhìn vào cũng đọc cái to màu đỏ trước.
    #
    # Đây là màn hình MỞ ĐẦU buổi demo, lúc board đã dọn sạch — nên nó phải nói
    # đúng một điều, và `view_trong()` đã viết sẵn điều đó: hệ thống bình thường,
    # Agent vẫn đang trực, và nó canh ba thứ gì.
    #
    # Đã vá lần đầu ngày 12/08, mất khi dựng lại UI ngày 17/08. Có test khoá lại
    # ở `tests/test_ui_import.py` để không mất lần thứ ba.
    dau_tien = cho_duyet or dang_mo
    dang_chon = dau_tien.get("jira_key", "") if dau_tien else ""

theme = _tham_so("theme", "dark")
if theme not in ("dark", "light"):
    theme = "dark"

# Chỉ phiếu đang xem mới cần chi tiết — xem `tai_chi_tiet()` để biết vì sao
# không tải sẵn tất cả. Chi tiết lỗi thì vẫn dựng được view từ bản rút gọn
# trong danh sách, chỉ ít mục hơn.
rut_gon = next((i for i in ds if i.get("jira_key") == dang_chon), None)
inc_chon = tai_chi_tiet(dang_chon) or rut_gon or {}

kho["prom"] = prom_song_cached()
kho["chuoi"] = {}
kho["anh_huong"] = {}
kho["log"] = {}
# Thẻ "sự cố liên quan" tra bằng bản rút gọn trong danh sách — đủ mã, mức độ,
# tiêu đề, trạng thái. Không gọi thêm API cho từng phiếu liên quan.
kho["bang_tra"] = {i["jira_key"]: i for i in ds if i.get("jira_key")}
if inc_chon:
    # Chỉ phiếu ĐANG XEM, cùng lý do với `tai_chi_tiet()`: mỗi lời gọi là một
    # lượt `docker logs` trên máy chạy API, nhân 34 phiếu là không dùng được.
    kho["log"][dang_chon] = tai_log(dang_chon)

    signal_chon = inc_chon.get("signal") or {}
    if signal_chon:
        # Hỏi tại MỐC PHÁT HIỆN, không phải "bây giờ". Sự cố đã qua thì cửa sổ
        # `[5m]` tính từ hiện tại chỉ chứa khoảng sau khi tải đã tắt, và ô "Ảnh
        # hưởng" trống — dòng quan trọng nhất với người không rành kỹ thuật.
        kho["anh_huong"][dang_chon] = ty_le_anh_huong(
            signal_chon, kho["prom"], _unix(inc_chon.get("detected_at"))
        )
        if kho["prom"]:
            bang_chung_chon = _bang_chung_kich_hoat(signal_chon) or {}
            bat_dau_cs, ket_thuc_cs = _cua_so(inc_chon)
            kho["chuoi"][dang_chon] = tai_chuoi(
                dang_chon, str(bang_chung_chon.get("promql", "")), bat_dau_cs, ket_thuc_cs
            )

if ds and inc_chon:
    views = view_su_co(inc_chon, kho, True)
else:
    views = view_trong(kho)

TRANG = f"""<!DOCTYPE html>
<html lang="vi" data-theme="{theme}">
<head>
<meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,300;1,6..72,400&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{_CSS}</style>
</head>
<body>
<div class="app">
{header_html(kho, inc_chon)}
<div class="main-grid">
{sidebar_html(kho, dang_chon)}
<main class="content">
{views}
</main>
</div>
<div class="dang-tai" id="man-tai" hidden><div class="hop"><span class="cham"></span>Đang tải chi tiết phiếu</div></div>
</div>
<script>{_JS}</script>
</body>
</html>
"""

# `st.iframe` thay `st.components.v1.html` từ Streamlit 1.57; bản cũ chưa có, mà
# `ui/requirements.txt` cố ý không ghim version (xem test_ui_import.py) — nên giữ
# cả hai đường. `height="stretch"` để iframe tự cao bằng khung chứa; CSS ở
# `_CSS_KHUNG` vẫn ép 100vh phòng khi khung chứa chưa kịp có chiều cao.
if hasattr(st, "iframe"):
    st.iframe(TRANG, height="stretch")
else:
    components.html(TRANG, height=900, scrolling=False)
