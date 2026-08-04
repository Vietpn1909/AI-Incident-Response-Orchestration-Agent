import logging
import os
import sys
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "AI20K Agent"
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:3000"

    # LLM
    #
    # Dùng thư viện `langchain-openai` cho mọi provider có endpoint tương thích
    # OpenAI — không phải nhất thiết là OpenAI. Đội đang dùng Alibaba Cloud
    # Model Studio (DashScope) vì có quota miễn phí.
    #
    # Đổi provider = đổi 3 biến trong .env, KHÔNG sửa code:
    #   Alibaba (quốc tế): LLM_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    #                      MODEL_NAME=qwen-plus
    #   Alibaba (TQ):      LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
    #   OpenAI:            để LLM_BASE_URL trống, MODEL_NAME=gpt-4o-mini
    openai_api_key: str = ""

    #: Trống = dùng endpoint mặc định của OpenAI.
    llm_base_url: str = ""

    model_name: str = "qwen-plus"

    #: Chẩn đoán cần ổn định để đo được độ chính xác trong `eval/`. Nhiệt độ cao
    #: làm cùng một bằng chứng ra kết luận khác nhau mỗi lần chạy, không đo được.
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)

    # Database — lịch sử deploy, nguồn bằng chứng cho `correlate_deploy`
    #
    # Chỗ duy nhất đọc biến này là `services/deploys.py`, để lấy bảng
    # `deploy_history` mà `demo/seed.py` sinh ra. Nó KHÔNG phải database của app.
    #
    # ⚠️ Mặc định của template là `sqlite:///./data/app.db`, mà `asyncpg` không
    # parse được URL sqlite — nên trên máy mới clone, đối chiếu deploy **không
    # bao giờ chạy** và chỉ để lại một dòng warning. Hệ quả đo được ngày 04/08:
    # giả thuyết mất bằng chứng deploy, độ tin cậy tụt từ 90% xuống 40%. Đây là
    # đúng loại "fail âm thầm" mà JOURNAL đã ghi ba lần.
    #
    # Máy nào đã có Postgres chiếm 5432 thì đổi cả `DEMO_POSTGRES_PORT` lẫn
    # cổng trong biến này — xem demo/README.md.
    database_url: str = "postgresql://demo:demo@localhost:5432/demo"

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"

    # LangSmith (AI Logs — Deliverable #4)
    langchain_api_key: str = ""
    langchain_project: str = "P-035"
    langchain_tracing_v2: bool = False

    # Prometheus — nguồn tín hiệu phát hiện sự cố (ADR-0002, không dùng Alertmanager)
    prometheus_url: str = "http://localhost:9090"

    # Jira — lớp quản lý vòng đời incident (ADR-0001)
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = "KAN"
    jira_webhook_secret: str = ""

    # accountId của account Agent. Cổng phê duyệt HITL so accountId này với
    # người đã chuyển issue sang Remediating — trùng nhau nghĩa là Agent đang
    # cố tự duyệt, và hành động bị từ chối. Xem src/services/hitl.py.
    jira_agent_account_id: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


def configure_tracing() -> bool:
    """Bật LangSmith tracing bằng cách export config sang os.environ.

    pydantic-settings chỉ nạp .env vào object Settings — nó không set biến
    môi trường. LangChain/LangGraph lại đọc thẳng từ os.environ, nên nếu
    không gọi hàm này thì trace sẽ không bao giờ được gửi lên LangSmith.

    Returns:
        True nếu tracing được bật, False nếu thiếu key hoặc bị tắt.
    """
    settings = get_settings()
    if not (settings.langchain_tracing_v2 and settings.langchain_api_key):
        return False

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    return True


def force_utf8_console() -> None:
    """Ép stdout/stderr về UTF-8.

    Console Windows mặc định dùng cp1252, không có ký tự tiếng Việt. Mọi thứ
    đội in ra đều là tiếng Việt, nên chưa ép thì chương trình **chết giữa
    chừng** với `UnicodeEncodeError` — không phải in ra chữ xấu, mà là dừng hẳn.
    3/4 thành viên dùng Windows.

    Tách riêng khỏi `configure_logging()` vì có chỗ cần ép UTF-8 **trước** khi
    dựng logging: `argparse` in `--help` và thông báo lỗi tham số thẳng ra
    stdout ngay trong `parse_args()`, tức trước cả dòng log đầu tiên.
    """
    for stream in (sys.stdout, sys.stderr):
        # `reconfigure` chỉ có ở TextIOWrapper — khi stdout bị thay bằng thứ
        # khác (pytest capture chẳng hạn) thì bỏ qua, không phải lỗi.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def configure_logging() -> None:
    """Dựng logging cho toàn app, và ép console về UTF-8.

    Hai việc, cùng một lý do là log phải đọc được:

    1. **Ép UTF-8 cho stdout/stderr.** Console Windows mặc định dùng cp1252,
       không có ký tự tiếng Việt. Log của đội viết bằng tiếng Việt nên nó ra
       thành `Kh�ng g\\u1ecdi \\u0111\\u01b0\\u1ee3c...` — đọc không nổi, mà 2
       trong 4 thành viên đang làm trên Windows. `logging` ghi vào **stderr**,
       nên chỉ chỉnh stdout là không đủ.

    2. **Gắn handler cho root logger.** Chưa gọi `basicConfig` thì Python dùng
       handler "cứu hộ" chỉ in từ mức WARNING trở lên và không có timestamp,
       nên `logger.info` của `webhooks.py` hay `prometheus.py` biến mất không
       dấu vết.

    Gọi một lần lúc khởi động app. Script chạy tay (`spike/`, `demo/`) tự ép
    UTF-8 của riêng nó vì không đi qua `main.py`.
    """
    force_utf8_console()

    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        # uvicorn đã gắn handler trước khi lifespan chạy; không có force thì
        # basicConfig lặng lẽ không làm gì và mọi cấu hình trên bị bỏ qua.
        force=True,
    )

    # `httpx` log một dòng INFO cho MỖI request. Agent poll Prometheus vài giây
    # một lần, nên để nguyên thì log của đội bị chôn dưới hàng nghìn dòng
    # "HTTP Request: GET ... 200 OK". Lỗi thật vẫn hiện vì WARNING trở lên
    # không bị chặn.
    logging.getLogger("httpx").setLevel(logging.WARNING)
