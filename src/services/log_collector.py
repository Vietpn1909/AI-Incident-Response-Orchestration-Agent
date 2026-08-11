"""Thu thập log từ container Docker — chỉ khi có sự cố.

CHỦ SỞ HỮU: (Tính năng mới — Log Analysis)

Nguyên tắc Event-Driven: **KHÔNG** đọc log stream 24/7. Chỉ gọi khi Rule
Engine đã phát hiện bất thường → thu thập log trong khoảng thời gian sự cố
→ lọc theo pattern → trả về cho Agent phân tích.

Cách tiếp cận hiện tại: gọi ``docker logs --since`` qua subprocess. Không cần
thêm infrastructure (Loki, ELK). Khi dự án cần scale lên, thay hàm
``collect_container_logs()`` bằng Loki API mà interface không đổi.

Pattern quan trọng được đánh dấu sẵn trong log của demo service:
- ``POOL_NEAR_EXHAUSTION`` / ``POOL_EXHAUSTED`` — UC-1
- ``MEMORY_LEAK_GROWING`` — UC-2
- ``AUTH_FAILURE`` — UC-3
- ``UPSTREAM_TIMEOUT`` / ``UPSTREAM_ERROR`` — UC-1a (lan truyền)
- ``PAYMENT_ERROR`` — lỗi tổng quát
"""

from __future__ import annotations

import logging
import re
import subprocess
from datetime import datetime, timedelta

from src.models.incident import LogEvidence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pattern phát hiện — khớp với các tag đã gắn trong demo service log
# ---------------------------------------------------------------------------

#: Các pattern quan trọng cần trích xuất từ log. Mỗi pattern khớp với một
#: loại sự cố cụ thể — Agent dùng chúng để bổ sung bằng chứng cho giả thuyết.
INCIDENT_PATTERNS: dict[str, re.Pattern[str]] = {
    "POOL_EXHAUSTED": re.compile(r"POOL_EXHAUSTED:.*", re.IGNORECASE),
    "POOL_NEAR_EXHAUSTION": re.compile(r"POOL_NEAR_EXHAUSTION:.*", re.IGNORECASE),
    "MEMORY_LEAK_GROWING": re.compile(r"MEMORY_LEAK_GROWING:.*", re.IGNORECASE),
    "AUTH_FAILURE": re.compile(r"AUTH_FAILURE:.*", re.IGNORECASE),
    "UPSTREAM_TIMEOUT": re.compile(r"UPSTREAM_TIMEOUT:.*", re.IGNORECASE),
    "UPSTREAM_ERROR": re.compile(r"UPSTREAM_ERROR:.*", re.IGNORECASE),
    "UPSTREAM_UNREACHABLE": re.compile(r"UPSTREAM_UNREACHABLE:.*", re.IGNORECASE),
    "PAYMENT_ERROR": re.compile(r"PAYMENT_ERROR:.*", re.IGNORECASE),
}

#: Log level được coi là "đáng chú ý" — bỏ qua INFO thông thường để giảm
#: nhiễu và tiết kiệm token khi gửi cho LLM.
NOTABLE_LEVELS = {"ERROR", "WARNING", "CRITICAL"}

#: Regex phân tách tiền tố timestamp do Docker `--timestamps` tự động chèn vào đầu mỗi dòng.
#: Ví dụ: ``2026-08-10T15:30:00.123456789Z ``
_DOCKER_TS_PREFIX_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\s+"
)

#: Regex phân tách một dòng log theo format đã cấu hình trong demo service.
#: Format: ``2026-08-10T22:30:00 [ERROR] service-thanh-toan: message``
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
    r"\s+\[(?P<level>\w+)\]\s+"
    r"(?P<source>[^:]+):\s+"
    r"(?P<message>.+)$"
)

#: Số dòng log tối đa trả về cho mỗi lần thu thập. Giữ thấp để không đốt
#: token LLM vào những dòng log lặp lại.
MAX_LOG_LINES = 50


def collect_container_logs(
    container_name: str,
    start_time: str,
    end_time: str,
    *,
    max_lines: int = MAX_LOG_LINES,
) -> list[LogEvidence]:
    """Thu thập log từ một Docker container trong một khoảng thời gian cụ thể.

    Args:
        container_name: Tên container Docker (khớp tên trong docker-compose).
        start_time: Thời gian bắt đầu (chuỗi ISO 8601).
        end_time: Thời gian kết thúc (chuỗi ISO 8601).
        max_lines: Giới hạn số dòng log trả về.

    Returns:
        Danh sách ``LogEvidence``, đã lọc chỉ giữ ERROR/WARNING và các pattern
        quan trọng. Rỗng nếu container không tồn tại hoặc không có log đáng chú ý.
    """
    try:
        result = subprocess.run(
            [
                "docker", "logs",
                "--since", start_time,
                "--until", end_time,
                "--timestamps",
                container_name,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if result.returncode != 0:
            return []
        raw_output = (result.stdout or "") + (result.stderr or "")
    except FileNotFoundError:
        logger.warning("Docker CLI không tìm thấy — không thu thập được log")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("docker logs timeout sau 10s cho container %s", container_name)
        return []
    except Exception as exc:
        logger.warning("Lỗi khi gọi docker logs cho %s: %s", container_name, exc)
        return []

    if not raw_output.strip():
        logger.info("Container %s không có log từ %s đến %s", container_name, start_time, end_time)
        return []

    return _parse_and_filter(raw_output, container_name, max_lines)


def collect_logs_for_service(
    service: str,
    start_time: str,
    end_time: str,
) -> list[LogEvidence]:
    """Thu thập log cho một service — thử nhiều tên container phổ biến.

    Docker Compose đặt tên container theo format ``<project>-<service>-1``
    hoặc ``<service>``. Hàm này thử tất cả các mẫu phổ biến.
    """
    # Các tên container phổ biến trong docker-compose demo
    candidates = [
        service,
        f"p035-demo-{service}-1",
        f"p035-demo_{service}_1",
        f"p-035-{service}-1",
        f"demo-{service}-1",
        f"{service}-1",
    ]

    for name in candidates:
        evidence = collect_container_logs(name, start_time, end_time)
        if evidence:
            return evidence

    logger.info("Không tìm thấy log cho service %s (đã thử: %s)", service, candidates)
    return []


def _parse_and_filter(
    raw_output: str,
    container_name: str,
    max_lines: int,
) -> list[LogEvidence]:
    """Parse log thô và lọc chỉ giữ dòng quan trọng."""
    evidence: list[LogEvidence] = []

    for line in raw_output.splitlines():
        line = line.strip()
        if not line:
            continue

        parsed = _parse_log_line(line, container_name)
        if parsed is None:
            continue

        # Lọc: chỉ giữ ERROR/WARNING hoặc dòng có pattern đặc biệt
        if parsed.level not in NOTABLE_LEVELS and not parsed.pattern:
            continue

        evidence.append(parsed)

        if len(evidence) >= max_lines:
            break

    return evidence


def _parse_log_line(line: str, default_source: str) -> LogEvidence | None:
    """Parse một dòng log thành LogEvidence.

    Hỗ trợ cả structured format và Docker timestamps format.
    """
    docker_ts = ""
    docker_match = _DOCKER_TS_PREFIX_RE.match(line)
    if docker_match:
        docker_ts = line[:19]
        line = line[docker_match.end():].strip()

    if not line:
        return None

    # Thử format structured trước
    match = _LOG_LINE_RE.match(line)
    if match:
        timestamp = match.group("timestamp") or docker_ts
        level = match.group("level").upper()
        source = match.group("source").strip()
        message = match.group("message").strip()
    else:
        # Fallback: Docker timestamp format hoặc plain log line
        parts = line.split(" ", 1)
        if len(parts) >= 2 and _DOCKER_TS_PREFIX_RE.match(parts[0] + " "):
            timestamp = parts[0][:19]
            message = parts[1].strip()
        else:
            timestamp = docker_ts
            message = line.strip()
        level = _infer_level(message)
        source = default_source

    pattern = _match_pattern(message)

    return LogEvidence(
        source=source,
        timestamp=timestamp,
        level=level,
        message=message[:500],  # Giới hạn độ dài message
        pattern=pattern,
    )



def _match_pattern(message: str) -> str:
    """Tìm pattern đầu tiên khớp với message."""
    for name, regex in INCIDENT_PATTERNS.items():
        if regex.search(message):
            return name
    return ""


def _infer_level(message: str) -> str:
    """Suy ra log level từ nội dung message khi không có level tường minh."""
    upper = message.upper()
    if "ERROR" in upper or "CRITICAL" in upper or "FATAL" in upper:
        return "ERROR"
    if "WARNING" in upper or "WARN" in upper:
        return "WARNING"
    return "INFO"
