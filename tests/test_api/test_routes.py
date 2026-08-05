"""Test endpoint trạng thái.

Hai test cũ nghiệm thu `POST /api/v1/chat` và `GET /api/v1/status` của template.
Cả hai endpoint đã bị gỡ ngày 05/08 — xem docstring `src/api/routes.py`: chúng
nằm trên Live URL nhóm nộp làm deliverable, và endpoint chat chỉ **lặp lại câu
đầu vào**, làm người mở URL kết luận Agent của nhóm là một con echo.

Test mới nghiệm thu thứ thay chúng: `GET /api/v1/agent/health` phải trả trạng
thái **đo được**, không phải chuỗi gán cứng.
"""

import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_endpoint_chat_cua_template_da_bi_go(client):
    """Không còn đường nào trả lời như một chatbot.

    Chốt bằng test vì đây là thứ dễ bị thêm lại: template có sẵn
    `ChatRequest`/`ChatResponse` trong `src/models/schemas.py` nên viết lại
    endpoint chat chỉ mất 5 dòng. Mà thêm lại là URL công khai lại nói sai về
    sản phẩm.
    """
    response = await client.post("/api/v1/chat", json={"message": "service cham"})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_agent_health_tra_trang_thai_do_duoc(client):
    """Mỗi trường phải là kết quả một phép kiểm, không phải chuỗi gán cứng."""
    response = await client.get("/api/v1/agent/health")

    assert response.status_code == 200
    data = response.json()

    # Đủ 6 node của chuỗi ứng phó sự cố, không phải "LangGraph Agent v1.0".
    assert data["graph"]["count"] == 6
    assert data["graph"]["nodes"][0] == "detect"
    assert data["graph"]["nodes"][-1] == "escalate"

    # `conftest` đã xoá cấu hình Jira/Prometheus trong test → phải báo chưa sẵn
    # sàng. Chỗ này vẫn `ready: True` nghĩa là nó không kiểm gì cả.
    assert data["ready"] is False
    assert data["jira"]["configured"] is False
    assert data["prometheus"]["configured"] is False

    # Ràng buộc bắt buộc của đề bài phải nói ra được qua API.
    assert data["human_approval_required"] is True


@pytest.mark.asyncio
async def test_agent_health_tra_200_du_co_thanh_phan_hong(client):
    """Endpoint chẩn đoán phải nói ra cái gì hỏng, không chỉ trả 503.

    Trả 503 thì người gọi biết "có gì đó sai" mà không biết sai ở đâu — đúng
    tình huống không muốn gặp giữa buổi demo.
    """
    response = await client.get("/api/v1/agent/health")

    assert response.status_code == 200
    assert response.json()["ready"] is False
