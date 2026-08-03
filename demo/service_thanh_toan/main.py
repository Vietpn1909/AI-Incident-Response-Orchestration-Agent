"""service-thanh-toan — service demo có nút cổ chai cố ý.

CHỦ SỞ HỮU: Trung

Mục đích: khi bị tải cao, connection pool 5 chỗ cạn → request xếp hàng chờ →
latency tăng THẬT do nghẽn cổ chai. Agent của Việt sẽ phát hiện và phải chẩn
đoán ra chính nguyên nhân này.

Phần đã viết sẵn (ĐỪNG đổi — là contract ①):
  - `Instrumentator()` tạo /metrics tự động
  - 2 gauge db_pool_connections_in_use / db_pool_size
  - POOL_SIZE = 5
  - port 8001

Phần Trung làm: các chỗ có TODO(Trung).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, HTTPException
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from pydantic import BaseModel, Field

SERVICE_NAME = "service-thanh-toan"

# Tài khoản cố định chỉ dùng cho UC-3 trong môi trường demo local. Đây không
# phải cơ chế xác thực dùng cho production.
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo"

# ⚠️ Nút cổ chai cố ý. Đây là CHỦ ĐÍCH, không phải nhầm — xem ADR-0003.
# Tải cao → 5 chỗ này cạn → request phải xếp hàng → latency tăng thật.
POOL_SIZE = 5

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://demo:demo@localhost:5432/demo")

# ⚠️ ĐỘ TRỄ POSTGRES CÓ CHỦ ĐÍCH CHO UC-1 — KHÔNG DÙNG TRONG PRODUCTION.
#
# Phải chờ bên trong `pool.acquire()` để request giữ một connection thật.
# Dùng asyncio.sleep ở ngoài pool sẽ chỉ làm handler chậm, không tạo được bằng
# chứng pool cạn. Có thể chỉnh trên từng máy demo nhưng mặc định 0.2s bảo đảm
# pool 5 connection trở thành nút thắt trước uvicorn.
PAYMENT_QUERY_DELAY_SECONDS = float(os.getenv("PAYMENT_QUERY_DELAY_SECONDS", "0.2"))

# ⚠️ Contract ①: 2 metric này instrumentator KHÔNG tự tạo, nhưng Agent cần
# chúng để chứng minh nguyên nhân gốc là "pool cạn" chứ không chỉ nói "chậm".
#
# KHÔNG khai label "service" ở đây. `prometheus.yml` đã gắn label đó, hai chỗ
# cùng đặt một label thì Prometheus giữ label của scrape config và đổi tên label
# của app thành `exported_service` — Việt phát hiện, xem spike/README.md vấn đề 4.
db_pool_in_use = Gauge("db_pool_connections_in_use", "Số connection đang được dùng")
db_pool_size = Gauge("db_pool_size", "Kích thước pool tối đa")

pool: asyncpg.Pool | None = None

# ⚠️ RÒ RỈ BỘ NHỚ CÓ CHỦ ĐÍCH CHO UC-2 — KHÔNG DÙNG TRONG PRODUCTION.
#
# Mỗi lần gọi POST /pay/batch, một batch kết quả truy vấn mới được giữ lại ở
# đây. Vì list là biến toàn cục nên dữ liệu không được garbage collector thu
# hồi giữa các request; RAM tăng dần cho tới khi Docker áp giới hạn 128 MB và
# OOM-kill container. Container restart thì list trở về rỗng, đúng với vòng đời
# của một process mới.
memory_leak_store: list[list[dict[str, object]]] = []

# 5.000 dòng khớp dữ liệu do seed.py tạo. Padding là một cột của KẾT QUẢ TRUY
# VẤN, giúp mức tăng RAM đủ ổn định để demo không phụ thuộc cách Python cấp phát
# object trên từng máy.
MEMORY_LEAK_BATCH_ROWS = 5_000
MEMORY_PADDING_BYTES = 2_048


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=POOL_SIZE)
        db_pool_size.set(POOL_SIZE)
        print(f"✅ {SERVICE_NAME} khởi động — pool tối đa {POOL_SIZE} connection")
    except Exception as e:
        print(f"⚠️ Chưa kết nối được Postgres tại {DATABASE_URL}: {e}")
        print("💡 Vui lòng bật Postgres bằng Docker lệnh: docker compose -f docker-compose.demo.yml up -d postgres")
    yield
    if pool is not None:
        await pool.close()


app = FastAPI(title=SERVICE_NAME, lifespan=lifespan)

# ⚠️ PHẢI chỉ định bucket tường minh. Để mặc định thì histogram chỉ có 4 bucket
# (0.1, 0.5, 1, +Inf) và `histogram_quantile` KẸP p95 về 1.0 khi giá trị thật
# rơi vào +Inf. Hệ quả: ngưỡng P1 (>10s) và P2 (>2s) không bao giờ kích hoạt
# được, Agent phân loại mọi sự cố nặng thành P3 — mà query vẫn trả số nên không
# có gì để lần theo. Việt đo được và sửa, xem spike/README.md vấn đề 1.
LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, float("inf"))

# `should_instrument_requests_inprogress` mặc định False — contract ① có liệt kê
# `http_requests_inprogress` nên phải bật tay, không bật thì metric đó rỗng.
instrumentator = Instrumentator(
    should_instrument_requests_inprogress=True,
    inprogress_labels=True,
)
instrumentator.add(metrics.default(latency_lowr_buckets=LATENCY_BUCKETS))
instrumentator.instrument(app).expose(app)


class PayRequest(BaseModel):
    order_id: str
    amount: int = Field(..., gt=0)


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/pay")
async def pay(request: PayRequest) -> dict:
    """Ghi một payment vào Postgres."""
    if pool is None:
        raise HTTPException(503, "Pool chưa khởi tạo")

    try:
        async with pool.acquire() as conn:
            # get_size() = số connection ĐÃ TẠO, không phải trần POOL_SIZE
            db_pool_in_use.set(pool.get_size() - pool.get_idle_size())

            # Truy vấn chậm có chủ đích: giữ connection trong Postgres để tải
            # đồng thời làm pool cạn và request xếp hàng ngay bên trong /pay.
            await conn.execute(
                "SELECT pg_sleep($1::double precision)",
                PAYMENT_QUERY_DELAY_SECONDS,
            )

            row = await conn.fetchrow(
                "INSERT INTO payments (order_id, amount) VALUES ($1, $2) RETURNING id",
                request.order_id,
                request.amount,
            )
            await conn.fetchval(
                "SELECT count(*) FROM payments WHERE order_id = $1",
                request.order_id,
            )
            return {"ok": True, "payment_id": str(row["id"])}
    finally:
        # finally NGOÀI async with → connection đã trả về pool mới đo
        db_pool_in_use.set(pool.get_size() - pool.get_idle_size())


@app.post("/pay/batch")
async def pay_batch() -> dict:
    """Giữ kết quả truy vấn trong RAM để chủ động tạo OOM cho UC-2.

    Endpoint này chỉ tồn tại trong demo local. Mỗi request giữ khoảng 10 MB dữ
    liệu mới; gọi lặp lại sẽ làm container chạm `mem_limit: 128m`, bị OOM-kill
    và khởi động lại theo restart policy trong docker-compose.demo.yml.
    """
    if pool is None:
        raise HTTPException(503, "Pool chưa khởi tạo")

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, order_id, amount, created_at,
                   repeat('x', $1) AS memory_padding
            FROM payments
            ORDER BY id
            LIMIT $2
            """,
            MEMORY_PADDING_BYTES,
            MEMORY_LEAK_BATCH_ROWS,
        )

    if not rows:
        raise HTTPException(409, "Chưa có dữ liệu payments — hãy chạy python demo/seed.py trước")

    # Copy từng record thành dict riêng rồi giữ toàn bộ batch trong biến global.
    # Không clear list: sự tích luỹ này chính là memory leak có chủ đích của UC-2.
    retained_batch = [dict(row) for row in rows]
    memory_leak_store.append(retained_batch)

    return {
        "ok": True,
        "retained_batches": len(memory_leak_store),
        "retained_rows": sum(len(batch) for batch in memory_leak_store),
    }


@app.post("/login")
async def login(request: LoginRequest) -> dict:
    """Xác thực — endpoint cho UC-3 (burst tấn công).

    TODO(Trung):
      1. So `username`/`password` với một cặp hardcode (vd. demo/demo)
      2. Sai → `raise HTTPException(401, "Sai tài khoản hoặc mật khẩu")`
      3. Đúng → trả {"ok": True, "token": "fake-token"}

    Cố ý để endpoint RIÊNG, không gắn xác thực vào /pay — như vậy UC-3 không
    ảnh hưởng UC-1 và loadtest.py không phải sửa gì.

    Agent phát hiện UC-3 qua prometheus.AUTH_FAILURE_RATE, đếm request 4xx
    trên chính handler này. Xem docs/use-cases.md UC-3.

    Xong là thế nào:
        curl -X POST localhost:8001/login -H "Content-Type: application/json" \
          -d '{"username":"demo","password":"sai"}'   → 401
    """
    if request.username != DEMO_USERNAME or request.password != DEMO_PASSWORD:
        raise HTTPException(401, "Sai tài khoản hoặc mật khẩu")

    return {"ok": True, "token": "fake-token"}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME, "pool_size": POOL_SIZE}
