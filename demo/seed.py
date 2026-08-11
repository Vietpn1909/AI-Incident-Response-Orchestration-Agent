"""Tạo schema và sinh dữ liệu mẫu cho demo.

CHỦ SỞ HỮU: Trung

Chạy một lần sau khi Postgres đã lên:
    python demo/seed.py

Vì sao cần dữ liệu: truy vấn trên bảng trống thì luôn nhanh, không lộ được độ
chậm khi tải tăng. Cần vài nghìn dòng để truy vấn có "trọng lượng" thật.
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
from datetime import UTC, datetime, timedelta

import asyncpg

# Đọc .env TRƯỚC khi lấy DATABASE_URL.
#
# Trước đây file này chỉ gọi `os.getenv`, tức chỉ thấy biến của shell chứ không
# thấy file `.env` — khác với phần còn lại của dự án (dùng pydantic-settings, có
# đọc `.env`). Hậu quả đo được ngày 11/08: máy đã có container Postgres khác giữ
# port 5432 nên stack demo phải chạy ở `DEMO_POSTGRES_PORT=55432` và `.env` ghi
# đúng 55432, nhưng seed vẫn rơi về mặc định 5432, nối sang Postgres LẠ và chết
# bằng `InvalidPasswordError: password authentication failed for user "demo"` —
# một thông báo trỏ hoàn toàn sai chỗ, vì mật khẩu chưa bao giờ là vấn đề.
#
# `override=False`: biến đặt sẵn ở shell vẫn thắng file, để dòng lệnh một lần
# `DATABASE_URL=... python demo/seed.py` còn dùng được.
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), os.pardir, ".env"), override=False)
except ImportError:
    # demo/ chạy được độc lập, không bắt buộc có python-dotenv.
    pass

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://demo:demo@localhost:5432/demo")

ROWS_ORDERS = 3_000
ROWS_PAYMENTS = 5_000

# ⚠️ CỐ Ý không tạo index trên payments(order_id). Truy vấn lọc theo cột đó sẽ
# phải scan toàn bảng, nên càng nhiều dữ liệu càng chậm — đó là nguyên nhân thứ
# hai để Agent chẩn đoán, cạnh việc pool cạn. Xem ADR-0003.
SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id          SERIAL PRIMARY KEY,
    order_id    TEXT NOT NULL,
    customer    TEXT NOT NULL,
    amount      INTEGER NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS payments (
    id          SERIAL PRIMARY KEY,
    order_id    TEXT NOT NULL,      -- KHÔNG có index: chủ đích
    amount      INTEGER NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Lịch sử deploy giả lập. Agent đối chiếu thời điểm incident với bảng này để
-- tìm ra "có deploy nào ngay trước sự cố không".
CREATE TABLE IF NOT EXISTS deploy_history (
    id           SERIAL PRIMARY KEY,
    service      TEXT NOT NULL,
    version      TEXT NOT NULL,
    deployed_at  TIMESTAMPTZ NOT NULL,
    deployed_by  TEXT NOT NULL DEFAULT 'ci-bot',
    commit_sha   TEXT NOT NULL DEFAULT '',
    -- Ghi chú thay đổi, kiểu release note. Đây là dữ liệu PHI CẤU TRÚC duy nhất
    -- Agent có — luật không đọc được, chỉ LLM đọc được.
    --
    -- ⚠️ Viết như release note thật: tả TÍNH NĂNG, không tả thứ còn thiếu.
    -- Bản nháp đầu ghi "cần chạy migration thêm cột idempotency_key" và đo thật
    -- cho thấy LLM trả lời đúng MÀ KHÔNG CẦN LOG — tức ghi chú đã nói hộ đáp án,
    -- đúng lỗi mà 5 dòng log nhãn chẩn đoán đang mắc.
    change_note  TEXT NOT NULL DEFAULT ''
);
"""


async def main() -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(SCHEMA)
    print("[OK] Da tao schema (orders, payments, deploy_history)")

    # Xoá sạch trước khi nạp — seed phải LẶP LẠI ĐƯỢC.
    #
    # Trước bản vá này seed chỉ INSERT, nên chạy lần hai là dữ liệu cộng dồn. Đo
    # ngày 11/08: lần một 3.000 orders / 5.002 payments / 4 deploy, lần hai thành
    # 6.000 / 16.973 / 8 — và `deploy_history` có v1.4.2 lẫn v1.4.3 xuất hiện HAI
    # lần ở hai mốc thời gian khác nhau.
    #
    # Hai hậu quả, cả hai đều đánh vào buổi demo:
    #   1. Bảng payments không có index là chủ đích, nên càng nhiều dòng truy vấn
    #      càng chậm — mức tải cần để p95 vượt ngưỡng đổi theo số lần đã seed.
    #      Con số ghi trong demo/README.md thành sai.
    #   2. Agent tìm "deploy ngay trước sự cố" trên bảng có phiên bản trùng. Lần
    #      đo này đích rollback vẫn đúng nhờ mỗi lượt seed chèn theo cùng một thứ
    #      tự tương đối, nhưng đó là may, không phải thiết kế.
    #
    # TRUNCATE ... RESTART IDENTITY để SERIAL cũng về 1, cho mọi lần chạy giống
    # nhau tới cả id.
    await conn.execute("TRUNCATE orders, payments, deploy_history RESTART IDENTITY")
    print("[OK] Da xoa du lieu cu (seed lap lai duoc)")

    # 1. Sinh dữ liệu mẫu bằng Faker / Random
    try:
        from faker import Faker
        fake = Faker()
    except ImportError:
        fake = None

    now = datetime.now(UTC)

    # Sinh 3000 dòng orders
    orders_data = []
    for i in range(1, ROWS_ORDERS + 1):
        cust = fake.name() if fake else f"Customer {i}"
        amt = random.randint(50, 500)
        orders_data.append((str(i), cust, amt, now - timedelta(minutes=random.randint(10, 1000))))

    await conn.executemany(
        "INSERT INTO orders (order_id, customer, amount, created_at) VALUES ($1, $2, $3, $4)",
        orders_data,
    )

    # Sinh 5000 dòng payments
    payments_data = []
    for i in range(1, ROWS_PAYMENTS + 1):
        ord_id = str(random.randint(1, ROWS_ORDERS))
        amt = random.randint(50, 500)
        payments_data.append((ord_id, amt, now - timedelta(minutes=random.randint(1, 500))))

    await conn.executemany(
        "INSERT INTO payments (order_id, amount, created_at) VALUES ($1, $2, $3)",
        payments_data,
    )

    # 2. Sinh deploy_history. Hai nghi phạm cố ý:
    #    - v1.4.2 cách đây 4 phút  → UC-1 (pool cạn)
    #    - v1.4.3 cách đây 3 phút  → UC-4 (thiếu migration)
    #
    # ⚠️ `change_note` tả TÍNH NĂNG, không tả thứ còn thiếu. Xem chú thích ở
    # schema — ghi chú gợi ý sẵn làm log thành thừa và phá phép đo.
    deploys = [
        ("service-thanh-toan", "v1.4.1", now - timedelta(days=2), "ci-bot", "a1b2c3d",
         "Thêm chỉ mục cho bảng payments để tăng tốc truy vấn đối soát."),
        ("service-dat-hang", "v2.1.0", now - timedelta(days=1), "ci-bot", "e5f6g7h",
         "Chuyển gọi service thanh toán sang HTTP client có timeout."),
        ("service-thanh-toan", "v1.4.2", now - timedelta(minutes=4), "ci-bot", "9f2c1ab",
         "Gộp batch job đối soát vào chung connection pool với API để giảm số kết "
         "nối tới Postgres. Batch chạy mỗi 5 phút."),
        ("service-thanh-toan", "v1.4.3", now - timedelta(minutes=3), "ci-bot", "7d4e9f1",
         "Thêm chống trùng giao dịch cho endpoint /pay bằng khoá idempotency."),
    ]

    await conn.executemany(
        "INSERT INTO deploy_history (service, version, deployed_at, deployed_by, commit_sha, change_note) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        deploys,
    )

    count_orders = await conn.fetchval("SELECT count(*) FROM orders")
    count_payments = await conn.fetchval("SELECT count(*) FROM payments")
    count_deploys = await conn.fetchval("SELECT count(*) FROM deploy_history")

    print(f"[OK] Da seed thanh cong: {count_orders} orders, {count_payments} payments, {count_deploys} deploy history records.")
    await conn.close()


if __name__ == "__main__":
    # Console Windows mặc định CP1252 — xem chú thích trong attack.py.
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    asyncio.run(main())
