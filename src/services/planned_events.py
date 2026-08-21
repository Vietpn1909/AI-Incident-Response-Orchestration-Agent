"""Việc đã lên lịch — giải thích một tín hiệu, KHÔNG bịt miệng mọi tín hiệu.

CHỦ SỞ HỮU: Đức

## Vấn đề

Bộ luật không biết *"việc này có người lên kế hoạch trước"*. Nên nó báo động cho:

    load test đã phê duyệt · pentest CISO đã ký · chaos engineering
    blue-green deploy · canary tự rollback · CDN đổi route

Đo ngày 18/08: **5 trong 10 case nhiễu** bị báo nhầm, và cả 5 cùng một nguyên
nhân này. Đây là nhóm báo nhầm lớn nhất trong bộ đo.

## Vì sao KHÔNG làm cách đơn giản

Cách đơn giản nhất là: có việc đã lên lịch thì bỏ qua hết. Nó ăn điểm ngay, và
trên bộ đo hiện tại **không bao giờ sai** — vì `maintenance_event` chỉ xuất hiện
ở case nhiễu, không case sự cố thật nào có.

Nhưng ngoài đời, **sự cố thật vẫn xảy ra trong lúc đang pentest**. Bịt miệng theo
cửa sổ thời gian là cách tạo ra đúng loại sự cố tệ nhất: hệ thống cháy trong lúc
mọi báo động bị tắt vì "đang có việc đã lên lịch".

Bộ đo hiện tại **không thể phát hiện** lỗi đó, vì nó không có case nào như vậy.
Nên nếu chỉ chạy theo điểm thì sẽ xây sai mà vẫn thấy điểm lên.

## Cách làm ở đây: giải thích có PHẠM VI

Một việc đã lên lịch chỉ giải thích được **thứ nó gây ra được**:

    pentest / load test đăng nhập  →  giải thích đăng nhập sai tăng
    chaos engineering / deploy     →  giải thích container restart
    đổi route CDN / batch job      →  giải thích độ trễ tăng

Pentest **không** giải thích service chết. Deploy **không** giải thích pool cạn.
Tín hiệu ngoài phạm vi thì vẫn báo động bình thường.

## Hai thứ không bao giờ được bỏ qua

1. **Service chết** (`up = 0`) — không việc đã lên lịch nào làm service ngừng
   phục vụ mà vẫn gọi là bình thường.
2. **Mất tín hiệu đo lường** — đó là lúc Agent đang mù. Bỏ qua nó nghĩa là bỏ qua
   chính khả năng mình đang không thấy gì.

Hai ngoại lệ này là lý do module tồn tại thay vì một dòng `if` trong `detect()`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.incident import IncidentSignal

logger = logging.getLogger(__name__)

#: Từ khoá trong mô tả việc đã lên lịch → những gì nó giải thích được.
#:
#: Khớp theo từ khoá trên văn bản tự do là cách yếu, và nói thẳng ra là yếu:
#: mô tả viết khác đi là trượt. Nhưng đây là dữ liệu đang có — ngoài đời chỗ này
#: sẽ là một API cửa sổ bảo trì có trường `affects` rõ ràng. Ghi ra để người sau
#: biết đây là chỗ cần thay, không phải chỗ đã xong.
_PHAM_VI: dict[str, tuple[str, ...]] = {
    "auth": ("pentest", "load test", "thử tải", "brute", "đăng nhập"),
    "crashloop": ("chaos", "deploy", "restart", "blue-green", "blue green", "rolling"),
    "latency": ("cdn", "route", "batch", "canary", "migration", "backfill"),
}

#: Tín hiệu KHÔNG bao giờ được bỏ qua, dù có việc gì đã lên lịch.
_KHONG_BAO_GIO_BO_QUA = ("mất tín hiệu", "up (service", "dự báo")


def giai_thich_duoc(
    mo_ta_viec: str | None,
    detector: str,
    metric_name: str = "",
) -> bool:
    """Việc đã lên lịch `mo_ta_viec` có giải thích được tín hiệu này không.

    Args:
        mo_ta_viec: Mô tả việc đã lên lịch, `None` nếu không có việc nào.
        detector: `"auth"` · `"crashloop"` · `"latency"` — đường phát hiện đã nổ.
        metric_name: Tên chỉ số đã kích hoạt, dùng để chặn hai ngoại lệ.

    Returns:
        `True` nghĩa là tín hiệu này **đã có lời giải thích**, không cần báo động.
    """
    if not mo_ta_viec:
        return False

    thap = metric_name.lower()
    if any(chan in thap for chan in _KHONG_BAO_GIO_BO_QUA):
        logger.info(
            "Có việc đã lên lịch (%s) nhưng KHÔNG bỏ qua %r — đây là loại tín hiệu "
            "không việc nào giải thích được",
            mo_ta_viec[:60], metric_name,
        )
        return False

    tu_khoa = _PHAM_VI.get(detector, ())
    mo_ta = mo_ta_viec.lower()
    khop = next((t for t in tu_khoa if t in mo_ta), None)
    if khop is None:
        logger.info(
            "Việc đã lên lịch (%s) KHÔNG giải thích được tín hiệu %s — vẫn báo động",
            mo_ta_viec[:60], detector,
        )
        return False

    logger.info(
        "Bỏ qua tín hiệu %s: đã có việc lên lịch giải thích (%r trong %r)",
        detector, khop, mo_ta_viec[:60],
    )
    return True


def bo_qua_duoc(signal: IncidentSignal, mo_ta_viec: str | None, detector: str) -> bool:
    """Việc đã lên lịch `mo_ta_viec` có giải thích được `signal` không.

    Đây là **chỗ duy nhất** quyết định việc đó. `giai_thich_duoc()` chỉ xét tên
    chỉ số; hàm này xét thêm những giới hạn cần đọc bằng chứng số.

    ⚠️ Gọi từ CẢ HAI đường — `detect.py` và `eval/case_suite.py`. Ngày 21/08 tôi
    thêm điều kiện bộ nhớ vào một đường thôi, và
    `test_pipeline_..._khop_voi_rule_truc_tiep` đỏ ngay. Đó là cùng loại lỗi với
    `_NODE_CHAIN` cắm cứng lệch khỏi graph: hai bản sao của một quyết định.

    Args:
        signal: Tín hiệu đã dựng, cần cả `metric_value` và `evidence`.
        mo_ta_viec: Mô tả việc đã lên lịch, `None` nếu không có.
        detector: `"auth"` · `"crashloop"` · `"latency"`.
    """
    from src.services import rules

    if not mo_ta_viec:
        return False

    # ── Deploy giải thích restart khi CẢ HAI đúng: ít lần, và không có áp lực
    # bộ nhớ. Thay pod là "old shutdown + new startup" = 2 lần, container mới thì
    # bộ nhớ thấp.
    #
    # Điều kiện bộ nhớ tìm ra bằng ĐO THẬT ngày 21/08, không bằng đọc code:
    # restart service 2 lần với deploy 5 phút trước, log ghi "UC-2 trên
    # service-thanh-toan: 2 lần restart" nhưng tín hiệu không ra tới danh sách
    # cuối. Đúng 2 lần thì hợp lý với blue-green deploy (case N12, bộ nhớ 0,35),
    # nhưng SAI với UC-2 thật — nó chết vì OOM nên bộ nhớ sát trần.
    if "restart" in signal.metric_name.lower():
        if signal.metric_value > rules.CRASHLOOP_RESTARTS:
            logger.info(
                "%.0f lần restart — ngoài mức một lần deploy giải thích được, vẫn báo động",
                signal.metric_value,
            )
            return False
        # ⚠️ Chỉ so bằng chứng nào là TỶ LỆ. `"bộ nhớ" in e.name` khớp cả
        # "đỉnh bộ nhớ 10 phút (trần 128 MB)" — giá trị tính bằng **MB** (54,
        # 108…), nên `>= 0.85` luôn đúng và điều kiện này vô hiệu. Đã vấp thật
        # ngày 21/08: đo lại thấy tín hiệu restart không bao giờ bị lọc nữa.
        #
        # Cùng loại lỗi `ui/labels.py` đã cảnh báo về hai chỉ số bộ nhớ. Hai
        # metric tỷ lệ đều kết thúc bằng "giới hạn container"; metric MB thì không.
        if any(
            e.name.endswith("giới hạn container") and e.value >= rules.MEMORY_NEAR_LIMIT_RATIO
            for e in signal.evidence
        ):
            logger.info("restart kèm bộ nhớ sát trần — không phải thay pod, vẫn báo động")
            return False

    return giai_thich_duoc(mo_ta_viec, detector, signal.metric_name)
