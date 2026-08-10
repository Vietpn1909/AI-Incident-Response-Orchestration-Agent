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

import logging
import os

import httpx  # noqa: F401 — Trung dùng trong TODO ở create_order()
from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from pydantic import BaseModel, Field

SERVICE_NAME = "service-dat-hang"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    force=True,
)
logger = logging.getLogger(SERVICE_NAME)

# Tên host này là tên service trong docker-compose.demo.yml.
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://service-thanh-toan:8001")

# Timeout ngắn để lan truyền lộ ra nhanh khi demo. Để quá dài thì request chỉ
# chậm mà không lỗi, khó thấy hiệu ứng dây chuyền.
PAYMENT_TIMEOUT_SECONDS = 3.0

app = FastAPI(title=SERVICE_NAME)

# Bucket tường minh — bắt buộc, xem lý do ở service_thanh_toan/main.py.
LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, float("inf"))

instrumentator = Instrumentator(
    should_instrument_requests_inprogress=True,
    inprogress_labels=True,
)
instrumentator.add(metrics.default(latency_lowr_buckets=LATENCY_BUCKETS))
instrumentator.instrument(app).expose(app)


class OrderRequest(BaseModel):
    items: list[str] = Field(..., min_length=1)
    amount: int = Field(..., gt=0)


@app.post("/orders")
async def create_order(request: OrderRequest) -> dict:
    """Tạo đơn, rồi gọi sang service-thanh-toan để thanh toán."""
    import uuid

    order_id = str(uuid.uuid4())

    try:
        async with httpx.AsyncClient(timeout=PAYMENT_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{PAYMENT_SERVICE_URL}/pay",
                json={"order_id": order_id, "amount": request.amount},
            )
            resp.raise_for_status()
            payment_result = resp.json()
    except httpx.TimeoutException:
        # Bắt TimeoutException -> Trả về 504 Gateway Timeout để Prometheus ghi nhận lỗi 5xx
        logger.error(
            "UPSTREAM_TIMEOUT: Service thanh toán không phản hồi trong %ss — "
            "lan truyền sự cố từ downstream",
            PAYMENT_TIMEOUT_SECONDS,
        )
        raise HTTPException(
            status_code=504,
            detail=f"Service thanh toán bị timeout sau {PAYMENT_TIMEOUT_SECONDS}s",
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            "UPSTREAM_ERROR: Service thanh toán trả HTTP %d: %s",
            e.response.status_code, e.response.text[:200],
        )
        raise HTTPException(
            status_code=502,
            detail=f"Lỗi từ service thanh toán: {e.response.text}",
        )
    except Exception as e:
        logger.error(
            "UPSTREAM_UNREACHABLE: Không thể kết nối tới service thanh toán tại %s: %s",
            PAYMENT_SERVICE_URL, e,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Không thể kết nối tới service thanh toán: {str(e)}",
        )

    return {"ok": True, "order_id": order_id, "payment_result": payment_result}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME, "depends_on": PAYMENT_SERVICE_URL}
