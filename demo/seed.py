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
    print("✅ đã tạo schema (orders, payments, deploy_history)")

    # TODO(Trung):
    #   1. Dùng Faker sinh ROWS_ORDERS dòng `orders` và ROWS_PAYMENTS dòng
    #      `payments`. Dùng `conn.executemany` hoặc `copy_records_to_table`
    #      cho nhanh, đừng insert từng dòng.
    #   2. Sinh vài dòng `deploy_history` cho cả 2 service, trong đó phải có
    #      MỘT dòng deploy cách thời điểm chạy demo chừng 3–5 phút — đó là
    #      "nghi phạm" để Agent tìm ra khi correlate.
    #   3. In ra số dòng đã tạo để verify.
    #
    # Xong là thế nào:
    #   psql $DATABASE_URL -c "SELECT count(*) FROM payments;"   -> >= 5000
    #   psql $DATABASE_URL -c "SELECT * FROM deploy_history;"    -> có dữ liệu

    print("⚠️  TODO(Trung): chưa sinh dữ liệu mẫu — xem TODO trong file này")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
