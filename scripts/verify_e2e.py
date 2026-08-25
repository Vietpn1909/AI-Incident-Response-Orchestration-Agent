"""Verify trọn chuỗi HITL: tạo war room → đề xuất → người duyệt → thi hành.

Từng mảnh của chuỗi này đã test riêng, nhưng cả chuỗi chưa bao giờ chạy liền
mạch một lần nào. Script này chạy nó, và in rõ tắc ở mảnh nào nếu tắc.

    # Chỉ kiểm logic, không cần Jira Automation rule — làm cái này TRƯỚC
    python scripts/verify_e2e.py --local

    # Kiểm cả hop Jira Automation → Render, cần đã cấu hình rule
    python scripts/verify_e2e.py --live

Chế độ `--local` gọi webhook trên máy (`uvicorn src.main:app` phải đang chạy).
Chế độ `--live` gọi webhook qua địa chỉ công khai, tức kiểm luôn được Jira Automation.

Issue tạo ra là issue THẬT trên Jira. Script chuyển nó sang Resolved khi xong,
nhưng không xoá được — account Agent không có quyền xoá issue (đúng như mong
muốn). Xoá tay trên UI nếu muốn cho gọn.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from datetime import UTC, datetime

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.config import force_utf8_console  # noqa: E402
from src.models.incident import (  # noqa: E402
    IncidentSignal,
    IncidentState,
    MetricEvidence,
    RemediationProposal,
    Severity,
)
from src.services.hitl import ApprovalError, assert_human_approved  # noqa: E402
from src.services.jira import RealJiraClient, status_candidates  # noqa: E402
from src.services.prometheus import P95_LATENCY  # noqa: E402

LOCAL_URL = "http://localhost:8000"

#: Địa chỉ webhook công khai mà Jira Automation đang gọi. Từ 23/08 dự án tự host
#: qua Cloudflare Tunnel thay cho Render — xem docs/self-host-cloudflare.md.
#: Đổi bằng biến môi trường `LIVE_URL` nếu chạy ở chỗ khác.
LIVE_URL = os.getenv("LIVE_URL", "https://api-035.emmetech.id.vn")

REQUIRED = [
    "JIRA_BASE_URL",
    "JIRA_EMAIL",
    "JIRA_API_TOKEN",
    "JIRA_PROJECT_KEY",
    "JIRA_AGENT_ACCOUNT_ID",
    "JIRA_WEBHOOK_SECRET",
]


def load_env() -> dict[str, str]:
    """Đọc .env. Không dùng pydantic Settings vì cần cả JIRA_WEBHOOK_SECRET."""
    env: dict[str, str] = {}
    path = pathlib.Path(".env")
    if not path.exists():
        sys.exit("❌ Không thấy .env — chạy script từ thư mục gốc của repo.")
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()

    missing = [k for k in REQUIRED if not env.get(k)]
    if missing:
        print("❌ Thiếu biến trong .env:")
        for k in missing:
            print(f"     {k}")
        if "JIRA_WEBHOOK_SECRET" in missing:
            print("\n   JIRA_WEBHOOK_SECRET lấy ở Render → service → Environment.")
            print("   Render tự sinh giá trị này (generateValue trong render.yaml).")
        sys.exit(1)
    return env


def step(n: int, title: str) -> None:
    print(f"\n{'─' * 62}\n{n}) {title}")


def ok(msg: str) -> None:
    print(f"   ✅ {msg}")


def fail(msg: str) -> None:
    print(f"   ❌ {msg}")


def main() -> int:
    # Trước parse_args(): argparse in `--help` và lỗi tham số bằng tiếng Việt
    # thẳng ra stdout. Console Windows là CP1252 nên chưa ép UTF-8 thì chết
    # bằng UnicodeEncodeError. 3/4 thành viên dùng Windows.
    force_utf8_console()

    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--local", action="store_true", help="webhook trên máy")
    mode.add_argument("--live", action="store_true", help="webhook công khai (tunnel)")
    args = parser.parse_args()

    env = load_env()
    base = LOCAL_URL if args.local else LIVE_URL
    agent_id = env["JIRA_AGENT_ACCOUNT_ID"]

    print(f"Verify chuỗi HITL — webhook: {base}")
    print(f"Jira: {env['JIRA_BASE_URL']} · project {env['JIRA_PROJECT_KEY']}")

    jira = RealJiraClient(
        base_url=env["JIRA_BASE_URL"],
        email=env["JIRA_EMAIL"],
        api_token=env["JIRA_API_TOKEN"],
        project_key=env["JIRA_PROJECT_KEY"],
    )
    failures = 0
    key = None

    try:
        # ── 1. Agent mở war room ──────────────────────────────────────────
        step(1, "Agent mở war room trên Jira")
        signal = IncidentSignal(
            affected_service="service-thanh-toan",
            severity=Severity.P2,
            detected_at=datetime.now(UTC),
            metric_name="http_request_duration_seconds p95",
            metric_value=5.1,
            threshold=2.0,
            breached_for_seconds=45.0,
            evidence=[
                MetricEvidence(
                    name="http_request_duration_seconds p95",
                    value=5.1,
                    baseline=0.2,
                    unit="s",
                    promql=P95_LATENCY.strip(),
                )
            ],
        )
        key = jira.create_incident(signal)
        ok(f"{key} — {env['JIRA_BASE_URL']}/browse/{key}")

        # ── 2. Agent đề xuất khắc phục rồi DỪNG ──────────────────────────
        step(2, "Agent đề xuất khắc phục rồi dừng chờ người")
        jira.post_proposal(
            key,
            RemediationProposal(
                action="rollback",
                target="service-thanh-toan",
                params={"to_version": "v1.4.1"},
                runbook="1. Xác nhận artifact v1.4.1  2. Rollback  3. Theo dõi p95 5 phút",
                risk="Mất tính năng mới của v1.4.2",
            ),
        )
        state = jira.get_incident(key).state
        (ok if state == IncidentState.AWAITING_APPROVAL else fail)(f"state = {state.value}")
        failures += state != IncidentState.AWAITING_APPROVAL

        # ── 3. Chưa ai duyệt → phải từ chối ──────────────────────────────
        step(3, "Chưa ai duyệt, xin thi hành → phải TỪ CHỐI")
        try:
            assert_human_approved(jira, key, agent_account_id=agent_id)
            fail("cho qua khi chưa ai duyệt")
            failures += 1
        except ApprovalError:
            ok("bị từ chối, đúng")

        # ── 4. Agent tự duyệt → phải từ chối ─────────────────────────────
        step(4, "Agent TỰ chuyển sang Remediating rồi xin thi hành → phải TỪ CHỐI")
        jira.transition(key, IncidentState.REMEDIATING)
        author = jira.get_transition_author(key, IncidentState.REMEDIATING)
        print(f"   changelog author = {author}")
        try:
            assert_human_approved(jira, key, agent_account_id=agent_id)
            fail("NGHIÊM TRỌNG — Agent tự duyệt được, ràng buộc bắt buộc bị phá")
            failures += 1
        except ApprovalError:
            ok("backend từ chối, đúng")

        # Đưa issue về lại Awaiting Approval trước khi nhờ người duyệt.
        #
        # Bước 4 vừa đẩy nó sang Remediating (với vai Agent). Không reset thì
        # issue đã nằm sẵn ở trạng thái đích, người duyệt không còn gì để bấm,
        # và changelog không sinh thêm bản ghi nào với tác giả là người —
        # bước 5 sẽ luôn fail dù bạn làm đúng.
        jira.transition(key, IncidentState.AWAITING_APPROVAL)

        # ── 5. Người duyệt thật ───────────────────────────────────────────
        step(5, "Chờ BẠN duyệt trên Jira")
        current = jira.get_incident(key)
        current_name = current.state.value if current else "?"
        want_rem, old_rem = status_candidates(IncidentState.REMEDIATING)
        print(f"   Issue đang ở '{current_name}'.")
        print(f"   Mở {env['JIRA_BASE_URL']}/browse/{key}")
        print("   Đăng nhập bằng account CỦA BẠN (không phải account Agent),")
        print(f"   chuyển issue sang '{want_rem}'.")
        input("\n   Duyệt xong thì Enter... ")

        author = jira.get_transition_author(key, IncidentState.REMEDIATING)
        if author and author != agent_id:
            ok(f"changelog ghi người duyệt = {author}")
        elif author == agent_id:
            fail("author vẫn là Agent — bạn chưa chuyển trạng thái, hoặc đang")
            print("      đăng nhập bằng account Agent thay vì account của bạn.")
            failures += 1
        else:
            fail("changelog chưa có bản ghi nào chuyển sang trạng thái này")
            failures += 1

        # ── 6. Gọi webhook ────────────────────────────────────────────────
        step(6, f"Gọi webhook {base}/webhooks/jira")
        try:
            response = httpx.post(
                f"{base}/webhooks/jira",
                json={"issue": {"key": key}},
                headers={"X-Webhook-Secret": env["JIRA_WEBHOOK_SECRET"]},
                timeout=120,  # Render free tier ngủ 15 phút, cold start ~50s
            )
        except httpx.RequestError as exc:
            fail(f"không gọi được: {exc}")
            if args.local:
                print("   → uvicorn src.main:app --reload  đang chạy chưa?")
            return 1

        if response.status_code == 200:
            body = response.json()
            ok(f"HTTP 200 · {body['action']} → {body['target']}")
            ok(f"người phê duyệt = {body['approved_by']}")
            if body.get("simulated"):
                print("   ℹ️  hành động đang MÔ PHỎNG (service demo chưa nối vào remediation)")
        elif response.status_code == 403:
            fail(f"403 — backend từ chối: {response.json().get('detail')}")
            print("   → nếu bạn ĐÃ duyệt thì kiểm JIRA_AGENT_ACCOUNT_ID trên Render")
            failures += 1
        elif response.status_code == 401:
            fail("401 — sai X-Webhook-Secret")
            print("   → giá trị trong .env phải khớp Render → Environment")
            failures += 1
        elif response.status_code == 503:
            fail("503 — JIRA_WEBHOOK_SECRET chưa cấu hình phía server")
            failures += 1
        else:
            fail(f"HTTP {response.status_code}: {response.text[:200]}")
            failures += 1

        # ── 7. Kết quả có lên war room? ───────────────────────────────────
        step(7, "Kết quả có được ghi lên war room?")
        events = jira.get_incident(key).timeline
        print(f"   {len(events)} mốc trong changelog")
        ok("mở issue xem comment cuối để xác nhận nội dung")

    finally:
        if key:
            print(f"\n{'─' * 62}\nDọn: chuyển {key} sang Resolved")
            try:
                jira.transition(key, IncidentState.RESOLVED)
                jira.add_comment(key, "[VERIFY-E2E] Issue do script verify tạo — có thể xoá.")
                print(f"   ✅ xong · {env['JIRA_BASE_URL']}/browse/{key}")
            except Exception as exc:
                print(f"   ⚠️  {exc}")
        jira.close()

    print(f"\n{'═' * 62}")
    if failures:
        print(f"❌ {failures} bước FAIL — xem lại ở trên")
    else:
        print("✅ TOÀN BỘ CHUỖI THÔNG")
        if args.local:
            print("   Tiếp: chạy lại với --live để kiểm hop Jira Automation → tunnel")
        else:
            print("   Bước 8 của kịch bản demo đã chạy được end-to-end.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
