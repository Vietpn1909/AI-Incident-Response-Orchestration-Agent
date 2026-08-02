"""War-room view — trang nội bộ cho on-call/IC theo dõi và xử lý incident.

CHỦ SỞ HỮU: Long

Làm SAU status_page.py. Chạy:
    streamlit run ui/war_room.py
"""

import os
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st

API = os.getenv("API_URL", "https://p-035-incident-agent.onrender.com")

SEVERITY_COLOR = {"P1": "🔴", "P2": "🟠", "P3": "🟡", "P4": "⚪"}

VN_TZ = timezone(timedelta(hours=7))  # Việt Nam không có DST, luôn UTC+7


def fmt_time_vn(iso: str) -> str:
    """Định dạng một chuỗi ISO 8601 (UTC) sang giờ Việt Nam, kiểu vi-VN."""
    dt = datetime.fromisoformat(iso).astimezone(VN_TZ)
    return dt.strftime("%H:%M:%S %d/%m/%Y")


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


only_open = st.checkbox("Chỉ hiện đang mở")

try:
    incidents = load_incidents(only_open=only_open)
except requests.RequestException as error:
    st.error(f"Không gọi được API: {error}")
    st.stop()

incidents = sorted(incidents, key=lambda i: i["detected_at"], reverse=True)

if "selected_key" not in st.session_state:
    awaiting = next((i for i in incidents if i["state"] == "Awaiting Approval"), None)
    default = awaiting or (incidents[0] if incidents else None)
    st.session_state["selected_key"] = default["jira_key"] if default else None

col_list, col_detail = st.columns([1, 2])

with col_list:
    if not incidents:
        st.info("Không có incident nào.")
    for inc in incidents:
        awaiting = inc["state"] == "Awaiting Approval"
        is_selected = inc["jira_key"] == st.session_state["selected_key"]
        with st.container(border=True):
            icon = SEVERITY_COLOR.get(inc["severity"], "⚪")
            st.markdown(f"{icon} **{inc['severity']}** · **{inc['jira_key']}** — {inc['state']}")
            st.write(inc["title"])
            st.caption(f"Phát hiện lúc {fmt_time_vn(inc['detected_at'])}")
            if awaiting:
                st.error("⏸ **ĐANG CHỜ DUYỆT**")
            if st.button(
                "📂 Đang xem" if is_selected else "Chọn xem",
                key=f"sel-{inc['jira_key']}",
                type="primary" if is_selected else "secondary",
                use_container_width=True,
            ):
                st.session_state["selected_key"] = inc["jira_key"]
                st.rerun()

with col_detail:
    selected_key = st.session_state["selected_key"]
    if not selected_key:
        st.info("Chọn một incident bên trái để xem chi tiết.")
    else:
        try:
            incident = load_incident(selected_key)
        except requests.RequestException as error:
            st.error(f"Không gọi được API: {error}")
            incident = None

        if incident:
            sev_icon = SEVERITY_COLOR.get(incident["severity"], "⚪")
            st.subheader(f"{sev_icon} {incident['jira_key']} — {incident['severity']} · {incident['state']}")
            st.write(incident["title"])
            st.caption(
                f"Dịch vụ ảnh hưởng: {', '.join(incident['affected_services'])} · "
                f"Phát hiện {fmt_time_vn(incident['detected_at'])}"
                + (f" · Đã xử lý {fmt_time_vn(incident['resolved_at'])}" if incident.get("resolved_at") else "")
            )
            if incident["state"] == "Awaiting Approval":
                st.error("⏸ **ĐANG CHỜ DUYỆT** — cần người duyệt trước khi Agent thực thi đề xuất bên dưới")

            # 1. Tín hiệu phát hiện — bằng chứng gốc trước khi có giả thuyết.
            st.markdown("#### 🔎 Tín hiệu phát hiện")
            signal = incident.get("signal")
            if signal:
                with st.container(border=True):
                    st.write(f"**{signal['metric_name']}**: {signal['metric_value']} (ngưỡng {signal['threshold']})")
                    st.caption(f"Vượt ngưỡng liên tục {signal['breached_for_seconds']:.0f}s")
                    for ev in signal.get("evidence", []):
                        unit = ev.get("unit", "")
                        st.write(f"- {ev['name']}: {ev['value']}{unit} (baseline {ev.get('baseline')}{unit})")
                        if ev.get("promql"):
                            st.code(ev["promql"])
            else:
                st.caption("Chưa có tín hiệu gốc.")

            # 2. Giả thuyết nguyên nhân — kèm bằng chứng, theo yêu cầu đề bài.
            st.markdown("#### 🧠 Giả thuyết nguyên nhân")
            hypotheses = incident.get("hypotheses") or []
            if hypotheses:
                for h in hypotheses:
                    with st.container(border=True):
                        st.write(h["statement"])
                        st.progress(h["confidence"], text=f"{h['confidence'] * 100:.0f}% tin cậy")
                        if h.get("reasoning"):
                            st.caption(h["reasoning"])
                        evidence = h.get("evidence") or []
                        if evidence:
                            st.markdown("**Bằng chứng:**")
                            for ev in evidence:
                                unit = ev.get("unit", "")
                                st.write(f"- {ev['name']}: {ev['value']}{unit} (baseline {ev.get('baseline')}{unit})")
                                if ev.get("promql"):
                                    st.code(ev["promql"])
                        deploy = h.get("related_deploy")
                        if deploy:
                            st.caption(
                                f"🚀 Deploy liên quan: `{deploy['version']}` ({deploy['commit_sha']}) "
                                f"lúc {fmt_time_vn(deploy['deployed_at'])} bởi {deploy['deployed_by']}"
                            )
            else:
                st.caption("Chưa có giả thuyết.")

            # 3. Đề xuất khắc phục — luôn qua HITL trước khi thực thi.
            st.markdown("#### 🛠️ Đề xuất khắc phục")
            proposal = incident.get("proposal")
            if proposal:
                with st.container(border=True):
                    st.write(f"**Hành động:** {proposal['action']} → `{proposal['target']}`")
                    if proposal.get("runbook"):
                        st.write(f"**Runbook:** {proposal['runbook']}")
                    if proposal.get("risk"):
                        st.warning(f"**Rủi ro:** {proposal['risk']}")
                    if proposal.get("requires_approval"):
                        st.error("✅ Bắt buộc — Agent không tự thực thi")
                    else:
                        st.caption("Không cần duyệt")
            else:
                st.caption("Chưa có đề xuất khắc phục.")

            # 4. Timeline.
            st.markdown("#### 🕒 Timeline")
            timeline = incident.get("timeline") or []
            if timeline:
                for t in sorted(timeline, key=lambda t: t["at"]):
                    st.write(f"`{fmt_time_vn(t['at'])}` **[{t['actor']}]** {t['action']} — {t.get('detail', '')}")
            else:
                st.caption("Chưa có timeline.")

            # 5. Postmortem, nếu incident đã Resolved.
            postmortem = incident.get("postmortem")
            if postmortem:
                st.markdown("#### 📋 Postmortem")
                with st.container(border=True):
                    st.write(f"**Tóm tắt:** {postmortem['summary']}")
                    st.write(f"**Nguyên nhân gốc:** {postmortem['root_cause']}")
                    st.write(f"**Tác động:** {postmortem['impact']}")
                    if postmortem.get("actions_taken"):
                        st.markdown("**Đã xử lý:**")
                        for a in postmortem["actions_taken"]:
                            st.write(f"- {a}")
                    if postmortem.get("action_items"):
                        st.markdown("**Action item:**")
                        for item in postmortem["action_items"]:
                            st.write(f"- {item['title']} — {item.get('owner', '')} ({item.get('jira_key', '')})")

            # 6. Incident liên quan — dấu hiệu lan truyền.
            related = incident.get("related_incidents") or []
            if related:
                st.markdown("#### 🔗 Incident liên quan")
                for col, key in zip(st.columns(len(related)), related):
                    with col:
                        if st.button(key, key=f"related-{key}", use_container_width=True):
                            st.session_state["selected_key"] = key
                            st.rerun()

with st.expander("Dữ liệu API trả về (để tham khảo khi code)"):
    st.json(incidents)
