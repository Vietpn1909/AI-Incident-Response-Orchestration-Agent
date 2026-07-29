import os
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
    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    # Database
    database_url: str = "sqlite:///./data/app.db"

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"

    # LangSmith (AI Logs — Deliverable #4)
    langchain_api_key: str = ""
    langchain_project: str = "P-035"
    langchain_tracing_v2: bool = False

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
