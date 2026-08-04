"""Gác cấu hình `DATABASE_URL` — nguồn bằng chứng deploy.

Biến này chỉ có [`services/deploys.py`](../../src/services/deploys.py) đọc, để
lấy bảng `deploy_history` cho `correlate_deploy`. Trỏ sai thì **không có
exception nào** — `deploys.py` bắt lỗi, log một dòng warning, và giả thuyết đi
tiếp mà thiếu hẳn phần deploy.

Đo được ngày 04/08 trên stack thật: cùng một sự cố, `DATABASE_URL` đúng thì độ
tin cậy 90% kèm `related_deploy=v1.4.2`; còn placeholder của template thì 40% và
không có deploy nào. Không có gì đỏ lên để báo, nên phải có test gác.
"""

from urllib.parse import urlparse

import pytest

from src.config import Settings

# Những giá trị từng có thật trong repo và đều làm đối chiếu deploy chết im lặng.
PLACEHOLDER_CUA_TEMPLATE = "postgresql://user:password@localhost:5432/dbname"
SQLITE_CUA_TEMPLATE = "sqlite:///./data/app.db"


def _mac_dinh_trong_code() -> str:
    """Giá trị mặc định khai trong `Settings`, KHÔNG phải giá trị đang chạy.

    Đọc `Settings().database_url` là đọc `.env` của máy đang chạy test. Trên máy
    thành viên (có `.env`) và trên CI (không có `.env`) sẽ ra hai kết quả khác
    nhau — test đó xanh đỏ theo máy chứ không theo code, vô dụng làm cổng gác.
    """
    return Settings.model_fields["database_url"].default


def test_mac_dinh_khong_phai_placeholder_cua_template():
    assert _mac_dinh_trong_code() not in (PLACEHOLDER_CUA_TEMPLATE, SQLITE_CUA_TEMPLATE)


def test_mac_dinh_la_url_postgres_asyncpg_doc_duoc():
    """`asyncpg.connect()` chỉ nhận URL postgres — sqlite thì nó ném lỗi parse."""
    parsed = urlparse(_mac_dinh_trong_code())

    assert parsed.scheme in ("postgresql", "postgres")
    assert parsed.hostname, "thiếu host"
    assert parsed.username, "thiếu user"
    assert parsed.path.strip("/"), "thiếu tên database"


@pytest.mark.parametrize("url", [PLACEHOLDER_CUA_TEMPLATE, SQLITE_CUA_TEMPLATE])
def test_dat_lai_placeholder_thi_test_nay_do(url: str):
    """Chứng minh test trên thật sự bắt được, không chỉ xanh vì trùng hợp."""
    settings = Settings(database_url=url)

    la_placeholder = settings.database_url in (PLACEHOLDER_CUA_TEMPLATE, SQLITE_CUA_TEMPLATE)
    assert la_placeholder, "giá trị này lẽ ra phải bị coi là placeholder"
