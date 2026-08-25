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
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime

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

#: Hai mức `--tail` đọc rồi GHÉP lại.
#:
#: ## Vì sao phải đọc hai lần thay vì một lần thật to
#:
#: `docker logs --tail N` trên Docker Desktop trả về lát cắt từ **một file log
#: duy nhất**, không ghép các file đã xoay vòng. Đo ngày 23/08 trên
#: `p035-demo-service-thanh-toan-1`, cùng một thời điểm:
#:
#:     --tail   80 → 12:58:26 .. 13:04:18   WARNING=0     ← file đang ghi
#:     --tail  400 → 12:58:18 .. 12:58:23   WARNING=142   ← file đã xoay vòng
#:     --tail 2000 → 12:57:44 .. 12:58:23   WARNING=921
#:
#: Chú ý dòng cuối: mức 400 và 2000 **dừng ở 12:58:23**, không hề chứa 80 dòng
#: gần nhất — hai tập rời nhau chứ không lồng nhau. Đợt tải nặng đẩy hàng nghìn
#: dòng vào một file rồi xoay sang file mới, và mỗi mức `--tail` rơi vào một file.
#:
#: Hệ quả nếu chỉ đọc một mức: mức nhỏ cho log MỚI nhưng rỗng bằng chứng, mức
#: lớn cho đúng lúc sự cố nhưng thiếu phần hiện tại. Cả hai đều dẫn tới kết luận
#: "log sạch" — một khẳng định SAI trong khi 921 dòng `pool_in_use=5 pool_size=5`
#: đang nằm ngay đó.
#:
#: Nên đọc cả hai rồi ghép, khử trùng, xếp lại theo mốc thời gian. Mốc do Docker
#: chèn có độ phân giải nano giây nên dòng trùng khử được chính xác.
_TAIL_RONG = 4000
_TAIL_HEP = 200


def _moc_docker(dong: str) -> datetime | None:
    """Mốc thời gian ở đầu dòng do `docker logs --timestamps` chèn. Luôn UTC."""
    if not _DOCKER_TS_PREFIX_RE.match(dong):
        return None
    try:
        return datetime.strptime(dong[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _doc_moc(gia_tri: str) -> datetime | None:
    """Chuỗi ISO từ phía gọi → datetime có múi giờ. None nếu không đọc được."""
    try:
        moc = datetime.fromisoformat(gia_tri.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return None
    return moc if moc.tzinfo else moc.replace(tzinfo=UTC)


def _ghep_lat_cat(*manh: str) -> str:
    """Ghép nhiều lát cắt `docker logs`, khử dòng trùng, xếp theo mốc thời gian."""
    da_co: set[str] = set()
    dong: list[str] = []
    for manh_mot in manh:
        for d in manh_mot.splitlines():
            if d.strip() and d not in da_co:
                da_co.add(d)
                dong.append(d)
    # Dòng không đọc được mốc thì giữ nguyên thứ tự tương đối bằng cách xếp
    # chúng xuống cuối — thà lệch chỗ còn hơn biến mất.
    xa = datetime.max.replace(tzinfo=UTC)
    dong.sort(key=lambda d: _moc_docker(d) or xa)
    return "\n".join(dong)


def _doc_log_tho(container_name: str) -> str:
    """Log thô của container, ghép từ hai mức `--tail` — xem `_TAIL_RONG`."""
    manh = [raw for raw in (
        _chay_docker_logs(container_name, _TAIL_RONG),
        _chay_docker_logs(container_name, _TAIL_HEP),
    ) if raw]
    return _ghep_lat_cat(*manh) if manh else ""


def _cu_nhat_sau(raw_output: str, end_time: str) -> bool:
    """Dòng CŨ NHẤT đọc được có nằm sau `end_time` không.

    Đúng nghĩa là cửa sổ đang hỏi đã trôi khỏi phần log container còn giữ.
    """
    ket_thuc = _doc_moc(end_time)
    if ket_thuc is None:
        return False
    for dong in raw_output.splitlines():
        moc = _moc_docker(dong)
        if moc is not None:
            return moc > ket_thuc
    return False


def _trong_cua_so(raw_output: str, start_time: str, end_time: str) -> str:
    """Giữ lại các dòng có mốc `docker logs --timestamps` nằm trong cửa sổ.

    ## Vì sao tự lọc thay vì để `docker logs --since/--until` làm

    Vì `--since` **im lặng trả rỗng** khi Docker Desktop lệch giờ, và đó là kiểu
    hỏng tệ nhất cho tính năng này: không có dòng nào thì `thu_thap_co_ly_do()`
    báo `log-sach`, tức UI khẳng định với người trực rằng "service không ghi
    dòng lỗi nào" — một BẰNG CHỨNG sai, chứ không phải một lỗi kỹ thuật họ nhìn
    ra được.

    Đo ngày 23/08 trên máy Windows sau khi host ngủ rồi thức, container
    `p035-demo-service-kho-hang-1` có 2.212 dòng, dòng cuối `10:12:01Z`, daemon
    cũng báo `10:12:14 UTC`:

        docker logs --since 2026-01-01T00:00:00Z  → 2212 dòng
        docker logs --since 2026-08-23T00:00:00Z  →    0 dòng   ← sai
        docker logs --since 10m                   →    0 dòng   ← sai
        docker logs --since 1h                    →    0 dòng   ← sai

    Cả ba container demo đều vậy, mọi định dạng đều vậy. Mốc tuyệt đối của chính
    dòng log (`--timestamps`) thì luôn đúng — nên lọc theo nó.

    Dòng không có tiền tố mốc thì GIỮ: thà thừa một dòng còn hơn lặng lẽ bỏ mất
    dòng nói ra nguyên nhân.
    """
    bat_dau, ket_thuc = _doc_moc(start_time), _doc_moc(end_time)
    if bat_dau is None or ket_thuc is None:
        return raw_output

    giu = []
    for dong in raw_output.splitlines():
        moc = _moc_docker(dong)
        if moc is None or bat_dau <= moc <= ket_thuc:
            giu.append(dong)
    return "\n".join(giu)


def _chay_docker_logs(container_name: str, tail: int) -> str | None:
    """`docker logs --timestamps --tail <tail>`. None nếu không gọi được."""
    try:
        ket_qua = subprocess.run(  # noqa: S603
            ["docker", "logs", "--timestamps", "--tail", str(tail), container_name],  # noqa: S607
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except FileNotFoundError:
        logger.warning("Docker CLI không tìm thấy — không thu thập được log")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("docker logs timeout sau 10s cho container %s", container_name)
        return None
    except Exception as exc:
        logger.warning("Lỗi khi gọi docker logs cho %s: %s", container_name, exc)
        return None
    if ket_qua.returncode != 0:
        return None
    return (ket_qua.stdout or "") + (ket_qua.stderr or "")


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
    # ⚠️ KHÔNG dùng `--since` / `--until`, và không tin một mức `--tail` duy nhất
    # — xem `_trong_cua_so()` và `_TAIL_RONG`. Cả hai đều im lặng trả sai khi
    # Docker Desktop lệch giờ hoặc log đã xoay vòng, mà rỗng ở đây bị hiểu thành
    # "log sạch", tức một bằng chứng SAI.
    raw_output = _doc_log_tho(container_name)
    if not raw_output.strip():
        return []

    trong_cua_so = _trong_cua_so(raw_output, start_time, end_time)
    if not trong_cua_so.strip():
        # Mọi dòng còn giữ đều MỚI HƠN cửa sổ → cửa sổ đã trôi mất, không phải
        # "không có dòng nào đáng chú ý". Phân biệt được vì ta đang cầm cả phần
        # thô: dòng cũ nhất đọc được mà vẫn sau `end_time` thì phần cần tìm đã
        # bị đẩy ra khỏi log từ lâu.
        #
        # Quan trọng với war room: gần như MỌI phiếu đã đóng đều rơi vào đây, và
        # báo chúng thành "log sạch" là khẳng định sai về một sự cố có thật.
        if _cu_nhat_sau(raw_output, end_time):
            _NGOAI_TAM.add(container_name)
        logger.info("Container %s không có log từ %s đến %s", container_name, start_time, end_time)
        return []
    raw_output = trong_cua_so

    return _parse_and_filter(raw_output, container_name, max_lines)


#: Container mà mọi dòng đọc được đều MỚI HƠN cửa sổ đang hỏi — tức cửa sổ đã
#: trôi khỏi tầm log còn giữ. Giữ ở module level để `thu_thap_co_ly_do()` phân
#: biệt được "không có dòng lỗi nào" với "không còn gì để đọc", mà không phải
#: đổi kiểu trả về của `collect_container_logs()` — vốn là API Agent đang dùng.
_NGOAI_TAM: set[str] = set()


#: Vì sao danh sách rỗng. Chuỗi rỗng nghĩa là KHÔNG rỗng — có log.
#:
#: Bốn trạng thái này khác nhau về bản chất và cần nói ra khác nhau, nhất là ở
#: war room: "chưa thấy dòng lỗi nào" là BẰNG CHỨNG, còn "máy này không có
#: Docker" là Agent đang mù. Gộp cả hai thành một dòng "không có log" là ném đi
#: thông tin mà cả hệ thống đã trả tiền để lấy.
LY_DO_KHONG_DOCKER = "khong-co-docker"
LY_DO_KHONG_CONTAINER = "khong-co-container"
LY_DO_LOG_SACH = "log-sach"
#: Cửa sổ sự cố đã trôi khỏi phần log container còn giữ. Cũng KHÔNG phải
#: `log-sach`: sự cố tháng trước mà báo "service không ghi lỗi nào" là bịa.
LY_DO_NGOAI_TAM = "ngoai-tam-log"


@dataclass(frozen=True)
class KetQuaThuThap:
    """Log thu được, kèm lý do khi không thu được gì."""

    logs: list[LogEvidence]
    ly_do: str = ""


def _ten_container_co_the(service: str) -> list[str]:
    """Các tên container Docker Compose có thể đặt cho một service."""
    return [
        service,
        f"p035-demo-{service}-1",
        f"p035-demo_{service}_1",
        f"p-035-{service}-1",
        f"demo-{service}-1",
        f"{service}-1",
    ]


def thu_thap_co_ly_do(
    service: str,
    start_time: str,
    end_time: str,
    *,
    max_lines: int = MAX_LOG_LINES,
) -> KetQuaThuThap:
    """Như `collect_logs_for_service()` nhưng nói luôn VÌ SAO khi không có gì.

    Tách ra để war room hiển thị được đúng câu: người trực mở phiếu thấy khung
    log trống cần biết ngay là "service này không ghi dòng lỗi nào" hay "trang
    đang chạy ở chỗ không với tới được container" — hai chuyện dẫn tới hai hành
    động hoàn toàn khác nhau.

    `max_lines` nới được vì trần mặc định 50 sinh ra để **tiết kiệm token LLM**,
    mà người đọc war room thì không tốn token nào. Trần thấp ở đó còn nguy hiểm:
    một cửa sổ đầy `pool_in_use=` có thể đẩy traceback ra khỏi 50 dòng đầu.
    """
    candidates = _ten_container_co_the(service)
    _NGOAI_TAM.difference_update(candidates)

    for name in candidates:
        evidence = collect_container_logs(name, start_time, end_time, max_lines=max_lines)
        if evidence:
            return KetQuaThuThap(evidence)

    if _NGOAI_TAM.intersection(candidates):
        logger.info(
            "Cửa sổ %s → %s của %s đã trôi khỏi phần log container còn giữ.",
            start_time, end_time, service,
        )
        return KetQuaThuThap([], LY_DO_NGOAI_TAM)

    # Không có Docker CLI thì mọi `docker logs` ở trên đã nuốt `FileNotFoundError`
    # và trả rỗng — không phân biệt được với "log sạch" nếu chỉ nhìn kết quả.
    # Đây là đường chạy THƯỜNG XUYÊN, không phải ngoại lệ hiếm: bản API deploy
    # trên Render không có Docker và không thấy container demo nào.
    if shutil.which("docker") is None:
        logger.info("Không có Docker CLI trên máy này — không thu thập được log của %s", service)
        return KetQuaThuThap([], LY_DO_KHONG_DOCKER)

    # Phân biệt hai chuyện KHÁC NHAU về bản chất, trước đây bị gộp thành một
    # thông báo duy nhất:
    #
    #   (a) không tìm được container nào  → Agent đang mù, chưa biết gì
    #   (b) container có thật, log có thật, nhưng KHÔNG có dòng nào đáng chú ý
    #       → "log sạch", và đây là BẰNG CHỨNG, không phải thiếu bằng chứng.
    #
    # Đo ngày 11/08 trên service-dat-hang: log cũ báo "Không tìm thấy log cho
    # service service-dat-hang (đã thử: [...])" kèm danh sách tên container,
    # trong khi `p035-demo-service-dat-hang-1` NẰM NGAY trong danh sách đó và có
    # 492 dòng log — chỉ là 0 dòng ERROR/WARNING. Thông báo quy oan cho việc đặt
    # tên container và làm người đọc đi sửa đúng chỗ không hỏng.
    #
    # Khác biệt này còn quan trọng với chuỗi ba cửa chặn: log sạch là bằng chứng
    # CHỐNG LẠI giả thuyết lỗi ứng dụng.
    co_that = _container_dang_chay(candidates)
    if co_that:
        logger.info(
            "Log của %s sạch — container %s có log nhưng không có dòng nào đáng chú ý "
            "trong khoảng %s → %s",
            service,
            ", ".join(co_that),
            start_time,
            end_time,
        )
        return KetQuaThuThap([], LY_DO_LOG_SACH)

    logger.info("Không tìm thấy container nào cho service %s (đã thử: %s)", service, candidates)
    return KetQuaThuThap([], LY_DO_KHONG_CONTAINER)


def collect_logs_for_service(
    service: str,
    start_time: str,
    end_time: str,
) -> list[LogEvidence]:
    """Thu thập log cho một service — thử nhiều tên container phổ biến.

    Docker Compose đặt tên container theo format ``<project>-<service>-1``
    hoặc ``<service>``. Hàm này thử tất cả các mẫu phổ biến.

    Chỉ trả danh sách; cần biết VÌ SAO rỗng thì dùng `thu_thap_co_ly_do()`.
    """
    return thu_thap_co_ly_do(service, start_time, end_time).logs


def _container_dang_chay(candidates: list[str]) -> list[str]:
    """Trong các tên đã thử, tên nào là container đang chạy thật.

    Chỉ dùng để ghi log cho đúng, nên mọi lỗi đều nuốt: không biết được container
    nào đang chạy thì tệ nhất là thông báo kém chính xác, không đáng làm sập việc
    thu thập log.
    """
    try:
        out = subprocess.run(  # noqa: S603
            ["docker", "ps", "--format", "{{.Names}}"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return []
    if out.returncode != 0:
        return []
    dang_chay = set(out.stdout.split())
    return [name for name in candidates if name in dang_chay]


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
