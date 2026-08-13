"""Test khói: hai trang Streamlit phải **import được**.

Nghe tầm thường, nhưng đây là loại lỗi đã giết trang war room hai lần, và cả hai
lần CI đều xanh:

1. **06/08** — `from ui import labels` ném `ModuleNotFoundError: No module named
   'ui'` khi chạy thật, vì `streamlit run ui/war_room.py` đặt **thư mục ui/** vào
   `sys.path` chứ không đặt gốc repo. pytest thì tự thêm rootdir nên không thấy.

2. **13/08** — bản UI mới thêm `import plotly`, khai đúng chỗ trong
   `ui/requirements.txt`, nhưng CI chỉ cài `requirements.txt` và
   `demo/requirements.txt`. Ruff không cần import giải được nên lint vẫn xanh,
   còn test thì chỉ đụng `ui/labels.py`. Trang war room **không mở nổi** mà không
   có tín hiệu nào — phát hiện ra 30 phút trước giờ demo.

Cả hai đều thuộc họ "test xanh mà chạy thật vỡ". File này đóng họ đó lại: hễ
trang UI thiếu dependency hoặc gãy import, CI đỏ ngay.

⚠️ Import ở đây **chạy toàn bộ file** `war_room.py` từ trên xuống, kể cả phần gọi
`st.*` ngoài hàm. Streamlit chấp nhận điều đó ở chế độ "bare mode" (chỉ cảnh
báo), nên test không cần dựng server. Nếu sau này ai thêm lời gọi mạng ở cấp
module thì test này sẽ chậm hoặc treo — và đó cũng là điều đáng biết.
"""

from __future__ import annotations

import importlib
import pathlib
import sys

import pytest

GOC_REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("ten_module", ["ui.war_room", "ui.status_page", "ui.labels"])
def test_trang_ui_import_duoc(ten_module: str):
    """Thiếu dependency hay gãy import là đỏ ở đây, không phải đỏ lúc demo."""
    if str(GOC_REPO) not in sys.path:
        sys.path.insert(0, str(GOC_REPO))

    module = importlib.import_module(ten_module)
    assert module is not None


def test_deps_cua_ui_deu_cai_duoc():
    """Mọi thư viện `ui/requirements.txt` khai phải thực sự import được.

    Bắt đúng khoảng cách giữa "đã khai dependency" và "môi trường đã có nó" —
    chính khoảng cách làm trang war room chết ngày 13/08.
    """
    ten_import = {"plotly": "plotly", "streamlit": "streamlit", "requests": "requests"}
    dong = (GOC_REPO / "ui" / "requirements.txt").read_text(encoding="utf-8").splitlines()

    khai_bao = [
        d.strip().split(">=")[0].split("==")[0].strip()
        for d in dong
        if d.strip() and not d.strip().startswith("#")
    ]
    assert khai_bao, "ui/requirements.txt trống — có thể đã bị xoá nhầm"

    for goi in khai_bao:
        importlib.import_module(ten_import.get(goi, goi))
