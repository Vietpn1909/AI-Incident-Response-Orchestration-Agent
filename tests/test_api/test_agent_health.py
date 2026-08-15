"""Test cho `/api/v1/agent/health` — endpoint người ngoài dùng để nhìn vào Agent.

Hai test dưới đây đều sinh ra từ cùng một loại lỗi: **một bản sao cắm cứng lệch
khỏi bản gốc mà không có gì báo**.
"""

from __future__ import annotations


def test_node_chain_khop_voi_graph_that():
    """Danh sách node khai trong endpoint phải khớp graph THẬT.

    `_NODE_CHAIN` cố ý cắm cứng — dựng graph cần cả `PrometheusClient` lẫn
    `JiraClient`, mà một endpoint kiểm tra sức khoẻ không nên mở kết nối chỉ để
    đếm node. Lý do đó đúng, nhưng bản sao cắm cứng thì lệch âm thầm.

    Đo ngày 15/08 trên bản deploy Render: endpoint báo **6 node**, trong khi graph
    đã có **8** — thiếu đúng `analyze_logs` và `link_incidents`, tức hai node làm
    nên phần chẩn đoán bằng log. Ai đọc endpoint để biết Agent làm được gì sẽ hiểu
    thiếu mất năng lực chính của nó.

    Test này giữ bản sao khớp bản gốc mà vẫn không bắt endpoint mở kết nối lúc
    chạy thật.
    """
    from src.agents.incident_graph import build_incident_graph
    from src.api.routes import _NODE_CHAIN
    from src.services.jira import FakeJiraClient
    from src.services.prometheus import PrometheusClient

    # Cổng 1 không ai lắng nghe: dựng graph không gọi mạng, chỉ cần object client.
    with PrometheusClient("http://127.0.0.1:1") as prom:
        graph = build_incident_graph(prom, FakeJiraClient(verbose=False))

    that = {n for n in graph.get_graph().nodes if n not in ("__start__", "__end__")}
    assert set(_NODE_CHAIN) == that, (
        f"_NODE_CHAIN lệch graph. Thiếu: {that - set(_NODE_CHAIN)} · "
        f"Thừa: {set(_NODE_CHAIN) - that}"
    )


def test_ready_khong_phu_thuoc_prometheus():
    """Bản deploy không chạy vòng quét nên không cần với tới Prometheus.

    Đo ngày 15/08: Render báo `ready: false` chỉ vì `PROMETHEUS_URL` trỏ
    `localhost:9090` — một địa chỉ mà Render **không thể** với tới theo đúng
    thiết kế, vì Prometheus chạy trên máy của người demo.

    Bản trên Render chỉ phục vụ API cho war room, đọc dữ liệu từ Jira; vòng quét
    nằm ở `scripts/run_agent.py`. Đòi Prometheus mới "sẵn sàng" là đặt sai điều
    kiện, và ai mở link deploy sẽ tưởng hệ thống hỏng.
    """
    import inspect

    from src.api import routes

    nguon = inspect.getsource(routes.agent_health)
    dong_ready = [d for d in nguon.splitlines() if '"ready"' in d]
    assert dong_ready, "không tìm thấy khoá ready trong agent_health()"
    assert "reachable" not in dong_ready[0], (
        "`ready` không được phụ thuộc Prometheus — bản deploy không chạy detect"
    )
