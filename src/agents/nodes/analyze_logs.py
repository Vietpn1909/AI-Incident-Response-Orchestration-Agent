"""Node ``analyze_logs`` — thu thập và phân tích log khi có sự cố.

CHỦ SỞ HỮU: (Tính năng mới — Log Analysis)

Node này nằm **sau** ``hypothesize`` và **trước** ``propose_remediation`` trong
LangGraph flow. Nó bổ sung bằng chứng từ log vào giả thuyết đã có bằng
cách cho phép Agent sử dụng tool truy vấn log (ReAct loop).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from src.models.incident import Hypothesis, IncidentSignal, LogEvidence
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
    def LogSearchTool(start_time: str, end_time: str) -> str:
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
- Giữ nguyên kết luận từ metric, log chỉ BỔ SUNG ngữ cảnh.
- Nếu log xác nhận giả thuyết metric → nói rõ log xác nhận.
- Nếu log cho thấy chi tiết mới (stack trace, error message) → bổ sung.
- Nếu tool không tìm thấy log, hãy giữ nguyên lý giải từ metric.
- Tối đa 4 câu. Viết tiếng Việt."""

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
    if messages and hasattr(messages[-1], "content") and type(messages[-1]) != ToolMessage:
        final_reasoning = messages[-1].content
    
    if final_reasoning:
        updated = hypothesis.model_copy(
            update={
                "log_evidence": collected_logs,
                "reasoning": final_reasoning[:1200]
            }
        )
    else:
        updated = hypothesis.model_copy(
            update={"log_evidence": collected_logs}
        )

    return LogAnalysisResult(
        hypothesis=updated,
        logs_collected=total_logs_found,
        logs_relevant=len(collected_logs),
    )
