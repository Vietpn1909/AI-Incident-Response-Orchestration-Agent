"""Fixture dùng chung, và một hàng rào chặn test gọi ra dịch vụ thật.

## Vì sao có `khong_goi_dich_vu_that`

Từ 05/08 `src/api/incidents.py` đọc Jira thật khi đã cấu hình đủ và rơi về
fixture khi chưa. Đúng cho lúc chạy thật, nhưng làm **kết quả test phụ thuộc vào
máy đang chạy**:

- CI không có `.env` → dùng fixture → xanh
- Máy đã setup Jira → `RealJiraClient` đi hỏi Jira thật về `INC-12`, mà key thật
  là `KAN-*` → 404 → **đỏ**

Ba test trong `test_api/test_incidents.py` đã đỏ đúng như vậy trên máy Đức sau
khi merge PR #16, dù CI của PR đó xanh. Chúng không sai — chúng đang nghiệm thu
một thứ khác với thứ tên nó nói.

Nguy hiểm hơn chuyện xanh đỏ theo máy: **unit test gọi Jira thật qua mạng**.
Chậm, phụ thuộc token, đếm vào rate limit, và nếu sau này ai thêm một test gọi
hàm ghi thì nó sửa dữ liệu thật.

Nên fixture dưới đây xoá cấu hình Jira/Postgres/Prometheus khỏi **mọi** test, tự
động. Test nào cần dịch vụ thật thì tự dựng client tường minh, chứ không nhờ
`.env` của người đang chạy.
"""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.config import get_settings
from src.main import app

#: Còn giá trị là còn một đường đi ra ngoài mạng từ trong test.
_BIEN_GOI_RA_NGOAI = (
    "JIRA_BASE_URL",
    "JIRA_EMAIL",
    "JIRA_API_TOKEN",
    "JIRA_PROJECT_KEY",
    "JIRA_AGENT_ACCOUNT_ID",
    "JIRA_WEBHOOK_SECRET",
    "DATABASE_URL",
    "PROMETHEUS_URL",
    # Đường ra mạng mới từ 12/08: `build_room_client()` đọc biến này rồi đi gọi
    # api.daily.co. Máy nào đã có key trong .env mà không chặn thì test tạo
    # phòng họp THẬT — và đốt dần hạn mức 5 phòng đồng thời của bản free.
    "DAILY_API_KEY",
    # Cùng ngày: `build_alerter()` đọc ba biến này rồi đi gọi smtp.gmail.com.
    # Đây là đường ra nguy hiểm nhất trong danh sách — Daily chỉ tốn hạn mức,
    # còn mail thì bay thẳng vào hộp thư người thật và không lấy lại được.
    "SMTP_EMAIL",
    "SMTP_APP_PASSWORD",
    "INCIDENT_ALERT_RECIPIENTS",
    "POSTMORTEM_RECIPIENTS",
    # Đường ra cũ nhất mà danh sách này bỏ sót. `hypothesize` gọi LLM thật qua
    # DashScope, nên MỌI test chạy graph với tín hiệu thật đều đi ra mạng.
    "OPENAI_API_KEY",
    "LLM_BASE_URL",
)


@pytest.fixture(autouse=True)
def khong_goi_dich_vu_that(monkeypatch: pytest.MonkeyPatch):
    """Chặn mọi test đi ra Jira / Postgres / Prometheus thật.

    `autouse=True` là cố ý: hàng rào nào phải nhớ bật thì sẽ có lúc quên, và lúc
    quên thì test vẫn xanh nên không ai biết.

    ⚠️ Phải `setenv("")` chứ KHÔNG phải `delenv`. `pydantic-settings` đọc thẳng
    **file** `.env`, không chỉ `os.environ` — nên xoá biến môi trường thì nó vẫn
    lấy giá trị từ file như cũ. Ghi đè bằng chuỗi rỗng mới thắng, vì env var có
    ưu tiên cao hơn file. Đã thử `delenv` trước và test vẫn đỏ.

    Xoá cache `get_settings()` cả trước lẫn sau vì nó là `lru_cache` — một
    `Settings` đã đọc `.env` ở test trước sẽ sống tiếp sang test này.
    """
    for bien in _BIEN_GOI_RA_NGOAI:
        monkeypatch.setenv(bien, "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing API endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_llm():
    """Mock LLM to avoid calling OpenAI during tests.

    Usage in test:
        def test_something(mock_llm):
            # LLM calls will return mock response instead of hitting OpenAI
            ...
    """
    mock = AsyncMock()
    mock.ainvoke.return_value = AsyncMock(content="Mocked LLM response")
    return mock
