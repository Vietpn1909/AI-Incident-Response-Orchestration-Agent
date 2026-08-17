"""Thực thi hành động khắc phục — CHỈ được gọi sau khi qua cổng HITL.

Không import module này ở chỗ nào mà chưa gọi
[`hitl.assert_human_approved()`](hitl.py) trước. Đó là ràng buộc bắt buộc của
đề bài: mọi hành động ảnh hưởng production phải có người phê duyệt.

Trạng thái hiện tại: hành động được **mô phỏng** và ghi log, chưa tác động thật.
Lý do là 2 service demo của Trung chưa tồn tại. Khi có rồi, thay thân các hàm
`_do_*` bằng lời gọi thật — chữ ký và kết quả trả về không đổi nên webhook và
Agent không phải sửa.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.services import executors

logger = logging.getLogger(__name__)

#: Chuỗi mà `RemediationResult.as_comment()` luôn bắt đầu bằng. Dùng làm
#: marker idempotency: trước khi thi hành, đọc comment Jira, thấy chuỗi này
#: thì bên kia (webhook hoặc poll) đã chạy rồi → bỏ qua.
#:
#: Jira là chỗ nhớ chung duy nhất mà cả webhook (Render) lẫn agent loop
#: (tiến trình khác) cùng nhìn thấy.
REMEDIATION_MARKER = "Đã thực thi khắc phục"

#: Cụm chữ `as_comment()` thêm vào khi hành động chỉ được mô phỏng.
#:
#: Nhờ nó mà phân biệt được "đã ghi nhận" với "đã làm thật" chỉ bằng cách đọc
#: comment — không cần thêm custom field hay chỗ lưu trạng thái nào khác.
DAU_MO_PHONG = "(mô phỏng)"


def is_already_remediated(
    client: Any, jira_key: str, *, cho_phep_nang_cap: bool = False
) -> bool:
    """Kiểm tra xem issue đã được thi hành remediation chưa.

    Đọc toàn bộ comment text trên issue, tìm marker ``REMEDIATION_MARKER``.
    Comment này do ``RemediationResult.as_comment()`` sinh ra và được cả webhook
    lẫn poll post lên Jira SAU khi execute thành công.

    Args:
        client: ``JiraClient`` (Protocol) — gọi ``get_comment_bodies()``.
        jira_key: Issue cần kiểm tra.

    Args (tiếp):
        cho_phep_nang_cap: `True` thì một bản ghi **chỉ mô phỏng** KHÔNG chặn nữa.
            Dùng khi người gọi thật sự thi hành được (`REMEDIATION_REAL=1` và có
            Docker) — xem lý do đo được ở thân hàm.

    Returns:
        ``True`` nếu đã thi hành rồi → **không được execute lại**.
    """
    try:
        bodies = client.get_comment_bodies(jira_key)
    except Exception:
        # Lỗi Jira khi đọc comment: an toàn hơn là BỎ QUA (không execute).
        # Lý do: nếu đọc hỏng mà vẫn cho execute, hai bên đều trượt guard →
        # vẫn bị duplicate. Bỏ qua thì tệ nhất là tạm không execute, vòng sau
        # sẽ thử lại.
        logger.warning("%s: không đọc được comment để kiểm idempotency — bỏ qua", jira_key)
        return True  # treat as already done to be safe
    da_thi_hanh = [b for b in bodies if REMEDIATION_MARKER in b]
    if not da_thi_hanh:
        return False

    if not cho_phep_nang_cap:
        return True

    # Chỉ có dấu MÔ PHỎNG thì chưa có gì được sửa — không được chặn bản thật.
    #
    # Đo ngày 17/08 khi chạy UC-4: người trực kéo issue sang `Remediating`, Jira
    # Automation gọi webhook trên Render, Render thi hành **mô phỏng** và post
    # comment. Lệnh chạy local có `REMEDIATION_REAL=1` — tức đường DUY NHẤT sửa
    # thật được, vì chỉ máy local có Docker — sau đó bị guard chặn với
    # `already_done: true`. Sự cố vẫn nguyên, 100% request vẫn lỗi.
    #
    # Render không bao giờ sửa thật được: nó không thấy Docker lẫn Prometheus của
    # người demo. Nên coi bản ghi mô phỏng của nó là "đã xong" là sai — nó chỉ
    # ghi nhận việc phê duyệt.
    da_lam_that = any(DAU_MO_PHONG not in b for b in da_thi_hanh)
    if da_lam_that:
        return True

    logger.info(
        "%s: chỉ có bản ghi MÔ PHỎNG — cho phép thi hành thật ghi đè", jira_key
    )
    return False

#: Các hành động Agent được phép đề xuất. Hành động ngoài danh sách này bị từ
#: chối ngay — tránh việc LLM sinh ra một `action` lạ rồi backend thi hành mù.
SUPPORTED_ACTIONS = frozenset(
    {
        "rollback",
        "restart",
        "scale_up",
        "increase_pool",
        # UC-3: chặn burst xác thực thất bại. Đây là hành động ảnh hưởng người
        # dùng thật (chặn truy cập), nên vẫn phải qua cổng HITL như mọi hành
        # động khác — một hành động bảo mật cũng không được để AI tự quyết.
        "rate_limit",
        "block_ip",
    }
)


class UnsupportedActionError(ValueError):
    """Hành động không nằm trong `SUPPORTED_ACTIONS`."""


@dataclass
class RemediationResult:
    """Kết quả thi hành, dùng để post comment lên Jira và ghi vào postmortem."""

    action: str
    target: str
    succeeded: bool
    detail: str
    approved_by: str
    simulated: bool = True
    params: dict[str, Any] = field(default_factory=dict)

    def as_comment(self) -> str:
        """Nội dung comment post lên war room."""
        status = "thành công" if self.succeeded else "THẤT BẠI"
        mode = " (mô phỏng)" if self.simulated else ""
        return (
            f"Đã thực thi khắc phục{mode}: {self.action} → {self.target} — {status}.\n\n"
            f"Người phê duyệt: {self.approved_by}\n\n"
            f"{self.detail}"
        )


def execute(
    action: str,
    target: str,
    *,
    approved_by: str,
    params: dict[str, Any] | None = None,
) -> RemediationResult:
    """Thi hành hành động khắc phục đã được phê duyệt.

    Args:
        action: Một trong `SUPPORTED_ACTIONS`.
        target: Service chịu tác động, vd. "service-thanh-toan".
        approved_by: accountId người đã phê duyệt — do
            `hitl.assert_human_approved()` trả về. Bắt buộc truyền để không thể
            gọi hàm này mà bỏ qua cổng phê duyệt một cách vô tình.
        params: Tham số của hành động, vd. `{"to_version": "v1.4.1"}`.

    Raises:
        UnsupportedActionError: hành động không được phép.
        ValueError: thiếu `approved_by`.
    """
    if not approved_by:
        raise ValueError(
            "Thiếu approved_by — hành động khắc phục phải đi kèm người phê duyệt. "
            "Gọi hitl.assert_human_approved() trước và truyền accountId nó trả về."
        )
    if action not in SUPPORTED_ACTIONS:
        raise UnsupportedActionError(
            f"Hành động '{action}' không được phép. Chỉ nhận: {sorted(SUPPORTED_ACTIONS)}"
        )

    params = params or {}
    logger.info("Thực thi %s trên %s, params=%s, duyệt bởi %s", action, target, params, approved_by)

    # Thử thi hành THẬT trước. Trả `None` nghĩa là cặp (action, target) không nằm
    # trong danh sách trắng, hoặc `REMEDIATION_REAL` chưa bật — khi đó rơi về
    # đường mô phỏng y như cũ.
    #
    # Đặt ở đây chứ không ở webhook: mọi lời gọi `execute()` đều phải đi qua cùng
    # một chỗ, kể cả lời gọi từ test hay script. Để webhook tự quyết thì sẽ có
    # ngày xuất hiện đường thứ hai không qua kiểm.
    that = executors.thi_hanh_that(action, target)
    if that is not None:
        thanh_cong, mo_ta = that
        logger.info("Thi hành THẬT %s → %s: %s", action, target, "OK" if thanh_cong else "HỎNG")
        return RemediationResult(
            action=action,
            target=target,
            succeeded=thanh_cong,
            detail=mo_ta,
            approved_by=approved_by,
            simulated=False,
            params=params,
        )

    detail = _describe(action, target, params)
    return RemediationResult(
        action=action,
        target=target,
        succeeded=True,
        detail=detail,
        approved_by=approved_by,
        simulated=True,
        params=params,
    )


def _describe(action: str, target: str, params: dict[str, Any]) -> str:
    """Mô tả việc đã làm. Khi có service thật thì đây là chỗ gọi hành động thật."""
    if action == "rollback":
        version = params.get("to_version", "phiên bản trước")
        return f"Rollback {target} về {version}."
    if action == "restart":
        return f"Restart {target}."
    if action == "scale_up":
        return f"Tăng số instance của {target} lên {params.get('replicas', '?')}."
    if action == "increase_pool":
        return f"Tăng connection pool của {target} lên {params.get('pool_size', '?')}."
    if action == "rate_limit":
        return f"Giới hạn tốc độ {target} ở {params.get('limit', '?')} request/phút."
    if action == "block_ip":
        return f"Chặn nguồn {params.get('ip', '?')} truy cập {target}."
    return f"{action} trên {target}."
