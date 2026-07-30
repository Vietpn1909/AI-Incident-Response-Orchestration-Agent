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
    """Gửi một request, trả (status_code, thời gian tính bằng giây)."""
    start_t = time.perf_counter()
    try:
        resp = await client.post(
            PAYMENT_URL,
            json={"order_id": f"load-{index}", "amount": 100},
        )
        elapsed = time.perf_counter() - start_t
        return resp.status_code, elapsed
    except Exception:
        elapsed = time.perf_counter() - start_t
        return 0, elapsed


async def run_stage(concurrency: int, seconds: int) -> None:
    """Giữ `concurrency` request đồng thời trong `seconds` giây."""
    print(f"🚀 [STAGE] Concurrency: {concurrency:3d} | Thời gian: {seconds}s")
    times: list[float] = []
    statuses: list[int] = []

    stage_start = time.perf_counter()
    req_index = 0

    async with httpx.AsyncClient(timeout=10.0) as client:
        while time.perf_counter() - stage_start < seconds:
            tasks = [one_request(client, req_index + i) for i in range(concurrency)]
            req_index += concurrency

            results = await asyncio.gather(*tasks)
            for status, elapsed in results:
                statuses.append(status)
                times.append(elapsed)

            await asyncio.sleep(0.05)  # Tránh tràn loop quá nhanh

    if not times:
        print("⚠️  Không có request nào được hoàn thành.")
        return

    sorted_times = sorted(times)
    p95_idx = int(len(sorted_times) * 0.95)
    p95 = sorted_times[min(p95_idx, len(sorted_times) - 1)]

    err_count = sum(1 for status in statuses if status != 200)
    err_rate = (err_count / len(statuses)) * 100 if statuses else 0.0

    print(
        f"📊 [KẾT QUẢ] Concurrency: {concurrency:3d} | Tổng req: {len(times):5d} | "
        f"p95: {p95:.3f}s | Lỗi: {err_rate:.1f}%"
    )

    if p95 > 2.0:
        print(f"⚠️  [CẢNH BÁO] p95 ({p95:.3f}s) đã VƯỢT NGƯỠNG 2.0s! Agent của Việt sẽ kích hoạt mở Incident!\n")
    else:
        print()


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
