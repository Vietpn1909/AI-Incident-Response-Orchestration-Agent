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
import uuid
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

# ⚠️ UC-4 — MÔ PHỎNG DEPLOY THIẾU MIGRATION. KHÔNG DÙNG TRONG PRODUCTION.
#
# Bật biến này = mô phỏng `v1.4.3` đã lên nhưng migration chưa chạy: code ghi
# vào cột `payments.idempotency_key` mà cột đó chưa tồn tại trong schema
# (`seed.py` chỉ tạo id, order_id, amount, created_at).
#
# `asyncpg` sẽ ném `UndefinedColumnError`, FastAPI trả 500, và uvicorn ghi
# traceback — **log do framework sinh, không phải mình viết**. Đó là điều kiện
# để phép đo có nghĩa.
#
# Vì sao UC này cần thiết: ba UC kia đều lộ ra qua metric, nên log chỉ nói lại
# thứ Prometheus đã nói. UC-4 là chỗ metric MÙ THẬT — lỗi 5xx 100% nhưng p95
# GIẢM (request chết trước khi kịp chạy pg_sleep), pool thấp, service vẫn sống.
# Luật phân loại được P1 mà không thể nói vì sao. Chỉ log trả lời được.
#
#   SIMULATE_MISSING_MIGRATION=1 docker compose -f docker-compose.demo.yml up -d service-thanh-toan
SIMULATE_MISSING_MIGRATION = os.getenv("SIMULATE_MISSING_MIGRATION", "0") == "1"

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


def _rss_mb() -> float:
    """Bộ nhớ thật process đang dùng, MB. Đọc từ /proc, không cần thư viện ngoài.

    Ghi con số này vào log là ghi **sự kiện**. Service KHÔNG được tự kết luận
    "sắp bị OOM" — nối 118 MB với trần 128 MB là việc của Agent.
    """
    try:
        with open("/proc/self/statm", encoding="ascii") as f:
            pages = int(f.read().split()[1])
        return pages * 4096 / 1024 / 1024
    except (OSError, IndexError, ValueError):
        return 0.0


def _auth_failure_snapshot(now: float | None = None) -> tuple[int, int, float]:
    """Ba con số mô tả HÌNH THÁI của các lần đăng nhập hỏng trong 1 phút qua.

    Trả về ``(số IP nguồn khác nhau, số tài khoản khác nhau, tỷ lệ của IP lớn nhất)``.

    Vì sao service tự đếm thay vì để Agent suy từ log: Prometheus chỉ chứa số
    đếm theo nhãn, không chứa từng dòng. Muốn biết "100 lần hỏng này đến từ MỘT
    IP hay từ 200 IP" thì phải có ai đó đếm lúc sự việc đang xảy ra — và đó
    chính là thứ phân biệt một cuộc dò mật khẩu với một đợt người dùng quên mật
    khẩu. Ba số này đi thẳng vào `MetricEvidence` của UC-3.

    Không có sự kiện nào trong cửa sổ thì trả ``(0, 0, 0.0)`` chứ không chia cho
    0.
    """
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
    """Tính ba con số từ hàng đợi sự kiện. Chỉ gọi khi đang giữ ``auth_failure_lock``.

    Tách riêng khỏi `_auth_failure_snapshot()` để phần tính toán không nằm lẫn
    trong khối `with lock` dài — và để test gọi thẳng được mà không phải dựng
    khoá.
    """
    sources = Counter(source for _, source, _ in auth_failure_events)
    accounts = {account for _, _, account in auth_failure_events}
    top_source_ratio = max(sources.values()) / len(auth_failure_events)
    return len(sources), len(accounts), top_source_ratio


def _record_auth_failure(source_ip: str, account: str) -> None:
    """Ghi một lần đăng nhập hỏng, đồng thời dọn các sự kiện đã quá cửa sổ.

    Dọn ngay lúc ghi chứ không chạy tác vụ nền: hàng đợi chỉ lớn lên khi có
    người đăng nhập hỏng, nên đúng lúc đó cũng là lúc rẻ nhất để cắt đuôi. Không
    dọn thì một đợt dò mật khẩu 10 phút sẽ để lại hàng chục nghìn phần tử trong
    RAM, và tỷ lệ IP tính ra sẽ trải trên cả 10 phút thay vì 1 phút.
    """
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
    """Mở connection pool lúc khởi động, đóng lúc tắt.

    ## Vì sao pool chỉ tạo MỘT LẦN và không thử lại

    Đây là hành vi của một service thật, và nó tạo ra một cái bẫy quen thuộc lúc
    demo: **Postgres restart sau khi service đã lên thì pool chết vĩnh viễn**,
    và `/pay` trả 503 "Pool chưa khởi tạo" cho tới khi ai đó restart service.

    Giữ nguyên chứ không thêm vòng thử lại, vì hai lý do:

    1. `docker-compose.demo.yml` đã khai `depends_on` kèm điều kiện healthcheck —
       thứ tự khởi động là việc của trình điều phối, không phải của mã ứng dụng.
    2. Pool 5 connection là **hạt nhân của UC-1**. Thêm logic tự phục hồi vào
       đây là bắt đầu che đi chính cái nghẽn mà bài toán cần thấy.

    Vấp lỗi này thì chạy:
    ``docker compose -f docker-compose.demo.yml restart service-thanh-toan``

    Không kết nối được lúc khởi động thì service **vẫn lên** — cố ý, để
    `/metrics` còn sống và Prometheus không mất luôn tín hiệu `up`.
    """
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
    """Thân request của ``POST /pay``.

    ``amount`` bắt buộc lớn hơn 0 — không phải để bảo mật, mà để một payload sai
    bị chặn ở tầng validate và trả 422, thay vì đi tới tận Postgres rồi hỏng ở
    đó. Request 422 không chạm database nên không tính vào p95 của đường xử lý
    thật; nhờ vậy bắn tải bằng payload sai sẽ KHÔNG tạo được sự cố giả.
    """

    order_id: str
    amount: int = Field(..., gt=0)


class LoginRequest(BaseModel):
    """Thân request của ``POST /login`` — đường vào của UC-3 (dò mật khẩu).

    Không có ràng buộc độ dài hay độ mạnh: endpoint này tồn tại để **bị tấn
    công**, và mọi lần hỏng đều được đếm vào thống kê 1 phút. Thêm luật chặn ở
    đây là làm mất chính tín hiệu mà UC-3 cần.
    """

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
                "pool_in_use=%d pool_size=%d",
                in_use, POOL_SIZE,
            )
        async with pool.acquire() as conn:
            # get_size() = số connection ĐÃ TẠO, không phải trần POOL_SIZE
            db_pool_in_use.set(pool.get_size() - pool.get_idle_size())

            # UC-4 fail NGAY, trước cả pg_sleep.
            #
            # `pg_sleep` là thiết bị nhân tạo dành riêng cho UC-1 (làm pool cạn).
            # Để nó chạy trước câu INSERT lỗi thì UC-4 vẫn phải xếp hàng chờ pool
            # rồi mới chết, nên p95 vẫn cao — đo ngày 11/08: 4,35s. Mất đúng đặc
            # điểm làm UC-4 đáng giá: metric thấy "hỏng" nhưng p95 GIẢM, khiến
            # luật chỉ nhìn độ trễ tưởng hệ thống vừa nhanh lên.
            #
            # Trong code thật sẽ không có pg_sleep, và lỗi schema nổ ngay lần
            # chạm database đầu tiên. Đặt trước là mô phỏng đúng hơn.
            if SIMULATE_MISSING_MIGRATION:
                row = await conn.fetchrow(
                    "INSERT INTO payments (order_id, amount, idempotency_key) "
                    "VALUES ($1, $2, $3) RETURNING id",
                    request.order_id,
                    request.amount,
                    str(uuid.uuid4()),
                )
                return {"ok": True, "payment_id": str(row["id"])}

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
            "asyncpg.TooManyConnectionsError pool_size=%d path=/pay",
            POOL_SIZE,
        )
        raise HTTPException(503, "Connection pool cạn kiệt")
    except Exception as exc:
        logger.error(
            "unhandled exception path=/pay order_id=%s %s: %s",
            request.order_id, type(exc).__name__, exc,
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
        "batch_retained=%d rows_retained=%d rss_mb=%.1f",
        total_batches, total_rows, _rss_mb(),
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
            "login failed status=401 source_ip=%s username=%s",
            source_ip, payload.username,
        )
        raise HTTPException(401, "Sai tài khoản hoặc mật khẩu")

    return {"ok": True, "token": "fake-token"}


@app.get("/health")
async def health() -> dict:
    """Kiểm tra sống — dùng cho ``depends_on`` của compose và lúc dựng demo.

    ⚠️ Cố ý trả ``ok`` kể cả khi ``pool is None``. Đây là kiểm tra **tiến trình
    còn sống**, không phải kiểm tra **phục vụ được**. Trộn hai thứ vào một
    endpoint thì compose sẽ giết và dựng lại container mỗi lần Postgres chớp —
    biến một sự cố database thành một crash-loop giả, đúng thứ UC-2 đang đo.

    Muốn biết có phục vụ được không thì gọi thẳng ``POST /pay``: pool chết thì
    nó trả 503.
    """
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
