"""Test cho service thu thập log (src/services/log_collector.py)."""

from unittest.mock import MagicMock, patch

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


def test_match_pattern_khop_su_kien_ky_thuat():
    """Pattern khớp thứ FRAMEWORK sinh, không khớp nhãn mình tự gắn."""
    assert _match_pattern("Traceback (most recent call last)") == "TRACEBACK"
    assert (
        _match_pattern('asyncpg.exceptions.UndefinedColumnError: column "x" does not exist')
        == "DB_EXCEPTION"
    )
    assert _match_pattern("httpx.TimeoutException upstream=http://x timeout_s=2") == "HTTP_EXCEPTION"
    assert _match_pattern("pool_in_use=5 pool_size=5") == "POOL_METRIC"
    assert _match_pattern("batch_retained=8 rows_retained=40000 rss_mb=118.4") == "MEMORY_METRIC"
    assert _match_pattern("login failed status=401 source_ip=1.2.3.4 username=admin") == "AUTH_401"
    assert _match_pattern("Normal log message") == ""


def test_khong_con_nhan_chan_doan_nao_duoc_nhan():
    """Chốt lại: nhãn kết luận không còn là pattern hợp lệ.

    Bản 11/08 khớp `POOL_EXHAUSTED`, `MEMORY_LEAK_GROWING`, `UPSTREAM_TIMEOUT` —
    những nhãn demo service tự gắn để **tự chẩn đoán chính nó**. Đo thật cho thấy
    khi đó LLM chỉ chép lại nhãn, nên mọi con số M3 mất nghĩa.

    Test này đỏ nếu ai thêm lại nhãn chẩn đoán vào bảng pattern.
    """
    for nhan in (
        "POOL_EXHAUSTED: pool cạn kiệt",
        "MEMORY_LEAK_GROWING: bộ nhớ sẽ tăng cho tới khi OOM",
        "UPSTREAM_TIMEOUT: lan truyền sự cố từ downstream",
        "PAYMENT_ERROR: lỗi khi xử lý thanh toán",
    ):
        assert _match_pattern(nhan) == "", f"nhãn chẩn đoán bị nhận lại: {nhan}"


def test_parse_log_line_structured():
    line = "2026-08-10T22:30:00 [ERROR] service-thanh-toan: asyncpg.TooManyConnectionsError pool_size=5 path=/pay"
    evidence = _parse_log_line(line, default_source="service-thanh-toan")
    assert evidence is not None
    assert evidence.source == "service-thanh-toan"
    assert evidence.timestamp == "2026-08-10T22:30:00"
    assert evidence.level == "ERROR"
    assert "TooManyConnectionsError" in evidence.message
    assert evidence.pattern == "DB_EXCEPTION"


def test_parse_log_line_docker_timestamp_prefix():
    # Docker --timestamps prepends its own ISO timestamp: 2026-08-10T15:30:00.123456789Z
    line = "2026-08-10T15:30:00.123456789Z 2026-08-10T22:30:00 [WARNING] service-thanh-toan: pool_in_use=4 pool_size=5"
    evidence = _parse_log_line(line, default_source="service-thanh-toan")
    assert evidence is not None
    assert evidence.source == "service-thanh-toan"
    assert evidence.level == "WARNING"
    assert evidence.pattern == "POOL_METRIC"


def test_parse_and_filter_ignores_info_without_pattern():
    raw_logs = (
        "2026-08-10T22:30:00 [INFO] service-thanh-toan: Normal request 200 OK\n"
        "2026-08-10T22:30:01 [ERROR] service-thanh-toan: asyncpg.TooManyConnectionsError pool_size=5\n"
        "2026-08-10T22:30:02 [WARNING] service-thanh-toan: high memory\n"
    )
    result = _parse_and_filter(raw_logs, "service-thanh-toan", max_lines=10)
    assert len(result) == 2
    assert result[0].level == "ERROR"
    assert result[1].level == "WARNING"


@patch("subprocess.run")
def test_collect_container_logs_success(mock_run):
    # stdout mô phỏng ĐÚNG dạng `docker logs --timestamps` trả về: mốc của
    # Docker (UTC) đứng trước, rồi mới tới dòng log của ứng dụng. Cửa sổ lọc so
    # với mốc ĐẦU DÒNG — xem `_trong_cua_so()`.
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=(
            "2026-08-10T10:05:00.123456789Z "
            "2026-08-10T17:05:00 [ERROR] service-thanh-toan: "
            "asyncpg.TooManyConnectionsError pool_size=5\n"
        ),
        stderr="",
    )
    logs = collect_container_logs("service-thanh-toan", "2026-08-10T10:03:00Z", "2026-08-10T10:07:00Z")
    assert len(logs) == 1
    assert logs[0].pattern == "DB_EXCEPTION"


@patch("subprocess.run")
def test_collect_container_logs_khong_dung_since_until(mock_run):
    """Không được truyền `--since`/`--until` cho `docker logs`.

    Chúng im lặng trả rỗng khi Docker Desktop lệch giờ, mà rỗng ở đây bị hiểu
    thành "log sạch" — một bằng chứng SAI hiện thẳng lên war room. Đo ngày
    23/08: `--since 10m` trả 0 dòng trong khi container vẫn đang ghi log.
    """
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    collect_container_logs("service-thanh-toan", "2026-08-10T10:03:00Z", "2026-08-10T10:07:00Z")
    cmd = mock_run.call_args[0][0]
    assert "--since" not in cmd
    assert "--until" not in cmd
    assert "--timestamps" in cmd


@patch("subprocess.run")
def test_collect_container_logs_loc_dong_ngoai_cua_so(mock_run):
    """Dòng nằm ngoài cửa sổ bị loại, dòng trong cửa sổ được giữ."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=(
            "2026-08-10T09:00:00.000000000Z [ERROR] cu: qua som\n"
            "2026-08-10T10:05:00.000000000Z [ERROR] service-thanh-toan: "
            "asyncpg.TooManyConnectionsError pool_size=5\n"
            "2026-08-10T23:00:00.000000000Z [ERROR] moi: qua muon\n"
        ),
        stderr="",
    )
    logs = collect_container_logs("service-thanh-toan", "2026-08-10T10:03:00Z", "2026-08-10T10:07:00Z")
    assert len(logs) == 1
    assert "TooManyConnectionsError" in logs[0].message


@patch("subprocess.run")
def test_collect_logs_for_service_tries_candidates(mock_run):
    # Lần thử 1 (service-thanh-toan) rỗng, lần thử 2 (p035-demo-service-thanh-toan-1) có log
    def side_effect(cmd, **kwargs):
        container = cmd[-1]
        if container == "p035-demo-service-thanh-toan-1":
            return MagicMock(
                returncode=0,
                stdout=(
                    "2026-08-10T10:05:01.000000000Z "
                    "2026-08-10T17:05:01 [ERROR] service-thanh-toan: "
                    "login failed status=401 source_ip=1.2.3.4\n"
                ),
                stderr="",
            )
        return MagicMock(returncode=1, stdout="", stderr="No such container")

    mock_run.side_effect = side_effect

    logs = collect_logs_for_service("service-thanh-toan", "2026-08-10T10:03:00Z", "2026-08-10T10:07:00Z")
    assert len(logs) == 1
    assert logs[0].pattern == "AUTH_401"

