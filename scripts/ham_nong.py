"""Hâm nóng 4 service ở mức tải THẤP — để Prometheus có series, KHÔNG mở sự cố.

    python scripts/ham_nong.py 75

## Vì sao cần

Prometheus mới khởi động thì mọi counter đều rỗng. Hệ quả nhìn thấy được ngay:

- Biểu đồ trên status page trắng trơn — không phải hỏng, chỉ là chưa có điểm nào
  để vẽ. Nhưng người xem demo không phân biệt được hai thứ đó.
- Agent log đầy dòng `PromQL không trả series nào`, và `detect()` bỏ qua mọi
  service vì không có gì để so.
- Baseline p95 cần `BASELINE_MIN_SAMPLES = 20` điểm trong cửa sổ 30 phút mới
  đáng tin. Chưa đủ điểm thì nhánh phát hiện "lệch baseline" (mức P4) coi như
  không tồn tại.

## Vì sao KHÔNG dùng `demo/loadtest.py`

File đó ramp lên tới hàng trăm concurrent và **cố ý** đẩy p95 vượt ngưỡng — đó
là việc của nó, để tạo sự cố cho demo. Chạy nó lúc chuẩn bị là mở một phiếu Jira
ngay trước giờ diễn.

Ở đây giữ concurrency 3 cho mỗi service. Đo ngày 25/08 trên máy demo: 1344
request, 0 lỗi, chậm nhất 0,45 giây — dưới xa ngưỡng P3 (p95 > 1 giây), nên Agent
vẫn báo "bình thường" suốt.
"""

from __future__ import annotations

import asyncio
import sys
import time

import httpx

#: Mỗi dòng: URL + hàm dựng payload hợp lệ cho service đó.
#:
#: Payload phải ĐÚNG SCHEMA, không phải bừa: request 422 vẫn tính là traffic cho
#: `http_requests_total` nhưng không đi qua đường xử lý thật, nên p95 đo được sẽ
#: thấp giả tạo và baseline dựng trên đó là baseline của một hệ thống không làm
#: gì cả.
DICH_VU = [
    ("http://localhost:8001/pay", lambda i: {"order_id": f"warm-{i}", "amount": 100}),
    ("http://localhost:8002/orders", lambda i: {"items": [f"sku-{i % 5}"], "amount": 100}),
    (
        "http://localhost:8003/check-stock",
        lambda i: {"item_id": f"item-00{i % 5 + 1}", "quantity": 1},
    ),
    (
        "http://localhost:8004/calculate-shipping",
        lambda i: {
            "destination": ["HCM", "HN", "DN"][i % 3],
            "weight_kg": 1.0 + i % 5,
            "method": ["standard", "express", "same_day"][i % 3],
        },
    ),
]

#: Số request song song mỗi service mỗi nhịp. Giữ THẤP là chủ đích — xem docstring
#: đầu file. Nâng lên quá 10 là bắt đầu có nguy cơ mở sự cố thật.
CONCURRENCY = 3

#: Nghỉ giữa hai nhịp. Không có nó thì vòng lặp quay hết tốc lực và biến bài hâm
#: nóng thành bài kiểm tra tải.
NHIP_NGHI_GIAY = 0.25


async def ham_nong(giay: int, concurrency: int = CONCURRENCY) -> int:
    """Bắn tải nhẹ trong `giay` giây. Trả về số request đã gửi."""
    bat_dau = time.perf_counter()
    dem = loi = 0
    cham_nhat = 0.0
    nhip = 0

    async with httpx.AsyncClient(timeout=10.0) as client:
        while time.perf_counter() - bat_dau < giay:

            async def mot_request(url: str, payload: dict) -> None:
                nonlocal dem, loi, cham_nhat
                t0 = time.perf_counter()
                try:
                    r = await client.post(url, json=payload)
                    if r.status_code != 200:
                        loi += 1
                except Exception:
                    # Nuốt lỗi mạng: đây là bài hâm nóng, không phải bài kiểm tra.
                    # Một service chưa kịp lên không đáng làm dừng cả script.
                    loi += 1
                cham_nhat = max(cham_nhat, time.perf_counter() - t0)
                dem += 1

            await asyncio.gather(
                *(
                    mot_request(url, dung_payload(nhip + k))
                    for k, (url, dung_payload) in enumerate(DICH_VU)
                    for _ in range(concurrency)
                )
            )
            nhip += 1
            await asyncio.sleep(NHIP_NGHI_GIAY)

    print(f"Ham nong xong: {dem} request, {loi} loi, cham nhat {cham_nhat:.3f}s")
    if loi:
        print("  !! Co loi — kiem tra `docker ps` va thu `docker compose restart`")
    return dem


if __name__ == "__main__":
    # Console Windows mặc định CP1252 nên mọi dòng print tiếng Việt đều chết bằng
    # UnicodeEncodeError. Ép UTF-8 trước — cùng cách `demo/attack.py` đang làm.
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")

    so_giay = int(sys.argv[1]) if len(sys.argv) > 1 else 75
    asyncio.run(ham_nong(so_giay))
