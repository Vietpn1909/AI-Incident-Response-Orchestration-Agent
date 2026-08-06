"""Thu số liệu thật cho deliverable #10.

Ground truth không nằm trong script này; đáp án đúng đã khóa trong
``docs/use-cases.md`` trước khi Agent được viết. Script chỉ:

* chạy Agent với FakeJira theo đúng ``scripts/run_agent.py --fake``;
* ghi timestamp, số vòng poll và incident mà Agent tạo;
* chạy lại bước hypothesize trên tín hiệu Prometheus đã chụp để đo M3.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import pathlib
import sys
import time
from datetime import UTC, datetime

import httpx

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agents.detection_loop import run_cycle  # noqa: E402
from src.agents.nodes.hypothesize import hypothesize_with_origin  # noqa: E402
from src.models.incident import IncidentSignal  # noqa: E402
from src.services.jira import FakeJiraClient  # noqa: E402
from src.services.prometheus import P95_LATENCY, PrometheusClient  # noqa: E402

_GROUND_TRUTH: dict[str, tuple[str, str]] = {
    "UC-1": ("P2", "Pool giới hạn 5 bị chiếm hết; truy vấn chậm giữ connection."),
    "UC-2": ("P1", "OOM-kill do rò rỉ bộ nhớ vượt giới hạn 128 MB."),
    "UC-3": ("P1 hoặc P2", "Credential-stuffing; là bất thường bảo mật, không phải quá tải."),
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def write_json(path: pathlib.Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def first_p95_crossing(
    prometheus_url: str,
    service: str,
    threshold: float,
    started: datetime,
    ended: datetime,
) -> datetime | None:
    """Mốc scrape đầu tiên mà p95 vượt ngưỡng trong khoảng quan sát."""
    response = httpx.get(
        f"{prometheus_url}/api/v1/query_range",
        params={
            "query": " ".join(P95_LATENCY.split()),
            "start": started.timestamp(),
            "end": ended.timestamp(),
            "step": "1s",
        },
        timeout=30,
    )
    response.raise_for_status()
    for series in response.json()["data"]["result"]:
        if series.get("metric", {}).get("service") != service:
            continue
        for timestamp, raw_value in series.get("values", []):
            value = float(raw_value)
            if value > threshold:
                return datetime.fromtimestamp(float(timestamp), UTC)
    return None


def observe(
    *,
    seconds: float | None,
    cycles_target: int | None,
    interval: float,
    output: pathlib.Path,
) -> None:
    """Chạy các vòng Agent với cùng FakeJira để đo báo nhầm/chống trùng."""
    jira = FakeJiraClient(verbose=False)
    prometheus = PrometheusClient()
    started = utc_now()
    deadline = time.monotonic() + seconds if seconds is not None else None
    cycles: list[dict[str, object]] = []

    try:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                break
            if cycles_target is not None and len(cycles) >= cycles_target:
                break

            cycle_started = utc_now()
            result = run_cycle(prometheus, jira)
            cycle_ended = utc_now()
            cycles.append(
                {
                    "number": len(cycles) + 1,
                    "started_at": cycle_started.isoformat(),
                    "ended_at": cycle_ended.isoformat(),
                    "duration_seconds": (cycle_ended - cycle_started).total_seconds(),
                    "detected": result.detected,
                    "opened": result.opened,
                    "updated": result.updated,
                    "error": result.error,
                }
            )
            print(
                f"cycle={len(cycles)} detected={result.detected} "
                f"opened={result.opened} updated={result.updated}",
                flush=True,
            )

            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(interval, remaining))
            elif len(cycles) < (cycles_target or 0):
                time.sleep(interval)
    finally:
        prometheus.close()

    ended = utc_now()
    incidents = jira.list_incidents()
    measurements: dict[str, object] = {}
    if incidents:
        first = min(incidents, key=lambda incident: incident.detected_at)
        opened_events = [event for event in first.timeline if event.action == "mở war room"]
        opened_at = opened_events[0].at if opened_events else None
        signal = first.signal
        if opened_at is not None:
            measurements["issue_opened_at"] = opened_at.isoformat()
            measurements["agent_processing_seconds"] = (
                opened_at - first.detected_at
            ).total_seconds()
        if signal is not None and "p95" in signal.metric_name:
            crossing = first_p95_crossing(
                "http://localhost:9090",
                signal.affected_service,
                signal.threshold,
                started,
                ended,
            )
            fixed_crossing = first_p95_crossing(
                "http://localhost:9090",
                signal.affected_service,
                2.0,
                started,
                ended,
            )
            measurements.update(
                {
                    "signal_threshold": signal.threshold,
                    "p95_crossed_signal_threshold_at": (
                        crossing.isoformat() if crossing else None
                    ),
                    "p95_crossed_2s_at": fixed_crossing.isoformat() if fixed_crossing else None,
                    "mttd_from_signal_threshold_seconds": (
                        (opened_at - crossing).total_seconds()
                        if opened_at is not None and crossing is not None
                        else None
                    ),
                    "mttd_from_fixed_2s_seconds": (
                        (opened_at - fixed_crossing).total_seconds()
                        if opened_at is not None and fixed_crossing is not None
                        else None
                    ),
                }
            )

    payload = {
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "duration_seconds": (ended - started).total_seconds(),
        "poll_interval_seconds": interval,
        "cycle_count": len(cycles),
        "issue_count": len(incidents),
        "cycles": cycles,
        "measurements": measurements,
        "incidents": [incident.model_dump(mode="json") for incident in incidents],
    }
    write_json(output, payload)
    print(f"wrote={output} issues={len(incidents)} cycles={len(cycles)}")


async def payment_request(client: httpx.AsyncClient, index: int) -> int:
    try:
        response = await client.post(
            "http://localhost:8001/pay",
            json={"order_id": f"eval-{index}", "amount": 100},
        )
        return response.status_code
    except httpx.HTTPError:
        return 0


async def payment_load(seconds: float, concurrency: int, pause: float) -> None:
    """Tải cố định: concurrency=1 là bình thường, 75 giữ UC-1."""
    deadline = time.monotonic() + seconds
    request_number = 0
    statuses: dict[int, int] = {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        while time.monotonic() < deadline:
            results = await asyncio.gather(
                *(payment_request(client, request_number + i) for i in range(concurrency))
            )
            request_number += concurrency
            for status in results:
                statuses[status] = statuses.get(status, 0) + 1
            if pause:
                await asyncio.sleep(pause)
    print(json.dumps({"requests": request_number, "statuses": statuses}, ensure_ascii=False))


def diagnosis_correct(uc: str, text: str) -> bool:
    """Chấm máy theo đúng câu chữ ground truth trong docs/use-cases.md."""
    normalized = text.casefold()
    if uc == "UC-1":
        pool = "pool" in normalized or "connection" in normalized
        exhausted = any(word in normalized for word in ("cạn", "hết", "kiệt", "exhaust"))
        slow_query = "truy vấn" in normalized and any(
            word in normalized for word in ("chậm", "giữ", "lâu")
        )
        return (pool and exhausted) or slow_query
    if uc == "UC-2":
        denied = any(
            phrase in normalized
            for phrase in (
                "không có nguyên nhân gốc",
                "không phải do oom",
                "không phải do bộ nhớ",
                "không bị oom",
                "không có oom",
                "không cho thấy áp lực bộ nhớ",
            )
        )
        if denied:
            return False
        oom = "oom" in normalized or "out of memory" in normalized
        memory = any(word in normalized for word in ("bộ nhớ", "memory", "ram"))
        cause = any(word in normalized for word in ("128", "giới hạn", "rò rỉ", "leak"))
        return oom or (memory and cause)
    if uc == "UC-3":
        security = any(
            word in normalized
            for word in ("bảo mật", "tấn công", "credential", "brute", "đăng nhập", "xác thực")
        )
        performance_text = normalized
        for negation in ("không phải quá tải", "không phải là quá tải"):
            performance_text = performance_text.replace(negation, "")
        performance = any(word in performance_text for word in ("quá tải", "pool cạn", "oom"))
        return security and not performance
    raise ValueError(f"UC không hỗ trợ: {uc}")


def diagnose(input_path: pathlib.Path, uc: str, runs: int, output: pathlib.Path) -> None:
    """Lặp inference trên snapshot telemetry thật; không đổi ground truth."""
    expected_severity, ground_truth = _GROUND_TRUTH[uc]
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    incidents = payload.get("incidents") or []
    if not incidents:
        raise SystemExit(f"{input_path} không có incident")
    signal = IncidentSignal.model_validate(incidents[0]["signal"])

    rows: list[dict[str, object]] = []
    for index in range(1, runs + 1):
        started = utc_now()
        outcome = hypothesize_with_origin(signal)
        hypothesis = outcome.hypothesis
        elapsed = (utc_now() - started).total_seconds()
        combined = f"{hypothesis.statement} {hypothesis.reasoning}"
        correct = diagnosis_correct(uc, combined)
        rows.append(
            {
                "run_id": f"{uc}-{index:02d}",
                "uc": uc,
                "evaluated_at": started.isoformat(),
                "model": "qwen-plus",
                "temperature": 0.2,
                "service": signal.affected_service,
                "expected_severity": expected_severity,
                "actual_severity": signal.severity.value,
                "ground_truth": ground_truth,
                "diagnosis_correct": str(correct).lower(),
                "confidence": hypothesis.confidence,
                "llm_latency_seconds": round(elapsed, 3),
                "statement_origin": outcome.statement_origin,
                "statement": hypothesis.statement,
                "reasoning": hypothesis.reasoning,
            }
        )
        print(f"{uc}-{index:02d} correct={correct} latency={elapsed:.2f}s", flush=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote={output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    observer = commands.add_parser("observe")
    length = observer.add_mutually_exclusive_group(required=True)
    length.add_argument("--seconds", type=float)
    length.add_argument("--cycles", type=int)
    observer.add_argument("--interval", type=float, default=10.0)
    observer.add_argument("--output", type=pathlib.Path, required=True)

    load = commands.add_parser("payment-load")
    load.add_argument("--seconds", type=float, required=True)
    load.add_argument("--concurrency", type=int, required=True)
    load.add_argument("--pause", type=float, default=0.05)

    diagnosis = commands.add_parser("diagnose")
    diagnosis.add_argument("--input", type=pathlib.Path, required=True)
    diagnosis.add_argument("--uc", choices=("UC-1", "UC-2", "UC-3"), required=True)
    diagnosis.add_argument("--runs", type=int, required=True)
    diagnosis.add_argument("--output", type=pathlib.Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "observe":
        observe(
            seconds=args.seconds,
            cycles_target=args.cycles,
            interval=args.interval,
            output=args.output,
        )
    elif args.command == "payment-load":
        asyncio.run(payment_load(args.seconds, args.concurrency, args.pause))
    else:
        diagnose(args.input, args.uc, args.runs, args.output)


if __name__ == "__main__":
    main()
