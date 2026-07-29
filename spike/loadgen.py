"""Sinh tải để pool 5 connection cạn — dùng cho spike, không thay k6/Locust.

Mục đích: tạo ra chênh lệch **thật** giữa lúc rảnh và lúc nghẽn, để verify
được rằng 4 câu PromQL của contract ① phân biệt được hai trạng thái đó. Nếu
không có tải thì mọi query đều trả ~0.08s và không chứng minh được gì.

    python spike/loadgen.py                 # 60 request đồng thời, 30 giây
    python spike/loadgen.py --concurrency 5 --seconds 15
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

import httpx

TARGET = "http://localhost:8001/pay"


async def _worker(client: httpx.AsyncClient, deadline: float, stats: dict[str, int]) -> None:
    while time.monotonic() < deadline:
        try:
            response = await client.post(TARGET)
            key = "ok" if response.status_code < 400 else f"http_{response.status_code}"
        except Exception:
            key = "loi_ket_noi"
        stats[key] = stats.get(key, 0) + 1


async def main(concurrency: int, seconds: int) -> None:
    # Console Windows mặc định cp1252, không in được tiếng Việt.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    stats: dict[str, int] = {}
    deadline = time.monotonic() + seconds
    started = time.monotonic()

    print(f"Bắn {concurrency} request đồng thời vào {TARGET} trong {seconds}s...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        await asyncio.gather(*(_worker(client, deadline, stats) for _ in range(concurrency)))

    elapsed = time.monotonic() - started
    total = sum(stats.values())
    print(f"Xong sau {elapsed:.1f}s — {total} request ({total / elapsed:.0f} req/s)")
    for key in sorted(stats):
        print(f"  {key}: {stats[key]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sinh tải cho spike")
    parser.add_argument("--concurrency", type=int, default=60, help="Số request đồng thời")
    parser.add_argument("--seconds", type=int, default=30, help="Chạy trong bao lâu")
    args = parser.parse_args()
    asyncio.run(main(args.concurrency, args.seconds))
