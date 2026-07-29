"""War-room view — trang nội bộ cho on-call/IC theo dõi và xử lý incident.

CHỦ SỞ HỮU: Long

Làm SAU status_page.py. Chạy:
    streamlit run ui/war_room.py
"""

import os

import requests
import streamlit as st

API = os.getenv("API_URL", "https://p-035-incident-agent.onrender.com")

SEVERITY_COLOR = {"P1": "🔴", "P2": "🟠", "P3": "🟡", "P4": "⚪"}

st.set_page_config(page_title="War room", page_icon="🚨", layout="wide")
st.title("War room — danh sách sự cố")


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
    incidents = load_incidents()
except requests.RequestException as error:
    st.error(f"Không gọi được API: {error}")
    st.stop()

# TODO(Long):
#   1. Checkbox "Chỉ hiện đang mở" → gọi load_incidents(only_open=True)
#
#   2. Danh sách incident. Mỗi dòng hiện: severity (dùng SEVERITY_COLOR),
#      jira_key, title, state, detected_at.
#
#      ⚠️ Incident có state == "Awaiting Approval" phải LÀM NỔI BẬT RÕ
#      (viền đỏ, chữ "⏸ ĐANG CHỜ DUYỆT", hoặc st.error). Đây là lúc đang chờ
#      người xử lý — và cũng là điểm người chấm để ý nhất, vì nó thể hiện cơ
#      chế HITL bằng mắt.
#
#   3. Chọn một incident → gọi load_incident(key) và hiện chi tiết:
#      - Giả thuyết nguyên nhân: incident["hypotheses"] — mỗi cái có
#        `statement`, `confidence`, và `evidence` (danh sách số liệu).
#        Hiện cả evidence, vì "chẩn đoán có bằng chứng" là yêu cầu của đề bài.
#      - Đề xuất khắc phục: incident["proposal"] — action, target, runbook, risk
#      - Timeline: incident["timeline"] — mỗi mốc có at, actor, action, detail
#      - Postmortem nếu có: incident["postmortem"]
#      - Incident liên quan: incident["related_incidents"] (dấu hiệu lan truyền)
#
#   Gợi ý layout: st.columns([1, 2]) — cột trái danh sách, cột phải chi tiết.
#
# Dữ liệu mẫu có sẵn để test: INC-12 (đang chờ duyệt, có giả thuyết + đề xuất),
# INC-13 (lan truyền, link với INC-12), INC-9 (đã xong, có postmortem đầy đủ).

st.warning("TODO(Long): chưa hiển thị — xem TODO trong file này")

with st.expander("Dữ liệu API trả về (để tham khảo khi code)"):
    st.json(incidents)
