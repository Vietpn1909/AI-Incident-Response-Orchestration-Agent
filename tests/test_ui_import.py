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
báo), nên test không cần dựng server.

## Vì sao phải giả lập `requests`, không chỉ đổi `API_URL`

`war_room.py` gọi `load_incidents()` **ngay ở cấp module**, và `API` mặc định là
bản deploy trên Render. Nên chỉ riêng việc import file đã đi ra Internet.

Đo ngày 13/08 lúc vừa thêm test này: cùng bộ test chạy **31,48s** lượt đầu rồi
**5,99s** lượt sau — chênh lệch là thời gian Render khởi động nguội, mà
`timeout=60` nên xấu nhất là treo cả phút. Test khói phụ thuộc dịch vụ ngoài thì
vừa chậm vừa đỏ ngẫu nhiên.

Cách đầu tiên đã thử là trỏ `API_URL` vào `127.0.0.1:1` cho `requests` lỗi ngay.
Không dùng được, và lý do đáng ghi lại: `war_room.py` bắt lỗi đó rồi gọi
`st.error(...)` + `st.stop()`, nhưng **`st.stop()` là no-op khi chạy ngoài
`streamlit run`** — nó không ném gì, nên module chạy tiếp xuống dòng dùng
`incidents` chưa được gán và chết bằng `NameError`.

Chạy thật bằng `streamlit run` thì `st.stop()` hoạt động đúng, nên đây **không
phải lỗi production** — chỉ là đường lỗi không kiểm được ở chế độ bare.

Nên giả lập `requests.get` trả danh sách rỗng, cho module chạy trọn **đường bình
thường**. Vừa không chạm mạng, vừa phủ nhiều hơn cách trỏ URL chết: nó thực sự
chạy tới phần vẽ, tức nơi dùng `plotly`.
"""

from __future__ import annotations

import importlib
import pathlib
import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

GOC_REPO = pathlib.Path(__file__).resolve().parent.parent


def _requests_rong() -> MagicMock:
    """`requests.get` giả — trả dữ liệu RỖNG nhưng **đúng kiểu theo endpoint**.

    Không thể trả `[]` cho mọi thứ: `war_room.py` gọi `/api/incidents` (danh
    sách) còn `status_page.py` gọi `/api/status` (đối tượng). Trả nhầm kiểu thì
    module chết bằng `TypeError: list indices must be integers or slices, not
    str` — đúng lỗi bản đầu của test này mắc phải.

    Prometheus (`/api/v1/query`) trả theo khuôn riêng của nó, cũng phải giả cho
    đúng, nếu không `status_page.py` đọc `goi.get("status")` sẽ vỡ.
    """

    def _get(url: str, *args, **kwargs) -> MagicMock:
        reply = MagicMock()
        reply.raise_for_status.return_value = None
        reply.status_code = 200
        if "/api/v1/query" in url:
            reply.json.return_value = {"status": "success", "data": {"result": []}}
        elif "/api/status" in url:
            reply.json.return_value = _status_rong()
        else:  # /api/incidents và /api/incidents/{key}
            reply.json.return_value = []
        return reply

    return MagicMock(side_effect=_get)


def _status_rong() -> dict:
    """Payload `/api/status` rỗng, dựng TỪ model `StatusPage`.

    Không viết tay dict theo trí nhớ. Bản đầu của test này gõ tay
    `{"services": [], "incidents": []}` và chết bằng `KeyError: 'updated_at'` —
    tức đoán sai đúng cái khoá quan trọng nhất. Dựng từ model thì model đổi field
    là mock đi theo, không lệch âm thầm.
    """
    from src.models.incident import StatusPage

    return StatusPage(
        updated_at=datetime.now(UTC), services=[], active_incidents=[]
    ).model_dump(mode="json")


@pytest.mark.parametrize("ten_module", ["ui.war_room", "ui.status_page", "ui.labels"])
def test_trang_ui_import_duoc(ten_module: str):
    """Thiếu dependency hay gãy import là đỏ ở đây, không phải đỏ lúc demo."""
    if str(GOC_REPO) not in sys.path:
        sys.path.insert(0, str(GOC_REPO))

    # Buộc nạp lại: file test khác có thể đã import sẵn mà không có mock.
    sys.modules.pop(ten_module, None)

    with patch("requests.get", _requests_rong()):
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


def test_khong_mo_san_su_co_da_dong():
    """Board sạch thì màn mở đầu phải là "hệ thống bình thường", không phải phiếu cũ.

    `war_room.py` chọn phiếu mở sẵn theo thứ tự: đang chờ duyệt → đang diễn ra →
    (trước 17/08) phiếu gần nhất bất kể trạng thái. Nhánh cuối làm trang tự mâu
    thuẫn: cột trái ghi "không có sự cố nào đang diễn ra" trong khi khung chính
    dựng nguyên một phiếu P1 màu đỏ đã đóng từ lâu.

    Đây là màn hình MỞ ĐẦU buổi demo, lúc board vừa dọn sạch — nên nó là thứ đầu
    tiên người xem nhìn thấy.

    Vá lần đầu 12/08, **mất khi dựng lại UI ngày 17/08**. Test này đọc thẳng mã
    nguồn vì logic chọn nằm ở cấp module, chạy lúc import, không gói trong hàm
    nào để gọi lại được.
    """
    nguon = (GOC_REPO / "ui" / "war_room.py").read_text(encoding="utf-8")

    assert "dau_tien = cho_duyet or dang_mo" in nguon, "không tìm thấy logic chọn phiếu mở sẵn"
    assert "or (ds[0] if ds else None)" not in nguon, (
        "war_room.py lại rơi về `ds[0]` — sẽ mở sẵn một sự cố ĐÃ ĐÓNG khi board sạch"
    )
