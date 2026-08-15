import json

import pytest

from eval.case_suite import (
    DEFAULT_CASES,
    compute_metrics,
    evaluate_case,
    evaluate_pipeline_case,
    load_suite,
    run_suite,
)


def test_dataset_co_dung_50_case_va_phan_bo_mentor_yeu_cau():
    suite = load_suite(DEFAULT_CASES)
    cases = suite["cases"]

    assert len(cases) == 50
    assert sum(case["split"] == "normal" for case in cases) == 15
    assert sum(case["split"] == "incident" for case in cases) == 25
    assert sum(case["split"] == "noisy" for case in cases) == 10
    assert sum(case["ground_truth"]["is_incident"] for case in cases) == 25


def test_moi_case_co_nguon_ground_truth_metric_va_guardrail():
    suite = load_suite(DEFAULT_CASES)

    for case in suite["cases"]:
        assert case["source_refs"]
        assert case["telemetry"]["service"]
        assert case["experiment"]["target"]
        assert case["experiment"]["action"]
        assert case["experiment"]["stop_condition"]
        assert "root_cause" in case["ground_truth"]


def test_baseline_hien_tai_co_ca_false_negative_va_false_positive():
    suite = load_suite(DEFAULT_CASES)
    results = [evaluate_case(case) for case in suite["cases"]]
    metrics = compute_metrics(results)

    assert metrics["confusion_matrix"] == {"TP": 18, "FN": 7, "FP": 7, "TN": 18}
    assert metrics["incident_recall"] == pytest.approx(0.72)
    assert metrics["incident_precision"] == pytest.approx(0.72)
    assert metrics["input_error_count"] == 0


def test_pipeline_prometheus_detect_jira_khop_voi_rule_truc_tiep():
    suite = load_suite(DEFAULT_CASES)
    direct = [evaluate_case(case) for case in suite["cases"]]
    pipeline = [evaluate_pipeline_case(case) for case in suite["cases"]]

    assert [item["classification"] for item in pipeline] == [
        item["classification"] for item in direct
    ]
    assert compute_metrics(pipeline)["incident_recall"] == pytest.approx(0.72)
    assert all(item["execution_mode"] == "prometheus-detect-jira" for item in pipeline)
    assert all(
        item["jira_issue_count"] == int(item["predicted_incident"])
        for item in pipeline
    )


def test_recall_tinh_ca_incident_bi_bo_lot():
    results = [
        {
            "classification": "TP",
            "expected_incident": True,
            "predicted_incident": True,
            "split": "incident",
            "family": "UC-X",
            "severity_correct": True,
            "root_cause_correct": True,
            "evidence_complete": True,
            "error": None,
        },
        {
            "classification": "FN",
            "expected_incident": True,
            "predicted_incident": False,
            "split": "incident",
            "family": "UC-X",
            "severity_correct": False,
            "root_cause_correct": False,
            "evidence_complete": False,
            "error": None,
        },
    ]

    metrics = compute_metrics(results)

    assert metrics["incident_recall"] == 0.5
    assert metrics["confusion_matrix"]["FN"] == 1


def test_runner_ghi_json_va_report_co_cong_thuc_recall(tmp_path):
    payload = run_suite(DEFAULT_CASES, tmp_path)

    saved = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert saved["metrics"]["incident_recall"] == payload["metrics"]["incident_recall"]
    assert saved["rule_baseline"]["metrics"] == payload["rule_baseline"]["metrics"]
    assert "**Recall**" in report
    assert "TP/(TP+FN)" in report
    assert "Pipeline (detect" in report
    assert "72.00%" in report
