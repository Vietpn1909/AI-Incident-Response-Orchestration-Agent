"""Bắn tải tăng dần để tạo sự cố thật.

CHỦ SỞ HỮU: Trung

Chạy:
    python demo/loadtest.py              # profile demo an toàn, ~1,5 phút
    python demo/loadtest.py --full       # profile nặng, chỉ dùng trên máy đủ mạnh

Có thể thay bằng k6 hoặc Locust nếu muốn — miễn là tải TĂNG DẦN. Tải phẳng
không cho thấy latency tăng theo tải, mà biểu đồ tăng dần mới là thứ thuyết
phục người xem (xem ADR-0003).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

import httpx

PAYMENT_URL = "http://localhost:8001/pay"
ORDER_URL = "http://localhost:8002/orders"

# (số request đồng thời, số giây giữ mức đó)
# Tăng dần từng bậc để thấy p95 leo theo tải. Sau khi /pay giữ connection 0.2s,
# 75 concurrent đã đủ làm pool 5 chỗ cạn và p95 server-side vượt 2s. Không cần
# đẩy mặc định lên 200 vì Docker Desktop + load client có thể làm máy demo đơ.
PROFILE_DEMO = [(5, 10), (15, 15), (30, 20), (50, 20), (75, 25)]

# Profile nặng là opt-in để đo giới hạn, không dùng trong buổi demo thông thường.
PROFILE_FULL = [(5, 30), (20, 30), (50, 60), (100, 60), (200, 90), (400, 120)]


#: Mỗi request thứ mấy thì đi qua `/orders` thay vì gọi `/pay` trực tiếp.
#:
#: `ORDER_URL` đã được khai từ đầu nhưng KHÔNG hàm nào dùng, nên toàn bộ tải chỉ
#: rơi vào service-thanh-toan. Hậu quả đo được ngày 11/08: service-dat-hang
#: không có lưu lượng nào ngoài Prometheus scrape `/metrics`, mà `detect` lọc
#: `handler!="/metrics"` — nên nó không bao giờ vào diện quan sát.
#:
#: Điều đó làm mất hẳn phần lan truyền của demo: không có war room thứ hai, nên
#: `classify_severity` không nâng P2 → P1 theo contract ①, và `link_incidents`
#: không có gì để nối. Ba node im lặng vì thiếu tải, không vì code sai — kiểu
#: hỏng không test nào bắt được.
#:
#: 1 trong 4 là đủ: `/orders` gọi chéo sang `/pay` nên mỗi request loại này tạo
#: tải cho CẢ HAI service. Đẩy tỷ lệ lên cao hơn thì phần lớn tải đi qua một lần
#: nhảy HTTP nữa, và p95 đo được của service-thanh-toan không còn phản ánh mức
#: concurrency đã khai trong PROFILE_DEMO — tức làm sai lệch chính con số mà
#: bảng đo ở cuối README.md dựa vào.
_MOI_N_REQUEST_QUA_ORDERS = 4


async def one_request(client: httpx.AsyncClient, index: int) -> tuple[int, float]:
    """Gửi một request, trả (status_code, thời gian tính bằng giây)."""
    qua_orders = index % _MOI_N_REQUEST_QUA_ORDERS == 0
    url = ORDER_URL if qua_orders else PAYMENT_URL
    payload = (
        {"items": [f"sp-{index % 7}"], "amount": 100}
        if qua_orders
        else {"order_id": f"load-{index}", "amount": 100}
    )

    start_t = time.perf_counter()
    try:
        resp = await client.post(url, json=payload)
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
        f"p95 client: {p95:.3f}s | Lỗi: {err_rate:.1f}%"
    )

    if p95 > 2.0:
        print(
            f"⚠️  p95 client ({p95:.3f}s) đã vượt 2s; "
            "hãy xác nhận p95 server-side trên Prometheus.\n"
        )
    else:
        print()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--full",
        action="store_true",
        help="profile nặng tới 400 concurrent; không dùng trên máy demo yếu",
    )
    args = parser.parse_args()

    profile = PROFILE_FULL if args.full else PROFILE_DEMO
    total_seconds = sum(seconds for _, seconds in profile)
    print(f"Bắt đầu bắn tải — {len(profile)} bậc, khoảng {total_seconds}s")
    print("Mở http://localhost:9090 và theo dõi:")
    print(
        '  histogram_quantile(0.95, sum by (service, le) '
        '(rate(http_request_duration_seconds_bucket{handler!="/metrics"}[1m])))\n'
    )

    started = time.perf_counter()
    for concurrency, seconds in profile:
        await run_stage(concurrency, seconds)
    print(f"\nXong sau {time.perf_counter() - started:.0f}s")
    print("⚠️  Ghi mức tải làm p95 server-side vượt 2s vào demo/README.md")


if __name__ == "__main__":
    # Console Windows mặc định CP1252 nên `--help` và mọi dòng print tiếng Việt
    # đều chết bằng UnicodeEncodeError. Ép UTF-8 trước khi chạy — cùng cách
    # attack.py đang làm. 3/4 thành viên dùng Windows.
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    asyncio.run(main())
