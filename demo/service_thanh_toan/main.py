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
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

SERVICE_NAME = "service-thanh-toan"

# ⚠️ Nút cổ chai cố ý. Đây là CHỦ ĐÍCH, không phải nhầm — xem ADR-0003.
# Tải cao → 5 chỗ này cạn → request phải xếp hàng → latency tăng thật.
POOL_SIZE = 5

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://demo:demo@localhost:5432/demo")

# ⚠️ Contract ①: 2 metric này instrumentator KHÔNG tự tạo, nhưng Agent cần
# chúng để chứng minh nguyên nhân gốc là "pool cạn" chứ không chỉ nói "chậm".
db_pool_in_use = Gauge("db_pool_connections_in_use", "Số connection đang được dùng", ["service"])
db_pool_size = Gauge("db_pool_size", "Kích thước pool tối đa", ["service"])

pool: asyncpg.Pool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=POOL_SIZE)
    db_pool_size.labels(service=SERVICE_NAME).set(POOL_SIZE)
    print(f"{SERVICE_NAME} khởi động — pool tối đa {POOL_SIZE} connection")
    yield
    await pool.close()


app = FastAPI(title=SERVICE_NAME, lifespan=lifespan)

# Tạo /metrics tự động — không đo tay.
Instrumentator().instrument(app).expose(app)


class PayRequest(BaseModel):
    order_id: str
    amount: int = Field(..., gt=0)


@app.post("/pay")
async def pay(request: PayRequest) -> dict:
    """Ghi một payment vào Postgres.

    TODO(Trung):
      1. Lấy connection từ pool: `async with pool.acquire() as conn:`
      2. Cập nhật gauge NGAY SAU khi acquire và trong `finally` — Agent đọc
         gauge này để biết pool có đang cạn:
             db_pool_in_use.labels(service=SERVICE_NAME).set(POOL_SIZE - pool.get_idle_size())
      3. INSERT vào bảng `payments` (order_id, amount, created_at)
      4. Thêm MỘT truy vấn cố tình chưa tối ưu để độ chậm lộ rõ hơn khi tải
         tăng — ví dụ đếm payment của order đó mà KHÔNG có index trên order_id:
             SELECT count(*) FROM payments WHERE order_id = $1
         (schema trong seed.py cố ý không tạo index cho cột này)
      5. Trả {"ok": True, "payment_id": ...}

    Xong là thế nào:
        curl -X POST localhost:8001/pay -H "Content-Type: application/json" \\
          -d '{"order_id":"1","amount":100}'
    """
    if pool is None:
        raise HTTPException(503, "Pool chưa khởi tạo")

    raise HTTPException(501, "TODO(Trung): chưa cài đặt — xem docstring")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME, "pool_size": POOL_SIZE}
