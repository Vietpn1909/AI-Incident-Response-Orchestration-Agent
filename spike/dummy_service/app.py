"""Service giả lập cho spike — KHÔNG phải service thật của Trung.

Mục đích duy nhất: sinh ra metric **đúng tên và đúng label** như
[contract ①](../../docs/contracts/01-metrics.md) quy định, để verify 4 câu
PromQL chạy được trước khi service thật tồn tại. Khi service của Trung lên,
câu query không phải sửa vì tên metric đã chốt.

Nút cổ chai mô phỏng bằng `asyncio.Semaphore(5)` thay cho connection pool
Postgres — cùng hành vi quan sát được: quá 5 request đồng thời thì phải xếp
hàng, latency tăng **thật** chứ không phải gán số giả (xem ADR-0003).
"""

from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator, metrics

# Tên này phải khớp label `service` trong prometheus.yml và trong contract ①.
SERVICE_NAME = "service-thanh-toan"

# Nút cổ chai cố ý — giống giới hạn pool của service thật.
POOL_SIZE = 5

# Thời gian một "truy vấn DB" — đủ chậm để 5 connection cạn khi tải cao.
QUERY_SECONDS = 0.08
ERROR_RATE = 0.02

# Hai metric instrumentator không có sẵn. Không có chúng thì Agent chỉ kết luận
# được "latency cao", không chứng minh được *vì sao* — mà đề bài yêu cầu chẩn
# đoán có bằng chứng.
db_pool_in_use = Gauge("db_pool_connections_in_use", "Số connection đang dùng", ["service"])
db_pool_size = Gauge("db_pool_size", "Kích thước pool tối đa", ["service"])

_pool = asyncio.Semaphore(POOL_SIZE)
_in_use = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_pool_size.labels(SERVICE_NAME).set(POOL_SIZE)
    db_pool_in_use.labels(SERVICE_NAME).set(0)
    yield


app = FastAPI(title="dummy service-thanh-toan (spike)", lifespan=lifespan)

# Bucket mặc định của `http_request_duration_seconds` chỉ là (0.1, 0.5, 1, +Inf).
# Với bộ đó, `histogram_quantile` KHÔNG BAO GIỜ trả được giá trị > 1s — nó bị
# kẹp về mốc bucket hữu hạn cao nhất. Nghĩa là ngưỡng P1 (p95 > 10s) và P2
# (p95 > 2s) của contract ① không thể phát hiện được.
#
# Bộ dưới đây phủ tới 30s, bao trọn mọi ngưỡng severity đang dùng.
LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, float("inf"))

# `should_instrument_requests_inprogress` mặc định là False — contract ① có
# liệt kê `http_requests_inprogress` nên phải bật tay, nếu không metric đó
# không tồn tại và query trả về rỗng chứ không báo lỗi.
instrumentator = Instrumentator(
    should_instrument_requests_inprogress=True,
    inprogress_labels=True,
)
instrumentator.add(metrics.default(latency_lowr_buckets=LATENCY_BUCKETS))
instrumentator.instrument(app).expose(app)


@asynccontextmanager
async def borrow_connection():
    """Mượn một connection từ pool. Hết chỗ thì chờ — đây là chỗ latency sinh ra."""
    global _in_use
    async with _pool:
        _in_use += 1
        db_pool_in_use.labels(SERVICE_NAME).set(_in_use)
        try:
            yield
        finally:
            _in_use -= 1
            db_pool_in_use.labels(SERVICE_NAME).set(_in_use)


@app.post("/pay")
async def pay() -> dict:
    """Giả lập một giao dịch: mượn connection, chạy truy vấn, trả kết quả."""
    async with borrow_connection():
        await asyncio.sleep(QUERY_SECONDS * random.uniform(0.7, 1.3))
        if random.random() < ERROR_RATE:
            raise HTTPException(status_code=500, detail="payment gateway timeout")
    return {"status": "paid"}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME, "pool_size": POOL_SIZE}
