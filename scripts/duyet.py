"""Kích webhook phê duyệt cho một issue — thay cho Jira Automation khi chưa bật rule.

CHỦ SỞ HỮU: Đức

    python scripts/duyet.py KAN-23

## Script này KHÔNG phải đường tắt qua cổng phê duyệt

Nó chỉ gọi đúng endpoint `POST /webhooks/jira` mà Jira Automation sẽ gọi, với
cùng payload. Ba lớp kiểm tra bên trong endpoint vẫn chạy nguyên vẹn:

    1. shared secret
    2. cổng HITL — người chuyển sang `Remediating` phải KHÁC account Agent
    3. thi hành, có gắn accountId người duyệt

Nên gõ lệnh này khi chưa ai duyệt thì vẫn bị từ chối, đúng như khi Jira tự gọi.
Nó thay cái *cầu nối* Jira→backend, không thay cái *cổng*.

## Vì sao cần

Đúng ra Jira tự gọi webhook khi issue sang `Remediating`, qua một Automation
rule (xem docs/jira-setup.md Phần 5). Rule đó chưa cấu hình, nên bước ấy còn
thiếu và phải kích tay.

Có thể gọi thẳng bằng curl, nhưng dòng lệnh đó dài và có phần trích secret từ
`.env` bằng shell — dễ gõ sai giữa buổi demo, và gõ sai thì thông báo trả về là
lỗi 401 chứ không nói rõ sai ở đâu. Script này in ra tiếng Việt tắc ở lớp nào.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.config import get_settings  # noqa: E402

MAC_DINH = "http://localhost:8000"


def main() -> int:
    parser = argparse.ArgumentParser(description="Kích webhook phê duyệt cho một issue Jira.")
    parser.add_argument("jira_key", help="ví dụ: KAN-23")
    parser.add_argument("--url", default=os.getenv("API_URL", MAC_DINH), help="gốc URL backend")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.jira_webhook_secret:
        print("❌ Thiếu JIRA_WEBHOOK_SECRET trong .env — webhook sẽ từ chối mọi lời gọi.")
        return 1

    dich = f"{args.url.rstrip('/')}/webhooks/jira"
    print(f"→ POST {dich}  (issue {args.jira_key})\n")

    try:
        reply = httpx.post(
            dich,
            headers={"X-Webhook-Secret": settings.jira_webhook_secret},
            json={"issue": {"key": args.jira_key}},
            timeout=60.0,
        )
    except httpx.HTTPError as loi:
        print(f"❌ Không gọi được backend ({loi}).")
        print("   Backend đã chạy chưa?  python -m uvicorn src.main:app --port 8000")
        return 1

    # Diễn giải theo từng lớp, để lúc demo biết ngay tắc ở đâu.
    if reply.status_code == 401:
        print("❌ Lớp 1 — sai shared secret. JIRA_WEBHOOK_SECRET trong .env khác bên backend.")
        return 1
    if reply.status_code == 403:
        print("⛔ Lớp 2 — CỔNG HITL TỪ CHỐI. Đây là hành vi ĐÚNG nếu chưa có người duyệt.")
        print(f"   {reply.json().get('detail', reply.text)}")
        print("\n   Sang Jira, chuyển issue sang 'Remediating' bằng account NGƯỜI")
        print("   (không phải account Agent), rồi chạy lại lệnh này.")
        return 2
    if reply.status_code != 200:
        print(f"❌ HTTP {reply.status_code}: {reply.text[:300]}")
        return 1

    data = reply.json()
    print("✅ QUA CỔNG — có người thật phê duyệt")
    print(f"   người duyệt : {data.get('approved_by')}")
    print(f"   hành động   : {data.get('action')} → {data.get('target')}")
    print(f"   kết quả     : thành công={data.get('succeeded')}")
    if data.get("simulated"):
        print("\n   ⚠️  simulated=true — hành động được ghi nhận nhưng KHÔNG đụng vào")
        print("      service thật.")
        if os.getenv("REMEDIATION_REAL", "").strip() == "1":
            # Bẫy đã vấp ngày 17/08, mất khoảng 15 phút để hiểu.
            print("\n   ❗ Bạn đặt REMEDIATION_REAL=1 cho LỆNH NÀY, nhưng nó không có")
            print("      tác dụng: script chỉ gửi HTTP, còn `executors` chạy trong")
            print("      tiến trình BACKEND. Cờ phải đặt ở đó:")
            print("\n        REMEDIATION_REAL=1 python -m uvicorn src.main:app --port 8000")
    return 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
