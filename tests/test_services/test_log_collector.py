"""Test cho service thu thập log (src/services/log_collector.py)."""

from unittest.mock import MagicMock, patch

from src.models.incident import LogEvidence
from src.services.log_collector import (
    _infer_level,
    _match_pattern,
    _parse_and_filter,
    _parse_log_line,
    collect_container_logs,
    collect_logs_for_service,
)


def test_infer_level():
    assert _infer_level("Fatal error in worker") == "ERROR"
    assert _infer_level("Warning: high memory usage") == "WARNING"
    assert _infer_level("User logged in successfully") == "INFO"


def test_match_pattern():
    assert _match_pattern("POOL_EXHAUSTED: all 5 connections in use") == "POOL_EXHAUSTED"
    assert _match_pattern("POOL_NEAR_EXHAUSTION: 4/5 connections in use") == "POOL_NEAR_EXHAUSTION"
    assert _match_pattern("MEMORY_LEAK_GROWING: retaining batch 5") == "MEMORY_LEAK_GROWING"
    assert _match_pattern("AUTH_FAILURE: login failed from IP 1.2.3.4") == "AUTH_FAILURE"
    assert _match_pattern("UPSTREAM_TIMEOUT: service thanh toan timeout") == "UPSTREAM_TIMEOUT"
    assert _match_pattern("Normal log message") == ""


def test_parse_log_line_structured():
    line = "2026-08-10T22:30:00 [ERROR] service-thanh-toan: POOL_EXHAUSTED: Connection pool cạn kiệt"
    evidence = _parse_log_line(line, default_source="service-thanh-toan")
    assert evidence is not None
    assert evidence.source == "service-thanh-toan"
    assert evidence.timestamp == "2026-08-10T22:30:00"
    assert evidence.level == "ERROR"
    assert "POOL_EXHAUSTED" in evidence.message
    assert evidence.pattern == "POOL_EXHAUSTED"


def test_parse_log_line_docker_timestamp_prefix():
    # Docker --timestamps prepends its own ISO timestamp: 2026-08-10T15:30:00.123456789Z
    line = "2026-08-10T15:30:00.123456789Z 2026-08-10T22:30:00 [WARNING] service-thanh-toan: POOL_NEAR_EXHAUSTION: 4/5"
    evidence = _parse_log_line(line, default_source="service-thanh-toan")
    assert evidence is not None
    assert evidence.source == "service-thanh-toan"
    assert evidence.level == "WARNING"
    assert evidence.pattern == "POOL_NEAR_EXHAUSTION"


def test_parse_and_filter_ignores_info_without_pattern():
    raw_logs = (
        "2026-08-10T22:30:00 [INFO] service-thanh-toan: Normal request 200 OK\n"
        "2026-08-10T22:30:01 [ERROR] service-thanh-toan: POOL_EXHAUSTED: pool full\n"
        "2026-08-10T22:30:02 [WARNING] service-thanh-toan: high memory\n"
    )
    result = _parse_and_filter(raw_logs, "service-thanh-toan", max_lines=10)
    assert len(result) == 2
    assert result[0].level == "ERROR"
    assert result[1].level == "WARNING"


@patch("subprocess.run")
def test_collect_container_logs_success(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="2026-08-10T22:30:01 [ERROR] service-thanh-toan: POOL_EXHAUSTED: pool full\n",
        stderr="",
    )
    logs = collect_container_logs("service-thanh-toan", "2026-08-10T10:03:00Z", "2026-08-10T10:07:00Z")
    assert len(logs) == 1
    assert logs[0].pattern == "POOL_EXHAUSTED"


@patch("subprocess.run")
def test_collect_logs_for_service_tries_candidates(mock_run):
    # Lần thử 1 (service-thanh-toan) rỗng, lần thử 2 (p035-demo-service-thanh-toan-1) có log
    def side_effect(cmd, **kwargs):
        container = cmd[-1]
        if container == "p035-demo-service-thanh-toan-1":
            return MagicMock(
                returncode=0,
                stdout="2026-08-10T22:30:01 [ERROR] service-thanh-toan: AUTH_FAILURE: failed\n",
                stderr="",
            )
        return MagicMock(returncode=1, stdout="", stderr="No such container")

    mock_run.side_effect = side_effect

    logs = collect_logs_for_service("service-thanh-toan", "2026-08-10T10:03:00Z", "2026-08-10T10:07:00Z")
    assert len(logs) == 1
    assert logs[0].pattern == "AUTH_FAILURE"

