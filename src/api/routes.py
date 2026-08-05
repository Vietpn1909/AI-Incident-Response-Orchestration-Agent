"""Endpoint trạng thái của Agent ứng phó sự cố.

## Vì sao file này bị viết lại ngày 05/08

Bản của template có hai endpoint mà nhóm chưa bao giờ dùng:

- `POST /api/v1/chat` — gọi `src/agents/graph.py`, một graph mẫu 2 node **không
  gọi LLM**. Đo trên URL công khai: gửi `{"message":"test"}` thì nó trả
  `{"response":"Kết quả dựa trên phân tích: Phân tích: test"}` — tức **lặp lại
  nguyên câu đầu vào**.
- `GET /api/v1/status` — trả cứng `{"status":"ready","agent":"LangGraph Agent v1.0"}`,
  không kiểm tra gì cả.

Cả hai nằm trên Live URL mà nhóm nộp làm deliverable, và Render bật `autoDeploy`
nên mỗi lần push là deploy lại. Người mở URL thấy tên *"Chat với AI agent"*, gọi
thử thì nó nhại lại câu hỏi — rồi kết luận Agent của nhóm là một con echo, trong
khi thứ nhóm thật sự làm nằm ở [`incident_graph.py`](../agents/incident_graph.py)
mà endpoint đó **không hề dẫn tới**. Nói sai về sản phẩm còn tệ hơn không có
endpoint nào.

## Endpoint mới kiểm thứ gì

`GET /api/v1/agent/health` trả trạng thái **đo được**, không phải chuỗi cố định:
Prometheus có trả lời không, Jira đã cấu hình chưa, LLM đã cấu hình chưa, graph
có những node nào. Mỗi trường là kết quả một phép kiểm thật, nên khi nó nói "ok"
thì câu đó có nghĩa.

Cố ý **không** có endpoint nào chạy Agent theo yêu cầu HTTP. Agent chạy theo chu
kỳ qua [`scripts/run_agent.py`](../../scripts/run_agent.py); một endpoint kích
hoạt được từ ngoài sẽ thành đường thứ hai tới `open_war_room` — mở incident thật
trên Jira chỉ vì có người tò mò gọi URL.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter()

#: Node của graph ứng phó sự cố, theo thứ tự chạy.
#:
#: Khai tường minh thay vì đọc từ graph: dựng graph cần cả `PrometheusClient` lẫn
#: `JiraClient`, mà một endpoint kiểm tra sức khoẻ thì không nên mở kết nối đi đâu
#: chỉ để đếm node.
_NODE_CHAIN = (
    "detect",
    "classify_severity",
    "open_war_room",
    "hypothesize",
    "propose_remediation",
    "escalate",
)


def _kiem_prometheus(url: str) -> dict[str, Any]:
    """Prometheus có trả lời không. Hỏi đúng một câu rẻ nhất (`up`)."""
    if not url:
        return {"configured": False, "reachable": False, "detail": "chưa đặt PROMETHEUS_URL"}
    try:
        from src.services.prometheus import PrometheusClient

        with PrometheusClient(url) as client:
            client.query("up")
        return {"configured": True, "reachable": True, "url": url}
    except Exception as error:
        return {"configured": True, "reachable": False, "url": url, "detail": str(error)[:200]}


def _kiem_jira(settings: Settings) -> dict[str, Any]:
    """Jira đã cấu hình đủ chưa.

    **Không** gọi Jira API ở đây: endpoint health bị gọi liên tục, mà mỗi lần đi
    Jira là đốt rate limit của Jira Cloud. Việc gọi thật để `/api/incidents` làm,
    và nó đã trả 502 kèm lý do rõ ràng khi Jira từ chối.
    """
    du_cau_hinh = bool(settings.jira_base_url and settings.jira_email and settings.jira_api_token)
    return {
        "configured": du_cau_hinh,
        "project": settings.jira_project_key or None,
        "hitl_gate": (
            "changelog" if settings.jira_agent_account_id else "chưa đặt JIRA_AGENT_ACCOUNT_ID"
        ),
    }


@router.get("/agent/health")
async def agent_health() -> dict[str, Any]:
    """Trạng thái đo được của Agent ứng phó sự cố.

    Trả **200 kể cả khi có thành phần không nối được** — đây là endpoint để chẩn
    đoán, nên nó phải nói ra được cái gì đang hỏng. Trả 503 thì người gọi chỉ
    biết "có gì đó sai" mà không biết sai ở đâu.
    """
    settings = get_settings()
    prometheus = _kiem_prometheus(settings.prometheus_url)
    jira = _kiem_jira(settings)
    llm_da_cau_hinh = bool(
        settings.openai_api_key and settings.openai_api_key != "sk-your-key-here"
    )

    return {
        "agent": "PTNT-20 — Agent Điều Phối Ứng Phó Sự Cố",
        "ready": bool(prometheus.get("reachable")) and bool(jira.get("configured")),
        "graph": {"nodes": list(_NODE_CHAIN), "count": len(_NODE_CHAIN)},
        "prometheus": prometheus,
        "jira": jira,
        "llm": {
            "configured": llm_da_cau_hinh,
            "model": settings.model_name if llm_da_cau_hinh else None,
            "role": "chỉ diễn giải bằng chứng thành câu chẩn đoán; luật quyết định hành động",
        },
        "human_approval_required": True,
        "note": (
            "Agent chạy theo chu kỳ qua scripts/run_agent.py, không kích hoạt được qua HTTP — "
            "endpoint như vậy sẽ thành đường thứ hai mở incident thật trên Jira."
        ),
    }
