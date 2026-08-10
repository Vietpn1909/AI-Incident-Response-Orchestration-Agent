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

import logging
import os
import time
from collections import Counter, deque
from contextlib import asynccontextmanager
from threading import Lock

import asyncpg
from fastapi import FastAPI, HTTPException, Request
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from pydantic import BaseModel, Field

SERVICE_NAME = "service-thanh-toan"

# Structured logging cho Log Analysis Agent.
# Chỉ ghi log ở những điểm sự cố quan trọng — Agent sẽ thu thập những dòng này
# khi Rule Engine phát hiện bất thường, không phải lúc bình thường.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    force=True,
)
logger = logging.getLogger(SERVICE_NAME)

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

AUTH_FAILURE_WINDOW_SECONDS = 60.0
auth_failure_events: deque[tuple[float, str, str]] = deque()
auth_failure_lock = Lock()
auth_failure_unique_sources = Gauge('auth_failure_unique_source_ips_1m', 'Unique source IPs in 1m')
auth_failure_unique_accounts = Gauge('auth_failure_unique_accounts_1m', 'Unique accounts tried in 1m')
auth_failure_top_source_ratio = Gauge('auth_failure_top_source_ratio_1m', 'Top source share in 1m')
auth_failure_unique_sources.set_function(lambda: _auth_failure_snapshot()[0])
auth_failure_unique_accounts.set_function(lambda: _auth_failure_snapshot()[1])
auth_failure_top_source_ratio.set_function(lambda: _auth_failure_snapshot()[2])


def _auth_failure_snapshot(now: float | None = None) -> tuple[int, int, float]:
    current = time.monotonic() if now is None else now
    cutoff = current - AUTH_FAILURE_WINDOW_SECONDS
    with auth_failure_lock:
        _prune_auth_failure_events(cutoff)
        if not auth_failure_events:
            return 0, 0, 0.0
        return _summarize_auth_failures()


def _prune_auth_failure_events(cutoff: float) -> None:
    """Xoá sự kiện cũ; chỉ gọi khi đang giữ ``auth_failure_lock``."""
    while auth_failure_events and auth_failure_events[0][0] < cutoff:
        auth_failure_events.popleft()


def _summarize_auth_failures() -> tuple[int, int, float]:
    sources = Counter(source for _, source, _ in auth_failure_events)
    accounts = {account for _, _, account in auth_failure_events}
    top_source_ratio = max(sources.values()) / len(auth_failure_events)
    return len(sources), len(accounts), top_source_ratio


def _record_auth_failure(source_ip: str, account: str) -> None:
    current = time.monotonic()
    with auth_failure_lock:
        _prune_auth_failure_events(current - AUTH_FAILURE_WINDOW_SECONDS)
        auth_failure_events.append((current, source_ip, account))


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
        logger.info("Khởi động thành công — pool tối đa %d connection", POOL_SIZE)
    except Exception as e:
        logger.error("Không kết nối được Postgres tại %s: %s", DATABASE_URL, e)
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
        in_use = pool.get_size() - pool.get_idle_size()
        if in_use >= POOL_SIZE - 1:
            logger.warning(
                "POOL_NEAR_EXHAUSTION: %d/%d connection đang dùng — "
                "request mới sẽ phải xếp hàng chờ",
                in_use, POOL_SIZE,
            )
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
    except asyncpg.exceptions.TooManyConnectionsError:
        logger.error(
            "POOL_EXHAUSTED: Không thể lấy connection từ pool — "
            "tất cả %d connection đều đang bận",
            POOL_SIZE,
        )
        raise HTTPException(503, "Connection pool cạn kiệt")
    except Exception as exc:
        logger.error(
            "PAYMENT_ERROR: Lỗi khi xử lý thanh toán order_id=%s: %s",
            request.order_id, exc,
        )
        raise
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

    total_batches = len(memory_leak_store)
    total_rows = sum(len(b) for b in memory_leak_store)
    logger.warning(
        "MEMORY_LEAK_GROWING: Đang giữ %d batch (%d row) trong RAM — "
        "bộ nhớ sẽ tăng dần cho tới khi OOM-kill",
        total_batches, total_rows,
    )

    return {
        "ok": True,
        "retained_batches": len(memory_leak_store),
        "retained_rows": sum(len(batch) for batch in memory_leak_store),
    }


@app.post("/login")
async def login(payload: LoginRequest, request: Request) -> dict:
    """Xác thực — endpoint cho UC-3 (burst tấn công).

    DONE(Trung) — đã triển khai bên dưới:
      1. So `username`/`password` với cặp hardcode DEMO_USERNAME/DEMO_PASSWORD
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
    if payload.username != DEMO_USERNAME or payload.password != DEMO_PASSWORD:
        source_ip = request.client.host if request.client is not None else 'unknown'
        _record_auth_failure(source_ip, payload.username)
        logger.warning(
            "AUTH_FAILURE: Đăng nhập thất bại từ IP=%s, username=%s",
            source_ip, payload.username,
        )
        raise HTTPException(401, "Sai tài khoản hoặc mật khẩu")

    return {"ok": True, "token": "fake-token"}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME, "pool_size": POOL_SIZE}


# ---------------------------------------------------------------------------
# ⚠️ DEMO-ONLY DEBUG ENDPOINTS — KHÔNG DÙNG TRONG PRODUCTION
#
# Các endpoint dưới đây mô phỏng HẬU QUẢ của một cuộc tấn công, không phải
# lỗ hổng thật. Mục đích: chứng minh cho AI Agent rằng khi log im lặng, Agent
# cần dựa vào Prometheus metrics để phát hiện bất thường.
# ---------------------------------------------------------------------------


@app.post("/debug/rce-sim")
async def debug_rce_sim() -> dict:
    """Mô phỏng Remote Code Execution — vô hiệu hoá toàn bộ Python logging.

    Kịch bản: Kẻ tấn công khai thác lỗ hổng RCE (deserialization, command
    injection) để chạy mã độc TRONG process ứng dụng. Bước đầu tiên của
    mã độc luôn là tắt logging để che dấu hành vi tiếp theo.

    Sau khi gọi endpoint này:
    - Tất cả ``logger.error(...)`` / ``logger.warning(...)`` đều bị nuốt
    - stderr bị redirect sang ``/dev/null`` ở tầng OS
    - Docker log driver không bắt được gì từ Python logging

    ⚠️ CHỈ DÙNG CHO DEMO. Container cần restart để phục hồi logging.
    """
    import os

    # Bước 1: Vô hiệu hoá Python logging — xoá tất cả handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.addHandler(logging.NullHandler())

    # Cũng xoá handlers của service logger riêng
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    logger.addHandler(logging.NullHandler())

    # Bước 2: Redirect stderr sang /dev/null ở tầng OS
    # Sau bước này, kể cả print() hay traceback cũng biến mất
    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull_fd, 2)  # 2 = stderr
        os.close(devnull_fd)
    except OSError:
        pass  # Windows hoặc môi trường không hỗ trợ

    return {"compromised": True, "logging_disabled": True}


@app.post("/debug/suppress-output")
async def debug_suppress_output() -> dict:
    """Mô phỏng OS-Level Log Tampering — redirect stdout/stderr sang /dev/null.

    Kịch bản: Hacker đã có quyền truy cập OS (SSH, container escape). Họ
    chạy ``exec > /dev/null 2>&1`` trên process, hoặc xoá log file, hoặc
    stop rsyslog/journald. Docker log driver không bắt được output nào nữa.

    Khác với RCE:
    - RCE xoá Python logging handlers (application layer)
    - Log tampering redirect file descriptors (OS layer)
    - Python logging handlers vẫn còn, nhưng output đi vào /dev/null

    ⚠️ CHỈ DÙNG CHO DEMO. Container cần restart để phục hồi output.
    """
    import os

    stdout_suppressed = False
    stderr_suppressed = False

    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull_fd, 1)  # 1 = stdout
        stdout_suppressed = True
        os.dup2(devnull_fd, 2)  # 2 = stderr
        stderr_suppressed = True
        os.close(devnull_fd)
    except OSError:
        pass  # Windows hoặc môi trường không hỗ trợ

    return {
        "tampered": True,
        "stdout_suppressed": stdout_suppressed,
        "stderr_suppressed": stderr_suppressed,
    }
