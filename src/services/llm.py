"""Khởi tạo LLM client.

Dùng `langchain-openai` cho **mọi provider có endpoint tương thích OpenAI**, không
chỉ riêng OpenAI. Đội đang dùng Alibaba Cloud Model Studio (DashScope) vì có
quota miễn phí — chỉ cần trỏ `base_url` sang endpoint `compatible-mode` của họ.

Đổi provider là đổi biến trong `.env`, không sửa file này:

    # Alibaba Cloud Model Studio — quốc tế
    LLM_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    MODEL_NAME=qwen-plus

    # OpenAI
    LLM_BASE_URL=
    MODEL_NAME=gpt-4o-mini

LangSmith tracing hoạt động với mọi provider vì nó bám vào lớp LangChain, không
bám vào OpenAI — nên deliverable #4 không bị ảnh hưởng khi đổi.
"""

from langchain_openai import ChatOpenAI

from src.config import get_settings


def get_llm() -> ChatOpenAI:
    """LLM dùng chung cho Agent.

    Raises:
        ValueError: chưa cấu hình API key. Fail to ở đây rõ hơn là để LangChain
            báo lỗi 401 giữa lúc Agent đang chẩn đoán một incident.
    """
    settings = get_settings()

    if not settings.openai_api_key or settings.openai_api_key == "sk-your-key-here":
        raise ValueError(
            "Chưa cấu hình OPENAI_API_KEY trong .env (hiện vẫn là placeholder). "
            "Với Alibaba Cloud Model Studio thì đây là API key của DashScope, và "
            "phải đặt cả LLM_BASE_URL — xem docstring của module này."
        )

    kwargs = {
        "model": settings.model_name,
        "api_key": settings.openai_api_key,
        "temperature": settings.llm_temperature,
    }
    # Trống thì để LangChain dùng endpoint mặc định của OpenAI.
    if settings.llm_base_url:
        kwargs["base_url"] = settings.llm_base_url

    return ChatOpenAI(**kwargs)
