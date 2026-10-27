"""Bắn tải vào ĐÚNG MỘT service — để mỗi lần diễn có một phiếu Jira riêng.

    python scripts/ban_mot_service.py pay 30 90
    python scripts/ban_mot_service.py kho 25 90
    python scripts/ban_mot_service.py van 25 90

Ba tham số: tên dịch vụ, số request song song, số giây.

## Vì sao không dùng `demo/loadtest.py`

File đó **cố ý** cho 1/4 request đi qua `/orders`, mà `/orders` gọi chéo sang
`/pay`. Hai service cùng chậm một lúc, `link_incidents()` nhận ra dạng lan
truyền và nối hai phiếu lại thành một sự cố. Đúng thiết kế — đó là thứ đáng khoe
khi diễn UC-1.

Nhưng khi cần **ba trường hợp HITL tách bạch**, mỗi trường hợp một phiếu độc
lập, thì đúng cái hay đó lại thành phiền: trường hợp 1 mở hai phiếu dính nhau,
và không còn cách nào diễn trường hợp 2 trên một phiếu sạch.

## Chỉ `pay` mới mở được sự cố độc lập một cách chắc chắn

`service-thanh-toan` là service duy nhất có pool asyncpg thật, nên nó nghẽn theo
đúng cơ chế thật khi tải cao. `kho-hang` và `van-chuyen` dùng `asyncio.sleep()`
— không chặn luồng, nên đo ngày 24/08 ở concurrency 150 p95 vẫn chỉ 0,242 giây,
dưới xa ngưỡng P3. Bắn vào chúng gần như không bao giờ mở được phiếu.
"""

from __future__ import annotations

import asyncio
import sys
import time

import httpx

#: tên gọi tắt → (URL, hàm dựng payload)
DICH_VU = {
    "pay": (
        "http://localhost:8001/pay",
        lambda i: {"order_id": f"demo-{i}", "amount": 100},
    ),
    "kho": (
        "http://localhost:8003/check-stock",
        lambda i: {"item_id": f"item-00{i % 5 + 1}", "quantity": 1},
    ),
    "van": (
        "http://localhost:8004/calculate-shipping",
        lambda i: {
            "destination": ["HCM", "HN", "DN"][i % 3],
            "weight_kg": 1.0 + i % 5,
            "method": ["standard", "express", "same_day"][i % 3],
        },
    ),
}


async def ban(ten: str, concurrency: int, giay: int) -> None:
    """Bắn `concurrency` request song song vào một service, trong `giay` giây."""
    url, dung_payload = DICH_VU[ten]
    print(f"Ban vao {url} — concurrency {concurrency}, {giay}s")

    do_tre: list[float] = []
    loi = 0
    bat_dau = time.perf_counter()
    chi_so = 0

    async with httpx.AsyncClient(timeout=15.0) as client:
        while time.perf_counter() - bat_dau < giay:

            async def mot(i: int) -> None:
                nonlocal loi
                t0 = time.perf_counter()
                try:
                    r = await client.post(url, json=dung_payload(i))
                    if r.status_code != 200:
                        loi += 1
                except Exception:
                    loi += 1
                do_tre.append(time.perf_counter() - t0)

            await asyncio.gather(*(mot(chi_so + k) for k in range(concurrency)))
            chi_so += concurrency
            await asyncio.sleep(0.02)

    # p95 phía client, KHÔNG phải p95 mà Agent nhìn. Agent đọc
    # `http_request_duration_seconds` do chính service tự đo, không tính thời gian
    # request nằm chờ trong hàng đợi của máy chạy script. Con số dưới đây luôn cao
    # hơn, và chỉ dùng để biết đã bắn đủ mạnh chưa.
    xep = sorted(do_tre)
    p95 = xep[min(int(len(xep) * 0.95), len(xep) - 1)] if xep else 0
    print(f"Tong req: {len(do_tre)} | p95 phia client: {p95:.3f}s | Loi: {loi}")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")

    if len(sys.argv) != 4 or sys.argv[1] not in DICH_VU:
        print(f"Dung: python scripts/ban_mot_service.py [{'|'.join(DICH_VU)}] <concurrency> <giay>")
        sys.exit(2)

    asyncio.run(ban(sys.argv[1], int(sys.argv[2]), int(sys.argv[3])))
