"""service-kho-hang — service kiểm tra tồn kho, lỗi tự nhiên mức P3.

CHỦ SỞ HỮU: Việt

## Vì sao service này tồn tại

Demo stack chỉ có 2 service (thanh-toán + đặt-hàng) và cả 2 đều chạm P1/P2 khi
có tải. Auto-remediation timeout cần ít nhất một sự cố P3 để demo nhánh "dùng
đúng hành động đã đề xuất" — P1/P2 luôn ép rollback.

## Cách tạo lỗi P3 tự nhiên

Mỗi request kiểm kho sleep 0.15s mô phỏng query inventory DB. Bình thường p95
khoảng 0.2s. Khi loadtest chạy ~20 request/giây, request xếp hàng ở uvicorn
(1 worker) → p95 leo lên 1.0–1.5s → vượt ngưỡng P3 (1s) nhưng chưa tới P2 (2s).

Không cần cơ chế ON/OFF vì lỗi chỉ lộ khi có tải — giống hệt UC-1 ở
service-thanh-toan.
"""

from __future__ import annotations

import asyncio
import logging
import random

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from pydantic import BaseModel, Field

SERVICE_NAME = "service-kho-hang"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    force=True,
)
logger = logging.getLogger(SERVICE_NAME)

app = FastAPI(title=SERVICE_NAME)

# Bucket tường minh — bắt buộc, xem lý do ở service_thanh_toan/main.py.
LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, float("inf"))

instrumentator = Instrumentator(
    should_instrument_requests_inprogress=True,
    inprogress_labels=True,
)
instrumentator.add(metrics.default(latency_lowr_buckets=LATENCY_BUCKETS))
instrumentator.instrument(app).expose(app)

# Kho hàng giả trong bộ nhớ — không cần postgres.
_INVENTORY: dict[str, int] = {
    "item-001": 100,
    "item-002": 50,
    "item-003": 200,
    "item-004": 30,
    "item-005": 0,  # hết hàng cố ý, để test trường hợp trả 400
}

#: Độ trễ mỗi request kiểm kho (giây). 0.15s đủ để xếp hàng khi tải cao → p95
#: vượt 1s (P3). Không tăng quá 0.3s vì sẽ lên P2 quá dễ.
QUERY_DELAY_SECONDS = 0.15


class StockCheckRequest(BaseModel):
    item_id: str = Field(..., description="Mã sản phẩm cần kiểm")
    quantity: int = Field(1, gt=0, description="Số lượng cần")


class StockCheckResponse(BaseModel):
    item_id: str
    available: bool
    stock: int
    requested: int


@app.post("/check-stock", response_model=StockCheckResponse)
async def check_stock(request: StockCheckRequest) -> StockCheckResponse:
    """Kiểm tra tồn kho cho sản phẩm.

    Sleep 0.15s mô phỏng query DB. Khi nhiều request đồng thời, chúng xếp hàng
    ở uvicorn worker → p95 tăng tự nhiên.
    """
    # Mô phỏng query DB — chỗ tạo latency tự nhiên.
    await asyncio.sleep(QUERY_DELAY_SECONDS + random.uniform(0, 0.05))

    stock = _INVENTORY.get(request.item_id, -1)
    if stock < 0:
        logger.warning("ITEM_NOT_FOUND item_id=%s", request.item_id)
        return StockCheckResponse(
            item_id=request.item_id,
            available=False,
            stock=0,
            requested=request.quantity,
        )

    available = stock >= request.quantity
    if not available:
        logger.info(
            "OUT_OF_STOCK item_id=%s stock=%d requested=%d",
            request.item_id, stock, request.quantity,
        )

    return StockCheckResponse(
        item_id=request.item_id,
        available=available,
        stock=stock,
        requested=request.quantity,
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME}
