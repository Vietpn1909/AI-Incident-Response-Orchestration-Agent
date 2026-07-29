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

logger = logging.getLogger(__name__)

#: Các hành động Agent được phép đề xuất. Hành động ngoài danh sách này bị từ
#: chối ngay — tránh việc LLM sinh ra một `action` lạ rồi backend thi hành mù.
SUPPORTED_ACTIONS = frozenset({"rollback", "restart", "scale_up", "increase_pool"})


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
    return f"{action} trên {target}."
