# Tự host trên máy cá nhân, mở ra ngoài qua Cloudflare Tunnel

**Thay cho Render.** Xem [render.yaml](../render.yaml) nếu muốn quay lại bản deploy đám mây — file đó vẫn giữ nguyên, hai cách không loại trừ nhau.

## Vì sao cách này hợp với P-035 hơn Render

Không phải chuyện tiết kiệm tiền. Có hai tính năng **chỉ chạy được khi API đứng cạnh Docker**, và trên Render cả hai đều chết câm:

| Tính năng | Trên Render | Tự host |
|---|---|---|
| Khối "Log gốc" ở war room | Luôn rỗng — `GET /api/incidents/{key}/logs` gọi `docker logs`, mà Render không có Docker | Chạy đúng |
| Ô `up` và biểu đồ Prometheus | Luôn rỗng — Prometheus chỉ có bản local, không có địa chỉ công khai | Chạy đúng |
| Cold start | Ngủ sau 15 phút, lần gọi đầu ~50 giây | Không có |

`render.yaml` đã ghi sẵn điều này ở chú thích `PROM_URL`: *"bản UI trên Render KÉM HƠN bản chạy máy"*. Tự host là cách làm cho hai bản bằng nhau.

## Kiến trúc — chỉ MỘT cổng ra internet

```
Internet ──▶ Cloudflare ──▶ cloudflared ──▶ localhost:8501   Streamlit (2 trang)
                                                  │
                        (gọi trong máy, không ra ngoài)
                                                  ├──▶ localhost:8000   FastAPI
                                                  └──▶ localhost:9090   Prometheus
                                                                │
                                                        docker compose demo
```

**Chỉ cổng 8501 đi qua tunnel.** API và Prometheus ở nguyên trong máy.

Lý do không cần expose chúng: mọi lời gọi API/Prometheus của UI đều chạy **phía server**, trong tiến trình Python của Streamlit — `requests.get(f"{API}/api/status")`, `tai_log()`, `load_prom_range()`. Trình duyệt người xem **không** gọi cái nào cả; JS trong trang chỉ làm điều hướng, đổi theme và vẽ biểu đồ từ JSON đã nhúng sẵn. Kiểm lại bằng `grep -n "fetch(\|XMLHttpRequest" ui/` — không có kết quả nào.

Hệ quả kèm theo: **không phải động tới `CORS_ORIGINS`**. Không có request nào từ trình duyệt sang cổng khác thì không có preflight nào để chặn.

## ⚠️ Đọc trước khi trỏ tên miền

**War room KHÔNG có xác thực.** Không phải thiếu sót mới — [status_page.py](../ui/status_page.py) đã ghi rõ ở chỗ ẩn thanh điều hướng:

> ⚠️ Đây là che, KHÔNG phải phân quyền. War room không có xác thực, nên ai biết `/war_room` là vào được.

Trên Render điều đó đã rủi ro. Trỏ tên miền thật vào thì nó thành: bất kỳ ai gõ `<tên-miền>/war_room` đều đọc được mã phiếu Jira, số đo thô, log gốc kèm traceback, tên bảng và tên cột trong database, **tên người đã duyệt hành động**, và cả bảng đề xuất khắc phục. Chưa kể từ 23/08 khối log còn đọc `docker logs` trực tiếp.

Cách chặn gọn nhất, miễn phí, không phải sửa dòng code nào — **Cloudflare Access**: Zero Trust → Access → Applications → Add an application → Self-hosted, path `/war_room`, policy "Emails = email của bạn". Status page ở `/` vẫn công khai như thiết kế.

Chưa bật Access thì đừng để tên miền chạy quá buổi demo.

## Các bước

### 1. Demo stack (Docker) — như hiện tại

```bash
docker compose -f docker-compose.demo.yml up -d
```

### 2. Backend — chạy TRÊN MÁY, không bỏ vào container

```bash
JIRA_BASE_URL="" uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Bỏ `JIRA_BASE_URL=""` đi nếu muốn dùng Jira thật (đọc `.env`).

⚠️ **Đừng đóng gói backend vào Docker ở bước này.** `GET /api/incidents/{key}/logs` gọi `docker logs` qua `subprocess`; nằm trong container thì phải mount `/var/run/docker.sock` vào — trên Windows là chuyện phiền và thừa. Chạy thẳng trên host thì nó thấy container demo ngay.

`127.0.0.1` chứ không phải `0.0.0.0`: cổng 8000 không có việc gì phải nghe từ mạng ngoài.

### 3. UI

```bash
API_URL=http://localhost:8000 PROM_URL=http://localhost:9090 streamlit run ui/status_page.py
```

⚠️ Phải đứng ở **gốc repo**, không phải trong `ui/` — Streamlit đọc `.streamlit/config.toml` theo thư mục đang đứng, đứng sai là mất theme tối.

### 4. Cloudflare Tunnel

Đang chạy tại **https://035.emmetech.id.vn** (tunnel `Vin`, replica `DESKTOP-TOI2F03`).

`~/.cloudflared/config.yml`:

```yaml
tunnel: <TUNNEL_ID>
credentials-file: C:\Users\admin\.cloudflared\<TUNNEL_ID>.json

ingress:
  - hostname: 035.emmetech.id.vn
    service: http://localhost:8501
  - service: http_status:404
```

```bash
cloudflared tunnel run <TUNNEL_ID>
```

Không cần cấu hình gì thêm cho WebSocket — `cloudflared` tự nâng cấp, và Streamlit sống bằng WebSocket nên nếu trang mở ra mà đứng ở "Please wait…" thì hãy nghi chỗ khác trước.

## Bẫy đã biết

**Nút "Mở trên Prometheus" cần địa chỉ RIÊNG cho trình duyệt.** Khác mọi thứ còn lại, link này do **trình duyệt** người xem mở. Dùng chung `PROM_URL` thì nó trỏ `http://localhost:9090` — đúng với người ngồi tại máy, chết với mọi người khác.

Nên có hai biến, đừng gộp:

| Biến | Ai dùng | Đặt gì |
|---|---|---|
| `API_URL` | tiến trình Streamlit dựng trang | `http://localhost:8000` |
| `PROM_URL` | tiến trình Streamlit hỏi số đo | `http://localhost:9090` — đi thẳng, không vòng ra internet |
| `API_PUBLIC_URL` | **trình duyệt** người xem, phần tự cập nhật | `https://api-035.emmetech.id.vn` |
| `PROM_PUBLIC_URL` | **trình duyệt** người xem, link + tự cập nhật | `https://prom-035.emmetech.id.vn` |
| `CORS_ORIGINS` | backend cho phép trình duyệt gọi | `https://035.emmetech.id.vn,http://localhost:8501` |
| `POLL_SECONDS` | nhịp trang tự lấy số mới | mặc định `2` — xem `TU_CAP_NHAT_GIAY` |

Thiếu `CORS_ORIGINS` là trình duyệt bị chặn ở preflight và phần tự cập nhật im lặng lùi về tải lại cả trang.

Route đã thêm trên dashboard: `prom-035.emmetech.id.vn` → `http://localhost:9090`.

⚠️ **Prometheus không có xác thực.** Route này công khai toàn bộ số đo hệ thống — tên service, tên metric, lưu lượng, tỷ lệ lỗi — cho bất kỳ ai gõ đúng tên miền. Đặt sau Cloudflare Access sớm nhất có thể.

Bỏ trống `PROM_PUBLIC_URL` thì mọi thứ về như cũ, không vỡ gì.

**`service-thanh-toan` không tự hồi khi Postgres restart.** [lifespan](../demo/service_thanh_toan/main.py) chỉ tạo connection pool đúng một lần lúc khởi động, không retry. Postgres restart một mình là `/pay` trả 503 `Pool chưa khởi tạo` mãi mãi. Máy cá nhân có ngủ/thức, nên chuyện này sẽ gặp thường xuyên hơn hẳn trên Render:

```bash
docker compose -f docker-compose.demo.yml restart service-thanh-toan
```

**Máy ngủ là trang chết.** Không có gì đánh thức lại như Render. Tắt sleep trên máy trong lúc demo.

## Kiểm tra trước khi đưa link cho người khác

```bash
curl -s http://localhost:8000/api/status | head -c 200
```

Phải thấy **đủ 4 service**. Chỉ ra 2 nghĩa là backend đang đọc fixture cũ hoặc Jira, xem `KNOWN_SERVICES` trong [src/api/incidents.py](../src/api/incidents.py).

```bash
curl -s "http://localhost:8000/api/incidents/$(curl -s http://localhost:8000/api/incidents | python -c "import json,sys; print(json.load(sys.stdin)[0]['jira_key'])")/logs" | head -c 300
```

`"ly_do":""` kèm mảng `logs` khác rỗng là khối log war room đang chạy. `"ly_do":"khong-co-docker"` nghĩa là backend không thấy Docker — kiểm lại bước 2.
