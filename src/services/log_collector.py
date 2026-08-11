"""Thu thập log từ container Docker — chỉ khi có sự cố.

CHỦ SỞ HỮU: (Tính năng mới — Log Analysis)

Nguyên tắc Event-Driven: **KHÔNG** đọc log stream 24/7. Chỉ gọi khi Rule
Engine đã phát hiện bất thường → thu thập log trong khoảng thời gian sự cố
→ lọc theo pattern → trả về cho Agent phân tích.

Cách tiếp cận hiện tại: gọi ``docker logs --since`` qua subprocess. Không cần
thêm infrastructure (Loki, ELK). Khi dự án cần scale lên, thay hàm
``collect_container_logs()`` bằng Loki API mà interface không đổi.

Log của demo service ghi **sự kiện**, không ghi kết luận — xem chú thích ở
``INCIDENT_PATTERNS``. Service không được tự chẩn đoán chính nó, vì khi đó Agent
chỉ đọc lại đáp án và phép đo M3 mất hết ý nghĩa.
"""

from __future__ import annotations

import logging
import re
import subprocess

from src.models.incident import LogEvidence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pattern xếp ưu tiên — khớp SỰ KIỆN kỹ thuật, KHÔNG khớp kết luận
# ---------------------------------------------------------------------------

#: Bản đầu (11/08) khớp các nhãn `POOL_EXHAUSTED`, `MEMORY_LEAK_GROWING`,
#: `UPSTREAM_TIMEOUT`… mà demo service tự gắn vào log. Vấn đề: những nhãn đó là
#: **kết luận**, không phải sự kiện — service tự chẩn đoán chính nó rồi Agent
#: đọc lại. Đo M3 khi đó chỉ đo được khả năng chép chữ in hoa.
#:
#: Đo thật ngày 11/08 với bốn điều kiện cho thấy khác biệt:
#:   chỉ metric                      → "pool cạn / quá tải"   SAI
#:   metric + ghi chú deploy gợi ý    → đúng, nhưng ghi chú nói hộ
#:   metric + ghi chú trung thực      → "có thể do một trong ba thứ"
#:   metric + ghi chú + LOG           → "cột idempotency_key chưa tồn tại"  ĐÚNG
#:
#: Nên pattern giờ khớp thứ **framework tự sinh** — tên lớp exception, traceback,
#: cặp khoá=giá trị. Chúng chỉ dùng để **xếp thứ tự ưu tiên** khi cắt còn 50 dòng
#: gửi cho LLM (`analyze_logs._prioritize_logs`), KHÔNG đi vào prompt, nên không
#: có đường nào mớm kết luận cho LLM.
INCIDENT_PATTERNS: dict[str, re.Pattern[str]] = {
    # Traceback và tên lớp exception — do Python/thư viện sinh, ưu tiên cao nhất
    # vì đây là chỗ duy nhất nói được LỖI GÌ, ở DÒNG NÀO.
    "TRACEBACK": re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE),
    "DB_EXCEPTION": re.compile(r"asyncpg\.\w*(Error|Exception)", re.IGNORECASE),
    "HTTP_EXCEPTION": re.compile(r"httpx\.\w*(Error|Exception)", re.IGNORECASE),
    "UNHANDLED": re.compile(r"unhandled exception", re.IGNORECASE),
    # Cặp khoá=giá trị do service ghi ra. Là SỰ KIỆN đo được, không phải kết luận.
    "POOL_METRIC": re.compile(r"pool_in_use=\d+", re.IGNORECASE),
    "MEMORY_METRIC": re.compile(r"rss_mb=[\d.]+", re.IGNORECASE),
    "AUTH_401": re.compile(r"login failed status=401", re.IGNORECASE),
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

    # ⚠️ Xếp ưu tiên TRƯỚC khi cắt.
    #
    # Bản đầu `break` ngay khi đủ `max_lines`, tức lấy 50 dòng ĐẦU TIÊN. Đo ngày
    # 11/08 trên UC-4: 50 dòng access log 500 tới trước, traceback
    # `UndefinedColumnError` nằm sau nên bị cắt mất — LLM không bao giờ thấy
    # dòng duy nhất nói được nguyên nhân, và chẩn đoán sai.
    #
    # Dòng có pattern (traceback, exception) đứng trước, rồi ERROR, rồi WARNING.
    evidence.sort(key=lambda e: (0 if e.pattern else 1, 0 if e.level == "ERROR" else 1))
    return evidence[:max_lines]


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


#: Access log của uvicorn: `INFO:  1.2.3.4:5678 - "POST /pay HTTP/1.1" 500 …`
#:
#: Dòng này mở đầu bằng `INFO:` nhưng chứa chuỗi "Internal Server Error", nên
#: dò chuỗi sẽ xếp nó thành ERROR. Đo ngày 11/08: 50 dòng access log như vậy
#: chiếm hết hạn mức rồi traceback thật KHÔNG BAO GIỜ tới được LLM — Agent
#: chẩn đoán sai UC-4 vì bằng chứng quan trọng nhất bị nhiễu đẩy ra ngoài.
_UVICORN_ACCESS_RE = re.compile(r'^INFO:\s', re.IGNORECASE)


def _infer_level(message: str) -> str:
    """Suy ra log level từ nội dung message khi không có level tường minh.

    Level tường minh ở đầu dòng THẮNG việc dò chuỗi trong nội dung. Không có
    quy tắc này thì mọi access log trả 5xx đều bị coi là ERROR.
    """
    if _UVICORN_ACCESS_RE.match(message):
        return "INFO"
    upper = message.upper()
    if "ERROR" in upper or "CRITICAL" in upper or "FATAL" in upper:
        return "ERROR"
    if "WARNING" in upper or "WARN" in upper:
        return "WARNING"
    return "INFO"
