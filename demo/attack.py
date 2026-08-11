"""Bắn request giả lập các kịch bản tấn công bảo mật & sự cố.

Hỗ trợ 3 chế độ:
  1. brute-force (UC-3): Burst đăng nhập sai vào /login (status 401).
  2. stealth-exfiltration: Rút dữ liệu qua API hợp lệ (status 200 OK), mô phỏng lộ token.
  3. direct-db-scrape: Nối trực tiếp Postgres port 5432 truy xuất dữ liệu, bypass app logs.
  4. rce-inject: Vô hiệu hoá Python logging rồi hoạt động âm thầm.
  5. log-tampering: Redirect stdout/stderr sang /dev/null ở tầng OS.
  6. oom-kill: Gây OOM Kill (SIGKILL 137) tức thời khiến app không kịp ghi log.
  7. connection-starvation: Chiếm dụng hết DB connection, app treo vĩnh viễn không ném lỗi.

Ví dụ sử dụng:
    python demo/attack.py --mode brute-force
    python demo/attack.py --mode stealth-exfiltration --rate 100 --duration 30
    python demo/attack.py --mode direct-db-scrape --duration 20
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
import time
from collections import Counter

import asyncpg
import httpx

DEFAULT_URL = "http://localhost:8001/login"
DEFAULT_RATE = 200.0
DEFAULT_DURATION = 60.0
DEFAULT_ACCOUNTS = 100

# Đọc .env trước khi lấy DATABASE_URL — cùng lý do và cùng cách như demo/seed.py.
# Máy nào đã có Postgres khác giữ port 5432 thì stack demo chạy ở port lệch, và
# nếu chỉ dựa vào `os.getenv` thì file này nối sang database LẠ rồi báo sai mật
# khẩu, một thông báo trỏ hoàn toàn sai chỗ.
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), os.pardir, ".env"), override=False)
except ImportError:
    pass

DEFAULT_DB_URL = os.getenv("DATABASE_URL", "postgresql://demo:demo@localhost:5432/demo")


def _account_for_request(request_number: int, account_count: int) -> str:
    if account_count <= 0:
        raise ValueError('accounts phải lớn hơn 0')
    return f'demo-account-{request_number % account_count:04d}'


async def _send_failed_login(
    client: httpx.AsyncClient,
    url: str,
    request_number: int,
    account_count: int,
    statuses: Counter[int],
) -> None:
    """Gửi một lần đăng nhập sai và ghi nhận status."""
    try:
        response = await client.post(
            url,
            json={
                "username": _account_for_request(request_number, account_count),
                "password": f"sai-{request_number}-{secrets.token_hex(4)}",
            },
        )
        statuses[response.status_code] += 1
    except httpx.HTTPError:
        statuses[0] += 1


async def run_attack(
    url: str = DEFAULT_URL,
    rate: float = DEFAULT_RATE,
    duration: float = DEFAULT_DURATION,
    accounts: int = DEFAULT_ACCOUNTS,
) -> tuple[Counter[int], float]:
    """Bắn request brute-force theo nhịp cố định."""
    if rate <= 0:
        raise ValueError("rate phải lớn hơn 0")
    if duration <= 0:
        raise ValueError("duration phải lớn hơn 0")
    if accounts <= 0:
        raise ValueError("accounts phải lớn hơn 0")

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

            if len(pending) >= max_pending:
                await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

            task = asyncio.create_task(
                _send_failed_login(client, url, request_number, accounts, statuses)
            )
            pending.add(task)
            task.add_done_callback(pending.discard)

        if pending:
            await asyncio.gather(*pending)

    return statuses, time.perf_counter() - started


async def run_stealth_exfiltration(
    target_url: str = "http://localhost:8001/health",
    rate: float = 100.0,
    duration: float = 30.0,
) -> tuple[Counter[int], float]:
    """Mô phỏng rút dữ liệu âm thầm qua API hợp lệ (mọi response đều là 200 OK)."""
    print(f"Bắt đầu Stealth Exfiltration: {rate:g} req/s trong {duration:g}s tới {target_url} (HTTP 200 OK)...")
    total_requests = max(1, round(rate * duration))
    statuses: Counter[int] = Counter()
    started = time.perf_counter()

    async with httpx.AsyncClient(timeout=5.0) as client:
        for i in range(total_requests):
            target_time = started + i / rate
            delay = target_time - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                res = await client.get(target_url)
                statuses[res.status_code] += 1
            except httpx.HTTPError:
                statuses[0] += 1

    return statuses, time.perf_counter() - started


async def run_direct_db_scrape(
    db_url: str = DEFAULT_DB_URL,
    duration: float = 20.0,
) -> tuple[int, float]:
    """Mô phỏng truy cập trực tiếp Postgres port 5432 rút dữ liệu bypassing application logs."""
    print(f"Bắt đầu Direct DB Scrape: truy vấn trực tiếp Postgres trong {duration:g}s...")
    started = time.perf_counter()
    query_count = 0
    try:
        conn = await asyncpg.connect(db_url)
        try:
            while time.perf_counter() - started < duration:
                # Không giữ kết quả — mục đích là tạo tải đọc thật lên DB,
                # không phải lấy dữ liệu. Gán vào biến rồi bỏ thì ruff báo F841.
                await conn.fetch("SELECT id, order_id, amount FROM payments ORDER BY id DESC LIMIT 100")
                query_count += 1
                await asyncio.sleep(0.05)
        finally:
            await conn.close()
    except Exception as exc:
        print(f"⚠️ Lỗi kết nối DB trực tiếp: {exc}")

    return query_count, time.perf_counter() - started


async def run_rce_inject(
    target_url: str = "http://localhost:8001",
    duration: float = 10.0,
) -> tuple[int, float]:
    """Mô phỏng RCE vô hiệu hoá logging trước khi rút dữ liệu."""
    print(f"Bắt đầu RCE Inject: Tắt logging qua {target_url}/debug/rce-sim rồi gửi request...")
    started = time.perf_counter()
    request_count = 0
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            # 1. Gọi endpoint RCE để vô hiệu hoá logging
            await client.post(f"{target_url}/debug/rce-sim")
            print("Đã chiếm quyền (RCE) và vô hiệu hoá Python logging.")

            # 2. Rút dữ liệu (hoặc chạy bình thường) mà không để lại log
            while time.perf_counter() - started < duration:
                await client.get(f"{target_url}/health")
                request_count += 1
                await asyncio.sleep(0.1)
        except Exception as e:
            print(f"⚠️ Lỗi RCE Inject: {e}")

    return request_count, time.perf_counter() - started


async def run_log_tampering(
    target_url: str = "http://localhost:8001",
    duration: float = 10.0,
) -> tuple[int, float]:
    """Mô phỏng OS-Level Log Tampering."""
    print(f"Bắt đầu Log Tampering: Redirect stdout/stderr qua {target_url}/debug/suppress-output rồi đăng nhập sai...")
    started = time.perf_counter()
    request_count = 0
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            # 1. Gọi endpoint tamper để chặn stdout/stderr ở tầng OS
            await client.post(f"{target_url}/debug/suppress-output")
            print("Đã redirect stdout/stderr sang /dev/null ở tầng OS.")

            # 2. Tạo lỗi (đăng nhập sai) nhưng log sẽ không xuất hiện
            while time.perf_counter() - started < duration:
                await client.post(
                    f"{target_url}/login",
                    json={"username": "tamper", "password": "sai"}
                )
                request_count += 1
                await asyncio.sleep(0.1)
        except Exception as e:
            print(f"⚠️ Lỗi Log Tampering: {e}")

    return request_count, time.perf_counter() - started


async def run_oom_kill(
    target_url: str = "http://localhost:8001",
) -> tuple[int, float]:
    """Mô phỏng bơm dữ liệu liên tục cho đến khi OOM Kill."""
    print(f"Bắt đầu OOM Kill: Bơm /pay/batch liên tục vào {target_url} cho đến khi chết...")
    started = time.perf_counter()
    batch_count = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            try:
                res = await client.post(f"{target_url}/pay/batch")
                res.raise_for_status()
                batch_count += 1
                print(f" Đã nhồi batch {batch_count}...")
            except httpx.HTTPError:
                print("💥 Service đã chết (OOM Kill / Connection Refused).")
                break
            except Exception as e:
                print(f"💥 Lỗi (có thể đã chết): {e}")
                break

    return batch_count, time.perf_counter() - started


async def run_connection_starvation(
    target_url: str = "http://localhost:8001",
    db_url: str = DEFAULT_DB_URL,
    duration: float = 15.0,
) -> tuple[int, float]:
    """Mô phỏng Connection Starvation/Deadlock."""
    print(f"Bắt đầu Connection Starvation: Chiếm dụng db connection rồi gọi {target_url}/pay...")
    started = time.perf_counter()
    connections = []
    request_count = 0
    try:
        # 1. Mở rất nhiều connection trực tiếp tới DB và không trả lại
        for i in range(30):  # Đảm bảo chiếm hơn số max pool size của app
            try:
                conn = await asyncpg.connect(db_url)
                connections.append(conn)
            except Exception:
                break
        print(f"Đã chiếm dụng {len(connections)} DB connections.")

        # 2. Gửi request tới /pay, request này sẽ treo vĩnh viễn (chờ lấy connection từ pool)
        async with httpx.AsyncClient(timeout=1.0) as client:
            while time.perf_counter() - started < duration:
                try:
                    await client.post(
                        f"{target_url}/pay",
                        json={"order_id": f"starvation-{request_count}", "amount": 100}
                    )
                    request_count += 1
                except httpx.TimeoutException:
                    pass # Timeout do treo chờ connection
                except httpx.HTTPError:
                    pass

                request_count += 1
                await asyncio.sleep(0.5)
    except Exception as e:
        print(f"⚠️ Lỗi Connection Starvation: {e}")
    finally:
        for conn in connections:
            await conn.close()

    return request_count, time.perf_counter() - started


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Giả lập các kịch bản tấn công bảo mật & sự cố")
    parser.add_argument(
        "--mode",
        choices=[
            "brute-force", "stealth-exfiltration", "direct-db-scrape",
            "rce-inject", "log-tampering", "oom-kill", "connection-starvation"
        ],
        default="brute-force",
        help="Chế độ tấn công giả lập",
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="URL endpoint /login")
    parser.add_argument("--rate", type=float, default=DEFAULT_RATE, help="request/giây")
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION, help="số giây chạy")
    parser.add_argument("--accounts", type=int, default=DEFAULT_ACCOUNTS, help="số tài khoản khác nhau bị thử")
    parser.add_argument("--db-url", default=DEFAULT_DB_URL, help="Database URL kết nối trực tiếp")
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()

    if args.mode == "brute-force":
        expected = max(1, round(args.rate * args.duration))
        print(
            f"Bắt đầu UC-3 Brute-force: {args.rate:g} request/giây × {args.duration:g}s "
            f"= khoảng {expected} request tới {args.url}, thử {args.accounts} tài khoản"
        )
        statuses, elapsed = await run_attack(args.url, args.rate, args.duration, args.accounts)
        completed = sum(statuses.values())
        actual_rate = completed / elapsed if elapsed else 0.0
        print(f"Xong sau {elapsed:.1f}s — {completed} request ({actual_rate:.1f} req/s)")
        print(f"Status: {dict(sorted(statuses.items()))}")

    elif args.mode == "stealth-exfiltration":
        statuses, elapsed = await run_stealth_exfiltration(
            target_url="http://localhost:8001/health",
            rate=args.rate if args.rate != DEFAULT_RATE else 50.0,
            duration=args.duration if args.duration != DEFAULT_DURATION else 10.0,
        )
        completed = sum(statuses.values())
        print(f"Xong Stealth Exfiltration sau {elapsed:.1f}s — {completed} requests")
        print(f"Status: {dict(sorted(statuses.items()))} (Lưu ý: Mọi request đều 200 OK nhưng tạo biến động traffic shape)")

    elif args.mode == "direct-db-scrape":
        queries, elapsed = await run_direct_db_scrape(
            db_url=args.db_url,
            duration=args.duration if args.duration != DEFAULT_DURATION else 10.0,
        )
        print(f"Xong Direct DB Scrape sau {elapsed:.1f}s — Thực thi {queries} câu lệnh SELECT trực tiếp trên DB")

    elif args.mode == "rce-inject":
        base_url = args.url.replace("/login", "")
        reqs, elapsed = await run_rce_inject(
            target_url=base_url,
            duration=args.duration if args.duration != DEFAULT_DURATION else 10.0,
        )
        print(f"Xong RCE Inject sau {elapsed:.1f}s — {reqs} requests xử lý âm thầm không log")

    elif args.mode == "log-tampering":
        base_url = args.url.replace("/login", "")
        reqs, elapsed = await run_log_tampering(
            target_url=base_url,
            duration=args.duration if args.duration != DEFAULT_DURATION else 10.0,
        )
        print(f"Xong Log Tampering sau {elapsed:.1f}s — {reqs} lần đăng nhập sai không log")

    elif args.mode == "oom-kill":
        base_url = args.url.replace("/login", "")
        batches, elapsed = await run_oom_kill(target_url=base_url)
        print(f"Xong OOM Kill sau {elapsed:.1f}s — Đã nhồi {batches} batch trước khi chết")

    elif args.mode == "connection-starvation":
        base_url = args.url.replace("/login", "")
        reqs, elapsed = await run_connection_starvation(
            target_url=base_url,
            db_url=args.db_url,
            duration=args.duration if args.duration != DEFAULT_DURATION else 15.0,
        )
        print(f"Xong Connection Starvation sau {elapsed:.1f}s — {reqs} requests bị treo")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    asyncio.run(_main())
