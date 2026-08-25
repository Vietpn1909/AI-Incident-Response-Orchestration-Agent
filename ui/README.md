# `ui/` — Giao diện

**Chủ sở hữu: Long**

Hai trang Streamlit — **chỉ cần deploy một lệnh** nhờ Streamlit multi-page.

| File | Vai trò | Ai xem |
|---|---|---|
| `status_page.py` | Status page công khai (trang chính) | Người dùng dịch vụ — không cần đăng nhập |
| `pages/war_room.py` | War-room view nội bộ (tự động phục vụ tại `/war_room`) | On-call / IC |
| `labels.py` | Bảng dịch thuật ngữ kỹ thuật sang tiếng Việt | — |
| `theme.py` | Design token, icon, mảnh CSS dùng chung | — |

## Hai trang dựng thế nào

Từ 17/08, cả hai trang **dựng nguyên một khối HTML/CSS/JS trong Python** rồi
nhúng bằng `st.iframe`, chứ không ghép bằng widget Streamlit nữa. Lý do và các
hệ quả phải biết trước khi sửa nằm trong docstring đầu mỗi file — đọc trước khi
đụng vào, nhất là phần nói về sandbox của iframe và về việc tải chi tiết phiếu.

Sửa màu, font, nút, pill thì sửa ở [theme.py](theme.py) — sửa ở một trang là hai
trang lệch nhau, mà lệch màu thì không có test nào bắt được.

## Chạy

```bash
pip install -r ui/requirements.txt
streamlit run ui/status_page.py        # mở ở localhost:8501
# War room tự có tại localhost:8501/war_room (Streamlit multi-page)
```

Khi dịch vụ có sự cố, thẻ dịch vụ trên status page hiện nút **"Xem chi tiết sự cố"** —
nhấn vào là chuyển thẳng sang war room với đúng incident đó.

## Dữ liệu đã có sẵn — không cần chờ ai

Backend đã deploy và trả dữ liệu thật. Long **không cần** chạy backend local, cũng **không cần** hiểu Agent hay Jira:

```
https://p-035-incident-agent.onrender.com
```

| Endpoint | Trả về |
|---|---|
| `GET /api/status` | 4 service + trạng thái → cho `status_page.py` |
| `GET /api/incidents` | Danh sách incident → cho `war_room.py` |
| `GET /api/incidents/INC-12` | Chi tiết 1 incident: giả thuyết, bằng chứng, timeline |
| `GET /api/incidents/INC-12/logs` | Log thô đọc TƯƠI từ container theo cửa sổ sự cố → khối "Log gốc" trong war room. ⚠️ Chỉ có dữ liệu khi API chạy trên máy có demo stack; bản Render không có Docker nên luôn trả rỗng kèm `ly_do` |

Xem trước JSON trước khi code:

```bash
curl https://p-035-incident-agent.onrender.com/api/status
```

Hoặc mở https://p-035-incident-agent.onrender.com/docs rồi bấm **Try it out**.

⚠️ Render free tier **ngủ sau 15 phút** không có request. Lần gọi đầu sau đó mất ~50 giây. Gọi `/health` một lần cho service tỉnh trước khi làm việc.

Hình dạng JSON là [contract ④](../docs/contracts/README.md) — sẽ **không đổi** khi backend chuyển từ dữ liệu mẫu sang dữ liệu Jira thật, nên UI làm xong bây giờ không phải sửa lại.

## Thứ tự làm

**1. `status_page.py` trước** — đơn giản nhất, có ngay kết quả nhìn thấy được. Chỉ cần đọc `/api/status` và hiện 4 service với màu.

**2. `war_room.py` sau** — danh sách incident + chi tiết.

Gợi ý cho war-room: incident có `state == "Awaiting Approval"` nên làm **nổi bật rõ**, vì đó là lúc đang chờ người xử lý. Đây cũng là điểm người chấm sẽ để ý — nó thể hiện cơ chế HITL bằng mắt.

## Việc riêng của Long: video + pitch deck

Deliverable #6 và #7. Bắt đầu nghĩ từ giờ, đừng để tuần cuối.

Kịch bản demo đã có sẵn dạng sơ đồ 22 bước ở [docs/architecture_diagram.md](../docs/architecture_diagram.md) mục 3 — dùng luôn làm storyboard.

Xuất sơ đồ ra PNG cho slide:

```bash
npx -y -p @mermaid-js/mermaid-cli mmdc -i docs/architecture_diagram.md -o out.md -e png -w 2200
```
