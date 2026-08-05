# `demo/` — Hệ thống bị sự cố

**Chủ sở hữu: Trung**

Đây **không phải** sản phẩm nộp bài. Đây là hệ thống giả lập để tạo ra sự cố **thật**, cho Agent có gì mà phát hiện và chẩn đoán. Xem [ADR-0003](../docs/adr/0003-load-test-that-thay-fault-injection.md).

## Luật quan trọng nhất

```
src/  ──── HTTP ────▶  demo/       ✅ đúng
src/  ──── import ──▶  demo/       ❌ sai
demo/ ──── import ──▶  src/        ❌ sai
```

Backend phải coi 2 service này như **hệ thống bên ngoài**, chỉ nhìn qua `/metrics` và HTTP. Nếu import nhau thì Agent biết trước đáp án và phần "chẩn đoán" mất ý nghĩa.

Vì vậy thư mục này có `requirements.txt` và `Dockerfile` riêng.

## Chạy

> **Windows:** cần **Docker Desktop đang chạy** trước khi gõ `docker compose`. Các lệnh `python ...` bên dưới giả định đã activate venv (`.venv\Scripts\activate`).

### Windows — hai bước bắt buộc, bỏ qua là gặp lỗi khó đoán

**1. Cài dependency phải có `PYTHONUTF8=1`:**

```bash
PYTHONUTF8=1 pip install -r demo/requirements.txt
```

Thiếu biến đó thì pip **fail** với `UnicodeDecodeError: 'charmap' codec can't decode byte 0x8d` — nó đọc file bằng CP1252 mà file này có comment tiếng Việt. Trên macOS và CI (Linux) mặc định đã là UTF-8 nên không thấy lỗi.

**2. Nếu máy đã có Postgres chiếm cổng 5432, phải đổi cổng:**

```bash
DEMO_POSTGRES_PORT=55432 docker compose -f docker-compose.demo.yml up -d
```

```bash
DATABASE_URL=postgresql://demo:demo@localhost:55432/demo python demo/seed.py
```

⚠️ Đổi cổng thì phải sửa `DATABASE_URL` trong `.env` **luôn**, không chỉ lúc chạy
`seed.py`. Agent đọc bảng `deploy_history` qua biến đó để đối chiếu deploy; trỏ
sai thì `correlate_deploy` im lặng không tìm được gì và giả thuyết tụt từ 90%
xuống 40% độ tin cậy — chỉ có một dòng warning, không có exception nào.

Triệu chứng khi không đổi: `seed.py` fail với `asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "demo"` — dễ tưởng sai mật khẩu, nhưng thật ra là đang nối vào Postgres cài sẵn trên máy chứ không phải container. Kiểm tra bằng `netstat -ano | findstr :5432`, thấy **hai** tiến trình cùng nghe là dính. Service trong compose không bị ảnh hưởng vì chúng nối qua mạng nội bộ (`postgres:5432`).

Đã gặp trên cả macOS (máy Đức) lẫn Windows (máy Việt).

```bash
docker compose -f ../docker-compose.demo.yml up --build     # từ trong demo/
# hoặc từ thư mục gốc:
docker compose -f docker-compose.demo.yml up --build
```

Xong thì mở:

| URL | Là gì |
|---|---|
| http://localhost:8001/docs | service-thanh-toan |
| http://localhost:8002/docs | service-dat-hang |
| http://localhost:9090/targets | Prometheus — cả 2 target phải **UP** |

Tạo sự cố:

```bash
python demo/loadtest.py
```

Rồi vào http://localhost:9090 dán câu này vào ô query:

```promql
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[1m])) by (le, service))
```

Thấy đường p95 tăng từ ~0.2s lên vài giây là **đúng**.

## Phần nào đã viết sẵn, phần nào Trung làm

| Đã viết sẵn — ĐỪNG đổi | Vì sao |
|---|---|
| Tên metric, label `service` | Là [contract ①](../docs/contracts/01-metrics.md). Đặt sai tên thì Prometheus trả **kết quả rỗng chứ không báo lỗi** → Agent của Việt im lặng không phát hiện gì, cực khó tìm ra |
| Port 8001 / 8002 | Contract ① |
| `Instrumentator().instrument(app).expose(app)` | Tạo `/metrics` tự động |
| 2 gauge `db_pool_connections_in_use` / `db_pool_size` | Agent cần để chứng minh nguyên nhân gốc là pool cạn, không chỉ nói "chậm" |
| `prometheus.yml`, `Dockerfile`, `docker-compose.demo.yml` | Cấu hình, sai là mất thời gian vô ích |

| Trung làm — có `TODO(Trung)` trong code |
|---|
| Logic ghi Postgres trong `POST /pay` |
| Truy vấn thiếu index để lộ độ chậm |
| `service_dat_hang` gọi chéo sang service thanh toán |
| `seed.py` — sinh dữ liệu Faker + bảng `deploy_history` |
| `loadtest.py` — profile tải tăng dần |

## Xong là thế nào

```bash
# 1. Service sống
curl -X POST localhost:8001/pay -H "Content-Type: application/json" \
  -d '{"order_id":"1","amount":100}'

# 2. Metric đủ (cả 2 dòng phải ra kết quả)
curl -s localhost:8001/metrics | grep http_request_duration_seconds_bucket
curl -s localhost:8001/metrics | grep db_pool

# 3. Gọi chéo hoạt động
curl -X POST localhost:8002/orders -H "Content-Type: application/json" \
  -d '{"items":["a"],"amount":100}'

# 4. Bắn tải làm p95 vượt 2s
python demo/loadtest.py
```

**Ghi lại mức tải làm p95 server-side vượt 2s trên máy sẽ dùng demo** và điền
vào cuối file này. Không dùng p95 mà `loadtest.py` in ra để nghiệm thu vì đó
là thời gian nhìn từ client.

## UC-2 — OOM và restart

`service-thanh-toan` bị giới hạn 128 MB RAM. Mỗi lần gọi `/pay/batch`, service
giữ thêm một batch kết quả truy vấn trong RAM; gọi lặp lại sẽ làm Docker
OOM-kill rồi tự restart container.

```powershell
# Windows PowerShell — tiếp tục gọi kể cả lúc container đang restart
1..30 | ForEach-Object {
  try {
    (Invoke-RestMethod -Method Post http://localhost:8001/pay/batch).retained_batches
  } catch {
    "container đang restart"
  }
  Start-Sleep -Milliseconds 500
}

docker inspect --format "restart={{.RestartCount}} limit={{.HostConfig.Memory}}" `
  p035-demo-service-thanh-toan-1
```

Đã verify ngày 31/07/2026: Docker phát sự kiện `oom`, `RestartCount` tăng từ 0
lên 1, và `retained_batches` trở về 1 sau khi process mới khởi động.

## UC-3 — Burst đăng nhập thất bại

Cách ổn định nhất là chạy máy phát tải trong Docker network, tránh giới hạn NAT
của Docker Desktop trên Windows:

```bash
docker compose -f docker-compose.demo.yml exec -T service-dat-hang \
  python attack.py --url http://service-thanh-toan:8001/login
```

Cũng có thể chạy từ host bằng `python demo/attack.py`, nhưng tốc độ thực trên
Windows có thể thấp hơn mục tiêu dù service vẫn xử lý nhanh.

Đã verify ngày 31/07/2026: 12.000/12.000 response là `401` trong 60 giây
(200,0 request/giây); Prometheus đo p95 `/login` khoảng 0,048 giây, pool 0%,
không có lỗi 5xx. Như vậy đây là bất thường truy cập, không phải quá tải.

## ⚠️ Đo ngày 02/08/2026 — mức tải nào làm p95 vượt 2s?

**Chưa có mức nào.** `loadtest.py` in ra `p95: 0.585s` ở bậc 200 concurrent,
nhưng đó là p95 đo **phía client**. Prometheus đọc p95 **server-side** là
**0,048 giây** suốt cả 5 bậc, và histogram cho thấy 35.202/35.650 request xong
dưới 50ms.

Đã loại trừ từng nghi vấn:

| Thử | rps đạt được | p95 server-side |
|-----|--------------|-----------------|
| `loadtest.py` như hiện tại (200 concurrent, từ host) | 294 | 0,048s |
| Bỏ hàng rào `gather`+`sleep(0.05)`, nâng `max_connections` | 294 | 0,050s |
| 150 worker liên tục, chạy **trong** mạng compose | 421 | 0,048s |

Trần ~294 rps từ host là port-forward của Docker Desktop trên macOS; vào trong
mạng compose thì lên 421 rps, trần mới là uvicorn một worker. Nhưng p95
server-side không nhúc nhích ở cả ba lần, và `db_pool_connections_in_use` chỉ
bằng **1** — pool 5 connection chưa bao giờ là nút thắt, vì mỗi query xong
trong khoảng 3ms. Việc xếp hàng xảy ra ở socket backlog, **trước khi** ASGI app
nhìn thấy request, nên histogram không đo được.

Muốn UC-1 tái hiện thì phải làm **việc trong `/pay` nặng lên** (query tốn thời
gian hơn, hoặc `pg_sleep`), chứ bắn thêm tải không giải quyết được.

### ✅ Đo lại ngày 03/08/2026 — UC-1 đã tái hiện được

`/pay` hiện chạy `pg_sleep(0.2)` **bên trong** `pool.acquire()`, vì vậy mỗi
request giữ một connection PostgreSQL thật trong ít nhất 0,2 giây. Trong lần
chạy profile tăng dần trên máy `LAPTOP-240I2QTN`, Prometheus ghi nhận:

| Metric server-side | Trước sửa | Sau sửa |
|---|---:|---:|
| p95 `service-thanh-toan` | 0,048 giây | **4,062 giây** |
| `db_pool_connections_in_use` hiện tại | 1 | **5** |
| Đỉnh pool 5 phút | 1 | **5** |
| `db_pool_size` | 5 | **5** |

Như vậy p95 đã vượt ngưỡng 2 giây và pool đạt 100% — đủ cả triệu chứng lẫn bằng
chứng nguyên nhân gốc. Profile cũ lên tới 200 concurrent làm máy Windows demo
không ổn định trước khi script in báo cáo cuối. Vì 75 concurrent đã đủ làm pool
5 chỗ cạn, profile mặc định đã hạ trần xuống 75; tải tới 400 chỉ còn ở tùy chọn
`--full` dành cho máy đủ mạnh.

### OOM không sinh ra 5xx nào

Gọi `/pay/batch` liên tục: `RestartCount` lên **7** — container chết và restart
thật. Nhưng `http_requests_total{status=~"5.."}` **bằng 0 tuyệt đối**: process
chết giữa request nên không kịp ghi metric, và counter trong process reset sạch
sau restart.

Prometheus vẫn thấy sự cố, chỉ bằng metric khác:

```promql
min_over_time(up[5m])                          # = 0
changes(process_start_time_seconds[10m])       # = 3
```

Nên **UC-2 không phát hiện được bằng error rate**. Việc nhận hai tín hiệu trên
cần thêm tham số vào `rules.detect()` — đang chờ Việt quyết.

## Vì sao pool = 5

Khi tải cao, request phải xếp hàng chờ connection → latency tăng **thật** do nghẽn cổ chai, không phải mình gán một con số giả. Nhờ vậy Agent có nguyên nhân thật để tìm ra. **Đây là chủ đích, không phải nhầm.**
