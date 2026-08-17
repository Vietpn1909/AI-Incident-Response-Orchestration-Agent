"""Node `verify` — đo lại sau khi khắc phục để biết có thật sự đỡ hay không.

CHỦ SỞ HỮU: Đức

## Vì sao node này là mảnh cuối, không phải mảnh đầu

Trước 17/08 không làm được, và lý do đáng ghi: hành động khắc phục còn **mô
phỏng** — `remediation.execute()` ghi một dòng log rồi trả `succeeded=True` cắm
cứng. Không sửa gì thì đo lại vô nghĩa, chỉ đo được rằng sự cố vẫn còn đó.

Từ khi `executors.py` thi hành thật được (lỗi 100% → 0% trên UC-4), đo lại mới có
nghĩa.

## Chính Agent yêu cầu bước này

Runbook do `runbooks.py` sinh ra, bước 2, nguyên văn:

    "Theo dõi p95 và chỉ số đã kích hoạt sự cố — phải về gần baseline trong 3 phút"

và bước 4:

    "KHÔNG hồi phục thì deploy chỉ là trùng thời gian, không phải nguyên nhân —
     chẩn đoán lại thay vì rollback tiếp"

Agent dặn người trực đo, mà tự nó không đo. Node này khép chỗ đó lại.

Nó cũng là thứ duy nhất kiểm được câu Agent tự viết trong phần rủi ro: *"nếu
rollback không làm sự cố hết thì kết luận ban đầu đã sai"*. Không có `verify` thì
câu đó chỉ là lời nói.

## Đo lại bằng CHÍNH truy vấn đã phát hiện sự cố

Không viết truy vấn mới. `detect_incidents()` chạy lại nguyên vẹn, rồi xem service
này còn xuất hiện trong danh sách tín hiệu hay không.

Vì sao quan trọng: một truy vấn riêng cho `verify` sẽ là bản sao lặng lẽ lệch đi
khi ai sửa ngưỡng ở `rules.py` — cùng loại lỗi với `_NODE_CHAIN` cắm cứng lệch
khỏi graph (vá 15/08), và với việc chép PromQL sang `ui/status_page.py` mà
`ui/labels.py` đã cảnh báo. Dùng lại đường phát hiện thì "đã hồi phục" **theo
đúng định nghĩa** mà Agent dùng để mở war room.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.agents.nodes.detect import detect_incidents
from src.models.incident import IncidentSignal, Severity
from src.services.prometheus import PrometheusClient, PrometheusError

logger = logging.getLogger(__name__)

#: Mức độ nặng dần, để so xem sự cố có tệ hơn trước không.
_THU_TU = {Severity.P4: 1, Severity.P3: 2, Severity.P2: 3, Severity.P1: 4}


@dataclass(frozen=True)
class VerifyResult:
    """Kết quả đo lại một war room sau khắc phục."""

    #: `True` = service không còn tín hiệu sự cố nào.
    hoi_phuc: bool
    #: Tín hiệu còn lại, nếu chưa hồi phục.
    con_lai: IncidentSignal | None
    #: `True` khi mức độ nặng HƠN lúc phát hiện — cần gọi người ngay.
    te_hon: bool
    #: Câu để post lên war room.
    ket_luan: str


def verify(
    prometheus_client: PrometheusClient,
    service: str,
    *,
    muc_luc_phat_hien: Severity | None = None,
) -> VerifyResult | None:
    """Đo lại xem `service` còn sự cố không.

    Args:
        prometheus_client: Nguồn số đo.
        service: Tên service cần kiểm, khớp label `service` trong Prometheus.
        muc_luc_phat_hien: Mức độ lúc mở war room, để nhận ra tình huống **tệ
            hơn**. Bỏ trống thì không so.

    Returns:
        `VerifyResult`, hoặc `None` khi **không đo được** — Prometheus lỗi.

    Vì sao `None` chứ không phải "coi như đã hồi phục": không đo được nghĩa là
    không biết, và không biết thì tuyệt đối không được ghi "đã hồi phục" lên war
    room rồi đóng issue. Người trực đọc thấy đóng là đi ngủ.
    """
    try:
        tin_hieu = detect_incidents(prometheus_client)
    except PrometheusError as loi:
        # Không ném ra ngoài: Agent chạy vòng lặp dài. Nhưng cũng KHÔNG kết luận
        # gì — trả None để người gọi biết là chưa đo được, vòng sau thử lại.
        logger.error("verify %s: không đọc được Prometheus (%s)", service, loi)
        return None

    con_lai = next((s for s in tin_hieu if s.affected_service == service), None)

    if con_lai is None:
        logger.info("verify %s: không còn tín hiệu sự cố — đã hồi phục", service)
        return VerifyResult(
            hoi_phuc=True,
            con_lai=None,
            te_hon=False,
            ket_luan=(
                f"✅ ĐÃ HỒI PHỤC — {service} không còn tín hiệu sự cố nào.\n\n"
                "Đo lại bằng đúng những truy vấn đã phát hiện sự cố này, nên "
                "\"hồi phục\" ở đây cùng một định nghĩa với \"phát hiện\"."
            ),
        )

    te_hon = bool(
        muc_luc_phat_hien
        and _THU_TU.get(con_lai.severity, 0) > _THU_TU.get(muc_luc_phat_hien, 0)
    )

    if te_hon:
        logger.warning(
            "verify %s: TỆ HƠN — %s → %s",
            service, muc_luc_phat_hien.value, con_lai.severity.value,
        )
        ket_luan = (
            f"🔴 TỆ HƠN SAU KHẮC PHỤC — {service} đi từ "
            f"{muc_luc_phat_hien.value} xuống {con_lai.severity.value}.\n\n"
            f"{con_lai.metric_name} = {con_lai.metric_value:.3f} "
            f"(ngưỡng {con_lai.threshold:.3f}), vượt liên tục "
            f"{con_lai.breached_for_seconds:.0f}s.\n\n"
            "Cần người vào ngay. **Đừng thi hành thêm hành động nào** cho tới khi "
            "có người xem — hành động vừa rồi có thể đang làm tình hình xấu đi."
        )
    else:
        logger.info(
            "verify %s: CHƯA ĐỠ — %s = %.3f (ngưỡng %.3f)",
            service, con_lai.metric_name, con_lai.metric_value, con_lai.threshold,
        )
        # Nói thẳng khả năng chẩn đoán ban đầu sai. Đây đúng bước 4 trong runbook
        # mà Agent tự viết, và là chỗ duy nhất kiểm được câu nó tự nhận trong
        # phần rủi ro: "nếu rollback không làm sự cố hết thì kết luận đã sai".
        ket_luan = (
            f"⚠️ CHƯA ĐỠ — {service} vẫn còn tín hiệu sự cố sau khắc phục.\n\n"
            f"{con_lai.metric_name} = {con_lai.metric_value:.3f} "
            f"(ngưỡng {con_lai.threshold:.3f}), vượt liên tục "
            f"{con_lai.breached_for_seconds:.0f}s.\n\n"
            "Nghĩa là **chẩn đoán ban đầu có thể sai**. Theo runbook: đừng thi "
            "hành lại cùng một hành động, mà chẩn đoán lại từ bằng chứng."
        )

    return VerifyResult(hoi_phuc=False, con_lai=con_lai, te_hon=te_hon, ket_luan=ket_luan)
