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
from datetime import datetime, timezone, timedelta

import asyncpg

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
    commit_sha   TEXT NOT NULL DEFAULT ''
);
"""


async def main() -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(SCHEMA)
    print("[OK] Da tao schema (orders, payments, deploy_history)")

    # 1. Sinh dữ liệu mẫu bằng Faker / Random
    try:
        from faker import Faker
        fake = Faker()
    except ImportError:
        fake = None

    now = datetime.now(timezone.utc)

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

    # 2. Sinh dữ liệu deploy_history (Có 1 dòng deploy v1.4.2 cách đây 4 phút cho service-thanh-toan)
    deploys = [
        ("service-thanh-toan", "v1.4.1", now - timedelta(days=2), "ci-bot", "a1b2c3d"),
        ("service-dat-hang", "v2.1.0", now - timedelta(days=1), "ci-bot", "e5f6g7h"),
        ("service-thanh-toan", "v1.4.2", now - timedelta(minutes=4), "ci-bot", "9f2c1ab"),
    ]

    await conn.executemany(
        "INSERT INTO deploy_history (service, version, deployed_at, deployed_by, commit_sha) VALUES ($1, $2, $3, $4, $5)",
        deploys,
    )

    count_orders = await conn.fetchval("SELECT count(*) FROM orders")
    count_payments = await conn.fetchval("SELECT count(*) FROM payments")
    count_deploys = await conn.fetchval("SELECT count(*) FROM deploy_history")

    print(f"[OK] Da seed thanh cong: {count_orders} orders, {count_payments} payments, {count_deploys} deploy history records.")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
