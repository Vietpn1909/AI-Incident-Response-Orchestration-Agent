"""Bắn burst đăng nhập sai để tạo UC-3 (credential-stuffing giả lập).

Chỉ chạy local với demo stack:
    python demo/attack.py

Mặc định script gửi xấp xỉ 200 request/giây trong 60 giây. Request được rải
đều theo thời gian và số task chờ được chặn trần, tránh biến UC-3 thành một bài
test quá tải ngoài ý muốn. Kết quả đúng là phần lớn response có status 401,
trong khi latency, lỗi 5xx và connection pool vẫn bình thường.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
import time
from collections import Counter

import httpx

DEFAULT_URL = "http://localhost:8001/login"
DEFAULT_RATE = 200.0
DEFAULT_DURATION = 60.0


async def _send_failed_login(
    client: httpx.AsyncClient,
    url: str,
    request_number: int,
    statuses: Counter[int],
) -> None:
    """Gửi một lần đăng nhập sai và ghi nhận status; không làm vỡ cả đợt bắn."""
    try:
        response = await client.post(
            url,
            json={
                "username": "demo",
                "password": f"sai-{request_number}-{secrets.token_hex(4)}",
            },
        )
        statuses[response.status_code] += 1
    except httpx.HTTPError:
        # Status 0 biểu diễn timeout/connection error ở phía client.
        statuses[0] += 1


async def run_attack(
    url: str = DEFAULT_URL,
    rate: float = DEFAULT_RATE,
    duration: float = DEFAULT_DURATION,
) -> tuple[Counter[int], float]:
    """Bắn request theo nhịp cố định và trả (thống kê status, thời gian thực)."""
    if rate <= 0:
        raise ValueError("rate phải lớn hơn 0")
    if duration <= 0:
        raise ValueError("duration phải lớn hơn 0")

    total_requests = max(1, round(rate * duration))
    max_connections = max(20, min(100, round(rate / 2)))
    max_pending = max(100, round(rate * 2))
    statuses: Counter[int] = Counter()
    pending: set[asyncio.Task[None]] = set()
    started = time.perf_counter()

    limits = httpx.Limits(
        max_connections=max_connections,
        max_keepalive_connections=max_connections,
    )
    async with httpx.AsyncClient(timeout=5.0, limits=limits) as client:
        for request_number in range(total_requests):
            target_time = started + request_number / rate
            delay = target_time - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)

            # Khi service phản hồi chậm, chờ bớt task thay vì để hàng nghìn task
            # tích tụ ở client rồi vô tình biến UC-3 thành bài test quá tải.
            if len(pending) >= max_pending:
                await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

            task = asyncio.create_task(
                _send_failed_login(client, url, request_number, statuses)
            )
            pending.add(task)
            task.add_done_callback(pending.discard)

        if pending:
            await asyncio.gather(*pending)

    return statuses, time.perf_counter() - started


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tạo burst đăng nhập sai cho UC-3")
    parser.add_argument("--url", default=DEFAULT_URL, help="URL endpoint /login")
    parser.add_argument("--rate", type=float, default=DEFAULT_RATE, help="request/giây")
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION, help="số giây chạy")
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    expected = max(1, round(args.rate * args.duration))
    print(
        f"Bắt đầu UC-3: {args.rate:g} request/giây × {args.duration:g}s "
        f"= khoảng {expected} request tới {args.url}"
    )

    statuses, elapsed = await run_attack(args.url, args.rate, args.duration)
    completed = sum(statuses.values())
    actual_rate = completed / elapsed if elapsed else 0.0

    print(f"Xong sau {elapsed:.1f}s — {completed} request ({actual_rate:.1f} request/giây)")
    print(f"Status: {dict(sorted(statuses.items()))}")
    if actual_rate < args.rate * 0.9:
        print(
            "⚠️ Tốc độ thực thấp hơn mục tiêu. Trên Windows, hãy chạy script "
            "trong service-dat-hang theo hướng dẫn ở demo/README.md để tránh bottleneck Docker NAT."
        )
    if statuses[401] != completed:
        print("⚠️ Có response không phải 401; kiểm tra service và Docker trước khi lấy số liệu eval.")


if __name__ == "__main__":
    # Windows có thể mặc định dùng CP1252, khiến argparse/print lỗi khi gặp
    # tiếng Việt. Ép UTF-8 để script chạy giống nhau trên máy của cả đội.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    asyncio.run(_main())
