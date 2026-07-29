"""Status page công khai — trang người dùng dịch vụ xem để biết có sự cố không.

CHỦ SỞ HỮU: Long

Chạy:
    streamlit run ui/status_page.py

Dữ liệu đã có sẵn, không cần chờ Agent hay Jira. Xem ui/README.md.
"""

import os

import requests
import streamlit as st

API = os.getenv("API_URL", "https://p-035-incident-agent.onrender.com")

# Ánh xạ trạng thái sang cách hiển thị. `health` là một trong 4 giá trị này —
# contract ④, sẽ không đổi.
HEALTH_DISPLAY = {
    "operational": ("🟢", "Hoạt động bình thường"),
    "degraded": ("🟡", "Suy giảm hiệu năng"),
    "down": ("🔴", "Đang gặp sự cố"),
    "maintenance": ("🔧", "Đang bảo trì"),
}

st.set_page_config(page_title="Trạng thái dịch vụ", page_icon="🟢")
st.title("Trạng thái dịch vụ")


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

# TODO(Long):
#   1. Hiện trạng thái TỔNG ở trên cùng (một dòng lớn, dễ thấy):
#      - nếu có service nào `down`   → 🔴 "Một số dịch vụ đang gặp sự cố"
#      - nếu có service nào `degraded` → 🟡 "Một số dịch vụ suy giảm"
#      - còn lại                     → 🟢 "Tất cả dịch vụ hoạt động bình thường"
#
#   2. Liệt kê từng service trong data["services"]:
#      for svc in data["services"]:
#          icon, label = HEALTH_DISPLAY[svc["health"]]
#          st.write(f"{icon} **{svc['name']}** — {svc['message']}")
#
#   3. Hiện data["updated_at"] ở cuối, dạng "Cập nhật lúc ...".
#
#   4. Thêm st.button("Tải lại") gọi load_status.clear() rồi st.rerun().
#
# Xong là thế nào: mở được trang, thấy 2 service với màu đúng theo `health`.

st.warning("TODO(Long): chưa hiển thị — xem TODO trong file này")

with st.expander("Dữ liệu API trả về (để tham khảo khi code)"):
    st.json(data)
