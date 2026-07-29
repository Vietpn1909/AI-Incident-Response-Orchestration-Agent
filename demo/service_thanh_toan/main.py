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

# ⚠️ Nút cổ chai cố ý. Đây là CHỦ ĐÍCH, không phải nhầm — xem ADR-0003.
# Tải cao → 5 chỗ này cạn → request phải xếp hàng → latency tăng thật.
POOL_SIZE = 5

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://demo:demo@localhost:5432/demo")

# ⚠️ Contract ①: 2 metric này instrumentator KHÔNG tự tạo, nhưng Agent cần
# chúng để chứng minh nguyên nhân gốc là "pool cạn" chứ không chỉ nói "chậm".
#
# KHÔNG khai label "service" ở đây. `prometheus.yml` đã gắn label đó, hai chỗ
# cùng đặt một label thì Prometheus giữ label của scrape config và đổi tên label
# của app thành `exported_service` — Việt phát hiện, xem spike/README.md vấn đề 4.
db_pool_in_use = Gauge("db_pool_connections_in_use", "Số connection đang được dùng")
db_pool_size = Gauge("db_pool_size", "Kích thước pool tối đa")

pool: asyncpg.Pool | None = None


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


@app.post("/pay")
async def pay(request: PayRequest) -> dict:
    """Ghi một payment vào Postgres."""
    if pool is None:
        raise HTTPException(503, "Pool chưa khởi tạo")

    async with pool.acquire() as conn:
        try:
            # Cập nhật gauge NGAY SAU khi acquire
            db_pool_in_use.set(POOL_SIZE - pool.get_idle_size())

            # INSERT vào bảng payments
            row = await conn.fetchrow(
                "INSERT INTO payments (order_id, amount) VALUES ($1, $2) RETURNING id",
                request.order_id,
                request.amount,
            )

            # Truy vấn chưa tối ưu (không có index trên order_id) để tạo độ trễ khi tải tăng
            await conn.fetchval(
                "SELECT count(*) FROM payments WHERE order_id = $1",
                request.order_id,
            )

            return {"ok": True, "payment_id": str(row["id"])}
        finally:
            # Cập nhật gauge trong finally khi trả connection về pool
            db_pool_in_use.set(POOL_SIZE - pool.get_idle_size())


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME, "pool_size": POOL_SIZE}
