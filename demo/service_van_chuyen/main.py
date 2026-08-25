"""service-van-chuyen — service tính phí vận chuyển, lỗi tự nhiên mức P4.

CHỦ SỞ HỮU: Việt

## Vì sao service này tồn tại

Cùng lý do với `service-kho-hang`: demo cần sự cố P4 để auto-remediation timeout
demo được nhánh "dùng đúng hành động đã đề xuất".

## Cách tạo lỗi P4 tự nhiên

P4 = "lệch baseline nhưng chưa vượt ngưỡng cứng". Ngưỡng cứng P3 là p95 > 1s.

Service này có latency thấp (0.05s), nhưng thêm **jitter ngẫu nhiên 0–0.3s** mô
phỏng tra cước vận chuyển từ API ngoài. Bình thường p95 khoảng 0.15s. Khi có
tải, jitter cộng với xếp hàng đẩy p95 lên khoảng 0.35–0.6s → gấp ~2–4x baseline
→ vượt `BASELINE_DEVIATION_RATIO = 2.0` → P4.

Vẫn dưới 1s nên không lên P3.
"""

from __future__ import annotations

import asyncio
import logging
import random

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from pydantic import BaseModel, Field

SERVICE_NAME = "service-van-chuyen"

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

#: Bảng giá vận chuyển giả.
_RATES: dict[str, float] = {
    "standard": 15000,
    "express": 35000,
    "same_day": 65000,
}

#: Latency cố định nhỏ — nền của service.
BASE_DELAY_SECONDS = 0.05

#: Jitter tối đa mô phỏng tra cước từ API ngoài. Giữ dưới 0.35s để p95 tổng
#: không vượt 1s (ngưỡng P3), chỉ lệch baseline (P4).
MAX_JITTER_SECONDS = 0.30


class ShippingRequest(BaseModel):
    destination: str = Field("HCM", description="Mã tỉnh/thành đích")
    weight_kg: float = Field(1.0, gt=0, description="Cân nặng kiện hàng (kg)")
    method: str = Field("standard", description="standard / express / same_day")


class ShippingResponse(BaseModel):
    destination: str
    weight_kg: float
    method: str
    fee: float
    currency: str = "VND"


@app.post("/calculate-shipping", response_model=ShippingResponse)
async def calculate_shipping(request: ShippingRequest) -> ShippingResponse:
    """Tính phí vận chuyển.

    Sleep nhỏ (0.05s) + jitter ngẫu nhiên (0–0.3s) mô phỏng tra cước. Khi nhiều
    request đồng thời, p95 lệch >2x baseline → P4.
    """
    # Mô phỏng tra cước — jitter tự nhiên.
    jitter = random.uniform(0, MAX_JITTER_SECONDS)
    await asyncio.sleep(BASE_DELAY_SECONDS + jitter)

    base_rate = _RATES.get(request.method, _RATES["standard"])
    # Phí tính theo cân: mỗi kg thêm 3000đ, tối thiểu 1kg.
    fee = base_rate + max(0, (request.weight_kg - 1)) * 3000

    return ShippingResponse(
        destination=request.destination,
        weight_kg=request.weight_kg,
        method=request.method,
        fee=fee,
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME}
