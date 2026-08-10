import logging
import pathlib
import sys
from datetime import UTC, datetime
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.config import force_utf8_console
from src.agents.nodes.analyze_logs import analyze_logs
from src.models.incident import Hypothesis, IncidentSignal, LogEvidence, Severity
from langchain_core.messages import AIMessage, ToolCall, ToolMessage
from unittest.mock import MagicMock

logging.basicConfig(level=logging.INFO, format="%(message)s")

def get_mock_llm(scenario: str):
    mock_llm = MagicMock()
    
    if scenario == "OOM":
        tool_call = ToolCall(name="LogSearchTool", args={"start_time": "2026-08-10T10:03:00Z", "end_time": "2026-08-10T10:07:00Z"}, id="call_oom")
        reply_1 = AIMessage(content="", tool_calls=[tool_call])
        reply_2 = AIMessage(content="Metric cho thấy RAM tăng vọt, và Log xác nhận bằng dòng lỗi `java.lang.OutOfMemoryError: Java heap space`. Điều này chứng tỏ ứng dụng đã cạn kiệt bộ nhớ hoàn toàn.")
        mock_llm.bind_tools.return_value.invoke.side_effect = [reply_1, reply_2]
        
    elif scenario == "Lateral Movement":
        tool_call = ToolCall(name="LogSearchTool", args={"start_time": "2026-08-10T10:03:00Z", "end_time": "2026-08-10T10:07:00Z"}, id="call_lateral")
        reply_1 = AIMessage(content="", tool_calls=[tool_call])
        reply_2 = AIMessage(content="Mặc dù log HTTP request báo 200 OK, nhưng log ứng dụng chỉ ra lỗi 'JWT signature validation failed from internal IP 10.0.1.5'. Kết hợp với việc lượng IP nội bộ tăng bất thường, đây là dấu hiệu rõ ràng của một cuộc tấn công Lateral Movement (dùng token giả từ bên trong).")
        mock_llm.bind_tools.return_value.invoke.side_effect = [reply_1, reply_2]
        
    return mock_llm


def test_oom():
    print("\n" + "="*50)
    print("--- Demo Workflow: LLM phát hiện OOM ---")
    print("="*50)
    signal = IncidentSignal(
        affected_service="service-thanh-toan",
        severity=Severity.P1,
        detected_at=datetime(2026, 8, 10, 10, 5, 0, tzinfo=UTC),
        metric_name="container_memory_usage_bytes",
        metric_value=2e9,
        threshold=1e9,
        breached_for_seconds=30.0,
    )
    hypothesis = Hypothesis(
        statement="Container bị crash do Out Of Memory", 
        confidence=0.85, 
        reasoning="Metric RAM tăng vọt."
    )
    
    mock_logs = [
        LogEvidence(
            source="service-thanh-toan", 
            level="INFO", 
            message="Processing batch 105", 
            timestamp="2026-08-10T10:04:10Z", 
            pattern=""
        ),
        LogEvidence(
            source="service-thanh-toan", 
            level="ERROR", 
            message="java.lang.OutOfMemoryError: Java heap space", 
            timestamp="2026-08-10T10:04:30Z", 
            pattern="java.lang.OutOfMemoryError"
        )
    ]
    
    with patch("src.agents.nodes.analyze_logs.collect_logs_for_service", return_value=mock_logs):
        mock_llm = get_mock_llm("OOM")
        result = analyze_logs(signal, hypothesis, llm=mock_llm)
        print("\n[KẾT QUẢ LLM - OOM]")
        print("Lý giải cuối cùng:\n", result.hypothesis.reasoning)


def test_lateral_movement():
    print("\n" + "="*50)
    print("--- Demo Workflow: LLM phát hiện Lateral Movement ---")
    print("="*50)
    signal = IncidentSignal(
        affected_service="service-thanh-toan",
        severity=Severity.P2,
        detected_at=datetime(2026, 8, 10, 10, 5, 0, tzinfo=UTC),
        metric_name="auth_failure_unique_source_ips_1m",
        metric_value=50.0,
        threshold=5.0,
        breached_for_seconds=60.0,
    )
    hypothesis = Hypothesis(
        statement="Nghi ngờ tấn công dò quét / Lateral Movement", 
        confidence=0.8, 
        reasoning="Phát hiện nhiều IP nội bộ gọi auth fail liên tục."
    )
    
    mock_logs = [
        LogEvidence(
            source="service-thanh-toan", 
            level="INFO", 
            message="HTTP 200 OK /internal/metrics", 
            timestamp="2026-08-10T10:03:50Z", 
            pattern=""
        ),
        LogEvidence(
            source="service-thanh-toan", 
            level="ERROR", 
            message="JWT signature validation failed for token from internal IP 10.0.1.5", 
            timestamp="2026-08-10T10:04:00Z", 
            pattern=""
        )
    ]
    
    with patch("src.agents.nodes.analyze_logs.collect_logs_for_service", return_value=mock_logs):
        mock_llm = get_mock_llm("Lateral Movement")
        result = analyze_logs(signal, hypothesis, llm=mock_llm)
        print("\n[KẾT QUẢ LLM - Lateral Movement]")
        print("Lý giải cuối cùng:\n", result.hypothesis.reasoning)


if __name__ == "__main__":
    force_utf8_console()
    from dotenv import load_dotenv
    load_dotenv()
    test_oom()
    test_lateral_movement()
