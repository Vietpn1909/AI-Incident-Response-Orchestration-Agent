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
"""

import os
import pathlib
import sys
import urllib.parse
from datetime import UTC, datetime, timedelta, timezone

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

VN_TZ = timezone(timedelta(hours=7))  # Việt Nam không có DST, luôn UTC+7

#: Trạng thái nghĩa là sự cố còn đang diễn ra.
DANG_XAY_RA = ("Open", "Investigating", "Awaiting Approval", "Remediating")


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
        if dong.promql:
            with st.expander("PromQL để kiểm chứng lại", expanded=False):
                st.code(dong.promql, language="promql")
                link = link_prometheus(dong.promql, luc_phat_hien)
                if link:
                    st.markdown(f"[▶ Mở Prometheus và chạy câu này tại lúc xảy ra sự cố]({link})")
                    st.caption(
                        "Câu này đo **tại thời điểm hỏi**. Bấm link để hỏi đúng lúc sự cố "
                        "— dán tay vào Prometheus sau khi sự cố qua sẽ ra rỗng, không phải "
                        "vì số liệu sai mà vì đang hỏi nhầm thời điểm."
                    )


st.set_page_config(page_title="War room", page_icon="🚨", layout="wide")
st.title("🚨 War Room — sự cố đang xảy ra")

st.markdown(
    """
**Trang này theo dõi sự cố của hệ thống.**
AI tự phát hiện sự cố từ số liệu đo được, tìm nguyên nhân **kèm bằng chứng**,
rồi đề xuất cách sửa. **Nó không tự sửa** — mọi hành động ảnh hưởng hệ thống
thật đều phải có người duyệt.
"""
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


def the_incident(inc: dict) -> None:
    """Một thẻ trong danh sách bên trái."""
    is_selected = inc["jira_key"] == st.session_state["selected_key"]
    with st.container(border=True):
        st.markdown(f"{labels.severity(inc['severity'])}")
        st.markdown(f"**{inc['jira_key']}** · {labels.state(inc['state'])}")
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


col_list, col_detail = st.columns([1, 2])

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

            # ── Đầu trang: hậu quả với người dùng trước, số liệu sau.
            with st.container(border=True):
                # Sự cố ĐÃ ĐÓNG thì trạng thái phải đứng trước mức nghiêm trọng.
                #
                # Bản cũ luôn dựng "🔴 Nghiêm trọng — nhiều khách hàng bị ảnh
                # hưởng (P1)" ở dòng to nhất, kể cả khi sự cố đã xử lý xong từ
                # lâu. Người xem đọc dòng to màu đỏ trước rồi mới thấy dòng "Đã
                # xử lý xong" nhỏ hơn bên dưới — tức hiểu ngược trong khoảng một
                # hai giây, đủ để hoảng.
                da_xong_roi = bool(incident.get("resolved_at"))
                if da_xong_roi:
                    st.subheader(f"{labels.state(incident['state'])} · {incident['jira_key']}")
                    st.caption(f"Mức lúc xảy ra: {labels.severity(incident['severity'])}")
                else:
                    st.subheader(f"{labels.severity(incident['severity'])}")
                    st.markdown(f"### {incident['jira_key']} · {labels.state(incident['state'])}")
                st.write(incident["title"])
                st.caption(
                    f"Dịch vụ ảnh hưởng: {', '.join(incident['affected_services'])} · "
                    f"Phát hiện {fmt_time_vn(incident['detected_at'])}"
                    + (
                        f" · Đã xử lý {fmt_time_vn(incident['resolved_at'])}"
                        if incident.get("resolved_at")
                        else ""
                    )
                )
                if incident.get("resolved_at"):
                    st.caption(f"Đã kéo dài {fmt_duration(incident['detected_at'], incident['resolved_at'])}")
                else:
                    st.caption(f"Đang kéo dài {fmt_duration(incident['detected_at'])}")

            if incident["state"] == "Awaiting Approval":
                st.error(
                    "### ⏸ ĐANG CHỜ NGƯỜI DUYỆT\n\n"
                    "AI đã chẩn đoán xong và đề xuất cách sửa bên dưới, nhưng **nó không tự "
                    "thực hiện**. Cần một người xem xét rồi bấm duyệt trên Jira."
                )

            # ── ① Tín hiệu phát hiện: bằng chứng gốc, trước mọi suy luận.
            st.markdown("### ① AI thấy gì")
            if signal:
                with st.container(border=True):
                    cau, _ = labels.metric(signal["metric_name"])
                    st.markdown(f"**Chỉ số kích hoạt:** {cau}")
                    st.caption(f"↳ `{signal['metric_name']} = {signal['metric_value']:g}` (ngưỡng {signal['threshold']:g})")
                    st.info(f"⏱ Đã kéo dài {labels.keo_dai(signal['breached_for_seconds'])}")
                    ve_bang_chung(signal.get("evidence", []), incident["detected_at"])
            else:
                st.caption("Chưa có tín hiệu gốc — sự cố này tạo trước khi Agent lưu lại tín hiệu.")

            # ── ② Giả thuyết: chỗ phân biệt TRIỆU CHỨNG với NGUYÊN NHÂN.
            st.markdown("### ② AI nghĩ vì sao")
            hypotheses = incident.get("hypotheses") or []
            if hypotheses:
                for h in hypotheses:
                    with st.container(border=True):
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
            st.markdown("### ③ AI đề xuất làm gì")
            proposal = incident.get("proposal")
            if proposal:
                with st.container(border=True):
                    st.markdown(f"**{labels.action(proposal['action'])}** → `{proposal['target']}`")
                    if proposal.get("params"):
                        st.caption(f"↳ tham số: `{proposal['params']}`")
                    if proposal.get("risk"):
                        st.warning(f"⚠️ **Đánh đổi cần cân nhắc:** {proposal['risk']}")
                    if proposal.get("runbook"):
                        with st.expander("Các bước thực hiện và cách kiểm đã hết chưa"):
                            st.markdown(proposal["runbook"])
                    if proposal.get("requires_approval"):
                        st.error("✅ **Bắt buộc có người duyệt** — AI không tự thực hiện")
                    else:
                        st.caption("Không cần duyệt")
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
