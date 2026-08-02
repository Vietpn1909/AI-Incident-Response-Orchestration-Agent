# `ui/` — Giao diện

**Chủ sở hữu: Long**

Hai trang Streamlit. Python thuần, không cần React, không cần biết JavaScript.

| File | Trang | Ai xem |
|---|---|---|
| `status_page.py` | Status page công khai | Người dùng dịch vụ — không cần đăng nhập |
| `war_room.py` | War-room view nội bộ | On-call / IC |

## Chạy

```bash
pip install -r ui/requirements.txt
streamlit run ui/status_page.py        # mở ở localhost:8501
streamlit run ui/war_room.py
```

## Dữ liệu đã có sẵn — không cần chờ ai

Backend đã deploy và trả dữ liệu thật. Long **không cần** chạy backend local, cũng **không cần** hiểu Agent hay Jira:

```
https://p-035-incident-agent.onrender.com
```

| Endpoint | Trả về |
|---|---|
| `GET /api/status` | 2 service + trạng thái → cho `status_page.py` |
| `GET /api/incidents` | Danh sách incident → cho `war_room.py` |
| `GET /api/incidents/INC-12` | Chi tiết 1 incident: giả thuyết, bằng chứng, timeline |

Xem trước JSON trước khi code:

```bash
curl https://p-035-incident-agent.onrender.com/api/status
```

Hoặc mở https://p-035-incident-agent.onrender.com/docs rồi bấm **Try it out**.

⚠️ Render free tier **ngủ sau 15 phút** không có request. Lần gọi đầu sau đó mất ~50 giây. Gọi `/health` một lần cho service tỉnh trước khi làm việc.

Hình dạng JSON là [contract ④](../docs/contracts/README.md) — sẽ **không đổi** khi backend chuyển từ dữ liệu mẫu sang dữ liệu Jira thật, nên UI làm xong bây giờ không phải sửa lại.

## Thứ tự làm

**1. `status_page.py` trước** — đơn giản nhất, có ngay kết quả nhìn thấy được. Chỉ cần đọc `/api/status` và hiện 2 service với màu.

**2. `war_room.py` sau** — danh sách incident + chi tiết.

Gợi ý cho war-room: incident có `state == "Awaiting Approval"` nên làm **nổi bật rõ**, vì đó là lúc đang chờ người xử lý. Đây cũng là điểm người chấm sẽ để ý — nó thể hiện cơ chế HITL bằng mắt.

## Việc riêng của Long: video + pitch deck

Deliverable #6 và #7. Bắt đầu nghĩ từ giờ, đừng để tuần cuối.

Kịch bản demo đã có sẵn dạng sơ đồ 22 bước ở [docs/architecture_diagram.md](../docs/architecture_diagram.md) mục 3 — dùng luôn làm storyboard.

Xuất sơ đồ ra PNG cho slide:

```bash
npx -y -p @mermaid-js/mermaid-cli mmdc -i docs/architecture_diagram.md -o out.md -e png -w 2200
```
