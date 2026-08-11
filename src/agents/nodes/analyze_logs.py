"""Node ``analyze_logs`` — thu thập và phân tích log khi có sự cố.

CHỦ SỞ HỮU: (Tính năng mới — Log Analysis)

Node này nằm **sau** ``hypothesize`` và **trước** ``propose_remediation`` trong
LangGraph flow. Nó bổ sung bằng chứng từ log vào giả thuyết đã có bằng
cách cho phép Agent sử dụng tool truy vấn log (ReAct loop).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from src.agents.nodes.hypothesize import _LUAT_CUNG_CHIU
from src.models.incident import Hypothesis, IncidentSignal, LogEvidence
from src.services import rules
from src.services.log_collector import collect_logs_for_service

logger = logging.getLogger(__name__)

#: Số dòng log tối đa gửi cho LLM phân tích. Giữ thấp để kiểm soát chi phí
#: token. Ưu tiên dòng có pattern match trước, rồi ERROR, rồi WARNING.
MAX_LOGS_FOR_LLM = 50


@dataclass(frozen=True)
class LogAnalysisResult:
    """Kết quả phân tích log — bổ sung vào giả thuyết đã có."""

    hypothesis: Hypothesis
    logs_collected: int
    logs_relevant: int


def _prioritize_logs(logs: list[LogEvidence]) -> list[LogEvidence]:
    """Sắp xếp log theo mức ưu tiên: pattern match → ERROR → WARNING."""

    def priority(log: LogEvidence) -> tuple[int, str]:
        if log.pattern:
            return (0, log.timestamp)
        if log.level == "ERROR":
            return (1, log.timestamp)
        if log.level == "WARNING":
            return (2, log.timestamp)
        return (3, log.timestamp)

    return sorted(logs, key=priority)


def analyze_logs(
    signal: IncidentSignal,
    hypothesis: Hypothesis,
    llm=None,
) -> LogAnalysisResult:
    """Agent Tool Calling: cho phép LLM chủ động tìm kiếm log.

    Args:
        signal: Tín hiệu sự cố.
        hypothesis: Giả thuyết đã dựng từ node ``hypothesize``.
        llm: Client LLM (optional). Nếu không, dùng mặc định.
    """
    if llm is None:
        from src.services.llm import get_llm

        llm = get_llm()

    service = signal.affected_service
    collected_logs: list[LogEvidence] = []
    total_logs_found = 0

    @tool
    # noqa N802: tên hàm này CHÍNH LÀ tên công cụ mà LLM nhìn thấy trong prompt
    # (LangChain lấy `__name__` làm tool name). Đổi sang snake_case là đổi thứ
    # LLM đọc — quyết định đó thuộc về Việt, không sửa kèm lúc dọn lint.
    def LogSearchTool(start_time: str, end_time: str) -> str:  # noqa: N802
        """Truy vấn hệ thống Log để lấy log của service đang gặp sự cố.

        Args:
            start_time: Thời gian bắt đầu (ISO 8601, ví dụ: 2026-08-10T10:03:00Z).
            end_time: Thời gian kết thúc (ISO 8601, ví dụ: 2026-08-10T10:07:00Z).
        """
        nonlocal collected_logs, total_logs_found

        logger.info("Agent gọi LogSearchTool(%s, %s)", start_time, end_time)
        all_logs = collect_logs_for_service(service, start_time, end_time)

        total_logs_found += len(all_logs)
        if not all_logs:
            return "Không có log nào được tìm thấy trong khoảng thời gian này."

        prioritized = _prioritize_logs(all_logs)
        relevant = prioritized[:MAX_LOGS_FOR_LLM]

        # Lưu vào scope bên ngoài để trả về trong Hypothesis
        collected_logs.extend(relevant)

        log_lines = "\n".join(
            f"[{log.level}] {log.timestamp} {log.message}"
            for log in relevant
        )
        return f"Tìm thấy {len(all_logs)} dòng log. Trả về {len(relevant)} dòng đáng chú ý nhất:\n{log_lines}"

    llm_with_tools = llm.bind_tools([LogSearchTool])

    system_prompt = """\
Bạn là kỹ sư on-call đang bổ sung phần lý giải cho một chẩn đoán sự cố.
Bạn CÓ THỂ sử dụng LogSearchTool để tìm kiếm log của service trong khoảng thời gian sự cố.

NHIỆM VỤ CUỐI CÙNG (Sau khi đã có thông tin hoặc quyết định không cần log):
Viết lại phần LÝ GIẢI, kết hợp cả bằng chứng metric VÀ log (nếu có).
- CHỈ dùng thông tin đo được và thông tin có trong log, KHÔNG bịa thêm.
- Nếu log xác nhận giả thuyết metric → nói rõ log xác nhận.
- Nếu log cho thấy chi tiết mới (stack trace, error message) → bổ sung.
- Nếu tool không tìm thấy log, hãy giữ nguyên lý giải từ metric.
- Tối đa 4 câu. Viết tiếng Việt.

QUY TẮC VỀ KẾT LUẬN:
- Metric ĐÃ nêu được nguyên nhân → GIỮ NGUYÊN kết luận đó, log chỉ bổ sung ngữ cảnh.
- Metric CHƯA nêu được nguyên nhân (ghi "chưa đủ bằng chứng") → nếu log chỉ ra
  nguyên nhân thì được nêu, nhưng phải thêm một dòng riêng:

  KẾT LUẬN TỪ LOG: <một câu, nêu nguyên nhân gốc, trích tên lỗi/cột/bảng có
  thật trong log>

  Không có dòng đó thì kết luận cũ được giữ."""

    user_prompt = f"""\
SỰ CỐ
- Service: {service}
- Thời điểm phát hiện: {signal.detected_at.isoformat()}
- Mức độ: {signal.severity.value}
- LÝ GIẢI TỪ METRIC HIỆN TẠI:
{hypothesis.reasoning or "(chưa có lý giải)"}

GỢI Ý TRUY VẤN:
Hãy truy vấn log từ khoảng 2 phút trước đến 2 phút sau thời điểm phát hiện sự cố để có cái nhìn toàn cảnh."""

    messages: list = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    # Tool calling loop (max 3 iterations)
    for step in range(3):
        try:
            reply = llm_with_tools.invoke(messages)
            messages.append(reply)

            # Thoát vòng lặp nếu LLM không gọi tool nào nữa
            if not getattr(reply, "tool_calls", None):
                break

            for tool_call in reply.tool_calls:
                if tool_call["name"] == "LogSearchTool":
                    try:
                        tool_result = LogSearchTool.invoke(tool_call["args"])
                    except Exception as e:
                        tool_result = f"Lỗi khi gọi tool: {e}"
                    messages.append(ToolMessage(content=tool_result, tool_call_id=tool_call["id"]))
        except Exception as error:
            logger.warning("Vòng lặp tool calling gặp lỗi (%s)", error)
            break

    # Trích xuất kết luận cuối cùng
    final_reasoning = ""
    if messages and hasattr(messages[-1], "content") and not isinstance(messages[-1], ToolMessage):
        final_reasoning = messages[-1].content

    thay_doi: dict = {"log_evidence": collected_logs}
    if final_reasoning:
        cau_tu_log, ly_giai = _tach_ket_luan_tu_log(final_reasoning)
        thay_doi["reasoning"] = ly_giai[:1200]

        # ⚠️ Phải hỏi LUẬT có chịu hay không, KHÔNG đọc `hypothesis.statement`.
        #
        # Tới đây `statement` có thể đã là câu LLM viết ở node `hypothesize` — nó
        # thay câu "chưa đủ bằng chứng" của luật rồi. Đo ngày 11/08: kiểm câu
        # hiện tại thì cửa dưới luôn từ chối, và UC-4 không bao giờ chữa được.
        #
        # `build_hypothesis` tất định nên gọi lại rẻ. Truyền `deploy=None` vì cụm
        # "chưa đủ bằng chứng" nằm ở nhánh mặc định, không phụ thuộc deploy.
        cau_cua_luat = rules.build_hypothesis(signal, None).statement
        cau_moi = _ket_luan_tu_log_co_duoc_nhan(
            cau_tu_log, cau_cua_luat, signal, collected_logs
        )
        if cau_moi:
            logger.info(
                "%s: log nêu được nguyên nhân mà metric không nêu được — nhận kết luận mới: %s",
                service, cau_moi,
            )
            thay_doi["statement"] = cau_moi[:400]
            thay_doi["confidence"] = _tin_cay_sau_khi_log_nen_duoc(hypothesis.confidence)

    updated = hypothesis.model_copy(update=thay_doi)

    return LogAnalysisResult(
        hypothesis=updated,
        logs_collected=total_logs_found,
        logs_relevant=len(collected_logs),
    )

#: Nhãn LLM phải dùng khi muốn nêu nguyên nhân dựa trên log.
_NHAN_KET_LUAN_LOG = "KẾT LUẬN TỪ LOG:"

#: Điểm tin cậy cộng thêm khi kết luận được một dòng log thật chống lưng.
#:
#: Đặt bằng 0.40 để khớp bảng điểm trong `rules._diem_tin_cay()`, nơi mọi bằng
#: chứng **nguyên nhân gốc** đều đáng 0.40 ("pool cạn ≥ 95%", "đỉnh bộ nhớ chạm
#: ≥ 90% trần", "đăng nhập hỏng ≥ ngưỡng P1"). Một dòng traceback nêu đúng tên
#: cột thiếu là bằng chứng nguyên nhân gốc theo đúng nghĩa đó — nó không xác nhận
#: "có bất thường", nó nói ra bất thường LÀ GÌ.
#:
#: Vì sao phải cộng: bảng điểm của `rules` chỉ biết `MetricEvidence`, nên UC-4
#: (chỉ có mỗi tín hiệu 5xx, đáng 0.10) luôn ra tin cậy rất thấp. Đo ngày 11/08
#: trên KAN-17/KAN-18: log nêu đúng `UndefinedColumnError` ở cột
#: `idempotency_key` và đúng cơ chế lan truyền sang service-dat-hang, nhưng cả
#: hai câu đều đeo nhãn "tin cậy 30%" và "10%" thừa hưởng từ giả thuyết cũ.
#: Người trực đọc war room sẽ gạt đi đúng câu đáng tin nhất — nhãn sai còn hại
#: hơn không có nhãn.
#:
#: Chỉ cộng khi câu mới đã qua `_ket_luan_tu_log_co_duoc_nhan()`, tức đã bắt buộc
#: trích được một chuỗi có thật trong log. Không có cửa đó thì đây thành chỗ để
#: LLM tự nâng điểm cho mình.
DIEM_LOG_CHONG_LUNG = 0.40


def _tin_cay_sau_khi_log_nen_duoc(cu: float) -> float:
    """Tin cậy mới khi một dòng log thật đã chống lưng cho kết luận.

    Cộng dồn rồi chặn ở 1.0, đúng cách `rules._diem_tin_cay()` làm — chứ không
    gán cứng một con số, vì gán cứng là ném đi phần điểm mà metric đã đóng góp.
    """
    return min(1.0, cu + DIEM_LOG_CHONG_LUNG)


def _tach_ket_luan_tu_log(reply: str) -> tuple[str, str]:
    """Tách `(câu kết luận từ log, phần lý giải)` khỏi câu trả lời của LLM.

    Không có nhãn thì trả `("", toàn bộ)` — tức LLM không đề nghị đổi kết luận.
    """
    cau, dong_ly_giai = "", []
    for dong in reply.splitlines():
        sach = dong.strip()
        if sach.upper().startswith(_NHAN_KET_LUAN_LOG):
            cau = sach.split(":", 1)[1].strip()
        elif sach:
            dong_ly_giai.append(sach)
    return cau, " ".join(dong_ly_giai)


def _ket_luan_tu_log_co_duoc_nhan(
    cau_tu_log: str,
    cau_hien_tai: str,
    signal: IncidentSignal,
    logs: list[LogEvidence],
) -> str | None:
    """Câu kết luận dựa trên log có được phép ghi đè câu hiện tại không?

    Trả câu mới nếu được, `None` nếu không.

    ## Vì sao cần cửa này, và vì sao nó HẸP

    Bản đầu của node (11/08) cố ý **không bao giờ** sửa `statement` — prompt ghi
    rõ *"giữ nguyên kết luận từ metric, log chỉ BỔ SUNG ngữ cảnh"*. Ranh giới đó
    đúng cho UC-1/2/3: metric đã nêu được nguyên nhân, log không nên lật lại.

    Nhưng nó làm UC-4 bất khả thi. Đo ngày 11/08 trên sự cố thiếu migration:
    metric chỉ thấy `lỗi 5xx = 100%`, `p95 = 0,049s` (THẤP hơn nền 0,089s),
    `pool = 0%` — luật rơi đúng nhánh *"chưa đủ bằng chứng để nêu nguyên nhân
    gốc"*, và log là nguồn DUY NHẤT nói được `UndefinedColumnError: column
    "idempotency_key"`. Cấm sửa `statement` thì log không bao giờ chữa được một
    chẩn đoán còn trống.

    Nên cửa này chỉ mở đúng một trường hợp: **luật đã chịu**. Luật có kết luận
    thì log vẫn không được lật — giữ nguyên ranh giới ban đầu.

    Và câu mới phải **trích được một chuỗi có thật trong log**. Không có thì bỏ:
    đó là cùng nguyên tắc với `hypothesize._nguyen_nhan_khong_co_can_cu()` —
    nêu nguyên nhân nào thì phải có bằng chứng chống lưng cho nguyên nhân đó.
    """
    if not cau_tu_log:
        return None

    # Luật đã nêu được nguyên nhân → không cho log lật lại.
    if _LUAT_CUNG_CHIU not in cau_hien_tai.lower():
        logger.info(
            "%s: bỏ kết luận từ log vì metric đã nêu được nguyên nhân. Câu bị bỏ: %s",
            signal.affected_service, cau_tu_log,
        )
        return None

    # Câu mới phải trích được một token có thật trong log — chống bịa.
    noi_dung_log = " ".join(e.message for e in logs).lower()
    tokens = [t.strip('\'"`.,;:()[]') for t in cau_tu_log.split()]
    co_can_cu = any(len(t) >= 8 and t.lower() in noi_dung_log for t in tokens)
    if not co_can_cu:
        logger.warning(
            "%s: BỎ kết luận từ log vì không trích được chuỗi nào có thật trong log. "
            "Câu bị bỏ: %s",
            signal.affected_service, cau_tu_log,
        )
        return None

    return cau_tu_log
