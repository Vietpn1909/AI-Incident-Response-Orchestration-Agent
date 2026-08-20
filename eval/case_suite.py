"""Bộ chấm offline cho 50 test case phát hiện incident.

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
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agents.nodes.detect import detect_incidents  # noqa: E402
from src.agents.nodes.open_war_room import open_war_room  # noqa: E402
from src.models.incident import IncidentSignal  # noqa: E402
from src.services import planned_events, rules  # noqa: E402
from src.services.jira import FakeJiraClient  # noqa: E402
from src.services.prometheus import MetricSample  # noqa: E402

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


def _detect(
    telemetry: dict[str, Any], context: dict[str, Any] | None = None
) -> IncidentSignal | None:
    """Chạy đúng đường phát hiện của bộ luật cho một snapshot.

    `context` là thông tin ngoài số đo — việc đã lên lịch, ghi chú deploy, dòng
    log. Ngoài đời chúng đến từ API cửa sổ bảo trì, bảng `deploy_history` và
    `docker logs`; ở đây đến từ trường `context` của case.
    """
    detector = telemetry["detector"]
    if detector == "latency":
        tin_hieu = rules.detect(
            p95_now=float(telemetry["p95_seconds"]),
            p95_baseline=float(telemetry["p95_baseline_seconds"]),
            error_rate=float(telemetry["error_rate"]),
            pool_saturation=float(telemetry["pool_saturation"]),
            service=str(telemetry["service"]),
            breached_for_seconds=float(telemetry["breached_for_seconds"]),
            baseline_samples=float(telemetry.get("baseline_samples", 0.0)),
        )
    elif detector == "auth":
        tin_hieu = rules.detect_auth_burst(
            failures_per_second=float(telemetry["failures_per_second"]),
            breached_for_seconds=float(telemetry["breached_for_seconds"]),
            service=str(telemetry["service"]),
            unique_source_ips=float(telemetry.get("unique_source_ips", 0.0)),
            unique_accounts=float(telemetry.get("unique_accounts", 0.0)),
            top_source_ratio=float(telemetry.get("top_source_ratio", 0.0)),
            # Snapshot chỉ có một trường thời gian, mô tả "điều kiện đã giữ bao
            # lâu" — dùng chung cho cả hai thước đo.
            accounts_sustained_seconds=float(telemetry["breached_for_seconds"]),
        )
    else:
        tin_hieu = rules.detect_crashloop(
            service_up=float(telemetry["service_up"]),
            restarts=float(telemetry["restarts_10m"]),
            down_for_seconds=float(telemetry["down_for_seconds"]),
            service=str(telemetry["service"]),
            memory_ratio=float(telemetry.get("memory_ratio", 0.0)),
            memory_peak_mb=float(telemetry.get("memory_peak_10m_mb", 0.0)),
        )

    if tin_hieu is None:
        return None

    # Lọc MỘT LẦN ở cuối, không bọc từng nhánh: bộ luật vẫn chạy nguyên vẹn và
    # vẫn dựng đủ bằng chứng, rồi mới hỏi "việc này đã có lời giải thích chưa".
    # Nhờ vậy log vẫn ghi được tín hiệu đã thấy gì, kể cả khi không báo động.
    viec = (context or {}).get("maintenance_event")
    if planned_events.giai_thich_duoc(viec, detector, tin_hieu.metric_name):
        return None
    return tin_hieu


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
        signal = _detect(case["telemetry"], case.get("context"))
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
        # Lọc những tín hiệu đã có việc lên lịch giải thích, TRƯỚC khi mở war room.
        #
        # Lọc ở đây chứ không trong `detect_incidents()`: node đó chỉ biết số đo,
        # còn "có việc gì đã lên lịch" là thông tin ngoài số đo. Giữ ranh giới đó
        # thì `detect` vẫn thuần và test được riêng.
        #
        # `detected_count` giữ nguyên số tín hiệu đã THẤY, không phải số đã báo —
        # để log còn phân biệt được "không thấy gì" với "thấy nhưng đã có lời giải
        # thích".
        viec = (case.get("context") or {}).get("maintenance_event")
        detector = case["telemetry"]["detector"]
        signals = [
            s
            for s in signals
            if not planned_events.giai_thich_duoc(viec, detector, s.metric_name)
        ]
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


def khoang_tin_cay(k: int, n: int) -> tuple[float, float] | None:
    """Khoảng tin cậy 95% cho một tỷ lệ `k/n`, theo xấp xỉ Wald.

    Trả `None` khi `n == 0`.

    ## Vì sao bắt buộc phải in ra cạnh mỗi phần trăm

    Bộ này có 25 case sự cố và 25 case âm. Với cỡ mẫu đó, `recall = 72%` thật ra
    là **"đâu đó giữa 54% và 90%"** — khoảng rộng 35 điểm phần trăm. Không phân
    biệt được 72% với 85%.

    Đo ngày 18/08, ba hệ quả:

    1. Mọi cải thiện dưới ~15 điểm đều **nằm trong nhiễu**. Sửa 3 lỗ hổng đưa
       recall từ 72% lên 80% — con số sau không phân biệt được với con số trước.
    2. Bảng "recall theo họ sự cố" còn tệ hơn: `deployment` có **1 case**, nên
       `0.0%` ở đó là một lần tung xu, không phải kết luận.
    3. Muốn khoảng hẹp còn ±10 điểm cần ~78 case sự cố, tức ~150 case tổng — gấp
       ba hiện tại.

    Nên giá trị của bộ đo này **không nằm ở con số phần trăm**, mà ở phần phân
    tích từng case bỏ lọt: 7 lỗ hổng, mỗi cái nêu rõ vì sao mù và cần gì để vá.
    Phần đó không phụ thuộc cỡ mẫu.

    In khoảng tin cậy ngay cạnh mỗi con số để chính người viết báo cáo không tự
    lừa mình, và để người đọc không trích một con số đơn lẻ ra khỏi ngữ cảnh.
    """
    if n <= 0:
        return None
    p_hat = k / n
    # 0.25 là phương sai lớn nhất có thể — dùng khi p_hat là 0 hoặc 1, lúc đó
    # công thức thường cho sai số 0, nghe như "chắc chắn tuyệt đối" trong khi
    # thật ra 0/3 chẳng nói được gì.
    var = p_hat * (1 - p_hat) if 0 < p_hat < 1 else 0.25
    se = math.sqrt(var / n)
    return max(0.0, p_hat - 1.96 * se), min(1.0, p_hat + 1.96 * se)


def _kct_fmt(k: int, n: int) -> str:
    """`"54%–90%"`, hoặc `"—"` nếu không tính được."""
    kct = khoang_tin_cay(k, n)
    if kct is None:
        return "—"
    lo, hi = kct
    return f"{lo * 100:.0f}%–{hi * 100:.0f}%"


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _f_beta(precision: float | None, recall: float | None, beta: float) -> float | None:
    """F-beta score: beta=1 → F1, beta=2 → F2 (thiên recall)."""
    if precision is None or recall is None or (precision + recall) == 0:
        return None
    b2 = beta * beta
    return round((1 + b2) * precision * recall / (b2 * precision + recall), 4)


def _mcc(tp: int, tn: int, fp: int, fn: int) -> float | None:
    """Matthews Correlation Coefficient — chỉ số tổng hợp tốt nhất cho binary classification.

    Giá trị: -1 (hoàn toàn sai) → 0 (ngẫu nhiên) → +1 (hoàn toàn đúng).
    """
    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    if denom == 0:
        return None
    return round((tp * tn - fp * fn) / denom, 4)


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

    recall = _ratio(tp, positives)
    precision = _ratio(tp, tp + fp)
    f1 = _f_beta(precision, recall, beta=1)
    f2 = _f_beta(precision, recall, beta=2)
    mcc = _mcc(tp, tn, fp, fn)

    # --- Per-family: recall + precision + F1 ---
    per_family: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[result["family"]].append(result)
    for family, family_results in sorted(grouped.items()):
        family_tp = sum(item["classification"] == "TP" for item in family_results)
        family_fn = sum(item["classification"] == "FN" for item in family_results)
        family_fp = sum(item["classification"] == "FP" for item in family_results)
        family_recall = _ratio(family_tp, family_tp + family_fn)
        family_precision = _ratio(family_tp, family_tp + family_fp)
        per_family[family] = {
            "true_incidents": family_tp + family_fn,
            "true_positives": family_tp,
            "false_negatives": family_fn,
            "false_positives": family_fp,
            "recall": family_recall,
            "precision": family_precision,
            "f1": _f_beta(family_precision, family_recall, beta=1),
        }

    # --- Severity confusion matrix ---
    severity_matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    severity_correct_count = 0
    for item in detected_incidents:
        expected = item.get("expected_severity") or "?"
        predicted = item.get("predicted_severity") or "?"
        severity_matrix[expected][predicted] += 1
        if item.get("severity_correct") is True:
            severity_correct_count += 1
    # Convert to plain dict for JSON serialization
    severity_matrix_plain = {k: dict(v) for k, v in severity_matrix.items()}

    return {
        "case_count": len(results),
        "true_incident_count": positives,
        "negative_count": negatives,
        "confusion_matrix": {key: confusion[key] for key in ("TP", "FN", "FP", "TN")},
        # --- Core detection metrics ---
        "incident_recall": recall,
        "incident_precision": precision,
        "f1_score": f1,
        "f2_score": f2,
        "accuracy": _ratio(tp + tn, len(results)),
        "specificity": _ratio(tn, negatives),
        "false_alarm_rate": _ratio(fp, negatives),
        "mcc": mcc,
        # --- Severity & root cause ---
        "severity_accuracy": _ratio(
            severity_correct_count,
            len(detected_incidents),
        ),
        "severity_confusion_matrix": severity_matrix_plain,
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


def _mcc_fmt(value: float | None) -> str:
    """Format MCC: giá trị -1..+1, không phải phần trăm."""
    return "N/A" if value is None else f"{value:+.4f}"


def render_markdown(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    confusion = metrics["confusion_matrix"]
    lines = [
        f"# Kết quả đánh giá — {metrics['case_count']} test case",
        "",
        f"- Sinh lúc: `{payload['generated_at']}`",
        f"- Dataset SHA-256: `{payload['dataset_sha256']}`",
        "- Phạm vi: snapshot → Prometheus client giả → node detect thật → FakeJira; không gọi LLM/Jira thật/Docker.",
        "",
        "## 1. Confusion Matrix",
        "",
        f"- TP={confusion['TP']}, FN={confusion['FN']}, FP={confusion['FP']}, TN={confusion['TN']}.",
        "",
        "## 2. Bộ chỉ số phát hiện (Detection Metrics)",
        "",
        "| Chỉ số | Kết quả | Khoảng tin cậy 95% | Công thức | Ý nghĩa |",
        "|---|---:|:---:|---|---|",
        f"| **Recall** | **{_percent(metrics['incident_recall'])}** | {_kct_fmt(confusion['TP'], confusion['TP'] + confusion['FN'])} | TP/(TP+FN) | Khả năng không bỏ lọt incident |",
        f"| **Precision** | **{_percent(metrics['incident_precision'])}** | {_kct_fmt(confusion['TP'], confusion['TP'] + confusion['FP'])} | TP/(TP+FP) | Tỷ lệ alert đúng |",
        f"| **F1 Score** | **{_percent(metrics['f1_score'])}** | — | 2·P·R/(P+R) | Cân bằng Precision-Recall |",
        f"| **F2 Score** | **{_percent(metrics['f2_score'])}** | — | 5·P·R/(4P+R) | Thiên Recall — phù hợp incident detection |",
        f"| **Accuracy** | **{_percent(metrics['accuracy'])}** | {_kct_fmt(confusion['TP'] + confusion['TN'], metrics['case_count'])} | (TP+TN)/All | Tổng thể đúng bao nhiêu |",
        f"| **Specificity** | **{_percent(metrics['specificity'])}** | {_kct_fmt(confusion['TN'], confusion['TN'] + confusion['FP'])} | TN/(TN+FP) | Khả năng nhận diện normal |",
        f"| **False Alarm Rate** | **{_percent(metrics['false_alarm_rate'])}** | {_kct_fmt(confusion['FP'], confusion['FP'] + confusion['TN'])} | FP/(FP+TN) | Tỷ lệ báo nhầm |",
        f"| **MCC** | **{_mcc_fmt(metrics['mcc'])}** | — | Matthews Correlation | Chỉ số tổng hợp (-1..+1) |",
        "",
        f"> ⚠️ **Cỡ mẫu {metrics['case_count']} case khiến mọi con số trên có sai số lớn.**",
        f"> Recall {_percent(metrics['incident_recall'])} thật ra là "
        f"\"đâu đó trong {_kct_fmt(confusion['TP'], confusion['TP'] + confusion['FN'])}\" — khoảng rộng vài chục",
        "> điểm phần trăm, nên **không phân biệt được** với một con số cao hơn 10–15 điểm.",
        ">",
        "> Hệ quả: đừng trích một phần trăm đơn lẻ ra khỏi ngữ cảnh, và đừng coi một",
        "> cải thiện dưới ~15 điểm là tiến bộ đo được. Giá trị của bộ đo này nằm ở",
        "> **phần phân tích từng case bỏ lọt** ở mục 3.2.2 — mỗi lỗ hổng nêu rõ vì sao",
        "> mù và cần gì để vá. Phần đó không phụ thuộc cỡ mẫu.",
        "",
        "## 3. Chỉ số chất lượng chẩn đoán",
        "",
        "| Chỉ số | Kết quả | Ý nghĩa |",
        "|---|---:|---|",
        f"| Severity Accuracy | **{_percent(metrics['severity_accuracy'])}** | Phân loại mức độ đúng (P1-P4) |",
        f"| Root Cause Accuracy | {_percent(metrics['top1_root_cause_accuracy'])} | Xác định đúng nguyên nhân gốc |",
        f"| Evidence Coverage | {_percent(metrics['evidence_coverage'])} | Đủ bằng chứng metric |",
        f"| Noisy Rejection | {_percent(metrics['noisy_rejection_rate'])} | Chặn đúng case nhiễu |",
        "",
    ]

    # --- Severity Confusion Matrix ---
    sev_matrix = metrics.get("severity_confusion_matrix", {})
    if sev_matrix:
        sev_levels = sorted({lv for row in sev_matrix.values() for lv in row} | set(sev_matrix.keys()))
        lines.extend([
            "## 4. Severity Confusion Matrix",
            "",
            "| Actual \\ Predicted | " + " | ".join(sev_levels) + " |",
            "|---" + "|---" * len(sev_levels) + "|",
        ])
        for actual in sev_levels:
            cells = [str(sev_matrix.get(actual, {}).get(pred, 0)) for pred in sev_levels]
            lines.append(f"| **{actual}** | " + " | ".join(cells) + " |")
        lines.append("")

    # --- Cross-validation ---
    lines.extend([
        "## 5. Đối chiếu Pipeline vs Rule trực tiếp",
        "",
        "| Đường chạy | Recall | Precision | F1 | Báo nhầm |",
        "|---|---:|---:|---:|---:|",
        f"| Pipeline (detect → Jira) | {_percent(metrics['incident_recall'])} | {_percent(metrics['incident_precision'])} | {_percent(metrics['f1_score'])} | {_percent(metrics['false_alarm_rate'])} |",
        f"| Rule trực tiếp | {_percent(payload['rule_baseline']['metrics']['incident_recall'])} | {_percent(payload['rule_baseline']['metrics']['incident_precision'])} | {_percent(payload['rule_baseline']['metrics'].get('f1_score'))} | {_percent(payload['rule_baseline']['metrics']['false_alarm_rate'])} |",
        "",
        "Hai đường phải khớp. Nếu lệch thì lỗi nằm ở wiring/collector.",
        "",
    ])

    # --- Per-family ---
    #
    # In SỐ ĐẾM, không in phần trăm.
    #
    # Bảng này từng in `Recall`, `Precision`, `F1` theo từng họ. Bỏ đi vì cỡ mẫu
    # mỗi họ quá nhỏ để phần trăm có nghĩa: `deployment` có ĐÚNG 1 case sự cố,
    # nên `recall = 0.0%` ở đó là một lần tung xu chứ không phải kết luận —
    # `UC-4` và `dependency` mỗi họ 3 case, tức sửa một case đổi 33 điểm.
    #
    # Phần trăm trên mẫu 1–3 case là con số **gây hiểu sai**: người đọc thấy
    # "0.0%" sẽ kết luận hệ thống hoàn toàn bất lực với loại đó, trong khi dữ
    # liệu chỉ đủ nói "case duy nhất bọn em thử thì trượt".
    #
    # Số đếm thô thì không nói quá: `0/1` tự nó cho thấy mẫu bé.
    lines.extend([
        "## 6. Số đếm theo họ sự cố",
        "",
        "| Họ | Bắt được | Bỏ lọt | Báo nhầm | Bắt / tổng sự cố |",
        "|---|---:|---:|---:|:---:|",
    ])
    for family, fm in metrics["per_family"].items():
        if not fm["true_incidents"] and not fm.get("false_positives", 0):
            continue
        tp = fm["true_positives"]
        tong = tp + fm["false_negatives"]
        lines.append(
            f"| {family} | {tp} | {fm['false_negatives']} | "
            f"{fm.get('false_positives', 0)} | **{tp}/{tong}** |"
        )
    lines.extend([
        "",
        "> Cố ý **không** in phần trăm ở bảng này. Họ nhỏ nhất có 1 case sự cố, họ",
        "> lớn nhất có 8 — phần trăm trên mẫu đó gây hiểu sai nhiều hơn là cho biết",
        "> thêm. `0/1` tự nó đã nói rõ mẫu bé tới đâu.",
    ])

    # --- Per-case results ---
    lines.extend(
        [
            "",
            "## 7. Kết quả từng case",
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
    lines.extend(["", "## 8. Top error để cải thiện tiếp", ""])
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
    parser = argparse.ArgumentParser(description="Chạy baseline offline cho 50 incident cases")
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
    cm = metrics["confusion_matrix"]
    print(f"{'='*60}")
    print(f"  EVALUATION RESULTS -- {metrics['case_count']} test cases")
    print(f"{'='*60}")
    print(f"  Confusion Matrix: TP={cm['TP']}  FN={cm['FN']}  FP={cm['FP']}  TN={cm['TN']}")
    print(f"{'-'*60}")
    print(f"  Recall       = {_percent(metrics['incident_recall'])}")
    print(f"  Precision    = {_percent(metrics['incident_precision'])}")
    print(f"  F1 Score     = {_percent(metrics['f1_score'])}")
    print(f"  F2 Score     = {_percent(metrics['f2_score'])}")
    print(f"  Accuracy     = {_percent(metrics['accuracy'])}")
    print(f"  Specificity  = {_percent(metrics['specificity'])}")
    print(f"  False Alarm  = {_percent(metrics['false_alarm_rate'])}")
    print(f"  MCC          = {_mcc_fmt(metrics['mcc'])}")
    print(f"{'-'*60}")
    print(f"  Severity Acc = {_percent(metrics['severity_accuracy'])}")
    print(f"  Root Cause   = {_percent(metrics['top1_root_cause_accuracy'])}")
    print(f"  Noisy Reject = {_percent(metrics['noisy_rejection_rate'])}")
    print(f"{'='*60}")
    print(f"  wrote={args.output_dir}")


if __name__ == "__main__":
    main()
