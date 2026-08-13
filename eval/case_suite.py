"""Bộ chấm offline cho 30 test case phát hiện incident.

Module này chỉ gọi các hàm public, tất định trong ``src.services.rules``. Nó
không gọi Jira, Docker, Prometheus hay LLM, vì vậy có thể chạy lặp lại mà không
gây tác dụng phụ lên demo và không làm lẫn cửa sổ telemetry giữa các case.

Dataset là các snapshot có ground truth khóa trước khi chạy. Đây là baseline
để đo khả năng *phát hiện*; các phép đo live/LLM cũ trong
``eval/run_measurements.py`` vẫn được giữ nguyên.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.agents.nodes.detect import detect_incidents
from src.agents.nodes.open_war_room import open_war_room
from src.models.incident import IncidentSignal
from src.services import rules
from src.services.jira import FakeJiraClient
from src.services.prometheus import MetricSample

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES = ROOT / "eval" / "cases" / "incident_cases.json"
DEFAULT_OUTPUT_DIR = ROOT / "eval" / "results" / "case-suite"
ALLOWED_SPLITS = {"normal", "incident", "noisy"}
ALLOWED_DETECTORS = {"latency", "auth", "crashloop"}


class SnapshotPrometheusClient:
    """Prometheus giả phát snapshot qua đúng interface ``query()``.

    Khác đường gọi thẳng ``rules.detect*()``, client này bắt node detect phải
    chạy đủ các PromQL, đo sustained window và ghép tín hiệu trước khi Jira
    được mở. Không có kết nối mạng và không giữ state giữa hai test case.
    """

    def __init__(self, telemetry: dict[str, Any]) -> None:
        self.telemetry = telemetry
        self.service = str(telemetry["service"])

    @staticmethod
    def _kind(promql: str) -> str:
        if "auth_failure_unique_source_ips_1m" in promql:
            return "unique_source_ips"
        if "auth_failure_unique_accounts_1m" in promql:
            return "unique_accounts"
        if "auth_failure_top_source_ratio_1m" in promql:
            return "top_source_ratio"
        if 'handler="/login"' in promql:
            return "auth"
        if "max_over_time(process_resident_memory_bytes[10m])" in promql:
            return "memory_peak"
        if "process_resident_memory_bytes /" in promql:
            return "memory_ratio"
        if "process_start_time_seconds" in promql:
            return "restarts"
        if "1 - (up)" in promql:
            return "down"
        if promql.strip() == "up":
            return "up"
        if "db_pool" in promql:
            return "pool"
        if "count_over_time" in promql:
            return "baseline_samples"
        if promql.count("histogram_quantile") >= 2:
            return "deviation"
        if "quantile_over_time" in promql:
            return "baseline"
        if "histogram_quantile" in promql:
            return "p95"
        return "error"

    def _value(self, kind: str) -> float | None:
        telemetry = self.telemetry
        mapping = {
            "p95": telemetry.get("p95_seconds"),
            "baseline": telemetry.get("p95_baseline_seconds"),
            "baseline_samples": telemetry.get("baseline_samples"),
            "error": telemetry.get("error_rate"),
            "pool": telemetry.get("pool_saturation"),
            "auth": telemetry.get("failures_per_second"),
            "unique_source_ips": telemetry.get("unique_source_ips"),
            "unique_accounts": telemetry.get("unique_accounts"),
            "top_source_ratio": telemetry.get("top_source_ratio"),
            "up": telemetry.get("service_up"),
            "restarts": telemetry.get("restarts_10m"),
            "memory_ratio": telemetry.get("memory_ratio"),
            "memory_peak": telemetry.get("memory_peak_10m_mb"),
        }
        if kind == "down":
            up = telemetry.get("service_up")
            return None if up is None else 1.0 - float(up)
        if kind == "deviation":
            baseline = telemetry.get("p95_baseline_seconds")
            samples = float(telemetry.get("baseline_samples", 0.0))
            if not baseline or samples < rules.BASELINE_MIN_SAMPLES:
                return 0.0
            return float(telemetry["p95_seconds"]) / float(baseline)
        value = mapping[kind]
        return None if value is None else float(value)

    def query(self, promql: str) -> list[MetricSample]:
        kind = self._kind(promql)
        value = self._value(kind)
        if value is None:
            return []

        # Node detect thử 4 cửa 30/60/120/300 giây. Snapshot chỉ trả giá trị
        # nếu case thật sự kéo dài đủ cửa đang được hỏi.
        if "min_over_time" in promql:
            match = re.search(r"\[(\d+)s:5s\]", promql)
            window = float(match.group(1)) if match else 0.0
            duration = float(
                self.telemetry.get(
                    "breached_for_seconds",
                    self.telemetry.get("down_for_seconds", 0.0),
                )
            )
            if duration < window:
                value = 0.0
        return [MetricSample(service=self.service, value=value)]


def load_suite(path: Path) -> dict[str, Any]:
    """Đọc và kiểm tra schema tối thiểu của dataset."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("dataset phải có danh sách cases không rỗng")

    ids = [case.get("id") for case in cases]
    if any(not case_id for case_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("mỗi case phải có id duy nhất và không rỗng")

    counts = Counter(case.get("split") for case in cases)
    if set(counts) - ALLOWED_SPLITS:
        raise ValueError(f"split không hỗ trợ: {sorted(set(counts) - ALLOWED_SPLITS)}")

    expected_counts = payload.get("metadata", {}).get("expected_counts", {})
    if expected_counts and dict(counts) != expected_counts:
        raise ValueError(f"phân bố thực tế {dict(counts)} khác expected_counts {expected_counts}")

    for case in cases:
        detector = case.get("telemetry", {}).get("detector")
        if detector not in ALLOWED_DETECTORS:
            raise ValueError(f"{case['id']}: detector không hỗ trợ: {detector}")
        truth = case.get("ground_truth", {})
        if not isinstance(truth.get("is_incident"), bool):
            raise ValueError(f"{case['id']}: ground_truth.is_incident phải là bool")
        if case["split"] == "incident" and not truth["is_incident"]:
            raise ValueError(f"{case['id']}: split incident phải có ground truth dương")
        if case["split"] != "incident" and truth["is_incident"]:
            raise ValueError(f"{case['id']}: chỉ split incident được tính là incident thật")
    return payload


def _detect(telemetry: dict[str, Any]) -> IncidentSignal | None:
    detector = telemetry["detector"]
    if detector == "latency":
        return rules.detect(
            p95_now=float(telemetry["p95_seconds"]),
            p95_baseline=float(telemetry["p95_baseline_seconds"]),
            error_rate=float(telemetry["error_rate"]),
            pool_saturation=float(telemetry["pool_saturation"]),
            service=str(telemetry["service"]),
            breached_for_seconds=float(telemetry["breached_for_seconds"]),
            baseline_samples=float(telemetry.get("baseline_samples", 0.0)),
        )
    if detector == "auth":
        return rules.detect_auth_burst(
            failures_per_second=float(telemetry["failures_per_second"]),
            breached_for_seconds=float(telemetry["breached_for_seconds"]),
            service=str(telemetry["service"]),
            unique_source_ips=float(telemetry.get("unique_source_ips", 0.0)),
            unique_accounts=float(telemetry.get("unique_accounts", 0.0)),
            top_source_ratio=float(telemetry.get("top_source_ratio", 0.0)),
        )
    return rules.detect_crashloop(
        service_up=float(telemetry["service_up"]),
        restarts=float(telemetry["restarts_10m"]),
        down_for_seconds=float(telemetry["down_for_seconds"]),
        service=str(telemetry["service"]),
        memory_ratio=float(telemetry.get("memory_ratio", 0.0)),
        memory_peak_mb=float(telemetry.get("memory_peak_10m_mb", 0.0)),
    )


def _matches_keyword_groups(text: str, groups: list[list[str]]) -> bool:
    normalized = text.casefold()
    return bool(groups) and all(
        any(keyword.casefold() in normalized for keyword in alternatives)
        for alternatives in groups
    )


def _contains_required_evidence(signal: IncidentSignal, required: list[str]) -> bool:
    names = [item.name.casefold() for item in signal.evidence]
    return all(any(term.casefold() in name for name in names) for term in required)


def _score_signal(
    case: dict[str, Any],
    signal: IncidentSignal | None,
    error: str | None,
    *,
    predicted_incident: bool | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    truth = case["ground_truth"]
    expected_incident = truth["is_incident"]
    if predicted_incident is None:
        predicted_incident = signal is not None
    if expected_incident and predicted_incident:
        classification = "TP"
    elif expected_incident:
        classification = "FN"
    elif predicted_incident:
        classification = "FP"
    else:
        classification = "TN"

    hypothesis_text: str | None = None
    confidence: float | None = None
    evidence_names: list[str] = []
    severity = None
    root_cause_correct = None
    evidence_complete = None
    severity_correct = None

    if signal is not None:
        hypothesis = rules.build_hypothesis(signal)
        hypothesis_text = hypothesis.statement
        confidence = hypothesis.confidence
        evidence_names = [item.name for item in signal.evidence]
        severity = signal.severity.value

    if expected_incident:
        severity_correct = bool(signal and severity == truth.get("severity"))
        root_cause_correct = bool(
            signal
            and hypothesis_text
            and _matches_keyword_groups(
                hypothesis_text,
                truth.get("accepted_hypothesis_keyword_groups", []),
            )
        )
        evidence_complete = bool(
            signal
            and _contains_required_evidence(signal, truth.get("required_evidence", []))
        )

    result = {
        "case_id": case["id"],
        "split": case["split"],
        "family": case["family"],
        "title": case["title"],
        "expected_incident": expected_incident,
        "predicted_incident": predicted_incident,
        "classification": classification,
        "expected_severity": truth.get("severity"),
        "predicted_severity": severity,
        "severity_correct": severity_correct,
        "root_cause_correct": root_cause_correct,
        "evidence_complete": evidence_complete,
        "hypothesis": hypothesis_text,
        "confidence": confidence,
        "evidence_names": evidence_names,
        "error": error,
    }
    result.update(extra or {})
    return result


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    """Chạy một snapshot qua rule thật và trả kết quả đủ để error analysis."""
    signal: IncidentSignal | None = None
    error: str | None = None
    try:
        signal = _detect(case["telemetry"])
    except (KeyError, TypeError, ValueError) as exc:
        error = f"{type(exc).__name__}: {exc}"
    return _score_signal(case, signal, error, extra={"execution_mode": "direct-rule"})


def evaluate_pipeline_case(case: dict[str, Any]) -> dict[str, Any]:
    """Chạy đường tự động Prometheus → detect node → FakeJira.

    Đây là điểm kết thúc đúng của phép đo incident recall: issue có được mở
    hay không. Các node chẩn đoán LLM/remediation nằm sau đó và được đo bằng M3,
    không được trộn vào recall phát hiện.
    """
    signal: IncidentSignal | None = None
    error: str | None = None
    jira = FakeJiraClient(verbose=False)
    detected_count = 0
    try:
        signals = detect_incidents(SnapshotPrometheusClient(case["telemetry"]))
        detected_count = len(signals)
        signal = signals[0] if signals else None
        for detected_signal in signals:
            open_war_room(jira, detected_signal)
    except (KeyError, TypeError, ValueError) as exc:
        error = f"{type(exc).__name__}: {exc}"

    issue_count = len(jira.list_incidents())
    return _score_signal(
        case,
        signal,
        error,
        predicted_incident=issue_count > 0,
        extra={
            "execution_mode": "prometheus-detect-jira",
            "detected_signal_count": detected_count,
            "jira_issue_count": issue_count,
        },
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def compute_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Tính confusion matrix và các metric đánh giá Agent."""
    confusion = Counter(result["classification"] for result in results)
    tp, fn = confusion["TP"], confusion["FN"]
    fp, tn = confusion["FP"], confusion["TN"]
    positives = tp + fn
    negatives = fp + tn

    detected_incidents = [result for result in results if result["classification"] == "TP"]
    true_incidents = [result for result in results if result["expected_incident"]]
    noisy_cases = [result for result in results if result["split"] == "noisy"]

    per_family: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[result["family"]].append(result)
    for family, family_results in sorted(grouped.items()):
        family_tp = sum(item["classification"] == "TP" for item in family_results)
        family_fn = sum(item["classification"] == "FN" for item in family_results)
        per_family[family] = {
            "true_incidents": family_tp + family_fn,
            "true_positives": family_tp,
            "false_negatives": family_fn,
            "recall": _ratio(family_tp, family_tp + family_fn),
        }

    return {
        "case_count": len(results),
        "true_incident_count": positives,
        "negative_count": negatives,
        "confusion_matrix": {key: confusion[key] for key in ("TP", "FN", "FP", "TN")},
        "incident_recall": _ratio(tp, positives),
        "incident_precision": _ratio(tp, tp + fp),
        "false_alarm_rate": _ratio(fp, negatives),
        "specificity": _ratio(tn, negatives),
        "accuracy": _ratio(tp + tn, len(results)),
        "severity_accuracy": _ratio(
            sum(item["severity_correct"] is True for item in detected_incidents),
            len(detected_incidents),
        ),
        "top1_root_cause_accuracy": _ratio(
            sum(item["root_cause_correct"] is True for item in true_incidents),
            len(true_incidents),
        ),
        "evidence_coverage": _ratio(
            sum(item["evidence_complete"] is True for item in true_incidents),
            len(true_incidents),
        ),
        "noisy_rejection_rate": _ratio(
            sum(not item["predicted_incident"] for item in noisy_cases),
            len(noisy_cases),
        ),
        "input_error_count": sum(item["error"] is not None for item in results),
        "per_family": per_family,
    }


def _percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.2f}%"


def render_markdown(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    confusion = metrics["confusion_matrix"]
    lines = [
        "# Kết quả bộ 30 test case incident",
        "",
        f"- Sinh lúc: `{payload['generated_at']}`",
        f"- Dataset SHA-256: `{payload['dataset_sha256']}`",
        "- Phạm vi recall: snapshot → Prometheus client giả → node detect thật → FakeJira; không gọi LLM/Jira thật/Docker.",
        "",
        "## Chỉ số chính",
        "",
        "| Chỉ số | Kết quả | Cách tính |",
        "|---|---:|---|",
        f"| Recall incident | **{_percent(metrics['incident_recall'])}** | TP / (TP + FN) |",
        f"| Precision incident | {_percent(metrics['incident_precision'])} | TP / (TP + FP) |",
        f"| Tỷ lệ báo nhầm | {_percent(metrics['false_alarm_rate'])} | FP / (FP + TN) |",
        f"| Đúng severity | {_percent(metrics['severity_accuracy'])} | severity đúng / incident đã bắt được |",
        f"| Top-1 nguyên nhân gốc (rule baseline) | {_percent(metrics['top1_root_cause_accuracy'])} | đúng nguyên nhân / 15 incident thật |",
        f"| Đủ bằng chứng metric | {_percent(metrics['evidence_coverage'])} | đủ evidence / 15 incident thật |",
        f"| Từ chối case nhiễu | {_percent(metrics['noisy_rejection_rate'])} | noisy không mở incident / 5 |",
        "",
        "## Confusion matrix",
        "",
        f"- TP={confusion['TP']}, FN={confusion['FN']}, FP={confusion['FP']}, TN={confusion['TN']}.",
        "- Recall chỉ đo khả năng không bỏ lọt incident; phải đọc cùng precision và tỷ lệ báo nhầm.",
        "",
        "## Đối chiếu với rule trực tiếp",
        "",
        "| Đường chạy | Recall | Precision | Báo nhầm |",
        "|---|---:|---:|---:|",
        f"| Pipeline phát hiện → Jira | {_percent(metrics['incident_recall'])} | {_percent(metrics['incident_precision'])} | {_percent(metrics['false_alarm_rate'])} |",
        f"| Gọi rule trực tiếp | {_percent(payload['rule_baseline']['metrics']['incident_recall'])} | {_percent(payload['rule_baseline']['metrics']['incident_precision'])} | {_percent(payload['rule_baseline']['metrics']['false_alarm_rate'])} |",
        "",
        "Hai đường phải khớp. Nếu rule bắt được nhưng pipeline không mở Jira thì lỗi nằm ở wiring/collector, không phải threshold.",
        "",
        "## Recall theo họ sự cố",
        "",
        "| Họ | TP | FN | Recall |",
        "|---|---:|---:|---:|",
    ]
    for family, family_metrics in metrics["per_family"].items():
        if not family_metrics["true_incidents"]:
            continue
        lines.append(
            f"| {family} | {family_metrics['true_positives']} | "
            f"{family_metrics['false_negatives']} | {_percent(family_metrics['recall'])} |"
        )

    lines.extend(
        [
            "",
            "## Kết quả từng case",
            "",
            "| ID | Nhóm | Họ | Kết quả | Severity | Nguyên nhân gốc |",
            "|---|---|---|---:|---:|---:|",
        ]
    )
    for result in payload["results"]:
        root = "—" if result["root_cause_correct"] is None else ("đúng" if result["root_cause_correct"] else "sai")
        severity = result["predicted_severity"] or "—"
        lines.append(
            f"| {result['case_id']} | {result['split']} | {result['family']} | "
            f"{result['classification']} | {severity} | {root} |"
        )

    errors = [
        result
        for result in payload["results"]
        if result["classification"] in {"FN", "FP"} or result["root_cause_correct"] is False
    ]
    lines.extend(["", "## Top error để cải thiện tiếp", ""])
    for result in errors:
        reason = result["classification"]
        if result["root_cause_correct"] is False:
            reason += ", top-1 nguyên nhân sai"
        lines.append(f"- `{result['case_id']}` — {result['title']}: {reason}.")

    lines.extend(
        [
            "",
            "## Giới hạn",
            "",
            "Các snapshot được nhóm thiết kế từ pattern trong nguồn tham khảo, không phải dữ liệu thô tải từ Cloudflare/AWS/OpenTelemetry. FakeJira chứng minh pipeline đã quyết định mở issue nhưng không chứng minh kết nối Jira Cloud thật. Cần chạy thêm một tập live end-to-end đại diện để đo MTTD, log reasoning và độ dao động của LLM.",
            "",
        ]
    )
    return "\n".join(lines)


def run_suite(cases_path: Path, output_dir: Path) -> dict[str, Any]:
    suite = load_suite(cases_path)
    raw = cases_path.read_bytes()
    rule_results = [evaluate_case(case) for case in suite["cases"]]
    results = [evaluate_pipeline_case(case) for case in suite["cases"]]
    try:
        dataset_name = cases_path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        dataset_name = cases_path.name
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": dataset_name,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "distribution": dict(Counter(case["split"] for case in suite["cases"])),
        "metrics": compute_metrics(results),
        "results": results,
        "rule_baseline": {
            "metrics": compute_metrics(rule_results),
            "results": rule_results,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(render_markdown(payload), encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chạy baseline offline cho 30 incident cases")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # Snapshot auth/crash hợp lệ có thể không có series p95; node detect cảnh
    # báo chuyện đó để vận hành live, nhưng trong dataset đây là chủ đích và sẽ
    # làm CLI đầy nhiễu nếu in 30 lần.
    logging.getLogger("src.agents.nodes.detect").setLevel(logging.ERROR)
    payload = run_suite(args.cases, args.output_dir)
    metrics = payload["metrics"]
    print(
        f"cases={metrics['case_count']} "
        f"recall={_percent(metrics['incident_recall'])} "
        f"precision={_percent(metrics['incident_precision'])} "
        f"false_alarm={_percent(metrics['false_alarm_rate'])}"
    )
    print(f"wrote={args.output_dir}")


if __name__ == "__main__":
    main()
