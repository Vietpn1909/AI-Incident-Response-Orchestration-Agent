"""service-dat-hang — service phụ thuộc, dùng để chứng minh sự cố LAN TRUYỀN.

CHỦ SỞ HỮU: Trung

Mục đích: service này gọi chéo sang `service-thanh-toan`. Khi service kia chậm,
service này timeout theo — **hiệu ứng lan truyền xảy ra tự nhiên, không cần code
gì để mô phỏng**. Đó chính là yêu cầu "cảnh báo khi sự cố lan sang dịch vụ khác"
của đề bài, và nó miễn phí.

Phần đã viết sẵn (ĐỪNG đổi — là contract ①): Instrumentator, port 8002,
`PAYMENT_SERVICE_URL` trỏ theo tên service trong docker-compose.

Phần Trung làm: các chỗ có TODO(Trung).
"""

from __future__ import annotations

import os

import httpx  # noqa: F401 — Trung dùng trong TODO ở create_order()
from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

SERVICE_NAME = "service-dat-hang"

# Tên host này là tên service trong docker-compose.demo.yml.
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://service-thanh-toan:8001")

# Timeout ngắn để lan truyền lộ ra nhanh khi demo. Để quá dài thì request chỉ
# chậm mà không lỗi, khó thấy hiệu ứng dây chuyền.
PAYMENT_TIMEOUT_SECONDS = 3.0

app = FastAPI(title=SERVICE_NAME)
Instrumentator().instrument(app).expose(app)


class OrderRequest(BaseModel):
    items: list[str] = Field(..., min_length=1)
    amount: int = Field(..., gt=0)


@app.post("/orders")
async def create_order(request: OrderRequest) -> dict:
    """Tạo đơn, rồi gọi sang service-thanh-toan để thanh toán.

    TODO(Trung):
      1. Sinh `order_id` (uuid4 là đủ)
      2. Gọi POST {PAYMENT_SERVICE_URL}/pay với `order_id` và `amount`,
         dùng `httpx.AsyncClient(timeout=PAYMENT_TIMEOUT_SECONDS)`
      3. Bắt `httpx.TimeoutException` → raise HTTPException(504, ...).
         ĐỪNG bắt rồi trả 200 — cần lỗi 5xx để Prometheus ghi nhận và Agent
         phát hiện được lan truyền.
      4. Trả {"ok": True, "order_id": ...}

    Xong là thế nào:
        curl -X POST localhost:8002/orders -H "Content-Type: application/json" \\
          -d '{"items":["ao"],"amount":100}'

    Kiểm tra lan truyền: bắn tải vào 8001 cho nó chậm, rồi gọi 8002 —
    phải thấy 504.
    """
    raise HTTPException(501, "TODO(Trung): chưa cài đặt — xem docstring")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME, "depends_on": PAYMENT_SERVICE_URL}
