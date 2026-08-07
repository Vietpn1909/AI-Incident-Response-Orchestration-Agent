import csv
import json
from datetime import UTC, datetime

import pytest

from eval import run_measurements
from eval.run_measurements import diagnosis_correct
from src.agents.nodes.hypothesize import HypothesisOutcome
from src.models.incident import Hypothesis, IncidentSignal, MetricEvidence, Severity


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Burst phù hợp credential-stuffing, không phải quá tải.", True),
        ("Đây là vấn đề bảo mật, không phải là quá tải.", True),
        ("Service quá tải nên login thất bại.", False),
        ("Connection pool cạn.", False),
        ("Chưa xác định được nguyên nhân gốc.", False),
    ],
)
def test_cham_uc3_hieu_phu_dinh(text: str, expected: bool):
    assert diagnosis_correct("UC-3", text) is expected


def test_cham_uc2_khong_nhan_cau_phu_dinh_oom():
    text = (
        "Không có nguyên nhân gốc từ quá tải bộ nhớ hoặc crash container. "
        "Số liệu không cho thấy áp lực bộ nhớ."
    )

    assert not diagnosis_correct("UC-2", text)


def test_diagnose_ghi_ro_cau_tu_luat(tmp_path, monkeypatch):
    signal = IncidentSignal(
        affected_service="service-thanh-toan",
        severity=Severity.P2,
        detected_at=datetime.now(UTC),
        metric_name="p95",
        metric_value=3.0,
        threshold=2.0,
        breached_for_seconds=60.0,
        evidence=[MetricEvidence(name="db_pool", value=1.0)],
    )
    source = tmp_path / "signal.json"
    source.write_text(
        json.dumps({"incidents": [{"signal": signal.model_dump(mode="json")}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    output = tmp_path / "runs.csv"
    rule_hypothesis = Hypothesis(
        statement="Connection pool cạn kiệt.",
        confidence=0.4,
        evidence=signal.evidence,
    )
    monkeypatch.setattr(
        run_measurements,
        "hypothesize_with_origin",
        lambda _signal: HypothesisOutcome(rule_hypothesis, "rule"),
    )

    run_measurements.diagnose(source, "UC-1", 1, output)

    row = next(csv.DictReader(output.open(encoding="utf-8")))
    assert row["statement_origin"] == "rule"
    assert row["diagnosis_correct"] == "true"
    assert row["expected_severity"] == "P2"
    assert row["ground_truth"] == "Pool giới hạn 5 bị chiếm hết; truy vấn chậm giữ connection."
