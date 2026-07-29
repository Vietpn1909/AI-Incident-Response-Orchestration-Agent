"""Bắn tải tăng dần để tạo sự cố thật.

CHỦ SỞ HỮU: Trung

Chạy:
    python demo/loadtest.py              # profile demo, ~3 phút
    python demo/loadtest.py --full       # profile đầy đủ, tới 100k request

Có thể thay bằng k6 hoặc Locust nếu muốn — miễn là tải TĂNG DẦN. Tải phẳng
không cho thấy latency tăng theo tải, mà biểu đồ tăng dần mới là thứ thuyết
phục người xem (xem ADR-0003).
"""

from __future__ import annotations

import argparse
import asyncio
import time

import httpx

PAYMENT_URL = "http://localhost:8001/pay"
ORDER_URL = "http://localhost:8002/orders"

# (số request đồng thời, số giây giữ mức đó)
# Tăng dần từng bậc để thấy p95 leo theo tải.
PROFILE_DEMO = [(5, 20), (20, 20), (50, 30), (100, 40), (200, 40)]
PROFILE_FULL = [(5, 30), (20, 30), (50, 60), (100, 60), (200, 90), (400, 120)]


async def one_request(client: httpx.AsyncClient, index: int) -> tuple[int, float]:
    """Gửi một request, trả (status_code, thời gian tính bằng giây).

    TODO(Trung):
      POST tới PAYMENT_URL với body {"order_id": f"load-{index}", "amount": 100}
      Đo thời gian bằng time.perf_counter(). Bắt mọi exception và trả
      (0, elapsed) để timeout cũng được tính vào thống kê.
    """
    raise NotImplementedError("TODO(Trung): xem docstring")


async def run_stage(concurrency: int, seconds: int) -> None:
    """Giữ `concurrency` request đồng thời trong `seconds` giây.

    TODO(Trung):
      1. Tạo httpx.AsyncClient với timeout khoảng 10s
      2. Vòng lặp tới khi hết `seconds`: mỗi vòng tạo `concurrency` task
         one_request rồi asyncio.gather
      3. Gom kết quả, in ra sau mỗi bậc:
             concurrency, tổng request, p95 (giây), tỷ lệ lỗi (%)
         p95 tính bằng sorted(times)[int(len(times) * 0.95)]
      4. In cảnh báo khi p95 vượt 2s — đó là ngưỡng Agent dùng để mở incident
    """
    raise NotImplementedError("TODO(Trung): xem docstring")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="profile đầy đủ, lâu hơn")
    args = parser.parse_args()

    profile = PROFILE_FULL if args.full else PROFILE_DEMO
    total_seconds = sum(seconds for _, seconds in profile)
    print(f"Bắt đầu bắn tải — {len(profile)} bậc, khoảng {total_seconds}s")
    print("Mở http://localhost:9090 và theo dõi:")
    print("  histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[1m])) by (le, service))\n")

    started = time.perf_counter()
    for concurrency, seconds in profile:
        await run_stage(concurrency, seconds)
    print(f"\nXong sau {time.perf_counter() - started:.0f}s")
    print("⚠️  Ghi lại mức tải làm p95 vượt 2s vào demo/README.md")


if __name__ == "__main__":
    asyncio.run(main())
