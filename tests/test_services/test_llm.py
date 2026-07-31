"""Test cấu hình LLM.

Đội dùng Alibaba Cloud Model Studio qua endpoint tương thích OpenAI, nên test ở
đây chủ yếu kiểm `base_url` được truyền đúng — sai chỗ đó thì request đi tới
OpenAI thật và trả 401 với thông báo không liên quan gì tới Alibaba.
"""

import pytest

from src.config import Settings
from src.services import llm as llm_module


def _patch_settings(monkeypatch: pytest.MonkeyPatch, **kwargs) -> None:
    monkeypatch.setattr(llm_module, "get_settings", lambda: Settings(**kwargs))


def test_thieu_key_thi_fail_to(monkeypatch: pytest.MonkeyPatch):
    """Fail ngay lúc khởi tạo, không để LangChain báo 401 giữa lúc chẩn đoán."""
    _patch_settings(monkeypatch, openai_api_key="")

    with pytest.raises(ValueError, match="Chưa cấu hình OPENAI_API_KEY"):
        llm_module.get_llm()


def test_placeholder_cung_bi_coi_la_thieu(monkeypatch: pytest.MonkeyPatch):
    """`sk-your-key-here` là giá trị mẫu trong .env.example — không phải key thật.

    Bắt riêng trường hợp này vì nó đã tồn tại trong .env của đội suốt tuần 1 mà
    không ai phát hiện, do chưa có chỗ nào gọi LLM.
    """
    _patch_settings(monkeypatch, openai_api_key="sk-your-key-here")

    with pytest.raises(ValueError, match="placeholder"):
        llm_module.get_llm()


def test_truyen_base_url_cho_provider_tuong_thich(monkeypatch: pytest.MonkeyPatch):
    """Alibaba Cloud: phải truyền base_url, không thì request đi tới OpenAI thật."""
    base = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    _patch_settings(
        monkeypatch,
        openai_api_key="sk-fake-for-test",
        llm_base_url=base,
        model_name="qwen-plus",
    )

    client = llm_module.get_llm()

    assert str(client.openai_api_base).rstrip("/") == base
    assert client.model_name == "qwen-plus"


def test_base_url_trong_thi_dung_endpoint_mac_dinh(monkeypatch: pytest.MonkeyPatch):
    """Để trống = dùng OpenAI, không được truyền base_url rỗng vào client."""
    _patch_settings(monkeypatch, openai_api_key="sk-fake-for-test", llm_base_url="")

    client = llm_module.get_llm()

    assert not client.openai_api_base


def test_temperature_thap_de_do_duoc_do_chinh_xac(monkeypatch: pytest.MonkeyPatch):
    """Mặc định phải thấp — nhiệt độ cao làm cùng bằng chứng ra kết luận khác nhau
    mỗi lần chạy, không đo được độ chính xác chẩn đoán trong eval/."""
    assert Settings(openai_api_key="x").llm_temperature <= 0.3
