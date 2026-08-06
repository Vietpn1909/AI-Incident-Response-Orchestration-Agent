"""Status page công khai — trang người dùng dịch vụ xem để biết có sự cố không.

CHỦ SỞ HỮU: Long

Chạy:
    streamlit run ui/status_page.py

Dữ liệu đã có sẵn, không cần chờ Agent hay Jira. Xem ui/README.md.
"""

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

VN_TZ = timezone(timedelta(hours=7))  # Việt Nam không có DST, luôn UTC+7


def fmt_time_vn(iso: str) -> str:
    """Định dạng một chuỗi ISO 8601 (UTC) sang giờ Việt Nam, kiểu vi-VN."""
    dt = datetime.fromisoformat(iso).astimezone(VN_TZ)
    return dt.strftime("%H:%M:%S %d/%m/%Y")


st.set_page_config(page_title="Trạng thái dịch vụ", page_icon="🟢")
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


try:
    data = load_status()
except requests.RequestException as error:
    st.error(f"Không gọi được API: {error}")
    st.caption("Render free tier ngủ sau 15 phút — lần gọi đầu có thể mất ~50 giây. Thử tải lại trang.")
    st.stop()

services = data["services"]
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

for svc in services:
    icon, label = labels.health(svc["health"])
    with st.container(border=True):
        # Tên dịch vụ dễ hiểu dẫn đường, tên kỹ thuật ở dòng dưới cho người trực
        # — cùng nguyên tắc "dịch THÊM, không dịch THAY" như war_room.
        st.write(f"{icon} **{labels.service(svc['name'])}** — {label}")
        st.caption(f"↳ `{svc['name']}`")
        st.write(svc["message"])
        if svc["active_incident"]:
            st.caption(f"Mã sự cố đang xử lý: `{svc['active_incident']}`")

st.caption(f"Cập nhật lúc {fmt_time_vn(data['updated_at'])}")

if st.button("🔄 Tải lại"):
    load_status.clear()
    st.rerun()

# Giữ lại nhưng gấp và đặt tên rõ là dành cho người trực. Đây là trang công
# khai nên "để tham khảo khi code" đọc ra như trang chưa làm xong.
with st.expander("Dữ liệu thô (dành cho người trực)"):
    st.json(data)
