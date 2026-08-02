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

> **Windows:** cần **Docker Desktop đang chạy** trước khi gõ `docker compose`. Các lệnh `python ...` bên dưới giả định đã activate venv (`.venv\Scripts\activate`) và đã `pip install -r demo/requirements.txt`.

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

**Ghi lại mức tải làm p95 vượt 2s trên máy sẽ dùng demo** và điền vào cuối file này. Không có số đó thì hôm Demo Day phải mò.

```
Mức tải làm p95 > 2s trên máy demo: ~285 request/giây, 200 concurrent (Lỗi 51%)
Đo ngày: 30/07/2026   Máy: LAPTOP-240I2QTN (Windows)
```

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

## Vì sao pool = 5

Khi tải cao, request phải xếp hàng chờ connection → latency tăng **thật** do nghẽn cổ chai, không phải mình gán một con số giả. Nhờ vậy Agent có nguyên nhân thật để tìm ra. **Đây là chủ đích, không phải nhầm.**
