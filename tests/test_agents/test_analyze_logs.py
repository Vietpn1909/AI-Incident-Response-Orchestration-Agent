"""Test cho node analyze_logs (src/agents/nodes/analyze_logs.py)."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolCall

from src.agents.nodes.analyze_logs import _prioritize_logs, analyze_logs
from src.models.incident import Hypothesis, IncidentSignal, LogEvidence, Severity


def _make_signal(service: str = "service-thanh-toan") -> IncidentSignal:
    return IncidentSignal(
        affected_service=service,
        severity=Severity.P2,
        detected_at=datetime.now(UTC),
        metric_name="http_request_duration_seconds p95",
        metric_value=5.0,
        threshold=2.0,
        breached_for_seconds=30.0,
    )


def _make_hypothesis() -> Hypothesis:
    return Hypothesis(
        statement="Connection pool cạn kiệt",
        confidence=0.85,
        reasoning="db_pool_connections_in_use chạm trần",
    )


def test_prioritize_logs():
    logs = [
        LogEvidence(source="s", level="WARNING", message="warn", pattern=""),
        LogEvidence(source="s", level="ERROR", message="err with pattern", pattern="DB_EXCEPTION"),
        LogEvidence(source="s", level="ERROR", message="err plain", pattern=""),
    ]
    sorted_logs = _prioritize_logs(logs)
    # Match pattern phải lên đầu tiên
    assert sorted_logs[0].pattern == "DB_EXCEPTION"
    assert sorted_logs[1].level == "ERROR"
    assert sorted_logs[2].level == "WARNING"


@patch("src.agents.nodes.analyze_logs.collect_logs_for_service")
def test_analyze_logs_no_logs_returns_original_hypothesis(mock_collect):
    mock_collect.return_value = []
    signal = _make_signal()
    hyp = _make_hypothesis()

    mock_llm = MagicMock()
    # Lần 1: LLM gọi tool
    tool_call = ToolCall(name="LogSearchTool", args={"start_time": "2026-08-10T10:03:00Z", "end_time": "2026-08-10T10:07:00Z"}, id="call_1")
    reply_1 = AIMessage(content="", tool_calls=[tool_call])
    # Lần 2: LLM trả về text sau khi tool trả rỗng
    reply_2 = AIMessage(content="Không có log, giữ nguyên.")

    mock_llm.bind_tools.return_value.invoke.side_effect = [reply_1, reply_2]

    res = analyze_logs(signal, hyp, llm=mock_llm)
    assert res.logs_collected == 0
    assert res.logs_relevant == 0
    # Lý giải được LLM cập nhật
    assert res.hypothesis.reasoning == "Không có log, giữ nguyên."
    assert len(res.hypothesis.log_evidence) == 0


@patch("src.agents.nodes.analyze_logs.collect_logs_for_service")
def test_analyze_logs_attaches_log_evidence(mock_collect):
    mock_logs = [
        LogEvidence(
            source="service-thanh-toan",
            timestamp="2026-08-10T22:30:00",
            level="ERROR",
            message="asyncpg.TooManyConnectionsError pool_size=5",
            pattern="DB_EXCEPTION",
        )
    ]
    mock_collect.return_value = mock_logs

    signal = _make_signal()
    hyp = _make_hypothesis()

    mock_llm = MagicMock()
    tool_call = ToolCall(name="LogSearchTool", args={"start_time": "2026-08-10T22:28:00Z", "end_time": "2026-08-10T22:32:00Z"}, id="call_1")
    reply_1 = AIMessage(content="", tool_calls=[tool_call])
    reply_2 = AIMessage(content="Lý giải đã được bổ sung thêm chi tiết từ log DB_EXCEPTION.")

    mock_llm.bind_tools.return_value.invoke.side_effect = [reply_1, reply_2]

    res = analyze_logs(signal, hyp, llm=mock_llm)
    assert res.logs_collected == 1
    assert res.logs_relevant == 1
    assert len(res.hypothesis.log_evidence) == 1
    assert res.hypothesis.log_evidence[0].pattern == "DB_EXCEPTION"
    assert "từ log DB_EXCEPTION" in res.hypothesis.reasoning


def test_log_chong_lung_thi_tin_cay_phai_tang():
    """Câu đúng không được đeo nhãn tin cậy của câu đoán mò.

    Đo ngày 11/08 trên KAN-17/KAN-18: log nêu đúng `UndefinedColumnError` ở cột
    `idempotency_key` và đúng cơ chế lan truyền, nhưng cả hai câu vẫn đeo nhãn
    30% và 10% thừa hưởng từ giả thuyết cũ — vì bảng điểm của `rules` chỉ biết
    `MetricEvidence`. Người trực đọc war room sẽ gạt đi đúng câu đáng tin nhất.
    """
    from src.agents.nodes.analyze_logs import DIEM_LOG_CHONG_LUNG, _tin_cay_sau_khi_log_nen_duoc

    assert _tin_cay_sau_khi_log_nen_duoc(0.10) == pytest.approx(0.10 + DIEM_LOG_CHONG_LUNG)
    assert _tin_cay_sau_khi_log_nen_duoc(0.30) == pytest.approx(0.30 + DIEM_LOG_CHONG_LUNG)


def test_tin_cay_khong_bao_gio_vuot_100_phan_tram():
    """Chặn ở 1.0 — cùng cách `rules._diem_tin_cay()` cộng dồn rồi chặn."""
    from src.agents.nodes.analyze_logs import _tin_cay_sau_khi_log_nen_duoc

    assert _tin_cay_sau_khi_log_nen_duoc(0.9) == 1.0
    assert _tin_cay_sau_khi_log_nen_duoc(1.0) == 1.0
